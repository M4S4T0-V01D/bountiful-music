"""The two LMMS instruments the Record desk uses, played without LMMS: sf2player (a SoundFont patch; LMMS runs
libfluidsynth for it, and so does this, through ctypes) and AudioFileProcessor (a one-shot sample played
chromatically). Same voice specs and note lists as engine.lmms.render_parts, so a part can go either way.
"""
from __future__ import annotations

import ctypes
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

from . import fx
from .lmms import SAMPLES, TPB, _find, sample_root
from .share import find_libfluidsynth

BASE_VELOCITY = 63      # LMMS's default MIDI base velocity: note vol 100 -> velocity 63
DEFAULT_RELEASE = 128   # frames LMMS fades a sample note out over when there's no envelope
INTERP_7TH = 7          # what LMMS's sf2player asks for at its usual quality
GEN_COARSETUNE = 51


def can_play(voice: dict) -> bool:
    """True when this voice needs no LMMS: no LMMS effects, and sf2player (with FluidSynth around) or a sample."""
    if voice.get("fx"):
        return False
    if voice.get("plugin") == "sf2player":
        return _fluid() is not None and Path(str(voice.get("attrs", {}).get("src", ""))).is_file()
    return "sample" in voice and not any(k in voice for k in ("zyn", "xpf", "lv2", "plugin"))


def _key(voice: dict, key: int) -> int:
    """the MIDI note an LMMS key sounds: LMMS keys sit an octave below MIDI, basenote = 57 - transpose"""
    return key + 12 + voice.get("transpose", 0)


# ---------------------------------------------------------------- sf2player
_lib = None
_lib_lock = threading.Lock()


def _fluid():
    global _lib
    with _lib_lock:
        if _lib is None:
            path = find_libfluidsynth()
            try:
                L = ctypes.CDLL(path) if path else None
            except OSError:
                L = None
            if L is not None:
                vp, ci, cd, cs = ctypes.c_void_p, ctypes.c_int, ctypes.c_double, ctypes.c_char_p
                for name, res, args in [("new_fluid_settings", vp, []), ("delete_fluid_settings", None, [vp]),
                                        ("fluid_settings_setnum", ci, [vp, cs, cd]), ("fluid_settings_setint", ci, [vp, cs, ci]),
                                        ("new_fluid_synth", vp, [vp]), ("delete_fluid_synth", None, [vp]),
                                        ("fluid_synth_sfload", ci, [vp, cs, ci]), ("fluid_synth_program_select", ci, [vp, ci, ci, ci, ci]),
                                        ("fluid_synth_set_interp_method", ci, [vp, ci, ci]), ("fluid_synth_set_gain", None, [vp, ctypes.c_float]),
                                        ("fluid_synth_noteon", ci, [vp, ci, ci, ci]), ("fluid_synth_noteoff", ci, [vp, ci, ci]),
                                        ("fluid_synth_write_float", ci, [vp, ci, vp, ci, ci, vp, ci, ci]),
                                        ("fluid_synth_pitch_bend", ci, [vp, ci, ci]), ("fluid_synth_pitch_wheel_sens", ci, [vp, ci, ci]),
                                        ("fluid_synth_get_polyphony", ci, [vp]),
                                        ("fluid_synth_get_voicelist", None, [vp, ctypes.POINTER(vp), ci, ci]),
                                        ("fluid_voice_get_channel", ci, [vp]), ("fluid_voice_get_key", ci, [vp]),
                                        ("fluid_voice_is_on", ci, [vp]),
                                        ("fluid_voice_gen_get", ctypes.c_float, [vp, ci]),
                                        ("fluid_voice_gen_set", None, [vp, ci, ctypes.c_float]),
                                        ("fluid_voice_update_param", None, [vp, ci])]:
                    f = getattr(L, name)
                    f.restype, f.argtypes = res, args
                for level in (2, 3, 4):           # warnings, info, debug (e.g. "SDL3 not initialized"): not ours to fix
                    L.fluid_set_log_function(level, None, None)
            _lib = L or False
        return _lib or None


