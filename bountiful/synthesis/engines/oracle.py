"""Oracle: analyses a local WAV and resynthesises it at the notes you play, wandering its timeline by similarity.

Analysis (once per file, cached, at most 30 s of audio; no neural models, just signal processing):
  STFT 2048 / hop 512, then per frame
    f0        normalised autocorrelation peak between 60 Hz and 1 kHz, with a voicing strength
    harm      the amplitudes of the first 32 harmonics of that f0 (the source's own timbre)
    env       the spectral envelope (peak-held, smoothed) on 64 log-spaced points, 40 Hz - 16 kHz (its formants)
    noise     the noise floor (min-held, smoothed) on the same points (its breath)
    loud      RMS
  and a similarity graph: each frame's 6 nearest frames by (env, loudness), the "oracle" of where the sound could go.

Resynthesis: every note gets a read head into the analysis. It moves at `speed` (0 freezes) from `start`, and
whenever it crosses a frame it may jump to one of that frame's neighbours (`predict`), so the sound continues in
ways the recording never did but always could have. The note's partials take their amplitudes from the source's
formants at the note's pitch (`formant` = 1, a voice singing the new note) or from the source's harmonic shape
(`formant` = 0, the instrument transposed); `contour` lays the source's own pitch movement on top. The noise floor
is resynthesised as shaped noise. Without a source file it analyses a seeded synthetic vowel, so it always plays.
"""
from __future__ import annotations

import os

import numpy as np
from scipy import ndimage

from synthesis.engine_api import Engine, Param
from synthesis.engines._dsp import hz

N, HOP = 2048, 512
NN, NHOP = 1024, 256                                   # noise resynthesis frames
PTS = np.geomspace(40.0, 16000.0, 64)
H = 32
CTRL = 256
MAX_SEC = 30.0
_MODELS: dict = {}


def _vowel(seed: int, sr: int, sec: float = 3.0) -> np.ndarray:
    """A seeded synthetic voice: glottal pulses with vibrato through moving vowel formants, plus breath."""
    r = np.random.default_rng([seed & 0x7FFFFFFF, 53])
    n = int(sec * sr)
    t = np.arange(n) / sr
    f0 = 140 * (1 + 0.012 * np.sin(2 * np.pi * 5.2 * t)) * (1 + 0.15 * np.sin(2 * np.pi * 0.3 * t + r.random() * 6))
    ph = np.cumsum(f0) / sr
    src = (ph % 1.0) ** 3 - 0.25
    vowels = np.array([[730, 1090, 2440], [530, 1840, 2480], [270, 2290, 3010], [570, 840, 2410], [300, 870, 2240]])
    order = r.permutation(5)
    seg = np.minimum((t / sec * 5).astype(int), 4)
    nxt = np.minimum(seg + 1, 4)
    frac = (t / sec * 5) % 1.0
    F = vowels[order[seg]] * (1 - frac[:, None]) + vowels[order[nxt]] * frac[:, None]
    y = np.zeros(n)
    from scipy.signal import lfilter
    for j in range(3):                                   # formants as slowly-varying resonators, piecewise per 512
        for s in range(0, n, 512):
            fc, bw = F[s, j], 80 + 40 * j
            rr = np.exp(-np.pi * bw / sr)
            a = [1, -2 * rr * np.cos(2 * np.pi * fc / sr), rr * rr]
            y[s:s + 512] += lfilter([1 - rr], a, src[s:s + 512]) / (j + 1)
    y += 0.02 * r.standard_normal(n)
    return y / (np.abs(y).max() + 1e-9)


