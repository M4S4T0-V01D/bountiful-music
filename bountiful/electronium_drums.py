"""The Electronium's own percussion: no samples, only what its tone generators and noise sources could make.
Raymond Scott's machine made rhythm from the same circuits as its tones: resonant pings, filtered noise
chuffs, falling thumps, water-drop plops. Each function is hit(rng, vel, **args) -> mono float32 at 44.1 kHz,
used by render_midi.py drum sounds as  py = { module = ".../electronium_drums.py", fn = "thump", args = {...} }.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import lfilter

SR = 44100


def _t(sec: float) -> np.ndarray:
    return np.arange(int(sec * SR)) / SR


def _onepole(x: np.ndarray, f: float, high: bool = False) -> np.ndarray:
    a = np.exp(-2 * np.pi * f / SR)
    y = lfilter([1 - a], [1, -a], x)
    return x - y if high else y


def _reson(x: np.ndarray, f: float, q: float) -> np.ndarray:
    """A two-pole resonator (the ringing filter of the old tone circuits)."""
    r = np.exp(-np.pi * f / (q * SR))
    return lfilter([1 - r], [1, -2 * r * np.cos(2 * np.pi * f / SR), r * r], x)


def _out(y: np.ndarray, vel: float) -> np.ndarray:
    y = y / (np.abs(y).max() + 1e-9)
    return (y * (0.35 + 0.65 * vel)).astype(np.float32)


def thump(rng, vel=1.0, start=110.0, end=42.0, decay=0.32, drop=0.045, tone=0.15):
    """The kick: a sine falling from start to end Hz, with a soft square edge for tone."""
    t = _t(decay * 2.2)
    f = end + (start - end) * np.exp(-t / drop)
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(ph) + tone * np.tanh(4 * np.sin(ph))
    return _out(y * np.exp(-t / decay) * np.minimum(1, t / 0.0015), vel)


def chuff(rng, vel=1.0, centre=1400.0, q=1.6, decay=0.11, body=190.0, body_mix=0.35):
    """The snare: a burst of band-passed noise with a short pitched body underneath."""
    t = _t(decay * 4)
    n = rng.standard_normal(len(t))
    y = _reson(n, centre * (0.97 + 0.06 * rng.random()), q) * np.exp(-t / decay)
    y = y / (np.abs(y).max() + 1e-9) + body_mix * np.sin(2 * np.pi * body * t) * np.exp(-t / (decay * 0.6))
    return _out(y, vel)


def tick(rng, vel=1.0, decay=0.022, bright=7000.0):
    """The closed hat: a very short high-passed noise tick."""
    t = _t(decay * 5)
    y = _onepole(rng.standard_normal(len(t)), bright, high=True) * np.exp(-t / decay)
    return _out(y, vel)


def hiss(rng, vel=1.0, decay=0.2, bright=5500.0):
    """The open hat: a longer hiss with a metallic ring (two detuned resonators)."""
    t = _t(decay * 4)
    n = _onepole(rng.standard_normal(len(t)), bright, high=True)
    ring = _reson(n, 8100, 30) + _reson(n, 10700, 30)
    y = (n + 0.4 * ring / (np.abs(ring).max() + 1e-9) * np.abs(n).max()) * np.exp(-t / decay)
    return _out(y, vel)


def ping(rng, vel=1.0, freq=1760.0, decay=0.09, q=60.0):
    """A resonant ping: an impulse into a high-Q filter; the rim shot and the clock's tick."""
    t = _t(decay * 6)
    x = np.zeros(len(t))
    x[0] = 1.0
    x[1:40] += 0.2 * rng.standard_normal(39)
    y = _reson(x, freq, q) * np.exp(-t / decay)
    return _out(y, vel)


def plop(rng, vel=1.0, start=180.0, end=520.0, decay=0.12):
    """The water drop: a sine gliding upward as it fades; the Electronium's toms."""
    t = _t(decay * 4)
    f = start + (end - start) * (1 - np.exp(-t / (decay * 0.5)))
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / decay) * np.minimum(1, t / 0.002)
    return _out(y, vel)


def shimmer(rng, vel=1.0, decay=1.1, base=540.0):
    """The cymbal: ring-modulated square waves (non-harmonic partials) over noise, slowly decaying."""
    t = _t(decay * 3)
    sq = sum(np.sign(np.sin(2 * np.pi * base * r * t)) for r in (1.0, 1.4471, 1.6170, 1.9265, 2.5028, 2.6637))
    y = _onepole(sq / 6 * np.sign(np.sin(2 * np.pi * 3.17 * base * t)) + 0.3 * rng.standard_normal(len(t)), 4000, high=True)
    return _out(y * np.exp(-t / decay) * np.minimum(1, t / 0.003), vel)


def clack(rng, vel=1.0, decay=0.06):
    """The clap: three quick noise chuffs and a tail."""
    t = _t(decay * 5)
    env = np.zeros(len(t))
    for k, off in enumerate((0.0, 0.011, 0.023)):
        i = int(off * SR)
        env[i:] += np.exp(-(t[: len(t) - i]) / (0.006 if k < 2 else decay))
    y = _reson(rng.standard_normal(len(t)), 1250, 1.2) * env
    return _out(y, vel)


KIT = {
    "kick": ("thump", {}, "kick"),
    "snare": ("chuff", {}, "snare"),
    "clap": ("clack", {}, "snare"),
    "hat": ("tick", {}, "hats"),
    "open": ("hiss", {}, "hats"),
    "rim": ("ping", {"freq": 1760}, "perc"),
    "crash": ("shimmer", {}, "crash"),
    "tom_hi": ("plop", {"start": 260, "end": 700}, "toms"),
    "tom_mid": ("plop", {"start": 200, "end": 520}, "toms"),
    "tom_lo": ("plop", {"start": 140, "end": 360}, "toms"),
    "shaker": ("tick", {"decay": 0.045, "bright": 5000}, "perc"),
    "wood": ("ping", {"freq": 920, "q": 25, "decay": 0.05}, "perc"),
}
MAP = {36: "kick", 35: "kick", 38: "snare", 40: "snare", 39: "clap", 42: "hat", 44: "hat", 46: "open", 37: "rim", 49: "crash",
       57: "crash", 50: "tom_hi", 48: "tom_hi", 47: "tom_mid", 45: "tom_lo", 43: "tom_lo", 41: "tom_lo", 70: "shaker", 76: "wood"}


def kit() -> dict:
    """The kit in render_midi.py's drum-track format."""
    return {"map": dict(MAP),
            "sounds": {k: {"py": {"module": __file__, "fn": fn, "args": a}, "stem": st} for k, (fn, a, st) in KIT.items()},
            "stems": {"kick": {"hp": 28, "mono": True, "gain_db": -3.0},
                      "snare": {"hp": 140, "sends": {"spring": 0.25, "room": 0.15}, "gain_db": -7.0},
                      "hats": {"pan": 0.18, "gain_db": -9.0},
                      "perc": {"pan": -0.3, "sends": {"spring": 0.3}, "gain_db": -12.0},
                      "crash": {"pan": -0.2, "gain_db": -17.0},
                      "toms": {"sends": {"spring": 0.35, "echo": 0.1}, "width": 1.2, "gain_db": -9.0}}}
