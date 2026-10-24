"""Phase Garden: every note is a small population of oscillators that pull on each other's phase (the Kuramoto model).

    dθ_i/dt = ω_i + K · r · sin(ψ − θ_i)          r·e^{iψ} = mean over the population of e^{iθ_j}

Each oscillator's natural frequency ω_i is spread around the note (spread, in cents). With weak coupling K they drift
apart: a slow shimmering chorus. Past a critical coupling (about the width of the spread) they lock: the cluster
collapses into one bright, coherent tone. The order parameter r (0 = scattered, 1 = locked) is heard, not just
computed: it opens the harmonics (bloom) and narrows the stereo field; it is also what the Lab draws.

`noise` jostles the phases (temperature), `season` swings the coupling slowly so a held chord breathes in and out of
sync, `sub` adds a population an octave below that couples to the same mean field. Phases advance at audio rate; the
coupling term is computed every CTRL samples (mean-field, O(N)).
"""
from __future__ import annotations

import numpy as np

from synthesis.engine_api import Engine, Param, voice_env
from synthesis.engines._dsp import cents, hz

CTRL = 64


class PhaseGarden(Engine):
    ID = "phase_garden"
    NAME = "Phase Garden"
    VERSION = 1
    DESCRIPTION = "Kuramoto-coupled oscillator populations drifting in and out of sync; order r drives brightness."
    POLY = 8
    PARAMS = (
        Param("count", 7, 2, 16, "int", doc="oscillators per note"),
        Param("spread", 22.0, 0.0, 120.0, unit="cents", doc="spread of natural frequencies"),
        Param("coupling", 4.0, 0.0, 30.0, unit="Hz@A4", doc="K: the pull towards the mean phase (scales with pitch)"),
        Param("noise", 0.1, 0.0, 1.0, doc="phase noise (temperature)"),
        Param("bloom", 0.6, 0.0, 1.0, doc="how much synchrony opens the harmonics"),
        Param("season", 0.0, 0.0, 1.0, doc="depth of the slow coupling swing"),
        Param("season_beats", 16.0, 1.0, 128.0, unit="beats", doc="period of the swing"),
        Param("sub", 0.0, 0.0, 1.0, doc="a coupled population an octave below"),
        Param("attack", 0.05, 0.001, 4.0, unit="s"),
        Param("release", 0.8, 0.01, 8.0, unit="s"),
        Param("width", 0.8, 0.0, 1.0),
        Param("level", 1.0, 0.0, 2.0),
    )
    PRESETS = {
        "bloom": {"count": 8, "spread": 30, "coupling": 3.0, "season": 0.8, "season_beats": 16, "bloom": 0.8,
                  "attack": 0.6, "release": 2.0},
        "lock-step-lead": {"count": 5, "spread": 12, "coupling": 18, "noise": 0.05, "bloom": 0.7, "attack": 0.01,
                           "release": 0.3, "width": 0.3},
        "fireflies": {"count": 12, "spread": 70, "coupling": 9, "noise": 0.4, "season": 0.6, "season_beats": 8,
                      "bloom": 0.4, "attack": 0.3, "release": 1.5},
        "drift-choir": {"count": 10, "spread": 45, "coupling": 0.8, "noise": 0.2, "bloom": 0.3, "attack": 1.0,
                        "release": 3.0, "width": 1.0},
        "garden-bass": {"count": 4, "spread": 8, "coupling": 12, "sub": 0.7, "bloom": 0.5, "attack": 0.005,
                        "release": 0.2, "width": 0.1},
        "seasons": {"count": 9, "spread": 40, "coupling": 6, "season": 1.0, "season_beats": 32, "bloom": 0.9,
                    "attack": 1.5, "release": 4.0},
    }

    def init_state(self) -> None:
        self.order = []                                  # the last r per voice: the Lab's display

    def state(self) -> dict:
        return {"order": self.order}

    def load_state(self, d: dict) -> None:
        self.order = list(d.get("order", []))

    def on_note(self, v: dict) -> None:
        n = int(self.v["count"])
        f = hz(v["pitch"])
        dev = self.rng.uniform(-1, 1, n) if n > 1 else np.zeros(1)
        v["w"] = (f * cents(1.0) ** (dev * self.v["spread"] / 2)).tolist()       # natural frequencies, Hz
        v["th"] = self.rng.random(n).tolist()                                     # phases, cycles
        v["pan"] = np.linspace(-1, 1, n).tolist() if n > 1 else [0.0]
        v["sub"] = self.rng.random(max(2, n // 2)).tolist()
        v["r"] = 0.0

    def alive(self, v: dict) -> bool:
        return v["gate"] or v["rel"] < self.v["release"] * self.sr

    def synth(self, n: int, inp) -> np.ndarray:
        out = np.zeros((n, 2))
        V = self.v
        swing = 1.0 + V["season"] * np.sin(2 * np.pi * self.beat() / V["season_beats"])
        K = V["coupling"] * max(swing, 0.0)
        sigma = V["noise"] * 6.0                          # Hz of phase jitter
        order = []
        for v in self.voices:
            w = np.asarray(v["w"])
            rel = w.mean() / 440.0                         # coupling and jitter scale with pitch: same behaviour on every note
            th = np.asarray(v["th"])
            sub = np.asarray(v["sub"])
            pans = np.asarray(v["pan"])
            ys = np.zeros((n, 2))
            pos = 0
            while pos < n:
                m = min(CTRL, n - pos)
                z = np.exp(2j * np.pi * th).mean()
                r, psi = abs(z), np.angle(z) / (2 * np.pi)
                dw = rel * (K * r * np.sin(2 * np.pi * (psi - th)) + self.rng.normal(0, sigma, len(th)))       # Hz
                inc = (w + dw) / self.sr
                ph = th[:, None] + inc[:, None] * np.arange(m)
                b = V["bloom"] * r
                s = np.sin(2 * np.pi * ph) + b * 0.5 * np.sin(4 * np.pi * ph) + b * b * 0.33 * np.sin(6 * np.pi * ph)
                spread = V["width"] * (1.0 - 0.7 * r)           # synchrony draws the cluster to the centre
                a = (np.clip(pans * spread, -1, 1) + 1) * np.pi / 4
                ys[pos:pos + m, 0] += (np.cos(a)[:, None] * s).sum(0)
                ys[pos:pos + m, 1] += (np.sin(a)[:, None] * s).sum(0)
                th = (th + inc * m) % 1.0
                if V["sub"] > 0:                                 # an octave down, pulled by the same mean phase
                    wsub = w[:len(sub)] * 0.5
                    dws = rel * K * r * np.sin(2 * np.pi * (psi * 0.5 - sub))
                    phs = sub[:, None] + ((wsub + dws) / self.sr)[:, None] * np.arange(m)
                    ss = np.sin(2 * np.pi * phs).sum(0) * V["sub"] * len(th) / len(sub) * 0.7
                    ys[pos:pos + m] += ss[:, None] * 0.7071
                    sub = (sub + (wsub + dws) / self.sr * m) % 1.0
                pos += m
            env = voice_env(v, n, self.sr, V["attack"], V["release"])
            out += ys * (env * v["vel"] * 0.22 * len(th) ** -0.75)[:, None]        # scattered ~ N^0.5, locked ~ N
            v["th"], v["sub"], v["r"] = th.tolist(), sub.tolist(), float(r)
            order.append(round(float(r), 3))
        self.order = order
        return (out * V["level"]).astype(np.float32)


ENGINE = PhaseGarden
