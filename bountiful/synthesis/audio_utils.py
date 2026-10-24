"""Measurements and safety for the Lab's engines: what tests assert, what the Lab's meters show.

  metrics(y)        peak, rms dBFS, crest, DC, spectral centroid / flatness, stereo width, onsets, silence
  safe(y)           NaN/inf removed, DC blocked, soft-limited under a ceiling
  pan(x, p)         equal-power mono -> stereo
  resonators(...)   a bank of 2-pole resonators driven by an excitation, state carried between blocks
"""
from __future__ import annotations

import numpy as np
from scipy import signal

SR = 44100


def mono(y: np.ndarray) -> np.ndarray:
    return y.mean(1) if y.ndim == 2 else y


def db(x: float) -> float:
    return float(20 * np.log10(max(float(x), 1e-12)))


def spectrum(y: np.ndarray, sr: int = SR, n: int = 8192) -> tuple[np.ndarray, np.ndarray]:
    """Mean magnitude spectrum (Welch), for the Lab's analyser and the tests."""
    x = mono(y).astype(float)
    if len(x) < 64:
        return np.zeros(1), np.zeros(1)
    f, p = signal.welch(x, sr, nperseg=min(n, len(x)))
    return f, p


def centroid(y: np.ndarray, sr: int = SR) -> float:
    f, p = spectrum(y, sr)
    return float((f * p).sum() / max(p.sum(), 1e-20))


def flatness(y: np.ndarray, sr: int = SR) -> float:
    """0 = a pure tone, 1 = white noise (geometric / arithmetic mean of the power spectrum)."""
    _, p = spectrum(y, sr)
    p = p[1:] + 1e-20
    return float(np.exp(np.log(p).mean()) / p.mean())


def onsets(y: np.ndarray, sr: int = SR, hop: int = 512) -> np.ndarray:
    """Onset times (s) by spectral flux peaks."""
    x = mono(y).astype(float)
    if len(x) < 4 * hop:
        return np.zeros(0)
    _, _, Z = signal.stft(x, sr, nperseg=2 * hop, noverlap=hop)
    mag = np.abs(Z)
    flux = np.maximum(np.diff(mag, axis=1), 0).sum(0)
    if flux.max() <= 0:
        return np.zeros(0)
    flux /= flux.max()
    thr = np.convolve(flux, np.ones(9) / 9, mode="same") + 0.08
    pk = [i for i in range(1, len(flux) - 1) if flux[i] > thr[i] and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1]]
    return np.array(pk) * hop / sr


def width(y: np.ndarray) -> float:
    """Side / mid energy: 0 = mono."""
    if y.ndim != 2:
        return 0.0
    m, s = (y[:, 0] + y[:, 1]) / 2, (y[:, 0] - y[:, 1]) / 2
    return float(np.sqrt((s ** 2).mean() / max((m ** 2).mean(), 1e-20)))


def metrics(y: np.ndarray, sr: int = SR) -> dict:
    x = mono(y)
    peak = float(np.abs(y).max()) if y.size else 0.0
    rms = float(np.sqrt((x.astype(float) ** 2).mean())) if x.size else 0.0
    return {"seconds": round(len(x) / sr, 3), "peak": round(peak, 4), "peak_db": round(db(peak), 2), "rms_db": round(db(rms), 2),
            "crest_db": round(db(peak) - db(rms), 2), "dc": round(float(x.mean()), 5) if x.size else 0.0,
            "centroid_hz": round(centroid(y, sr), 1), "flatness": round(flatness(y, sr), 4), "width": round(width(y), 3),
            "onsets": int(len(onsets(y, sr))), "finite": bool(np.isfinite(y).all()), "silent": rms < 1e-5}


def safe(y: np.ndarray, ceiling: float = 0.98) -> np.ndarray:
    y = np.nan_to_num(np.asarray(y, np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    b, a = [1, -1], [1, -0.9995]                                    # DC blocker
    y = signal.lfilter(b, a, y, axis=0)
    over = np.abs(y) > ceiling * 0.8
    if over.any():                                                  # soft knee above 80 % of the ceiling
        k = ceiling * 0.8
        y = np.where(over, np.sign(y) * (k + (ceiling - k) * np.tanh((np.abs(y) - k) / (ceiling - k))), y)
    return y.astype(np.float32)


def pan(x: np.ndarray, p: float | np.ndarray) -> np.ndarray:
    a = (np.clip(p, -1, 1) + 1) * np.pi / 4
    return np.stack([x * np.cos(a), x * np.sin(a)], 1) * np.sqrt(2)          # centre = unity in each side


def resonator_coeffs(freqs: np.ndarray, decays: np.ndarray, sr: int = SR) -> tuple[np.ndarray, np.ndarray]:
    """Two-pole resonators: pole radius from a T60 decay (s), angle from the frequency. Returns (a1, a2) arrays."""
    f = np.clip(freqs, 10, sr * 0.45)
    r = np.exp(-6.9078 / (np.maximum(decays, 1e-3) * sr))
    return -2 * r * np.cos(2 * np.pi * f / sr), r * r


def resonate(exc: np.ndarray, a1: np.ndarray, a2: np.ndarray, zi: np.ndarray | None = None
             ) -> tuple[np.ndarray, np.ndarray]:
    """Drive K resonators with exc (n,) or (n, K); returns ((n, K) outputs, (K, 2) state). Each mode is normalised
    so its peak gain stays near 1 whatever the decay."""
    K = len(a1)
    n = exc.shape[0]
    x = exc if exc.ndim == 2 else np.repeat(exc[:, None], K, 1)
    zi = np.zeros((K, 2)) if zi is None else zi
    out = np.empty((n, K))
    g = (1 - np.sqrt(np.maximum(a2, 0)))                           # ~ (1 - r): keeps long decays from towering
    for k in range(K):
        out[:, k], zi[k] = signal.lfilter([g[k]], [1.0, a1[k], a2[k]], x[:, k], zi=zi[k])
    return out, zi
