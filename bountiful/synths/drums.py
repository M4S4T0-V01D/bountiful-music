"""A modern drum machine, every sound built from scratch: 808 and 909 kicks and snares, claps, hats, ride, crash, toms,
cowbell, shaker, rim, and a cinematic impact. Each hit is a mix of parts:

  body        a sine (or triangle) falling from f_start to f_end Hz in pdecay s, ringing for decay s; tuned = it
              follows the note instead (toms, 808 bass), relative to middle C
  click       level 0-1 of a short transient at the start
  noise       {level, filter hp|bp|lp, cut Hz, q, decay s, attack s}; bursts = claps (that many hits ~10 ms apart)
  metal       {level, filter, cut, q, decay}: six detuned squares, the 808's hats and cymbals; cowbell = two of them
  drive 0-1   saturation; choke = the note's duration cuts the sound (open hat)
"""
from __future__ import annotations

import numpy as np

from synths import core as C

ONE_SHOT = True
METAL = [205.3, 304.4, 369.6, 522.7, 540.0, 800.0]

PRESETS = {
    "kick-808": {"body": {"f_start": 110, "f_end": 48, "pdecay": 0.06, "decay": 0.9}, "click": 0.15, "drive": 0.15,
                 "level": 0.7},
    "kick-909": {"body": {"f_start": 230, "f_end": 55, "pdecay": 0.035, "decay": 0.38}, "click": 0.5,
                 "noise": {"level": 0.15, "filter": "lp", "cut": 5000, "decay": 0.012}, "drive": 0.4, "level": 0.65},
    "kick-game": {"body": {"f_start": 320, "f_end": 50, "pdecay": 0.025, "decay": 0.22}, "click": 0.6, "drive": 0.6,
                  "level": 0.6},
    "sub-boom": {"body": {"f_start": 80, "f_end": 32, "pdecay": 0.25, "decay": 2.2}, "click": 0.05, "drive": 0.25,
                 "level": 0.7},
    "snare-909": {"body": {"f_start": 330, "f_end": 185, "pdecay": 0.03, "decay": 0.12, "level": 0.55},
                  "noise": {"level": 0.8, "filter": "hp", "cut": 1800, "decay": 0.17}, "click": 0.3, "drive": 0.3,
                  "level": 0.55},
    "snare-808": {"body": {"f_start": 240, "f_end": 175, "pdecay": 0.02, "decay": 0.15, "level": 0.7},
                  "noise": {"level": 0.5, "filter": "hp", "cut": 3500, "decay": 0.11}, "level": 0.55},
    "rim": {"body": {"f_start": 1700, "f_end": 1650, "pdecay": 0.01, "decay": 0.02, "level": 0.8},
            "noise": {"level": 0.4, "filter": "bp", "cut": 4200, "q": 2.0, "decay": 0.012}, "click": 0.5, "level": 0.5},
    "clap": {"noise": {"level": 1.0, "filter": "bp", "cut": 1300, "q": 1.4, "decay": 0.16}, "bursts": 4,
             "level": 0.85},
    "hat-closed": {"metal": {"level": 0.7, "filter": "hp", "cut": 7500, "decay": 0.045},
                   "noise": {"level": 0.35, "filter": "hp", "cut": 9000, "decay": 0.03}, "level": 0.75},
    "hat-open": {"metal": {"level": 0.7, "filter": "hp", "cut": 7000, "decay": 0.45},
                 "noise": {"level": 0.35, "filter": "hp", "cut": 8500, "decay": 0.35}, "choke": True, "level": 0.65},
    "ride": {"metal": {"level": 0.6, "filter": "bp", "cut": 5200, "q": 0.9, "decay": 1.6},
             "noise": {"level": 0.15, "filter": "hp", "cut": 7000, "decay": 0.9}, "click": 0.15, "level": 0.6},
    "crash": {"metal": {"level": 0.5, "filter": "hp", "cut": 4500, "decay": 2.2},
              "noise": {"level": 0.6, "filter": "hp", "cut": 5000, "decay": 1.9, "attack": 0.004}, "level": 0.35},
    "tom-low": {"body": {"f_start": 140, "f_end": 90, "pdecay": 0.12, "decay": 0.5, "tuned": True},
                "noise": {"level": 0.1, "filter": "lp", "cut": 3000, "decay": 0.04}, "click": 0.2, "level": 0.6},
    "tom-mid": {"body": {"f_start": 200, "f_end": 135, "pdecay": 0.1, "decay": 0.4, "tuned": True},
                "noise": {"level": 0.1, "filter": "lp", "cut": 3500, "decay": 0.04}, "click": 0.2, "level": 0.6},
    "tom-high": {"body": {"f_start": 290, "f_end": 200, "pdecay": 0.08, "decay": 0.32, "tuned": True},
                 "noise": {"level": 0.1, "filter": "lp", "cut": 4000, "decay": 0.035}, "click": 0.2, "level": 0.6},
    "cowbell": {"metal": {"level": 1.0, "freqs": [540.0, 800.0], "filter": "bp", "cut": 2600, "q": 1.2,
                          "decay": 0.28}, "level": 0.45},
    "shaker": {"noise": {"level": 1.0, "filter": "hp", "cut": 6000, "decay": 0.05, "attack": 0.025}, "level": 1.4},
    "impact": {"body": {"f_start": 90, "f_end": 28, "pdecay": 0.4, "decay": 2.6},
               "noise": {"level": 0.7, "filter": "lp", "cut": 2200, "decay": 0.9, "attack": 0.002}, "click": 0.4,
               "drive": 0.5, "level": 0.65},
}


