"""Tidewater: a third 1992-95 atmospheric jungle track, after Night Signal, on the same three breaks.

The break pipeline is Haze Theory's (bountiful/jungle174.py): the Amen (s..), break 2 (z.., the "yeah, uh huh" take) and the
cowbell break (c.., breaks/break3.wav, a one-bar loop played round to four bars) sped up to 136 bpm on a 12-bit sampler and
re-laid on the grid as continuous takes. They share its kit and layer programs, and Night Signal's edits and fill library.
What is new: F minor on another skeleton (Fm - Bbm7 - Dbmaj7 - Fm7, a soft-Rhodes progression), sixteen bars of Rhodes and
strings before any drum; the cowbell break rising out of a closed filter; an exchange in the middle of the track, seven
bars that trade the three breaks beat by beat (program X); a half-time passage cut from break 2 (the snare on three, its
voice kept); a muted-horn lead over soft Rhodes, a fretless upper bass and vibes; the track closing on the Rhodes again.

    python -I bountiful/tidewater.py              # sample the breaks (if needed), compose, render, master, validate
    python -I bountiful/tidewater.py --validate   # the checks only, on the last render
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

os.environ.setdefault("BOUNTIFUL_BREAK_BPM", "136")   # the jazzstep pocket, a touch under Night Signal
os.environ.setdefault("BOUNTIFUL_BREAK_CRUSH", "0.6")  # a little less sampler grit on the breaks than Night Signal
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jungle174 as J   # noqa: E402  (the break pipeline, the kit and the layer programs)
import night_signal as NS   # noqa: E402  (its edits and fill library; importing it builds nothing)

LT, ROOT, BPM, SR, NOTES, PITCHED, sound_of = J.LT, J.ROOT, J.BPM, J.SR, J.NOTES, J.PITCHED, J.sound_of
base, swap, zb, head, vary, blk, groove, cb, half = J.base, J.swap, J.zb, J.head, J.vary, J.blk, J.groove, NS.cb, NS.half
TITLE, SLUG = "Tide", "tidewater"
TRANSPOSE = -4                                     # A minor skeleton -> F minor
KEY_PCS = {5, 7, 8, 10, 0, 1, 3}                   # F natural minor


# ---------------------------------------------------------------- new edits
# X: the exchange, the three breaks traded inside the bar (c the cowbells, s the Amen, z break 2), one edit per bar
def mix(*parts):
    """one bar from (break, bar of the take, first step, last step) pieces, each piece in its own place on the grid"""
    return [[i, 1.0 if p == "s" else 0.95, f"{p}{16 * b + i:02d}"] for p, b, a, e in parts for i in range(a, e)]


X = {"a": mix(("c", 0, 0, 8), ("s", 0, 8, 16)),                                            # cowbells, then the Amen answers
     "b": mix(("s", 1, 0, 8), ("z", 1, 8, 16)),                                            # the Amen, then break 2
     "c": mix(("z", 2, 0, 8), ("c", 2, 8, 16)),                                            # break 2, then the cowbells
     "d": mix(("s", 0, 0, 4), ("c", 1, 4, 8), ("z", 0, 8, 12), ("s", 3, 12, 16)),           # one beat each
     "e": mix(("c", 3, 0, 12)) + [[12, 1.0, "s12"], [13, 0.6, "t12"], [14, 0.9, "z04"], [15, 0.8, "t04"], [15.5, 0.9, "t12"]],
     "f": mix(("z", 0, 0, 4), ("c", 0, 4, 8), ("z", 0, 8, 12), ("c", 0, 12, 16)),          # break 2 and the cowbells, beat about
     "g": mix(("s", 2, 0, 8)) + [[8 + i, 0.5 + 0.06 * i, ("c04", "s04", "z04", "s12")[i % 4]] for i in range(8)]}   # a three-break snare climb


# ZH: half time on break 2, its kick beat, the hats take where the snare was, its snare beat moved to beat 3
def zhalf(b, extra=()):
    return ([[i, (1.0, 0.8, 0.9, 0.8)[i], f"z{16 * b + i:02d}"] for i in range(4)] + [[4 + i, 0.6, f"h{4 + i:02d}"] for i in range(4)]
            + [[8 + i, 1.0 if i == 0 else 0.85, f"z{16 * b + 4 + i:02d}"] for i in range(4)] + [[12 + i, 0.6, f"h{12 + i:02d}"] for i in range(2)]
            + ([[14, 0.85, "z14"], [15, 0.85, "z15"]] if b % 2 == 0 else [[14, 0.85, "z42"], [15, 0.85, "z43"]])   # the voice, "yeah, uh huh"
            + list(extra))


ZH = {"a": zhalf(0), "b": zhalf(1, [[14, 0.6, "zk1"]]), "c": zhalf(2, [[6, 0.22, "zs1", 3]]), "d": zhalf(3, [[15, 0.7, "zt12"], [15.5, 0.8, "zt12"]])}
ZH2 = {"a": zhalf(0) + [[2, 0.5, "c02"], [6, 0.45, "c06"], [10, 0.5, "c10"], [14, 0.45, "c14"]],   # the cowbells come back in on the off-beats
       "b": zhalf(1, [[14, 0.6, "zk1"], [2, 0.5, "c02"], [10, 0.5, "c10"]]),
       "c": swap(zhalf(2), 13, [13, 0.5, "z04u"]) + [[6, 0.45, "c06"], [14, 0.45, "c14"]],
       "d": zhalf(3, [[14, 0.5, "zt04"], [15, 0.7, "zt12"], [15.5, 0.85, "s04u"]])}
F = dict(NS.F)
F |= {"ZF": zhalf(1)[:8] + [[8, 1.0, "z04"], [10, 0.7, "zt12"], [11, 0.6, "zt04"], [12, 0.9, "z04"], [13, 0.6, "zt12"], [14, 0.8, "z04u"], [15, 0.95, "s04u"]],
      "CF": cb(1, range(8)) + [[8, 0.9, "c00"], [10, 0.8, "c00"], [12, 1.0, "s12"], [13, 0.6, "t12"], [14, 0.85, "s04u"], [14.5, 0.9, "t12"], [15, 1.0, "s04u"]],
      "FZ8": [e for e in zb(2) if e[0] < 8] + [[8, 0.9, "c08"], [9, 0.6, "c09"], [10, 0.9, "s12d"], [12, 1.0, "z04"], [13, 0.7, "zt12"], [14, 0.85, "c04"],
                                              [15, 0.9, "z04u"], [15.5, 1.0, "zt12"]],          # the cowbells cut into break 2's fill
      "PU3": [[12, 0.7, "c12"], [13, 0.5, "zt12"], [14, 0.8, "zt04"], [14.5, 0.85, "zt12"], [15, 0.9, "z04u"], [15.5, 1.0, "s04u"]]}
PROGRAMS = {**{k: NS.PROGRAMS[k] for k in ("A", "A2", "T", "T2", "TL", "hats", "hatsq", "ride", "rz", "kr", "kr2", "sl", "sl2", "N", "N2", "B2", "T3",
                                            "W", "W2", "Wq", "hl")},
            "X": X, "ZH": ZH, "ZH2": ZH2, **F}


# ---------------------------------------------------------------- arrangement (176 bars)
INTRO = 16      # bars of Rhodes, strings and voices before the first break (28.2 s at 136 bpm)
FULL = ["pad", "bass", "lead", "comp", "vox"]
Z2 = ("kr2", "sl2", "rz")
HT = ["pad", "vox", "lead_hi", "bass2", "comp"]
ARR = ([blk("Atmosphere: Rhodes and strings", "B", 8, ["pad", "comp"], vel={"pad": 0.7, "comp": 0.7}),
        blk("Atmosphere: voices and vibes", "B", INTRO - 8, ["pad", "comp", "vox", "lead_hi"], vel={"pad": 0.8, "comp": 0.75, "lead_hi": 0.7}),
        blk("Cowbells out of the filter", "A", 7, ["pad", "vox"], ["W"]), blk("Cowbells out of the filter: fill CF", "A", 1, ["pad", "vox"], ["CF"])]
       + groove("Break 2 on the cowbells", "A", ["pad", "bass2", "lead_hi"], [["T", "Wq"]], ["FZ8"], extra=Z2, restart=True)
       + groove("The Amen arrives", "V", ["pad", "bass", "comp"], [["N", "Wq", "kr", "sl"], ["A", "TL", "ride", "kr", "sl"]], ["G1", "G3"], extra=())
       + groove("Main groove", "A", ["pad", "bass", "lead", "comp"], ["N", "N2"], ["G2", "G6"], restart=True)
       + [blk("Breakdown", "B", 8, ["pad", "vox", "lead", "comp"], vel={"pad": 0.85, "lead": 0.8, "comp": 0.8}),
          blk("Breakdown: hats", "B", 8, ["pad", "vox", "lead_hi", "comp"], ["hatsq"], vel={"pad": 0.85, "comp": 0.8})]
       + [blk("Exchange", "A", 7, ["pad", "bass2"], ["X"]), blk("Exchange: roll-in FZ5", "A", 1, ["pad", "bass2"], ["FZ5"])]
       + groove("Drop", "A", FULL, [["N", "Wq"]], ["G4"], restart=True)
       + groove("Drop: break 2", "A", FULL, [["T3", "TL"]], ["FZ6"], extra=Z2)
       + groove("Drop: hats", "A", FULL, [["N2", "hats"]], ["G5"])
       # half time on break 2: the snare on beat 3, long sub notes; the cowbells come back in on the off-beats; subtraction, pickup
       + [blk("Half-time passage", "V", 7, HT, ["ZH", "hl", "rz"], loop_restart=True), blk("Half-time passage: fill ZF", "V", 1, HT, ["ZF", "rz"]),
          blk("Half-time passage: cowbells", "V", 6, HT + ["lead"], ["ZH2", "hl", "rz"], vel={"lead": 0.8}),
          blk("Half-time passage: subtraction", "V", 1, ["pad", "vox"]),
          blk("Half-time passage: pickup", "V", 1, ["pad", "bass"], ["PU3"])]
       + groove("Final groove", "A", FULL, [["B2", "TL"]], ["G1v"], restart=True)
       + groove("Final groove: break 3", "A", FULL, [["W2", "rz"]], ["FZ7"], extra=("kr2", "sl2"))
       + groove("Final groove: last pass", "A", FULL, [["N", "Wq", "hats"]], ["G3v"])
       + groove("Outro", "B", ["pad", "comp", "vox"], ["N2"], ["G6v"])
       + [blk("Outro: cowbells into the filter", "B", 8, ["pad", "comp"], ["W", "kr2"]),
          blk("Last light: Rhodes and strings", "B", 8, ["pad", "comp", "lead_hi"], vel={"pad": 0.75, "comp": 0.7, "lead_hi": 0.6})])
for b_ in ARR:
    b_["transpose"] = TRANSPOSE
TOTAL = sum(x["bars"] for x in ARR)
START = [1 + sum(x["bars"] for x in ARR[:i]) for i in range(len(ARR))]
FILL_BARS = [START[i] for i, x in enumerate(ARR) if any(d in F for d in x["drums"])]
at = lambda prefix: next(START[i] for i, x in enumerate(ARR) if x["name"].startswith(prefix))   # the first bar of a block
SUBTRACT = at("Half-time passage: subtraction")
# sections: blocks merged by their name before ":" and any block number
SECTIONS = []
for i, x in enumerate(ARR):
    nm = re.sub(r" \d+$", "", x["name"].split(":")[0])
    end = START[i] + x["bars"] - 1
    if SECTIONS and SECTIONS[-1][2] == nm:
        SECTIONS[-1] = (SECTIONS[-1][0], end, nm)
    else:
        SECTIONS.append((START[i], end, nm))
SONG = ROOT / "songs" / "jungle174" / "jungle174-781837343.am.json"      # A: Am Dm7 Fmaj7 Am7, V: Am Dm7 E7 Em7, B: Am Dm7 Dm6 Em7

SUB = copy.deepcopy(J.SUB)
SUB["layers"][1]["preset"] |= {"cutoff": 150, "resonance": 0.4, "env_amount": 1200, "filter_decay": 0.18}   # rounder than Night Signal's

DROP = at("Drop")
SPEC = {
    "title": TITLE, "song": SONG, "genre": "atmospheric-jungle-95", "rebuild": "bountiful/tidewater.py",
    "composer": LT.B.COMPOSER_CREDIT, "artist": LT.B.ARTIST, "album": "Littoral", "year": 2026,
    "blurb": ("A 1992-95 atmospheric jungle track at 136 bpm in F minor on three real breaks, the Amen, a funk break and a cowbell break, "
              "sampled on a 12-bit sampler and re-laid on the grid as continuous takes. Half a minute of soft Rhodes and strings, the cowbells "
              "rising out of a closed filter, break 2 on top of them, the Amen arriving; an exchange in the middle that trades the three breaks "
              "beat by beat, a half-time passage cut from break 2; a rolling two-layer sub under a fretless upper bass, a muted horn lead "
              "sung behind the beat, vibes, voices, printed through tape, closing on the Rhodes."),
    "overrides": {"bpm": BPM, "swing": 0.5, "drums": "grid", "grid": PROGRAMS, "arrangement": ARR, "drum_cycle_per_block": True, "loop_continuous": True,
                  "master": {**LT.B.MASTER, "hp": 25, "mono_below": 120, "glue": {},
                             "tape": {"drive": 1.7, "bias": 0.07, "bump_db": 1.6, "hf_db": -1.2, "lp_hz": 16500, "hiss_db": -73, "wow_ms": 0.07},
                             "eq": [["peak", 180, 1.0, 0.7], ["peak", 400, -0.8, 1.0], ["peak", 1500, 1.0, 0.7], ["peak", 5000, -0.8, 1.0]],
                             "multiband": {"freqs": [150, 5000], "bands": [{"threshold_rel": -3, "ratio": 2.5, "attack": 0.03, "release": 0.15},
                                                                           {"threshold_rel": -3, "ratio": 1.6, "attack": 0.015, "release": 0.12},
                                                                           {"threshold_rel": -3, "ratio": 1.8, "attack": 0.005, "release": 0.08}]},
                             "bus_comp": {"threshold_rel": -3, "ratio": 2.0, "attack": 0.03, "release": 0.2, "sc_hp": 100},
                             "target_lufs": -9.6, "ceiling": -1.0, "clip": 0.9, "true_peak": -1.0},   # a softer clip: less crackle on the hits
                  # m9 / maj7 only: wider colours than the pad's five voices drop the root (see AGENT_README, pitfalls)
                  "harmony": {"rhythm": 1, "dominant": "modal", "tonic_major": "7sus4", "colors": {"m": "m9", "": "maj7", "m7": "m9", "7": "7sus4", "maj7": "maj7", "6": "6"}},
                  "melody": {"modal": True, "register": [64, 84], "max_leap": 7, "max_notes_per_bar": 4, "articulation": "legato", "phrase_bars": 4,
                             "swing": 0.58, "push_ms": 16, "humanize_ms": 12, "velocity": [0.38, 0.95]},   # long horn phrases, further behind the beat
                  # registers are before the transpose (-4): the sub sounds from D1 up
                  "bass": {"style": "pattern", "register": [30, 47],
                           "patterns": [[[0, "R", 0.7, 1.0], [3, "R", 0.2, 0.7], [6, "5", 0.45, 0.85], [8, "O", 0.45, 0.85], [11, "R", 0.45, 0.9], [14, "5", 0.4, 0.8]],
                                        [[0, "R", 1.5, 1.0], [7, "O", 0.25, 0.8], [8, "5", 0.7, 0.85], [12, "R", 0.5, 0.9]],
                                        [[0, "R", 0.45, 1.0], [2, "R", 0.2, 0.7], [4, "3", 0.45, 0.8], [8, "5", 0.7, 0.85], [12, "7", 0.25, 0.75], [14, "O", 0.4, 0.8]],
                                        [[0, "R", 2.2, 1.0], [11, "5", 0.25, 0.8], [12, "O", 0.5, 0.85], [14, "5", 0.25, 0.75], [15, "3", 0.25, 0.7]]]},
                  "bass2": {"style": "pattern", "register": [30, 47],
                            "patterns": [[[0, "R", 3.5, 0.9]], [[0, "R", 2.0, 0.9], [10, "5", 1.0, 0.75]]]},
                  "comp": {"steps": [0, 3, 6, 10, 13], "low": 53, "high": 72, "top": 69, "notes": 4, "gate": 0.95, "strum_ms": 24, "swing": 0.58, "push_ms": 12,
                           "humanize_ms": 12, "vel": 0.44, "accent": 0.66},                      # soft Rhodes, behind the beat
                  "vox": {"steps": [0], "low": 60, "high": 77, "top": 72, "notes": 3, "gate": 3.8, "vel": 0.5, "accent": 0.5},
                  "pad": {"low": 50, "high": 79, "top": 74, "notes": 5, "vel": 0.5}},
    "kit_def": J.kit(),
    "layers": [("bass", "bass_mid")],
    "sends": {"slap": {"type": "delay", "time_beats": 0.75, "feedback": 0.35, "taps": 3, "tone": 2800},
              "plate": {"type": "reverb", "seconds": 4.2, "predelay": 0.035, "damp": 0.6}},
    "voices": {
        "pad": ({"zyn": "Collection/0066-Hollow Ice Field.xiz"}, "Hollow Ice Field (ZynAddSubFX - Collection), the cold wash",
                dict(hp=150, width=0.7, eq=[["peak", 2500, 1.0, 0.8], ["highshelf", 3500, 3.0]], crush=J.SAMPLER(32000, 0.5),
                     sends={"plate": 0.5}, gain_db=-9.0)),
        "vox": ({"zyn": "Collection/0116-Far Space Voice.xiz"}, "Far Space Voice (ZynAddSubFX - Collection), the voices",
                dict(hp=300, lp=9000, width=0.75, crush=J.SAMPLER(26040, 0.5), sends={"plate": 0.6}, gain_db=-14.0)),
        "lead_hi": ({"zyn": "Collection/0002-Vibraphone.xiz"}, "Vibraphone (ZynAddSubFX - Collection), the high motif",
                    dict(hp=400, width=0.8, crush=J.SAMPLER(26040, 0.4), sends={"slap": 0.4, "plate": 0.5}, gain_db=-13.0)),
        "lead": ({"zyn": "Collection/0098-Wet Brass.xiz"}, "Wet Brass (ZynAddSubFX - Collection), the muted horn lead",
                 dict(hp=220, lp=7000, width=0.5, crush=J.SAMPLER(26040, 0.35), sends={"slap": 0.35, "plate": 0.45}, gain_db=-8.0)),
        "comp": ({"zyn": "Rhodes/0041-Soft Rhodes.xiz"}, "Soft Rhodes (ZynAddSubFX - Rhodes), chords",
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
        {"type": "lowpass", "tracks": ["comp"], "points": [[1, 900], [9, 2500], [INTRO + 1, 12000]]},             # the Rhodes opens first
        {"type": "lowpass", "tracks": ["pad"], "points": [[1, 500], [9, 800], [INTRO + 1, 1200], [INTRO + 9, 3000], [INTRO + 17, 12000]]},
        {"type": "lowpass", "tracks": ["break3"], "points": [[INTRO + 1, 300], [INTRO + 5, 1200], [INTRO + 8, 18000]]},   # the cowbells rise out of the filter
        {"type": "lowpass", "tracks": ["pad"], "points": [[at("Breakdown"), 2000], [at("Breakdown: hats"), 3500], [at("Exchange"), 12000]]},
        {"type": "lowpass", "tracks": ["break", "break2", "break3"], "points": [[at("Exchange"), 600], [at("Exchange") + 4, 2500], [DROP, 18000]]},
        {"type": "lowpass", "tracks": ["pad"], "points": [[at("Half-time"), 2500], [at("Half-time") + 8, 5000], [at("Final groove"), 12000]]},
        {"type": "lowpass", "tracks": ["break3"], "points": [[at("Outro: cowbells"), 18000], [at("Outro: cowbells") + 4, 1500], [at("Last light"), 300]]}],   # and sink back in
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
    res.append((f"bars 1-{INTRO}: Rhodes and strings, no drums", not any(b in per_bar for b in range(1, INTRO + 1)) and INTRO + 1 in per_bar, ""))
    res.append((f"bars {INTRO + 1}-{INTRO + 7}: the cowbell break alone", all(kind(b) == {"c"} for b in range(INTRO + 1, INTRO + 8)), ""))
    lost = sum(1 for v in per_bar.values() for _, n in v if not isinstance(n, str))
    res.append(("every drum note names a kit sound (none clipped at MIDI's 127)", lost == 0, f"{lost} undecoded notes"))
    VOX = {"z14", "z15", "z42", "z43"}
    late = [b for b in per_bar if VOX & {n for _, n in per_bar[b]}]
    res.append(("break 2's voice plays (yeah, uh huh)", len(late) >= 20, f"{len(late)} bars with z14/z15/z42/z43"))
    ex = range(at("Exchange"), at("Exchange") + 7)
    traded = sum(1 for b in ex if len(kind(b)) >= 2)
    res.append(("the exchange trades the breaks inside the bar", traded >= 6 and set().union(*(kind(b) for b in ex)) == {"s", "z", "c"},
                f"{traded}/7 bars with two or more breaks"))
    mid = [sigs.get(b) for b in ex]
    res.append(("the exchange is edited bar by bar, not looped", all(mid) and len(set(mid)) == 7, f"{len(set(mid))} distinct of 7 bars"))
    c_bars = sum(1 for b in per_bar if "c" in kind(b))
    res.append(("the cowbells run through the track", c_bars >= 40, f"{c_bars} bars"))
    distinct = len(set(sigs.values()))
    res.append(("drum bars are varied (distinct bar patterns)", distinct >= 15, f"{distinct} distinct patterns over {len(sigs)} drum bars"))
    fills = [sigs.get(b) for b in FILL_BARS]
    res.append(("every fill bar is its own edit", len(set(fills)) == len(fills), f"{len(set(fills))} distinct fills over {len(fills)} fill bars"))
    blocks = [tuple(sigs.get(b) for b in range(s, s + 7)) for s in range(INTRO + 1, TOTAL - 7, 8) if all(b in sigs for b in range(s, s + 7))]
    res.append(("8-bar groove blocks are not copies of each other", len(set(blocks)) >= len(blocks) // 2, f"{len(set(blocks))} distinct of {len(blocks)}"))
    res.append((f"bar {SUBTRACT} subtracts the drums before the final return", SUBTRACT not in per_bar and SUBTRACT + 1 in per_bar, ""))
    last = at("Last light")
    res.append((f"bars {last}-{TOTAL}: the Rhodes close it, no drums", not any(b in per_bar for b in range(last, TOTAL + 1))
                and any(n["track"] == "comp" and bar_of(n["start"]) >= last for n in notes), ""))
    harm = [n for n in notes if n["track"] in ("pad", "comp", "bass", "bass2", "vox", "lead", "lead_hi")]
    out_key = sum(1 for n in harm if n["pitch"] % 12 not in KEY_PCS)
    res.append(("harmony is in F minor (transposed skeleton)", out_key <= 0.02 * len(harm), f"{out_key}/{len(harm)} notes outside F natural minor"))
    names = [x[1] for v in per_bar.values() for x in v]
    for label, test in (("32nd pickups", lambda s: str(s).startswith(("t", "zt"))), ("pitched slices", lambda s: s in PITCHED),
                        ("extra ghost one-shots", lambda s: s in ("gh1", "zs1")), ("extra kicks", lambda s: s in ("kick1", "zk1")),
                        ("kick reinforcement", lambda s: s == "kreinf"), ("snare layer", lambda s: s == "snlay"), ("hats-only take", lambda s: str(s).startswith("h"))):
        c = sum(1 for s in names if test(s))
        res.append((f"break uses {label}", c > 0, f"{c} hits"))
    ht = [b for b in range(at("Half-time"), SUBTRACT) if b in per_bar]
    snares = {f"z{16 * k + 4:02d}" for k in range(4)}
    on8 = sum(1 for b in ht if any(s == 8.0 and str(n) in snares for s, n in per_bar[b]))
    res.append(("half-time passage on break 2: its snare moves to beat 3", ht and on8 >= len(ht) - 1, f"{on8}/{len(ht)} bars"))
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
    for a, b, name in SECTIONS + [(INTRO + 1, INTRO + 7, "cowbells alone")]:   # the last row: the cowbell bars without fill CF
        i0, i1 = int(((a - 1) * 4 + 1) * beat * SR), int(b * 4 * beat * SR) - int(0.01 * SR)   # the next bar's 5 ms leads stay out
        rows.append((a, b, name, round(meter.integrated_loudness(master[i0:i1]), 1), {s: round(lvl(x[i0:i1]), 0) for s, x in stems.items()}))
    row = {name: v for _, _, name, _, v in rows}
    ra = row["Atmosphere"]
    res.append((f"bars 1-{INTRO}: Rhodes and strings sound, nothing else", ra.get("pad", -120) > -40 and ra.get("comp", -120) > -40
                and all(v < -60 for s, v in ra.items() if s not in ("pad", "comp", "vox", "lead_hi")), f"pad {ra.get('pad')}, comp {ra.get('comp')}"))
    r0 = row["cowbells alone"]
    res.append(("the cowbells under the pads, no other break", r0.get("break3", -120) > -45 and r0.get("break", -120) < -60 and r0.get("break2", -120) < -60,
                f"break3 {r0.get('break3')}"))
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
