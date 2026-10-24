#!/usr/bin/env python3
"""'Night Stage': dark rally / drift phonk, 140 bpm, F# minor (F#m - D - Bm - A). The phonk signature, a pitched TR-808 cowbell
playing the melody (LMMS AudioFileProcessor, chromatic), written by the melody writer in its 'phonk' rhythm (tresillo 3-3-2
and 16th stutters); half-time 808 drums (kick on 1, snare and clap on 3) with hat rolls; a heavily driven 808 bass; a dark
resonant pad and evil voice chops; a louder, saturated master.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/phonk_song.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import album_mezzanine_v2 as A2  # noqa: E402
import lmms_tracks as LT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
blk, kit, zyn, calf, dm = A2.blk, A2.kit, A2.zyn, A2.calf, A2.dm
BPM = 140
DR = ["kick", "snare", "clap", "hat"]
ROLL = [[s, 0.35 + 0.03 * i, "hat"] for i, s in enumerate((12, 12.5, 13, 13.25, 13.5, 13.75, 14, 14.25, 14.5, 14.75, 15, 15.5))]

ARR = [blk("Cowbell through the haze", "A", 8, ["lead", "pad"]),
       blk("Hats and the voice", "A", 8, ["lead", "pad", "vox"], ["hat", "open", "rolls"]),
       blk("Drop", "A", 16, ["lead", "bass"], DR + ["open", "rim", "rolls"], crash=True),
       blk("Break", "V", 8, ["pad", "vox", "lead"], ["hat"], lead_var="sparse"),
       blk("Drop 2", "A", 16, ["lead", "bass", "vox"], DR + ["open", "rim", "rolls"], crash=True),
       blk("Drop 2, harder", "V", 8, ["lead", "bass", "pad"], DR + ["open", "rim", "rolls"], lead_var="lift"),
       blk("Outro", "A", 8, ["lead", "bass"], ["kick", "hat"])]
OUT = A2.bars_upto(ARR, "Outro")

SPEC = {
    "title": "Night Stage", "song": ROOT / "songs" / "phonk" / "phonk-1700957924.am.json", "genre": "ny-house-93",
    "rebuild": "bountiful/phonk_song.py", "composer": A2.COMPOSER, "artist": A2.ARTIST, "album": "", "year": A2.YEAR,
    "blurb": ("Dark rally / drift phonk, 140 bpm, F# minor F#m - D - Bm - A: a pitched TR-808 cowbell melody, half-time 808 drums with hat "
              "rolls, a heavily driven 808 bass, a dark pad and evil voice chops."),
    "overrides": {"bpm": BPM, "swing": 0.5, "drums": "grid", "arrangement": ARR, "drum_cycle_per_block": True, "loop_continuous": True,
                  "harmony": {"rhythm": 1, "dominant": "keep", "colors": {"m": "m", "m7": "m", "7": "", "maj7": "", "": ""}},
                  "melody": {"writer": "motif", "rhythm": "phonk", "register": [66, 85], "range_min": 12, "density": 0.95,
                             "articulation": "detached", "humanize_ms": 2, "velocity": [0.7, 1.0]},
                  "bass": {"style": "pattern", "register": [30, 45], "pattern": [[0, "R", 1.4, 1.0], [10, "R", 0.7, 0.9], [14, "O", 0.4, 0.8]]},
                  "vox": {"steps": [0], "low": 55, "high": 72, "top": 66, "notes": 1, "gate": 0.6, "vel": 0.7, "accent": 0.8},
                  "pad": {"low": 50, "high": 70, "top": 66, "notes": 3, "vel": 0.45},
                  "grid": {"kick": {"a": [[0, 1.0], [10, 0.9]], "b": [[0, 1.0], [3, 0.7], [10, 0.9]], "c": [[0, 1.0], [6, 0.8], [10, 0.9]],
                                    "d": [[0, 1.0], [10, 0.9], [13, 0.7], [14, 0.6]]},
                           "snare": [[8, 1.0]], "clap": [[8, 0.8]],
                           "hat": [[s, 0.6 if s % 4 == 0 else 0.45] for s in range(0, 16, 2)],
                           "open": {"a": [], "b": [[6, 0.45]], "c": [], "d": [[6, 0.45]]},
                           "rolls": {"a": [], "b": [], "c": [], "d": ROLL},
                           "rim": {"a": [[7, 0.4]], "b": [], "c": [[15, 0.4]], "d": []}}},
    "kit_def": kit({"kick": (dm("tr808/kicklong"), "kick", {"gate": 0.45}), "snare": (dm("tr808/snr_snap"), "break", None),
                    "clap": (dm("tr808/handclap"), "break", None), "hat": (dm("tr808/hat_c"), "hats", {"gate": 0.06}),
                    "open": (dm("tr808/hat_o"), "hats", {"gate": 0.2}),
                    "rim": (dm("tr808/rimshot"), "perc", None), "crash": ("/usr/share/lmms/samples/drums/crash02.ogg", "hats", {"gate": 0.6})},
                   {"kick": {"hp": 28, "mono": True, "drive": 2.0, "gain_db": -2.0},
                    "break": {"hp": 150, "drive": 1.6, "crush": {"bits": 12, "rate": 26040, "mix": 0.4}, "sends": {"room": 0.12}, "gain_db": -4.0},
                    "hats": {"hp": 400, "pan": 0.2, "gain_db": 2.0}, "perc": {"pan": -0.3, "sends": {"room": 0.2}, "gain_db": -8.0}}),
    "layers": [],
    "voices": {
        # the 808 cowbell retuned -0.19 st so its lower partial sits exactly on the note (samples/phonk, measured: 560.5 Hz = midi 73.19)
        "lead": ({"sample": str(ROOT / "samples" / "phonk" / "cowbell808_tuned.wav"), "root": 73, "vol": 100}, "TR-808 cowbell, tuned and pitched (LMMS AudioFileProcessor)",
                 dict(hp=300, drive=1.6, crush={"bits": 12, "rate": 26040, "mix": 0.3}, sends={"echo": 0.15, "plate": 0.12}, width=1.0, gain_db=-4.0)),
        "bass": (*calf("Monosynth", "Boom Bass"), dict(hp=28, lp=3500, drive=3.5, mono=True, gain_db=-4.0)),
        "pad": (*zyn("Pads/0009-Resonance Pad2.xiz", "Resonance Pad2 (ZynAddSubFX - Pads), dark"), dict(hp=200, lp=3500, width=0.7, sends={"plate": 0.4}, gain_db=-6.0)),
        "vox": (*zyn("ChoirAndVoice/0038-HellVoice.xiz", "HellVoice (ZynAddSubFX - ChoirAndVoice), chops"), dict(hp=250, drive=1.4, sends={"echo": 0.35, "plate": 0.3}, width=0.8, gain_db=-13.5))},
    "targets": {"bass": -4.0, "lead": -8.0, "pad": -17.0, "vox": -18.0},
    "level_ref": "kick",
    "test_bars": (17, 24),
    "automation": [{"type": "lowpass", "tracks": ["lead"], "points": [[1, 900], [8, 5000], [8.99, 9000], [9, 20000]]},
                   {"type": "highpass", "tracks": ["kick", "bass"], "points": [[16, 20], [16.95, 300], [17, 20]]},
                   {"type": "highpass", "tracks": ["kick", "bass", "lead"], "points": [[40, 20], [40.95, 400], [41, 20]]},
                   {"type": "lowpass", "tracks": ["lead", "bass", "kick", "hats"], "points": [[OUT + 2, 20000], [OUT + 8, 400]]}],
}
SPEC["overrides"]["master"] = {"glue": {"threshold": -16.0, "ratio": 2.5, "attack": 0.01, "release": 0.2}, "saturate": 1.3,
                               "eq": [["peak", 50, 1.0, 0.8], ["peak", 300, -1.5, 0.9], ["highshelf", 4000, 3.0], ["highshelf", 10000, 1.5]],
                               "target_lufs": -8.5, "ceiling": -1.0, "clip": 3.0, "true_peak": -1.0}

if __name__ == "__main__":
    LT.make(SPEC, log=lambda m: print(m, flush=True))
