"""Sections: many players on one note, each a little out of tune and with their own vibrato. A string section, and a
choir whose voices pass through the formants of a sung vowel.

  kind        strings | choir; voices 1-8 players, detune cents spread, vibrato cents (each player's rate and depth
              a little different), bow / breath noise level 0-1
  vowel       choir: a | e | i | o | u, or {"from": "o", "to": "a", "time": s} to sing one into the other
  cutoff      strings: low-pass Hz (key_track 0-1); tremolo depth 0-1 at tremolo_rate Hz (bowed tremolo)
  a / d / s / r                envelope; chorus mix 0-1; glide as in core.pitch
"""
from __future__ import annotations

import numpy as np
from scipy import signal

from synths import core as C

OVER = 2
VOWELS = {                                        # formant Hz, and their gains; bandwidths below
    "a": [730, 1090, 2440, 3400],
    "e": [530, 1840, 2480, 3500],
    "i": [300, 2290, 3010, 3600],
    "o": [570, 840, 2410, 3300],
    "u": [320, 870, 2240, 3300],
}
F_GAIN = [1.0, 0.55, 0.3, 0.15]
F_BW = [90, 110, 150, 200]

PRESETS = {
    "strings": {"kind": "strings", "voices": 6, "detune": 10, "vibrato": 14, "bow": 0.06, "cutoff": 4200,
                "key_track": 0.3, "a": 0.22, "d": 1.0, "s": 1.0, "r": 0.55, "chorus": 0.3, "level": 0.45},
    "slow-strings": {"kind": "strings", "voices": 7, "detune": 12, "vibrato": 12, "bow": 0.04, "cutoff": 3200,
                     "key_track": 0.3, "a": 0.9, "d": 1.0, "s": 1.0, "r": 1.4, "chorus": 0.45, "level": 0.45},
    "cello-section": {"kind": "strings", "voices": 4, "detune": 8, "vibrato": 18, "bow": 0.08, "cutoff": 1800,
                      "key_track": 0.4, "a": 0.15, "d": 1.0, "s": 1.0, "r": 0.4, "chorus": 0.2, "level": 0.5},
    "tremolo-strings": {"kind": "strings", "voices": 6, "detune": 10, "vibrato": 8, "bow": 0.1, "cutoff": 4000,
                        "key_track": 0.3, "tremolo": 0.7, "tremolo_rate": 9.0, "a": 0.08, "d": 1.0, "s": 1.0,
                        "r": 0.35, "chorus": 0.3, "level": 0.45},
    "choir-aah": {"kind": "choir", "vowel": "a", "voices": 5, "detune": 12, "vibrato": 22, "breath": 0.08,
                  "a": 0.35, "d": 1.0, "s": 1.0, "r": 0.7, "chorus": 0.4, "level": 0.5},
    "choir-ooh": {"kind": "choir", "vowel": "u", "voices": 5, "detune": 10, "vibrato": 18, "breath": 0.1,
                  "a": 0.45, "d": 1.0, "s": 1.0, "r": 0.8, "chorus": 0.45, "level": 0.55},
    "choir-oh-ah": {"kind": "choir", "vowel": {"from": "o", "to": "a", "time": 0.8}, "voices": 5, "detune": 12,
                    "vibrato": 20, "breath": 0.08, "a": 0.3, "d": 1.0, "s": 1.0, "r": 0.7, "chorus": 0.4,
                    "level": 0.5},
    "ghost-choir": {"kind": "choir", "vowel": "o", "voices": 7, "detune": 18, "vibrato": 10, "breath": 0.3,
                    "a": 1.2, "d": 1.0, "s": 1.0, "r": 1.6, "chorus": 0.7, "level": 0.55},
    "voice-lead": {"kind": "choir", "vowel": "a", "voices": 1, "vibrato": 32, "vibrato_rate": 5.4, "breath": 0.05,
                   "a": 0.07, "d": 1.0, "s": 1.0, "r": 0.3, "glide": 0.06, "level": 0.5},
}


def _section(f: np.ndarray, p: dict, rng) -> np.ndarray:
    """The players' band-limited saws, each detuned and with a vibrato of its own (f is already oversampled)."""
    k = int(p.get("voices", 5))
    t = np.arange(len(f)) / (C.SR * OVER)
    out = np.zeros_like(f)
    for s in (np.linspace(-1, 1, k) if k > 1 else [0.0]):
        rate = p.get("vibrato_rate", 5.2) * (1 + 0.12 * rng.uniform(-1, 1))
        depth = p.get("vibrato", 15) * (1 + 0.3 * rng.uniform(-1, 1))
        ramp = np.clip((t - 0.12) / 0.4, 0, 1)
        cents = s * p.get("detune", 10) + depth * ramp * np.sin(2 * np.pi * rate * t + 2 * np.pi * rng.random())
        cents = cents + 4 * np.sin(2 * np.pi * 0.3 * rng.uniform(0.5, 1.5) * t + 2 * np.pi * rng.random())  # drift
        ph, dt = C.phase(f * 2 ** (cents / 1200), rng.random())
        out += C.saw(ph, dt)
    return out / np.sqrt(k)


def _formants(x: np.ndarray, vowel, n: int) -> np.ndarray:
    if isinstance(vowel, str):
        fs = [float(v) for v in VOWELS[vowel]]
    else:
        mix = np.clip(np.arange(n) / C.SR / max(vowel.get("time", 0.6), 1e-3), 0, 1)
        mix = mix * mix * (3 - 2 * mix)
        fs = [a + (b - a) * mix for a, b in zip(VOWELS[vowel["from"]], VOWELS[vowel["to"]])]
    y = np.zeros_like(x)
    for f, g, bw in zip(fs, F_GAIN, F_BW):
        q = float(np.mean(f)) / bw
        y += g * C.biquad(x, "bandpass", f, q, block=64)
    return y * 2.2


def note(midi, vel, dur, p, rng, from_midi=None) -> np.ndarray:
    a, d, s, r = p.get("a", 0.2), p.get("d", 1.0), p.get("s", 1.0), p.get("r", 0.5)
    n = int((dur + r) * C.SR) + 256
    m = C.pitch(midi, n, {k: v for k, v in p.items() if k != "vibrato"}, 100.0, int(np.ceil(dur * 100)), from_midi)
    f = np.repeat(C.hz(m), OVER) / OVER
    y = signal.resample_poly(_section(f, p, rng), 1, OVER)[:n]
    if p.get("kind") == "choir":
        y = y + p.get("breath", 0.05) * C.biquad(rng.uniform(-1, 1, n), "bandpass", 2500, 0.8) * 2
        y = _formants(y, p.get("vowel", "a"), n)
    else:
        y = y + p.get("bow", 0.05) * C.biquad(rng.uniform(-1, 1, n), "bandpass", 3000, 1.0) * 2
        y = C.biquad(y, "lowpass", p.get("cutoff", 4000) * (C.hz(midi) / 261.6) ** p.get("key_track", 0.3))
        y = C.onepole(y, 70.0, high=True)
    if p.get("tremolo"):
        t = np.arange(n) / C.SR
        y *= 1 - p["tremolo"] * 0.5 * (1 - np.cos(2 * np.pi * p.get("tremolo_rate", 8.0) * t))
    y = y * C.adsr(n, dur, a, d, s, r) * (0.45 + 0.55 * vel)
    y = C.chorus(y, p.get("chorus", 0.0))
    return C.finish(y, p)
