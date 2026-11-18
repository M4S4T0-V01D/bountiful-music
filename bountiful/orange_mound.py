#!/usr/bin/env python3
"""'Orange Mound Fog': a Memphis rap / phonk instrumental by M4S4T0, 70 bpm in G minor, 64 bars (~3:39), made to rap over.

The MIDI is composed here: a 4-bar loop Gm | Gm Ab | Eb | D7b9, an eerie tresillo (3-3-2) piano riff doubled by a music box
in the hooks, a pitched TR-808 cowbell hook melody, a choir under the hooks and a tuned 808 bass (bountiful/tr808_voice.py)
that slides an octave up and between chord tones. Bountiful lays the drum grid around it.

Made for vocals: hooks (8 bars) carry the cowbell, the music box and the choir; verses (16 bars) leave the 1-4 kHz band to
the rapper (riff low-passed and quieter, no lead) and stop the beat after beat 3 of their last bar, a pocket for the last line
before the hook. Verse 2 opens with 808 and hats only. Form: Intro 4 | Hook 8 | Verse 16 | Hook 8 | Verse 16 | Hook 8 | Outro 4.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python -I bountiful/orange_mound.py              # build + checks
    ~/Documents/Projects/intelligent-jungle/.venv/bin/python -I bountiful/orange_mound.py --validate   # checks only
"""
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import album_mezzanine_v2 as A2  # noqa: E402
import lmms_tracks as LT  # noqa: E402
import moss_radio as MR  # noqa: E402  (its GeneralUser GS helper and soundfont copy)

import mido  # noqa: E402
import numpy as np  # noqa: E402

LT.B.produce = MR._produce                                 # moss_radio swaps produce on import; this file does its own swap below
ROOT = A2.ROOT
TITLE, SLUG, BPM = "Orange Mound Fog", "orange-mound-fog", 70
SONG = MR.SONG                                             # only for the drum grid's bar count
DM = A2.dm
CRACKLE = ROOT / "samples" / "lofi" / f"vinyl_crackle_4bar_{BPM}.wav"
VOICE808 = Path(__file__).resolve().parent / "tr808_voice.py"
COWBELL = ROOT / "samples" / "phonk" / "cowbell808_tuned.wav"
blk, gs = A2.blk, MR.gs

# ------------------------------------------------------------------ harmony
CH = {"Gm": (7, [0, 3, 7]), "Ab": (8, [0, 4, 7]), "Eb": (3, [0, 4, 7]), "D7b9": (2, [0, 4, 7, 10, 13])}
LOOP = [["Gm"], ["Gm", "Ab"], ["Eb"], ["D7b9"]]
SCALE = {7, 8, 9, 10, 0, 2, 3, 5, 6}                       # G minor with the Phrygian b2 (Ab) and the raised 7th (F#)

# ------------------------------------------------------------------ written parts: per bar [step16, pitch, length16, vel]
RIFF = [[[0, 67, 3, .8], [3, 74, 3, .7], [6, 70, 2, .65], [8, 67, 3, .75], [11, 74, 3, .65], [14, 75, 2, .6]],
        [[0, 74, 3, .75], [3, 70, 3, .65], [6, 67, 2, .6], [8, 68, 3, .8], [11, 72, 3, .65], [14, 75, 2, .6]],
        [[0, 70, 3, .75], [3, 75, 3, .7], [6, 67, 2, .6], [8, 70, 3, .7], [11, 79, 3, .7], [14, 75, 2, .6]],
        [[0, 66, 3, .8], [3, 72, 3, .7], [6, 75, 2, .65], [8, 74, 3, .75], [11, 66, 3, .65], [14, 69, 2, .6]]]
