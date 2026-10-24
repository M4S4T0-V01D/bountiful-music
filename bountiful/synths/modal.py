"""Struck bars, tines and bells by modal synthesis: each instrument is the set of frequencies its body rings at, each
with its own loudness and ring time, set going by a mallet. Marimba, xylophone, vibraphone, glockenspiel, celesta,
music box, kalimba, steel drum, handpan, tubular and church bells, wood block.

  modes       [[ratio to the note, amplitude, ring time s at middle C], ...]
  decay_track how much shorter higher notes ring (0-1); hardness 0-1, how much the mallet wakes the upper modes
              (velocity adds to it) and how loud its click is
  tremolo     depth 0-1 at tremolo_rate Hz (the vibraphone's fans); beat = cents between a mode's two halves (bells)
  damp        s: let go of the note and the bar is damped in this time (vibraphone pedal); None lets it ring out
"""
from __future__ import annotations

import numpy as np

from synths import core as C

ONE_SHOT = True                                         # notes ring out by themselves; dur only damps them
CANTILEVER = [1.0, 6.27, 17.55, 34.39]                  # a tine clamped at one end (music box, kalimba)

PRESETS = {
    "marimba": {"modes": [[1, 1.0, 0.9], [3.99, 0.35, 0.25], [9.9, 0.1, 0.08]], "hardness": 0.4, "decay_track": 0.6,
                "level": 0.6},
    "xylophone": {"modes": [[1, 1.0, 0.45], [3.0, 0.4, 0.2], [6.0, 0.25, 0.08], [9.2, 0.1, 0.04]], "hardness": 0.8,
                  "decay_track": 0.5, "level": 0.55},
    "vibraphone": {"modes": [[1, 1.0, 3.8], [4.0, 0.3, 1.0], [10.0, 0.08, 0.3]], "hardness": 0.35, "tremolo": 0.35,
                   "tremolo_rate": 5.2, "damp": 0.5, "level": 0.55},
    "glockenspiel": {"modes": [[1, 1.0, 2.6], [2.71, 0.5, 1.4], [5.15, 0.3, 0.7], [8.54, 0.15, 0.4]],
                     "hardness": 0.85, "decay_track": 0.3, "level": 0.45},
    "celesta": {"modes": [[1, 1.0, 1.6], [4.0, 0.25, 0.6], [10.1, 0.05, 0.2]], "hardness": 0.3, "decay_track": 0.4,
                "damp": 0.35, "level": 0.55},
    "music-box": {"modes": [[r, a, d] for r, a, d in zip(CANTILEVER, [1.0, 0.35, 0.15, 0.05], [2.4, 0.6, 0.2, 0.08])],
                  "hardness": 0.9, "decay_track": 0.3, "level": 0.5},
    "kalimba": {"modes": [[1, 1.0, 1.3], [CANTILEVER[1], 0.2, 0.2], [CANTILEVER[2], 0.06, 0.05], [2.0, 0.08, 0.6]],
                "hardness": 0.5, "decay_track": 0.4, "level": 0.6},
    "steel-drum": {"modes": [[1, 1.0, 0.9], [2.01, 0.55, 0.6], [3.0, 0.25, 0.35], [4.02, 0.12, 0.2],
                             [5.05, 0.06, 0.1]], "hardness": 0.6, "beat": 4, "decay_track": 0.4, "level": 0.5},
    "handpan": {"modes": [[1, 1.0, 3.0], [2.0, 0.45, 2.0], [3.0, 0.2, 1.2], [0.5, 0.12, 2.5]], "hardness": 0.25,
                "beat": 3, "decay_track": 0.3, "level": 0.55},
    "tubular-bell": {"modes": [[1, 1.0, 5.0], [2.76, 0.6, 3.5], [5.4, 0.35, 2.0], [8.93, 0.2, 1.2],
                               [13.34, 0.08, 0.6]], "hardness": 0.6, "beat": 2, "decay_track": 0.2, "level": 0.45},
    "church-bell": {"modes": [[0.5, 0.6, 6.0], [1, 1.0, 4.5], [1.19, 0.6, 3.5], [1.5, 0.35, 3.0], [2.0, 0.5, 2.5],
                              [2.51, 0.25, 1.6], [3.01, 0.15, 1.2], [4.07, 0.1, 0.8]], "hardness": 0.7, "beat": 3,
                    "decay_track": 0.2, "level": 0.4},
    "crystal": {"modes": [[1, 1.0, 2.8], [2.32, 0.4, 1.6], [4.25, 0.25, 0.9], [6.63, 0.12, 0.5]], "hardness": 0.5,
                "beat": 5, "decay_track": 0.3, "level": 0.45},
    "wood-block": {"modes": [[1, 1.0, 0.07], [2.57, 0.5, 0.04], [4.2, 0.25, 0.02]], "hardness": 0.9,
                   "decay_track": 0.0, "damp": 0.02, "level": 0.6},
}


def note(midi, vel, dur, p, rng, from_midi=None) -> np.ndarray:
    f0 = float(C.hz(midi))
    track = (261.6 / f0) ** p.get("decay_track", 0.5)
    modes = [(r, a, d * track) for r, a, d in p["modes"] if f0 * r < C.SR * 0.45]
    damp = p.get("damp")
    ring = max(d for _, _, d in modes)                                # down 60 dB
    length = min(ring, dur + damp) if damp is not None else ring
    n = int(length * C.SR) + 256
    t = np.arange(n) / C.SR
    hard = min(1.0, p.get("hardness", 0.5) * (0.5 + 0.7 * vel))
    y = np.zeros(n)
    for k, (r, a, d) in enumerate(modes):
        amp = a * (hard ** (0.5 * k) if k else 1.0)                   # a soft mallet barely reaches the upper modes
        env = np.exp(-t * 6.9 / d) * amp
        phase = 2 * np.pi * rng.random()
        if p.get("beat") and r != 1:                                  # bells: each mode is a pair a few cents apart
            fb = f0 * r * 2 ** (p["beat"] / 1200)
            y += env * 0.5 * (np.sin(2 * np.pi * f0 * r * t + phase) + np.sin(2 * np.pi * fb * t + phase))
        else:
            y += env * np.sin(2 * np.pi * f0 * r * t + phase)
    y = y * np.clip(t / 0.0015, 0, 1)                                 # a mallet takes a moment to land
    if hard > 0.2:                                                    # its click
        m = int(0.004 * C.SR)
        click = rng.uniform(-1, 1, m) * np.exp(-np.arange(m) / (0.0008 * C.SR))
        click = C.biquad(click, "bandpass", min(f0 * 6, 9000), 1.0)
        y[:m] += click * 0.6 * (hard - 0.2)
    if p.get("tremolo"):
        y *= 1 - p["tremolo"] * 0.5 * (1 - np.cos(2 * np.pi * p.get("tremolo_rate", 5.0) * t))
    if damp is not None:
        y *= np.clip(1 - (t - dur) / max(damp, 1e-3), 0, 1)
    y = y / sum(a for _, a, _ in modes) * 1.6 * (0.35 + 0.65 * vel)
    return C.finish(y, p)
