"""Undertow: the second track of Littoral (after Tide), a 1992-95 soul jungle track at 145 bpm in D minor.

The break pipeline is Haze Theory's (bountiful/jungle174.py), with its kit and layer programs, but on its own set of three
breaks (the album keeps one break in common from track to track, never all three): the Amen (s.., shared with Tide but
edited its own way: long half-bar runs, Y/Y2/Yq, and its own fills, no bar copied from Tide), break7 (z.., breaks/break7.wav,
a four-bar rolling percussion break near 111 bpm) and break4 (c.., breaks/break4.wav, a hard two-bar funk break near 103 bpm).
They are sampled to 145 on the 12-bit sampler into their own folder (samples/breaks/undertow145), so Tide's samples stay as they are.
What is new: D minor on another skeleton (jungle162-196520246, F minor transposed: Dm F6 Gm6 F / Dm Gm7 C Bbmaj7), soul
voicings (ninths, elevenths, 6/9), a 32-bar opening (Rhodes alone, strings, a soul ooh over the sub, the guitar); the
percussion break rising out of a high-pass; the undertow, a two-step cut from the Amen pulled out from under the track before
the drop lands full on break4; a half-time passage cut from break4; a walking sub, a jazz guitar behind the beat, a soft organ;
a DJ outro of beat alone, pulled out again.

    python -I bountiful/undertow.py              # sample the breaks (if needed), compose, render, master, validate
    python -I bountiful/undertow.py --validate   # the checks only, on the last render
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

os.environ.setdefault("BOUNTIFUL_BREAK_BPM", "145")   # quicker than Tide: the undertow pulls
os.environ.setdefault("BOUNTIFUL_BREAK_CRUSH", "0.6")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jungle174 as J   # noqa: E402  (the break pipeline, the kit and the layer programs)
import night_signal as NS   # noqa: E402  (its Amen edits and fills; importing it builds nothing)

# this track's breaks: the z.. and c.. slots take break7 and break4, sampled into their own folder (kit() and
# build_real_break() read these module names when they run)
J.BREAK2_SRC = J.ROOT / "breaks" / "break7.wav"
J.BREAK3_SRC = J.ROOT / "breaks" / "break4.wav"
J.OUT = J.ROOT / "samples" / "breaks" / f"undertow{J.BPM}"

LT, ROOT, BPM, SR, NOTES, PITCHED, sound_of = J.LT, J.ROOT, J.BPM, J.SR, J.NOTES, J.PITCHED, J.sound_of
base, swap, zb, head, vary, blk, groove, cb = J.base, J.swap, J.zb, J.head, J.vary, J.blk, J.groove, NS.cb
TITLE, SLUG, ALBUM = "Undertow", "undertow", "Littoral"
TRANSPOSE = -3                                     # F minor skeleton -> D minor
KEY_PCS = {2, 4, 5, 7, 9, 10, 0}                   # D natural minor


# ---------------------------------------------------------------- edits
# The Amen is the break shared with Tide, so none of Tide's Amen edits or fills come back: here it plays in long runs,
# whole half bars of the take recombined (the first half of one bar, the second half of another), never chopped step by step.
def hb(b1, b2, vel=1.0, extra=()):
    return [[i, vel, f"s{16 * b1 + i:02d}"] for i in range(8)] + [[8 + i, vel, f"s{16 * b2 + 8 + i:02d}"] for i in range(8)] + list(extra)


Y = {"a": hb(0, 2), "b": hb(1, 0, extra=[[11, 0.22, "gh1", 4]]), "c": hb(2, 3), "d": hb(3, 1, extra=[[15.5, 0.55, "t12"]])}
Y2 = {"a": hb(2, 0, extra=[[3, 0.2, "gh1", -3]]), "b": hb(3, 2), "c": hb(0, 1, extra=[[7, 0.25, "gh1", 4], [13, 0.2, "gh1", -2]]),
      "d": hb(1, 3, extra=[[14.5, 0.5, "t04"], [15.5, 0.7, "t12"]])}
Yq = {k: [[e[0], 0.45, *e[2:]] for e in v] for k, v in Y2.items()}   # the Amen, quiet, under break4
# U: the undertow, a two-step cut from the Amen: the kick on 1 and the and of 3 only, the doubled kicks and the ghost
# after beat 2 swapped for the hats take; one edit per bar
def ts(b, extra=()):
    return ([e for e in base(b) if e[0] not in (2, 3, 8, 9, 11)]
            + [[2, 0.5, "h02"], [3, 0.4, "h03"], [8, 0.55, "h08"], [9, 0.4, "h09"], [11, 0.45, "h11"]] + list(extra))


U = {"a": ts(0), "b": ts(1, [[9, 0.25, "gh1", 3]]), "c": ts(2), "d": ts(3, [[15.5, 0.7, "t12"]]),
     "e": ts(0, [[14, 0.6, "kick1"]]), "f": swap(ts(1), 13, [13, 0.6, "s12d"]), "g": ts(2, [[7, 0.3, "gh1", -3], [15, 0.6, "t04"]])}
# break4 (c..): the take, a quiet layer, its own edit
K4 = {k: cb(i) for i, k in enumerate("abcd")}
K4q = {k: cb(i, vel=0.45) for i, k in enumerate("abcd")}
K4e = {"a": cb(0),
       "b": swap(cb(1), 14, [14, 0.85, "c04"]),
       "c": [e for e in cb(2) if not 8 <= e[0] < 12] + [[8 + i, 0.95, f"c{i:02d}"] for i in range(4)],   # beat 3 re-cut from beat 1
       "d": cb(3, range(12)) + [[12, 1.0, "c12"], [13, 0.7, "c12"], [14, 0.85, "c04"], [15, 0.9, "s04u"], [15.5, 1.0, "t12"]]}
# break7 (z..): its own edit, the fourth bar (its fill) kept whole
ZE = {"a": zb(0),
      "b": swap(zb(1), 10, [10, 0.85, "z00"]),
      "c": [e for e in zb(2) if not 8 <= e[0] < 12] + [[8 + i, 0.95, f"z{i:02d}"] for i in range(4)],
      "d": zb(3)}


# KH: half time on break4, its kick beat, the hats take where the snare was, its snare beat moved to beat 3
def khalf(b, extra=()):
    return ([[i, (1.0, 0.8, 0.9, 0.8)[i], f"c{16 * b + i:02d}"] for i in range(4)] + [[4 + i, 0.6, f"h{4 + i:02d}"] for i in range(4)]
            + [[8 + i, 1.0 if i == 0 else 0.85, f"c{16 * b + 4 + i:02d}"] for i in range(4)] + [[12 + i, 0.6, f"h{12 + i:02d}"] for i in range(4)]
            + list(extra))


KH = {"a": khalf(0), "b": khalf(1, [[14, 0.6, "kick1"]]), "c": khalf(2, [[6, 0.22, "gh1", 3]]), "d": khalf(3, [[15, 0.6, "t12"], [15.5, 0.75, "t12"]])}
perc = lambda b, vel=0.35: [[s, vel, f"z{16 * b + s:02d}"] for s in (2, 3, 6, 7, 10, 11, 14, 15)]   # break7's off-beat percussion under it
KH2 = {"a": khalf(0) + perc(0), "b": khalf(1, [[14, 0.6, "zk1"]]) + perc(1), "c": swap(khalf(2), 13, [13, 0.5, "s09u"]) + perc(2),
       "d": khalf(3, [[14, 0.5, "zt04"], [15, 0.7, "zt12"], [15.5, 0.85, "s04u"]]) + perc(3, 0.3)}
s_ = lambda b, steps: [[i, 1.0, f"s{16 * b + i:02d}"] for i in steps]
F = {"YF1": s_(2, range(8)) + [[8, 0.9, "s12d"], [9, 0.3, "gh1"], [10, 0.85, "s04"], [11, 0.6, "s13"], [12, 1.0, "s12"], [14, 0.8, "s04u"], [14.5, 0.6, "t12"], [15, 0.95, "s12u"]],
     "YF2": s_(1, range(12)) + [[12, 0.7, "s07d"], [13, 0.8, "s09u"], [14, 0.9, "s04"], [15, 0.95, "s04u"], [15.5, 0.7, "t04"]],
     "YF3": s_(3, range(10)) + [[10, 0.6, "t04"], [10.5, 0.7, "t12"], [11, 0.75, "t04"], [11.5, 0.8, "t12"], [12, 1.0, "s12"], [13, 0.4, "gh1"], [14, 0.9, "s04"],
                                [15, 0.6, "s12d"], [15.5, 0.9, "s04u"]],
     "YF4": s_(0, range(8)) + [[12, 0.45, "gh1"], [14, 0.7, "s12"], [15, 0.85, "s04u"]],                       # two beats of air, the soul breath
     "YF5": zb(1, range(8)) + s_(3, range(8, 16)),                                                              # break7 hands over to the Amen's last half bar
     "YF6": s_(2, range(4)) + [[4, 1.0, "s04"], [6, 0.6, "s09u"], [7, 0.4, "gh1"], [8, 0.9, "c04"], [10, 0.8, "s12d"], [12, 1.0, "c12"], [13, 0.6, "t12"],
                               [14, 0.85, "s04u"], [15, 0.9, "s12u"], [15.5, 1.0, "t04"]],
     "YF7": s_(1, range(12)) + [[12, 0.6, "t04"], [12.5, 0.7, "t12"], [13, 0.75, "t04"], [13.5, 0.8, "t12"], [14, 0.9, "s12d"], [15, 1.0, "s04u"]],
     "YR": s_(3, range(4)) + [[4 + i / 2, 0.3 + 0.028 * i, ("c04", "t12", "c12", "t04")[i % 4]] for i in range(22)] + [[15, 0.95, "c04"], [15.5, 1.0, "s04u"]],   # the roll-in
     "PUY": [[4, 0.3, "gh1", 3], [8, 0.5, "s12d"], [10, 0.4, "gh1", -2], [12, 0.8, "s04"], [13, 0.5, "t12"], [14, 0.7, "s09u"], [15, 0.85, "s04u"], [15.5, 1.0, "s12u"]],
     "FD3": cb(1, range(8)) + [[8, 0.9, "s04"], [9, 0.5, "s05"], [10, 0.85, "c10"], [11, 0.6, "c11"], [12, 1.0, "s12"], [13, 0.7, "c12"], [14, 0.8, "s04u"],
                               [15, 0.9, "c04"], [15.5, 1.0, "s12u"]]}
F |= {"FP": zb(3, range(8)) + [[8, 0.9, "z04"], [10, 0.7, "zt04"], [11, 0.6, "zt12"], [12, 1.0, "z04u"], [13, 0.7, "zt12"], [14, 0.85, "s04"], [15, 0.95, "s04u"]],
      "FD1": cb(0, range(8)) + [[8 + i, 0.5 + 0.06 * i, ("c04", "c12", "s04u", "s12")[i % 4]] for i in range(8)],   # a snare climb over break4
      "FD2": [e for e in zb(1) if e[0] < 8] + [[8, 0.9, "c10"], [9, 0.6, "c09"], [10, 0.9, "c04"], [12, 1.0, "z04"], [13, 0.7, "zt12"], [14, 0.85, "c12"],
                                              [15, 0.9, "z04u"], [15.5, 1.0, "zt12"]],   # break4 cuts into break7's fill
      "KF": khalf(1)[:8] + [[8, 1.0, "c04"], [10, 0.7, "t12"], [11, 0.6, "t04"], [12, 0.9, "c12"], [13, 0.6, "zt12"], [14, 0.8, "s04u"], [15, 0.95, "s12u"]],
      "FK": cb(2, range(12)) + [[12, 0.7, "zt04"], [13, 0.6, "zt12"], [14, 0.85, "c12"], [14.5, 0.9, "zt12"], [15, 0.95, "z04u"], [15.5, 1.0, "s04u"]]}
PROGRAMS = {**{k: NS.PROGRAMS[k] for k in ("TL", "hats", "hatsq", "ride", "rz", "kr", "kr2", "sl", "sl2", "hl")},   # layers only, no Amen edits
            "Y": Y, "Y2": Y2, "Yq": Yq, "U": U, "K4": K4, "K4q": K4q, "K4e": K4e, "ZE": ZE, "Z": {k: zb(i) for i, k in enumerate("abcd")}, "KH": KH, "KH2": KH2, **F}


# ---------------------------------------------------------------- arrangement (176 bars)
INTRO = 32      # bars before the first break (53 s at 145 bpm): Rhodes alone, strings, the ooh and the sub, the guitar
FULL = ["pad", "bass", "lead", "comp", "vox"]
Z2 = ("kr2", "sl2", "rz")
HT = ["pad", "vox", "lead_hi", "bass2", "comp"]
ARR = ([blk("Opening: Rhodes alone", "B", 8, ["comp"], vel={"comp": 0.7}),
        blk("Opening: strings", "B", 8, ["comp", "pad"], vel={"pad": 0.7, "comp": 0.75}),
        blk("Opening: the ooh and the sub", "A", 8, ["comp", "pad", "vox", "bass2"], vel={"pad": 0.8, "comp": 0.8, "bass2": 0.7}),
        blk("Opening: the guitar", "A", 8, ["comp", "pad", "vox", "bass2", "lead"], vel={"pad": 0.85, "comp": 0.8, "lead": 0.75, "bass2": 0.8}),
        blk("Percussion out of the filter", "V", 7, ["pad", "vox", "comp"], ["Z"]), blk("Percussion out of the filter: fill FP", "V", 1, ["pad", "vox", "comp"], ["FP"])]
       + groove("The Amen arrives", "A", ["pad", "bass2", "lead_hi", "comp"], [["Y", "TL"]], ["YF1"], extra=("kr", "sl"), restart=True)
       + groove("Main groove", "V", ["pad", "bass", "comp"], [["Y2", "TL"], ["Y", "hats"]], ["YF2", "YF3"])
       + groove("Main groove: the guitar", "A", ["pad", "bass", "lead", "comp"], [["Y", "ride"], ["Y2", "rz"]], ["YF4", "YF5"], restart=True)
       + [blk("Breakdown", "B", 8, ["pad", "vox", "lead", "comp"], vel={"pad": 0.85, "lead": 0.8, "comp": 0.8}),
          blk("Breakdown: hats", "B", 8, ["pad", "vox", "lead_hi", "comp"], ["hatsq"], vel={"pad": 0.85, "comp": 0.8})]
       # the undertow: a two-step under a rising high-pass, a roll over break4's snare, then the drop lands full
       + [blk("Undertow", "A", 7, ["pad", "bass2"], ["U"]), blk("Undertow: roll-in YR", "A", 1, ["pad", "bass2"], ["YR"])]
       + groove("Drop", "A", FULL, [["K4", "hats", "kr"]], ["FD1"], restart=True, extra=())
       + groove("Drop: the Amen", "A", FULL, [["K4", "Yq"]], ["FD3"])
       + groove("Drop: percussion", "A", FULL, [["ZE", "K4q"]], ["FD2"], extra=Z2)
       # half time on break4: the snare on beat 3, long sub notes; break7's percussion comes in on the off-beats; subtraction, pickup
       + [blk("Half-time passage", "V", 7, HT, ["KH", "hl", "rz"], loop_restart=True), blk("Half-time passage: fill KF", "V", 1, HT, ["KF", "rz"]),
          blk("Half-time passage: percussion", "V", 6, HT + ["lead"], ["KH2", "hl"], vel={"lead": 0.8}),
          blk("Half-time passage: subtraction", "V", 1, ["pad", "vox"]),
          blk("Half-time passage: pickup", "V", 1, ["pad", "bass"], ["PUY"])]
       + groove("Final groove", "A", FULL, [["Y2", "K4q"]], ["YF6"], restart=True)
       + groove("Final groove: break4", "A", FULL, [["K4e", "rz"]], ["FK"], extra=("kr2", "sl2"))
       + groove("Final groove: last pass", "A", FULL, [["Y", "K4q", "hats"]], ["YF7"])
       + [blk("DJ outro", "A", 4, [], ["Y2", "ride", "kr"]), blk("DJ outro: pulled out", "A", 4, [], ["Y", "hats", "kr"])])
for b_ in ARR:
    b_["transpose"] = TRANSPOSE
TOTAL = sum(x["bars"] for x in ARR)
START = [1 + sum(x["bars"] for x in ARR[:i]) for i in range(len(ARR))]
FILL_BARS = [START[i] for i, x in enumerate(ARR) if any(d in F for d in x["drums"])]
at = lambda prefix: next(START[i] for i, x in enumerate(ARR) if x["name"].startswith(prefix))   # the first bar of a block
SUBTRACT = at("Half-time passage: subtraction")
SECTIONS = []
for i, x in enumerate(ARR):
    nm = re.sub(r" \d+$", "", x["name"].split(":")[0])
    end = START[i] + x["bars"] - 1
    if SECTIONS and SECTIONS[-1][2] == nm:
        SECTIONS[-1] = (SECTIONS[-1][0], end, nm)
    else:
        SECTIONS.append((START[i], end, nm))
SONG = ROOT / "songs" / "jungle162" / "jungle162-196520246.am.json"      # F minor: A: Fm Ab6 Bbm6 Ab, V: Fm Bbm7 Eb Dbmaj7, B: Fm Bbm7 Dbmaj7 Cm7

SUB = copy.deepcopy(J.SUB)
SUB["layers"][1]["preset"] |= {"cutoff": 140, "resonance": 0.35, "env_amount": 1000, "filter_decay": 0.2}

DROP, UNDER, OUTRO = at("Drop"), at("Undertow"), at("DJ outro")
ALL_DRUMS = ["break", "breakfx", "break2", "break3", "ride", "kick", "snlay"]
SPEC = {
    "title": TITLE, "song": SONG, "genre": "atmospheric-jungle-95", "rebuild": "bountiful/undertow.py",
    "composer": LT.B.COMPOSER_CREDIT, "artist": LT.B.ARTIST, "album": ALBUM, "year": 2026,
    "blurb": ("A 1992-95 soul jungle track at 145 bpm in D minor on three real breaks, the Amen in its own long half-bar edits, a rolling "
              "percussion break and a hard funk break, sampled on a 12-bit sampler and re-laid on the grid as continuous takes. Fifty seconds of "
              "opening: Ice Rhodes alone, slow strings, a soul ooh over the sub, a jazz guitar sung behind the beat; the percussion rising out of "
              "a high-pass, the Amen arriving; ninth and eleventh chords, a walking sub under a fretless upper bass, a soft organ answering; a "
              "two-step pulled out from under the track before the drop lands on the funk break, a half-time passage cut from it, printed "
              "through tape, and a DJ outro of beat alone."),
    "overrides": {"bpm": BPM, "swing": 0.5, "drums": "grid", "grid": PROGRAMS, "arrangement": ARR, "drum_cycle_per_block": True, "loop_continuous": True,
                  "master": {**LT.B.MASTER, "hp": 25, "mono_below": 120, "glue": {},
                             "tape": {"drive": 1.7, "bias": 0.07, "bump_db": 1.6, "hf_db": -1.2, "lp_hz": 16500, "hiss_db": -73, "wow_ms": 0.07},
                             "eq": [["peak", 180, 1.0, 0.7], ["peak", 400, -0.8, 1.0], ["peak", 1500, 1.0, 0.7], ["peak", 5000, -0.8, 1.0]],
                             "multiband": {"freqs": [150, 5000], "bands": [{"threshold_rel": -3, "ratio": 2.5, "attack": 0.03, "release": 0.15},
                                                                           {"threshold_rel": -3, "ratio": 1.6, "attack": 0.015, "release": 0.12},
                                                                           {"threshold_rel": -3, "ratio": 1.8, "attack": 0.005, "release": 0.08}]},
                             "bus_comp": {"threshold_rel": -3, "ratio": 2.0, "attack": 0.03, "release": 0.2, "sc_hp": 100},
                             "target_lufs": -9.6, "ceiling": -1.0, "clip": 0.9, "true_peak": -1.0},   # Tide's master: the album sits together
                  "harmony": {"rhythm": 1, "dominant": "modal", "tonic_major": "7sus4", "colors": {"m": "m9", "": "maj9", "m7": "m9", "7": "9", "maj7": "maj9", "6": "6/9"}},
                  "melody": {"modal": True, "register": [63, 83], "max_leap": 9, "max_notes_per_bar": 5, "articulation": "legato", "phrase_bars": 4,
                             "swing": 0.62, "push_ms": 22, "humanize_ms": 16, "velocity": [0.32, 0.95]},   # guitar phrases sung late, behind the beat
                  # registers are before the transpose (-3): the sub sounds from D1 up, as in Tide
                  "bass": {"style": "pattern", "register": [29, 46],   # a walking soul bass: root, third, fifth, seventh, octave
                           "patterns": [[[0, "R", 0.9, 1.0], [6, "3", 0.3, 0.8], [8, "5", 0.45, 0.85], [11, "O", 0.3, 0.8], [14, "5", 0.4, 0.8]],
                                        [[0, "R", 1.5, 1.0], [7, "O", 0.25, 0.8], [8, "5", 0.7, 0.85], [12, "3", 0.5, 0.9], [15, "R", 0.2, 0.7]],
                                        [[0, "R", 0.45, 1.0], [3, "R", 0.2, 0.7], [6, "3", 0.4, 0.8], [8, "5", 0.6, 0.85], [11, "7", 0.25, 0.75], [14, "O", 0.4, 0.8]],
                                        [[0, "R", 2.2, 1.0], [10, "5", 0.3, 0.8], [12, "3", 0.5, 0.85], [14, "O", 0.25, 0.75], [15, "5", 0.2, 0.7]]]},
                  "bass2": {"style": "pattern", "register": [29, 46],
                            "patterns": [[[0, "R", 3.5, 0.9]], [[0, "R", 2.0, 0.9], [10, "5", 1.0, 0.75]]]},
                  "comp": {"steps": [0, 6, 10, 14], "low": 52, "high": 71, "top": 68, "notes": 5, "gate": 1.4, "strum_ms": 30, "swing": 0.62, "push_ms": 18,
                           "humanize_ms": 14, "vel": 0.42, "accent": 0.68},
                  "vox": {"steps": [0], "low": 59, "high": 76, "top": 71, "notes": 3, "gate": 3.8, "vel": 0.5, "accent": 0.5},
                  "pad": {"low": 49, "high": 78, "top": 73, "notes": 5, "vel": 0.5}},
    "kit_def": J.kit(),
    "layers": [("bass", "bass_mid")],
    "sends": {"slap": {"type": "delay", "time_beats": 0.75, "feedback": 0.35, "taps": 3, "tone": 2800},
              "plate": {"type": "reverb", "seconds": 4.5, "predelay": 0.035, "damp": 0.6}},
    "voices": {
        "pad": ({"zyn": "Collection/0025-Slow Strings.xiz"}, "Slow Strings (ZynAddSubFX - Collection), the strings",
                dict(hp=150, width=0.75, eq=[["peak", 2500, 1.0, 0.8], ["highshelf", 3500, 2.0]], crush=J.SAMPLER(32000, 0.5),
                     sends={"plate": 0.5}, gain_db=-9.0)),
        "vox": ({"zyn": "ChoirAndVoice/0004-Voice OOH.xiz"}, "Voice OOH (ZynAddSubFX - ChoirAndVoice), the soul ooh",
                dict(hp=300, lp=9000, width=0.75, crush=J.SAMPLER(26040, 0.5), sends={"plate": 0.6}, gain_db=-14.0)),
        "lead_hi": ({"zyn": "Organ/0069-Soft Organ 1.xiz"}, "Soft Organ 1 (ZynAddSubFX - Organ), the organ answering",
                    dict(hp=350, lp=8000, width=0.8, crush=J.SAMPLER(26040, 0.4), sends={"slap": 0.4, "plate": 0.5}, gain_db=-15.0)),
        "lead": ({"zyn": "Collection/0107-Smooth Guitar.xiz"}, "Smooth Guitar (ZynAddSubFX - Collection), the jazz-guitar lead",
                 dict(hp=200, lp=7500, width=0.5, crush=J.SAMPLER(26040, 0.35), sends={"slap": 0.35, "plate": 0.4}, gain_db=-8.0)),
        "comp": ({"zyn": "Rhodes/0012-Ice Rhodes1.xiz"}, "Ice Rhodes1 (ZynAddSubFX - Rhodes), chords",
                 dict(hp=140, crush={"bits": 12, "rate": 26040, "mix": 0.35}, width=0.85, sends={"plate": 0.3, "slap": 0.12}, gain_db=-7.0)),
        "bass_mid": ({"zyn": "Collection/0043-Fretless Bass.xiz"}, "Fretless Bass (ZynAddSubFX - Collection), upper-bass texture",
                     dict(hp=180, lp=1600, mono=True, duck={"depth": 0.25, "release": 0.09}, gain_db=-15.0)),
    },
    "extra_tracks": {"bass": dict(SUB, duck={"depth": 0.3, "release": 0.09}, gain_db=-14.0),
                     "bass2": dict(SUB, duck={"depth": 0.25, "release": 0.1}, gain_db=-11.5)},
    "targets": {"bass": -0.5, "bass_mid": -12.0, "pad": -11.5, "comp": -12.0, "lead": -10.0, "vox": -19.0},
    "level_ref": "break",
    "test_bars": (DROP, DROP + 7),
    "automation": [
        {"type": "lowpass", "tracks": ["comp"], "points": [[1, 700], [9, 1600], [17, 3500], [INTRO + 1, 12000]]},  # the Rhodes opens slowly
        {"type": "lowpass", "tracks": ["pad"], "points": [[9, 500], [17, 1200], [25, 2500], [INTRO + 1, 5000], [INTRO + 17, 12000]]},
        {"type": "highpass", "tracks": ["break2"], "points": [[INTRO + 1, 2500], [INTRO + 5, 600], [INTRO + 8, 20]]},   # the percussion rises out of the high-pass
        {"type": "lowpass", "tracks": ["pad"], "points": [[at("Breakdown"), 2000], [at("Breakdown: hats"), 3500], [UNDER, 12000]]},
        {"type": "highpass", "tracks": ALL_DRUMS, "points": [[UNDER, 20], [UNDER + 3, 400], [DROP, 3500]]},          # the undertow: the beat pulled out
        {"type": "highpass", "tracks": ["bass2"], "points": [[UNDER + 3, 20], [DROP, 700]]},                          # and the sub drains away under it
        {"type": "lowpass", "tracks": ["pad"], "points": [[at("Half-time"), 2500], [at("Half-time") + 8, 5000], [at("Final groove"), 12000]]},
        {"type": "highpass", "tracks": ALL_DRUMS, "points": [[OUTRO + 4, 20], [TOTAL + 1, 2500]]}],                  # and pulled out again at the end
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
    kind = lambda b: {str(n)[0] for _, n in per_bar.get(b, []) if str(n)[:1] in "szc" and str(n)[1:3].isdigit()}
    res.append((f"a long opening: {INTRO} bars", INTRO * 4 * beat >= 48, f"{INTRO * 4 * beat:.1f} s before the first break"))
    tide, tbpm, _ = read_midi(ROOT / "tracks" / "tidewater" / "tidewater.mid")
    tbeat = 60 / tbpm

    def amen_bars(ns, bt):
        bars = {}
        for n in ns:
            if n["track"] == "drums" and isinstance(sound_of(n), str) and sound_of(n)[:1] == "s" and sound_of(n)[1:3].isdigit():
                st = round((n["start"] / bt) % 4 * 4, 1)
                bars.setdefault(int((n["start"] + 0.01) / bt // 4), set()).add(((st - 16 if st > 15.9 else st), sound_of(n)))
        return {frozenset(v) for v in bars.values() if len(v) >= 8}
    shared = amen_bars(notes, beat) & amen_bars(tide, tbeat)
    res.append(("the Amen is edited its own way: no Amen bar copied from Tide", not shared, f"{len(shared)} shared bars"))
    res.append((f"bars 1-{INTRO}: Rhodes and strings, no drums", not any(b in per_bar for b in range(1, INTRO + 1)) and INTRO + 1 in per_bar, ""))
    res.append((f"bars {INTRO + 1}-{INTRO + 7}: the percussion break alone", all(kind(b) == {"z"} for b in range(INTRO + 1, INTRO + 8)), ""))
    lost = sum(1 for v in per_bar.values() for _, n in v if not isinstance(n, str))
    res.append(("every drum note names a kit sound (none clipped at MIDI's 127)", lost == 0, f"{lost} undecoded notes"))
    srcs = json.loads((J.OUT / "z_info.json").read_text())["source"], json.loads((J.OUT / "c_info.json").read_text())["source"]
    res.append(("this track's breaks: break7 and break4 in the z and c slots", srcs[0].endswith("break7.wav") and srcs[1].endswith("break4.wav"),
                ", ".join(Path(s).name for s in srcs)))
    used = set().union(*(kind(b) for b in per_bar))
    res.append(("all three breaks play", used == {"s", "z", "c"}, "".join(sorted(used))))
    un = range(UNDER, UNDER + 7)
    two = [b for b in un if not any(s in (2.0, 3.0, 8.0, 9.0, 11.0) and str(n).startswith("s") for s, n in per_bar.get(b, []))
           and any(str(n)[:1] == "s" and str(n)[1:3].isdigit() for s, n in per_bar.get(b, []))]   # the downbeat slice leads by a few ms
    res.append(("the undertow: a two-step cut from the Amen", len(two) == 7, f"{len(two)}/7 bars"))
    mid = [sigs.get(b) for b in un]
    res.append(("the undertow is edited bar by bar, not looped", all(mid) and len(set(mid)) == 7, f"{len(set(mid))} distinct of 7 bars"))
    d_bars = range(DROP, DROP + 7)
    res.append(("the drop lands on break4", all("c" in kind(b) for b in d_bars) and all(kind(b) == {"c"} for b in d_bars), ""))
    distinct = len(set(sigs.values()))
    res.append(("drum bars are varied (distinct bar patterns)", distinct >= 15, f"{distinct} distinct patterns over {len(sigs)} drum bars"))
    fills = [sigs.get(b) for b in FILL_BARS]
    res.append(("every fill bar is its own edit", len(set(fills)) == len(fills), f"{len(set(fills))} distinct fills over {len(fills)} fill bars"))
    blocks = [tuple(sigs.get(b) for b in range(s, s + 7)) for s in range(INTRO + 1, TOTAL - 7, 8) if all(b in sigs for b in range(s, s + 7))]
    res.append(("8-bar groove blocks are not copies of each other", len(set(blocks)) >= len(blocks) // 2, f"{len(set(blocks))} distinct of {len(blocks)}"))
    res.append((f"bar {SUBTRACT} subtracts the drums before the final return", SUBTRACT not in per_bar and SUBTRACT + 1 in per_bar, ""))
    music = {"pad", "comp", "bass", "bass2", "vox", "lead", "lead_hi", "bass_mid"}
    res.append((f"bars {OUTRO}-{TOTAL}: a DJ outro, the beat alone", all(b in per_bar for b in range(OUTRO, TOTAL + 1))
                and not any(n["track"] in music and bar_of(n["start"]) >= OUTRO for n in notes), ""))
    harm = [n for n in notes if n["track"] in ("pad", "comp", "bass", "bass2", "vox", "lead", "lead_hi")]
    out_key = sum(1 for n in harm if n["pitch"] % 12 not in KEY_PCS)
    res.append(("harmony is in D minor (transposed skeleton)", out_key <= 0.02 * len(harm), f"{out_key}/{len(harm)} notes outside D natural minor"))
    names = [x[1] for v in per_bar.values() for x in v]
    for label, test in (("32nd pickups", lambda s: str(s).startswith(("t", "zt"))), ("pitched slices", lambda s: s in PITCHED),
                        ("extra ghost one-shots", lambda s: s in ("gh1", "zs1")), ("extra kicks", lambda s: s in ("kick1", "zk1")),
                        ("kick reinforcement", lambda s: s == "kreinf"), ("snare layer", lambda s: s == "snlay"), ("hats-only take", lambda s: str(s).startswith("h"))):
        c = sum(1 for s in names if test(s))
        res.append((f"break uses {label}", c > 0, f"{c} hits"))
    ht = [b for b in range(at("Half-time"), SUBTRACT) if b in per_bar]
    snares = {f"c{16 * k + 4:02d}" for k in range(4)}
    on8 = sum(1 for b in ht if any(s == 8.0 and str(n) in snares | {"c04"} for s, n in per_bar[b]))
    res.append(("half-time passage on break4: its snare moves to beat 3", ht and on8 >= len(ht) - 1, f"{on8}/{len(ht)} bars"))
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
    res.append(("bass moves by octaves, and stays above C1", octs > 0 and low >= 24, f"{octs} bars with an octave move, lowest note {low}"))
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
    extra_rows = [(INTRO + 1, INTRO + 7, "percussion alone"), (UNDER, UNDER + 3, "undertow, first half"), (UNDER + 4, UNDER + 6, "undertow, pulled out"),
                  (DROP, DROP + 6, "drop landing")]
    for a, b, name in SECTIONS + extra_rows:
        i0, i1 = int(((a - 1) * 4 + 1) * beat * SR), int(b * 4 * beat * SR) - int(0.01 * SR)   # the next bar's 5 ms leads stay out
        rows.append((a, b, name, round(meter.integrated_loudness(master[i0:i1]), 1), {s: round(lvl(x[i0:i1]), 0) for s, x in stems.items()}))
    row = {name: v for _, _, name, _, v in rows}
    ra = row["Opening"]
    res.append((f"bars 1-{INTRO}: the opening, music only", ra.get("pad", -120) > -40 and ra.get("comp", -120) > -40
                and all(v < -60 for s, v in ra.items() if s not in ("pad", "comp", "vox", "lead", "bass2")), f"pad {ra.get('pad')}, comp {ra.get('comp')}"))
    r0 = row["percussion alone"]
    res.append(("the percussion break under the pads, no other break", r0.get("break2", -120) > -45 and r0.get("break", -120) < -60 and r0.get("break3", -120) < -60,
                f"break2 {r0.get('break2')}"))
    loud = {name: l for a, b, name, l, _ in rows}
    contrast = loud["Drop"] - loud["Breakdown"]
    res.append(("dynamic contrast between breakdown and drop", contrast >= 2.5, f"{contrast:.1f} LU"))
    pull = loud["drop landing"] - loud["undertow, pulled out"]
    res.append(("the undertow pulls the beat out, the drop lands full", pull >= 2.0, f"{pull:.1f} LU"))
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