BELL = [[[0, 79, 2, .9], [3, 79, 1, .6], [4, 82, 2, .8], [6, 79, 2, .7], [8, 86, 3, .9], [11, 84, 2, .7], [13, 82, 1, .6], [14, 79, 2, .7]],
        [[0, 77, 2, .8], [3, 79, 1, .6], [4, 80, 4, .85], [8, 84, 2, .8], [10, 80, 2, .7], [12, 79, 4, .75]],
        [[0, 82, 2, .9], [3, 82, 1, .6], [4, 87, 2, .8], [6, 82, 2, .7], [8, 86, 3, .85], [11, 84, 2, .7], [13, 82, 1, .6], [14, 79, 2, .7]],
        [[0, 78, 3, .9], [3, 81, 3, .75], [6, 84, 2, .8], [8, 87, 4, .85], [12, 86, 4, .8]]]
# the 808: a 5th field "s" ties the note into the next one, so the voice slides there instead of hitting again
B808 = [[[0, 31, 7, 1.], [7, 31, 3, .85], [10, 31, 4, .9, "s"], [14, 43, 2, .75]],
        [[0, 31, 6, 1.], [6, 31, 2, .8], [8, 32, 6, .95, "s"], [14, 34, 2, .8]],
        [[0, 39, 7, 1.], [7, 39, 3, .8], [10, 34, 4, .85], [14, 39, 2, .75]],
        [[0, 38, 6, 1.], [6, 38, 2, .8], [8, 38, 4, .9, "s"], [12, 42, 2, .8, "s"], [14, 38, 2, .7]]]
POCKET808 = [[0, 38, 12, 1.]]                              # last verse bar: one long D under the drop

# ------------------------------------------------------------------ arrangement: (name, bars, parts)
SECTIONS = [("Intro", 4, {"riff": .8, "choir": 1}),
            ("Hook 1", 8, {"riff": 1., "box": 1, "bell": 1, "choir": 1, "808": 1}),
            ("Verse 1", 16, {"riff": .7, "808": 1, "tubular": 1, "pocket": 1}),
            ("Hook 2", 8, {"riff": 1., "box": 1, "bell": 1, "choir": 1, "808": 1}),
            ("Verse 2 open", 2, {"riff": .7, "808": 1}),
            ("Verse 2", 14, {"riff": .7, "808": 1, "tubular": 1, "pocket": 1}),
            ("Hook 3", 8, {"riff": 1., "box": 1, "bell": 1, "choir": 1, "808": 1}),
            ("Outro", 4, {"riff": .75, "choir": 1, "808_out": 1})]
ALL = sum(s[1] for s in SECTIONS)
VERSES = [("Verse 1", 16), ("Verse 2 open", 16)]           # (first block, bars) of each verse, for the checks
HOOKS = ["Hook 1", "Hook 2", "Hook 3"]


def start_bar(name):
    return 1 + sum(s[1] for s in SECTIONS[:[s[0] for s in SECTIONS].index(name)])


def chord_voicing(name, lo=55, hi=72):
    root, iv = CH[name]
    tones = [(root + i) % 12 for i in iv[:3]] + ([(root + iv[3]) % 12] if len(iv) > 3 else [])
    out = []
    for pc in tones:
        p = lo + (pc - lo) % 12
        out.append(p if p <= hi else p - 12)
    return sorted(set(out))


