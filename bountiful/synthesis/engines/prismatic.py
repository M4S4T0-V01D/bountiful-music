"""Prismatic: one note sung by several sources in a room, heard by a listener walking an orbit between them.

Every note places `sources` emitters on a seeded ring (radius `spread` metres) around the room's centre. Each partial
h of the note travels from each source to each of the listener's two ears (`ears` apart) along a straight path of
length d; it arrives d / c_h later and 1 / d quieter. Dispersion makes the higher partials slower,
c_h = c / (1 + dispersion * (h-1) / 8), so a note's colours arrive one after another like light through a prism
(`room` scales the distances, so big rooms smear more). Refraction bends each partial's apparent source a little
further around the ring, so the colours sit in different places.

The listener orbits on a Lissajous path (`orbit` radius, `speed` Hz). As the path lengths change, the sum over the
sources of a_s · e^(-i 2π f_h d_s / c_h) changes too: partials swell and cancel (interference), the Doppler shift
falls out of the moving phase, and the two ears hear different interference, which gives the stereo image.

Per control step (256 samples) each partial's complex ear gain is computed at both ends and interpolated, then the
partials are summed analytically. No delay lines and no noise, so a snapshot is a handful of phases.
"""
from __future__ import annotations

import numpy as np

from synthesis.engine_api import Engine, Param
from synthesis.engines._dsp import hz

CTRL = 256
C = 343.0


