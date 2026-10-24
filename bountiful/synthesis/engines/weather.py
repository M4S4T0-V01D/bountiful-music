"""Spectral Weather: a pressure field over the spectrum, with wind, humidity, storms and seasons, heard as noise.

The field is 48 log-spaced bands (30 Hz - 18 kHz) of log-pressure. Every frame (2048-point, hop 512) it evolves:
  wind       advects the field along the frequency axis (`drift` picks the direction): weather fronts sweeping up
             or down the spectrum
  humidity   diffuses neighbouring bands into each other and pulls the climate darker
  turbulence seeded random walk per band
  climate    the field relaxes towards a baseline (`tilt`), which the `seasons` slowly reshape (seeded sinusoids)
  storms     seeded pressure cells that form at a random band, grow, drift with the wind and die; with `lightning`
             a storm can crack (one broadband frame) and leave a slow low rumble behind
The spectrum is built by interpolating the field onto the FFT bins, given random phases (independent per channel as
`width` rises) and overlap-added with a sqrt-Hann window.

Notes condense the weather: each held note draws the pressure into its harmonic series (Gaussian peaks, narrower with
`clarity`), so pitch emerges out of the wind like air over bottles, and clear peaks keep phase-coherent so they whistle.
The output is delivered from a FIFO of finished hops, and frames read the voices as they stand at the frame's start,
so the sound does not depend on how the host splits blocks.
"""
from __future__ import annotations

import numpy as np

from synthesis.engine_api import Engine, Param
from synthesis.engines._dsp import hz

N = 2048
HOP = 512
BANDS = 48
LO, HI = 30.0, 18000.0


