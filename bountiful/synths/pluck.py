"""Plucked and struck strings by physical model (extended Karplus-Strong): a burst of noise shaped like the pick runs
round a delay line one period long, losing its highs a little each trip. Guitars, harp, koto, harpsichord, pizzicato,
bass, banjo, dulcimer.

  bright      0-1, how sharp the pick is (velocity adds to it); pick 0-0.5, where along the string (0.5 = middle, hollow)
  soft        a rounded excitation (finger, felt hammer) instead of a sharp pick
  damping     0-0.25, how fast the highs die against the lows; decay = ring time (T60) in s at middle C,
              decay_track how much shorter higher notes ring; release = T60 once the note is let go (the hand mutes it)
  strings     1-3 strings per note, detune cents apart (courses: harpsichord, 12-string); octave 0-1, a string an
              octave up mixed in
  body        [[Hz, Q, gain], ...] resonances of the instrument's body, body_mix 0-1; tone = a last low-pass in Hz
"""
from __future__ import annotations

import numpy as np

from synths import core as C

PRESETS = {
    "nylon-guitar": {"bright": 0.45, "pick": 0.18, "damping": 0.12, "decay": 2.4, "release": 0.12, "soft": True,
                     "body": [[105, 2.0, 1.0], [210, 3.0, 0.6], [400, 2.5, 0.3]], "body_mix": 0.35, "level": 0.55},
    "steel-guitar": {"bright": 0.75, "pick": 0.13, "damping": 0.05, "decay": 3.2, "release": 0.12,
                     "body": [[100, 2.0, 1.0], [230, 3.0, 0.5], [800, 2.0, 0.25]], "body_mix": 0.3, "level": 0.5},
    "twelve-string": {"bright": 0.8, "pick": 0.13, "damping": 0.05, "decay": 3.0, "release": 0.15, "strings": 2,
                      "detune": 5, "octave": 0.6, "body": [[100, 2.0, 1.0], [230, 3.0, 0.5]], "body_mix": 0.25,
                      "level": 0.45},
    "muted-guitar": {"bright": 0.5, "pick": 0.15, "damping": 0.2, "decay": 0.28, "release": 0.03,
                     "body": [[110, 2.0, 1.0]], "body_mix": 0.3, "level": 0.6},
    "harp": {"bright": 0.4, "pick": 0.5, "soft": True, "damping": 0.08, "decay": 3.5, "release": 1.6, "level": 0.6},
    "koto": {"bright": 0.85, "pick": 0.08, "damping": 0.04, "decay": 1.8, "release": 0.4,
             "body": [[180, 2.0, 1.0], [520, 3.0, 0.4]], "body_mix": 0.2, "level": 0.5},
    "harpsichord": {"bright": 0.95, "pick": 0.06, "damping": 0.02, "decay": 2.6, "release": 0.08, "strings": 2,
                    "detune": 3, "body": [[250, 2.0, 1.0], [1100, 3.0, 0.3]], "body_mix": 0.15, "level": 0.45},
    "pizzicato": {"bright": 0.35, "pick": 0.22, "soft": True, "damping": 0.2, "decay": 0.55, "release": 0.05,
                  "strings": 2, "detune": 9, "body": [[280, 2.0, 1.0], [540, 2.5, 0.5]], "body_mix": 0.4,
                  "level": 0.6},
    "bass-guitar": {"bright": 0.3, "pick": 0.25, "soft": True, "damping": 0.15, "decay": 3.0, "decay_track": 0.2,
                    "release": 0.06, "tone": 2500, "level": 0.6},
    "slap-pop-bass": {"bright": 0.9, "pick": 0.1, "damping": 0.06, "decay": 1.6, "decay_track": 0.2,
                      "release": 0.05, "tone": 5000, "level": 0.5},
    "banjo": {"bright": 0.9, "pick": 0.07, "damping": 0.03, "decay": 1.1, "release": 0.1,
              "body": [[420, 3.0, 1.0], [1300, 3.0, 0.6]], "body_mix": 0.35, "level": 0.5},
    "dulcimer": {"bright": 0.7, "pick": 0.12, "soft": True, "damping": 0.04, "decay": 3.5, "release": 1.2,
                 "strings": 2, "detune": 6, "level": 0.5},
}


def _excite(N: int, P: float, p: dict, vel: float, rng) -> np.ndarray:
    x = rng.uniform(-1, 1, N)
    bright = min(1.0, p.get("bright", 0.5) * (0.6 + 0.5 * vel))
    x = C.onepole(x, 200 + 14000 * bright ** 2)
    if p.get("soft"):
        x = x * np.hanning(N)
    k = int(round(p.get("pick", 0.15) * P))
    if 0 < k < N:
        x[k:] = x[k:] - x[:-k]
    x = x - x.mean()
    return x / (np.abs(x).max() + 1e-9)


def _string(f0: float, n: int, gate: int, p: dict, vel: float, rng) -> np.ndarray:
    P = C.SR / f0
    N = max(3, int(P))
    fr = P - N
    dmp = float(np.clip(p.get("damping", 0.1), 0, 0.25))
    w = np.convolve([dmp, 1 - 2 * dmp, dmp], [1 - fr, fr])         # loss filter and fractional delay, taps N-1 .. N+2
    t60 = p.get("decay", 2.0) * (261.6 / f0) ** p.get("decay_track", 0.5)
    g_on = 10 ** (-3 * P / C.SR / t60)
    g_off = 10 ** (-3 * P / C.SR / max(p.get("release", 0.1), 0.01))
    x = np.zeros(n)
    e = _excite(N, P, p, vel, rng)
    x[:min(N, n)] = e[:n]
    o = N + 3
    buf = np.zeros(o + n)
    B = N - 1
    for st in range(0, n, B):
        en = min(st + B, n)
        g = g_on if st < gate else g_off
        fb = (w[0] * buf[o + st - N + 1:o + en - N + 1] + w[1] * buf[o + st - N:o + en - N]
              + w[2] * buf[o + st - N - 1:o + en - N - 1] + w[3] * buf[o + st - N - 2:o + en - N - 2])
        buf[o + st:o + en] = x[st:en] + g * fb
    return buf[o:]


def note(midi, vel, dur, p, rng, from_midi=None) -> np.ndarray:
    n = int((dur + p.get("release", 0.1) * 1.5) * C.SR) + 256
    gate = int(dur * C.SR)
    f0 = float(C.hz(midi))
    k = int(p.get("strings", 1))
    y = np.zeros(n)
    for s in (np.linspace(-0.5, 0.5, k) if k > 1 else [0.0]):
        y += _string(f0 * 2 ** (s * p.get("detune", 0) / 1200), n, gate, p, vel, rng)
    if p.get("octave"):
        y += p["octave"] * _string(f0 * 2, n, gate, p, vel, rng)
    y = y / (k + p.get("octave", 0))
    if p.get("body"):
        res = sum(g * C.biquad(y, "bandpass", f, q) for f, q, g in p["body"])
        y = y + p.get("body_mix", 0.3) * res
    if p.get("tone"):
        y = C.biquad(y, "lowpass", p["tone"])
    y = C.onepole(y, 35.0, high=True) * (0.4 + 0.6 * vel)
    return C.finish(y, p)