# ------------------------------------------------------------------ the MIDI
def compose():
    """{track: [(start_beat, end_beat, pitch, vel)]} and the chord per half bar (for the checks)"""
    rng = np.random.default_rng(70)
    beat_ms = 60000 / BPM
    out = {k: [] for k in ("riff", "box", "bell", "choir", "tubular", "boom")}
    chart = []

    def put(track, bar, step, pitch, length, vel, jitter=6, gap=0.04):
        s = max(0.0, (bar - 1) * 4 + step / 4 + (rng.normal(0, jitter) / beat_ms if jitter else 0))
        out[track].append((s, max(s + 0.05, (bar - 1) * 4 + (step + length) / 4 - gap), pitch,
                           float(np.clip(vel + rng.normal(0, 0.03), 0.2, 1.0))))

    bar = 1
    for name, bars, parts in SECTIONS:
        for i in range(bars):
            li = (bar - 1) % 4                             # the loop runs from bar 1, whatever the section
            names = LOOP[li]
            half = 16 // len(names)
            for k, cn in enumerate(names):
                chart.append((bar, k * half, cn))
                if parts.get("choir"):
                    for p in chord_voicing(cn):
                        put("choir", bar, k * half, p, half, 0.5 if name != "Intro" else 0.42, jitter=0, gap=0.0)
            pocket = parts.get("pocket") and i == bars - 1
            if parts.get("riff"):
                for s, p, n, v in RIFF[li]:
                    put("riff", bar, s, p, n, v * parts["riff"])
            if parts.get("box"):
                for s, p, n, v in RIFF[li]:
                    put("box", bar, s, p + 12, n, v * 0.8, jitter=3)
            if parts.get("bell"):
                for s, p, n, v in BELL[li]:
                    put("bell", bar, s, p, n, v, jitter=3)
            if parts.get("tubular") and (bar - 1) % 8 == 4:   # one far-off bell every 8 verse bars
                put("tubular", bar, 0, 74, 16, 0.5, jitter=0)
            line = POCKET808 if pocket else B808[li] if parts.get("808") else \
                B808[li] if parts.get("808_out") and i < 2 else []
            for e in line:
                s, p, n, v = e[:4]
                put("boom", bar, s, p, n, v, jitter=0, gap=0.0 if len(e) > 4 else 0.08)
            bar += 1
    out["boom"].sort()
    return out, chart


def write_parts(mid: Path):
    """swap every pitched track of Bountiful's MIDI for the composed ones (the tempo track and the drum grid stay)"""
    parts, _ = compose()
    m = mido.MidiFile(str(mid))
    tpb = m.ticks_per_beat
    m.tracks = [t for t in m.tracks if not any(x.type == "note_on" for x in t)
                or any(x.type == "track_name" and x.name == "drums" for x in t)]
    for ch, (name, notes) in enumerate(parts.items()):
        ev = []
        for s, e, p, v in sorted(notes):
            ev += [(int(round(s * tpb)), 1, p, int(round(v * 127))), (int(round(e * tpb)), 0, p, 0)]
        ev.sort(key=lambda x: (x[0], x[1]))
        tr = mido.MidiTrack([mido.MetaMessage("track_name", name=name, time=0)])
        held, last = {}, 0
        for t, on, p, v in ev:
            if on and held.get(p):
                tr.append(mido.Message("note_off", channel=ch, note=p, velocity=0, time=t - last)); last = t
                held[p] -= 1
            elif not on and not held.get(p):
                continue
            tr.append(mido.Message("note_on" if on else "note_off", channel=ch, note=p, velocity=v if on else 0, time=t - last))
            last = t
            held[p] = held.get(p, 0) + (1 if on else -1)
        tr.append(mido.MetaMessage("end_of_track", time=0))
        m.tracks.append(tr)
    m.save(str(mid))


def produce_then_write(song, g, title, out, seed=1, log=print):
    _produce(song, g, title=title, out=out, seed=seed, log=log)
    write_parts(out / f"{SLUG}.mid")
    inst = out / "instruments.toml"
    cfg = tomllib.loads(inst.read_text())
    cfg["tracks"] = {k: v for k, v in cfg["tracks"].items() if k == "drums"}
    inst.write_text(LT.to_toml(cfg))
    loop = " | ".join(" ".join(c) for c in LOOP)
    lines = [f"  {n} ({b} bars, bars {start_bar(n)}-{start_bar(n) + b - 1})" for n, b, _ in SECTIONS]
    (out / "notes.txt").write_text(
        f"{TITLE} — Memphis rap / phonk instrumental, {BPM} bpm, G minor, {ALL} bars ({ALL * 240 / BPM // 60:.0f}:"
        f"{ALL * 240 / BPM % 60:02.0f})\nloop (every section): {loop}\ncomposition: written in bountiful/orange_mound.py "
        "(riff, cowbell hook, 808 line, choir); drums: Bountiful grid\nfor vocals: verses keep 1-4 kHz clear; the last "
        "bar of each verse drops the beat after beat 3\n\n" + "\n".join(lines) + "\n")


