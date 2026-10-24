#!/usr/bin/env python3
"""Four more dark Soviet synth-pop songs in the 'Zona' recipe: Bountiful Music MIDI, LMMS instruments.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/darkwave_ep.py [beton tunguska noch kassiopeya]

Each song has its own composed skeleton (darkwave candidates, songs/soviet-darkwave-87/), tempo, bass
rhythm, sequencer figure and LMMS instrument set.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lmms_tracks as LT  # noqa: E402

SONGS = Path(__file__).resolve().parent.parent / "songs" / "soviet-darkwave-87"


def zyn(path, label):
    return {"zyn": path}, label


def mono(preset):
    return {"lv2": "calf:Monosynth", "preset": preset}, f"{preset} (Calf Monosynth)"


def dingy_bass(v, grit=False):   # the Zona bass chain: LMMS saturator + crusher, then drive and a parallel 9-bit crush
    if grit:                        # for clean bass presets: harder drive, deeper crush, the mids pushed (the sub layer keeps the weight)
        return (*v, dict(lmms_fx=[{"lv2": "calf:Saturator"}, {"lv2": "calf:Crusher"}], hp=45, lp=5000,
                         eq=[["lowshelf", 90, -3.0], ["peak", 700, 5.0, 0.9], ["peak", 1400, 3.0, 1.0], ["peak", 250, -1.5, 1.0]], drive=3.2,
                         crush={"bits": 8, "rate": 14000, "mix": 0.55}, mono=True, duck={"depth": 0.25, "release": 0.09}, gain_db=-5.0))
    return (*v, dict(lmms_fx=[{"lv2": "calf:Saturator"}, {"lv2": "calf:Crusher"}], hp=35, lp=4500,
                     eq=[["peak", 700, 2.5, 1.0], ["peak", 250, -2.0, 1.0]], drive=1.8, crush={"bits": 9, "rate": 16000, "mix": 0.35},
                     mono=True, duck={"depth": 0.25, "release": 0.09}, gain_db=-5.0))


def sub_bass():
    return ({"zyn": "Bass/0003-Bass 3 _analog_.xiz"}, "Bass 3 analog (ZynAddSubFX / Bass)",
            dict(hp=28, lp=180, mono=True, duck={"depth": 0.3, "release": 0.1}, gain_db=-13.0))


def lead(v, fx=True):
    return (*v, dict(lmms_fx=[{"lv2": "calf:Saturator"}] if fx else [], hp=180, chorus={"depth_ms": 2.0, "rate": 0.4, "base_ms": 9, "mix": 0.2},
                     sends={"echo": 0.22, "plate": 0.32}, width=1.2, gain_db=3.0))


def lead_hi(v):
    return (*v, dict(hp=400, pan=-0.2, sends={"echo": 0.3, "plate": 0.4}, gain_db=-8.0))


def arp(v, transpose=0):
    return (*v, dict(lmms_fx=[{"lv2": "calf:Phaser"}], hp=220, width=1.5, sends={"echo": 0.25, "plate": 0.15},
                     duck={"depth": 0.15, "release": 0.12}, gain_db=-6.0, **({"transpose": transpose} if transpose else {})))


def pad(v):
    return (*v, dict(lmms_fx=[{"lv2": "calf:Flanger", "preset": "Warble"}], hp=200, lp=5000, width=1.6, sends={"plate": 0.4}, gain_db=-11.0))


def choir(v):
    return (*v, dict(hp=250, lp=6000, width=1.8, sends={"plate": 0.5}, gain_db=-19.0))


SPECS = {
    "beton": {
        "title": "Beton", "song": SONGS / "soviet-darkwave-87-2124844069.am.json", "genre": "soviet-darkwave-87",
        "blurb": "Concrete and sodium light: D minor i-iv-v-i, a galloping 16th bass, Calf Monosynth bass and lead.",
        "overrides": {"bpm": 112, "bass": {"pattern": [[0, "R", 0.2], [2, "R", 0.18], [3, "R", 0.18], [4, "O", 0.2], [6, "R", 0.18], [7, "R", 0.18],
                                                       [8, "R", 0.2], [10, "R", 0.18], [11, "R", 0.18], [12, "5", 0.2], [14, "R", 0.18], [15, "O", 0.18]]}},
        "voices": {"bass": dingy_bass(mono("Boom Bass")), "bass_sub": sub_bass(), "lead": lead(mono("Square Worm")),
                   "lead_hi": lead_hi(zyn("olivers-100/0042-Low pH Lead.xiz", "Low pH Lead (ZynAddSubFX / olivers-100)")),
                   "arp": arp(zyn("Laba170bank/0132-chip-SIDarpSharp2.xiz", "chip-SIDarpSharp2 (ZynAddSubFX / Laba170bank)")),
                   "pad": pad(zyn("Strings/0016-Sweep Pad 1.xiz", "Sweep Pad 1 (ZynAddSubFX / Strings)")),
                   "choir": choir(zyn("Fantasy/0011-Space Choir1.xiz", "Space Choir1 (ZynAddSubFX / Fantasy)"))},
    },
    "tunguska": {
        "title": "Tunguska", "song": SONGS / "soviet-darkwave-87-1883521999.am.json", "genre": "soviet-darkwave-87",
        "blurb": "Slow and heavy: B-flat minor, a syncopated half-weight Punch Bass, a bell sequencer in 8ths, an ethereal Organic pad.",
        "overrides": {"bpm": 104, "bass": {"pattern": [[0, "R", 0.9], [3, "R", 0.25], [6, "O", 0.3], [8, "R", 0.6], [11, "R", 0.25], [14, "5", 0.3]]},
                      "arp": {"rate": 0.5, "pattern": [0, 2, 1, 3]}},
        "voices": {"bass": dingy_bass(zyn("olivers-100/0060-Punch Bass.xiz", "Punch Bass (ZynAddSubFX / olivers-100)")), "bass_sub": sub_bass(),
                   "lead": lead(zyn("olivers-100/0042-Low pH Lead.xiz", "Low pH Lead (ZynAddSubFX / olivers-100)")),
                   "lead_hi": lead_hi(zyn("olivers-100/0049-Bitey Triangle Lead.xiz", "Bitey Triangle Lead (ZynAddSubFX / olivers-100)")),
                   "arp": arp(({"xpf": "TripleOscillator/AnalogBell.xpf"}, "AnalogBell (LMMS TripleOscillator)")),
                   "pad": pad(({"xpf": "Organic/pad_ethereal.xpf"}, "pad_ethereal (LMMS Organic)")),
                   "choir": choir(zyn("the_mysterious_bank_2/0022-fantasy_choir.xiz", "fantasy_choir (ZynAddSubFX / the_mysterious_bank_2)"))},
    },
    "noch": {
        "title": "Noch'", "song": SONGS / "soviet-darkwave-87-1440493463.am.json", "genre": "soviet-darkwave-87",
        "blurb": "Night: A minor i-iv-III-v, a Calf Monosynth OctaWorm bass in 8th-note octaves, the LB302 sequencer, soft strings and choir.",
        "overrides": {"bpm": 110, "bass": {"style": "octave8", "gate": 0.3}, "arp": {"rate": 0.5, "pattern": [0, 1, 2, 1]}},
        "voices": {"bass": dingy_bass(mono("OctaWorm")), "bass_sub": sub_bass(),
                   "lead": lead(mono("Barkline")),
                   "lead_hi": lead_hi(zyn("olivers-100/0046-Bogus PWM Lead.xiz", "Bogus PWM Lead (ZynAddSubFX / olivers-100)")),
                   "arp": arp(({"xpf": "LB302/DroneArp.xpf"}, "DroneArp (LMMS LB302)")),
                   "pad": pad(zyn("the_mysterious_bank_3/0001-soft_strings.xiz", "soft_strings (ZynAddSubFX / the_mysterious_bank_3)")),
                   "choir": choir(zyn("Collection/0118-Soft Choir.xiz", "Soft Choir (ZynAddSubFX / Collection)"))},
    },
    "kassiopeya": {
        "title": "Kassiopeya", "song": SONGS / "soviet-darkwave-87-1711689560.am.json", "genre": "soviet-darkwave-87",
        "blurb": "The fastest of the set: E minor i-iv-VI-v, the Zona 16th pulse on a hard-driven Calf Monosynth Goa Bass, a plucked-wah sequencer.",
        "overrides": {"bpm": 116, "arp": {"pattern": [0, 1, 2, 3, 2, 1]}},
        "voices": {"bass": dingy_bass(mono("Goa Bass"), grit=True), "bass_sub": sub_bass(),
                   "lead": lead(zyn("olivers-100/0049-Bitey Triangle Lead.xiz", "Bitey Triangle Lead (ZynAddSubFX / olivers-100)")),
                   "lead_hi": lead_hi(zyn("olivers-100/0042-Low pH Lead.xiz", "Low pH Lead (ZynAddSubFX / olivers-100)")),
                   "arp": arp(zyn("Plucked/0036-Plucked Wah.xiz", "Plucked Wah (ZynAddSubFX / Plucked)")),
                   "pad": pad(zyn("Strings/0018-Sweep Pad 2.xiz", "Sweep Pad 2 (ZynAddSubFX / Strings)")),
                   "choir": choir(zyn("Companion/0119-Ghost Choir.xiz", "Ghost Choir (ZynAddSubFX / Companion)"))},
    },
}

if __name__ == "__main__":
    for k in sys.argv[1:] or list(SPECS):
        LT.make(SPECS[k], log=lambda s: print(s, flush=True))
