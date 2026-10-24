"""Breakforge's drum voices: every hit synthesised from oscillators and noise, no samples. Each function is
hit(rng, vel, **args) -> mono float32 at 44.1 kHz, so render_midi.py can play them as drum sounds
(py = { module = ".../breakforge_voices.py", fn = "snare", args = {...} }) and the Breakforge engine can play them
live. Standalone on purpose (numpy and scipy only): render_midi loads it by file path.

`grit` (0-1) on any voice: sample-and-hold decimation, bit reduction and drive, the sound of an old sampler.
"""
from __future__ import annotations

import zlib

import numpy as np
from scipy.signal import lfilter

SR = 44100
METAL = np.array([205.3, 304.4, 369.6, 522.7, 540.0, 800.0])     # six square oscillators, inharmonic: cymbal metal


def _t(sec: float) -> np.ndarray:
    return np.arange(max(1, int(sec * SR))) / SR


def _hp(x: np.ndarray, f: float) -> np.ndarray:
    a = np.exp(-2 * np.pi * f / SR)
    return x - lfilter([1 - a], [1, -a], x)


def _lp(x: np.ndarray, f: float) -> np.ndarray:
    a = np.exp(-2 * np.pi * min(f, SR * 0.45) / SR)
    return lfilter([1 - a], [1, -a], x)


def _bp(x: np.ndarray, f: float, q: float) -> np.ndarray:
    w = 2 * np.pi * min(f, SR * 0.45) / SR
    al = np.sin(w) / (2 * q)
    c = np.cos(w)
    return lfilter([al, 0, -al], [1 + al, -2 * c, 1 - al], x)


def _sweep(t: np.ndarray, start: float, end: float, tau: float) -> np.ndarray:
    f = end + (start - end) * np.exp(-t / tau)
    return 2 * np.pi * np.cumsum(f) / SR


def grit(y: np.ndarray, amount: float) -> np.ndarray:
    """Decimate (hold every k samples), quantise to fewer bits, drive: 0 leaves the sound alone."""
    if amount <= 1e-3:
        return y
    k = 1 + int(amount * 5)
    y = np.repeat(y[::k], k)[:len(y)]
    bits = 16 - amount * 10
    q = 2 ** (bits - 1)
    y = np.round(y * q) / q
    d = 1 + amount * 3
    return np.tanh(y * d) / np.tanh(d)


def _out(y: np.ndarray, vel: float, g: float = 0.0) -> np.ndarray:
    y = y / (np.abs(y).max() + 1e-9)
    y = grit(y, g)
    fade = min(len(y), 64)
    y[-fade:] *= np.linspace(1, 0, fade)
    return (y * (0.3 + 0.7 * vel)).astype(np.float32)


def kick(rng, vel=1.0, pitch=50.0, punch=190.0, drop=0.028, decay=0.26, click=0.35, drive=1.6, grit=0.0):
    """A falling sine (punch -> pitch Hz), a noise click on top, driven."""
    t = _t(decay * 2.5)
    y = np.sin(_sweep(t, punch, pitch, drop)) * np.exp(-t / decay)
    n = _hp(rng.standard_normal(len(t)), 2500) * np.exp(-t / 0.004)
    y = np.tanh((y + click * n) * drive) * np.minimum(1, t / 0.001)
    return _out(y, vel, grit)


def snare(rng, vel=1.0, tone=190.0, body=0.55, snap=0.7, crack=2200.0, decay=0.15, grit=0.0):
    """Two body modes (tone, 1.62 tone) under band-passed noise, with a hard transient (snap)."""
    t = _t(decay * 4)
    b = np.sin(_sweep(t, tone * 1.5, tone, 0.012)) + 0.5 * np.sin(2 * np.pi * tone * 1.62 * t)
    b *= np.exp(-t / (decay * 0.45))
    n = rng.standard_normal(len(t))
    nz = (0.6 * _bp(n, crack, 0.9) + 0.4 * _hp(n, 4500)) * np.exp(-t / decay)
    nz /= np.abs(nz).max() + 1e-9
    tr = _hp(n, 1500) * np.exp(-t / 0.002) * snap
    return _out(body * b + nz + tr, vel, grit)


def ghost(rng, vel=0.4, tone=210.0, crack=2600.0, decay=0.07, grit=0.0):
    """A ghost note: the snare played softly near the rim, short and thin."""
    return RAW["snare"](rng, vel, tone=tone, body=0.25, snap=0.3, crack=crack, decay=decay, grit=grit)


def _metal(rng, t: np.ndarray, scale: float) -> np.ndarray:
    ph = rng.random(len(METAL))
    return sum(np.sign(np.sin(2 * np.pi * (f * scale * t + p))) for f, p in zip(METAL, ph)) / len(METAL)


