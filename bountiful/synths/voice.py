"""The one file the renderer loads for every Bountiful synth (kind = "pyvoice", preset = {module = <this file>, ...}).
The preset names the instrument: synth = "nes", plus that synth's knobs; note() hands each note to it."""
from __future__ import annotations

import sys
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:      # loaded by path, not as part of the package
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from synths import get  # noqa: E402


def note(midi, vel, dur, p, rng, from_midi=None):
    return get(p["synth"]).note(midi, vel, dur, p, rng, from_midi=from_midi)
