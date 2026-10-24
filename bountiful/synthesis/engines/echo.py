"""Echo Organism: a colony of delay cells feeding each other through a bounded feedback graph, keeping itself alive.

Each of the `cells` (2-8) is a delay line (6 ms - 1.5 s) followed by a resonant low-pass (its colour) and a tanh
(its skin). The cells feed each other through a seeded sparse matrix W, rescaled so its spectral radius is `feedback`
(< 1): with the tanh, every cell's output stays within ±1, so the colony is bounded however it is wired.

It behaves like an organism:
  metabolism  each cell measures its own energy every control step; a cell louder than `limit` lowers its gain, a
              quiet one recovers towards 1 + hunger · 0.3. With hunger high the colony can sing on by itself (and still
              cannot blow up); with hunger 0 it is a pure echo network that dies away.
  tuning      notes retune the delays to multiples of the note's period (`tune`), gliding there (`glide`), so the
              colony rings at the note like plucked strings; tune 0 leaves the free echo times.
  growth      every `generation` seconds one edge of W is rewired (seeded), when `mutate` > 0.
Notes bite into the colony with a short seeded noise burst (`bite` ms), and audio routed into the engine
(the "audio_in" capability) feeds every cell, so it can live on another engine's sound.

Delays are at least two control steps long, so a whole step can be read before it is written: block-vectorised and
exact across snapshots (buffers, write position, filter states and gains are the state).
"""
from __future__ import annotations

import numpy as np

from synthesis.engine_api import CAPS_BASE, Engine, Param
from synthesis.engines._dsp import biquad, filt, hz

CTRL = 128
MAXD = 1.5


