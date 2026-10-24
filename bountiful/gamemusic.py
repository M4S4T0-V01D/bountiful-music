"""Game music: a section of a track as a seamless loop in intensity layers, plus stingers, ready for a game engine.

    sections(track)          the track's sections with an energy score; the busiest one is the default loop
    make(track, ...)         render the loop and stingers and write <track>/game/ (see below)
    wrap(x, n)               fold everything after sample n back onto the start: the loop's own tail rings into
                             its next pass, so the seam is exactly what a repeat would sound like
    split(stems, n, bpm)     stems -> wrapped layers -> state mixes (pure, no rendering)
    stinger_song(song, ...)  victory, game over, pickup, alert and level start, in the track's key and sounds

What <track>/game/ holds:
    loop_<state>.wav         calm, explore, tense, combat: whole mixes, 16-bit, with a RIFF smpl loop point
    layers/<layer>.wav       bed, low, beat, drive, top: same length, sample-aligned, linear (they sum to combat)
    stingers/<name>.wav      one-shots that start on the next bar (or beat) of the loop
    manifest.json            tempo, key, loop length in samples, which layers make which state, the stingers
    godot/BountifulMusic.gd  an adaptive player for Godot 4 (crossfades layers, quantizes stingers)
    unity/BountifulMusic.cs  the same for Unity
    README.txt               how to drop it into a game
    *.ogg                    with LOOPSTART / LOOPLENGTH tags, when asked for and ffmpeg is there

Deterministic (the renderer is seeded; nothing here is random) and bounded: a loop is at most MAX_BARS bars and
everything after the render is memoryless, so nothing can smear across the seam.

    $PY bountiful/gamemusic.py tracks/<track> [--section N | --bars 17-24] [--no-stingers] [--ogg]
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build as B  # noqa: E402

SR = 44100
MAX_BARS = 16
MIN_BARS = 2
TARGET_RMS = 10 ** (-16 / 20)        # the combat mix sits near -16 dBFS RMS
STATE_DB = {"calm": -21.0, "explore": -18.5, "tense": -17.0, "combat": -16.0}     # each whole-mix loop's RMS
CEILING = 10 ** (-0.3 / 20)
HEADROOM = 10 ** (-1 / 20)           # layers are linear: the loudest of them, and their sum, peak at -1 dBFS
NOTE = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
SCALES = {"major": (0, 2, 4, 5, 7, 9, 11), "minor": (0, 2, 3, 5, 7, 8, 10), "dorian": (0, 2, 3, 5, 7, 9, 10),
          "phrygian": (0, 1, 3, 5, 7, 8, 10), "lydian": (0, 2, 4, 6, 7, 9, 11), "mixolydian": (0, 2, 4, 5, 7, 9, 10),
          "harmonic_minor": (0, 2, 3, 5, 7, 8, 11), "minor_pent": (0, 3, 5, 7, 10), "major_pent": (0, 2, 4, 7, 9),
          "blues": (0, 3, 5, 6, 7, 10)}

LAYERS = ("bed", "low", "beat", "drive", "top")
LAYER_WHAT = {"bed": "pads, keys, chords", "low": "bass", "beat": "kick, hats, toms",
              "drive": "snare, claps, percussion, arps, cymbals", "top": "lead lines"}
STATES = {"calm": {"bed": 1.0, "low": 0.6},
          "explore": {"bed": 1.0, "low": 1.0, "beat": 0.8},
          "tense": {"bed": 1.0, "low": 1.0, "beat": 1.0, "drive": 1.0},
          "combat": {"bed": 1.0, "low": 1.0, "beat": 1.0, "drive": 1.0, "top": 1.0}}
STATE_WHAT = {"calm": "menus, safe rooms, exploring at rest", "explore": "moving through the world",
              "tense": "danger is near, puzzles against the clock", "combat": "fights and chases"}


def layer_of(stem: str) -> str:
    s = stem.lower()
    if "bass" in s:
        return "low"
    if any(k in s for k in ("lead", "sidekick", "counter", "melody", "solo", "hook")):
        return "top"
    if any(k in s for k in ("kick", "hat", "tom", "open", "rim", "shaker")):
        return "beat"
    if any(k in s for k in ("snare", "clap", "perc", "crash", "ride", "cymbal", "arp", "stab", "break")):
        return "drive"
    return "bed"


# ---------------------------------------------------------------- the song's sections

def song_of(track: Path) -> dict | None:
    import observatory as O
    return O.song_of(Path(track))


def sections(track: Path, song: dict | None = None) -> list[dict]:
    """[{index, name, start, bars, energy, parts}] (start 1-based). Energy: how many parts play, then notes per bar."""
    song = song or song_of(track)
    if not song:
        return []
    secs = song.get("sections") or [{"name": f"bars {a}-{min(a + 7, song['bars'])}", "start": a,
                                     "bars": min(8, song["bars"] - a + 1)} for a in range(1, song["bars"] + 1, 8)]
    voices = dict(song.get("parts", {}))
    voices["drums"] = song.get("drums", [])
    out = []
    for i, s in enumerate(secs):
        lo, hi = (s["start"] - 1) * 4, (s["start"] - 1 + s["bars"]) * 4
        counts = {k: sum(1 for n in evs if lo <= n[0] < hi) for k, evs in voices.items()}
        playing = sorted(k for k, c in counts.items() if c)
        out.append({"index": i, "name": s.get("name", f"section {i + 1}"), "start": int(s["start"]), "bars": int(s["bars"]),
                    "parts": playing, "energy": round(len(playing) * 10 + sum(counts.values()) / max(1, s["bars"]), 2)})
    return out


def busiest(secs: list[dict]) -> dict | None:
    ok = [s for s in secs if s["bars"] >= MIN_BARS] or secs
    return max(ok, key=lambda s: (s["energy"], -s["index"])) if ok else None


def loop_bars(sec: dict) -> tuple[int, int]:
    n = max(MIN_BARS, min(MAX_BARS, sec["bars"]))
    return sec["start"], sec["start"] + n - 1


# ---------------------------------------------------------------- loops, layers and states (pure)

def wrap(x: np.ndarray, n: int) -> np.ndarray:
    """The first n samples of x with everything after them folded back onto the start, as often as it reaches."""
    out = np.array(x[:n], dtype=np.float64)
    for k in range(n, len(x), n):
        seg = x[k:k + n]
        out[:len(seg)] += seg
    return out


def soft(x: np.ndarray, knee: float = 0.75, ceil: float = CEILING) -> np.ndarray:
    """Memoryless soft clip: linear up to the knee, then a tanh shoulder that never passes the ceiling."""
    a = np.abs(x)
    over = a > knee
    y = np.array(x, dtype=np.float64)
    w = ceil - knee
    y[over] = np.sign(x[over]) * (knee + w * np.tanh((a[over] - knee) / w))
    return y


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def split(stems: dict[str, np.ndarray], n: int) -> dict:
    """{layers: {name: wrapped array}, members: {layer: [stems]}, states: {name: mastered array}, mix, gain, layer_gain}.
    Layers share one gain (so they still sum to the raw combat mix, with headroom); each whole-mix state is brought
    to its own level (STATE_DB) through the memoryless soft clip."""
    members: dict[str, list[str]] = {k: [] for k in LAYERS}
    raw: dict[str, np.ndarray] = {}
    for name in sorted(stems):
        x = np.asarray(stems[name], dtype=np.float64)
        if x.ndim == 1:
            x = np.stack([x, x], 1)
        L = layer_of(name)
        members[L].append(name)
        w = wrap(x, n)
        if len(w) < n:
            w = np.vstack([w, np.zeros((n - len(w), 2))])
        raw[L] = raw[L] + w if L in raw else w
    layers = {k: raw[k] for k in LAYERS if k in raw and np.abs(raw[k]).max() > 1e-6}
    if not layers:
        raise ValueError("the loop is silent")
    mixes = {}
    for st, mix in STATES.items():
        x = sum(layers[k] * g for k, g in mix.items() if k in layers)
        if not isinstance(x, np.ndarray) or np.abs(x).max() < 1e-6:      # e.g. no pads and no bass: the quietest layer
            q = min(layers, key=lambda k: rms(layers[k]))
            x, mix = layers[q] * 0.8, {q: 0.8}
        mixes[st] = (x, {k: g for k, g in mix.items() if k in layers})
    combat = mixes["combat"][0]
    gain = TARGET_RMS / max(rms(combat), 1e-9)
    peak = max([np.abs(combat).max()] + [np.abs(v).max() for v in layers.values()])
    lgain = min(gain, HEADROOM / peak)
    return {"layers": {k: v * lgain for k, v in layers.items()}, "members": {k: v for k, v in members.items() if k in layers},
            "states": {k: soft(x * 10 ** (STATE_DB[k] / 20) / max(rms(x), 1e-9)) for k, (x, _) in mixes.items()},
            "mix": {k: m for k, (_, m) in mixes.items()}, "gain": gain, "layer_gain": lgain}


# ---------------------------------------------------------------- WAV with a loop point

def write_wav(path: Path, x: np.ndarray, loop: tuple[int, int] | None = None) -> None:
    """16-bit PCM WAV. loop = (first, last) sample, inclusive, written as a RIFF smpl chunk (Godot, FMOD, Wwise and
    most samplers read it)."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    ch = x.shape[1]
    pcm = np.round(np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    fmt = struct.pack("<HHIIHH", 1, ch, SR, SR * ch * 2, ch * 2, 16)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(pcm)) + pcm
    if len(pcm) % 2:
        chunks += b"\0"
    if loop:
        smpl = struct.pack("<9I", 0, 0, round(1e9 / SR), 60, 0, 0, 0, 1, 0) + struct.pack("<6I", 0, 0, loop[0], loop[1], 0, 0)
        chunks += b"smpl" + struct.pack("<I", len(smpl)) + smpl
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks)


