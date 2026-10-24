#!/usr/bin/env python3
"""'Haze Theory': a classic 1992-95 atmospheric jungle track at 174 bpm, built to a written brief with the existing
pipeline (Bountiful Music composition, break_maker, LMMS instruments, render_midi mix/master, lmms_tracks recipe).

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/jungle174.py            # break + song
    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/jungle174.py --validate # checks only

The break: the brief's 16-step blueprint (kick 1, 7, 12 / snare 5, 13 / ghosts 3, 8, 10, 14 / hats) performed on the
break_maker's acoustic kit at 145 bpm, recorded through its room/compressor/saturation/12-bit chain, sped up to 174 on a
sampler (+3.2 semitones), cut into 16th slices, 32nd slices and a hats-only take, plus processed one-shots for extra
ghosts and kicks. Breaks A (main), B (rolling) and C (transition) are built from those slices.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import break_maker as BM  # noqa: E402
import lmms_tracks as LT  # noqa: E402
import producer as PR  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BPM, PLAY = 174, 145
OUT = ROOT / "samples" / "breaks" / "haze174"
SR = 44100

# ------------------------------------------------------------------ the blueprint (0-based 16th steps)
HATS = (0, 2, 3, 4, 6, 8, 9, 10, 12, 14, 15)
BLUE = {"kick": [[(0, 1.0), (6, 0.9), (11, 0.92)]] * 4,
        "snare": [[(4, 0.95), (12, 0.97)]] * 4,
        "ghost": [[(2, 0.32), (7, 0.27), (9, 0.3), (13, 0.35)]] * 4,
        "hat": [[(s, 0.52 if s % 4 == 0 else 0.42 if s % 2 == 0 else 0.3) for s in HATS]] * 4}


def build_break():
    """Record the blueprint, speed it up, slice it; returns nothing (files in OUT)."""
    OUT.mkdir(parents=True, exist_ok=True)
    bus, step = BM.perform(PLAY, seed=174, pattern=BLUE, ride_on=False)
    full = BM.record(bus)
    hats_bus, _ = BM.perform(PLAY, seed=174, pattern=BLUE, ride_on=False, mute=("kick", "snare"))
    hats = BM.record(hats_bus) * 0.6
    sf.write(str(OUT / f"break_{PLAY}.wav"), full[: int(64 * step * SR)], SR, subtype="PCM_24")
    fast, fh = BM.speed(full, PLAY, BPM), BM.speed(hats, PLAY, BPM)
    st = 60 / BPM / 4
    n1 = st * SR
    fade = int(0.0015 * SR)
    sf.write(str(OUT / f"break_{BPM}.wav"), fast[: int(round(64 * n1))], SR, subtype="PCM_24")

    def cut(src, a, b, name, fade_in=True):
        s = src[int(round(a)): int(round(b)) + fade].copy()
        s[-fade:] *= np.linspace(1, 0, fade)[:, None]
        if fade_in:
            s[:fade] *= np.linspace(0, 1, fade)[:, None]
        sf.write(str(OUT / f"{name}.wav"), s.astype(np.float32), SR, subtype="PCM_24")

    for i in range(64):
        cut(fast, i * n1, (i + 1) * n1, f"s{i:02d}", fade_in=i > 0)
    for i in (0, 4, 6, 11, 12):                     # 32nd slices: the first half of a hit
        cut(fast, i * n1, (i + 0.5) * n1, f"t{i:02d}")
    for i in range(16):                             # the hats-only take, one bar
        cut(fh, i * n1, (i + 1) * n1, f"h{i:02d}", fade_in=i > 0)
    ride_bus, _ = BM.perform(PLAY, seed=175, pattern={"kick": [[]]}, ride_on=True, mute=("kick", "snare"))
    fr = BM.speed(BM.record(ride_bus) * 0.7, PLAY, BPM)
    for k in range(4):                              # the ride-only take, whole bars
        cut(fr, 16 * k * n1, 16 * (k + 1) * n1, f"rd{k}", fade_in=k > 0)
    for name, pat in (("kick1", {"kick": [[(0, 1.0)]]}), ("snr1", {"snare": [[(0, 1.0)]]}), ("gh1", {"ghost": [[(0, 1.0)]]})):
        b, _ = BM.perform(PLAY, seed=7, pattern=pat, bars=1, ride_on=False)
        x = BM.speed(BM.record(b), PLAY, BPM)
        on = int(np.argmax(np.abs(x).max(1) > 0.02))
        cut(x[max(0, on - 32):], 0, 0.3 * SR, name)
    print(f"break: {OUT} ({len(list(OUT.glob('*.wav')))} files)")


SOUNDS = ([f"s{i:02d}" for i in range(64)] + [f"t{i:02d}" for i in (0, 4, 6, 11, 12)] + [f"h{i:02d}" for i in range(16)]
          + ["kick1", "snr1", "gh1", "kreinf", "snlay", "s04u", "s12d", "s02u", "s07d", "s13u", "rd0", "rd1", "rd2", "rd3"])
NOTES = {s: 20 + k for k, s in enumerate(SOUNDS)}
PR.GM.update(NOTES)
PITCHED = {"s04u": ("s04", 1.5), "s12d": ("s12", -1.0), "s02u": ("s02", 2.0), "s07d": ("s07", -2.0), "s13u": ("s13", 1.0)}


def kit():
    snd = {}
    for s in SOUNDS:
        if s in PITCHED:
            src, semis = PITCHED[s]
            snd[s] = {"samples": [str(OUT / f"{src}.wav")], "pitch": semis, "stem": "breakfx", "detune_cents": 0}
        elif s[0] == "t":
            snd[s] = {"samples": [str(OUT / f"{s}.wav")], "stem": "breakfx", "detune_cents": 0}
        elif s[0] in "sh" and s[1:].isdigit():
            snd[s] = {"samples": [str(OUT / f"{s}.wav")], "stem": "break", "detune_cents": 0}
        elif s.startswith("rd"):
            snd[s] = {"samples": [str(OUT / f"{s}.wav")], "stem": "ride", "detune_cents": 0}
        elif s in ("kick1", "snr1", "gh1"):
            snd[s] = {"samples": [str(OUT / f"{s}.wav")], "stem": "break", "detune_cents": 4}
    snd["kreinf"] = {"samples": ["/usr/share/lmms/samples/drums/bassdrum01.ogg"], "lp": 160, "stem": "kick", "detune_cents": 0}
    snd["snlay"] = {"samples": ["/usr/share/lmms/samples/drums/snare01.ogg"], "hp": 1500, "stem": "snlay", "detune_cents": 6}
    return {"map": {str(NOTES[s]): s for s in snd}, "sounds": snd,
            "stems": {"break": {"hp": 30, "eq": [["peak", 110, 1.5, 0.9], ["highshelf", 8000, -2.0]], "sends": {"room": 0.08}, "gain_db": -2.0},
                      "breakfx": {"hp": 60, "sends": {"slap": 0.3, "room": 0.1}, "gain_db": -3.0},
                      "kick": {"hp": 30, "mono": True, "gain_db": -14.0},
                      "ride": {"hp": 500, "eq": [["highshelf", 9000, -2.0]], "sends": {"room": 0.12}, "gain_db": -11.0},
                      "snlay": {"hp": 1500, "sends": {"room": 0.15}, "gain_db": 0.0}}}


# ------------------------------------------------------------------ breaks A, B, C, built from slices
def base(b, steps=range(16)):
    return [[i, 1.0, f"s{16 * b + i:02d}"] for i in steps]


def swap(bar, step, entry):
    return [e for e in bar if e[0] != step] + ([entry] if entry else [])


A = {"a": base(0),
     "b": swap(base(1), 14, [14, 0.9, "s11"]),                                   # a kick slice moved into the second half
     "c": base(2),
     "d": swap(swap(base(3), 15, [15, 0.55, "t12"]), 15.5, None) + [[15.5, 0.7, "t12"]]}   # 32nd snare pickup into the next bar
B = {"a": base(0) + [[5, 0.24, "gh1", 4], [15, 0.3, "gh1", -3], [9, 0.7, "kick1"]],      # extra ghosts (late/early), a syncopated kick
     "b": [e for e in base(1) if e[0] not in (8, 9, 10, 11)] + [[8, 1.0, "s00"], [9, 1.0, "s01"], [10, 1.0, "s02"], [11, 1.0, "s03"]]
          + [[3, 0.26, "gh1", 3], [7, 0.85, "s07d"]],                            # a re-cut half bar: kick on 9 instead of 7; a lower ghost
     "c": swap(base(2), 2, [2, 0.9, "s02u"]) + [[14, 0.7, "kick1"], [13, 0.22, "gh1", 5]],
     "d": swap(swap(swap(base(3), 13, [13, 0.95, "s13u"]), 14, [14, 0.8, "t12"]), 15, [15, 0.9, "s15"]) + [[14.5, 0.85, "t12"]]}
C = {"a": [e for e in base(0) if e[0] < 8] + [[8, 1.0, "s00"], [9, 1.0, "s01"], [11, 0.95, "s11"],      # a gap on 10, then
                                             [12, 1.0, "s12"], [13, 0.8, "s04"], [14, 0.6, "t12"], [14.5, 0.75, "t12"],
                                             [15, 0.9, "s04u"], [15.5, 1.0, "s04u"]],                # snare doubles, pitched up into the next bar
     "b": [e for e in base(1) if e[0] < 8] + [[8, 0.85, "s04"], [9, 0.0, "s05"], [10, 0.9, "s12d"], [11, 0.0, "s13"],
                                             [12, 1.0, "s12"], [13, 0.75, "t04"], [13.5, 0.85, "t04"], [14, 0.9, "s04"],
                                             [15, 0.8, "t12"], [15.5, 1.0, "s04u"]]}
C = {k: [e for e in v if e[1] > 0] for k, v in C.items()}
# A2: the main break breathing: extra ghost one-shots (early/late), shuffled hats from the hats-only take, one re-cut beat
A2 = {"a": base(0) + [[3, 0.2, "gh1", -4], [11, 0.32, "h11", 5]],
      "b": swap(swap(base(1), 10, [10, 0.9, "s06"]), 11, [11, 0.6, "s07"]) + [[15, 0.25, "gh1", 6]],        # beat 3 re-cut: the kick comes early
      "c": base(2) + [[5, 0.34, "h13", -3], [9, 0.22, "gh1", 3], [13, 0.36, "h15", 4]],
      "d": swap(base(3), 14, [14, 0.85, "s02u"])}


# the fill library: every fill bar in the song is its own edit, placed by hand (FILLS below)
def head(b, upto):
    return [e for e in base(b) if e[0] < upto]


F = {"F1": C["a"],                                                                # gap on 10, snare doubles, pitched up
     "F2": C["b"],                                                                # snare/low-snare call and answer, 32nd doubles
     "F3": head(2, 12) + [[14, 0.55, "t12"], [14.5, 0.7, "t12"], [15, 0.8, "t04"], [15.5, 0.95, "s04u"]],   # drop-out: two steps of air, then a pickup
     "F4": head(0, 8) + [[8 + i, 0.55 + 0.05 * i, "s04" if i % 2 == 0 else "s05"] for i in range(6)] + [[14, 0.9, "s04u"], [15, 1.0, "s04u"]],  # half-bar stutter
     "F5": head(1, 8) + [[8 + i, 0.18 + 0.05 * i, "gh1", (-3, 4, -2, 5, 0, -4, 3, 0)[i]] for i in range(8)] + [[8, 0.9, "s00"], [12, 1.0, "s12"], [15, 0.9, "s04u"]],  # ghost roll
     "F6": swap(base(2), 15, None) + [[3, 0.65, "kick1"], [10, 0.7, "kick1"], [7, 0.8, "s07d"]],     # kick shuffle, the last step left empty
     "F7": head(0, 8) + [[8 + e[0], e[1], e[2]] for e in head(0, 8) if e[0] < 7] + [[15, 0.6, "t12"], [15.5, 0.8, "t12"]],  # a half-bar repeat
     "F8": head(3, 4) + [[4 + i / 2, 0.35 + 0.026 * i, "t12" if i % 2 else "t04"] for i in range(22)] + [[15, 0.95, "s04u"], [15.5, 1.0, "s13u"]],  # the one snare roll-in (into the main drop)
     "PU": [[8, 0.3, "gh1", 3], [10, 0.35, "gh1", -2], [12, 0.8, "s12"], [13, 0.4, "gh1"], [14, 0.6, "t12"], [14.5, 0.75, "t12"], [15, 0.85, "s04u"], [15.5, 1.0, "s04u"]]}
VARY = {"s04u": "s13u", "s12": "s12d", "s04": "s02u", "t12": "t04", "s05": "t06"}


def vary(f):
    """a fill's second outing: the same edit with its snare slices swapped for pitched / 32nd ones"""
    return [[e[0], e[1], VARY.get(e[2], e[2]), *e[3:]] for e in f]