def hat(rng, vel=1.0, decay=0.032, tone=8500.0, metal=0.55, grit=0.0):
    """Closed hat: square-oscillator metal and noise, band-passed high."""
    t = _t(decay * 6)
    y = metal * _metal(rng, t, 1.0 + 0.04 * rng.random()) + (1 - metal) * rng.standard_normal(len(t))
    y = _hp(_bp(y, tone, 0.8), 6000) * np.exp(-t / decay)
    return _out(y, vel, grit)


def open_hat(rng, vel=1.0, decay=0.28, tone=8000.0, metal=0.6, grit=0.0):
    return RAW["hat"](rng, vel, decay=decay, tone=tone, metal=metal, grit=grit)


def ride(rng, vel=1.0, decay=1.3, bell=0.35, tone=5200.0, grit=0.0):
    """Ride: inharmonic partials (a few strong, bell-like) over a bright metallic wash."""
    t = _t(decay * 2.2)
    fr = np.array([510, 742, 1093, 1380, 2210, 3170]) * (0.98 + 0.04 * rng.random())
    bl = sum(np.sin(2 * np.pi * f * t + 6.283 * rng.random()) * np.exp(-t / (decay * (0.6 - 0.07 * i)))
             for i, f in enumerate(fr)) / len(fr)
    wash = _hp(_bp(_metal(rng, t, 2.6) + 0.4 * rng.standard_normal(len(t)), tone, 0.6), 3000) * np.exp(-t / (decay * 0.45))
    ping = _hp(rng.standard_normal(len(t)), 7000) * np.exp(-t / 0.006)
    return _out(bell * bl + wash + 0.5 * ping, vel, grit)


def crash(rng, vel=1.0, decay=1.8, tone=6000.0, grit=0.0):
    """Crash: noise and metal, opening fast and darkening as it decays."""
    t = _t(decay * 2.2)
    y = _metal(rng, t, 3.1) * 0.5 + rng.standard_normal(len(t))
    y = _hp(y, 900)
    bright = _hp(y, tone) * np.exp(-t / (decay * 0.3))
    y = _lp(y, tone * 1.2) * np.exp(-t / decay) * 0.6 + bright
    return _out(y * np.minimum(1, t / 0.002), vel, grit)


def rim(rng, vel=1.0, freq=1650.0, decay=0.035, grit=0.0):
    """Rim shot: a short resonant ping with a click."""
    t = _t(decay * 5)
    y = np.sin(2 * np.pi * freq * t) * np.exp(-t / decay) + 0.6 * np.sin(2 * np.pi * freq * 2.4 * t) * np.exp(-t / (decay * 0.5))
    y += _hp(rng.standard_normal(len(t)), 3000) * np.exp(-t / 0.002)
    return _out(y, vel, grit)


def tom(rng, vel=1.0, pitch=120.0, decay=0.22, skin=0.25, grit=0.0):
    """Tom: a sine bending down a little onto its pitch, with a touch of skin noise."""
    t = _t(decay * 3)
    y = np.sin(_sweep(t, pitch * 1.6, pitch, 0.03)) * np.exp(-t / decay)
    y += skin * _bp(rng.standard_normal(len(t)), pitch * 6, 1.5) * np.exp(-t / (decay * 0.3))
    return _out(y, vel, grit)


def swell(rng, vel=1.0, length=0.35, tone=5000.0, grit=0.0):
    """A reversed cymbal / snare tail rising into the next downbeat (the reverse mutation and phrase fills)."""
    t = _t(length)
    y = _hp(rng.standard_normal(len(t)) + 0.5 * _metal(rng, t, 2.0), 800)
    y = _lp(y, tone) * np.exp(-t / (length * 0.35))
    return _out(y[::-1].copy(), vel, grit)


RAW = {"kick": kick, "snare": snare, "ghost": ghost, "hat": hat, "open_hat": open_hat, "ride": ride, "crash": crash,
       "rim": rim, "tom": tom, "swell": swell}
TAKES = 12                     # round-robin takes per voice setting
_CACHE: dict = {}


def _taken(name: str):
    """The voice as a song's drum track plays it: one of TAKES takes (picked by rng) per setting, synthesised once at
    full velocity and scaled (every voice scales by 0.3 + 0.7 vel), so a song's thousands of hits cost a few dozen."""
    f = RAW[name]

    def hit(rng, vel=1.0, **args):
        take = int(rng.integers(TAKES))
        key = (name, take, tuple(sorted(args.items())))
        y = _CACHE.get(key)
        if y is None:
            if len(_CACHE) > 400:
                _CACHE.clear()
            y = f(np.random.default_rng([zlib.crc32(repr(key[::2]).encode()), take]), 1.0, **args)
            _CACHE[key] = y
        return y * np.float32(0.3 + 0.7 * vel)
    hit.__name__ = hit.__qualname__ = name
    hit.__doc__ = f.__doc__
    return hit


for _n in RAW:
    globals()[_n] = _taken(_n)
VOICES = {"kick": kick, "snare": snare, "ghost": ghost, "hat": hat, "open": open_hat, "ride": ride,  # noqa: F821
          "crash": crash, "rim": rim, "tom": tom, "swell": swell}                                     # noqa: F821
