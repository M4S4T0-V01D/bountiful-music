"""Night Signal: a second 1992-95 atmospheric jungle track on Haze Theory's two breaks and a third, the cowbell break.

The break pipeline is Haze Theory's (bountiful/jungle174.py): breaks/break.mp3 (the Amen) and breaks/break2.wav sped up to
138 bpm on a 12-bit sampler and re-laid on the grid as continuous takes, every slice with a 5 ms crossfade lead and
choking the one before. They share its sample folder, kit and layer programs. What is new: G minor (the song transposed
down two semitones), another skeleton's chords, the cowbell break (breaks/break3.wav, slices c00..c63) opening (after 16 bars of strings and choir) and closing the track and layered under break 2,
break 2 leading and the Amen arriving later, a half-time passage, its own
break edits and fill library (the middle reintroduction is a bar-by-bar edit, program R), a bass cycle, voices and mix:
a chorused-flute lead sung behind the beat over syncopated Rhodes comping.

    python -I bountiful/night_signal.py              # sample the breaks (if needed), compose, render, master, validate
    python -I bountiful/night_signal.py --validate   # the checks only, on the last render
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

os.environ.setdefault("BOUNTIFUL_BREAK_BPM", "138")   # slower than Haze Theory: the jazzstep pocket, the breaks pitched up less
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jungle174 as J   # noqa: E402  (the break pipeline, the kit and the layer programs)

LT, PR, ROOT, BPM, SR, NOTES, PITCHED, sound_of = J.LT, J.PR, J.ROOT, J.BPM, J.SR, J.NOTES, J.PITCHED, J.sound_of
base, swap, zb, head, vary, blk, groove = J.base, J.swap, J.zb, J.head, J.vary, J.blk, J.groove
TITLE, SLUG = "Night Signal", "night-signal"
TRANSPOSE = -2                                     # A minor skeleton -> G minor
KEY_PCS = {7, 9, 10, 0, 2, 3, 5}                   # G natural minor


# ---------------------------------------------------------------- break edits (Amen: s.., break 2: z..)
# N / N2: the main Amen edits, a moved kick, a doubled kick, pitched slices and a re-cut last beat
N = {"a": base(0) + [[7, 0.25, "gh1", 4]],
     "b": swap(base(1), 6, [6, 0.8, "s02"]) + [[13, 0.3, "gh1", -3]],
     "c": swap(swap(base(2), 3, [3, 0.85, "s16"]), 11, [11, 0.6, "s07d"]),
     "d": head(3, 12) + [[12, 1.0, "s12"], [13, 0.5, "s13"], [14, 0.85, "s04"], [15, 0.7, "t04"], [15.5, 0.85, "t12"]]}
N2 = {"a": swap(base(0), 10, [10, 0.9, "s32"]) + [[5, 0.22, "gh1", 3]],
      "b": base(1) + [[9, 0.65, "kick1"]],
      "c": swap(base(2), 14, [14, 0.6, "s12d"]),
      "d": swap(swap(base(3), 6, [6, 0.7, "s09u"]), 7, [7, 0.5, "s07"]) + [[15.5, 0.6, "t12"]]}
B2 = {"a": [e for e in base(0) if e[0] not in (6, 7)] + [[6, 0.9, "s00"], [7, 0.7, "s01"], [11, 0.28, "gh1", -4]],
      "b": swap(base(1), 15, [15, 0.8, "s04u"]),
      "c": base(2) + [[3, 0.3, "gh1", 4], [9.5, 0.4, "t04"]],
      "d": swap(swap(base(3), 12, [12, 0.95, "s12"]), 13, [13, 0.7, "s12d"]) + [[14.5, 0.8, "t12"]]}
# T3: break 2's own edit (a kick slice on 10, a snare on 14, a re-cut half bar, a pitched pickup)
T3 = {"a": swap(zb(0), 10, [10, 0.8, "z16"]) + [[7, 0.25, "zs1", 3]],
      "b": swap(zb(1), 14, [14, 0.8, "z04"]),
      "c": [e for e in zb(2) if not 8 <= e[0] < 12] + [[8, 1.0, "z00"], [9, 0.9, "z01"], [10, 1.0, "z02"], [11, 0.8, "z03"]],
      "d": swap(zb(3), 15, [15, 0.7, "z04u"]) + [[15.5, 0.8, "zt04"]]}

# break 3, the cowbell break: W the straight take, W2 its own edit, Wq a quiet layer under break 2, FC1 the hand-over to break 2
cb = lambda b, steps=range(16), vel=1.0: [[i, vel, f"c{16 * b + i:02d}"] for i in steps]
W = {k: cb(i) for i, k in enumerate("abcd")}
W2 = {"a": cb(0),
      "b": [e for e in cb(1) if not 8 <= e[0] < 12] + [[8 + i, 0.95, f"c{16 + i:02d}"] for i in range(4)],   # beat 3 re-cut from beat 1
      "c": swap(cb(2), 14, [14, 0.85, "c04"]),
      "d": cb(3, range(12)) + [[12, 1.0, "c12"], [13, 0.7, "c12"], [14, 0.85, "c04"], [15, 0.9, "z04u"], [15.5, 1.0, "zt12"]]}
Wq = {k: cb(i, vel=0.45) for i, k in enumerate("abcd")}
FC1 = cb(3, range(12)) + [[12, 0.7, "zt04"], [13, 0.6, "zt12"], [14, 0.85, "zt04"], [14.5, 0.9, "zt12"], [15, 0.95, "z04u"], [15.5, 1.0, "zt12"]]

# R: the reintroduction (the middle of the track), one edit per bar, building from bare hits to a snare climb into FZ5
R = {"a": [[0, 1.0, "z00"], [4, 1.0, "z04"], [10, 0.8, "z16"], [12, 1.0, "z12"]],                    # bare hits, the tails ring
     "b": [e for e in zb(0) if e[0] < 8] + [[8, 1.0, "z00"], [10, 0.9, "z02"], [12, 1.0, "z12"], [14, 0.8, "z14"], [15, 0.8, "z15"]],
     "c": [e for e in zb(1) if e[0] < 12] + [[12, 1.0, "z04"], [13, 0.6, "zt04"], [13.5, 0.7, "zt04"], [14, 0.9, "z12"],
                                             [15, 0.8, "zt12"], [15.5, 0.9, "zt12"]],                 # a 32nd stutter on beat 4
     "d": swap(swap(swap(zb(2), 6, [6, 0.9, "z00"]), 7, [7, 0.7, "z01"]), 10, [10, 0.85, "z16"]),     # kicks re-cut, the "uh huh" kept
     "e": [e for e in zb(0) if e[0] < 8] + [[8 + i, 0.95, f"z{i:02d}"] for i in range(8)],            # the half bar played twice
     "f": zb(2),                                                                                       # the take straight: let it breathe
     "g": [e for e in zb(3) if e[0] < 8] + [[8 + i, 0.5 + 0.06 * i, "z04" if i % 2 == 0 else "z12"] for i in range(8)]}   # snare climb


# H: half time, the bar's kick beat, the hats-only take where the snare was, the snare beat moved to beat 3
def half(b, extra=()):
    return ([[i, (1.0, 0.8, 0.9, 0.8)[i], f"s{16 * b + i:02d}"] for i in range(4)] + [[4 + i, 0.6, f"h{4 + i:02d}"] for i in range(4)]
            + [[8 + i, 1.0 if i == 0 else 0.85, f"s{16 * b + 4 + i:02d}"] for i in range(4)] + [[12 + i, 0.6, f"h{12 + i:02d}"] for i in range(4)]
            + list(extra))


H = {"a": half(0), "b": half(1, [[14, 0.6, "kick1"]]), "c": half(2), "d": half(3, [[15, 0.6, "t12"], [15.5, 0.75, "t12"]])}
H2 = {"a": half(0, [[6, 0.22, "gh1", 4]]), "b": half(1, [[14, 0.6, "kick1"], [11, 0.25, "gh1", -3]]),
      "c": swap(half(2), 13, [13, 0.5, "s09u"]), "d": half(3, [[14, 0.5, "t04"], [15, 0.7, "t12"], [15.5, 0.85, "s04u"]])}

# the fill library: every fill bar is its own edit
F = {"G1": head(0, 8) + [[8, 0.9, "s32"], [9, 0.6, "s33"], [10, 0.8, "s12d"], [11, 0.5, "t04"], [12, 1.0, "s12"], [13, 0.7, "s13"],
                         [14, 0.85, "s12u"], [15, 0.9, "s04u"]],                                      # kick re-cut, a pitched answer
     "G2": head(1, 12) + [[12 + i / 2, 0.45 + 0.07 * i, "t12" if i % 2 else "t04"] for i in range(8)],   # a 32nd roll on the last beat
     "G3": head(2, 4) + [[4, 1.0, "s04"], [6, 0.7, "s04"], [8, 0.9, "s00"], [10, 0.75, "s12d"], [12, 1.0, "s12"], [14, 0.8, "s12d"],
                         [15, 0.9, "s04u"]],                                                          # sparse: air between the hits
     "G4": head(3, 8) + [[8 + i, 0.5 + 0.06 * i, ("s04", "s12d", "s04u", "s12")[i % 4]] for i in range(8)],   # a snare climb
     "G5": head(0, 6) + [[13, 0.6, "t12"], [14, 0.75, "t04"], [15, 0.95, "s04u"]],                     # drop-out, then a pickup
     "G6": head(1, 8) + [[8, 0.9, "kick1"], [9, 0.25, "gh1", 3], [10, 0.8, "kick1"], [11, 0.3, "gh1", -4], [12, 1.0, "s12"],
                         [14, 0.7, "kick1"], [15, 0.9, "s04u"]],                                      # kicks and ghosts
     "FZ3": [e for e in zb(0) if e[0] < 8] + [[8, 0.9, "zs1"], [10, 0.8, "zt04"], [11, 0.6, "zt12"], [12, 1.0, "z04"], [13, 0.7, "zt12"],
                                              [14, 0.85, "z04u"], [15, 0.9, "z04u"], [15.5, 1.0, "zt12"]],
     "FZ4": [e for e in zb(3) if e[0] < 12] + [[12, 1.0, "s12"], [13, 0.8, "s13"], [14, 1.0, "s04u"], [15, 0.9, "s15"]],  # break 2 hands over
     "FZ5": [e for e in zb(3) if e[0] < 4] + [[4 + i / 2, 0.3 + 0.03 * i, "zt12" if i % 2 else "zt04"] for i in range(22)]
            + [[15, 0.95, "z04u"], [15.5, 1.0, "s04u"]],                                              # the roll-in to the drop
     "FZ6": [e for e in zb(1) if e[0] < 8] + [[8, 0.9, "z16"], [9, 0.5, "zs1", 4], [10, 0.85, "z16"], [12, 1.0, "z04"], [14, 0.8, "zt12"],
                                              [14.5, 0.9, "zt12"], [15, 1.0, "s04u"]],
     "FZ7": [e for e in zb(2) if e[0] < 8] + [[8 + i / 2, 0.35 + 0.05 * i, "zt04" if i % 2 else "zt12"] for i in range(14)]
            + [[15, 1.0, "z04u"], [15.5, 1.0, "s04u"]],
     "HF": half(1)[:8] + [[8, 1.0, "s04"], [10, 0.7, "s12d"], [11, 0.6, "t12"], [12, 0.9, "s04"], [13, 0.6, "t04"], [14, 0.8, "s04u"], [15, 0.95, "s12u"]],
     "FC1": FC1,
     "PU2": [[12, 0.7, "zs1"], [13, 0.5, "zt12"], [14, 0.8, "zt04"], [14.5, 0.85, "zt12"], [15, 0.9, "z04u"], [15.5, 1.0, "s04u"]]}
F |= {k + "v": vary(F[k]) for k in ("G1", "G2", "G3", "G6")}

# bars 9-12 keep the first render's sound: a MIDI note limit turned every break-2 slice from z08 on into z08, a stutter on the
# first eight slices; as_was plays that on purpose, and from bar 13 the real take (with its "yeah", "uh huh") comes through
as_was = lambda p: {k: [[e[0], e[1], "z08" if NOTES.get(e[2], 0) >= 127 else e[2], *e[3:]] for e in v] for k, v in p.items()}
LAYERS = {k: J.PROGRAMS[k] for k in ("A", "A2", "T", "T2", "TL", "hats", "hatsq", "ride", "rz", "kr", "kr2", "sl", "sl2")}
PROGRAMS = {**LAYERS, "N": N, "N2": N2, "B2": B2, "T3": T3, "H": H, "H2": H2, "W": W, "W2": W2, "Wq": Wq, "R": R, **F, "T0": as_was(J.PROGRAMS["T"]), "rz0": as_was(J.PROGRAMS["rz"]),
            "hl": [[0, 0.9, "kreinf"], [8, 0.55, "snlay"]]}       # the half-time layers: a kick on 1, a snare under beat 3


# ---------------------------------------------------------------- arrangement (184 bars)
INTRO = 16      # bars of atmosphere before the first break (16 bars at 138 bpm: 27.8 s); every bar number below is shifted by it
FULL = ["pad", "bass", "lead", "comp", "vox"]
Z2 = ("kr2", "sl2", "rz")
HT = ["pad", "vox", "lead_hi", "bass2"]
ARR = ([blk("Atmosphere: pads", "A", 8, ["pad"], vel={"pad": 0.7}),                    # strings alone, under a closed filter
        blk("Atmosphere: choir and bells", "A", INTRO - 8, ["pad", "vox", "lead_hi"], vel={"pad": 0.8, "lead_hi": 0.7}),
        blk("Break 3: the cowbells", "A", 7, ["pad", "vox"], ["W"]), blk("Break 3: hand-over FC1", "A", 1, ["pad", "vox"], ["FC1"]),
        blk("Break 2 under the filter", "A", 4, ["pad", "vox", "lead_hi"], ["T0", "rz0"]),
        blk("Break 2: the real take", "A", 4, ["pad", "vox", "lead_hi"], ["T", "rz"])]
       + groove("Break 2 opens", "A", ["pad", "bass2"], [["T", "Wq"]], ["FZ3"], extra=Z2, restart=True)
       + groove("The Amen arrives", "V", ["pad", "bass", "comp"], [["T2", "hatsq", *Z2], ["A", "TL", "kr", "sl", "ride"]], ["FZ4", "G1"], extra=())
       + groove("Main groove", "A", ["pad", "bass", "lead", "comp"], ["N", "N2"], ["G2", "G3"], restart=True)
       + [blk("Breakdown", "B", 8, ["pad", "vox", "lead", "comp"], vel={"pad": 0.85, "lead": 0.8, "comp": 0.8}),
          blk("Breakdown: hats", "B", 8, ["pad", "vox", "lead_hi", "comp"], ["hatsq"], vel={"pad": 0.85, "comp": 0.8})]
       + [blk("Reintroduction", "A", 7, ["pad", "bass2"], ["R", "rz"]), blk("Reintroduction: roll-in FZ5", "A", 1, ["pad", "bass2"], ["FZ5"])]
       + groove("Drop", "A", FULL, [["N", "TL"]], ["G4"], restart=True)
       + groove("Drop: break 2", "A", FULL, [["T3", "Wq"]], ["FZ6"], extra=Z2)
       + groove("Drop: hats", "A", FULL, [["N2", "hats"]], ["G5"])
       # half time: the snare on beat 3, long sub notes, the bright verse chords; then a bar of subtraction and a pickup
       + [blk("Half-time passage", "V", 7, HT, ["H", "hl", "ride"], loop_restart=True), blk("Half-time passage: fill HF", "V", 1, HT, ["HF", "ride"]),
          blk("Half-time passage: lift", "V", 6, HT + ["comp"], ["H2", "hl", "ride"], vel={"comp": 0.8}),
          blk("Half-time passage: subtraction", "V", 1, ["pad", "vox"]),
          blk("Half-time passage: pickup", "V", 1, ["pad", "bass"], ["PU2"])]
       + groove("Final groove", "A", FULL, [["B2", "TL"]], ["G1v"], restart=True)
       + groove("Final groove: break 3", "A", FULL, [["W2", "rz"]], ["FZ7"], extra=("kr2", "sl2"))
       + groove("Final groove: last pass", "A", FULL, [["N", "hats"]], ["G3v"])
       + groove("Outro", "A", ["pad", "bass", "comp"], ["N2"], ["G6v"])
       + groove("Outro: harmony out", "A", ["bass"], ["A2"], ["G2v"])
       + [blk("DJ outro", "A", 4, [], ["N", "ride", "kr"]), blk("DJ outro: break 3", "A", 4, [], ["W", "kr2"])])
for b_ in ARR:
    b_["transpose"] = TRANSPOSE
TOTAL = sum(x["bars"] for x in ARR)
FILL_BARS = [1 + sum(x["bars"] for x in ARR[:i]) for i, x in enumerate(ARR) if any(d in F for d in x["drums"])]
SUBTRACT = 1 + sum(x["bars"] for x in ARR[:next(i for i, x in enumerate(ARR) if x["name"].endswith("subtraction"))])
SECTIONS = [(1, INTRO, "Atmosphere")] + [(a + INTRO, b + INTRO, name) for a, b, name in (
            (1, 8, "Break 3 intro"), (9, 12, "Break 2 under the filter"), (13, 16, "Break 2: the real take"), (17, 24, "Break 2 opens"), (25, 40, "The Amen arrives"),
            (41, 56, "Main groove"), (57, 72, "Breakdown"), (73, 80, "Reintroduction"), (81, 104, "Drop"),
            (105, 120, "Half-time passage"), (121, 144, "Final groove"), (145, 160, "Outro"), (161, 168, "DJ outro"))]
SONG = ROOT / "songs" / "jungle174" / "jungle174-1653034831.am.json"

# the same two-layer sub as Haze Theory, the analog layer a little more resonant and open
SUB = copy.deepcopy(J.SUB)
SUB["layers"][1]["preset"] |= {"cutoff": 160, "resonance": 0.45, "env_amount": 1400, "filter_decay": 0.15}

SPEC = {
    "title": TITLE, "song": SONG, "genre": "atmospheric-jungle-95", "rebuild": "bountiful/night_signal.py",
    "composer": LT.B.COMPOSER_CREDIT, "artist": LT.B.ARTIST, "album": "", "year": 2026,
    "blurb": ("A 1992-95 atmospheric jungle track at 138 bpm in G minor on Haze Theory's two real breaks and a cowbell break, opening on half a minute of strings and choir, sampled on a 12-bit "
              "sampler and re-laid on the grid as continuous takes: the cowbell break opening and closing it, then break 2 alone under a closing filter first, the Amen arriving over it, "
              "its own edits and fills, a half-time passage with the snare on three; a rolling two-layer sub, choir and string pads, "
              "a chorused-flute lead sung behind the beat over syncopated Rhodes, a bell motif, printed through tape."),
    "overrides": {"bpm": BPM, "swing": 0.5, "drums": "grid", "grid": PROGRAMS, "arrangement": ARR, "drum_cycle_per_block": True, "loop_continuous": True,
                  "master": {**LT.B.MASTER, "hp": 25, "mono_below": 120, "glue": {},
                             "tape": {"drive": 1.6, "bias": 0.07, "bump_db": 1.5, "hf_db": -1.0, "lp_hz": 17000, "hiss_db": -74, "wow_ms": 0.06},
                             "eq": [["peak", 180, 1.0, 0.7], ["peak", 400, -0.8, 1.0], ["peak", 1500, 1.0, 0.7], ["peak", 5000, -0.8, 1.0]],
                             "multiband": {"freqs": [150, 5000], "bands": [{"threshold_rel": -3, "ratio": 2.5, "attack": 0.03, "release": 0.15},
                                                                           {"threshold_rel": -3, "ratio": 1.6, "attack": 0.015, "release": 0.12},
                                                                           {"threshold_rel": -3, "ratio": 1.8, "attack": 0.005, "release": 0.08}]},
                             "bus_comp": {"threshold_rel": -3, "ratio": 2.0, "attack": 0.03, "release": 0.2, "sc_hp": 100},
                             "target_lufs": -9.6, "ceiling": -1.0, "clip": 1.5, "true_peak": -1.0},
                  "harmony": {"rhythm": 1, "dominant": "modal", "tonic_major": "7sus4", "colors": {"m": "m9", "": "maj7", "m7": "m9", "7": "7sus4", "maj7": "maj7", "6": "6"}},
                  "melody": {"modal": True, "register": [62, 84], "max_leap": 9, "max_notes_per_bar": 5, "articulation": "legato", "phrase_bars": 2,
                             "swing": 0.56, "push_ms": 12, "humanize_ms": 10, "velocity": [0.4, 0.95]},   # sung: laid back, swung, wide dynamics
                  # registers are before the transpose (-2): the sub sounds from D1 up
                  "bass": {"style": "pattern", "register": [30, 47],
                           "patterns": [[[0, "R", 0.45, 1.0], [3, "R", 0.2, 0.75], [6, "O", 0.45, 0.85], [10, "5", 0.45, 0.85], [14, "R", 0.45, 0.9]],
                                        [[0, "R", 1.2, 1.0], [6, "5", 0.25, 0.8], [8, "O", 0.5, 0.85], [11, "R", 0.7, 0.9]],
                                        [[0, "R", 0.7, 1.0], [4, "3", 0.45, 0.8], [8, "5", 0.7, 0.85], [12, "O", 0.25, 0.8], [13, "7", 0.25, 0.7], [14, "5", 0.5, 0.8]],
                                        [[0, "R", 2.0, 1.0], [10, "O", 0.25, 0.8], [11, "R", 0.25, 0.75], [12, "5", 0.5, 0.85], [14, "3", 0.25, 0.75], [15, "7", 0.25, 0.7]]]},   # walks up into the next bar
                  "bass2": {"style": "pattern", "register": [30, 47],
                            "patterns": [[[0, "R", 3.5, 0.9]], [[0, "R", 1.5, 0.9], [6, "5", 1.0, 0.75], [12, "O", 1.0, 0.8]]]},
                  "comp": {"steps": [0, 3, 7, 10, 14], "low": 55, "high": 74, "top": 71, "notes": 4, "gate": 0.9, "strum_ms": 20, "swing": 0.56, "push_ms": 10,
                           "humanize_ms": 10, "vel": 0.42, "accent": 0.64},                      # syncopated, behind the beat
                  "vox": {"steps": [0], "low": 60, "high": 77, "top": 72, "notes": 3, "gate": 3.8, "vel": 0.5, "accent": 0.5},
                  "pad": {"low": 50, "high": 79, "top": 74, "notes": 5, "vel": 0.5}},
    "kit_def": J.kit(),
    "layers": [("bass", "bass_mid")],
    "sends": {"slap": {"type": "delay", "time_beats": 0.375, "feedback": 0.3, "taps": 3, "tone": 3200},
              "plate": {"type": "reverb", "seconds": 3.6, "predelay": 0.03, "damp": 0.55}},
    "voices": {
        "pad": ({"zyn": "Strings/0014-Strings Pad5.xiz"}, "Strings Pad5 (ZynAddSubFX - Strings), slow string pad",
                dict(hp=150, width=0.6, eq=[["peak", 2500, 1.5, 0.8], ["highshelf", 3500, 4.0]], crush=J.SAMPLER(32000, 0.5),
                     sends={"plate": 0.45}, gain_db=-8.0)),
        "vox": ({"zyn": "ChoirAndVoice/0001-AHH Choir 1.xiz"}, "AHH Choir 1 (ZynAddSubFX - Choir and Voice), the choir",
                dict(hp=300, lp=9000, width=0.7, crush=J.SAMPLER(26040, 0.5), sends={"plate": 0.6}, gain_db=-14.0)),
        "lead_hi": ({"zyn": "Collection/0003-Soft Vibes.xiz"}, "Soft Vibes (ZynAddSubFX - Collection), the high motif",
                    dict(hp=400, width=0.8, crush=J.SAMPLER(26040, 0.4), sends={"slap": 0.45, "plate": 0.5}, gain_db=-12.0)),
        "lead": ({"zyn": "ReedAndWind/0068-Chorused Flute.xiz"}, "Chorused Flute (ZynAddSubFX - Reed and Wind), the soul lead",
                 dict(hp=250, width=0.6, crush=J.SAMPLER(26040, 0.35), sends={"slap": 0.4, "plate": 0.5}, gain_db=-6.0)),
        "comp": ({"zyn": "Rhodes/0067-RhodesPad1.xiz"}, "RhodesPad1 (ZynAddSubFX - Rhodes), chords",
                 dict(hp=150, crush={"bits": 12, "rate": 26040, "mix": 0.35}, width=0.85, sends={"plate": 0.3, "slap": 0.1}, gain_db=-8.0)),
        "bass_mid": ({"zyn": "Bass/0006-Analogue Bass.xiz"}, "Analogue Bass (ZynAddSubFX - Bass), upper-bass texture",
                     dict(hp=180, lp=1400, mono=True, duck={"depth": 0.25, "release": 0.09}, gain_db=-16.0)),
    },
    "extra_tracks": {"bass": dict(SUB, duck={"depth": 0.3, "release": 0.09}, gain_db=-14.0),
                     "bass2": dict(SUB, duck={"depth": 0.25, "release": 0.1}, gain_db=-11.5)},
    "targets": {"bass": -0.5, "bass_mid": -12.5, "pad": -11.0, "comp": -13.0, "lead": -10.0, "vox": -19.0},
    "level_ref": "break",
    "test_bars": (81 + INTRO, 88 + INTRO),
    # the atmosphere: the strings open slowly from a dark 400 Hz over the intro and keep opening under break 3
    "automation": [{"type": "lowpass", "tracks": ["pad"], "points": [[1, 400], [9, 650], [INTRO + 1, 900], [INTRO + 9, 2000], [INTRO + 17, 12000]]}]
                  + [{**a, "points": [[b + INTRO, v] for b, v in a["points"]]} for a in (
                   {"type": "lowpass", "tracks": ["break2", "ride"], "points": [[9, 350], [12, 700], [13, 18000]]},
                   {"type": "lowpass", "tracks": ["pad"], "points": [[57, 2000], [65, 3500], [73, 12000]]},
                   {"type": "lowpass", "tracks": ["break2", "ride"], "points": [[73, 450], [77, 1400], [81, 18000]]},
                   {"type": "lowpass", "tracks": ["pad"], "points": [[105, 2500], [113, 5000], [121, 12000]]})],
    "mmp_drums": False, "kick_gain": None, "drum_stems": {},
}


def validate():
    """Checks against the brief, from the MIDI and the rendered audio."""
    import pyloudnorm as pyln
    sys.path.insert(0, str(LT.B.ENGINE / "studio"))
    from render_midi import read_midi
    track = ROOT / "tracks" / SLUG
    notes, bpm, _ = read_midi(track / f"{SLUG}.mid")
    beat = 60 / bpm
    bar_of = lambda t: int((t + 0.01) / beat // 4) + 1
    res = []
    total_bars = max(bar_of(n["start"]) for n in notes)
    res.append((f"{TOTAL} bars at {BPM} bpm", total_bars == TOTAL and abs(bpm - BPM) < 0.01, f"{total_bars} bars, {bpm:.0f} bpm, {TOTAL * 4 * beat:.1f} s"))
    drums = [n for n in notes if n["track"] == "drums"]
    per_bar: dict[int, list] = {}
    for n in drums:
        per_bar.setdefault(bar_of(n["start"]), []).append((round((n["start"] / beat) % 4 * 4, 2), sound_of(n)))
    sigs = {b: tuple(sorted(v)) for b, v in per_bar.items()}
    res.append((f"bars 1-{INTRO}: the atmosphere, no drums", not any(b in per_bar for b in range(1, INTRO + 1)) and INTRO + 1 in per_bar, ""))
    intro = {n for b in range(INTRO + 1, INTRO + 8) for _, n in per_bar.get(b, [])}
    res.append((f"bars {INTRO + 1}-{INTRO + 7}: break 3 alone (the cowbell take)", len(intro) == 64 and all(str(n)[0] == "c" for n in intro), f"{len(intro)} slices"))
    w_bars = [b for i, x in enumerate(ARR) if {"W", "W2", "Wq"} & set(x["drums"])
              for b in range(1 + sum(y["bars"] for y in ARR[:i]), 1 + sum(y["bars"] for y in ARR[:i + 1])) if b > INTRO + 16]
    later = sum(1 for b in w_bars if any(str(n)[0] == "c" for _, n in per_bar.get(b, [])))
    res.append(("break 3 returns: under break 2, its own groove, the DJ outro", w_bars and later == len(w_bars), f"{later}/{len(w_bars)} bars after bar {INTRO + 16}"))
    lost = sum(1 for v in per_bar.values() for _, n in v if not isinstance(n, str))
    res.append(("every drum note names a kit sound (none clipped at MIDI's 127)", lost == 0, f"{lost} undecoded notes"))
    early = {n for b in range(INTRO + 9, INTRO + 13) for _, n in per_bar.get(b, []) if str(n).startswith("z")}
    res.append((f"bars {INTRO + 9}-{INTRO + 12}: the first render's break 2 (slices z00-z08 only)", early and early <= {f"z{i:02d}" for i in range(9)}, " ".join(sorted(early))))
    VOX = {"z14", "z15", "z42", "z43"}
    late = sorted(b for b in range(INTRO + 13, TOTAL + 1) if VOX & {n for _, n in per_bar.get(b, [])})
    res.append((f"from bar {INTRO + 13}: the real take, its vocal slices play", late[:1] == [INTRO + 13] and len(late) >= 20, f"{len(late)} bars with z14/z15/z42/z43, first {late[:1]}"))
    distinct = len(set(sigs.values()))
    res.append(("drum bars are varied (distinct bar patterns)", distinct >= 15, f"{distinct} distinct patterns over {len(sigs)} drum bars"))
    fills = [sigs.get(b) for b in FILL_BARS]
    res.append(("every fill bar is its own edit", len(set(fills)) == len(fills),
                f"{len(set(fills))} distinct fills over {len(fills)} fill bars (bars {', '.join(map(str, FILL_BARS))})"))
    mid = [sigs.get(b) for b in range(INTRO + 73, INTRO + 80)]
    res.append((f"the middle break (bars {INTRO + 73}-{INTRO + 79}) is edited bar by bar, not looped", all(mid) and len(set(mid)) == 7, f"{len(set(mid))} distinct of 7 bars"))
    blocks = [tuple(sigs.get(b) for b in range(s, s + 7)) for s in range(INTRO + 17, TOTAL - 7, 8) if all(b in sigs for b in range(s, s + 7))]
    res.append(("8-bar groove blocks are not copies of each other", len(set(blocks)) >= len(blocks) // 2, f"{len(set(blocks))} distinct of {len(blocks)}"))
    res.append((f"bar {SUBTRACT} subtracts the drums before the final return", SUBTRACT not in per_bar and SUBTRACT + 1 in per_bar, ""))
    harm = [n for n in notes if n["track"] in ("pad", "comp", "bass", "bass2", "vox", "lead", "lead_hi")]
    out_key = sum(1 for n in harm if n["pitch"] % 12 not in KEY_PCS)
    res.append(("harmony is in G minor (transposed skeleton)", out_key <= 0.02 * len(harm), f"{out_key}/{len(harm)} notes outside G natural minor"))
    names = [x[1] for v in per_bar.values() for x in v]
    for label, test in (("32nd pickups", lambda s: str(s).startswith(("t", "zt"))), ("pitched slices", lambda s: s in PITCHED),
                        ("extra ghost one-shots", lambda s: s in ("gh1", "zs1")), ("extra kicks", lambda s: s in ("kick1", "zk1")),
                        ("kick reinforcement", lambda s: s == "kreinf"), ("snare layer", lambda s: s == "snlay"), ("hats-only take", lambda s: str(s).startswith("h"))):
        c = sum(1 for s in names if test(s))
        res.append((f"break uses {label}", c > 0, f"{c} hits"))
    both = sum(1 for v in per_bar.values() if any(str(n)[0] == "s" for _, n in v) and any(str(n)[0] == "z" for _, n in v))
    only2 = sum(1 for v in per_bar.values() if any(str(n)[0] == "z" for _, n in v) and not any(str(n)[0] == "s" and str(n)[1:].isdigit() for _, n in v))
    res.append(("both breaks: layered, and break 2 alone", both > 0 and only2 > 0, f"{both} layered bars, {only2} bars of break 2 alone"))
    # half time: in the half-time bars the snare slices sit on step 8, not 4 / 12
    ht = [b for b in range(INTRO + 105, INTRO + 119) if b in per_bar]
    on8 = sum(1 for b in ht if any(s == 8.0 and str(n) in {f"s{16 * k + 4:02d}" for k in range(4)} for s, n in per_bar[b]))
    res.append(("half-time passage: the snare moves to beat 3", ht and on8 >= len(ht) - 1, f"{on8}/{len(ht)} bars"))
    chords = [n for n in notes if n["track"] in ("pad", "comp")]
    hit = tot = 0
    for n in (n for n in notes if n["track"] in ("bass", "bass2")):
        pcs = {h["pitch"] % 12 for h in chords if h["start"] <= n["start"] + 0.01 < h["end"]}
        if pcs:
            tot += 1
            hit += (n["pitch"] % 12) in pcs
    res.append(("bass follows the harmony (bass notes are chord tones)", tot and hit / tot >= 0.9, f"{hit}/{tot} bass notes"))
    bass_bars = {}
    for n in notes:
        if n["track"] == "bass":
            bass_bars.setdefault(bar_of(n["start"]), set()).add(n["pitch"])
    octs = sum(1 for v in bass_bars.values() if max(v) - min(v) >= 12)
    low = min(n["pitch"] for n in notes if n["track"] in ("bass", "bass2"))
    res.append(("bass moves by octaves, and stays above C1", octs > 0 and low >= 26, f"{octs} bars with an octave move, lowest note {low}"))
    # audio
    sc = json.loads((track / "exports" / "render_info.json").read_text())
    stems = {p.stem: sf.read(str(p))[0].mean(1) / sc["stem_scale"] for p in (track / "stems").glob("*.wav")}
    master, _ = sf.read(str(track / "exports" / f"{SLUG}.wav"))
    meter = pyln.Meter(SR)

    def lvl(x):
        k = len(x) // 2048
        r = np.sqrt((x[:k * 2048].reshape(k, 2048) ** 2).mean(1))
        return 20 * np.log10(np.sqrt((r[r > r.max() * 0.03] ** 2).mean()) + 1e-12) if r.max() > 1e-6 else -120

    rows = []
    for a, b, name in SECTIONS:
        i0, i1 = int(((a - 1) * 4 + 1) * beat * SR), int(b * 4 * beat * SR) - int(0.01 * SR)   # the next bar's 5 ms leads stay out
        rows.append((a, b, name, round(meter.integrated_loudness(master[i0:i1]), 1), {s: round(lvl(x[i0:i1]), 0) for s, x in stems.items()}))
    ra = rows[0][4]
    res.append((f"bars 1-{INTRO}: the atmosphere, pads and choir with no drums", ra.get("pad", -120) > -40 and ra.get("vox", -120) > -60
                and all(v < -60 for s, v in ra.items() if s not in ("pad", "vox", "lead_hi")), f"pad {ra.get('pad')}, vox {ra.get('vox')}"))
    r0, r1 = rows[1][4], {k: max(rows[2][4].get(k, -120), rows[3][4].get(k, -120)) for k in rows[2][4] | rows[3][4]}
    res.append((f"bars {INTRO + 1}-{INTRO + 8}: break 3 under the pads and choir", r0.get("pad", -120) > -40 and r0.get("break3", -120) > -40
                and r0.get("lead_hi", -120) < -45      # the intro's bells may ring over the downbeat
                and all(v < -60 for s, v in r0.items() if s not in ("pad", "vox", "lead_hi", "break3", "breakfx")), f"break3 {r0.get('break3')}"))
    res.append((f"bars {INTRO + 9}-{INTRO + 16}: break 2 under the filter, the bell motif", r1.get("break2", -120) > -60 and r1.get("lead_hi", -120) > -60
                and r1.get("break", -120) < -60, f"break2 {r1.get('break2')}, Amen {r1.get('break')}"))
    loud = {name: l for a, b, name, l, _ in rows}
    contrast = loud["Drop"] - loud["Breakdown"]
    res.append(("dynamic contrast between breakdown and drop", contrast >= 2.5, f"{contrast:.1f} LU"))
    a_ = sc["analysis"]
    res.append(("master: no clipping, true peak below -0.5 dBTP", a_["clipped_samples"] == 0 and a_["true_peak_dbtp_approx"] < -0.5,
                f"{a_['integrated_lufs']} LUFS, TP {a_['true_peak_dbtp_approx']}"))
    res.append(("low end centred (correlation below 120 Hz)", a_["correlation_below_120hz"] > 0.95, f"{a_['correlation_below_120hz']}"))
    lines = [f"# Validation: {TITLE}", "", f"**{sum(bool(r[1]) for r in res)}/{len(res)} checks pass**", "", "| check | result | detail |", "|---|---|---|"]
    lines += [f"| {n} | {'ok' if ok else '**FAIL**'} | {d} |" for n, ok, d in res]
    order = [s for s in ("pad", "vox", "lead_hi", "lead", "comp", "bass", "bass2", "bass_mid", "break", "breakfx", "break2", "break3", "ride", "kick", "snlay") if s in stems]
    lines += ["", "| bars | section | LUFS | " + " | ".join(order) + " |", "|---|---|---|" + "---|" * len(order)]
    lines += [f"| {a}-{b} | {name} | {l} | " + " | ".join("–" if v.get(s, -120) < -60 else f"{v[s]:.0f}" for s in order) + " |" for a, b, name, l, v in rows]
    lines += ["", f"Master: {a_['integrated_lufs']} LUFS, true peak {a_['true_peak_dbtp_approx']} dBTP, stereo correlation {a_['correlation_full']}, "
              f"spectrum " + ", ".join(f"{k} {v:.1f}" for k, v in a_["spectrum_share_db"].items())]
    (track / "validation.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    if "--validate" in sys.argv:
        validate()
    else:
        J.build_break()
        LT.make(SPEC, log=lambda m: print(m, flush=True))
        validate()
