#!/usr/bin/env python3
"""Two dingy, gritty early-90s house songs: Bountiful Music composition (ny-house-93), LMMS instruments,
and a dirtier chain than Crushed Red Pepper (formerly Testimony): 12-bit sampler-crunched drums (SP-1200 style), the dingy LMMS bass chain,
crushed stabs and vocal chops, a harder tape master.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/dirty_house.py [sub-basement rust]
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lmms_tracks as LT  # noqa: E402
from house_song import ARRANGEMENT, BUILD_START  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SONGS = ROOT / "songs" / "ny-house-93"


def zyn(path, label):
    return {"zyn": path}, label


def mono(preset):
    return {"lv2": "calf:Monosynth", "preset": preset}, f"{preset} (Calf Monosynth)"


SP1200 = {"bits": 12, "rate": 26040}
GRIT_DRUMS = {   # the kit through a 12-bit sampler (stems keep their gains)
    "kick": {"drive": 1.5, "crush": dict(SP1200, mix=0.5)},
    "clap": {"drive": 1.4, "crush": dict(SP1200, mix=0.7)},
    "snare": {"drive": 1.4, "crush": dict(SP1200, mix=0.7)},
    "hats": {"drive": 1.3, "crush": {"bits": 10, "rate": 22050, "mix": 0.5}},
    "perc": {"crush": dict(SP1200, mix=0.5)},
    "toms": {"crush": dict(SP1200, mix=0.5)},
}
DIRTY_TAPE = {"tape": {"drive": 1.7, "bias": 0.06, "bump_db": 1.0, "hf_db": -2.0, "lp_hz": 16000, "hiss_db": -74, "wow_ms": 0.05},
              "glue": {"threshold": -15.0, "ratio": 2.5, "attack": 0.015, "release": 0.2}, "target_lufs": -10.0, "ceiling": -1.0}


def dingy_bass(v):
    return (*v, dict(lmms_fx=[{"lv2": "calf:Saturator"}, {"lv2": "calf:Crusher"}], hp=38, lp=4500,
                     eq=[["peak", 700, 3.0, 1.0], ["peak", 250, -2.0, 1.0]], drive=2.0, crush={"bits": 9, "rate": 16000, "mix": 0.4},
                     mono=True, duck={"depth": 0.3, "release": 0.1}, gain_db=-6.0))


def sub():
    return (*zyn("Bass/0003-Bass 3 _analog_.xiz", "Bass 3 analog (ZynAddSubFX / Bass), sub"),
            dict(hp=28, lp=150, mono=True, duck={"depth": 0.35, "release": 0.1}, gain_db=-12.0))


def stabs(v, leslie=False, bits=12):
    mix = dict(lmms_fx=[{"lv2": "calf:Saturator"}], hp=160, eq=[["peak", 300, -3.0, 1.0], ["peak", 2500, 2.0, 0.8]], drive=1.4,
               crush={"bits": bits, "rate": 22050, "mix": 0.55}, width=1.3, sends={"room": 0.2}, duck={"depth": 0.2, "release": 0.12}, gain_db=-6.0)
    if leslie:
        mix["leslie"] = {"speed": [[1, 1]], "crossover": 800, "mix": 0.5}
    return (*v, mix)


def chops(v):
    return (*v, dict(hp=300, drive=1.5, crush={"bits": 10, "rate": 16000, "mix": 0.6}, width=1.2, sends={"plate": 0.25, "echo": 0.25},
                     duck={"depth": 0.2, "release": 0.12}, gain_db=-8.0))


def lead(v):
    return (*v, dict(lmms_fx=[{"lv2": "calf:Saturator"}], hp=200, drive=1.3, sends={"echo": 0.18, "plate": 0.2}, gain_db=-6.0))


def strings(v):
    return (*v, dict(hp=250, lp=6000, crush={"bits": 11, "rate": 22050, "mix": 0.3}, width=1.4, sends={"plate": 0.3},
                     duck={"depth": 0.3, "release": 0.15}, gain_db=-14.0))


def spec(title, seed, bpm, blurb, bass_pattern, voices, comp_steps=(0, 3, 6, 10, 13)):
    arr = copy.deepcopy(ARRANGEMENT)
    return {
        "title": title, "song": SONGS / f"ny-house-93-{seed}.am.json", "genre": "ny-house-93", "blurb": blurb,
        "rebuild": f"bountiful/dirty_house.py {title.lower().replace(' ', '-')}",
        "overrides": {"bpm": bpm, "bass": {"pattern": bass_pattern},
                      "comp": {"steps": list(comp_steps), "low": 55, "high": 75, "top": 72, "notes": 4, "gate": 0.22, "humanize_ms": 4},
                      "vox": {"steps": [7, 15], "low": 62, "high": 79, "top": 74, "notes": 2, "gate": 0.3, "vel": 0.74, "accent": 0.82, "humanize_ms": 5},
                      "pad": {"low": 53, "high": 76, "top": 72, "notes": 4, "vel": 0.5},
                      "arrangement": arr, "master": DIRTY_TAPE},
        "layers": [("bass", "bass_sub")],
        "voices": voices,
        "drum_stems": GRIT_DRUMS,
        "targets": {"bass": -6.0, "bass_sub": -17.0, "comp": -7.0, "lead": -8.0, "pad": -18.0, "vox": -10.0},
        "automation": [{"type": "lowpass", "tracks": ["comp", "pad", "vox"], "points": [[BUILD_START, 300], [BUILD_START + 4, 1000], [BUILD_START + 8, 18000]]}],
    }


SPECS = {
    "sub-basement": spec(
        "Sub Basement", 847914251, 126,
        "C minor i9-iv9-III6-v7 (no bright major chords anywhere): Hammond organ stabs crushed to 12 bits through a fast Leslie, "
        "the dingy Funky Reso Bass, crushed 'aah' chops, a gritty Calf Monosynth lead, 12-bit sampler drums.",
        [[0, "R", 0.4], [3, "R", 0.18], [6, "O", 0.22], [8, "R", 0.3], [10, "O", 0.18], [11, "R", 0.18], [14, "5", 0.25]],
        {"bass": dingy_bass(zyn("olivers-100/0054-Funky Reso Bass.xiz", "Funky Reso Bass (ZynAddSubFX / olivers-100)")), "bass_sub": sub(),
         "comp": stabs(zyn("Collection/0054-Hammond Organ.xiz", "Hammond Organ (ZynAddSubFX / Collection), organ stabs"), leslie=True),
         "vox": chops(zyn("ChoirAndVoice/0001-AHH Choir 1.xiz", "AHH Choir 1 (ZynAddSubFX / ChoirAndVoice), vocal chops")),
         "lead": lead(mono("Square Worm")),
         "pad": strings(zyn("Strings/0034-Dark Strings.xiz", "Dark Strings (ZynAddSubFX / Strings)"))}),
    "rust": spec(
        "Rust", 580558825, 124,
        "D minor i9-VII-iv9-V: synth piano crushed to 10 bits like an old sampler, Calf Monosynth Boom Bass on a driving 16th "
        "pattern, crushed 'eh' chops, a PWM lead, saw strings, 12-bit sampler drums.",
        [[0, "R", 0.3], [2, "R", 0.15], [3, "O", 0.15], [6, "R", 0.25], [8, "R", 0.2], [10, "O", 0.2], [11, "R", 0.15], [14, "R", 0.25]],
        {"bass": dingy_bass(mono("Boom Bass")), "bass_sub": sub(),
         "comp": stabs(zyn("Cormi_Sound/0066-Synth_Piano_02.xiz", "Synth_Piano_02 (ZynAddSubFX / Cormi_Sound), piano stabs"), bits=10),
         "vox": chops(zyn("ChoirAndVoice/0003-EHH Choir 1.xiz", "EHH Choir 1 (ZynAddSubFX / ChoirAndVoice), vocal chops")),
         "lead": lead(zyn("olivers-100/0046-Bogus PWM Lead.xiz", "Bogus PWM Lead (ZynAddSubFX / olivers-100)")),
         "pad": strings(zyn("Strings/0005-Saw Strings 5.xiz", "Saw Strings 5 (ZynAddSubFX / Strings)"))},
        comp_steps=(0, 3, 6, 10, 12)),
}

if __name__ == "__main__":
    for k in sys.argv[1:] or list(SPECS):
        LT.make(SPECS[k], log=lambda s: print(s, flush=True))