_produce = LT.B.produce
LT.B.produce = produce_then_write

# ------------------------------------------------------------------ drums: kick on the 808's hits, clap+snare on 2 and 4
KICKS = {"a": [[0, 1.], [7, .8], [10, .9]], "b": [[0, 1.], [6, .8], [8, .9]],
         "c": [[0, 1.], [7, .8], [10, .85]], "d": [[0, 1.], [6, .8], [8, .9]]}


def hats16(roll=False):
    h = [[s, .62 if s % 4 == 0 else .48 if s % 2 == 0 else .34, "hat"] for s in range(12 if roll else 16)]
    if roll:                                               # 32nds, then a triplet stutter into the next bar
        h += [[12 + k / 2, .32 + .03 * k, "hat"] for k in range(4)] + [[14 + k / 3, .36 + .04 * k, "hat"] for k in range(6)]
    return h


GRID = {
    "kick": KICKS,
    "snare": {"a": [[4, .95, "snare"], [12, .95, "snare"]], "b": [[4, .95, "snare"], [12, .95, "snare"]],
              "c": [[4, .95, "snare"], [12, .95, "snare"]], "d": [[4, .95, "snare"], [12, .95, "snare"], [15, .35, "snare"]]},
    "clap": [[4, .85, "clap", 4], [12, .88, "clap", 6]],
    "hat": {"a": hats16(), "b": hats16(), "c": hats16(), "d": hats16(roll=True)},
    "hat3": {"a": [[k * 4 / 3, .5 if k % 3 == 0 else .34, "hat"] for k in range(12)],
             "b": hats16(), "c": [[k * 4 / 3, .5 if k % 3 == 0 else .34, "hat"] for k in range(12)], "d": hats16(roll=True)},
    "open": [[2, .5, "open"], [10, .45, "open"]],
    "snare_v": {k: [[4, .82, "snare"], [12, .82, "snare"]] for k in "abc"} | {"d":[[4, .82, "snare"], [12, .82, "snare"], [15, .3, "snare"]]},
    "clap_v": [[4, .7, "clap", 4], [12, .72, "clap", 6]],                 # verses: a touch softer, for the vocal
    "perc": {"a": [[6, .5, "clave"]], "b": [[14, .45, "clave"]], "c": [[6, .5, "clave"], [15, .35, "clave"]], "d": []},
    "vinyl": {"a": [[0, .8, "swell"]], "b": [], "c": [], "d": []},
}
DRUMS = {"Intro": ["vinyl"],
         "Hook 1": ["vinyl", "kick", "snare", "clap", "hat", "open", "perc"],
         "Verse 1": ["vinyl", "kick", "snare_v", "clap_v", "hat"],
         "Hook 2": ["vinyl", "kick", "snare", "clap", "hat", "open", "perc"],
         "Verse 2 open": ["vinyl", "hat3"],
         "Verse 2": ["vinyl", "kick", "snare_v", "clap_v", "hat3"],
         "Hook 3": ["vinyl", "kick", "snare", "clap", "hat", "open", "perc"],
         "Outro": ["vinyl"]}
ARR = [blk(n, "A", b, ["comp"], DRUMS[n], crash=n in HOOKS, **({"fill": "drop"} if p.get("pocket") else {}))
       for n, b, p in SECTIONS]