class Weather(Engine):
    ID = "weather"
    NAME = "Spectral Weather"
    VERSION = 1
    DESCRIPTION = "A spectral pressure field with wind, humidity, storms and seasons; notes condense pitch out of it."
    POLY = 8
    PARAMS = (
        Param("pressure", 0.5, 0.0, 1.0, doc="how dense the weather bed is"),
        Param("wind", 0.3, 0.0, 1.0, doc="how fast fronts sweep along the spectrum"),
        Param("drift", 0.4, -1.0, 1.0, doc="wind direction: up (+) or down (-) the spectrum"),
        Param("humidity", 0.4, 0.0, 1.0, doc="diffusion between bands, darker climate"),
        Param("turbulence", 0.3, 0.0, 1.0, doc="random walk of each band"),
        Param("tilt", -0.3, -1.0, 1.0, doc="the climate's brightness"),
        Param("seasons", 0.3, 0.0, 1.0, doc="slow reshaping of the climate"),
        Param("season_rate", 0.05, 0.005, 1.0, unit="Hz"),
        Param("storm", 0.2, 0.0, 1.0, doc="how often storm cells form and how strong"),
        Param("lightning", 0.2, 0.0, 1.0, doc="chance a storm cracks and leaves rumble"),
        Param("condense", 0.6, 0.0, 1.0, doc="how strongly notes draw the weather into their harmonics"),
        Param("clarity", 0.5, 0.0, 1.0, doc="narrow, coherent peaks (whistle) vs broad ones (breath)"),
        Param("partials", 12, 1, 32, "int"),
        Param("rolloff", 0.8, 0.0, 2.0, doc="harmonic falloff"),
        Param("attack", 0.15, 0.0, 4.0, unit="s"),
        Param("release", 0.8, 0.01, 8.0, unit="s"),
        Param("width", 0.7, 0.0, 1.0),
        Param("level", 1.0, 0.0, 2.0),
    )
    PRESETS = {
        "drizzle": {"pressure": 0.35, "wind": 0.15, "humidity": 0.7, "tilt": -0.1, "storm": 0.05, "condense": 0.5,
                    "clarity": 0.3},
        "monsoon-front": {"pressure": 0.7, "wind": 0.7, "drift": -0.6, "humidity": 0.8, "storm": 0.5,
                          "lightning": 0.5, "condense": 0.4, "tilt": -0.5},
        "dry-whistle": {"pressure": 0.3, "wind": 0.4, "humidity": 0.1, "condense": 0.9, "clarity": 0.9,
                        "partials": 8, "tilt": 0.2, "storm": 0.0},
        "thunderhead": {"pressure": 0.55, "storm": 0.9, "lightning": 0.9, "humidity": 0.5, "wind": 0.3,
                        "condense": 0.3, "release": 3.0},
        "aurora": {"pressure": 0.4, "seasons": 0.9, "season_rate": 0.12, "wind": 0.2, "drift": 0.9,
                   "condense": 0.75, "clarity": 0.7, "partials": 20, "rolloff": 0.5, "attack": 1.0, "release": 4.0},
        "desert-heat": {"pressure": 0.45, "humidity": 0.0, "turbulence": 0.8, "tilt": 0.5, "wind": 0.5,
                        "storm": 0.1, "condense": 0.6, "clarity": 0.6},
    }

    def init_state(self) -> None:
        self.cf = np.geomspace(LO, HI, BANDS)
        self.field = np.zeros(BANDS)
        self.storms: list = []
        self.rumble = 0.0
        self.crack = 0.0
        self.frame = 0
        self.acc = np.zeros((N, 2))
        self.buf = np.zeros((0, 2))
        self.coh = np.zeros(N // 2 + 1)
        r = np.random.default_rng([self.seed & 0x7FFFFFFF, 31])
        self.season_ph = r.random((3, 2))                  # three slow climate waves (phase, band offset)
        self.win = np.sqrt(np.hanning(N + 1)[:N])
        self.binhz = self.sr / N

    def state(self) -> dict:
        return {"field": self.field, "storms": self.storms, "rumble": self.rumble, "crack": self.crack,
                "frame": self.frame, "acc": self.acc, "buf": self.buf, "coh": self.coh}

    def load_state(self, d: dict) -> None:
        self.field = np.asarray(d["field"], float)
        self.storms = [dict(s) for s in d.get("storms", [])]
        self.rumble, self.crack, self.frame = float(d["rumble"]), float(d["crack"]), int(d["frame"])
        self.acc = np.asarray(d["acc"], float).reshape(N, 2)
        self.buf = np.asarray(d["buf"], float).reshape(-1, 2)
        self.coh = np.asarray(d["coh"], float)

    def on_note(self, v: dict) -> None:
        v["amt"] = 0.0

    def alive(self, v: dict) -> bool:
        return v["gate"] or v.get("amt", 0.0) > 1e-3

    def synth(self, n: int, inp) -> np.ndarray:
        while len(self.buf) < n:
            self.buf = np.concatenate([self.buf, self._frame()])
        out, self.buf = self.buf[:n], self.buf[n:]
        return (out * self.v["level"]).astype(np.float32)

    # one frame of weather ------------------------------------------------------------------------------------------
    def _climate(self) -> np.ndarray:
        V = self.v
        oct_ = np.log2(self.cf / 1000.0)
        base = (V["tilt"] - 1) * 0.35 * oct_ - V["humidity"] * 0.3 * np.clip(oct_, 0, None)   # pink at tilt 0
        t = self.frame * HOP / self.sr
        for j, (ph, off) in enumerate(self.season_ph):
            rate = V["season_rate"] * (1 + 0.37 * j)
            base = base + V["seasons"] * 0.9 * np.sin(2 * np.pi * (rate * t + ph) + (off * 6 + j) *
                                                      np.arange(BANDS) / BANDS * np.pi * 2)
        return base

    def _evolve(self) -> np.ndarray:
        V, rng = self.v, self.rng
        idx = np.arange(BANDS, dtype=float)
        shift = V["wind"] * 0.6 * V["drift"]
        f = np.interp(idx - shift, idx, self.field)
        lap = np.concatenate([[f[1] - f[0]], f[2:] - 2 * f[1:-1] + f[:-2], [f[-2] - f[-1]]])
        f = f + V["humidity"] * 0.35 * lap
        f = f + (self._climate() - f) * 0.04
        f = f + V["turbulence"] * 0.18 * rng.standard_normal(BANDS)
        self.field = np.clip(f, -6, 6)

        if rng.random() < V["storm"] * 0.06:               # a new storm cell
            self.storms.append({"band": float(rng.random() * BANDS), "amp": 0.0, "peak": 0.6 + 1.2 * V["storm"] *
                                rng.random(), "w": 1.5 + 4 * rng.random(), "age": 0, "life": int(20 + 120 * rng.random()),
                                "bolt": bool(rng.random() < V["lightning"])})
        bump = np.zeros(BANDS)
        keep = []
        for s in self.storms[:12]:
            s["age"] += 1
            s["band"] = float(np.clip(s["band"] + shift * 1.5, 0, BANDS - 1))
            x = s["age"] / s["life"]
            s["amp"] = s["peak"] * np.sin(np.pi * min(x, 1.0)) ** 2
            if s["bolt"] and abs(x - 0.5) < 0.5 / s["life"] + 1e-9:
                self.crack = 0.5 + V["lightning"]
                self.rumble = max(self.rumble, s["peak"])
            bump += s["amp"] * np.exp(-((idx - s["band"]) / s["w"]) ** 2)
            if x < 1.0:
                keep.append(s)
        self.storms = keep
        bump += self.rumble * np.exp(-(idx / 6.0) ** 2) * 0.8          # thunder rolls in the low bands
        self.rumble *= 0.985
        bump += self.crack
        self.crack *= 0.25 if self.crack > 0.01 else 0.0
        return self.field + np.clip(bump, 0, 2.2)

    def _mask(self, nb: int) -> tuple:
        """The harmonic peaks of the held notes on the FFT bins, and how present the notes are overall."""
        V = self.v
        a_att = 1 - np.exp(-HOP / (max(V["attack"], 1e-3) * self.sr))
        a_rel = 1 - np.exp(-HOP / (max(V["release"], 1e-3) * self.sr))
        bins = np.arange(nb, dtype=float)
        mask = np.zeros(nb)
        pres = 0.0
        for v in self.voices:
            tgt = v["vel"] if v["gate"] else 0.0
            v["amt"] += (tgt - v["amt"]) * (a_att if v["gate"] else a_rel)
            if v["amt"] < 1e-4:
                continue
            pres = max(pres, v["amt"])
            f0 = hz(v["pitch"])
            for h in range(1, int(V["partials"]) + 1):
                f = f0 * h
                if f > self.sr * 0.45:
                    break
                c = f / self.binhz
                w = max(0.55, (1 - V["clarity"]) * f * 0.04 / self.binhz + 0.55)
                lo, hi = max(0, int(c - 4 * w)), min(nb, int(c + 4 * w) + 2)
                mask[lo:hi] += v["amt"] * h ** -V["rolloff"] * np.exp(-0.5 * ((bins[lo:hi] - c) / w) ** 2)
        return mask, min(pres, 1.0)

    def _frame(self) -> np.ndarray:
        V, rng = self.v, self.rng
        nb = N // 2 + 1
        fb = np.arange(nb) * self.binhz
        logp = self._evolve()
        lf = np.log(np.maximum(fb, 1.0))
        bed = np.exp(np.interp(lf, np.log(self.cf), logp))
        bed[fb < 20] = 0
        clim = np.exp(np.interp(lf, np.log(self.cf), self._climate()))
        clim[fb < 20] = 0
        bed *= 0.1 * (0.3 + V["pressure"]) / (np.sqrt(2 * (clim ** 2).sum()) / N + 1e-9)   # climate-level bed ~ -20 dB
        mask, pres = self._mask(nb)
        c = V["condense"]
        mag = bed * (1 - c * pres) + (bed + bed.mean()) * c * mask * 3.0
        q = np.clip(V["clarity"] * mask / (mask.max() + 1e-9), 0, 1) if pres > 0 else 0.0
        self.coh = (self.coh + 2 * np.pi * np.arange(nb) * HOP / N) % (2 * np.pi)
        ph_l = rng.random(nb) * 2 * np.pi
        ph_r = ph_l + V["width"] * (rng.random(nb) - 0.5) * np.pi
        xs = []
        for ph in (ph_l, ph_r):
            X = mag * ((1 - q) * np.exp(1j * ph) + q * np.exp(1j * self.coh))
            xs.append(np.fft.irfft(X, N) * self.win)
        self.acc += np.stack(xs, 1) * 0.7
        done = self.acc[:HOP].copy()
        self.acc = np.concatenate([self.acc[HOP:], np.zeros((HOP, 2))])
        self.frame += 1
        return np.tanh(done * 0.7) / 0.7


ENGINE = Weather
