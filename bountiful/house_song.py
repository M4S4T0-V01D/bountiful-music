#!/usr/bin/env python3
"""'Crushed Red Pepper' (formerly 'Testimony', renamed 2026-10-16 for Taste Tester): an early-90s New York house song. Bountiful Music composition (genre ny-house-93),
LMMS instruments, the lmms_tracks recipe.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/house_song.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lmms_tracks as LT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FULL = ["kick", "clap", "hat", "open", "shaker", "congas"]


def blk(name, loop, bars, parts=(), drums=(), **kw):
    return {"name": name, "loop": loop, "bars": bars, "parts": list(parts), "drums": list(drums), **kw}


ARRANGEMENT = [
    blk("Intro: kick and hats", "A", 8, drums=["kick", "hat"]),
    blk("Intro: full kit", "A", 8, drums=FULL, fill="toms"),
    blk("Organ bass", "A", 16, ["bass"], FULL, fill="toms"),
    blk("Piano", "V", 16, ["bass", "comp"], FULL, fill="toms"),
    blk("Verse: organ melody", "V", 16, ["bass", "comp", "lead"], FULL, fill="snare_roll"),
    blk("Chorus", "A", 16, ["bass", "comp", "pad", "lead", "vox"], FULL, crash=True, fill="toms"),
    blk("Lift", "B", 16, ["bass", "comp", "pad", "vox"], FULL + ["timbales"], crash=True, fill="toms"),
    blk("Breakdown", "A", 8, ["pad", "vox", "lead"]),
    blk("Build", "A", 8, ["pad", "comp", "vox"], ["hat", "shaker", "congas"], fill="roll16"),
    blk("Peak", "A", 32, ["bass", "comp", "pad", "lead", "vox"], FULL + ["timbales"], crash=True, fill="toms"),
    blk("Lift 2", "B", 16, ["bass", "comp", "pad", "lead", "vox"], FULL + ["timbales"], crash=True, fill="snare_roll"),
    blk("Last chorus", "A", 16, ["bass", "comp", "pad", "lead", "vox"], FULL, crash=True, fill="toms"),
    blk("Outro: piano and vocal", "A", 16, ["bass", "comp", "vox"], FULL),
    blk("Outro: drums", "A", 8, drums=["kick", "clap", "hat", "open"]),
]
BUILD_START = 1 + sum(b["bars"] for b in ARRANGEMENT[:8])           # first bar of the build


def zyn(path, label):
    return {"zyn": path}, label


SPEC = {
    "title": "Crushed Red Pepper",
    "song": ROOT / "songs" / "ny-house-93" / "ny-house-93-1410744044.am.json",
    "genre": "ny-house-93",
    "rebuild": "bountiful/house_song.py",
    "blurb": ("G-sharp minor, i9-iv9-VII-VImaj7: M1-style organ bass with a sub, synth-piano stabs on the 3-3-4-3-3 "
              "rhythm, 'eh' vocal stabs answering them, an organ melody with a slow Leslie, strings, 909-style drums with congas "
              "and timbales, a filter build into a 32-bar peak."),
    "overrides": {
        "bpm": 124,
        "bass": {"pattern": [[0, "R", 0.45], [3, "R", 0.2], [6, "O", 0.25], [8, "R", 0.3], [10, "O", 0.2], [11, "R", 0.2], [14, "5", 0.3]]},
        "comp": {"steps": [0, 3, 6, 10, 13], "low": 56, "high": 76, "top": 73, "notes": 4, "gate": 0.24, "humanize_ms": 4},
        "vox": {"steps": [7, 15], "low": 64, "high": 80, "top": 76, "notes": 2, "gate": 0.32, "vel": 0.72, "accent": 0.8, "humanize_ms": 5},
        "pad": {"low": 55, "high": 79, "top": 76, "notes": 4, "vel": 0.5},
        "arrangement": ARRANGEMENT,
    },
    "layers": [("bass", "bass_sub")],
    "voices": {
        "bass": (*zyn("Organ/0002-Organ 2.xiz", "Organ 2 (ZynAddSubFX / Organ), the M1-style organ bass"),
                 dict(hp=38, lp=3200, drive=1.3, eq=[["peak", 900, 2.0, 1.0]], mono=True, duck={"depth": 0.3, "release": 0.1}, gain_db=-6.0)),
        "bass_sub": (*zyn("Bass/0003-Bass 3 _analog_.xiz", "Bass 3 analog (ZynAddSubFX / Bass), an octave below"),
                     dict(transpose=-12, hp=28, lp=150, mono=True, duck={"depth": 0.35, "release": 0.1}, gain_db=-12.0)),
        "comp": (*zyn("Cormi_Sound/0065-Synth_piano_03.xiz", "Synth_piano_03 (ZynAddSubFX / Cormi_Sound)"),
                 dict(hp=150, eq=[["peak", 300, -3.0, 1.0], ["peak", 2800, 2.5, 0.8]], chorus={"depth_ms": 1.8, "rate": 0.4, "base_ms": 9, "mix": 0.25},
                      width=1.5, sends={"room": 0.2, "plate": 0.08}, duck={"depth": 0.15, "release": 0.12}, gain_db=-6.0)),
        "lead": (*zyn("Collection/0055-Percussion Organ.xiz", "Percussion Organ (ZynAddSubFX / Collection)"),
                 dict(hp=180, leslie={"speed": [[1, 0]], "crossover": 800, "mix": 0.6}, sends={"plate": 0.22, "echo": 0.12}, gain_db=-6.0)),
        "pad": (*zyn("Strings/0011-Strings Pad2.xiz", "Strings Pad2 (ZynAddSubFX / Strings)"),
                dict(hp=250, lp=7000, width=1.6, sends={"plate": 0.35}, duck={"depth": 0.25, "release": 0.15}, gain_db=-14.0)),
        "vox": (*zyn("ChoirAndVoice/0003-EHH Choir 1.xiz", "EHH Choir 1 (ZynAddSubFX / ChoirAndVoice), vocal stabs"),
                dict(hp=300, width=1.3, sends={"plate": 0.3, "echo": 0.2}, duck={"depth": 0.15, "release": 0.12}, gain_db=-8.0)),
    },
    "targets": {"bass": -7.0, "bass_sub": -17.0, "comp": -7.0, "lead": -8.0, "pad": -18.0, "vox": -11.0},
    "automation": [{"type": "lowpass", "tracks": ["comp", "pad", "vox"], "points": [[BUILD_START, 350], [BUILD_START + 4, 1200], [BUILD_START + 8, 18000]]}],
}

if __name__ == "__main__":
    LT.make(SPEC, log=lambda s: print(s, flush=True))