F |= {k + "v": vary(F[k]) for k in ("F1", "F2", "F3", "F4", "F5", "F7")}
F["F9"] = head(1, 8) + [[12, 0.7, "s12d"], [15.5, 0.5, "t04"]]                 # the long drop-out: half a bar of air before the second passage
F["F6v"] = swap(swap(base(2), 15, None), 14, None) + [[9, 0.7, "kick1"], [13, 0.6, "kick1"], [14, 0.5, "gh1", 4]]
PROGRAMS = {"A": A, "A2": A2, "B": B, **F,
            "hats": [[i, 0.85, f"h{i:02d}", round(float(np.random.default_rng(i).normal(0, 3)), 1) if i % 2 else 0.0] for i in range(16)],
            "frag": {"a": [[4, 0.55, "s04"], [12, 0.6, "s12"]], "b": [[4, 0.5, "s04"], [7, 0.3, "s07"], [12, 0.6, "s12"], [14.5, 0.45, "t12"]]},
            "unrest": {"a": [[6, 0.45, "s07d"], [10, 0.4, "s02u", 6], [12, 0.6, "s12d"]], "b": [[3, 0.3, "gh1", 5], [12, 0.55, "s12"], [14, 0.45, "s13u"]],
                       "c": [[4, 0.5, "s04"], [9, 0.35, "s07d", -4], [12, 0.55, "s12d"], [15, 0.4, "t12"]]},
            "ride": {"a": [[0, 0.8, "rd0"]], "b": [[0, 0.8, "rd1"]], "c": [[0, 0.8, "rd2"]], "d": [[0, 0.8, "rd3"]]},
            "kr": [[0, 0.9, "kreinf"], [6, 0.75, "kreinf"], [11, 0.8, "kreinf"]],
            "sl": [[4, 0.5, "snlay"], [12, 0.55, "snlay"]]}


