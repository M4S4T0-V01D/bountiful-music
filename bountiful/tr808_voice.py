"""A tuned TR-808 bass drum played as a bass (the Memphis / phonk / trap "808"): a sine with a fast pitch drop on the
attack (the kick's punch), a long decay, slides between tied notes, and saturation that adds the odd harmonics a phone
speaker can play while the fundamental stays a sine.

The renderer plays it as kind = "pyvoice" (intelligent-jungle studio/render_midi.py) with preset = { module = <this file>,
fn = "note", ...the knobs below }. A note glides when it starts within the track's glide_gap of the previous note's end.

  punch_st    semitones the pitch starts above the note on a fresh hit (0 = none), falling over punch_ms
  click       level of a short 1.5 kHz click on fresh hits (the beater), 0-1
  decay       s for the body to fall by 1/e (808 "decay" knob); held notes still fade, as on the machine
  hold        s at full level before the decay starts
  glide       s for a slide to cover most of the interval (portamento, in pitch, not in Hz)
  legato      level a slid note starts at (the previous note's body carries on, so there is no new attack)
  h2          second harmonic (warmth), 0-0.3
  drive       tanh saturation before the output; dist_mix blends the clean sine back in (1 = all driven)
  tone_hp     Hz: the driven part is high-passed here so distortion never muddies the fundamental (0 = off)
  release     s fade after note-off
  level       output gain
"""
from __future__ import annotations

import numpy as np
from scipy import signal

SR = 44100
DEFAULT = {"punch_st": 9.0, "punch_ms": 28.0, "click": 0.25, "decay": 1.6, "hold": 0.12, "glide": 0.09, "legato": 0.8,
           "h2": 0.08, "drive": 2.6, "dist_mix": 0.55, "tone_hp": 90.0, "release": 0.07, "level": 0.9}


def _hz(m):
    return 440.0 * 2 ** ((np.asarray(m, dtype=np.float64) - 69) / 12)


def note(midi: float, vel: float, dur: float, p: dict, rng: np.random.Generator, from_midi: float | None = None) -> np.ndarray:
    q = {**DEFAULT, **{k: v for k, v in p.items() if k in DEFAULT}}
    n = int((dur + q["release"]) * SR)
    t = np.arange(n) / SR
    slid = from_midi is not None
    if slid:
        pitch = midi + (from_midi - midi) * np.exp(-t / max(q["glide"] / 3, 1e-3))
    else:
        pitch = midi + q["punch_st"] * np.exp(-t / max(q["punch_ms"] / 1000, 1e-4))
    ph = np.cumsum(2 * np.pi * _hz(pitch) / SR)
    body = np.sin(ph) + q["h2"] * np.sin(2 * ph)
    env = np.where(t < q["hold"], 1.0, np.exp(-np.maximum(t - q["hold"], 0) / q["decay"]))
    if slid:
        env *= q["legato"] + (1 - q["legato"]) * (1 - np.exp(-t / 0.03))
    else:
        env *= np.clip(t / 0.0015, 0, 1)
    env *= np.clip(1 - (t - dur) / q["release"], 0, 1)
    clean = body * env
    hot = np.tanh(clean * q["drive"]) / np.tanh(q["drive"])
    if q["tone_hp"]:
        sos = signal.butter(2, q["tone_hp"], "highpass", fs=SR, output="sos")
        harm = signal.sosfilt(sos, hot - clean)
        y = clean + q["dist_mix"] * harm * 2.0
    else:
        y = (1 - q["dist_mix"]) * clean + q["dist_mix"] * hot
    if q["click"] and not slid:
        k = min(n, int(0.006 * SR))
        c = np.zeros(n)
        c[:k] = np.sin(2 * np.pi * 1500 * t[:k]) * np.exp(-t[:k] / 0.0012) + 0.3 * rng.standard_normal(k) * np.exp(-t[:k] / 0.0008)
        y += q["click"] * c
    return (y * q["level"] * (0.5 + 0.5 * vel)).astype(np.float32)