def _filt(x, spec):
    kind = {"hp": "highpass", "bp": "bandpass", "lp": "lowpass"}[spec.get("filter", "hp")]
    return C.biquad(x, kind, spec.get("cut", 5000), spec.get("q", 0.707))


def _env(t, spec):
    e = np.exp(-t * 6.9 / max(spec.get("decay", 0.1), 1e-3))
    if spec.get("attack"):
        e *= np.clip(t / spec["attack"], 0, 1)
    return e


def _length(p) -> float:
    return max(p[k].get("decay", 0.1) + p[k].get("attack", 0) for k in ("body", "noise", "metal") if k in p)


def note(midi, vel, dur, p, rng, from_midi=None) -> np.ndarray:
    length = _length(p) + (0.04 * p.get("bursts", 0))
    if p.get("choke"):
        length = min(length, dur + 0.03)
    n = int(length * C.SR) + 256
    t = np.arange(n) / C.SR
    y = np.zeros(n)
    if "body" in p:
        b = p["body"]
        k = C.hz(midi) / 261.6 if b.get("tuned") else 1.0
        f = (b["f_end"] + (b["f_start"] - b["f_end"]) * np.exp(-t / max(b.get("pdecay", 0.05), 1e-4))) * k
        ph = np.cumsum(f) / C.SR
        y += b.get("level", 1.0) * np.sin(2 * np.pi * ph) * _env(t, b)
    if "noise" in p:
        s = p["noise"]
        e = _env(t, s)
        if p.get("bursts"):                                           # a clap: several hands, then the room
            gap = int(0.0095 * C.SR)
            hits = np.zeros(n)
            for i in range(p["bursts"] - 1):
                m = np.arange(n) - i * gap
                hits += np.where(m >= 0, np.exp(-np.maximum(m, 0) / (0.003 * C.SR)), 0) * (m < gap)
            tail = np.roll(e, (p["bursts"] - 1) * gap)
            tail[:(p["bursts"] - 1) * gap] = 0
            e = hits + tail
        y += s.get("level", 1.0) * _filt(rng.uniform(-1, 1, n), s) * e * 1.6
    if "metal" in p:
        s = p["metal"]
        sq = sum(np.sign(np.sin(2 * np.pi * f * t + 2 * np.pi * rng.random())) for f in s.get("freqs", METAL))
        y += s.get("level", 1.0) * _filt(sq / len(s.get("freqs", METAL)), s) * _env(t, s) * 1.4
    if p.get("click"):
        m = int(0.003 * C.SR)
        y[:m] += p["click"] * np.exp(-np.arange(m) / (0.0004 * C.SR)) * np.sign(rng.uniform(-1, 1))
    y = y * np.clip(t / 0.0004, 0, 1)
    if p.get("choke"):
        y *= np.clip(1 - (t - dur) / 0.03, 0, 1)
    y = C.drive(y, p.get("drive", 0.0)) * (0.35 + 0.65 * vel)
    return C.finish(y, p)