def _load(path: str, sr: int) -> np.ndarray:
    from scipy.io import wavfile
    rate, x = wavfile.read(path)
    x = x.astype(np.float64)
    if np.issubdtype(np.asarray(x).dtype, np.integer) or np.abs(x).max() > 1.5:
        x = x / max(np.abs(x).max(), 1.0)
    if x.ndim > 1:
        x = x.mean(1)
    x = x[:int(MAX_SEC * rate)]
    if rate != sr:
        from scipy.signal import resample_poly
        g = np.gcd(int(rate), int(sr))
        x = resample_poly(x, sr // g, int(rate) // g)
    return x / (np.abs(x).max() + 1e-9)


def analyse(x: np.ndarray, sr: int) -> dict:
    """The oracle model of a mono signal (see the module docstring)."""
    x = np.concatenate([x, np.zeros(N)])
    nf = max(1, (len(x) - N) // HOP)
    win = np.hanning(N)
    fr = np.lib.stride_tricks.sliding_window_view(x, N)[::HOP][:nf] * win
    X = np.abs(np.fft.rfft(fr, axis=1))                                   # (F, 1025)
    fb = np.fft.rfftfreq(N, 1 / sr)
    # f0: normalised autocorrelation
    ac = np.fft.irfft(X ** 2, axis=1)[:, :N // 2]
    ac = ac / (ac[:, :1] + 1e-12)
    lo, hi = int(sr / 1000), int(sr / 60)
    lag = lo + ac[:, lo:hi].argmax(1)
    voiced = np.clip(ac[np.arange(nf), lag], 0, 1)
    f0 = sr / lag
    # harmonic amplitudes at k f0
    k = np.arange(1, H + 1)
    bins = np.clip(np.round(np.outer(f0, k) * N / sr).astype(int), 0, len(fb) - 1)
    harm = np.take_along_axis(X, bins, 1) * (np.outer(f0, k) < sr * 0.45)
    harm = harm / (np.sqrt((harm ** 2).sum(1, keepdims=True)) + 1e-12)
    # envelope (peaks) and noise floor (troughs), on log points
    env = ndimage.uniform_filter1d(ndimage.maximum_filter1d(X, 9, axis=1), 9, axis=1)
    flo = ndimage.uniform_filter1d(ndimage.minimum_filter1d(X, 15, axis=1), 15, axis=1)
    idx = np.clip(np.round(PTS * N / sr).astype(int), 0, len(fb) - 1)
    lenv, lnoise = np.log(env[:, idx] + 1e-6), np.log(flo[:, idx] + 1e-6)
    loud = np.sqrt((fr ** 2).mean(1)) / 0.375
    loud = loud / (loud.max() + 1e-9)
    # the oracle: nearest frames by shape and loudness
    feat = np.concatenate([lenv - lenv.mean(1, keepdims=True), 4 * np.log(loud[:, None] + 1e-3)], 1)
    knn = np.zeros((nf, 6), int)
    for s in range(0, nf, 256):
        d = ((feat[s:s + 256, None, :] - feat[None, :, :]) ** 2).sum(-1)
        rows = np.arange(s, min(s + 256, nf))
        d[np.arange(len(rows)), rows] = np.inf                            # not itself ...
        d[np.arange(len(rows)), np.minimum(rows + 1, nf - 1)] = np.inf    # ... nor simply the next frame
        kk = min(6, max(1, nf - 2))
        knn[rows, :kk] = np.argsort(d, 1)[:, :kk]
    return {"f0": f0, "voiced": voiced, "harm": harm, "env": lenv, "noise": lnoise, "loud": loud, "knn": knn,
            "frames": nf, "median_f0": float(np.median(f0[voiced > 0.5])) if (voiced > 0.5).any() else 150.0}


def model(assets: dict, seed: int, sr: int) -> tuple[dict, str]:
    path = (assets or {}).get("source")
    if path and os.path.isfile(path):
        key = (os.path.abspath(path), os.path.getmtime(path), sr)
        label = os.path.basename(path)
    else:
        key, label = ("vowel", seed, sr), "synthetic vowel (no source file)"
    if key not in _MODELS:
        if len(_MODELS) > 8:
            _MODELS.clear()
        x = _load(path, sr) if key[0] != "vowel" else _vowel(seed, sr)
        _MODELS[key] = analyse(x, sr)
    return _MODELS[key], label


class Oracle(Engine):
    ID = "oracle"
    NAME = "Oracle"
    VERSION = 1
    DESCRIPTION = "Local WAV analysis (f0, harmonics, formants, noise, similarity graph) resynthesised at your notes."
    POLY = 6
    PARAMS = (
        Param("start", 0.0, 0.0, 1.0, doc="where in the source the read heads begin"),
        Param("speed", 1.0, 0.0, 4.0, doc="read-head speed (0 freezes the sound)"),
        Param("predict", 0.2, 0.0, 1.0, doc="chance per frame of jumping to a similar moment"),
        Param("spread", 0.0, 0.0, 1.0, doc="each note starts at a different (seeded) moment"),
        Param("formant", 0.7, 0.0, 1.0, doc="keep the source's formants (1) or its harmonic shape (0)"),
        Param("contour", 0.0, 0.0, 1.0, doc="lay the source's own pitch movement on the notes"),
        Param("noise", 0.5, 0.0, 2.0, doc="level of the resynthesised breath / noise floor"),
        Param("harmonics", 24, 1, 32, "int"),
        Param("bright", 0.0, -1.0, 1.0, doc="tilt the resynthesis"),
        Param("dynamics", 0.8, 0.0, 1.0, doc="follow the source's loudness"),
        Param("attack", 0.02, 0.0, 4.0, unit="s"),
        Param("release", 0.5, 0.01, 8.0, unit="s"),
        Param("width", 0.5, 0.0, 1.0),
        Param("level", 1.0, 0.0, 2.0),
    )
    PRESETS = {
        "singing-source": {"formant": 1.0, "speed": 1.0, "predict": 0.1, "noise": 0.4},
        "frozen-moment": {"speed": 0.0, "start": 0.4, "formant": 0.8, "attack": 0.6, "release": 2.5, "noise": 0.8,
                          "width": 0.8},
        "dreaming-oracle": {"speed": 0.6, "predict": 0.7, "spread": 1.0, "attack": 0.3, "release": 2.0,
                            "contour": 0.4},
        "transposed-instrument": {"formant": 0.0, "speed": 1.2, "predict": 0.0, "dynamics": 1.0, "noise": 0.2},
        "whisper": {"noise": 2.0, "harmonics": 4, "formant": 1.0, "bright": 0.4, "speed": 0.5, "predict": 0.4},
        "slow-scan": {"speed": 0.15, "predict": 0.3, "spread": 0.5, "attack": 1.0, "release": 3.0, "bright": -0.3},
    }

    def init_state(self) -> None:
        self.m, self.source = model(self.assets, self.seed, self.sr)
        self.acc = np.zeros((NN, 2))
        self.nbuf = np.zeros((0, 2))
        self.win = np.sqrt(np.hanning(NN + 1)[:NN])
        self.frame_sec = HOP / self.sr

    def state(self) -> dict:
        return {"acc": self.acc, "nbuf": self.nbuf}

    def load_state(self, d: dict) -> None:
        self.acc = np.asarray(d["acc"], float).reshape(NN, 2)
        self.nbuf = np.asarray(d["nbuf"], float).reshape(-1, 2)

    def describe_source(self) -> dict:
        m = self.m
        return {"source": self.source, "frames": m["frames"], "seconds": round(m["frames"] * self.frame_sec, 2),
                "median_f0": round(m["median_f0"], 1), "voiced": round(float((m["voiced"] > 0.5).mean()), 2)}

    def on_note(self, v: dict) -> None:
        F = self.m["frames"]
        off = self.rng.random() * self.v["spread"]
        v["pos"] = ((self.v["start"] + off) % 1.0) * max(F - 1, 1)
        v["ph"] = self.rng.random(H)
        v["amp"] = np.zeros(H)

    def alive(self, v: dict) -> bool:
        return v["gate"] or v["rel"] < self.v["release"] * self.sr

    def _env(self, v: dict, pos: int, m: int) -> np.ndarray:
        i = np.arange(m)
        att = np.clip((v["age"] + pos + i) / max(self.v["attack"] * self.sr, 1.0), 0, 1)
        if v["gate"]:
            return att
        return att * np.exp(-6.9 * (v["rel"] + pos + i) / max(self.v["release"] * self.sr, 1.0))

    def _advance(self, v: dict, sec: float) -> None:
        m, V = self.m, self.v
        F = m["frames"]
        old = int(v["pos"])
        v["pos"] = (v["pos"] + V["speed"] * sec / self.frame_sec) % F
        for _ in range(min(int(v["pos"]) - old if int(v["pos"]) >= old else 1, 8)):
            if self.rng.random() < V["predict"] * 0.25:
                v["pos"] = float(m["knn"][int(v["pos"]) % F, self.rng.integers(m["knn"].shape[1])])
                break

    def _partials(self, v: dict) -> tuple:
        m, V = self.m, self.v
        f = int(v["pos"]) % m["frames"]
        ratio = (m["f0"][f] / m["median_f0"]) ** V["contour"] if m["voiced"][f] > 0.5 else 1.0
        f0 = hz(v["pitch"]) * ratio
        K = int(min(V["harmonics"], max(1, (self.sr * 0.45) // f0)))
        k = np.arange(1, K + 1)
        fk = f0 * k
        form = np.exp(np.interp(np.log(fk), np.log(PTS), m["env"][f]))
        form = form / (np.sqrt((form ** 2).sum()) + 1e-12)
        shape = m["harm"][f][:K] + 1e-9
        shape = shape / np.sqrt((shape ** 2).sum())
        a = V["formant"] * form + (1 - V["formant"]) * shape
        a = a * k ** (V["bright"] * 0.8)
        a = a / (np.sqrt((a ** 2).sum()) + 1e-12)
        loud = (1 - V["dynamics"]) + V["dynamics"] * m["loud"][f] * (0.4 + 0.6 * m["voiced"][f])
        amp = np.zeros(H)
        amp[:K] = a * loud * v["vel"]
        return fk, K, amp, f

    def synth(self, n: int, inp) -> np.ndarray:
        V = self.v
        out = np.zeros((n, 2))
        pos = 0
        while pos < n:
            mm = min(CTRL, n - pos)
            i = np.arange(mm)
            for v in self.voices:
                fk, K, amp, fr = self._partials(v)
                env = self._env(v, pos, mm)
                a = v["amp"][None, :K] + (amp[None, :K] - v["amp"][None, :K]) * ((i + 1) / mm)[:, None]
                s = (np.sin(2 * np.pi * (v["ph"][None, :K] + np.outer(i, fk / self.sr))) * a).sum(1) * env
                out[pos:pos + mm] += s[:, None]
                v["ph"][:K] = (v["ph"][:K] + fk / self.sr * mm) % 1.0
                v["amp"] = amp
                v["frame"], v["envlast"] = fr, float(env[-1])
                self._advance(v, mm / self.sr)
            pos += mm
        if V["noise"] > 0:
            while len(self.nbuf) < n:
                self.nbuf = np.concatenate([self.nbuf, self._noise_frame()])
            out += self.nbuf[:n] * V["noise"]
            self.nbuf = self.nbuf[n:]
        return (out * 0.3 * V["level"]).astype(np.float32)

    def _noise_frame(self) -> np.ndarray:
        """One hop of the voices' noise floors, as shaped noise (OLA, independent channels as width rises)."""
        m = self.m
        nb = NN // 2 + 1
        fb = np.maximum(np.fft.rfftfreq(NN, 1 / self.sr), 1.0)
        mag = np.zeros(nb)
        for v in self.voices:
            f = v.get("frame", int(v["pos"]) % m["frames"])
            g = v.get("envlast", 0.0) * v["vel"] * m["loud"][f]
            if g > 1e-4:
                mag += g * np.exp(np.interp(np.log(fb), np.log(PTS), m["noise"][f]))
        if mag.any():
            mag = mag / (np.sqrt(2 * (mag ** 2).sum()) / NN + 1e-9) * 0.05 * min(1.0, mag.max())
        ph = self.rng.random(nb) * 2 * np.pi
        ph2 = ph + self.v["width"] * (self.rng.random(nb) - 0.5) * np.pi
        fr = np.stack([np.fft.irfft(mag * np.exp(1j * p), NN) * self.win for p in (ph, ph2)], 1)
        self.acc += fr
        done = self.acc[:NHOP].copy()
        self.acc = np.concatenate([self.acc[NHOP:], np.zeros((NHOP, 2))])
        return done


ENGINE = Oracle
