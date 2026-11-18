"""Handshake: a 1995-97 dark drum & bass track at 160 bpm in G minor, after Source Direct's Modem (Odysee to Anywhere).

The break pipeline is Haze Theory's (bountiful/jungle174.py), with its kit and layer programs, on three real breaks: the
Amen (s..), break2 (z.., a funk break near 114 bpm, a quiet layer here) and break6 (c.., breaks/break6.wav, one crisp bar at
160 bpm: it plays at its own tempo, no pitch). They are sampled on the 12-bit sampler into their own folder
(samples/breaks/handshake160). What is taken from Modem: the tempo, the key and its two-chord sub (G, then C), the shape
(two minutes of the beat and the sub before anything moves), a two-step kick on 1 and the and of 3, off-beat hats, the
Amen pulled back under a tighter break, very little harmony. The track: 32 bars of a dark drone, glass voices and a
space choir; break6 rising out of a low-pass with no sub; the sub arrives; a 64-bar roller on G and C; a breakdown on
B-flat; the sub pulled out while the drums carry on; the second drop; a DJ outro of beat alone.

    python -I bountiful/handshake.py              # sample the breaks (if needed), compose, render, master, validate
    python -I bountiful/handshake.py --validate   # the checks only, on the last render
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

os.environ.setdefault("BOUNTIFUL_BREAK_BPM", "160")   # Modem's tempo (159.6 measured)
os.environ.setdefault("BOUNTIFUL_BREAK_CRUSH", "0.7")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jungle174 as J   # noqa: E402  (the break pipeline, the kit and the layer programs)
import night_signal as NS   # noqa: E402  (its layer programs; importing it builds nothing)

J.BREAK2_SRC = J.ROOT / "breaks" / "break2.wav"
J.BREAK3_SRC = J.ROOT / "breaks" / "break6.wav"
J.OUT = J.ROOT / "samples" / "breaks" / f"handshake{J.BPM}"
_sample_break = J.sample_break
# break6 is a 160 bpm bar, outside the c slot's tempo-fit range (95-125): fit it near its own tempo
J.sample_break = lambda p, lo, hi: _sample_break(p, 140, 180) if Path(p).name == "break6.wav" else _sample_break(p, lo, hi)

LT, ROOT, BPM, SR, NOTES, PITCHED, sound_of = J.LT, J.ROOT, J.BPM, J.SR, J.NOTES, J.PITCHED, J.sound_of
base, swap, zb, cb = J.base, J.swap, J.zb, NS.cb
TITLE, SLUG = "Handshake", "handshake"
TRANSPOSE = -5                                     # C minor skeleton -> G minor
KEY_PCS = {7, 9, 10, 0, 2, 3, 5}                   # G natural minor


# ---------------------------------------------------------------- edits
# break6 (c..): one bar, kick on 1 only, snare on 2 and 4, busy hats. two(): its kick slice copied onto the and of 3,
# the two-step under Modem.
def two(b, kicks=(10,), vel=1.0, extra=()):
    bar = cb(b, vel=vel)
    for k in kicks:
        bar = swap(bar, k, [k, 0.95 * vel, f"c{16 * b:02d}"])
    return bar + list(extra)


SD = {"a": two(0), "b": two(1, extra=[[7, 0.22, "gh1", 3]]), "c": two(2, (10, 11)), "d": two(3, extra=[[15.5, 0.6, "t12"]])}
SD2 = {"a": two(0, extra=[[3, 0.3, "h03"]]),
       "b": swap(two(1, (6, 10)), 13, [13, 0.5, "s09u"]),                                          # a kick pushed onto 6
       "c": two(2, extra=[[14.5, 0.5, "t12"]]),
       "d": [e for e in two(3) if e[0] < 12] + [[12 + i, 0.95, f"c{56 + i:02d}"] for i in range(4)]}   # beat 4 re-cut from beat 3


# AR: the Amen as a two-step, its second kick and the kick after beat 3 swapped for the hats take
def ar(b, extra=()):
    return [e for e in base(b) if e[0] not in (2, 11)] + [[2, 0.5, "h02"], [11, 0.45, "h11"]] + list(extra)


AR = {"a": ar(0), "b": ar(1, [[6, 0.25, "gh1", 3]]), "c": ar(2), "d": ar(3, [[15.5, 0.6, "t12"]])}
Aq = {k: [[e[0], 0.4, *e[2:]] for e in ar(i)] for i, k in enumerate("abcd")}   # the Amen, quiet, under break6
s_ = lambda b, steps: [[i, 1.0, f"s{16 * b + i:02d}"] for i in steps]
# fills: a half bar from one break, then a turn; every head/tail pair is its own fill
HEADS = [cb(0, range(8)), s_(0, range(8)), zb(2, range(8)), cb(2, range(4)) + s_(1, range(4, 8))]
TAILS = [[[8, 0.9, "c00"], [10, 0.7, "c04"], [11, 0.6, "c09"], [12, 1.0, "c12"], [13, 0.6, "t12"], [14, 0.85, "s04u"], [15, 0.95, "c12"], [15.5, 0.8, "t04"]],
         [[8 + i / 2, 0.35 + 0.04 * i, ("t12", "t04")[i % 2]] for i in range(14)] + [[15, 0.95, "s04u"], [15.5, 1.0, "s12u"]],   # a 32nd roll
         [[12, 0.5, "gh1"], [14, 0.8, "c12"], [15, 0.9, "s04u"]],                                                               # half a bar of air
         s_(3, range(8, 16)),                                                                                                   # the Amen's last half bar
         [[8, 0.9, "s12d"], [9, 0.4, "gh1", -3], [10, 0.9, "c04"], [12, 1.0, "s12"], [13, 0.7, "c12"], [14, 0.8, "s09u"], [15, 1.0, "s04u"]],
         [[8, 0.95, "c00"], [9, 0.6, "c01"], [11, 0.9, "c00"], [12, 1.0, "c04"], [14, 0.7, "kick1"], [15, 0.85, "t12"], [15.5, 1.0, "c12"]]]
PAIRS = sorted(((h, t) for h in range(4) for t in range(6)), key=lambda p: ((p[0] * 7 + p[1] * 5) % 24))
F = {f"FX{k}": HEADS[h] + TAILS[t] for k, (h, t) in enumerate(PAIRS)}
F["PU"] = [[8, 0.3, "gh1", 3], [10, 0.35, "gh1", -2], [12, 0.8, "c12"], [13, 0.4, "gh1"], [14, 0.6, "t12"], [14.5, 0.75, "t12"], [15, 0.85, "s04u"], [15.5, 1.0, "s04u"]]
PROGRAMS = {**{k: NS.PROGRAMS[k] for k in ("TL", "hats", "hatsq", "ride", "rz", "kr", "sl")},
            "oh": [[i, 0.6 if i % 4 == 3 else 0.5, f"h{i:02d}"] for i in range(1, 16, 2)],   # the off-beat hats
            "k2": [[0, 0.9, "kreinf"], [10, 0.8, "kreinf"]],                                 # the two-step kick, reinforced
            "SD": SD, "SD2": SD2, "AR": AR, "Aq": Aq, **F}
_fills = iter(f"FX{k}" for k in range(len(PAIRS)))
nf = lambda n: [next(_fills) for _ in range(n)]


def groove(name, loop, parts, breaks, extra=("k2", "sl"), restart=False):
    return J.groove(name, loop, parts, breaks, nf(len(breaks)), extra=extra, restart=restart)


# ---------------------------------------------------------------- arrangement (240 bars, 6:00)
blk = J.blk
INTRO = 32      # 48 s before the first break: the drone, glass voices, the choir
FULL = ["pad", "bass", "lead", "comp", "vox", "lead_hi"]
ROLL = ["pad", "bass", "comp", "lead_hi"]
ARR = ([blk("Opening: the drone", "V", 8, ["pad"], vel={"pad": 0.7}),
        blk("Opening: glass", "V", 8, ["pad", "lead_hi"], vel={"pad": 0.75, "lead_hi": 0.6}),
        blk("Opening: the choir", "B", 8, ["pad", "vox", "lead_hi"], vel={"pad": 0.8, "vox": 0.7, "lead_hi": 0.65}),
        blk("Opening: the stabs", "B", 8, ["pad", "vox", "lead_hi", "comp"], vel={"pad": 0.8, "vox": 0.75, "comp": 0.6})]
       + groove("Breaks out of the filter", "V", ["pad", "vox", "lead_hi"], [["SD"], ["SD", "oh"]], extra=("k2",), restart=True)
       + groove("The sub arrives", "A", ["pad", "bass2", "lead_hi", "comp"], [["SD", "Aq"], ["AR", "oh"], ["SD2", "TL"], ["SD", "Aq", "oh"]], restart=True)
       + groove("Main roller", "V", ROLL, [["SD", "Aq"], ["SD2", "oh"], ["AR", "TL"], ["SD", "Aq", "oh"]], restart=True)
       + groove("Main roller: the drips", "V", ["pad", "bass", "comp", "lead"], [["SD2", "Aq"], ["AR", "oh"], ["SD", "TL"], ["SD2", "Aq", "oh"]])
       + [blk("Breakdown", "B", 8, ["pad", "vox", "lead"], vel={"pad": 0.8, "vox": 0.75, "lead": 0.7}),            # no sub: the valley
          blk("Breakdown: hats", "B", 8, ["pad", "vox", "lead_hi", "bass2"], ["hatsq"], vel={"pad": 0.8, "vox": 0.75, "bass2": 0.45})]
       # the sub pulled out: the drums carry on under the pads, then a bar of nothing, a pickup
       + groove("Sub out", "V", ["pad", "lead_hi"], [["SD", "oh"]], extra=("k2",), restart=True)
       + [blk("Sub out: no fill", "V", 6, ["pad", "lead_hi", "vox"], ["SD2", "rz"]),
          blk("Sub out: subtraction", "V", 1, ["pad", "vox"]),
          blk("Sub out: pickup", "V", 1, ["pad", "bass2"], ["PU"])]
       + groove("Second drop", "A", FULL, [["SD", "Aq", "oh"], ["AR", "TL"], ["SD2", "Aq"], ["SD", "oh", "rz"]], restart=True)
       + groove("Outro", "V", ["pad", "bass2"], [["SD2", "oh"], ["AR", "ride"]], restart=True)
       + [blk("DJ outro", "V", 8, [], ["SD", "oh", "k2"]), blk("DJ outro: pulled out", "V", 8, [], ["SD2", "k2"])])
for b_ in ARR:
    b_["transpose"] = TRANSPOSE
TOTAL = sum(x["bars"] for x in ARR)
START = [1 + sum(x["bars"] for x in ARR[:i]) for i in range(len(ARR))]
FILL_BARS = [START[i] for i, x in enumerate(ARR) if any(d in F for d in x["drums"])]
at = lambda prefix: next(START[i] for i, x in enumerate(ARR) if x["name"].startswith(prefix))   # the first bar of a block
SECTIONS = []
for i, x in enumerate(ARR):
    nm = re.sub(r" \d+$", "", x["name"].split(":")[0])
    end = START[i] + x["bars"] - 1
    if SECTIONS and SECTIONS[-1][2] == nm:
        SECTIONS[-1] = (SECTIONS[-1][0], end, nm)
    else:
        SECTIONS.append((START[i], end, nm))
SONG = ROOT / "songs" / "ny-house-93" / "ny-house-93-1677638598.am.json"   # C minor: A: Cm9 Cm9 G Cm9, V: Cm9 Cm9 Fm9 Cm9, B: Cm9 Ebmaj7 G Cm9

SUB = copy.deepcopy(J.SUB)                          # deeper and darker than Haze Theory's: Modem lives under 60 Hz
SUB["layers"][0]["preset"] |= {"sub_decay": 4.0, "body": 0.12}
SUB["layers"][1]["preset"] |= {"cutoff": 120, "resonance": 0.4, "env_amount": 900, "filter_decay": 0.25}
SUB["eq"] = [["peak", 55, 1.5, 0.9], ["peak", 250, -2.0, 1.0]]

ROLLER, BREAKDOWN, SUBOUT, DROP, DJ = at("Main roller"), at("Breakdown"), at("Sub out"), at("Second drop"), at("DJ outro")
SUBTRACT = at("Sub out: subtraction")
ALL_DRUMS = ["break", "breakfx", "break2", "break3", "ride", "kick", "snlay"]
SPEC = {
    "title": TITLE, "song": SONG, "genre": "atmospheric-jungle-95", "rebuild": "bountiful/handshake.py",
    "composer": LT.B.COMPOSER_CREDIT, "artist": LT.B.ARTIST, "album": "", "year": 2026,
    "blurb": ("A 1995-97 dark drum & bass track at 160 bpm in G minor, after Source Direct's Modem: a crisp break at its own tempo with "
              "a two-step kick, the Amen pulled back under it and a funk break as a ghost layer, sampled on a 12-bit sampler; off-beat hats; "
              "a deep sub on G and C; a drone, glass voices, a space choir and metal drips over very little harmony; the beat rising out "
              "of a low-pass with no sub, a 64-bar roller, a breakdown on B-flat, the sub pulled out while the drums carry on, a second "
              "drop and a DJ outro of beat alone."),
    "overrides": {"bpm": BPM, "swing": 0.5, "drums": "grid", "grid": PROGRAMS, "arrangement": ARR, "drum_cycle_per_block": True, "loop_continuous": True,
                  "master": {**LT.B.MASTER, "hp": 25, "mono_below": 120, "glue": {},
                             "tape": {"drive": 1.6, "bias": 0.07, "bump_db": 1.8, "hf_db": -1.0, "lp_hz": 17000, "hiss_db": -74, "wow_ms": 0.05},
                             "eq": [["peak", 55, 0.8, 0.8], ["peak", 400, -1.0, 1.0], ["peak", 3000, 0.8, 0.7], ["peak", 6000, -0.6, 1.0]],
                             "multiband": {"freqs": [150, 5000], "bands": [{"threshold_rel": -3, "ratio": 2.5, "attack": 0.03, "release": 0.15},
                                                                           {"threshold_rel": -3, "ratio": 1.6, "attack": 0.015, "release": 0.12},
                                                                           {"threshold_rel": -3, "ratio": 1.8, "attack": 0.005, "release": 0.08}]},
                             "bus_comp": {"threshold_rel": -3, "ratio": 2.0, "attack": 0.03, "release": 0.2, "sc_hp": 100},
                             "target_lufs": -9.6, "ceiling": -1.0, "clip": 0.9, "true_peak": -1.0},
                  "harmony": {"rhythm": 1, "dominant": "modal", "colors": {"m": "m9", "": "maj9", "m7": "m9", "7": "m7", "maj7": "maj9"}},
                  "melody": {"modal": True, "register": [67, 84], "max_leap": 7, "max_notes_per_bar": 3, "articulation": "legato", "phrase_bars": 4,
                             "swing": 0.55, "push_ms": 10, "humanize_ms": 10, "velocity": [0.3, 0.85]},   # sparse metal drips
                  # registers are before the transpose (-5): the sub sounds from C1 up, G1 its home
                  "bass": {"style": "pattern", "register": [29, 46],   # long sub notes on the two-step kick: 1 and the and of 3
                           "patterns": [[[0, "R", 2.3, 1.0], [10, "R", 1.4, 0.9]],
                                        [[0, "R", 1.5, 1.0], [6, "O", 0.4, 0.75], [10, "R", 1.4, 0.9]],
                                        [[0, "R", 3.8, 1.0]],
                                        [[0, "R", 2.3, 1.0], [10, "5", 0.8, 0.85], [14, "O", 0.4, 0.75]]]},
                  "bass2": {"style": "pattern", "register": [29, 46], "patterns": [[[0, "R", 3.8, 0.9]]]},
                  "comp": {"steps": [6, 14], "low": 55, "high": 72, "top": 68, "notes": 4, "gate": 0.6, "strum_ms": 8, "swing": 0.55, "push_ms": 6,
                           "humanize_ms": 8, "vel": 0.4, "accent": 0.55},   # two dark stabs a bar, off the beat
                  "vox": {"steps": [0], "low": 57, "high": 74, "top": 69, "notes": 3, "gate": 3.8, "vel": 0.5, "accent": 0.5},
                  "pad": {"low": 48, "high": 72, "top": 67, "notes": 4, "vel": 0.5}},
    "kit_def": J.kit(),
    "layers": [("bass", "bass_mid")],
    "sends": {"slap": {"type": "delay", "time_beats": 0.75, "feedback": 0.4, "taps": 4, "tone": 2400},
              "plate": {"type": "reverb", "seconds": 6.0, "predelay": 0.04, "damp": 0.65}},
    "voices": {
        "pad": ({"zyn": "Fantasy/0001-Emptyness1.xiz"}, "Emptyness1 (ZynAddSubFX - Fantasy), the drone",
                dict(hp=120, width=0.8, eq=[["peak", 300, -1.5, 1.0], ["highshelf", 5000, -1.5]], crush=J.SAMPLER(32000, 0.5),
                     sends={"plate": 0.5}, gain_db=-9.0)),
        "vox": ({"zyn": "Fantasy/0011-Space Choir1.xiz"}, "Space Choir1 (ZynAddSubFX - Fantasy), the choir",
                dict(hp=300, lp=8000, width=0.8, crush=J.SAMPLER(26040, 0.5), sends={"plate": 0.6}, gain_db=-14.0)),
        "lead_hi": ({"zyn": "Fantasy/0014-Glass Voices.xiz"}, "Glass Voices (ZynAddSubFX - Fantasy), glass over the beat",
                    dict(hp=400, lp=9000, width=0.85, crush=J.SAMPLER(26040, 0.4), sends={"slap": 0.45, "plate": 0.55}, gain_db=-17.0)),
        "lead": ({"zyn": "Collection/0008-Metal Drips.xiz"}, "Metal Drips (ZynAddSubFX - Collection), the drips",
                 dict(hp=300, lp=8000, width=0.6, crush=J.SAMPLER(26040, 0.4), sends={"slap": 0.5, "plate": 0.45}, gain_db=-9.0)),
        "comp": ({"zyn": "Fantasy/0042-Rhodes Space1.xiz"}, "Rhodes Space1 (ZynAddSubFX - Fantasy), the stabs",
                 dict(hp=160, crush={"bits": 12, "rate": 26040, "mix": 0.4}, width=0.8, sends={"plate": 0.35, "slap": 0.25}, gain_db=-8.0)),
        "bass_mid": ({"zyn": "Bass/0003-Bass 3 _analog_.xiz"}, "Bass 3 analog (ZynAddSubFX - Bass), upper-bass growl",
                     dict(hp=160, lp=1200, mono=True, drive=1.4, duck={"depth": 0.25, "release": 0.09}, gain_db=-15.0)),
    },
    "extra_tracks": {"bass": dict(SUB, duck={"depth": 0.3, "release": 0.09}, gain_db=-14.0),
                     "bass2": dict(SUB, duck={"depth": 0.25, "release": 0.1}, gain_db=-11.5)},
    "targets": {"bass": 0.0, "bass_mid": -13.0, "pad": -12.5, "comp": -14.0, "lead": -12.0, "vox": -19.0},
    "level_ref": "break3",
    "test_bars": (DROP, DROP + 6),
    "automation": [
        {"type": "lowpass", "tracks": ["pad"], "points": [[1, 500], [9, 1000], [17, 2000], [INTRO + 1, 4000], [INTRO + 17, 9000]]},   # the drone opens slowly
        {"type": "lowpass", "tracks": ALL_DRUMS, "points": [[INTRO + 1, 500], [INTRO + 5, 1200], [INTRO + 12, 4000], [INTRO + 16, 18000]]},   # the beat out of the filter
        {"type": "lowpass", "tracks": ["pad"], "points": [[BREAKDOWN, 2500], [BREAKDOWN + 8, 4000], [SUBOUT, 9000]]},
        {"type": "highpass", "tracks": ["pad", "lead_hi"], "points": [[SUBOUT, 120], [SUBTRACT, 600], [DROP, 120]]},              # the floor thins while the sub is out
        {"type": "highpass", "tracks": ALL_DRUMS, "points": [[DJ + 8, 20], [TOTAL + 1, 2500]]}],                                  # pulled out at the end
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
    step_of = lambda t: (lambda s: s - 16 if s > 15.9 else s)(round((t / beat) % 4 * 4, 2))   # the downbeat slice leads by a few ms
    res = []
    total_bars = max(bar_of(n["start"]) for n in notes)
    res.append((f"{TOTAL} bars at {BPM} bpm", total_bars == TOTAL and abs(bpm - BPM) < 0.01, f"{total_bars} bars, {bpm:.0f} bpm, {TOTAL * 4 * beat:.1f} s"))
    res.append(("about six minutes, like Modem (6:08)", 330 <= TOTAL * 4 * beat <= 380, f"{TOTAL * 4 * beat / 60:.2f} min"))
    drums = [n for n in notes if n["track"] == "drums"]
    per_bar: dict[int, list] = {}
    for n in drums:
        per_bar.setdefault(bar_of(n["start"]), []).append((step_of(n["start"]), sound_of(n)))
    sigs = {b: tuple(sorted(v, key=str)) for b, v in per_bar.items()}
    kind = lambda b: {str(n)[0] for _, n in per_bar.get(b, []) if str(n)[:1] in "szc" and str(n)[1:3].isdigit()}
    res.append((f"a long opening: {INTRO} bars", INTRO * 4 * beat >= 45, f"{INTRO * 4 * beat:.1f} s before the first break"))
    res.append((f"bars 1-{INTRO}: drone and pads, no drums", not any(b in per_bar for b in range(1, INTRO + 1)) and INTRO + 1 in per_bar, ""))
    res.append((f"bars {INTRO + 1}-{INTRO + 7}: break6 alone", all(kind(b) == {"c"} for b in range(INTRO + 1, INTRO + 8)), ""))
    bassn = [n for n in notes if n["track"] in ("bass", "bass2")]
    first_sub = min(bar_of(n["start"]) for n in bassn)
    res.append(("no sub until the breaks have played 16 bars", first_sub == INTRO + 17, f"first sub note in bar {first_sub}"))
    lost = sum(1 for v in per_bar.values() for _, n in v if not isinstance(n, str))
    res.append(("every drum note names a kit sound (none clipped at MIDI's 127)", lost == 0, f"{lost} undecoded notes"))
    infos = [json.loads((J.OUT / f"{p}_info.json").read_text()) for p in ("z", "c")]
    res.append(("this track's breaks: break2 and break6 in the z and c slots, break6 near its own 160",
                infos[0]["source"].endswith("break2.wav") and infos[1]["source"].endswith("break6.wav") and abs(infos[1]["pitch_semitones"]) < 0.5,
                f"{Path(infos[0]['source']).name}, {Path(infos[1]['source']).name} ({infos[1]['source_bpm']} bpm, {infos[1]['pitch_semitones']:+} st)"))
    used = set().union(*(kind(b) for b in per_bar))
    res.append(("all three breaks play", used == {"s", "z", "c"}, "".join(sorted(used))))
    kicks = {f"c{16 * k:02d}" for k in range(4)} | {f"s{16 * k + i:02d}" for k in range(4) for i in (0, 10)} | {"kick1", "kreinf"}
    roll = [b for b in range(ROLLER, BREAKDOWN) if b in per_bar and b not in FILL_BARS]
    k10 = sum(1 for b in roll if any(s == 10 and n in kicks for s, n in per_bar[b]) and any(s == 0 and n in kicks for s, n in per_bar[b]))
    res.append(("the roller's two-step: a kick on 1 and the and of 3", k10 == len(roll), f"{k10}/{len(roll)} bars"))
    oh = sum(1 for b in roll if sum(1 for s, n in per_bar[b] if str(n)[:1] == "h" and int(s) % 2 == 1) >= 4)
    res.append(("off-beat hats in the roller", oh >= len(roll) // 2, f"{oh}/{len(roll)} bars"))
    distinct = len(set(sigs.values()))
    res.append(("drum bars are varied (distinct bar patterns)", distinct >= 15, f"{distinct} distinct patterns over {len(sigs)} drum bars"))
    fills = [sigs.get(b) for b in FILL_BARS]
    res.append(("every fill bar is its own edit", len(set(fills)) == len(fills), f"{len(set(fills))} distinct fills over {len(fills)} fill bars"))
    blocks = [tuple(sigs.get(b) for b in range(s, s + 7)) for s in range(INTRO + 1, TOTAL - 7, 8) if all(b in sigs for b in range(s, s + 7))]
    res.append(("8-bar groove blocks are not copies of each other", len(set(blocks)) >= len(blocks) // 2, f"{len(set(blocks))} distinct of {len(blocks)}"))
    out = range(SUBOUT, SUBTRACT)
    res.append(("the sub pulled out while the drums carry on", all(b in per_bar for b in out) and not any(bar_of(n["start"]) in out for n in bassn),
                f"bars {SUBOUT}-{SUBTRACT - 1}"))
    res.append((f"bar {SUBTRACT} subtracts the drums before the second drop", SUBTRACT not in per_bar and SUBTRACT + 1 in per_bar, ""))
    music = {"pad", "comp", "bass", "bass2", "vox", "lead", "lead_hi", "bass_mid"}
    res.append((f"bars {DJ}-{TOTAL}: a DJ outro, the beat alone", all(b in per_bar for b in range(DJ, TOTAL + 1))
                and not any(n["track"] in music and bar_of(n["start"]) >= DJ for n in notes), ""))
    harm = [n for n in notes if n["track"] in ("pad", "comp", "bass", "bass2", "vox", "lead", "lead_hi")]
    out_key = sum(1 for n in harm if n["pitch"] % 12 not in KEY_PCS)
    res.append(("harmony is in G minor (transposed skeleton)", out_key <= 0.02 * len(harm), f"{out_key}/{len(harm)} notes outside G natural minor"))
    downs = {}
    for n in (n for n in notes if n["track"] == "bass" and ROLLER <= bar_of(n["start"]) < BREAKDOWN):
        downs.setdefault(bar_of(n["start"]), min((n["start"], n["pitch"]) for n in [n]))
    dpcs = [p % 12 for b, (t, p) in sorted(downs.items())]
    res.append(("the roller's sub sits on G and C, as in Modem", set(dpcs) == {7, 0}, f"{dpcs.count(7)} bars on G, {dpcs.count(0)} on C"))
    names = [x[1] for v in per_bar.values() for x in v]
    for label, test in (("32nd pickups", lambda s: str(s).startswith(("t", "zt"))), ("pitched slices", lambda s: s in PITCHED),
                        ("extra ghost one-shots", lambda s: s in ("gh1", "zs1")), ("extra kicks", lambda s: s in ("kick1", "zk1")),
                        ("kick reinforcement", lambda s: s == "kreinf"), ("snare layer", lambda s: s == "snlay"), ("hats-only take", lambda s: str(s).startswith("h"))):
        c = sum(1 for s in names if test(s))
        res.append((f"break uses {label}", c > 0, f"{c} hits"))
    chords = [n for n in notes if n["track"] in ("pad", "comp")]
    hit = tot = 0
    for n in bassn:
        pcs = {h["pitch"] % 12 for h in chords if h["start"] <= n["start"] + 0.01 < h["end"]}
        if pcs:
            tot += 1
            pc = n["pitch"] % 12   # the pads voice m9/maj9 rootless: the root is implied by its fifth and ninth
            hit += pc in pcs or {(pc + 7) % 12, (pc + 2) % 12} <= pcs
    res.append(("bass follows the harmony (bass notes are chord tones)", tot and hit / tot >= 0.9, f"{hit}/{tot} bass notes"))
    bass_bars = {}
    for n in notes:
        if n["track"] == "bass":
            bass_bars.setdefault(bar_of(n["start"]), set()).add(n["pitch"])
    octs = sum(1 for v in bass_bars.values() if max(v) - min(v) >= 12)
    low = min(n["pitch"] for n in bassn)
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
    extra_rows = [(INTRO + 1, INTRO + 7, "break6 alone"), (SUBOUT, SUBTRACT - 1, "sub pulled out"), (DROP, DROP + 6, "drop landing")]
    for a, b, name in SECTIONS + extra_rows:
        i0, i1 = int(((a - 1) * 4 + 1) * beat * SR), int(b * 4 * beat * SR) - int(0.01 * SR)   # the next bar's 5 ms leads stay out
        rows.append((a, b, name, round(meter.integrated_loudness(master[i0:i1]), 1), {s: round(lvl(x[i0:i1]), 0) for s, x in stems.items()}))
    row = {name: v for _, _, name, _, v in rows}
    ra = row["Opening"]
    res.append((f"bars 1-{INTRO}: the opening, music only", ra.get("pad", -120) > -40
                and all(v < -60 for s, v in ra.items() if s not in ("pad", "comp", "vox", "lead_hi")), f"pad {ra.get('pad')}, lead_hi {ra.get('lead_hi')}"))
    r0 = row["break6 alone"]
    # the break stem carries the one-shots (t12, gh1) at a whisper; the Amen and break2 slices are absent (checked in the MIDI)
    res.append(("break6 under the pads, the rest 12 dB under it, no sub", r0.get("break3", -120) > -45 and r0.get("break", -120) <= r0["break3"] - 12
                and r0.get("break2", -120) < -60 and r0.get("bass", -120) < -60 and r0.get("bass2", -120) < -60,
                f"break3 {r0.get('break3')}, break {r0.get('break')}"))
    rs = row["sub pulled out"]
    res.append(("the sub is silent while it is pulled out", rs.get("bass", -120) < -60 and rs.get("bass2", -120) < -60 and rs.get("break3", -120) > -45, ""))
    loud = {name: l for a, b, name, l, _ in rows}
    for nm in ("Main roller", "Second drop"):
        contrast = loud[nm] - loud["Breakdown"]
        res.append((f"dynamic contrast between breakdown and {nm.lower()}", contrast >= 2.5, f"{contrast:.1f} LU"))
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