CRUNCH = {"bits": 10, "rate": 22050, "mix": 0.45}
KIT = A2.kit({"kick": (DM("tr808/kick"), "kick", None), "snare": (DM("tr808/snare"), "snare", None),
              "clap": (DM("tr808/handclap"), "snare", {"gain_db": -2}),
              "hat": (DM("tr808/hat_c"), "hats", None), "open": (DM("tr808/hat_o"), "hats", {"gain_db": -6, "lp": 9000}),
              "clave": (DM("tr808/clave"), "perc", None),
              "crash": (DM("tr808/ride"), "hats", {"gain_db": -6, "lp": 8000}), "swell": (str(CRACKLE), "vinyl", {"detune_cents": 0})},
             {"kick": {"hp": 45, "mono": True, "drive": 1.6, "eq": [["peak", 3500, 2.0, 1.0]], "gain_db": -4.0},
              "snare": {"hp": 160, "lp": 9000, "drive": 1.5, "crush": CRUNCH, "sends": {"room": 0.2}, "gain_db": 4.0},
              "hats": {"pan": 0.12, "hp": 400, "lp": 10000, "crush": {"bits": 12, "rate": 26040, "mix": 0.35}, "gain_db": 14.0},
              "perc": {"pan": -0.35, "crush": CRUNCH, "sends": {"echo": 0.25}, "gain_db": 10.0},
              "vinyl": {"hp": 500, "lp": 8000, "gain_db": 0.0}})

BOOM = {"kind": "pyvoice", "glide_gap": 0.04,
        "preset": {"module": str(VOICE808), "fn": "note", "label": "Tuned TR-808 bass drum with slides (bountiful/tr808_voice.py)",
                   "decay": 1.4, "drive": 2.8, "dist_mix": 0.6, "glide": 0.08},
        "hp": 25, "lp": 4000, "mono": True, "gain_db": 0.0}
LOFI = {"bits": 12, "rate": 26040, "mix": 0.4}
WOW = {"depth_ms": 1.4, "rate": 0.5, "flutter_ms": 0.15}

SPEC = {
    "title": TITLE, "genre": "lofi-downtempo", "song": SONG, "album": "", "track": 0, "year": 2026, "seed": 7,
    "composer": LT.B.COMPOSER_CREDIT, "rebuild": "bountiful/orange_mound.py",
    "blurb": "Memphis rap / phonk instrumental at 70 bpm in G minor, made to rap over: an eerie tresillo piano riff over "
             "Gm - Ab - Eb - D7b9, a pitched 808 cowbell hook, a choir, and a tuned, sliding 808 bass under a crunchy TR-808 kit "
             "with rolling hats. Verses leave room for the vocal and drop the beat into every hook.",
    "overrides": {"bpm": BPM, "swing": 0.5, "drums": "grid", "drum_humanize_ms": 4, "arrangement": ARR, "grid": GRID,
                  "master": {"tape": {"drive": 1.6, "bias": 0.06, "bump_db": 1.0, "hf_db": -1.5, "lp_hz": 13000, "hiss_db": -62,
                                      "wow_ms": 0.15}, "target_lufs": -10.0, "true_peak": -1.0, "mono_below": 120}},
    "kit_def": KIT,
    "layers": [],
    "sends": {"echo": {"type": "delay", "time_beats": 0.75, "feedback": 0.4, "tone": 2000, "taps": 5}},
    "voices": {
        "riff": (*gs(0, 0, "Grand Piano"),
                 dict(hp=180, lp=6000, eq=[["peak", 300, -2.0, 1.0]], crush=LOFI, drive=1.2, wow=WOW,
                      sends={"room": 0.25, "plate": 0.15}, width=0.8, gain_db=0.0)),
        "box": (*gs(0, 10, "Music Box"),
                dict(hp=500, lp=8000, crush=LOFI, wow=WOW, pan=0.25, sends={"plate": 0.3, "echo": 0.15}, gain_db=0.0)),
        "bell": ({"sample": str(COWBELL), "root": 73, "vol": 100}, "TR-808 cowbell, tuned and pitched (LMMS AudioFileProcessor)",
                 dict(hp=350, drive=1.6, crush={"bits": 12, "rate": 26040, "mix": 0.3}, sends={"echo": 0.18, "plate": 0.12},
                      width=1.0, gain_db=0.0)),
        "choir": (*gs(0, 52, "Choir Aahs"),
                  dict(hp=220, lp=4500, width=0.9, wow=WOW, sends={"plate": 0.4}, gain_db=0.0)),
        "tubular": (*gs(0, 14, "Tubular Bells"),
                    dict(hp=300, lp=6000, pan=-0.3, crush=LOFI, sends={"plate": 0.45, "echo": 0.3}, gain_db=-17.0)),   # verses only, so untrimmed
    },
    "extra_tracks": {"boom": BOOM},
    "level_ref": "kick",
    "targets": {"boom": 3.0, "riff": -5.0, "box": -11.0, "bell": -6.0, "choir": -13.0},
    "test_bars": (start_bar("Hook 2"), start_bar("Hook 2") + 7),
    "automation": [
        {"type": "lowpass", "tracks": ["riff", "choir"], "points": [[1, 500], [3, 900], [4.5, 1800], [5, 18000]]},
        *[{"type": "lowpass", "tracks": ["riff"], "points": [[start_bar(v), 18000], [start_bar(v) + 0.01, 2400],
                                                            [start_bar(v) + b - 0.01, 2400], [start_bar(v) + b, 18000]]}
          for v, b in VERSES],
        {"type": "lowpass", "tracks": ["riff", "choir", "boom"], "points": [[start_bar("Outro"), 18000], [ALL + 1, 700]]},
        {"type": "gain", "tracks": ["riff", "choir", "boom", "vinyl"], "points": [[start_bar("Outro") + 2, 0], [ALL, -10], [ALL + 1.5, -40]]}],
    "mmp_drums": True,
    "lead_hi_follows_lead": False,
}


