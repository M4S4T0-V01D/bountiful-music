#!/usr/bin/env python3
"""'Hikari': 80s Japanese jazz fusion (Casiopea / T-Square school). Bountiful Music composition (genre
jp-fusion-84), LMMS instruments, the lmms_tracks recipe.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/fusion_song.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lmms_tracks as LT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def zyn(path, label):
    return {"zyn": path}, label


SPEC = {
    "title": "Hikari",
    "song": ROOT / "songs" / "jp-fusion-84" / "jp-fusion-84-1518204825.am.json",
    "genre": "jp-fusion-84",
    "rebuild": "bountiful/fusion_song.py",
    "blurb": ("A-flat major, I-IV-ii-V turnarounds with 9ths and half-bar changes: an overdriven guitar theme doubled in unison by a "
              "70s triangle synth, DX7 electric-piano comping, brass-synth hits, slap bass with pops and dead notes, a busy session "
              "kit with ghost notes and tom runs, band 'kime' unison breaks, a synth solo section, and the last chorus up a whole step to B-flat."),
    "layers": [("lead", "lead_syn")],
    "kick_gain": -4.0,
    "lead_hi_follows_lead": False,     # lead_hi is also the solo synth: its own level
    "voices": {
        "lead": (*zyn("Guitar/0001-Dist Guitar 1.xiz", "Dist Guitar 1 (ZynAddSubFX - Guitar), lead guitar"),
                 dict(hp=150, eq=[["peak", 2200, 2.0, 0.9]], chorus={"depth_ms": 2.5, "rate": 0.6, "base_ms": 10, "mix": 0.25},
                      sends={"echo": 0.16, "plate": 0.25}, gain_db=-6.0)),
        "lead_syn": (*zyn("olivers-100/0050-70s Triangle Lead.xiz", "70s Triangle Lead (ZynAddSubFX - olivers-100), unison synth"),
                     dict(hp=250, pan=0.15, sends={"plate": 0.25}, gain_db=-14.0)),
        "lead_hi": (*zyn("Laba170bank/0009-GenericLead2.xiz", "GenericLead2 (ZynAddSubFX - Laba170bank), synth solo"),
                    dict(hp=250, chorus={"depth_ms": 2.0, "rate": 0.5, "base_ms": 9, "mix": 0.25}, sends={"echo": 0.2, "plate": 0.25}, gain_db=-1.0)),   # not in the test chorus, so set by hand (+7 after measuring the solo)
        "comp": (*zyn("Rhodes/0002-DX Rhodes 2.xiz", "DX Rhodes 2 (ZynAddSubFX - Rhodes), DX7 electric piano"),
                 dict(hp=140, chorus={"depth_ms": 2.0, "rate": 0.8, "base_ms": 8, "mix": 0.35}, width=1.5, sends={"plate": 0.12}, gain_db=-8.0)),
        "vox": (*zyn("Brass/0003-Synth Brazz 1.xiz", "Synth Brazz 1 (ZynAddSubFX - Brass), brass hits"),
                dict(hp=200, width=1.3, sends={"plate": 0.2, "room": 0.1}, gain_db=-8.0)),
        "pad": (*zyn("Strings/0011-Strings Pad2.xiz", "Strings Pad2 (ZynAddSubFX - Strings)"),
                dict(hp=250, lp=8000, width=1.6, sends={"plate": 0.3}, gain_db=-16.0)),
        "bass": (*zyn("olivers-100/0018-Bass Guitar - Slap.xiz", "Bass Guitar - Slap (ZynAddSubFX - olivers-100)"),
                 dict(hp=35, eq=[["peak", 2500, 3.0, 1.0], ["peak", 250, -2.0, 1.0]], drive=1.2, mono=True, gain_db=-6.0)),
    },
    "targets": {"lead": -5.0, "lead_syn": -13.0, "lead_hi": -7.0, "comp": -10.0, "vox": -10.0, "pad": -20.0, "bass": -6.0},
}

if __name__ == "__main__":
    LT.make(SPEC, log=lambda s: print(s, flush=True))
