#!/usr/bin/env python3
"""'Service Elevator': a companion to Pepperoni, in its aesthetic as the user left it in their edit of
tracks/pepperoni/pepperoni.mmp: breakbeat house with no four-to-the-floor, the same 12-bit acoustic kit with
TR-808 clap and cowbell, Calf Organ 'Std Jimmy' stabs, the dingy Funky Reso Bass through Calf Saturator over a sub,
vocal-morph chops, Synth Brazz and Saw Strings. The balance follows the user's mix, measured from its stems against the
kick: hats and percussion well forward, snare above the kick, the pad up, the bass, stabs and chops behind the drums.
Its own key (E minor), tempo (118), beat, opening and arrangement.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/lobby_sequel.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import album_mezzanine_v2 as A2  # noqa: E402
import lmms_tracks as LT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
blk, kit, zyn, calf, sub, dm, LMMS_DRUMS = A2.blk, A2.kit, A2.zyn, A2.calf, A2.sub, A2.dm, A2.LMMS_DRUMS
DR = ["kick", "snare", "ghost", "hat"]
GATE = {"gate": 10 / 48 * 60 / 118}       # 10 ticks at 118 bpm

# opens on percussion (Pepperoni opens on the break): hats, open hat, cowbell and clap, then the break drops in under them
ARR = [blk("Percussion", "A", 4, [], ["hat", "open", "cowbell", "clap"]),
       blk("The break drops in", "A", 4, [], DR + ["open", "cowbell", "clap"]),
       blk("Organ", "A", 16, ["stab", "bass"], DR + ["open", "cowbell"]),
       blk("Chops", "V", 16, ["stab", "bass", "vox"], DR + ["open", "clap", "cowbell"]),
       blk("Hook", "A", 16, ["stab", "bass", "vox", "lead", "pad"], DR + ["open", "clap", "cowbell", "tamb"], crash=True),
       blk("Between floors", "B", 4, ["pad", "vox"], ["hat", "cowbell"]),
       blk("Break and bass", "B", 4, ["bass"], DR + ["open"]),
       blk("Second hook", "V", 16, ["stab", "bass", "vox", "pad"], DR + ["open", "clap", "cowbell"], crash=True),
       blk("Hook again", "A", 16, ["stab", "bass", "vox", "lead", "pad"], DR + ["open", "clap", "cowbell", "tamb"], crash=True),
       blk("Outro", "A", 8, ["stab"], DR + ["open", "cowbell"]),
       blk("Outro: percussion", "A", 4, [], ["hat", "open", "cowbell", "clap"])]

SPEC = {
    "title": "Service Elevator", "song": ROOT / "songs" / "lobby2" / "lobby2-769490674.am.json", "genre": "ny-house-93",
    "rebuild": "bountiful/lobby_sequel.py", "composer": A2.COMPOSER, "artist": A2.ARTIST, "album": "", "year": A2.YEAR,
    "blurb": ("A companion to Pepperoni in its sound: breakbeat house, no four-to-the-floor, a chopped 12-bit acoustic kit with ghost notes, "
              "TR-808 clap and cowbell up front, E minor Em9 - Am9 - B7, Calf Organ 'Std Jimmy' stabs, the dingy Funky Reso Bass, "
              "vocal-morph chops, Synth Brazz and Saw Strings; mixed to the balance of the user's own Pepperoni edit."),
    "overrides": {"bpm": 118, "swing": 0.56, "drums": "grid", "arrangement": ARR, "drum_cycle_per_block": True, "loop_continuous": True,
                  "harmony": {"rhythm": 1, "dominant": "keep", "colors": {"m": "m9", "m7": "m9", "7": "7"}},
                  "melody": {"register": [64, 84], "max_leap": 7, "max_notes_per_bar": 6, "articulation": "detached", "humanize_ms": 6, "velocity": [0.65, 0.92]},
                  "bass": {"style": "pattern", "register": [38, 55],          # E2 roots: Pepperoni's B1 weight, not E1 sub rumble
                          
                           "pattern": [[0, "R", 0.25, 1.0], [2, "O", 0.15, 0.7], [5, "R", 0.2, 0.8], [8, "R", 0.3, 0.9], [11, "5", 0.2, 0.75], [13, "R", 0.15, 0.7], [14, "O", 0.25, 0.85]]},
                  "stab": {"steps": [0, 3, 10], "low": 57, "high": 77, "top": 74, "notes": 4, "gate": 0.22, "vel": 0.78, "accent": 0.9},
                  "vox": {"steps": [6, 12, 15], "low": 62, "high": 80, "top": 74, "notes": 2, "gate": 0.2, "vel": 0.75, "accent": 0.85},
                  "pad": {"low": 55, "high": 77, "top": 74, "notes": 4, "vel": 0.48},
                  # the beat: a two-bar break that pushes the kick off the beat (Pepperoni: kick 1, 7, 11); four bars cycle per block
                  "grid": {"kick": {"a": [[0, 1.0], [7, 0.8], [10, 0.9]], "b": [[0, 1.0], [3, 0.7], [10, 0.85], [15, 0.55]],
                                    "c": [[0, 1.0], [7, 0.8], [10, 0.9]], "d": [[2, 0.9], [7, 0.8], [11, 0.75]]},
                           "snare": {"a": [[4, 0.95], [12, 0.95]], "b": [[4, 0.95], [12, 0.95]], "c": [[4, 0.95], [12, 0.95]], "d": [[4, 0.95], [12, 0.9], [14, 0.65], [15, 0.75]]},
                           "ghost": {"a": [[6, 0.3], [9, 0.28], [14, 0.36]], "b": [[1, 0.25], [9, 0.32], [11, 0.3]], "c": [[6, 0.3], [9, 0.28], [13, 0.34]], "d": [[6, 0.3], [9, 0.3]]},
                           "hat": [[s, 0.55 if s % 4 == 0 else 0.42 if s % 2 == 0 else 0.26] for s in range(16)],
                           "open": {"a": [[14, 0.5]], "b": [[6, 0.45]], "c": [[14, 0.5]], "d": [[6, 0.45], [14, 0.5]]},
                           "clap": {"a": [], "b": [[12, 0.6]], "c": [], "d": [[12, 0.6], [15, 0.4]]},
                           "cowbell": {"a": [[3, 0.42], [11, 0.3]], "b": [[6, 0.38]], "c": [[3, 0.42], [11, 0.3]], "d": [[6, 0.38], [13, 0.3]]},
                           "tamb": [[s, 0.3 if s % 4 == 2 else 0.18] for s in range(2, 16, 2)]}},
    # every hit gated to 10 LMMS ticks, as in the Pepperoni render the user edited (the sampler stops each sample at the note's end):
    # a short, punchy kick without its sub tail, clipped snares and open hats
    "kit_def": kit({"kick": (str(LMMS_DRUMS / "bassdrum02.ogg"), "kick", GATE), "snare": (str(LMMS_DRUMS / "snare03.ogg"), "break", GATE),
                    "ghost": (str(LMMS_DRUMS / "snare05.ogg"), "break", {"gain_db": -8, "lp": 6000, **GATE}), "hat": (str(LMMS_DRUMS / "hihat_closed02.ogg"), "hats", GATE),
                    "open": (str(LMMS_DRUMS / "hihat_opened03.ogg"), "hats", GATE), "clap": (dm("tr808/handclap"), "perc", GATE),
                    "cowbell": (dm("tr808/cowbell"), "perc", GATE), "tamb": (dm("misc_perc/lo-fi_tamb"), "hats", {"gain_db": -6, **GATE}),
                    "crash": (str(LMMS_DRUMS / "crash01.ogg"), "hats", {"gate": 24 / 48 * 60 / 118})},
                   # Pepperoni's kit chain; hats +8.5 dB and percussion +10 dB, as in the user's mix
                   {"kick": {"hp": 35, "mono": True, "drive": 1.4, "crush": {"bits": 12, "rate": 26040, "mix": 0.4}, "gain_db": -3.0},
                    "break": {"hp": 90, "drive": 1.5, "crush": {"bits": 12, "rate": 26040, "mix": 0.5}, "sends": {"room": 0.15}, "gain_db": -3.2},
                    "hats": {"pan": 0.15, "crush": {"bits": 12, "rate": 26040, "mix": 0.4}, "gain_db": 0.8},
                    "perc": {"pan": -0.25, "sends": {"room": 0.2}, "gain_db": 1.4}}),
    "layers": [("bass", "bass_sub")],
    "voices": {"bass": (*zyn("olivers-100/0054-Funky Reso Bass.xiz", "Funky Reso Bass (ZynAddSubFX - olivers-100)"),
                        dict(lmms_fx=[{"lv2": "calf:Saturator"}], hp=38, lp=4500, drive=1.6, crush={"bits": 10, "rate": 18000, "mix": 0.3}, mono=True, gain_db=-6.0)),
               "bass_sub": sub(),
               "stab": (*calf("Organ", "Std Jimmy"), dict(hp=160, sends={"room": 0.2}, width=1.2, gain_db=-6.0)),
               "vox": (*zyn("ChoirAndVoice/0067-Vocal Morph 3.xiz", "Vocal Morph 3 (ZynAddSubFX - ChoirAndVoice), chops"), dict(hp=280, drive=1.3, sends={"echo": 0.2, "plate": 0.2}, gain_db=-8.0)),
               "lead": (*zyn("Brass/0004-Synth Brazz 2.xiz", "Synth Brazz 2 (ZynAddSubFX - Brass)"), dict(hp=200, sends={"plate": 0.2, "echo": 0.12}, gain_db=-7.0)),
               "pad": (*zyn("Strings/0005-Saw Strings 5.xiz", "Saw Strings 5 (ZynAddSubFX - Strings)"), dict(hp=250, width=1.5, sends={"plate": 0.3}, gain_db=-12.0))},
    # the user's Pepperoni balance vs the kick: bass -10.5, sub -16.6, stab -11.9, pad -15.1, lead -13.2 (pushed past its fader with
    # a +9 dB gain plugin, so a little more here), chops -24 (fader at its maximum, so they wanted more: -20)
    "targets": {"bass": -10.5, "bass_sub": -16.6, "stab": -12.0, "pad": -15.0, "lead": -11.5, "vox": -20.0},
    "level_ref": "kick",
}
SPEC["test_bars"] = (A2.bars_upto(ARR, "Hook"), A2.bars_upto(ARR, "Hook") + 7)
SPEC["overrides"]["master"] = {"target_lufs": -11.0, "ceiling": -1.8}     # the gated transients overshoot between samples: a lower ceiling keeps true peak under -1 dBTP

if __name__ == "__main__":
    LT.make(SPEC, log=lambda m: print(m, flush=True))
