"""Small stateful DSP pieces the engines share. State lives in plain dicts / arrays the engine keeps (and snapshots),
never in hidden globals, so an engine restored from a snapshot continues sample-exactly."""
from __future__ import annotations

import numpy as np
from scipy import signal


def hz(pitch: float) -> float:
    return 440.0 * 2.0 ** ((pitch - 69.0) / 12.0)


def cents(c: float) -> float:
    return 2.0 ** (c / 1200.0)


def ramp(a: float, b: float, n: int) -> np.ndarray:
    """a -> b across n samples (parameter smoothing between blocks, no zipper)."""
    return a + (b - a) * (np.arange(1, n + 1) / n)


def phases(ph: float, inc, n: int) -> tuple[np.ndarray, float]:
    """Running phase in cycles: inc per sample (scalar or (n,)); returns the n phases and the next start, wrapped."""
    if np.ndim(inc) == 0:
        p = ph + inc * np.arange(n)
        nxt = ph + inc * n
    else:
        c = np.cumsum(inc)
        p = ph + np.concatenate(([0.0], c[:-1]))
        nxt = ph + c[-1]
    return p, float(nxt % 1.0)


def additive(p: np.ndarray, f0: float, sr: int, bright: float, max_h: int = 16, odd: float = 0.0) -> np.ndarray:
    """A band-limited tone from phase p (cycles): harmonics k at 1/k^(2-bright), odd-weighted by odd, below Nyquist."""
    h = int(max(1, min(max_h, (sr * 0.45) // max(f0, 1.0))))
    k = np.arange(1, h + 1)
    w = 1.0 / k ** (2.0 - 1.4 * np.clip(bright, 0, 1))
    w = w * np.where(k % 2 == 0, 1.0 - odd, 1.0)
    w /= w.sum()
    return np.sin(2 * np.pi * np.outer(p, k)) @ w


def lp_coeffs(fc: float, sr: int, q: float = 0.707):
    fc = float(np.clip(fc, 20.0, sr * 0.45))
    return signal.butter(2, fc / (sr / 2), "low") if q == 0.707 else _rbj("lp", fc, sr, q)


def _rbj(kind: str, fc: float, sr: int, q: float):
    w = 2 * np.pi * fc / sr
    a = np.sin(w) / (2 * max(q, 0.1))
    c = np.cos(w)
    if kind == "lp":
        b = [(1 - c) / 2, 1 - c, (1 - c) / 2]
    elif kind == "hp":
        b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]
    else:                                                    # band-pass, peak gain 1
        b = [a, 0.0, -a]
    den = [1 + a, -2 * c, 1 - a]
    return np.array(b) / den[0], np.array(den) / den[0]


def biquad(kind: str, fc: float, sr: int, q: float = 0.707):
    return _rbj(kind, float(np.clip(fc, 20.0, sr * 0.45)), sr, q)


def filt(b, a, x: np.ndarray, zi: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
    """lfilter along axis 0 carrying state; x (n,) or (n, C)."""
    order = max(len(a), len(b)) - 1
    if zi is None or zi.shape[0] != order:
        zi = np.zeros((order,) + x.shape[1:])
    y, zf = signal.lfilter(b, a, x, axis=0, zi=zi)
    return y, zf


def soft(x, drive: float = 1.0):
    return np.tanh(x * drive) / np.tanh(max(drive, 1e-3)) if drive > 1e-3 else x


def stereo(x: np.ndarray, pan: float = 0.0) -> np.ndarray:
    a = (np.clip(pan, -1, 1) + 1) * np.pi / 4
    return np.stack([x * np.cos(a), x * np.sin(a)], 1) * np.sqrt(2)
