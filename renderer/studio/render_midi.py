#!/usr/bin/env python3
"""Render any MIDI file to audio through an instrument map (TOML). This is the library behind MIDI Studio,
and it also works on the command line.

    python studio/render_midi.py song.mid map.toml [--out DIR] [--stems DIR] [--bars 33-40] [--only lead,bass]
                                                   [--no-stems] [--no-mp3] [--name slug]

Each MIDI track is matched to a [tracks.<name>] table, by track name and then by `channel` (0-based;
drums are channel 9). A track table chooses the sound:
  kind = "organ" | "analogbass" | "polylead" | "pad" | "rhodes" | "bass" | "vibes" | "horn" | "piano" | "stab"
         | "vox" | "reese" | "guitar" | "sampler"          + preset = "file.json" (or an inline table)
  kind = "pyvoice", preset = { module = "/abs/voice.py", fn = "note", ... }   a note function from another program
  layers = [{ kind, preset, gain_db, transpose }, ...]    several sounds at once
  kind = "lmms", voice = { zyn = "Bank/0001-Name.xiz" }   any sound from the LMMS atlas, played by headless LMMS
         (falls back to `fallback = { kind, preset }` if LMMS fails, so a render always finishes)
and the mix: gain_db, pan, hp, lp, eq, drive, crush, chorus, leslie, width, mono, sends, duck, transpose, mute, solo.
Drum tracks have map / sounds / stems tables (a sound: samples, synth, or py = { module, fn, args }).
Sends: room, plate, echo, spring (or your own [sends.x] of type reverb / delay / spring). `variants` (default 6 for
pyvoice, else 1): how many takes of an identical note are synthesised, so drift and noise differ between repeats.
Bar-based [[automation]]: lowpass sweeps and gain moves.

Output lines starting with "PROGRESS i/n" are read by the GUI.
"""
from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
import time
import tomllib
from pathlib import Path

import mido
import numpy as np

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))
from engine import fx, synth  # noqa: E402
from engine import drums as DR  # noqa: E402
from engine.export import analyse, mp3, write_audio  # noqa: E402
from engine.render import master  # noqa: E402
from engine.theory import hz  # noqa: E402

SR = fx.SR
TAU = 2 * np.pi
PROJECTS = ENGINE.parent


# ------------------------------------------------------------------ MIDI in

def read_midi(path: Path) -> tuple[list[dict], float, list]:
    """-> notes [{track, ch, start, end (s), pitch, vel 0-1, program}], first tempo (bpm), tempo map."""
    mf = mido.MidiFile(str(path))
    ppq = mf.ticks_per_beat
    tempos = [(0, 500000)]
    for tr in mf.tracks:
        tick = 0
        for m in tr:
            tick += m.time
            if m.type == "set_tempo":
                tempos.append((tick, m.tempo))
    tempos = sorted(dict(tempos).items())

    def sec(tick):
        s, last_t, last_tempo = 0.0, 0, tempos[0][1]
        for t, tempo in tempos[1:]:
            if t >= tick:
                break
            s += (t - last_t) * last_tempo / ppq / 1e6
            last_t, last_tempo = t, tempo
        return s + (tick - last_t) * last_tempo / ppq / 1e6

    notes = []
    for i, tr in enumerate(mf.tracks):
        name = next((m.name for m in tr if m.type == "track_name"), "") or f"track{i}"
        tick, held, prog = 0, {}, {}
        for m in tr:
            tick += m.time
            if m.type == "program_change":
                prog[m.channel] = m.program
            elif m.type == "note_on" and m.velocity > 0:
                held.setdefault((m.channel, m.note), []).append((tick, m.velocity))
            elif m.type in ("note_off", "note_on"):
                k = (m.channel, m.note)
                if held.get(k):
                    t0, v = held[k].pop(0)
                    notes.append({"track": name, "ch": m.channel, "start": sec(t0), "end": sec(tick), "pitch": m.note,
                                  "vel": v / 127, "program": prog.get(m.channel)})
    first = tempos[1][1] if len(tempos) > 1 and tempos[1][0] == 0 else tempos[-1][1] if len(tempos) > 1 else tempos[0][1]
    return sorted(notes, key=lambda n: n["start"]), mido.tempo2bpm(first), tempos