class Echo(Engine):
    ID = "echo"
    NAME = "Echo Organism"
    VERSION = 1
    DESCRIPTION = "Self-regulating colony of delay cells and resonators in a bounded feedback graph; hears audio input."
    CAPS = CAPS_BASE | {"audio_in"}
    POLY = 8
    PARAMS = (
        Param("cells", 5, 2, 8, "int"),
        Param("time", 0.25, 0.006, MAXD, unit="s", doc="the colony's typical echo time"),
        Param("scatter", 0.6, 0.0, 1.0, doc="how different the cells' times are"),
        Param("feedback", 0.7, 0.0, 0.97, doc="spectral radius of the wiring: how long echoes live"),
        Param("density", 0.5, 0.1, 1.0, doc="how many cells feed each other"),
        Param("colour", 3000.0, 100.0, 16000.0, unit="Hz", doc="the cells' low-pass"),
        Param("reso", 0.9, 0.5, 6.0, doc="resonance of each cell's filter"),
        Param("skin", 1.2, 0.3, 4.0, doc="drive into each cell's tanh"),
        Param("limit", 0.3, 0.02, 1.0, doc="energy a cell tolerates before it calms itself"),
        Param("hunger", 0.0, 0.0, 1.0, doc="how far quiet cells raise their gain (above 0.5 it can self-sustain)"),
        Param("tune", 0.0, 0.0, 1.0, doc="retune the delays to the note's period"),
        Param("glide", 0.3, 0.0, 1.0, doc="how slowly the delays move to their new length"),
        Param("bite", 30.0, 1.0, 400.0, unit="ms", doc="length of a note's noise burst"),
        Param("tone", 0.5, 0.0, 1.0, doc="pitched (pulse train at the note) vs noise bite"),
        Param("mutate", 0.0, 0.0, 1.0, doc="chance per generation that an edge is rewired"),
        Param("generation", 4.0, 0.25, 30.0, unit="s"),
        Param("input", 1.0, 0.0, 2.0, doc="how much routed audio feeds the cells"),
        Param("dry", 0.2, 0.0, 1.0),
        Param("width", 0.8, 0.0, 1.0),
        Param("level", 1.0, 0.0, 2.0),
    )
    PRESETS = {
        "cave-colony": {"cells": 6, "time": 0.38, "feedback": 0.8, "colour": 2200.0, "scatter": 0.8, "dry": 0.3},
        "tuned-coral": {"cells": 5, "tune": 1.0, "feedback": 0.93, "time": 0.02, "colour": 6000.0, "reso": 1.4,
                        "bite": 12.0, "tone": 0.2, "glide": 0.1, "dry": 0.05},
        "hungry-swarm": {"cells": 8, "time": 0.09, "feedback": 0.85, "hunger": 0.8, "limit": 0.15, "skin": 2.0,
                         "mutate": 0.6, "generation": 2.0, "colour": 4000.0},
        "dub-cells": {"cells": 3, "time": 0.375, "scatter": 0.3, "feedback": 0.88, "colour": 1500.0, "reso": 2.0,
                      "skin": 1.8, "dry": 0.5, "tone": 0.9, "bite": 80.0},
        "glass-lungs": {"cells": 7, "time": 0.05, "scatter": 1.0, "feedback": 0.9, "colour": 9000.0, "reso": 4.0,
                        "tune": 0.5, "bite": 5.0, "tone": 0.0},
        "input-eater": {"cells": 4, "time": 0.15, "feedback": 0.75, "input": 1.5, "dry": 0.0, "hunger": 0.3,
                        "bite": 40.0},
    }

    def init_state(self) -> None:
        self.K = 8
        self.L = int(MAXD * self.sr) + 2 * CTRL + 4
        self.buf = np.zeros((self.K, self.L))
        self.w = 0
        self.zi = np.zeros((self.K, 2))
        self.gain = np.ones(self.K)
        self.energy = np.zeros(self.K)
        r = np.random.default_rng([self.seed & 0x7FFFFFFF, 41])
        self.base_ratio = np.exp((r.random(self.K) - 0.5) * 2.0)          # each cell's own echo time (scattered)
        self.harm = r.integers(1, 5, self.K).astype(float)                # periods per delay when tuned
        self.pan = np.linspace(-1, 1, self.K)[r.permutation(self.K)]
        self.W = r.standard_normal((self.K, self.K)) * (r.random((self.K, self.K)) < 0.6)
        self.mask = r.random((self.K, self.K))
        self.D = None
        self.f0 = None
        self.clock = 0
        self.next_gen = 0

    def state(self) -> dict:
        return {"buf": self.buf, "w": self.w, "zi": self.zi, "gain": self.gain, "energy": self.energy, "W": self.W,
                "D": self.D, "f0": self.f0, "clock": self.clock, "next_gen": self.next_gen}

    def load_state(self, d: dict) -> None:
        self.buf = np.asarray(d["buf"], float).reshape(self.K, self.L)
        self.w, self.clock, self.next_gen = int(d["w"]), int(d["clock"]), int(d["next_gen"])
        self.zi = np.asarray(d["zi"], float).reshape(self.K, 2)
        self.gain = np.asarray(d["gain"], float)
        self.energy = np.asarray(d["energy"], float)
        self.W = np.asarray(d["W"], float).reshape(self.K, self.K)
        self.D = None if d.get("D") is None else np.asarray(d["D"], float)
        self.f0 = d.get("f0")

    def on_note(self, v: dict) -> None:
        self.f0 = hz(v["pitch"])
        v["pulse"] = 0.0
        v["cells"] = 0.4 + 0.6 * np.random.default_rng([self.seed & 0x7FFFFFFF, v["pitch"]]).random(self.K)

    def alive(self, v: dict) -> bool:
        return v["age"] < self.v["bite"] * 0.001 * self.sr * 3

    # ------------------------------------------------------------------------------------------------------------
    def _targets(self) -> np.ndarray:
        V = self.v
        free = V["time"] * self.base_ratio ** V["scatter"]
        if self.f0 and V["tune"] > 0:
            per = self.harm / self.f0
            per = per * np.ceil((2 * CTRL + 2) / self.sr / per)            # long enough to read a whole step
            free = np.exp((1 - V["tune"]) * np.log(free) + V["tune"] * np.log(per))
        return np.clip(free * self.sr, 2 * CTRL + 2, MAXD * self.sr)

    def _wiring(self, k: int) -> np.ndarray:
        V = self.v
        W = self.W[:k, :k] * (self.mask[:k, :k] < V["density"])
        W = W + np.eye(k) * 0.3 * (np.abs(W).sum() == 0)
        r = np.abs(np.linalg.eigvals(W)).max()
        return W * (V["feedback"] / r if r > 1e-9 else 0.0)

    def _bite(self, m: int) -> np.ndarray:
        V = self.v
        exc = np.zeros(m)
        L = V["bite"] * 0.001 * self.sr
        i = np.arange(m)
        for v in self.voices:
            env = np.exp(-(v["age"] + i) / max(L, 1.0)) * (v["age"] + i < 3 * L)
            if not env.any():
                continue
            noise = self.rng.standard_normal(m)
            p = hz(v["pitch"]) / self.sr
            ph = (v["pulse"] + p * i) % 1.0
            pulse = np.where(ph < p, 1.0, 0.0) * 4.0 - 4.0 * p
            v["pulse"] = float((v["pulse"] + p * m) % 1.0)
            exc += env * v["vel"] * ((1 - V["tone"]) * noise * 0.5 + V["tone"] * pulse)
        return exc

    def synth(self, n: int, inp) -> np.ndarray:
        V = self.v
        k = int(V["cells"])
        out = np.zeros((n, 2))
        W = self._wiring(k)
        b, a = biquad("lp", V["colour"], self.sr, V["reso"])
        b = b / max(1.0, V["reso"])                                        # peak gain <= 1: the loop stays <= feedback
        hunger = 1 + V["hunger"] * 0.3
        rate_g = 1 - np.exp(-CTRL / (0.12 * self.sr))
        pa = (np.clip(self.pan[:k] * V["width"], -1, 1) + 1) * np.pi / 4
        glide = 1 - np.exp(-CTRL / (max(V["glide"], 1e-3) * 0.5 * self.sr))
        pos = 0
        while pos < n:
            m = min(CTRL, n - pos)
            tgt = self._targets()
            self.D = tgt[:] if self.D is None else self.D + (tgt - self.D) * glide
            # read the step: fractional delays, linear interpolation
            rd = (self.w - self.D[:k, None] + np.arange(m)[None, :]) % self.L
            i0 = np.floor(rd).astype(int)
            fr = rd - i0
            rows = np.arange(k)[:, None]
            y = self.buf[rows, i0] * (1 - fr) + self.buf[rows, (i0 + 1) % self.L] * fr          # (k, m)
            for c in range(k):
                y[c], self.zi[c] = filt(b, a, y[c], self.zi[c])
            y = np.tanh(y * V["skin"] * self.gain[:k, None]) / max(np.tanh(V["skin"]), 0.3)
            exc = self._bite(m)
            feed = W @ y + exc[None, :] * self._cells_of_voices(k)[:, None]
            if inp is not None:
                feed += inp[pos:pos + m].mean(1)[None, :] * V["input"]
            wi = (self.w + np.arange(m)) % self.L
            self.buf[:k, wi] = feed
            self.buf[k:, wi] = 0.0
            self.w = (self.w + m) % self.L
            # metabolism
            e = (y ** 2).mean(1)
            self.energy[:k] = e
            self.gain[:k] += (np.where(e > V["limit"] ** 2, 0.15, hunger) - self.gain[:k]) * rate_g
            out[pos:pos + m, 0] += np.cos(pa) @ y + exc * V["dry"]
            out[pos:pos + m, 1] += np.sin(pa) @ y + exc * V["dry"]
            self.clock += m
            pos += m
            if V["mutate"] > 0 and self.clock >= self.next_gen:
                self.next_gen = self.clock + int(V["generation"] * self.sr)
                if self.rng.random() < V["mutate"]:
                    i, j = self.rng.integers(self.K, size=2)
                    self.W[i, j] = self.rng.standard_normal()
                    self.mask[i, j] = self.rng.random()
        return (out * 0.35 * V["level"]).astype(np.float32)

    def _cells_of_voices(self, k: int) -> np.ndarray:
        if not self.voices:
            return np.ones(k)
        return np.mean([v["cells"][:k] for v in self.voices], 0)


ENGINE = Echo
