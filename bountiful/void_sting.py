#!/usr/bin/env python3
"""'Your Approval': a 20-second piece for the VOID Workshop video, 120 bpm in D minor (Dm9 - Gm9 - Bbmaj9 - Dm9), ten
bars of two seconds each so the video can cut on the bar. Copper Bars' chip kit and grid (pixel_dnb.py) on a new song:
a filtered boot, a pickup fill into the drop on bar 3, a lift on bar 5, a fill into the end hit on bar 9 and a ring-out.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/void_sting.py
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import album_mezzanine_v2 as A2  # noqa: E402
import lmms_tracks as LT  # noqa: E402
import pixel_dnb as P  # noqa: E402

blk, zyn, xpf = A2.blk, A2.zyn, A2.xpf
BPM = 120
FULL = ["lead", "pad", "arp", "bass", "bass_mid"]
ARR = [blk("Boot", "A", 1, ["pad", "arp"]),
       blk("Pickup", "A", 1, ["pad", "arp", "lead"], ["hat", "FD"], lead_var="sparse"),
       blk("Drop", "A", 2, FULL, P.DR, crash=True),
       blk("Lift", "B", 1, ["lead", "comp", "pad", "bass", "bass_mid"], ["kick", "snare", "ghost", "ride", "open"], crash=True),
       blk("Lift: fill", "B", 1, ["lead", "comp", "pad", "bass", "bass_mid"], ["FC", "hat"]),
       blk("Last scene", "A", 1, FULL + ["comp"], P.DR + ["open"], crash=True),
       blk("Last scene: fill", "A", 1, FULL + ["comp"], ["FA", "hat"]),
       blk("End hit", "A", 1, ["pad", "comp", "bass"], ["kick"], crash=True),
       blk("Ring out", "A", 1, ["pad"])]
ALL = sum(b["bars"] for b in ARR)

SPEC = copy.deepcopy({k: v for k, v in P.SPEC.items() if k != "kit_def"})
SPEC.update({
    "title": "Your Approval", "song": P.ROOT / "songs" / "lofi-downtempo" / "lofi-downtempo-860401564.am.json",
    "rebuild": "bountiful/void_sting.py", "kit_def": P.chip_kit(),
    "blurb": ("A 20-second piece for the VOID Workshop video: 120 bpm in D minor (Dm9 - Gm9 - Bbmaj9 - Dm9), ten two-second bars "
              "cut to the video. Copper Bars' NES-style chip kit, a Watsyn pulse lead, plucked chip arps, superpulse pads, "
              "a chip e-piano and a rolling sub; a filtered boot, a drop on bar 3 and an end hit on bar 9."),
    "test_bars": (3, 8),
    "automation": [{"type": "lowpass", "tracks": ["arp", "pad", "choir"], "points": [[1, 500], [2, 2200], [2.9, 7000], [3, 18000]]},
                   {"type": "highpass", "tracks": ["kick", "bass", "bass_mid"], "points": [[2.5, 20], [2.95, 400], [3, 20]]},
                   {"type": "gain", "tracks": ["pad", "choir", "comp", "bass"], "points": [[10.4, 0], [ALL + 2, -24]]}],
})
SPEC["overrides"].update({"bpm": BPM, "arrangement": ARR})
SPEC["voices"].update({
    "lead": (*xpf("Watsyn/Pulse.xpf", "Watsyn pulse lead"), dict(hp=250, lp=9000, sends={"echo": 0.28, "plate": 0.2}, gain_db=-6.0)),
    "arp": (*zyn("Laba170bank/0146-PluckedWithVibTail.xiz", "PluckedWithVibTail (ZynAddSubFX - Laba170bank), arpeggios"),
            dict(hp=450, pan=0.2, sends={"echo": 0.2, "plate": 0.2}, width=1.2, gain_db=-12.0)),
    "pad": (*zyn("the_mysterious_bank/0015-superpulse.xiz", "superpulse (ZynAddSubFX - the mysterious bank)"),
            dict(hp=180, lp=6500, width=1.3, sends={"plate": 0.4}, gain_db=-10.0)),
})

if __name__ == "__main__":
    P.build_kit()
    LT.make(SPEC, log=lambda m: print(m, flush=True))