def blk(name, loop, bars, parts=(), drums=(), **kw):
    return {"name": name, "loop": loop, "bars": bars, "parts": list(parts), "drums": list(drums), **kw}


def groove(name, loop, parts, breaks, fills, extra=("kr", "sl"), restart=False):
    """8-bar blocks: seven bars of a break (each block's own: breaks[k], e.g. "A" or ["A2", "ride"]) and a fill bar (fills[k])."""
    out = []
    for k, (brk, fill) in enumerate(zip(breaks, fills)):
        brk = [brk] if isinstance(brk, str) else list(brk)
        out += [blk(name + (f" {k + 1}" if len(fills) > 1 else ""), loop, 7, parts, [*brk, *extra], loop_restart=restart and k == 0),
                blk(f"{name}: fill {fill}", loop, 1, parts, [fill, *extra])]
    return out


FULL = ["pad", "bass", "lead", "comp", "vox"]
ARR = ([blk("Pad intro A", "A", 8, ["pad"]),
        blk("Pad intro B", "A", 8, ["pad", "vox", "lead_hi"]),
        blk("Percussion introduction", "A", 8, ["pad", "vox"], ["hats", "frag"])]
       + groove("First full break", "A", ["pad", "bass2"], ["A", "A"], ["F1", "F3"], restart=True)
       + groove("Main groove A", "V", ["pad", "bass", "comp"], ["A", "A2"], ["F4", "F2"])
       + groove("Main groove B", "V", ["pad", "bass", "lead", "comp"], ["B", "B"], ["F5", "F3v"])
       + [blk("Atmospheric breakdown", "B", 8, ["pad", "vox", "lead", "comp"]),
          blk("Atmospheric breakdown: hats return", "B", 8, ["pad", "vox", "lead", "comp"], ["hats"], vel={"lead": 0.9})]
       + [blk("Break reintroduction", "A", 7, ["pad", "bass2"], ["A", "kr"]), blk("Break reintroduction: roll-in F8", "A", 1, ["pad", "bass2"], ["F8", "kr"])]
       + groove("Main drop / groove return", "A", FULL, ["A", "A2", ["A2", "ride"]], ["F7", "F2v", "F5v"], restart=True)
       + [blk("Breakbeat variation: A", "V", 4, FULL[:4], ["A", "kr", "sl"]), blk("Breakbeat variation: B", "V", 3, FULL[:4], ["B", "kr", "sl"]),
          blk("Breakbeat variation: fill F6", "V", 1, FULL[:4], ["F6", "kr", "sl"]),
          blk("Breakbeat variation: A2", "V", 4, FULL[:4], ["A2", "kr", "sl"]), blk("Breakbeat variation: B again", "V", 3, FULL[:4], ["B", "kr", "sl"]),
          blk("Breakbeat variation: drop-out F9", "V", 1, FULL[:4], ["F9", "kr"])]
       # the second passage is not the first breakdown again: other chords (loop V), the vibraphone motif instead of the Rhodes
       # phrases, long sub notes, and loose pitched fragments that grow more restless; then a bar of subtraction and a pickup
       + [blk("Second atmospheric passage", "V", 8, ["pad", "vox", "lead_hi", "comp", "bass2"], ["hats", "frag"], vel={"bass2": 0.7}),
          blk("Second atmospheric passage: unrest", "V", 6, ["pad", "vox", "lead_hi", "comp", "bass2"], ["hats", "unrest", "ride"], vel={"bass2": 0.75}),
          blk("Second atmospheric passage: subtraction", "V", 1, ["pad", "vox"]),
          blk("Second atmospheric passage: pickup", "V", 1, ["pad", "bass"], ["PU"])]
       + groove("Final full groove", "A", FULL, ["B", ["B", "ride"]], ["F1v", "F4v"])
       + groove("Outro development", "A", ["pad", "bass", "comp"], ["A2"], ["F7v"])
       + groove("Outro development: harmony out", "A", ["bass"], ["A"], ["F6v"])
       + [blk("DJ outro", "A", 4, [], ["A2", "ride", "kr"]), blk("DJ outro: last bars", "A", 4, [], ["A", "hats", "kr"])])