def setup():
    if not MR.SF2.exists():                                # moss_radio copies the soundfont once
        MR.setup()
    if CRACKLE.exists():
        return
    import soundfile as sf
    from engine import fx
    rng = np.random.default_rng(70)
    n = int(round(16 * 60 / BPM * fx.SR)) + fx.SR // 2
    clicks = (rng.random(n) < 9.0 / fx.SR) * rng.standard_normal(n) * rng.random(n) ** 3
    pops = (rng.random(n) < 0.6 / fx.SR) * rng.standard_normal(n) * 2.0
    x = fx.bp((clicks + pops).astype(np.float32), 900, 7000) * 3.0
    x += fx.lp(rng.standard_normal(n).astype(np.float32), 4000) * 0.03
    x[:200] *= np.linspace(0, 1, 200)
    x[-fx.SR // 2:] *= np.linspace(1, 0, fx.SR // 2)
    x[0] = max(abs(x).max(), 1e-3)                         # a click on the onset so the loader does not trim the start
    CRACKLE.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(CRACKLE), (x / abs(x).max() * 0.9).astype(np.float32), fx.SR)


# ------------------------------------------------------------------ checks
def validate():
    import soundfile as sf
    from render_midi import read_midi
    track = LT.B.DATA / "tracks" / SLUG
    an = json.loads((track / "exports" / "render_info.json").read_text())["analysis"]
    notes, bpm, _ = read_midi(track / f"{SLUG}.mid")
    bar_s, beat = 4 * 60 / bpm, 60 / bpm
    res = []

    def check(name, ok, detail):
        res.append((name, bool(ok), detail))

    check("length 3:00-4:00", 180 <= an["duration_s"] <= 240, f"{an['duration_s']:.1f} s")
    check("loudness -10 LUFS (+-0.7)", abs(an["integrated_lufs"] + 10) <= 0.7, f"{an['integrated_lufs']} LUFS")
    check("true peak <= -1 dBTP", an["true_peak_dbtp_approx"] <= -0.95, f"{an['true_peak_dbtp_approx']} dBTP")
    check("no clipping", an["clipped_samples"] == 0, f"{an['clipped_samples']} samples")
    check("low end mono (corr <120 Hz > 0.95)", an["correlation_below_120hz"] > 0.95, f"{an['correlation_below_120hz']}")
    tracks = {n["track"] for n in notes}
    check("composed parts in the MIDI", {"riff", "box", "bell", "choir", "tubular", "boom", "drums"} <= tracks, ", ".join(sorted(tracks)))
    drums = [n for n in notes if n["track"] == "drums"]
    swell = A2.PR.GM["swell"]
    intro = [n for n in drums if n["start"] < 4 * bar_s - 0.01 and n["pitch"] != swell]
    check("intro: no drums", not intro, f"{len(intro)} drum hits in bars 1-4")

    def in_bars(ns, a, b):
        return [n for n in ns if (a - 1) * bar_s - 0.01 <= n["start"] < (b - 1) * bar_s - 0.01]
    bell = [n for n in notes if n["track"] == "bell"]
    vb = sum(len(in_bars(bell, start_bar(v), start_bar(v) + b)) for v, b in VERSES)
    check("no cowbell lead in the verses", vb == 0, f"{vb} cowbell notes in verses")
    pockets = [start_bar(v) + b - 1 for v, b in VERSES]
    late = [n for p in pockets for n in in_bars(drums, p, p + 1)
            if n["pitch"] != swell and (n["start"] - (p - 1) * bar_s) > 3 * beat + 0.02]
    check("verse pockets: beat stops after beat 3 of each verse's last bar", not late, f"{len(late)} hits after beat 3")
    _, chart = compose()

    def chord_at(t):
        b, s = int(t / bar_s) + 1, (t % bar_s) / beat * 4
        cur = None
        for cb, cs, cn in chart:
            if (cb, cs) <= (b, s + 0.5):
                cur = cn
        root, iv = CH[cur]
        return {(root + i) % 12 for i in iv}
    mel = [n for n in notes if n["track"] in ("bell", "riff")]
    bad = [n for n in mel if n["pitch"] % 12 not in chord_at(n["start"]) | SCALE]
    check("riff and hook in G (harmonic) minor", not bad, f"{len(bad)}/{len(mel)} outside")
    boom = [n for n in notes if n["track"] == "boom"]
    strong = [n for n in boom if ((n["start"] % bar_s) / beat) % 2 < 0.05]
    off = [n for n in strong if n["pitch"] % 12 not in chord_at(n["start"] + 0.01)]
    check("808 on beats 1 and 3 is a chord tone", not off, f"{len(off)}/{len(strong)} off")
    x, sr = sf.read(str(track / "exports" / f"{SLUG}.wav"), dtype="float32", always_2d=True)
    m = x.mean(1)

    def band_db(a, b, lo, hi):
        seg = m[int((a - 1) * bar_s * sr):int((b - 1) * bar_s * sr)]
        spec = np.abs(np.fft.rfft(seg)) ** 2
        f = np.fft.rfftfreq(len(seg), 1 / sr)
        return 10 * np.log10(spec[(f >= lo) & (f < hi)].sum() + 1e-12)
    h = start_bar("Hook 2")
    lows, mids = band_db(h, h + 8, 20, 120), band_db(h, h + 8, 120, 8000)
    check("bass heavy: energy < 120 Hz above 120 Hz-8 kHz (hook 2)", lows - mids >= 2.0, f"{lows - mids:+.1f} dB")
    v = start_bar("Verse 1")
    vox_v = band_db(v, v + 15, 1000, 4000) - 10 * np.log10(15)
    vox_h = band_db(h, h + 8, 1000, 4000) - 10 * np.log10(8)
    check("room for vocals: verse 1-4 kHz >= 3 dB under the hook", vox_h - vox_v >= 3.0, f"{vox_h - vox_v:.1f} dB")
    n_ok = sum(ok for _, ok, _ in res)
    lines = [f"- {'PASS' if ok else 'FAIL'} {name}: {d}" for name, ok, d in res]
    print("\n".join(lines))
    print(f"{n_ok}/{len(res)} checks pass")
    (track / "validation.md").write_text(f"# {TITLE}: validation\n\n" + "\n".join(lines) + f"\n\n{n_ok}/{len(res)} checks pass\n")
    return n_ok == len(res)


if __name__ == "__main__":
    if "--validate" not in sys.argv:
        setup()
        LT.make(SPEC, log=lambda m: print(m, flush=True))
    validate()
