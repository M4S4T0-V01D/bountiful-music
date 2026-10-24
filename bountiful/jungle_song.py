#!/usr/bin/env python3
"""A 1994 jungle track on our own break ('the C-Lizzy break', bountiful/break_maker.py): the break sped up to 168 on a
sampler, chopped into 16th slices mapped across keys and re-sequenced as jungle edits (straight, rolling re-orders,
snare rolls, stutters, reversed beats, half-time), an 808 boom under the drops, a dub sub bass, a Reese that only comes
in on the second drop, and Bountiful Music's composition (half-speed harmony) on LMMS pads, stabs, Rhodes and voice.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/jungle_song.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import break_maker as BM  # noqa: E402
import lmms_tracks as LT  # noqa: E402
import producer as PR  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BPM = 168
SL = BM.OUT / f"slices_{BPM}"
if not (SL / "s00.wav").exists():
    BM.make(BPM)

# the sampler: every slice on its own key (GM note numbers are free here; the drum track is this kit alone)
NOTES = {f"s{i:02d}": 24 + i for i in range(64)} | {f"rb{k:02d}": 88 + k for k in range(16)} | {f"ride{k}": 104 + k for k in range(4)} | {"boom": 108}
PR.GM.update(NOTES)
KIT = {"map": {str(n): s for s, n in NOTES.items()},
       "sounds": {**{s: {"samples": [str(SL / f"{s}.wav")], "stem": "break", "detune_cents": 0} for s in NOTES if s[0] == "s"},
                  **{s: {"samples": [str(SL / f"{s}.wav")], "stem": "reverse", "detune_cents": 0} for s in NOTES if s.startswith("rb")},
                  **{s: {"samples": [str(SL / f"{s}.wav")], "stem": "ride", "detune_cents": 0} for s in NOTES if s.startswith("ride")},
                  "boom": {"samples": [str(BM.ROOT / "samples" / "drummachines" / "tr808" / "kicklong.wav")], "stem": "boom", "detune_cents": 0, "lp": 180}},
       "stems": {"break": {"hp": 28, "eq": [["highshelf", 7000, -3.0], ["lp", 12000, 2]], "sends": {"room": 0.08}, "gain_db": -2.0},
                 "reverse": {"hp": 150, "sends": {"plate": 0.3}, "gain_db": -8.0},
                 "ride": {"hp": 400, "sends": {"room": 0.15}, "gain_db": -9.0},
                 "boom": {"mono": True, "gain_db": -8.0}}}


# ------------------------------------------------------------------ chop programs: a bar is four beats; a beat is a break beat (0-15),
# "R" a snare roll, "S" a stutter, "rev" a reversed beat, None rests (the ride layer carries it)
def bar(beats, vel=1.0):
    out = []
    for q, b in enumerate(beats):
        if b is None:
            continue
        if b == "R":
            out += [[q * 4 + r, 0.65 + 0.1 * r, "s04"] for r in range(4)]
        elif b == "S":
            out += [[q * 4 + r, 0.9, f"s{4 + r % 2:02d}"] for r in range(4)]
        elif isinstance(b, str) and b.startswith("rev"):
            out.append([q * 4, 0.85, f"rb{int(b[3:]):02d}"])
        else:
            out += [[q * 4 + r, vel, f"s{4 * b + r:02d}"] for r in range(4)]
    return out


PROGRAMS = {
    "straight": {"A": bar([0, 1, 2, 3]), "B": bar([4, 5, 6, 7]), "C": bar([8, 9, 10, 11]), "D": bar([12, 13, 14, 15])},
    "roller": {"A": bar([0, 1, 2, 3]), "B": bar([4, 5, 6, 7]), "C": bar([0, 9, 10, 11]), "D": bar([12, 13, 2, 15])},
    "edit": {"A": bar([0, 1, 2, 3]), "B": bar([4, 5, 2, "R"]), "C": bar([8, "S", 10, 11]), "D": bar([12, 13, "rev3", 15])},
    "half": {"A": bar([0, None, 1, None]), "B": bar([0, None, 1, None]), "C": bar([0, None, 1, None]), "D": bar([2, None, 5, "R"])},
    "roll": [[s, 0.45 + 0.035 * s, "s04"] for s in range(0, 16, 2)] + [[s, 0.5 + 0.03 * s, "s04"] for s in range(1, 16, 2)],
    "ride": {"A": [[0, 0.9, "ride0"]], "B": [[0, 0.9, "ride1"]], "C": [[0, 0.9, "ride2"]], "D": [[0, 0.9, "ride3"]]},
    "boom": {"A": [[0, 1.0, "boom"]], "B": [], "C": [[0, 1.0, "boom"], [10, 0.8, "boom"]], "D": []},
}


def blk(name, loop, bars, parts=(), drums=(), **kw):
    return {"name": name, "loop": loop, "bars": bars, "parts": list(parts), "drums": list(drums), **kw}


ARR = [blk("Intro: pads and ride", "A", 16, ["pad", "vox"], ["ride"]),
       blk("Intro: half-time break", "A", 16, ["pad", "vox", "lead"], ["half", "ride"]),
       blk("Snare roll", "A", 2, ["pad"], ["roll"]),
       blk("Drop", "A", 32, ["bass", "pad", "stab"], ["straight", "boom"]),
       blk("Rolling", "V", 16, ["bass", "pad", "lead", "stab"], ["roller", "boom"]),
       blk("Edits", "V", 8, ["bass", "lead"], ["edit", "boom"]),
       blk("Breakdown", "B", 16, ["pad", "vox", "lead"], ["ride"]),
       blk("Build", "B", 8, ["pad", "stab"], ["half", "ride"]),
       blk("Roll into the second drop", "B", 2, ["pad"], ["roll"]),
       blk("Second drop", "A", 16, ["bass", "pad", "stab", "lead"], ["roller", "boom"]),
       blk("Second drop: edits", "A", 8, ["bass", "pad", "stab", "lead"], ["edit", "boom"]),
       blk("Second drop: rolling", "A", 8, ["bass", "pad", "stab", "lead"], ["roller", "boom"]),
       blk("Outro", "A", 16, ["pad", "bass"], ["straight"]),
       blk("Outro: ride", "A", 8, ["pad"], ["ride"])]
SECOND_DROP = 1 + sum(b["bars"] for b in ARR[:9])
SONG = ROOT / "songs" / "jungle94" / "jungle94-531624833.am.json"

SPEC = {
    "title": "Pressure Zone", "song": SONG, "genre": "atmospheric-jungle-95", "rebuild": "bountiful/jungle_song.py",
    "composer": LT.B.COMPOSER_CREDIT, "artist": LT.B.ARTIST, "album": "", "year": 2026,
    "blurb": ("1994 jungle on our own break: the C-Lizzy break (an original funk performance in the Amen's rhythmic style) sped up to 168 "
              "and chopped across keys, played as straight runs, rolling re-orders, snare rolls, stutters, reversed beats and half-time; "
              "an 808 boom, a dub sub bass, a Reese on the second drop; D minor Dm9 - Bb6 - Am7 - C6 at half speed on LMMS pads, stabs, Rhodes and voice."),
    "overrides": {"bpm": BPM, "swing": 0.5, "drums": "grid", "grid": PROGRAMS, "arrangement": ARR, "drum_cycle_per_block": True,
                  "harmony": {"rhythm": 1, "dominant": "modal", "colors": {"m": "m9", "": "6", "m7": "m7", "7": "7sus4", "maj7": "maj9"}},
                  "melody": {"modal": True, "register": [62, 81], "max_leap": 7, "max_notes_per_bar": 3, "articulation": "legato", "humanize_ms": 6, "velocity": [0.55, 0.85]},
                  "bass": {"style": "pattern", "register": [26, 43], "pattern": [[0, "R", 2.6], [11, "5", 0.45], [14, "O", 0.7]]},
                  "stab": {"steps": [0, 10], "low": 55, "high": 74, "top": 70, "notes": 4, "gate": 0.3, "vel": 0.8, "accent": 0.85},
                  "vox": {"steps": [0], "low": 62, "high": 79, "top": 74, "notes": 2, "gate": 3.8, "vel": 0.55, "accent": 0.55},
                  "pad": {"low": 50, "high": 74, "top": 69, "notes": 4, "vel": 0.5}},
    "kit_def": KIT,
    "layers": [("bass", "reese")],
    "voices": {
        "bass": ({"zyn": "Bass/0003-Bass 3 _analog_.xiz"}, "Bass 3 analog (ZynAddSubFX - Bass), the sub",
                 dict(hp=25, lp=220, mono=True, duck={"depth": 0.2, "release": 0.1}, gain_db=-4.0)),
        "pad": ({"zyn": "Strings/0018-Sweep Pad 2.xiz"}, "Sweep Pad 2 (ZynAddSubFX - Strings)",
                dict(hp=180, width=1.0, sends={"plate": 0.4}, gain_db=-10.0)),
        "stab": ({"zyn": "Brass/0008-Brass Pad.xiz"}, "Brass Pad (ZynAddSubFX - Brass), stabs",
                 dict(hp=200, sends={"plate": 0.25, "echo": 0.2}, gain_db=-8.0)),
        "lead": ({"zyn": "Rhodes/0013-Ice Rhodes2.xiz"}, "Ice Rhodes2 (ZynAddSubFX - Rhodes)",
                 dict(hp=200, sends={"plate": 0.3, "echo": 0.25}, gain_db=-3.0)),   # not in the test bars: set by hand (+3 after measuring)
        "vox": ({"zyn": "Fantasy/0008-Space Voice1.xiz"}, "Space Voice1 (ZynAddSubFX - Fantasy)",
                dict(hp=250, width=0.9, sends={"plate": 0.5}, gain_db=-12.0)),
    },
    "targets": {"bass": -1.0, "pad": -14.0, "stab": -9.0, "lead": -7.0, "vox": -16.0},
    "test_bars": (1 + sum(b["bars"] for b in ARR[:3]), 1 + sum(b["bars"] for b in ARR[:3]) + 7),
    "automation": [{"type": "gain", "tracks": ["reese"], "points": [[1, -60], [SECOND_DROP - 0.01, -60], [SECOND_DROP, 0], [SECOND_DROP + 31.99, 0], [SECOND_DROP + 32, -60]]}],
    "drum_stems": {},
    "kick_gain": None,
    "mmp_drums": False,          # the break is an 85-key sampler: the LMMS project carries the instruments, not 85 drum tracks
    "extra_tracks": {"reese": {"kind": "reese", "preset": "reese-dingy.json", "hp": 60, "lp": 3500, "mono": True,
                               "duck": {"depth": 0.2, "release": 0.1}, "gain_db": -14.0}},
}

if __name__ == "__main__":
    LT.make(SPEC, log=lambda m: print(m, flush=True))
