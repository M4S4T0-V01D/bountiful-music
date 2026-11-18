#!/usr/bin/env python3
"""'Your Approval (Studio Mix)': the same MIDI as void_sting.py (the VOID Workshop video piece), played on a full
studio palette instead of the chip one: a TR-909 kit, an analog sub with a growling mid bass, a morphing supersaw lead,
a fat pad with an analog-pad layer, piano-bell arps and a soft Rhodes on the chords, each with its own effect chain
(Calf saturation and phaser in LMMS; EQ, chorus, width, sidechain ducking, plate and dotted echo in the mix), then a
master chain: tape, glue compression, mastering EQ, width, soft clip and a true-peak limiter.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/void_sting_studio.py
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import album_mezzanine_v2 as A2  # noqa: E402
import lmms_tracks as LT  # noqa: E402
import void_sting as V  # noqa: E402

zyn, xpf, kit = A2.zyn, A2.xpf, A2.kit
D909 = A2.DM / "tr909"
LM = A2.LMMS_DRUMS


def studio_kit():
    s = lambda p: str(p)
    return kit({"kick": (s(D909 / "tr909_kick.wav"), "kick", {"detune_cents": 0}),
                "snare": (s(D909 / "snare.wav"), "snare", {"detune_cents": 0}),
                "ghost": (s(D909 / "snare2.wav"), "snare", {"detune_cents": 0}),
                "hat": (s(D909 / "hat-c.wav"), "hats", {"detune_cents": 0}),
                "open": (s(D909 / "hat-o.wav"), "hats", {"detune_cents": 0}),
                "ride": (s(A2.DM / "acoustic" / "ride.wav"), "ride", {"detune_cents": 0}),
                "crash": (s(LM / "crash01.ogg"), "ride", {"detune_cents": 0}),
                "rim": (s(LM / "rim01.ogg"), "perc", {"detune_cents": 0}),
                "tom_hi": (s(LM / "tom_hi01.ogg"), "perc", {"detune_cents": 0}),
                "tom_mid": (s(LM / "tom_mid01.ogg"), "perc", {"detune_cents": 0}),
                "tom_lo": (s(LM / "tom_low01.ogg"), "perc", {"detune_cents": 0})},
               {"kick": {"hp": 30, "mono": True, "drive": 1.25, "eq": [["peak", 60, 2.5, 1.0], ["peak", 350, -3.0, 1.2], ["peak", 4000, 2.0, 1.0]], "gain_db": -2.0},
                "snare": {"hp": 140, "eq": [["peak", 220, 2.0, 1.0], ["highshelf", 6000, 2.5]], "sends": {"room": 0.2, "plate": 0.12}, "gain_db": -4.0},
                "hats": {"hp": 4000, "pan": 0.18, "sends": {"room": 0.1}, "gain_db": -7.5},
                "ride": {"hp": 1500, "pan": -0.22, "sends": {"room": 0.15}, "gain_db": -14.0},
                "perc": {"hp": 70, "pan": -0.1, "sends": {"room": 0.2, "echo": 0.08}, "gain_db": -7.0}})


SPEC = copy.deepcopy(V.SPEC)
SPEC.update({
    "title": "Your Approval (Studio Mix)", "rebuild": "bountiful/void_sting_studio.py", "kit_def": studio_kit(),
    "blurb": ("The VOID Workshop video piece on a studio palette: the same MIDI as the chip version (120 bpm, D minor, "
              "Dm9 - Gm9 - Bbmaj9 - Dm9) with a TR-909 kit, an analog sub and growling mid bass, a morphing supersaw lead, "
              "a fat pad, piano-bell arps and a soft Rhodes, mastered with tape, glue, EQ, a soft clip and a true-peak limiter."),
    "layers": [("bass", "bass_mid"), ("pad", "choir")],
    "sends": {"echo": {"type": "delay", "time_beats": 0.75, "feedback": 0.35, "tone": 4200},
              "plate": {"type": "reverb", "seconds": 2.4, "predelay": 0.025, "damp": 0.35},
              "room": {"type": "reverb", "seconds": 0.7, "predelay": 0.008, "size": 0.45, "damp": 0.5}},
    "targets": {"lead": -6.0, "arp": -15.0, "pad": -14.0, "choir": -19.0, "comp": -12.0, "bass": -4.5, "bass_mid": -12.0},
})
SPEC["overrides"]["master"] = {
    "tape": {"drive": 1.1, "bias": 0.01, "bump_db": 0.6, "hf_db": 0.0, "lp_hz": 19500, "hiss_db": -100, "wow_ms": 0.0},
    "glue": {"threshold": -16.0, "ratio": 2.0, "attack": 0.02, "release": 0.15},
    "eq": [["hp", 24], ["lowshelf", 90, -1.5], ["peak", 280, -1.2, 0.9], ["peak", 3200, 1.0, 0.8], ["highshelf", 8500, 3.0]],
    "width": 1.12, "target_lufs": -10.5, "ceiling": -1.0, "clip": 1.5, "true_peak": -1.0}
SPEC["voices"] = {
    "lead": (*zyn("Laba170bank/0007-MorphingSuperSaw.xiz", "MorphingSuperSaw (ZynAddSubFX - Laba170bank), the lead"),
             dict(lmms_fx=[{"lv2": "calf:Saturator"}], hp=220, lp=11000, eq=[["peak", 2500, 1.5, 1.0]],
                  chorus={"depth_ms": 1.2, "rate": 0.35, "base_ms": 8, "mix": 0.2}, width=1.15,
                  sends={"echo": 0.24, "plate": 0.2}, gain_db=-6.0)),
    "arp": (*zyn("Laba170bank/0028-PianoBell.xiz", "PianoBell (ZynAddSubFX - Laba170bank), the arpeggios"),
            dict(hp=500, lp=12000, pan=0.2, width=1.35, sends={"echo": 0.22, "plate": 0.25}, gain_db=-12.0)),
    "pad": (*zyn("Laba170bank/0091-FatPad.xiz", "FatPad (ZynAddSubFX - Laba170bank), the pad"),
            dict(hp=160, lp=7500, eq=[["peak", 400, -2.0, 1.0]], width=1.45, sends={"plate": 0.4},
                 duck={"depth": 0.2, "release": 0.18}, gain_db=-10.0)),
    "choir": (*zyn("Pads/0003-Analog Pad 1.xiz", "Analog Pad 1 (ZynAddSubFX - Pads), the pad layer"),
              dict(hp=300, lp=8000, width=1.6, sends={"plate": 0.5}, duck={"depth": 0.2, "release": 0.18}, gain_db=-16.0)),
    "comp": (*zyn("Rhodes/0041-Soft Rhodes.xiz", "Soft Rhodes (ZynAddSubFX - Rhodes), the chords"),
             dict(lmms_fx=[{"lv2": "calf:Phaser"}], hp=180, eq=[["peak", 300, -1.5, 1.0]],
                  chorus={"depth_ms": 1.8, "rate": 0.45, "base_ms": 9, "mix": 0.3}, width=1.3,
                  sends={"plate": 0.22, "echo": 0.08}, gain_db=-9.0)),
    "bass": (*zyn("Bass/0003-Bass 3 _analog_.xiz", "Bass 3 analog (ZynAddSubFX - Bass), the sub"),
             dict(hp=28, lp=180, mono=True, duck={"depth": 0.35, "release": 0.1}, gain_db=-4.0)),
    "bass_mid": (*zyn("Laba170bank/0097-AnalogBass.xiz", "AnalogBass (ZynAddSubFX - Laba170bank), the mid bass"),
                 dict(lmms_fx=[{"lv2": "calf:Saturator"}], hp=140, lp=3200, drive=1.3, mono=True,
                      duck={"depth": 0.3, "release": 0.1}, gain_db=-12.0)),
}


def same_midi():
    """Play the chip version's MIDI note for note (the drum humanising would otherwise be re-rolled for the new title)."""
    import shutil
    src = V.P.ROOT / "tracks" / "your-approval" / "your-approval.mid"
    produce = LT.B.produce

    def produce_then_copy(song, g, title, out, **kw):
        r = produce(song, g, title=title, out=out, **kw)
        shutil.copy(src, Path(out) / f"{LT.B.slug(title)}.mid")
        return r
    LT.B.produce = produce_then_copy


if __name__ == "__main__":
    same_midi()
    LT.make(SPEC, log=lambda m: print(m, flush=True))