def _events(voice: dict, notes: list, spb: float) -> list:
    """(frame, on, key, velocity), offs before ons at the same frame. A key held by several notes stays on until
    the last one ends, as in LMMS's sf2player (it counts the notes running on each key). Frames are truncated as
    LMMS does: FluidSynth starts notes on 64-frame block edges, so rounding up by one frame can move a note 64."""
    ev = []
    for tick, length, key, vol in notes:
        k = int(np.clip(_key(voice, key), 0, 127))
        ev += [(int(tick * spb), 1, k, int(np.clip(vol * BASE_VELOCITY // 100, 1, 127))),
               (int((tick + max(1, length)) * spb), 0, k, 0)]
    ev.sort(key=lambda e: (e[0], e[1]))
    running, out = [0] * 128, []
    for e in ev:
        running[e[2]] += 1 if e[1] else -1
        if e[1] or running[e[2]] <= 0:
            out.append(e)
    return out


def sf2(voice: dict, notes: list, bpm: float, n: int, sr: int) -> np.ndarray:
    L = _fluid()
    if L is None:
        raise RuntimeError("FluidSynth isn't installed (no libfluidsynth found)")
    a = voice.get("attrs", {})
    st = L.new_fluid_settings()
    L.fluid_settings_setnum(st, b"synth.sample-rate", float(sr))
    L.fluid_settings_setint(st, b"synth.reverb.active", int(a.get("reverbOn", 0)))
    L.fluid_settings_setint(st, b"synth.chorus.active", int(a.get("chorusOn", 0)))
    L.fluid_settings_setint(st, b"synth.polyphony", 256)
    syn = L.new_fluid_synth(st)
    try:
        sfid = L.fluid_synth_sfload(syn, str(a["src"]).encode(), 1)
        if sfid < 0:
            raise RuntimeError(f"FluidSynth couldn't load {a['src']}")
        if L.fluid_synth_program_select(syn, 0, sfid, int(a.get("bank", 0)), int(a.get("patch", 0))) != 0:
            raise RuntimeError(f"no patch {a.get('bank', 0)}:{a.get('patch', 0)} in {Path(a['src']).name}")
        L.fluid_synth_set_interp_method(syn, -1, INTERP_7TH)
        L.fluid_synth_set_gain(syn, float(a.get("gain", 1.0)))   # as LMMS sets it
        L.fluid_synth_pitch_wheel_sens(syn, 0, 1)    # LMMS's pitch knob: range 1, centre sent as 8191
        L.fluid_synth_pitch_bend(syn, 0, 8191)
        poly = L.fluid_synth_get_polyphony(syn)
        voices = (ctypes.c_void_p * poly)()
        out = np.zeros((n, 2), np.float32)
        pos = 0

        def retune(key):
            """LMMS re-sets each new voice's coarse tune after note-on (its detuning hook), which re-derives the
            voice's pitch: about a cent flat of a plain note-on"""
            L.fluid_synth_get_voicelist(syn, voices, poly, -1)
            for v in voices:
                if not v:
                    break
                if L.fluid_voice_get_channel(v) == 0 and L.fluid_voice_get_key(v) == key and L.fluid_voice_is_on(v):
                    L.fluid_voice_gen_set(v, GEN_COARSETUNE, L.fluid_voice_gen_get(v, GEN_COARSETUNE))
                    L.fluid_voice_update_param(v, GEN_COARSETUNE)

        def run(upto):
            nonlocal pos
            upto = min(upto, n)
            while pos < upto:
                k = min(upto - pos, 8192)
                v = out[pos:pos + k]
                p = v.ctypes.data
                L.fluid_synth_write_float(syn, k, p, 0, 2, p + 4, 0, 2)   # interleaved stereo, straight into out
                pos += k
        for frame, on, key, vel in _events(voice, notes, 60 / bpm / TPB * sr):
            if frame >= n:
                break
            run(frame)
            if on:
                L.fluid_synth_noteon(syn, 0, key, vel)
                retune(key)
            else:
                L.fluid_synth_noteoff(syn, 0, key)
        run(n)
        return out
    finally:
        L.delete_fluid_synth(syn)
        L.delete_fluid_settings(st)


# ---------------------------------------------------------------- AudioFileProcessor
_smp: dict = {}


def _sample(path: Path, sr: int) -> np.ndarray:
    k = (str(path), sr)
    if k not in _smp:
        x, fsr = sf.read(str(path), dtype="float32", always_2d=True)
        if x.shape[1] == 1:
            x = np.repeat(x, 2, 1)
        _smp[k] = (fx.resample(x[:, :2], fsr / sr) if fsr != sr else x[:, :2]).astype(np.float32)
    return _smp[k]


def sampler(voice: dict, notes: list, bpm: float, n: int, sr: int) -> np.ndarray:
    """AudioFileProcessor: the sample (between start and end) resampled to each note's pitch, louder with the note's
    vol, cut at note-off with LMMS's short fade or the voice's release (LMMS envelope time: knob² x 5 s)."""
    path = _find(SAMPLES, voice["sample"])
    root = voice.get("root") or sample_root(path)
    src = _sample(path, sr)
    s0, s1 = int(len(src) * voice.get("start", 0)), max(1, int(len(src) * voice.get("end", 1)))
    src = src[s0:s1] * (voice.get("amp", 100) / 100)
    rel = int(voice["release"] ** 2 * 5 * sr) if voice.get("release") else DEFAULT_RELEASE
    out = np.zeros((n, 2), np.float32)
    spb = 60 / bpm / TPB * sr
    cache = {}
    for tick, length, key, vol in notes:
        i = int(tick * spb)                       # frames truncated, as LMMS places notes
        dur = int((tick + max(1, length)) * spb) - i
        if i >= n:
            continue
        midi = _key(voice, key)
        if midi not in cache:
            cache[midi] = fx.resample(src, 2 ** ((midi - root) / 12))
        y = cache[midi][:dur + rel].copy()
        if len(y) > dur:
            y[dur:] *= np.linspace(1, 0, len(y) - dur, endpoint=False)[:, None]
        k = min(len(y), n - i)
        out[i:i + k] += y[:k] * (vol / 100)
    return out


def render_parts(parts: dict[str, tuple[dict, list]], bpm: float, n_samples: int, sr: int) -> dict[str, np.ndarray]:
    """Like engine.lmms.render_parts, for voices can_play() accepts; parts render side by side."""
    def one(item):
        name, (voice, notes) = item
        x = sf2(voice, notes, bpm, n_samples, sr) if voice.get("plugin") == "sf2player" else sampler(voice, notes, bpm, n_samples, sr)
        return name, x.astype(np.float32)
    with ThreadPoolExecutor(4) as ex:
        return dict(ex.map(one, parts.items()))