def read_wav(path: Path) -> tuple[np.ndarray, tuple[int, int] | None]:
    """(float samples [n, ch], loop or None) from a 16-bit WAV written by write_wav."""
    b = Path(path).read_bytes()
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        raise ValueError(f"{path}: not a WAV")
    i, ch, data, loop = 12, 1, b"", None
    while i + 8 <= len(b):
        cid, size = b[i:i + 4], struct.unpack("<I", b[i + 4:i + 8])[0]
        body = b[i + 8:i + 8 + size]
        if cid == b"fmt ":
            ch = struct.unpack("<H", body[2:4])[0]
        elif cid == b"data":
            data = body
        elif cid == b"smpl" and struct.unpack("<I", body[28:32])[0] >= 1:
            loop = struct.unpack("<II", body[44:52])
        i += 8 + size + (size & 1)
    x = np.frombuffer(data, "<i2").astype(np.float64).reshape(-1, ch) / 32767
    return x, loop


def ogg(wav: Path, n: int | None) -> bool:
    """An OGG Vorbis copy with LOOPSTART/LOOPLENGTH tags (RPG Maker, many engines' music players). Needs ffmpeg."""
    if not shutil.which("ffmpeg"):
        return False
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-c:a", "libvorbis", "-q:a", "6"]
    if n:
        cmd += ["-metadata", "LOOPSTART=0", "-metadata", f"LOOPLENGTH={n}"]
    return subprocess.run(cmd + [str(wav.with_suffix(".ogg"))], capture_output=True).returncode == 0