class Prismatic(Engine):
    ID = "prismatic"
    NAME = "Prismatic"
    VERSION = 1
    DESCRIPTION = "Interference of a note's sources at a moving listener: path lengths, Doppler and dispersion."
    POLY = 8
    PARAMS = (
        Param("sources", 4, 1, 8, "int", doc="emitters per note"),
        Param("spread", 4.0, 0.2, 20.0, unit="m", doc="radius of the emitters' ring"),
        Param("orbit", 2.5, 0.0, 20.0, unit="m", doc="radius of the listener's path"),
        Param("speed", 0.08, 0.0, 2.0, unit="Hz", doc="how fast the listener walks the orbit"),
        Param("shape", 0.5, 0.0, 1.0, doc="the orbit: circle (0) to figure-of-eight (1)"),
        Param("ears", 0.25, 0.0, 2.0, unit="m", doc="distance between the listener's ears (the stereo)"),
        Param("room", 1.0, 0.1, 6.0, doc="scales every distance: bigger rooms, longer flights"),
        Param("dispersion", 0.3, 0.0, 1.0, doc="how much slower the high partials travel"),
        Param("refraction", 0.2, 0.0, 1.0, doc="how far each colour's source is bent round the ring"),
        Param("partials", 10, 1, 24, "int"),
        Param("bright", 0.5, 0.0, 1.0),
        Param("odd", 0.0, 0.0, 1.0, doc="weight the odd partials (hollow)"),
        Param("attack", 0.01, 0.0, 4.0, unit="s"),
        Param("release", 0.6, 0.01, 8.0, unit="s"),
        Param("width", 0.8, 0.0, 1.0),
        Param("level", 1.0, 0.0, 2.0),
    )
    PRESETS = {
        "glass-prism": {"sources": 4, "dispersion": 0.6, "refraction": 0.5, "bright": 0.7, "speed": 0.05,
                        "release": 1.5},
        "hall-of-mirrors": {"sources": 8, "spread": 9.0, "orbit": 6.0, "room": 3.0, "speed": 0.03, "partials": 14,
                            "attack": 0.3, "release": 3.0},
        "spinning-chord": {"sources": 3, "orbit": 3.0, "speed": 0.6, "shape": 0.0, "dispersion": 0.1,
                           "ears": 0.6, "release": 0.8},
        "rainbow-pluck": {"sources": 5, "dispersion": 1.0, "room": 5.0, "spread": 6.0, "bright": 0.9,
                          "partials": 18, "attack": 0.0, "release": 0.4},
        "still-water": {"sources": 2, "speed": 0.0, "orbit": 1.0, "dispersion": 0.0, "odd": 0.6, "attack": 0.5,
                        "release": 2.0, "width": 0.5},
        "doppler-swarm": {"sources": 6, "orbit": 12.0, "speed": 0.35, "shape": 1.0, "room": 2.0, "spread": 3.0,
                          "release": 1.0},
    }

    def init_state(self) -> None:
        self.clock = 0                                     # the listener's own time, in samples

    def state(self) -> dict:
        return {"clock": self.clock}

    def load_state(self, d: dict) -> None:
        self.clock = int(d.get("clock", 0))

    def on_note(self, v: dict) -> None:
        S = int(self.v["sources"])
        ang = (np.arange(S) + self.rng.random(S) * 0.6) / S * 2 * np.pi + self.rng.random() * 2 * np.pi
        v["ang"] = ang
        v["rad"] = 0.7 + 0.6 * self.rng.random(S)
        v["amp_s"] = 0.6 + 0.4 * self.rng.random(S)
        v["ph"] = self.rng.random(24)

    def alive(self, v: dict) -> bool:
        return v["gate"] or v["rel"] < self.v["release"] * self.sr

    def listener(self, t: float) -> np.ndarray:
        """Left and right ear positions (2, 2) at time t seconds."""
        V = self.v
        a = 2 * np.pi * V["speed"] * t
        R = V["orbit"] * V["room"]
        c = np.array([R * np.cos(a), R * ((1 - V["shape"]) * np.sin(a) + V["shape"] * np.sin(2 * a) * 0.7)])
        head = a + np.pi / 2
        e = np.array([np.cos(head), np.sin(head)]) * V["ears"] * 0.5
        return np.stack([c - e, c + e])

    def _gains(self, v: dict, f: np.ndarray, ears: np.ndarray) -> np.ndarray:
        """Complex gain (2 ears, K partials) of the note's sources, and how far each partial has flown."""
        V = self.v
        K = len(f)
        k = np.arange(K)
        ang = v["ang"][None, :] + V["refraction"] * 0.25 * k[:, None]           # (K, S): colours bent round
        R = V["spread"] * V["room"] * v["rad"][None, :]
        src = np.stack([R * np.cos(ang), R * np.sin(ang)], -1)                    # (K, S, 2)
        d = np.sqrt(((src[None] - ears[:, None, None, :]) ** 2).sum(-1)) + 0.05  # (2, K, S)
        ch = C / (1 + V["dispersion"] * k / 8.0)
        delay = d / ch[None, :, None]
        dref = V["spread"] * V["room"]                                            # loudness independent of room size
        g = (v["amp_s"][None, None, :] / np.maximum(d / dref, 0.3)) * np.exp(-2j * np.pi * f[None, :, None] * delay)
        return g.sum(-1) / np.sqrt(len(v["ang"])), delay.min(-1)                  # (2, K), (2, K)

    def synth(self, n: int, inp) -> np.ndarray:
        V = self.v
        out = np.zeros((n, 2))
        pos = 0
        while pos < n:
            m = min(CTRL, n - pos)
            t0, t1 = (self.clock + pos) / self.sr, (self.clock + pos + m) / self.sr
            e0, e1 = self.listener(t0), self.listener(t1)
            i = np.arange(m)
            for v in self.voices:
                f0 = hz(v["pitch"])
                K = int(min(V["partials"], max(1, (self.sr * 0.45) // f0)))
                h = np.arange(1, K + 1)
                f = f0 * h
                A = h ** -(2.0 - 1.6 * V["bright"]) * (1 - V["odd"] * (h % 2 == 0) * 0.9)
                A = A / np.sqrt((A ** 2).sum()) * v["vel"]
                G0, D0 = self._gains(v, f, e0)
                G1, _ = self._gains(v, f, e1)
                osc = np.exp(2j * np.pi * (v["ph"][:K][None, :] + np.outer(i, f / self.sr)))   # (m, K)
                age0 = (v["age"] + pos) / self.sr
                if age0 < D0.max() + 0.004:                                          # colours still landing
                    w = (i / m)[:, None, None]
                    G = G0[None] * (1 - w) + G1[None] * w                            # (m, 2, K)
                    arrive = np.clip((age0 + i[:, None, None] / self.sr - D0[None]) / 0.004, 0, 1)
                    s = (osc[:, None, :] * G * arrive).real @ A
                else:                                                                # G linear in time: two products
                    w = (i / m)[:, None]
                    s = (osc @ (A * G0).T).real + w * (osc @ (A * (G1 - G0)).T).real
                out[pos:pos + m] += s * self._env(v, pos, m)[:, None]
                v["ph"][:K] = (v["ph"][:K] + f / self.sr * m) % 1.0
            pos += m
        self.clock += n
        mid = out.mean(1, keepdims=True)
        out = mid + (out - mid) * V["width"]
        return (out * 0.2 * V["level"]).astype(np.float32)

    def _env(self, v: dict, pos: int, m: int) -> np.ndarray:
        i = np.arange(m)
        att = np.clip((v["age"] + pos + i) / max(self.v["attack"] * self.sr, 1.0), 0, 1)
        if v["gate"]:
            return att
        return att * np.exp(-6.9 * (v["rel"] + pos + i) / max(self.v["release"] * self.sr, 1.0))


ENGINE = Prismatic