FILL_BARS = [1 + sum(x["bars"] for x in ARR[:i]) for i, x in enumerate(ARR) if any(d in F for d in x["drums"])]
SECTIONS = [(1, 8, "Pad intro A"), (9, 16, "Pad intro B"), (17, 24, "Percussion introduction"), (25, 40, "First full break"),
            (41, 56, "Main groove A"), (57, 72, "Main groove B"), (73, 88, "Atmospheric breakdown"), (89, 96, "Break reintroduction"),
            (97, 120, "Main drop / groove return"), (121, 136, "Breakbeat variation"), (137, 152, "Second atmospheric passage"),
            (153, 168, "Final full groove"), (169, 184, "Outro development"), (185, 192, "DJ outro")]
SONG = ROOT / "songs" / "jungle174" / "jungle174-1589336164.am.json"

SPEC = {
    "title": "Haze Theory", "song": SONG, "genre": "atmospheric-jungle-95", "rebuild": "bountiful/jungle174.py",
    "composer": LT.B.COMPOSER_CREDIT, "artist": LT.B.ARTIST, "album": "", "year": 2026,
    "blurb": ("A 1992-95 atmospheric jungle track at 174 bpm built to a brief: sixteen bars of pads alone, then a chopped break performed from "
              "the brief's blueprint (kick 1/7/12, snare 5/13, ghosts, hats) on an acoustic kit, sampled, sped up and cut into Breaks A, B "
              "and C (32nd pickups, snare doubles, gaps, pitched slices, extra ghosts and kicks); a warm rolling sub following A minor "
              "Am9 - Fmaj7 - Em7 - Amaj7 - Dm9 at half speed; evolving sweep pads, dusty Rhodes chords and phrases, a distant vibraphone motif and voice."),
    "overrides": {"bpm": BPM, "swing": 0.5, "drums": "grid", "grid": PROGRAMS, "arrangement": ARR, "drum_cycle_per_block": True, "loop_continuous": True,
                  "harmony": {"rhythm": 1, "dominant": "modal", "tonic_major": "7sus4", "colors": {"m": "m9", "": "maj7", "m7": "m9", "7": "7sus4", "maj7": "maj7", "6": "6"}},
                  "melody": {"modal": True, "register": [64, 84], "max_leap": 7, "max_notes_per_bar": 3, "articulation": "legato", "humanize_ms": 7, "velocity": [0.5, 0.82]},
                  "bass": {"style": "pattern", "register": [28, 45],
                           "pattern": [[0, "R", 0.7, 1.0], [3, "R", 0.25, 0.8], [8, "5", 0.45, 0.85], [10, "O", 0.2, 0.75], [13, "7", 0.2, 0.7], [14, "R", 0.45, 0.85]]},
                  "bass2": {"style": "pattern", "register": [28, 45], "pattern": [[0, "R", 2.8, 0.9], [12, "O", 0.9, 0.75]]},
                  "comp": {"steps": [0, 10], "low": 55, "high": 74, "top": 71, "notes": 4, "gate": 1.8, "strum_ms": 16, "humanize_ms": 8, "vel": 0.55, "accent": 0.62},
                  "vox": {"steps": [0], "low": 62, "high": 79, "top": 74, "notes": 2, "gate": 3.8, "vel": 0.5, "accent": 0.5},
                  "pad": {"low": 50, "high": 79, "top": 74, "notes": 5, "vel": 0.5}},
    "kit_def": kit(),
    "layers": [("bass", "bass_mid")],
    "sends": {"slap": {"type": "delay", "time_beats": 0.25, "feedback": 0.25, "taps": 3, "tone": 3500},
              "plate": {"type": "reverb", "seconds": 3.2, "predelay": 0.03, "damp": 0.5}},
    "voices": {
        "pad": ({"zyn": "Strings/0018-Sweep Pad 2.xiz"}, "Sweep Pad 2 (ZynAddSubFX - Strings), evolving pad",
                dict(hp=150, width=1.0, eq=[["highshelf", 6000, 2.0]], sends={"plate": 0.45}, gain_db=-8.0)),
        "vox": ({"zyn": "Fantasy/0008-Space Voice1.xiz"}, "Space Voice1 (ZynAddSubFX - Fantasy), distant voice",
                dict(hp=300, lp=6000, width=0.9, sends={"plate": 0.6}, gain_db=-14.0)),
        "lead_hi": ({"zyn": "Collection/0002-Vibraphone.xiz"}, "Vibraphone (ZynAddSubFX - Collection), the high motif",
                    dict(hp=400, sends={"echo": 0.45, "plate": 0.5}, gain_db=-12.0)),
        "lead": ({"zyn": "Rhodes/0013-Ice Rhodes2.xiz"}, "Ice Rhodes2 (ZynAddSubFX - Rhodes), phrases",
                 dict(hp=200, crush={"bits": 12, "rate": 26040, "mix": 0.3}, sends={"echo": 0.3, "plate": 0.35}, gain_db=-4.0)),
        "comp": ({"zyn": "Rhodes/0003-DX Rhodes 3.xiz"}, "DX Rhodes 3 (ZynAddSubFX - Rhodes), jazzy chords",
                 dict(hp=150, crush={"bits": 12, "rate": 26040, "mix": 0.35}, width=1.0, sends={"plate": 0.3, "echo": 0.1}, gain_db=-8.0)),
        "bass": ({"zyn": "Bass/0003-Bass 3 _analog_.xiz"}, "Bass 3 analog (ZynAddSubFX - Bass), the sub",
                 dict(hp=25, lp=200, mono=True, duck={"depth": 0.3, "release": 0.09}, gain_db=-4.0)),
        "bass_mid": ({"zyn": "Bass/0001-Bass 1.xiz"}, "Bass 1 (ZynAddSubFX - Bass), upper-bass texture",
                     dict(hp=180, lp=1400, mono=True, duck={"depth": 0.25, "release": 0.09}, gain_db=-16.0)),
        "bass2": ({"zyn": "Bass/0003-Bass 3 _analog_.xiz"}, "Bass 3 analog (ZynAddSubFX - Bass), long sub notes",
                  dict(hp=25, lp=200, mono=True, duck={"depth": 0.25, "release": 0.1}, gain_db=-4.0)),
    },
    "targets": {"bass": -3.0, "bass_mid": -15.0, "pad": -11.0, "comp": -13.0, "lead": -10.0, "vox": -19.0},
    "level_ref": "break",
    "test_bars": (97, 104),
    "automation": [{"type": "lowpass", "tracks": ["pad"], "points": [[1, 800], [9, 1500], [17, 6500]]},
                   {"type": "lowpass", "tracks": ["break", "breakfx"], "points": [[17, 600], [21, 1100], [25, 18000]]},
                   {"type": "lowpass", "tracks": ["pad"], "points": [[73, 2200], [81, 3500], [89, 7000]]},
                   {"type": "lowpass", "tracks": ["break", "breakfx", "kick"], "points": [[89, 450], [93, 1400], [97, 18000]]},
                   {"type": "lowpass", "tracks": ["pad"], "points": [[137, 2500], [145, 4500], [153, 7000]]}],
    "mmp_drums": False, "kick_gain": None, "drum_stems": {},
}