# ---------------------------------------------------------------- stingers

STINGERS = {"victory": ("a rising fanfare that lands on the home chord", "bar", 5.0),
            "game_over": ("a falling line that settles low", "bar", 6.5),
            "pickup": ("a quick bright blip for coins, items, points", "beat", 1.4),
            "alert": ("an urgent figure on the fifth: you have been spotted", "beat", 3.5),
            "level_start": ("a short call to begin", "bar", 4.0)}       # (what, quantize, longest seconds)


def scale_of(mode: str) -> tuple[int, ...]:
    if mode in SCALES:
        return SCALES[mode]
    return SCALES["minor"] if "min" in str(mode) or "aeol" in str(mode) else SCALES["major"]


def stinger_song(song: dict, parts: list[str]) -> dict[str, dict]:
    """{name: {parts: {part: [(beat, dur, pitch, vel, off)]}, drums: [...], beats}}: every pitch in the song's scale.
    parts: the track's pitched instruments; the first lead-like, pad-like and bass-like ones play."""
    tonic, sc = int(song.get("tonic", 0)) % 12, scale_of(song.get("mode", "minor"))
    pick = lambda pref, avoid=(): next((p for p in pref if p in parts), None) or next(   # noqa: E731
        (p for p in parts if p not in avoid and layer_of(p) != "low"), None)
    bass = next((p for p in ("bass", "bass2") if p in parts), None) or next((p for p in parts if layer_of(p) == "low"), None)
    pad = next((p for p in ("pad", "comp", "stab", "vox", "rhodes", "keys") if p in parts), None)
    lead = pick(("lead", "lead_hi", "sidekick", "counter", "arp"), avoid=(pad,)) or pad or bass
    if lead is None:
        return {}
    slow = 2.0 if song.get("bpm", 120) >= 140 else 1.0           # fast songs: stingers in half time

    def p(deg: int, root: int) -> int:
        return root + tonic + sc[deg % len(sc)] + 12 * (deg // len(sc))
    n = len(sc)
    third, fifth = (2, 4) if n == 7 else (1, 3)
    octave = n

    def chord(degs, at, dur, root, vel):
        return [(at * slow, dur * slow, p(d, root), vel, 0.0) for d in degs]
    out = {}

    def add(name, lead_line, pad_ch=(), bass_line=(), drums=(), beats=4):
        prt = {lead: [(b * slow, d * slow, p(g, 72), v, 0.0) for b, d, g, v in lead_line]}
        if pad and pad_ch:
            prt.setdefault(pad, []).extend(e for c in pad_ch for e in chord(*c, 60, 0.6))
        if bass and bass_line:
            prt.setdefault(bass, []).extend((b * slow, d * slow, p(g, 36), 0.8, 0.0) for b, d, g in bass_line)
        out[name] = {"parts": prt, "drums": [(b * slow, 0.25, k, v, 0.0) for b, k, v in drums], "beats": beats * slow}
    add("victory", [(0, .45, 0, .8), (.5, .45, third, .8), (1, .45, fifth, .85), (1.5, 2.5, octave, .9)],
        [((0, third, fifth), 1.5, 2.5)], [(1.5, 2.5, 0)], [(.5, 38, .5), (1, 38, .6), (1.5, 36, .9), (1.5, 49, .8)], 4)
    add("game_over", [(0, .9, fifth, .7), (1, .9, third + 1 if n == 7 else third, .65), (2, .9, third, .6),
                      (3, .9, 1, .6), (4, 3, 0, .6)],
        [((3, 5, 7) if n == 7 else (2, 3, 5), 0, 4), ((0, third, fifth), 4, 3)], [(0, 4, 3 if n == 7 else 2), (4, 3, 0)],
        [(4, 36, .7), (4, 49, .4)], 7)
    add("pickup", [(0, .22, fifth, .8), (.25, .22, octave, .85), (.5, .7, octave + third, .9)], beats=1.25)
    add("alert", [(0, .4, fifth, .9), (.5, .4, fifth - 1, .85), (1, .4, fifth, .9), (1.5, .4, fifth - 1, .85), (2, 1, fifth, .9)],
        [((fifth, fifth + 2, fifth + 4), 0, 3)], [(0, 3, fifth)],
        [(0, 36, .8), (0, 38, .7), (.5, 38, .5), (1, 36, .8), (1, 38, .7), (1.5, 38, .5), (2, 49, .6)], 3)
    add("level_start", [(0, .45, 0, .8), (.5, .45, fifth, .85), (1, 2, octave, .9)],
        [((0, third, fifth), 0, 3)], [(0, 3, 0)], [(0, 36, .8), (1, 36, .8), (1, 49, .6)], 3)
    return out


# ---------------------------------------------------------------- rendering

def _run(cmd: list[str], log) -> None:
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    tail = []
    for line in p.stdout:
        line = line.rstrip()
        tail = (tail + [line])[-12:]
        if line.startswith("PROGRESS") or line.startswith("  !"):
            log(line)
    if p.wait() != 0:
        raise RuntimeError("the renderer failed:\n" + "\n".join(tail))


def _read(path: Path) -> np.ndarray:
    import soundfile as sf
    x, sr = sf.read(str(path), dtype="float64", always_2d=True)
    if sr != SR:
        raise ValueError(f"{path.name}: {sr} Hz (expected {SR})")
    return x if x.shape[1] == 2 else np.repeat(x[:, :1], 2, 1)


PUSH_S = 0.021                       # the renderer keeps notes that start up to 20 ms before its window


def loop_midi(src: Path, a: int, b: int, dst: Path) -> Path:
    """A copy of the MIDI for looping bars a..b: a note pushed just ahead of bar a moves to just ahead of the bar after
    b (where it sounds on every later pass), and the notes pushed ahead of that bar, which belong to the next
    section, go. Everything else is untouched."""
    import mido
    mf = mido.MidiFile(str(src))
    ppq = mf.ticks_per_beat
    tempo = next((m.tempo for tr in mf.tracks for m in tr if m.type == "set_tempo"), 500000)
    eps = math.ceil(PUSH_S * 1e6 / tempo * ppq)
    lo, hi = (a - 1) * 4 * ppq, b * 4 * ppq
    for tr in mf.tracks:
        now, evs, open_ = 0, [], {}
        for m in tr:
            now += m.time
            evs.append([now, m])
        notes = []                       # [on index, off index]
        for i, (t, m) in enumerate(evs):
            if m.type == "note_on" and m.velocity > 0:
                open_.setdefault((m.channel, m.note), []).append(i)
            elif m.type in ("note_off", "note_on") and open_.get((m.channel, m.note)):
                notes.append((open_[(m.channel, m.note)].pop(0), i))
        drop, shift = set(), set()
        for on, off in notes:
            t = evs[on][0]
            if hi - eps <= t < hi:
                drop |= {on, off}
            elif lo - eps <= t < lo:
                shift |= {on, off}
        if not drop and not shift:
            continue
        kept = [(t + (hi - lo) if i in shift else t, k, m) for k, (i, (t, m)) in enumerate(enumerate(evs)) if i not in drop]
        kept.sort(key=lambda e: (e[2].type == "end_of_track", e[0], e[1]))
        tr.clear()
        last = 0
        for t, _, m in kept:
            t = max(t, last)             # end_of_track may sit before a note that moved past it
            tr.append(m.copy(time=t - last))
            last = t
    mf.save(str(dst))
    return dst


def render_loop(track: Path, a: int, b: int, work: Path, log=print) -> tuple[dict[str, np.ndarray], float]:
    """Bars a..b with stems (each with the ringing after bar b). Returns ({stem: samples}, bpm)."""
    mid = loop_midi(next(track.glob("*.mid")), a, b, work / "loop.mid")
    _run(["nice", "-n", "10", B.PY, "-u", str(B.render_script(track)), str(mid), str(track / "instruments.toml"),
          "--out", str(work), "--bars", f"{a}-{b}", "--stems", str(work / "stems"), "--no-mp3", "--name", "loop"], log)
    info = json.loads((work / "loop_info.json").read_text())
    return {w.stem: _read(w) for w in sorted((work / "stems").glob("*.wav"))}, float(info["bpm"])


def instruments(track: Path) -> list[str]:
    try:
        tr = tomllib.loads((track / "instruments.toml").read_text()).get("tracks", {})
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [k for k, v in tr.items() if k != "drums" and isinstance(v, dict) and v.get("channel") != 9 and not v.get("mute")]


def render_stingers(track: Path, song: dict, bpm: float, work: Path, log=print) -> dict[str, np.ndarray]:
    """All stingers in one render, each in its own slot of whole bars with room for its ringing, then cut apart."""
    st = stinger_song(dict(song, bpm=bpm), instruments(track))
    if not st:
        return {}
    bar_s = 4 * 60 / bpm
    parts: dict[str, list] = {}
    drums, slots, at = [], {}, 0.0
    for name, s in st.items():
        for k, evs in s["parts"].items():
            parts.setdefault(k, []).extend((t + at, d, pi, v, o) for t, d, pi, v, o in evs)
        drums += [(t + at, d, pi, v, o) for t, d, pi, v, o in s["drums"]]
        bars = math.ceil((s["beats"] * 60 / bpm + 3.0) / bar_s)
        slots[name] = (at, at + bars * 4)
        at += bars * 4
    mid = work / "stingers.mid"
    B.write_midi(mid, "stingers", bpm, {k: [] for k in B.PART_ORDER} | parts, drums)
    _run(["nice", "-n", "10", B.PY, "-u", str(B.render_script(track)), str(mid), str(track / "instruments.toml"),
          "--out", str(work), "--no-stems", "--no-mp3", "--name", "stingers"], log)
    x = _read(work / "stingers_premaster.wav")
    out = {}
    for name, (b0, b1) in slots.items():
        seg = x[round(b0 * 60 / bpm * SR):round(b1 * 60 / bpm * SR)]
        env = np.abs(seg).max(1)
        if not len(env) or env.max() < 1e-6:
            continue
        last = int(np.nonzero(env > env.max() * 10 ** (-50 / 20))[0][-1]) + 1    # trim to -50 dB under the peak
        cap = int(STINGERS[name][2] * SR)
        seg = seg[:min(last, cap)].copy()
        f = min(len(seg), int((0.35 if last > cap else 0.03) * SR))
        seg[-f:] *= np.linspace(1, 0, f)[:, None] ** 2
        out[name] = seg
    return out


def loudest(x: np.ndarray, win: int = int(0.4 * SR)) -> float:
    if len(x) <= win:
        return rms(x)
    e = np.cumsum(np.concatenate([[0.0], np.square(x).mean(1)]))
    return float(np.sqrt((e[win:] - e[:-win]).max() / win))


# ---------------------------------------------------------------- the export

def key_name(song: dict) -> str:
    return f"{NOTE[int(song.get('tonic', 0)) % 12]} {str(song.get('mode', 'minor')).replace('_', ' ')}"


def make(track: Path, section: int | None = None, bars: tuple[int, int] | None = None, stingers: bool = True,
         ogg_too: bool = False, out: Path | None = None, log=print) -> dict:
    """Render and write the game-music export; returns the manifest (with "folder")."""
    track = Path(track)
    song = song_of(track)
    if not song:
        raise ValueError(f"{track.name}: no song to read (no MIDI)")
    secs = sections(track, song)
    if bars:
        a, b = int(bars[0]), int(bars[1])
        name = f"bars {a}-{b}"
    else:
        sec = secs[section] if section is not None and 0 <= section < len(secs) else busiest(secs)
        a, b = loop_bars(sec)
        name = sec["name"]
    a, b = max(1, a), min(max(a, b), a + MAX_BARS - 1, max(song["bars"], a))
    out = Path(out) if out else track / "game"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bountiful-game-") as tmp:
        work = Path(tmp)
        log(f"rendering the loop: bars {a}-{b} ({name}) ...")
        stems, bpm = render_loop(track, a, b, work, log)
        n = round((b - a + 1) * 4 * 60 / bpm * SR)
        res = split(stems, n)
        sting = {}
        if stingers:
            log("rendering the stingers ...")
            sting = render_stingers(track, song, bpm, work, log)
    for old in list(out.glob("loop_*.*")) + list((out / "layers").glob("*.*")) + list((out / "stingers").glob("*.*")):
        old.unlink()
    title = song.get("title") or track.name
    man = {"v": 1, "title": title, "track": track.name, "bpm": round(bpm, 4), "key": key_name(song), "sample_rate": SR,
           "beats_per_bar": 4,
           "loop": {"section": name, "bars": [a, b], "samples": n, "seconds": round(n / SR, 4),
                    "bar_samples": round(n / (b - a + 1), 3), "start": 0, "end": n - 1},
           "layers": {}, "states": {}, "stingers": {}, "order": list(STATES)}
    for k, x in res["layers"].items():
        f = f"layers/{k}.wav"
        write_wav(out / f, x, (0, n - 1))
        man["layers"][k] = {"file": f, "stems": res["members"][k], "what": LAYER_WHAT[k]}
    for k, x in res["states"].items():
        f = f"loop_{k}.wav"
        write_wav(out / f, x, (0, n - 1))
        if ogg_too:
            ogg(out / f, n)
        man["states"][k] = {"file": f, "mix": res["mix"][k], "what": STATE_WHAT[k],
                            "rms_db": round(20 * math.log10(max(rms(x), 1e-9)), 1)}
    ref = loudest(res["states"]["combat"])
    for k, x in sting.items():
        f = f"stingers/{k}.wav"
        y = soft(x * (ref / max(loudest(x), 1e-9)))
        write_wav(out / f, y)
        if ogg_too:
            ogg(out / f, None)
        what, q, _ = STINGERS[k]
        man["stingers"][k] = {"file": f, "seconds": round(len(y) / SR, 3), "quantize": q, "what": what}
    (out / "manifest.json").write_text(json.dumps(man, indent=1))
    (out / "README.txt").write_text(readme(man))
    (out / "godot").mkdir(exist_ok=True)
    (out / "godot" / "BountifulMusic.gd").write_text(GODOT)
    (out / "unity").mkdir(exist_ok=True)
    (out / "unity" / "BountifulMusic.cs").write_text(unity(man))
    log(f"game music written to {out}")
    return dict(man, folder=str(out))


def readme(m: dict) -> str:
    lp = m["loop"]
    lines = [f"{m['title']}: game music from Bountiful", "",
             f"{m['bpm']:g} bpm, {m['key']}, loop = bars {lp['bars'][0]}-{lp['bars'][1]} ({lp['section']}), "
             f"{lp['samples']} samples = {lp['seconds']:.3f} s at {m['sample_rate']} Hz.", "",
             "Every loop file is exactly one loop long and loops from the first sample to the last; the WAVs carry",
             "a smpl loop chunk. The loop's own reverb and release tails are already folded onto its start, so the",
             "seam sounds like the music simply going round again.", "",
             "Simple use: play one loop_<state>.wav on repeat and switch files on the bar.", ""]
    lines += [f"  loop_{k}.wav   {v['what']}" for k, v in m["states"].items()]
    lines += ["", "Adaptive use: start every file in layers/ at the same moment, all looping, and fade their volumes",
              "to a state's mix (manifest.json \"states\" -> \"mix\", linear gains; a missing layer is silent):", ""]
    lines += [f"  layers/{k}.wav   {v['what']}" for k, v in m["layers"].items()]
    lines += ["", "Stingers are one-shots. Start them on the next bar (or beat, see \"quantize\") of the loop:",
              "one bar is loop.bar_samples samples.", ""]
    lines += [f"  {v['file']}   {v['what']}" for v in m["stingers"].values()]
    lines += ["", "Engines", "",
              "  Godot 4: copy this folder into res://music/<name>/, add a Node with godot/BountifulMusic.gd and set",
              "           its folder. Then call set_state(\"combat\") and stinger(\"victory\").",
              "  Unity:   copy layers/ and stingers/ into Assets/Resources/Music/<name>/ and set each clip to",
              "           Load Type \"Decompress On Load\" (or Compression \"PCM\") so the loop stays gapless. Add",
              "           unity/BountifulMusic.cs to a GameObject and call SetState(\"combat\") and Stinger(\"victory\").",
              "  FMOD / Wwise: import the layers as a multitrack loop region; the states are the mixes in the manifest.",
              "", "Both scripts are written from each engine's documented API. Bountiful did not run them inside the",
              "engines, so check them in your project.", ""]
    return "\n".join(lines)


GODOT = '''# BountifulMusic.gd: adaptive player for a Bountiful game-music export (Godot 4).
# Written from Godot's documented API and not run inside Godot by Bountiful: check it in your project.
#   $Music.set_state("combat")    crossfades the layers over fade_s seconds
#   $Music.stinger("victory")     plays on the next bar (or beat) of the loop
extends Node

@export var folder: String = "res://music/"
@export var start_state: String = "explore"
@export var fade_s: float = 1.5

var manifest: Dictionary = {}
var layers: Dictionary = {}
var state: String = ""


func _ready() -> void:
	var f := FileAccess.open(folder.path_join("manifest.json"), FileAccess.READ)
	manifest = JSON.parse_string(f.get_as_text())
	var loop_end: int = int(manifest["loop"]["samples"])
	for name in manifest["layers"]:
		var stream = load(folder.path_join(manifest["layers"][name]["file"]))
		if stream is AudioStreamWAV:
			stream.loop_mode = AudioStreamWAV.LOOP_FORWARD
			stream.loop_begin = 0
			stream.loop_end = loop_end
		var p := AudioStreamPlayer.new()
		p.stream = stream
		p.volume_db = -80.0
		add_child(p)
		layers[name] = p
	for name in layers:
		layers[name].play()
	set_state(start_state, 0.0)


func set_state(s: String, fade: float = -1.0) -> void:
	if not manifest["states"].has(s):
		return
	state = s
	var mix: Dictionary = manifest["states"][s]["mix"]
	var time := fade_s if fade < 0.0 else fade
	var t: Tween = null
	if time > 0.0:
		t = create_tween().set_parallel(true)
	for name in layers:
		var g: float = float(mix.get(name, 0.0))
		var db := linear_to_db(g) if g > 0.0 else -80.0
		if t == null:
			layers[name].volume_db = db
		else:
			t.tween_property(layers[name], "volume_db", db, time)


func stinger(name: String) -> void:
	if not manifest["stingers"].has(name):
		return
	var info: Dictionary = manifest["stingers"][name]
	var p := AudioStreamPlayer.new()
	p.stream = load(folder.path_join(info["file"]))
	add_child(p)
	p.finished.connect(p.queue_free)
	var wait := _until_next(info.get("quantize", "bar"))
	if wait > 0.005:
		await get_tree().create_timer(wait).timeout
	p.play()


func _until_next(unit: String) -> float:
	if layers.is_empty():
		return 0.0
	var first: AudioStreamPlayer = layers.values()[0]
	var pos := first.get_playback_position() + AudioServer.get_time_since_last_mix()
	var step := 60.0 / float(manifest["bpm"]) * (4.0 if unit == "bar" else 1.0)
	return step - fmod(pos, step)
'''


def unity(m: dict) -> str:
    names = list(m["layers"])
    rows = []
    for s, v in m["states"].items():
        gains = ", ".join("%.3ff" % float(v["mix"].get(k, 0.0)) for k in names)
        rows.append('        {"%s", new float[] {%s}}' % (s, gains))
    states = ",\n".join(rows)
    quant = ", ".join('{"%s", %s}' % (k, "true" if v["quantize"] == "beat" else "false") for k, v in m["stingers"].items())
    layer_list = ", ".join('"%s"' % k for k in names)
    folder, title, bpm = B.slug(m["track"]), m["title"], m["bpm"]
    return f'''// BountifulMusic.cs: adaptive player for the Bountiful game-music export "{title}" (Unity).
// Written from Unity's documented API and not run inside Unity by Bountiful: check it in your project.
// Put layers/ and stingers/ under Assets/Resources/<resourcesFolder>/ with Load Type "Decompress On Load".
//   music.SetState("combat");   crossfades the layers over fadeSeconds
//   music.Stinger("victory");   plays on the next bar (or beat) of the loop
using System.Collections.Generic;
using UnityEngine;

public class BountifulMusic : MonoBehaviour
{{
    public string resourcesFolder = "Music/{folder}";
    public string startState = "explore";
    public float fadeSeconds = 1.5f;

    const double Bpm = {bpm};
    static readonly string[] Layers = {{{layer_list}}};
    static readonly Dictionary<string, float[]> States = new Dictionary<string, float[]>
    {{
{states}
    }};
    static readonly Dictionary<string, bool> OnBeat = new Dictionary<string, bool> {{{quant}}};

    readonly List<AudioSource> sources = new List<AudioSource>();
    float[] current, target;
    double startDsp;

    void Start()
    {{
        startDsp = AudioSettings.dspTime + 0.2;
        foreach (var name in Layers)
        {{
            var src = gameObject.AddComponent<AudioSource>();
            src.clip = Resources.Load<AudioClip>(resourcesFolder + "/layers/" + name);
            src.loop = true;
            src.playOnAwake = false;
            src.volume = 0f;
            src.PlayScheduled(startDsp);
            sources.Add(src);
        }}
        current = new float[Layers.Length];
        target = new float[Layers.Length];
        SetState(startState, true);
    }}

    public void SetState(string state, bool instant = false)
    {{
        if (!States.TryGetValue(state, out var mix)) return;
        target = (float[])mix.Clone();
        if (instant) {{ current = (float[])mix.Clone(); Apply(); }}
    }}

    void Update()
    {{
        if (current == null) return;
        float step = fadeSeconds > 0f ? Time.deltaTime / fadeSeconds : 1f;
        for (int i = 0; i < current.Length; i++) current[i] = Mathf.MoveTowards(current[i], target[i], step);
        Apply();
    }}

    void Apply()
    {{
        for (int i = 0; i < sources.Count; i++) sources[i].volume = current[i];
    }}

    public void Stinger(string name)
    {{
        var clip = Resources.Load<AudioClip>(resourcesFolder + "/stingers/" + name);
        if (clip == null) return;
        double unit = 60.0 / Bpm * (OnBeat.TryGetValue(name, out var beat) && beat ? 1.0 : 4.0);
        double now = AudioSettings.dspTime;
        double since = now - startDsp;
        double at = since < 0 ? startDsp : startDsp + System.Math.Ceiling(since / unit) * unit;
        var src = gameObject.AddComponent<AudioSource>();
        src.clip = clip;
        src.playOnAwake = false;
        src.PlayScheduled(at);
        Destroy(src, (float)(at - now) + clip.length + 0.1f);
    }}
}}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("track", type=Path)
    ap.add_argument("--section", type=int, help="section number (1 = first; see --list)")
    ap.add_argument("--bars", help="a-b instead of a section")
    ap.add_argument("--list", action="store_true", help="list the sections and their energy")
    ap.add_argument("--no-stingers", action="store_true")
    ap.add_argument("--ogg", action="store_true", help="also write OGG copies with loop tags (needs ffmpeg)")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    if a.list:
        secs = sections(a.track)
        top = busiest(secs)
        for s in secs:
            mark = "  <- default" if top and s["index"] == top["index"] else ""
            print(f"{s['index'] + 1:3d}  bars {s['start']:3d}-{s['start'] + s['bars'] - 1:3d}  {s['name']:14s} "
                  f"energy {s['energy']:6.1f}  {', '.join(s['parts'])}{mark}")
        return
    bars = tuple(int(v) for v in a.bars.split("-")) if a.bars else None
    m = make(a.track, None if a.section is None else a.section - 1, bars, not a.no_stingers, a.ogg, a.out)
    print(json.dumps({k: m[k] for k in ("folder", "bpm", "key", "loop")}, indent=1))


if __name__ == "__main__":
    main()
