"""Gravity: struck, plucked and bowed physical networks, heard through their normal modes.

A topology gives the mode frequencies, from the physics of the network rather than a table of nice ratios:
  chain     N masses on springs between fixed ends      f_k ∝ sin(kπ / 2(N+1)),  k = 1..N
  ring      N masses in a closed loop                    f_k ∝ sin(kπ / N): pairs of modes, split by `flaw`
  membrane  a circular drum skin                         ratios of the Bessel zeros j_mn / j_01
  bar       a free-free beam (marimba, glockenspiel)     f_k ∝ (2k+1)²
Where it is struck (`position`) decides which modes sound (a node there stays silent), `hardness` how bright.

Tension modulation: a hard hit stretches the network, so every mode starts sharp and falls as the energy decays
(f_k · (1 + nonlinear · E)), the bend of a tom or a slack string. Gravity between voices: modes of different
notes that sit within a bandwidth of each other trade energy each control step (`couple`), so a held chord rings
sympathetically. The bow keeps feeding the modes while the key is held, with seeded stick-slip roughness.
Modes are analytic decaying sinusoids with running phases, updated every CTRL samples: cheap and restorable.
"""
from __future__ import annotations

import numpy as np

from synthesis.engine_api import Engine, Param
from synthesis.engines._dsp import hz

CTRL = 128
MEMBRANE = np.array([1.0, 1.594, 2.136, 2.296, 2.653, 2.918, 3.156, 3.501, 3.600, 3.652, 4.060, 4.154, 4.601, 4.832,
                     4.903, 5.131])
TOPOLOGIES = ("chain", "ring", "membrane", "bar")