def midi_summary(path: Path) -> dict:
    """Tracks of a MIDI file for the GUI: name, channel, note count, range, GM program, first bar."""
    notes, bpm, _ = read_midi(path)
    bar_s = 4 * 60 / bpm
    tracks: dict[str, dict] = {}
    for n in notes:
        t = tracks.setdefault(n["track"], {"name": n["track"], "ch": n["ch"], "notes": 0, "lo": 127, "hi": 0, "program": n["program"],
                                            "first_bar": int(n["start"] // bar_s) + 1, "pitches": {}})
        t["notes"] += 1
        t["lo"], t["hi"] = min(t["lo"], n["pitch"]), max(t["hi"], n["pitch"])
        t["pitches"][n["pitch"]] = t["pitches"].get(n["pitch"], 0) + 1
    end = max((n["end"] for n in notes), default=0)
    return {"bpm": bpm, "seconds": end, "bars": int(np.ceil(end / bar_s)), "tracks": list(tracks.values())}


# ------------------------------------------------------------------ instruments

def poly_lead(midi, vel, dur, p, rng):
    """Warm early-90s poly synth voice: detuned band-limited saws + a pulse, 24 dB low-pass with its own
    envelope, delayed vibrato. No supersaw stack."""
    rel = p["release"]
    n = int((dur + rel) * SR)
    t = np.arange(n) / SR
    f0 = hz(midi)
    vib = 1 + (2 ** (p.get("vib_cents", 6) / 1200) - 1) * np.sin(TAU * 5.3 * t) * np.clip((t - 0.3) / 0.5, 0, 1)
    top = min(p.get("max_hz", 9000), SR * 0.45)
    y = np.zeros(n)
    for det, amp, shape in [(d, 1.0, "saw") for d in p["detune"]] + [(0.0, p.get("pulse", 0.0), "square")]:
        if amp <= 0:
            continue
        ph = np.cumsum(TAU * f0 * 2 ** (det / 1200) * vib / SR) + rng.random() * TAU
        for k in range(1, int(top / f0) + 1):
            if shape == "square" and k % 2 == 0:
                continue
            y += amp * np.sin(k * ph) / k
    y /= len(p["detune"]) + p.get("pulse", 0.0)
    cut = p["cutoff"] * (1 + p.get("key_track", 0.5) * (f0 / 440 - 1)) + p["env_amount"] * (0.4 + 0.6 * vel) * np.exp(-t / p["filter_decay"])
    y = fx.sweep(fx.sweep(y.astype(np.float32), "lowpass", cut, block=128), "lowpass", cut, block=128)
    a, d, s = p["attack"], p["decay"], p["sustain"]
    rl = np.clip(1 - (t - dur) / rel, 0, 1)
    held = s + (1 - s) * np.exp(-max(dur - a, 0) / d)
    amp = np.where(t < dur, np.where(t < a, t / a, s + (1 - s) * np.exp(-(t - a) / d)), held * rl)
    y = np.tanh(y * amp * p.get("drive", 1.2)) / np.tanh(p.get("drive", 1.2))
    return (y * (0.45 + 0.55 * vel)).astype(np.float32)


_PYVOICE: dict = {}


def py_voice(midi, vel, dur, p, rng, from_midi=None):
    """kind = "pyvoice": a note function from another program's Python file, preset = { module = "/abs/file.py",
    fn = "note", ... } (the whole preset is passed on). Called as fn(midi, vel, dur, p, rng, from_midi=...) -> mono float32."""
    return np.asarray(py_fn(p["module"], p.get("fn", "note"))(midi, vel, dur, p, rng, from_midi=from_midi), np.float32)


def py_fn(module: str, fn: str):
    """A function from another program's Python file (loaded once)."""
    key = (module, fn)
    if key not in _PYVOICE:
        import importlib.util
        spec = importlib.util.spec_from_file_location(f"pyvoice_{len(_PYVOICE)}", module)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _PYVOICE[key] = getattr(mod, fn)
    return _PYVOICE[key]


GLIDERS = {"analogbass", "bass", "horn", "vox", "reese", "guitar", "pyvoice"}
NOTE_FN = {"organ": synth.organ_note, "analogbass": synth.analog_bass_note, "polylead": poly_lead, "rhodes": synth.rhodes_note,
           "bass": synth.bass_note, "vibes": synth.vibes_note, "horn": synth.horn_note, "piano": synth.piano_note,
           "stab": synth.stab_note, "vox": synth.vox_note, "reese": synth.reese_note, "guitar": synth.guitar_note,
           "sampler": synth.sampler_note, "pyvoice": py_voice, "pad": None}
KINDS = list(NOTE_FN)


def required_keys(kind: str) -> set[str]:
    """Preset keys a kind needs (read from the synth function's source), so a GUI can list only fitting presets."""
    fn = synth.pad_chord if kind == "pad" else NOTE_FN[kind]
    return set(re.findall(r'\bp\["(\w+)"\]', inspect.getsource(fn)))


def note_audio(kind, midi, vel, dur, p, rng, prev):
    if kind == "pad":
        return synth.pad_chord([midi], dur, p, rng) * (0.4 + 0.6 * vel)
    fn = NOTE_FN[kind]
    if kind in GLIDERS:
        return fn(midi, vel, dur, p, rng, from_midi=prev)
    return fn(midi, vel, dur, p, rng)


def preset_dirs(cfg: dict, base: Path) -> list[Path]:
    dirs = [Path(d) for d in cfg.get("preset_dirs", [])] + [base / "presets", ENGINE / "presets"]
    return [d for d in dirs if d.is_dir()]


def load_preset(spec, dirs: list[Path]) -> dict:
    if isinstance(spec, dict):
        return spec
    p = Path(spec)
    if p.is_absolute() and p.exists():
        return json.loads(p.read_text())
    for d in dirs:
        if (d / spec).exists():
            return json.loads((d / spec).read_text())
    raise FileNotFoundError(f"preset {spec} not found in {[str(d) for d in dirs]}")


def render_engine(notes, cfg, dirs, n, rng, t0) -> np.ndarray:
    layers = cfg.get("layers") or [{"kind": cfg["kind"], "preset": cfg.get("preset", {}), "gain_db": 0.0}]
    out = np.zeros(n, np.float32)
    for L in layers:
        p = load_preset(L.get("preset", {}), dirs)
        prev_end, prev_pitch = -1.0, None
        cache: dict = {}            # identical notes are synthesised once (or `variants` times, so drift and noise differ)
        seen: dict = {}
        variants = max(1, int(L.get("variants", cfg.get("variants", 6 if L["kind"] == "pyvoice" else 1))))
        tr = L.get("transpose", 0) + cfg.get("transpose", 0)
        for nt in notes:
            dur = round(nt["end"] - nt["start"], 3)
            vel = round(nt["vel"] * 64) / 64
            glide = prev_pitch if (L["kind"] in GLIDERS and nt["start"] - prev_end < cfg.get("glide_gap", 0.03)) else None
            key = (nt["pitch"], dur, vel, glide)
            seen[key] = seen.get(key, -1) + 1
            key += (seen[key] % variants,)
            if key not in cache:
                cache[key] = note_audio(L["kind"], nt["pitch"] + tr, vel, max(dur, 0.01), p, rng, None if glide is None else glide + tr)
            y = cache[key]
            i = int((nt["start"] - t0) * SR)
            if 0 <= i < n:
                m = min(len(y), n - i)
                out[i:i + m] += y[:m] * fx.db(L.get("gain_db", 0.0))
            prev_end, prev_pitch = nt["end"], nt["pitch"]
    return out


def lmms_notes(notes, bpm, t0, transpose=0):
    from engine.lmms import TPB
    beat = 60 / bpm
    return [(max(0, int(round((nt["start"] - t0) / beat * TPB))), max(1, int(round((nt["end"] - nt["start"]) / beat * TPB))),
             int(nt["pitch"]) - 12 + transpose, int(np.clip(40 + 120 * nt["vel"], 1, 200))) for nt in notes if nt["end"] > t0]


def render_lmms(jobs: dict, bpm, n, t0, log) -> dict[str, np.ndarray]:
    """jobs: track -> (cfg, notes). One headless LMMS run for all; on failure one run per track; the
    result is level-normalised (LMMS presets vary by 30 dB) so gain_db means the same as for engine sounds."""
    from engine import lmms as LM
    parts = {k: (dict(c["voice"], **({"fx": c["lmms_fx"]} if c.get("lmms_fx") else {})), lmms_notes(ns, bpm, t0, c.get("transpose", 0)))
             for k, (c, ns) in jobs.items()}
    out = {}
    try:
        out = LM.render_parts(parts, bpm, n, SR, timeout=1800)
    except Exception as ex:
        log(f"  LMMS batch failed ({str(ex)[:120]}); trying tracks one by one")
        for k, v in parts.items():
            try:
                out.update(LM.render_parts({k: v}, bpm, n, SR, timeout=900))
            except Exception as ex2:
                log(f"  ! LMMS could not play {k}: {str(ex2)[:160]}")
    for k, x in out.items():
        m = x.mean(1)
        fr = 2048
        kk = len(m) // fr
        r = np.sqrt((m[:kk * fr].reshape(kk, fr) ** 2).mean(1)) if kk else np.array([0.0])
        act = r[r > r.max() * 0.01]
        level = float(np.sqrt((act ** 2).mean())) if len(act) and r.max() > 1e-7 else 0.0
        if level <= 0:
            log(f"  ! LMMS rendered {k} silent")
            continue
        out[k] = (x * (0.1 / level)).astype(np.float32)       # -> -20 dBFS while playing
    return {k: v for k, v in out.items() if np.abs(v).max() > 0}


DEFAULT_FALLBACK = {"kind": "pad", "preset": "pad-night.json"}


def drum_sound(snd: dict, vel, rng):
    parts = []
    if snd.get("samples"):
        parts.append(DR.sampled_hit(rng, snd["samples"], vel, detune_cents=snd.get("detune_cents", 8)) * fx.db(snd.get("sample_db", 0)))
    if snd.get("synth"):
        parts.append(getattr(synth, snd["synth"])(rng, vel, **snd.get("args", {})) * fx.db(snd.get("synth_db", 0)))
    if snd.get("py"):                          # py = { module, fn, args }: fn(rng, vel, **args) from another program
        py = snd["py"]
        parts.append(np.asarray(py_fn(py["module"], py["fn"])(rng, vel, **py.get("args", {})), np.float32) * fx.db(snd.get("py_db", 0)))
    if not parts:
        return np.zeros(16, np.float32)
    m = max(len(x) for x in parts)
    y = sum(np.pad(x, (0, m - len(x))) for x in parts)
    if snd.get("pitch"):
        y = fx.resample(y, 2 ** (snd["pitch"] / 12))
    if snd.get("hp"):
        y = fx.hp(y, snd["hp"])
    if snd.get("lp"):
        y = fx.lp(y, snd["lp"])
    if snd.get("gate"):                        # cut the hit after `gate` seconds (5 ms fade), as LMMS's sampler does at the note's end
        k, f = int(snd["gate"] * SR), int(0.005 * SR)
        if len(y) > k:
            y = y[:k + f].copy()
            y[k:] *= np.linspace(1, 0, len(y) - k)
    return y.astype(np.float32)


# GM percussion -> a default kit from LMMS's sample folder (used when a map has no drum table)
GM_DRUMS = {35: "kick", 36: "kick", 37: "rim", 38: "snare", 40: "snare", 39: "clap", 42: "hat", 44: "hat", 46: "open",
            49: "crash", 57: "crash", 51: "ride", 59: "ride", 41: "tom_lo", 43: "tom_lo", 45: "tom_mid", 47: "tom_mid", 48: "tom_hi",
            50: "tom_hi", 54: "shaker", 69: "shaker", 70: "shaker", 56: "rim", 60: "conga_hi", 61: "conga_lo", 62: "conga_hi",
            63: "conga_hi", 64: "conga_lo", 75: "wood", 76: "wood", 77: "wood"}
GM_NAMES = {35: "Acoustic Bass Drum", 36: "Bass Drum", 37: "Side Stick", 38: "Snare", 39: "Hand Clap", 40: "Electric Snare",
            41: "Low Floor Tom", 42: "Closed Hi-Hat", 43: "High Floor Tom", 44: "Pedal Hi-Hat", 45: "Low Tom", 46: "Open Hi-Hat",
            47: "Low-Mid Tom", 48: "Hi-Mid Tom", 49: "Crash", 50: "High Tom", 51: "Ride", 54: "Tambourine", 56: "Cowbell",
            57: "Crash 2", 59: "Ride 2", 60: "Hi Bongo", 61: "Low Bongo", 62: "Mute Hi Conga", 63: "Open Hi Conga",
            64: "Low Conga", 69: "Cabasa", 70: "Maracas", 75: "Claves", 76: "Hi Wood Block", 77: "Low Wood Block"}
DEFAULT_SOUNDS = {
    "kick": {"samples": ["drums/bassdrum01.ogg"], "synth": "kick", "args": {"start": 120, "end": 50, "decay": 0.28, "click": 0.2},
             "synth_db": -6, "detune_cents": 0, "stem": "kick"},
    "snare": {"samples": ["drums/snare01.ogg"], "stem": "snare"},
    "clap": {"samples": ["drums/clap02.ogg", "drums/clap03.ogg"], "stem": "clap"},
    "rim": {"samples": ["drums/sidestick01.ogg"], "stem": "perc"},
    "hat": {"samples": ["drums/hihat_closed01.ogg", "drums/hihat_closed03.ogg"], "hp": 400, "lp": 12000, "stem": "hats"},
    "open": {"samples": ["drums/hihat_opened02.ogg"], "hp": 400, "lp": 12000, "stem": "hats"},
    "crash": {"samples": ["drums/crash02.ogg"], "lp": 12000, "stem": "cymbals"},
    "ride": {"samples": ["drums/ride01.ogg"], "stem": "cymbals"},
    "tom_lo": {"samples": ["drums/tom_low01.ogg"], "stem": "toms"},
    "tom_mid": {"samples": ["drums/tom_mid01.ogg"], "stem": "toms"},
    "tom_hi": {"samples": ["drums/tom_hi01.ogg"], "stem": "toms"},
    "shaker": {"samples": ["drums/shaker02.ogg", "drums/shaker03.ogg"], "stem": "perc"},
    "conga_hi": {"synth": "bongo", "args": {"pitch": 310}, "stem": "perc"},
    "conga_lo": {"synth": "bongo", "args": {"pitch": 205}, "stem": "perc"},
    "wood": {"samples": ["drums/wood01.ogg"], "stem": "perc"},
}


def default_drums() -> dict:
    return {"channel": 9, "map": {str(k): v for k, v in GM_DRUMS.items()}, "sounds": json.loads(json.dumps(DEFAULT_SOUNDS)),
            "stems": {"kick": {"hp": 28, "mono": True, "gain_db": -3.0}, "snare": {"gain_db": -8.0}, "clap": {"gain_db": -6.0},
                      "hats": {"pan": 0.12, "gain_db": -6.0}, "cymbals": {"gain_db": -14.0}, "toms": {"gain_db": -8.0},
                      "perc": {"pan": 0.2, "gain_db": -9.0}}}


# ------------------------------------------------------------------ automation and mixing

def bar_time(bar: float, bpm: float) -> float:
    return (bar - 1) * 4 * 60 / bpm


def curve(points, bpm, n, t0, shape="lin"):
    ts = np.array([(bar_time(b, bpm) - t0) * SR for b, _ in points])
    vs = np.array([v for _, v in points], float)
    x = np.arange(0, n, 64)
    c = np.exp(np.interp(x, ts, np.log(np.maximum(vs, 1e-6)))) if shape == "exp" else np.interp(x, ts, vs)
    return np.repeat(c, 64)[:n].astype(np.float32)


def process(name, x, cfg, auto, bpm, n, t0, sends, kick_times):
    if cfg.get("hp"):
        x = fx.hp(x, cfg["hp"])
    if cfg.get("eq"):
        x = fx.eq(x, [tuple(b) for b in cfg["eq"]])
    if cfg.get("lp"):
        x = fx.lp(x, cfg["lp"])
    if cfg.get("drive"):
        x = fx.saturate(x, cfg["drive"])
    if cfg.get("wow"):                         # tape wow/flutter: { depth_ms, rate, flutter_ms }
        x = fx.wow(x, **cfg["wow"]).astype(np.float32)
    if cfg.get("tape"):                        # a pass through a tape machine: { drive, hf_db, hiss_db, ... } (fx.tape)
        x = fx.tape(x, **cfg["tape"]).astype(np.float32)
    if cfg.get("crush"):                     # parallel bit-crush: { bits, rate, mix } (the clean part keeps the lows solid)
        cr = cfg["crush"]
        x = (x * (1 - cr.get("mix", 1.0)) + fx.crush(x, cr.get("bits", 10), cr.get("rate", 22050)) * cr.get("mix", 1.0)).astype(np.float32)
    for a in auto:                             # filter sweeps by bar: lowpass (open = 20000) and highpass (open = 20)
        if name in a.get("tracks", []) and a["type"] in ("lowpass", "highpass"):
            a0, a1 = int((bar_time(a["points"][0][0], bpm) - t0) * SR), int((bar_time(a["points"][-1][0], bpm) - t0) * SR)
            s0, s1 = max(0, a0 - int(0.5 * SR)), min(n, a1)
            if s1 <= s0:
                continue
            c = curve(a["points"], bpm, n, t0, "exp")[s0:s1]
            if a0 > s0:
                c[: a0 - s0] = 20000 if a["type"] == "lowpass" else 20
            x = x.copy()
            x[s0:s1] = fx.sweep(x[s0:s1].astype(np.float32), a["type"], c, block=256, order=2)
    if cfg.get("leslie"):
        L = cfg["leslie"]
        y = fx.leslie(x, curve(L.get("speed", [[1, 0]]), bpm, n, t0), crossover=L.get("crossover", 800), mix=L.get("mix", 1.0))
    else:
        y = fx.pan(x, cfg.get("pan", 0.0))
    if cfg.get("chorus"):
        y = fx.chorus(y, **cfg["chorus"])
    if cfg.get("width") is not None:
        y = fx.width(y, cfg["width"])
    pan_t = np.zeros(n, np.float32)            # moving pans: "pan" automation by bar, and a tempo-synced auto-pan
    moving = False
    for a in auto:
        if name in a.get("tracks", []) and a["type"] == "pan":
            pan_t += curve(a["points"], bpm, n, t0)
            moving = True
    if cfg.get("autopan"):                     # { rate_beats (one L-R-L cycle), depth, bars: [[from, to, depth], ...] }
        ap = cfg["autopan"]
        t = t0 + np.arange(n) / SR
        depth = np.full(n, float(ap.get("depth", 0.4)), np.float32)
        if ap.get("bars"):
            depth[:] = 0
            for b0, b1, d in ap["bars"]:
                i0, i1 = max(0, int((bar_time(b0, bpm) - t0) * SR)), max(0, int((bar_time(b1, bpm) - t0) * SR))
                depth[i0:i1] = d
            k = int(0.25 * SR)                 # depth changes glide over a quarter second
            depth = np.convolve(depth, np.ones(k) / k, mode="same").astype(np.float32)
        pan_t += depth * np.sin(2 * np.pi * t / (ap.get("rate_beats", 2) * 60 / bpm) + ap.get("phase", 0.0))
        moving = True
    if moving:
        a_ = (np.clip(pan_t, -1, 1) + 1) * np.pi / 4
        y = y * (np.stack([np.cos(a_), np.sin(a_)], 1) * np.sqrt(2)).astype(np.float32)
    g = np.ones(n, np.float32)
    for a in auto:
        if name in a.get("tracks", []) and a["type"] == "gain":
            g *= fx.db(curve(a["points"], bpm, n, t0))
    if cfg.get("duck") and kick_times:
        g *= fx.duck(n, kick_times, cfg["duck"]["depth"], cfg["duck"].get("release", 0.12))
    y = y * g[:, None]
    wet = np.zeros_like(y)
    for s, amt in cfg.get("sends", {}).items():
        if amt and s in sends:
            wet += fx.convolve(fx.hp(y, 250) * amt, sends[s])
    out = (y + wet) * fx.db(cfg.get("gain_db", 0.0))
    if cfg.get("mono"):
        out = np.repeat(out.mean(1, keepdims=True), 2, 1)
    return out.astype(np.float32)


DEFAULT_SENDS = {"room": {"type": "reverb", "seconds": 0.8, "predelay": 0.01, "size": 0.5, "damp": 0.6},
                 "plate": {"type": "reverb", "seconds": 2.2, "predelay": 0.025, "damp": 0.5},
                 "echo": {"type": "delay", "time_beats": 0.75, "feedback": 0.35, "tone": 2800},
                 "spring": {"type": "spring", "seconds": 2.0, "period": 0.031, "chirp": 1.0}}


def spring_ir(seconds: float = 2.0, period: float = 0.031, chirp: float = 1.0, seed: int = 11) -> np.ndarray:
    """A spring tank as a stereo IR: the drip. Each trip along the spring returns as a dispersed chirp (highs arrive
    first and fall to the lows), repeating every `period` seconds and dying away; a little diffuse wash glues it."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    ir = np.zeros((n, 2), np.float32)
    L = int(period * 0.9 * SR)
    tc = np.arange(L) / SR
    f = 4200 * (300 / 4200) ** (tc / tc[-1]) ** (0.6 / max(chirp, 0.1))   # an exponential downward chirp
    burst = (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.hanning(L)).astype(np.float32)
    for ch, (per, off) in enumerate(((period, 0.0), (period * 1.13, 0.004))):      # two springs, slightly apart
        k = 0
        while True:
            i = int((off + 0.006 + k * per) * SR)
            if i + L >= n:
                break
            g = np.exp(-6.9 * (i / SR) / seconds) * (0.8 + 0.4 * rng.random())
            ir[i:i + L, ch] += burst * g * (1 if k % 2 == 0 else -0.85)
            k += 1
    wash = fx.reverb_ir(seconds * 0.6, 0.01, 0.7, seed=seed, size=0.4)[:n]
    ir[:len(wash)] += 0.25 * wash
    ir = fx.lp(fx.hp(ir, 180), 5200)
    return (ir / np.sqrt((ir ** 2).sum(0).mean())).astype(np.float32)


# ------------------------------------------------------------------ the render

def render(midi: Path, cfg: dict, base: Path, out_dir: Path, stem_dir: Path | None, bars: tuple[int, int] | None = None,
           only: list[str] | None = None, do_mp3: bool = True, slug: str | None = None, log=print) -> dict:
    t_start = time.time()
    notes, bpm, _ = read_midi(midi)
    meta = cfg.get("meta", {})
    slug = slug or meta.get("slug") or midi.stem
    dirs = preset_dirs(cfg, base)
    tail = cfg.get("tail_s", 3.0)
    end_all = max(n["end"] for n in notes)
    t0, t1 = 0.0, end_all
    if bars:
        t0, t1 = bar_time(bars[0], bpm), bar_time(bars[1] + 1, bpm)
        notes = [dict(n, end=min(n["end"], t1 + 2.0)) for n in notes if n["end"] > t0 and n["start"] < t1]
        notes = [n for n in notes if n["start"] >= t0 - 0.02]                 # notes that start in the window
    n = int((t1 - t0 + tail) * SR)
    log(f"{midi.name}: {len(notes)} notes, {bpm:.1f} bpm" + (f", bars {bars[0]}-{bars[1]}" if bars else f", {end_all:.1f} s"))

    beat_s = 60 / bpm
    sends = {}
    for k, s in {**DEFAULT_SENDS, **cfg.get("sends", {})}.items():
        if s["type"] == "delay":
            sends[k] = fx.delay_ir(beat_s, s["time_beats"], s["feedback"], s.get("taps", 6), s.get("tone", 3000))
        elif s["type"] == "spring":
            sends[k] = spring_ir(s.get("seconds", 2.0), s.get("period", 0.031), s.get("chirp", 1.0))
        else:
            sends[k] = fx.reverb_ir(s["seconds"], s.get("predelay", 0.02), s.get("damp", 0.5), size=s.get("size", 1.0))
    auto = cfg.get("automation", [])
    tracks = cfg.get("tracks", {})

    midi_names = {nn["track"] for nn in notes}

    def cfg_for(tr_name, ch):
        if tr_name in tracks:
            return tr_name
        for k, v in tracks.items():          # by channel, for a table not named after another MIDI track
            if v.get("channel") == ch and k not in midi_names:
                return k
        return None

    by: dict[str, list] = {}
    for nt in notes:
        k = cfg_for(nt["track"], nt["ch"])
        if k is None:
            if nt["ch"] == 9:
                tracks["drums"] = default_drums()
                k = "drums"
            else:
                log(f"  ! no instrument for track {nt['track']!r}; skipped")
                tracks[nt["track"]] = {"mute": True}
                continue
        by.setdefault(k, []).append(nt)
    solo = {k for k, v in tracks.items() if v.get("solo")}
    play = [k for k in by if not tracks[k].get("mute") and (not solo or k in solo) and (not only or k in only)]
    total_steps = len(play) + 1
    step = 0

    def progress(msg):
        nonlocal step
        step += 1
        log(f"PROGRESS {step}/{total_steps} {msg}")

    stems: dict[str, np.ndarray] = {}
    kick_times: list[float] = []
    rng = np.random.default_rng(cfg.get("seed", 1))
    if "drums" in by:
        dc = tracks["drums"]
        dmap, dsounds = dc.get("map", {}), dc.get("sounds", {})
        # a key "<channel>:<note>" names a sound on one channel of the drums track (a kit of more than 128 sounds)
        dkey = lambda nt: f"{nt['ch']}:{nt['pitch']}" if f"{nt['ch']}:{nt['pitch']}" in dmap else str(nt["pitch"])
        bufs: dict[str, np.ndarray] = {}
        # choke groups (a sound's "choke": name): a hit stops when the next hit of its group starts, like a sampler's
        # mono slice voice, so break slices can keep their tails without doubling the next slice.
        # "preroll_ms": the sample starts that long before the note (its fade-in lead), and the hit it chokes fades out
        # over the same span, so slices cut from one continuous take and played in order rebuild it without a seam
        def preroll(j):
            sd = dsounds.get(dmap.get(dkey(by["drums"][j])), {})
            return sd.get("preroll_ms", 0.0) / 1000 * 2 ** (-sd.get("pitch", 0) / 12)

        choke_end: dict[int, tuple[float, float]] = {}
        last: dict[str, int] = {}
        for j in sorted(range(len(by["drums"])), key=lambda j: by["drums"][j]["start"]):
            g = dsounds.get(dmap.get(dkey(by["drums"][j])), {}).get("choke")
            if g:
                if g in last and by["drums"][j]["start"] > by["drums"][last[g]]["start"] + 1e-4:
                    p = preroll(j)
                    choke_end[last[g]] = (by["drums"][j]["start"] - p, p if p > 0 else 0.003)
                last[g] = j
        for j, nt in enumerate(by["drums"]):
            snd_name = dmap.get(dkey(nt))
            if snd_name is None or snd_name not in dsounds:
                continue
            snd = dsounds[snd_name]
            stem = snd.get("stem", snd_name)
            if stem == "kick":
                kick_times.append(nt["start"] - t0)
            if "drums" not in play or snd.get("mute"):
                continue
            y = drum_sound(snd, nt["vel"], rng) * fx.db(snd.get("gain_db", 0))
            p0 = preroll(j)
            if j in choke_end:
                k, f = int(round((choke_end[j][0] - nt["start"] + p0) * SR)), int(round(choke_end[j][1] * SR))
                if len(y) > k + f + 1:          # a sound that already fades out where the next one fades in is left alone
                    y = y[:max(k, 0) + f].copy()
                    y[max(k, 0):] *= np.linspace(1, 0, len(y) - max(k, 0))
            b = bufs.setdefault(stem, np.zeros(n, np.float32))
            i = int(round((nt["start"] - t0 - p0) * SR))
            if i < 0:
                y, i = y[-i:], 0
            k = min(len(y), n - i)
            if k > 0:
                b[i:i + k] += y[:k]
        for stem, mono in bufs.items():
            stems[stem] = process(stem, mono, dict(dc.get("stems", {}).get(stem, {})), auto, bpm, n, t0, sends, [])
        if "drums" in play:
            progress(f"drums ({len(by['drums'])} hits, stems {', '.join(bufs)})")

    lm_jobs = {k: (tracks[k], by[k]) for k in play if k != "drums" and tracks[k].get("kind") == "lmms"}
    lm_audio = {}
    if lm_jobs:
        log(f"  LMMS: playing {', '.join(lm_jobs)} (headless)")
        lm_audio = render_lmms(lm_jobs, bpm, n, t0, log)
    for k in play:
        if k == "drums":
            continue
        c = tracks[k]
        if c.get("kind") == "lmms":
            if k in lm_audio:
                x = lm_audio[k]
            else:
                fb = c.get("fallback") or DEFAULT_FALLBACK
                log(f"  {k}: LMMS unavailable, using the engine's {fb['kind']} instead")
                x = render_engine(by[k], {**fb, "transpose": c.get("transpose", 0)}, dirs, n, np.random.default_rng(cfg.get("seed", 1)), t0)
        else:
            x = render_engine(by[k], c, dirs, n, np.random.default_rng(cfg.get("seed", 1) + sum(map(ord, k))), t0)
        stem = c.get("stem", k)
        y = process(k, x, c, auto, bpm, n, t0, sends, kick_times)
        stems[stem] = stems[stem] + y if stem in stems else y
        progress(f"{k}: {len(by[k])} notes ({time.time() - t_start:.0f} s)")

    if not stems:
        raise SystemExit("nothing to render (all tracks muted?)")
    mixc = cfg.get("mix", {})
    pre = np.zeros((n, 2), np.float32)
    for s in list(stems):
        stems[s] = stems[s] * fx.db(mixc.get("stem_trim_db", {}).get(s, 0.0))
        pre += stems[s]
    if mixc.get("console_drive"):
        pre = fx.console(pre, mixc["console_drive"])
    peak = float(np.abs(pre).max())
    scale = 0.5 / peak if peak > 0.5 else 1.0
    out_dir.mkdir(parents=True, exist_ok=True)
    if stem_dir:
        stem_dir.mkdir(parents=True, exist_ok=True)
        for s, x in stems.items():
            write_audio(stem_dir / f"{s}.wav", x * scale)
    write_audio(out_dir / f"{slug}_premaster.wav", pre * scale)
    final, minfo = master(pre, {"master": cfg.get("master", {"target_lufs": -12.0, "ceiling": -1.0})})
    fade = int(min(cfg.get("fade_out_s", 1.5), tail) * SR)
    final[-fade:] *= np.linspace(1, 0, fade)[:, None] ** 2
    if bars:
        fi = int(0.01 * SR)
        final[:fi] *= np.linspace(0, 1, fi)[:, None]
    wav = out_dir / f"{slug}.wav"
    write_audio(wav, final)
    ok_mp3 = do_mp3 and mp3(wav, out_dir / f"{slug}.mp3", {"title": meta.get("title", slug), "artist": meta.get("artist", ""),
                                                          "album": meta.get("album", meta.get("title", slug)), "composer": meta.get("composer", ""),
                                                          "genre": meta.get("genre", "Electronic"), "year": meta.get("year", 2026),
                                                          "track": meta.get("track", 1), "album_artist": meta.get("album_artist", meta.get("artist", ""))})
    progress("master")
    info = {"midi": str(midi), "bpm": bpm, "bars": bars, "seconds": len(final) / SR, "stems": sorted(stems), "stem_scale": scale,
            "master": minfo, "mp3": bool(ok_mp3), "wav": str(wav), "analysis": analyse(final, None, wav.name), "render_s": round(time.time() - t_start, 1)}
    (out_dir / ("render_info.json" if not bars else f"{slug}_info.json")).write_text(json.dumps(info, indent=1, default=float))
    a = info["analysis"]
    log(f"DONE {wav} | {info['seconds']:.1f} s, {a['integrated_lufs']} LUFS, TP {a['true_peak_dbtp_approx']} dBTP, {info['render_s']} s to render")
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("midi", type=Path)
    ap.add_argument("instruments", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--stems", type=Path)
    ap.add_argument("--no-stems", action="store_true")
    ap.add_argument("--no-mp3", action="store_true")
    ap.add_argument("--bars", help="render only these bars, e.g. 33-40")
    ap.add_argument("--only", help="comma-separated track names to render (solo)")
    ap.add_argument("--name", help="output file name (slug)")
    args = ap.parse_args()
    cfg = tomllib.loads(args.instruments.read_text())
    base = Path(cfg.get("base_dir", args.instruments.resolve().parent))
    out = args.out or base / "exports"
    stems = None if args.no_stems else (args.stems or base / "stems")
    bars = tuple(int(x) for x in args.bars.split("-")) if args.bars else None
    render(args.midi, cfg, base, out, stems, bars, args.only.split(",") if args.only else None, not args.no_mp3, args.name,
           log=lambda m: print(m, flush=True))


if __name__ == "__main__":
    main()