def validate():
    """Checks against the brief, from the MIDI and the rendered audio."""
    import pyloudnorm as pyln
    sys.path.insert(0, str(LT.B.ENGINE / "studio"))
    from render_midi import read_midi
    track = ROOT / "tracks" / "haze-theory"
    notes, bpm, _ = read_midi(track / "haze-theory.mid")
    beat = 60 / bpm
    bar_of = lambda t: int((t + 0.01) / beat // 4) + 1
    res = []
    total_bars = max(bar_of(n["start"]) for n in notes)
    res.append(("192 bars at 174 bpm", total_bars == 192 and abs(bpm - 174) < 0.01, f"{total_bars} bars, {bpm:.0f} bpm, {192 * 4 * beat:.1f} s"))
    drums = [n for n in notes if n["track"] == "drums"]
    res.append(("bars 1-16: no drums at all", not any(bar_of(n["start"]) <= 16 for n in drums), ""))
    inv = {v: k for k, v in NOTES.items()}
    per_bar: dict[int, list] = {}
    for n in drums:
        per_bar.setdefault(bar_of(n["start"]), []).append((round((n["start"] / beat) % 4 * 4, 2), inv.get(n["pitch"], n["pitch"])))
    sigs = {b: tuple(sorted(v)) for b, v in per_bar.items()}
    distinct = len(set(sigs.values()))
    res.append(("drum bars are varied (distinct bar patterns)", distinct >= 15, f"{distinct} distinct patterns over {len(sigs)} drum bars"))
    fills = [sigs.get(b) for b in FILL_BARS]
    res.append(("every fill bar is its own edit", len(set(fills)) == len(fills),
                f"{len(set(fills))} distinct fills over {len(fills)} fill bars (bars {', '.join(map(str, FILL_BARS))})"))
    blocks = [tuple(sigs.get(b) for b in range(s, s + 7)) for s in range(25, 185, 8) if all(b in sigs for b in range(s, s + 7))]
    res.append(("8-bar groove blocks are not copies of each other", len(set(blocks)) >= len(blocks) // 2,
                f"{len(set(blocks))} distinct of {len(blocks)}"))
    res.append(("bar 151 subtracts the drums before the final return", 151 not in per_bar and 152 in per_bar, ""))
    harm_pcs = {n["pitch"] % 12 for n in notes if n["track"] in ("pad", "comp", "bass", "bass2", "vox")}
    res.append(("harmony stays in A minor (no bright C# from Amaj7)", 1 not in harm_pcs, f"pitch classes {sorted(harm_pcs)}"))
    names = [x[1] for v in per_bar.values() for x in v]
    for label, test in (("32nd pickups", lambda s: s.startswith("t")), ("pitched slices", lambda s: s in PITCHED),
                        ("extra ghost one-shots", lambda s: s == "gh1"), ("extra kicks", lambda s: s == "kick1"),
                        ("kick reinforcement", lambda s: s == "kreinf"), ("snare layer", lambda s: s == "snlay"), ("hats-only take", lambda s: s.startswith("h"))):
        c = sum(1 for s in names if test(s))
        res.append((f"break uses {label}", c > 0, f"{c} hits"))
    gaps = sum(1 for b, v in per_bar.items() if len({s for s, _ in v if isinstance(s, float) and s == int(s)}) < 16 and any(x[1].startswith("s") for x in v)
               and {10.0} - {s for s, _ in v})
    res.append(("transition breaks leave gaps", gaps > 0, f"{gaps} bars with a removed slice"))
    # bass follows the harmony: each bass note's pitch class is a tone of the chord sounding on the pad/comp at that moment
    harm = [n for n in notes if n["track"] in ("pad", "comp")]
    hit = tot = 0
    for n in (n for n in notes if n["track"] in ("bass", "bass2")):
        pcs = {h["pitch"] % 12 for h in harm if h["start"] <= n["start"] + 0.01 < h["end"]}
        if pcs:
            tot += 1
            hit += (n["pitch"] % 12) in pcs
    res.append(("bass follows the harmony (bass notes are chord tones)", tot and hit / tot >= 0.9, f"{hit}/{tot} bass notes"))
    bass_bars = {}
    for n in notes:
        if n["track"] == "bass":
            bass_bars.setdefault(bar_of(n["start"]), set()).add(n["pitch"])
    octs = sum(1 for v in bass_bars.values() if max(v) - min(v) >= 12)
    res.append(("bass moves by octaves / passing tones", octs > 0, f"{octs} bars with an octave move"))
    # audio: sections
    sc = json.loads((track / "exports" / "render_info.json").read_text())
    stems = {p.stem: sf.read(str(p))[0].mean(1) / sc["stem_scale"] for p in (track / "stems").glob("*.wav")}
    master, _ = sf.read(str(track / "exports" / "haze-theory.wav"))
    meter = pyln.Meter(SR)

    def lvl(x):
        k = len(x) // 2048
        r = np.sqrt((x[:k * 2048].reshape(k, 2048) ** 2).mean(1))
        return 20 * np.log10(np.sqrt((r[r > r.max() * 0.03] ** 2).mean()) + 1e-12) if r.max() > 1e-6 else -120

    rows = []
    for a, b, name in SECTIONS:
        i0, i1 = int(((a - 1) * 4 + 1) * beat * SR), int(b * 4 * beat * SR)
        rows.append((a, b, name, round(meter.integrated_loudness(master[i0:i1]), 1), {s: round(lvl(x[i0:i1]), 0) for s, x in stems.items()}))
    pads_only = rows[0][4]
    res.append(("bars 1-8: pads alone", pads_only.get("pad", -120) > -40 and all(v < -60 for s, v in pads_only.items() if s not in ("pad",)), ""))
    res.append(("bars 9-16: a second texture and the high motif join", rows[1][4].get("vox", -120) > -60 and rows[1][4].get("lead_hi", -120) > -60, ""))
    res.append(("the break is silent until bar 17", rows[0][4].get("break", -120) < -60 and rows[1][4].get("break", -120) < -60, ""))
    loud = {name: l for a, b, name, l, _ in rows}
    contrast = loud["Main drop / groove return"] - loud["Atmospheric breakdown"]
    res.append(("dynamic contrast between breakdown and groove", contrast >= 2.5, f"{contrast:.1f} LU"))
    a_ = sc["analysis"]
    res.append(("master: no clipping, true peak below -0.5 dBTP", a_["clipped_samples"] == 0 and a_["true_peak_dbtp_approx"] < -0.5,
                f"{a_['integrated_lufs']} LUFS, TP {a_['true_peak_dbtp_approx']}"))
    res.append(("low end centred (correlation below 120 Hz)", a_["correlation_below_120hz"] > 0.95, f"{a_['correlation_below_120hz']}"))
    lines = ["# Validation: Haze Theory", "", f"**{sum(r[1] for r in res)}/{len(res)} checks pass**", "", "| check | result | detail |", "|---|---|---|"]
    lines += [f"| {n} | {'ok' if ok else '**FAIL**'} | {d} |" for n, ok, d in res]
    stems_order = [s for s in ("pad", "vox", "lead_hi", "lead", "comp", "bass", "bass2", "bass_mid", "break", "breakfx", "kick", "snlay") if s in stems]
    lines += ["", "| bars | section | LUFS | " + " | ".join(stems_order) + " |", "|---|---|---|" + "---|" * len(stems_order)]
    lines += [f"| {a}-{b} | {name} | {l} | " + " | ".join("–" if v.get(s, -120) < -60 else f"{v[s]:.0f}" for s in stems_order) + " |" for a, b, name, l, v in rows]
    lines += ["", f"Master: {a_['integrated_lufs']} LUFS, true peak {a_['true_peak_dbtp_approx']} dBTP, stereo correlation {a_['correlation_full']}, "
              f"spectrum " + ", ".join(f"{k} {v:.1f}" for k, v in a_["spectrum_share_db"].items())]
    (track / "validation.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    if "--validate" in sys.argv:
        validate()
    else:
        build_break()
        LT.make(SPEC, log=lambda m: print(m, flush=True))
        validate()
