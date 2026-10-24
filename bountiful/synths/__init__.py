"""Bountiful's own instruments: every sound made by our code, from oscillators up. No samples, no plug-ins, no LMMS.

  nes   Ricoh 2A03: pulse, triangle, noise          gb    Game Boy: pulse, 4-bit wave RAM, noise
  sid   C64 SID: tri/saw/pulse/noise and combined waves, ring mod, sync, ADSR, resonant multimode filter

  va        virtual analog: supersaws, plucks, pads, brass, reese / acid / sub basses
  fm        4-operator FM: e-pianos, bells, glass, FM bass, brass, organ, clav
  pluck     physical-model strings: guitars, harp, koto, harpsichord, pizzicato, bass
  modal     struck bars and bells: marimba, vibes, glockenspiel, music box, kalimba, steel drum, handpan, bells
  ensemble  string sections and a formant choir
  drums     a drum machine built from scratch: 808 / 909 kicks and snares, claps, hats, cymbals, toms, impact

    track("nes", "lead-25", vibrato=30)   -> a track table for the renderer: {"kind": "pyvoice", "preset": {...}}
    preset("sid", "acid-bass")            -> the knobs alone
    get("nes").note(60, 1.0, 0.5, p, rng) -> render one note directly
"""
from __future__ import annotations

import importlib
from pathlib import Path

SYNTHS = ("nes", "gb", "sid", "va", "fm", "pluck", "modal", "ensemble", "drums")
VOICE = Path(__file__).resolve().parent / "voice.py"


def get(name: str):
    if name not in SYNTHS:
        raise KeyError(f"unknown synth {name!r} (have {', '.join(SYNTHS)})")
    return importlib.import_module(f"synths.{name}")


def presets(name: str) -> dict:
    return get(name).PRESETS


def preset(name: str, which: str, **over) -> dict:
    return {"synth": name, **presets(name)[which], **over}


def track(name: str, which: str, **over) -> dict:
    return {"kind": "pyvoice", "preset": {"module": str(VOICE), "fn": "note", **preset(name, which, **over)}}