def mode_ratios(topology: str, masses: int, flaw: float) -> np.ndarray:
    """Mode frequencies relative to the fundamental, at most 16 modes."""
    n = int(np.clip(masses, 2, 24))
    if topology == "chain":
        k = np.arange(1, n + 1)
        r = np.sin(k * np.pi / (2 * (n + 1)))
    elif topology == "ring":
        k = np.repeat(np.arange(1, n // 2 + 1), 2)                       # degenerate pairs ...
        r = np.sin(k * np.pi / n) * (1 + flaw * 0.03 * np.tile([-1, 1], len(k) // 2))   # ... split by the flaw
    elif topology == "membrane":
        r = MEMBRANE[:max(n, 4)]
    else:
        k = np.arange(1, min(n, 7) + 1)
        r = (2 * k + 1.0) ** 2
    r = np.asarray(r, float)[:16]
    return r / r[0]


def mode_shape(topology: str, ratios: np.ndarray, x: float, seed: int) -> np.ndarray:
    """How strongly a hit at x (0-1) excites each mode."""
    k = np.arange(1, len(ratios) + 1)
    if topology == "chain":
        return np.abs(np.sin(k * np.pi * np.clip(x, 0.02, 0.98)))
    if topology == "ring":
        return np.abs(np.cos(np.ceil(k / 2) * 2 * np.pi * x + (k % 2) * np.pi / 2))
    if topology == "bar":
        return np.abs(np.cos((k + 0.5) * np.pi * x)) * 0.9 + 0.1
    rng = np.random.default_rng([seed & 0x7FFFFFFF, 7])                   # membrane: nodal circles, seeded angles
    return np.abs(np.cos(k * np.pi * x * 0.7 + rng.random(len(k)) * np.pi)) * 0.8 + 0.2


class Gravity(Engine):
    ID = "gravity"
    NAME = "Gravity"
    VERSION = 1
    DESCRIPTION = "Mass-spring chains, rings, membranes and bars as normal modes; tension bend and sympathetic coupling."
    POLY = 8
    PARAMS = (
        Param("topology", "chain", kind="choice", choices=TOPOLOGIES, doc="the network the modes come from"),
        Param("masses", 8, 2, 24, "int", doc="masses in a chain or ring (more = denser, more modes)"),
        Param("exciter", "strike", kind="choice", choices=("strike", "pluck", "bow")),
        Param("position", 0.23, 0.0, 1.0, doc="where the network is struck"),
        Param("hardness", 0.5, 0.0, 1.0, doc="brightness of the hit"),
        Param("tension", 1.0, 0.25, 4.0, doc="tightens the whole network (pitch ∝ √tension)"),
        Param("mass", 1.0, 0.25, 4.0, doc="heavier masses lower it (pitch ∝ 1/√mass)"),
        Param("nonlinear", 0.15, 0.0, 1.0, doc="tension modulation: hard hits start sharp and fall"),
        Param("couple", 0.2, 0.0, 1.0, doc="energy trade between nearby modes of different notes"),
        Param("flaw", 0.3, 0.0, 1.0, doc="splits a ring's paired modes into beating pairs"),
        Param("decay", 2.0, 0.05, 12.0, unit="s", doc="T60 of the fundamental"),
        Param("damp_hf", 0.5, 0.0, 4.0, doc="how much faster the upper modes die"),
        Param("release", 0.4, 0.01, 6.0, unit="s", doc="T60 once the key is let go (damped)"),
        Param("rough", 0.3, 0.0, 1.0, doc="stick-slip jitter of the bow"),
        Param("width", 0.6, 0.0, 1.0),
        Param("level", 1.0, 0.0, 2.0),
    )
    PRESETS = {
        "steel-chain": {"topology": "chain", "masses": 12, "position": 0.13, "hardness": 0.7, "decay": 3.5,
                        "damp_hf": 0.3, "nonlinear": 0.1},
        "gong-ring": {"topology": "ring", "masses": 16, "flaw": 0.8, "hardness": 0.6, "decay": 6.0, "damp_hf": 0.2,
                      "nonlinear": 0.35, "release": 3.0},
        "tom-skin": {"topology": "membrane", "masses": 8, "hardness": 0.4, "decay": 0.7, "damp_hf": 1.5,
                     "nonlinear": 0.8, "release": 0.5},
        "marimba-bar": {"topology": "bar", "masses": 4, "position": 0.08, "hardness": 0.35, "decay": 1.2,
                        "damp_hf": 2.0, "nonlinear": 0.0},
        "bowed-chain": {"topology": "chain", "masses": 10, "exciter": "bow", "position": 0.31, "decay": 2.5,
                        "rough": 0.4, "release": 1.2, "couple": 0.4},
        "sympathy": {"topology": "ring", "masses": 12, "exciter": "pluck", "couple": 0.9, "decay": 5.0,
                     "flaw": 0.4, "release": 4.0, "width": 0.9},
        "slack-bass": {"topology": "chain", "masses": 6, "exciter": "pluck", "tension": 0.6, "nonlinear": 0.6,
                       "decay": 1.5, "damp_hf": 1.0, "width": 0.1},
    }

    def init_state(self) -> None:
        self.energy: list = []                            # per voice, for the Lab's display

    def state(self) -> dict:
        return {"energy": self.energy}

    def load_state(self, d: dict) -> None:
        self.energy = list(d.get("energy", []))

    def on_note(self, v: dict) -> None:
        V = self.v
        r = mode_ratios(V["topology"], V["masses"], V["flaw"])
        k = np.arange(1, len(r) + 1)
        shape = mode_shape(V["topology"], r, V["position"], self.seed + v["pitch"])
        bright = 1.0 / k ** (2.2 - 1.8 * V["hardness"])
        if V["exciter"] == "pluck":
            bright = 1.0 / k ** 2.0
        a = shape * bright
        a = a / (np.sqrt((a ** 2).sum()) + 1e-9) * v["vel"]
        v["r"] = r
        v["a"] = a if V["exciter"] != "bow" else a * 0.05
        v["target"] = a                                    # the bow pulls the modes towards this
        v["ph"] = self.rng.random(len(r))
        v["pan"] = np.linspace(-1, 1, len(r)) * (self.rng.random(len(r)) * 0.5 + 0.5)

    def alive(self, v: dict) -> bool:
        return v["gate"] or (float(np.abs(v["a"]).max()) > 1e-4 and v["rel"] < 12 * self.sr)

    def synth(self, n: int, inp) -> np.ndarray:
        V = self.v
        out = np.zeros((n, 2))
        scale = np.sqrt(V["tension"] / V["mass"])
        self._couple(n)
        pos = 0
        while pos < n:
            m = min(CTRL, n - pos)
            i = np.arange(m)
            for v in self.voices:
                r, a = v["r"], v["a"]
                k = np.arange(1, len(r) + 1)
                E = float((a ** 2).sum())
                f = hz(v["pitch"]) * scale * r * (1 + V["nonlinear"] * 0.06 * min(E, 4.0))
                ok = f < self.sr * 0.45
                t60 = V["decay"] / (1 + V["damp_hf"] * (k - 1) * 0.5)
                if not v["gate"]:
                    t60 = np.minimum(t60, V["release"])
                if V["exciter"] == "bow" and v["gate"]:
                    t60 = np.maximum(t60, 0.05)
                    jit = 1 + V["rough"] * 0.3 * self.rng.standard_normal(len(r))
                    a = a + (v["target"] * jit - a) * min(1.0, m / (0.08 * self.sr))
                decay = np.exp(-6.9078 * np.outer(i, 1.0 / (t60 * self.sr)))       # (m, K)
                ph = v["ph"][None, :] + np.outer(i, f / self.sr)
                s = np.sin(2 * np.pi * ph) * decay * (a * ok)[None, :]
                pa = (np.clip(v["pan"] * V["width"], -1, 1) + 1) * np.pi / 4
                out[pos:pos + m, 0] += s @ np.cos(pa)
                out[pos:pos + m, 1] += s @ np.sin(pa)
                v["ph"] = (v["ph"] + f / self.sr * m) % 1.0
                v["a"] = a * decay[-1] * np.exp(-6.9078 / (t60 * self.sr))
            pos += m
        self.energy = [round(float((v["a"] ** 2).sum()), 4) for v in self.voices]
        return (out * 0.35 * V["level"]).astype(np.float32)

    def _couple(self, m: int) -> None:
        """Modes of different voices within a bandwidth of each other drift towards equal energy."""
        c = self.v["couple"]
        if c <= 0 or len(self.voices) < 2:
            return
        scale = np.sqrt(self.v["tension"] / self.v["mass"])
        fs = [hz(v["pitch"]) * scale * v["r"] for v in self.voices]
        rate = c * m / (0.25 * self.sr)
        for i in range(len(self.voices)):
            for j in range(i + 1, len(self.voices)):
                d = np.abs(fs[i][:, None] - fs[j][None, :]) / (0.02 * fs[i][:, None] + 1.0)
                w = np.exp(-d ** 2) * rate                                  # (Ki, Kj) closeness
                if w.max() < 1e-6:
                    continue
                ai, aj = self.voices[i]["a"], self.voices[j]["a"]
                ei, ej = ai ** 2, aj ** 2
                flow = w * (ei[:, None] - ej[None, :]) * 0.5                 # energy from i's mode to j's
                ei2 = np.maximum(ei - flow.sum(1), 0)
                ej2 = np.maximum(ej + flow.sum(0), 0)
                self.voices[i]["a"] = np.sqrt(ei2) * np.sign(ai + 1e-12)
                self.voices[j]["a"] = np.sqrt(ej2) * np.sign(aj + 1e-12)


ENGINE = Gravity
