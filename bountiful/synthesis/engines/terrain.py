"""Terrain: wave-terrain synthesis. A note is an orbit traced across a surface; the sound is the height under it.

The surface is a sum of plane waves, z(x, y) = Σ a_j sin(k_j · (x, y) + φ_j), drawn (seeded) from a family:
  dunes    a few waves sharing one direction: wind-blown ridges, soft and vocal
  lattice  integer wave vectors (cos x cos y and friends): harmonic, organ-like
  crater   many directions with the same |k|: rings round a centre, bell-like Bessel spectra
  fractal  wave vectors at all scales with amplitude 1 / |k|^roughness: rough, noisy, mountainous
The note's frequency is the orbit's: (x, y) = centre + (rx cos θ, ry sin(ratio · θ + tilt)), θ advancing at f.
`ratio` makes Lissajous orbits. The centre walks a slow path of radius `wander` at `drift` Hz, so the orbit crosses
other ground and the timbre moves. `morph` lets the terrain itself shift (each wave's phase drifts at its own speed).

Band limit: a wave with |k| crossed by an orbit of radius r makes harmonics up to about |k| r + 2 (Bessel J_n),
so each wave is faded out before those reach Nyquist: high notes see a smoother terrain instead of aliasing.
`fold` passes the height through a sine wavefolder for extra edge. Stereo: the right ear's orbit runs `width`
radians ahead. A gentle DC blocker (the orbit's average height) keeps it centred.
"""
from __future__ import annotations

import numpy as np

from synthesis.engine_api import Engine, Param
from synthesis.engines._dsp import biquad, filt, hz

CTRL = 256
FAMILIES = ("dunes", "lattice", "crater", "fractal")


def surface(family: str, seed: int, n: int, roughness: float, scale: float) -> tuple:
    """Wave vectors (K, 2), amplitudes (K,), phases (K,) and morph speeds (K,) of a seeded terrain."""
    r = np.random.default_rng([seed & 0x7FFFFFFF, 89, FAMILIES.index(family)])
    n = int(n)
    if family == "dunes":
        ang = r.normal(0.0, 0.25, n) + r.random() * np.pi
        mag = np.arange(1, n + 1) * (0.8 + 0.4 * r.random(n))
        amp = 1.0 / np.arange(1, n + 1) ** (0.5 + roughness)
    elif family == "lattice":
        kx, ky = r.integers(-4, 5, n), r.integers(-4, 5, n)
        kx[kx == 0] = 1
        k = np.stack([kx, ky], 1).astype(float)
        mag, ang = np.hypot(k[:, 0], k[:, 1]), np.arctan2(k[:, 1], k[:, 0])
        amp = 1.0 / mag ** (0.5 + roughness)
    elif family == "crater":
        ang = np.arange(n) / n * 2 * np.pi
        mag = np.full(n, 2.5) * (1 + 0.03 * r.standard_normal(n)) * (1 + (np.arange(n) % 3 == 2))
        amp = 1.0 / (1 + (np.arange(n) % 3 == 2)) ** (1 + roughness)
    else:
        mag = np.geomspace(0.5, 12.0, n) * (0.9 + 0.2 * r.random(n))
        ang = r.random(n) * 2 * np.pi
        amp = 1.0 / mag ** roughness
    k = np.stack([np.cos(ang), np.sin(ang)], 1) * (mag * scale)[:, None]
    amp = amp / np.sqrt((amp ** 2).sum())
    return k, amp, r.random(n) * 2 * np.pi, r.standard_normal(n)


class Terrain(Engine):
    ID = "terrain"
    NAME = "Terrain"
    VERSION = 1
    DESCRIPTION = "Wave-terrain: orbits over seeded plane-wave landscapes, wandering centre, morphing ground, band-limited."
    POLY = 8
    PARAMS = (
        Param("terrain", "dunes", kind="choice", choices=FAMILIES),
        Param("waves", 16, 2, 48, "int", doc="plane waves in the surface"),
        Param("roughness", 1.0, 0.0, 3.0, doc="how fast the small-scale waves fall off"),
        Param("scale", 1.0, 0.1, 4.0, doc="spatial frequency of the whole terrain"),
        Param("radius", 0.8, 0.0, 4.0, doc="orbit radius: bigger orbits cross more ground, brighter"),
        Param("ellipse", 1.0, 0.1, 1.0, doc="ry / rx"),
        Param("ratio", 1, 1, 5, "int", doc="Lissajous ratio of the orbit's y to its x"),
        Param("tilt", 0.0, 0.0, 3.1416, doc="phase of the orbit's y"),
        Param("wander", 1.0, 0.0, 6.0, doc="radius of the centre's slow walk"),
        Param("drift", 0.05, 0.0, 4.0, unit="Hz", doc="speed of the centre's walk"),
        Param("morph", 0.0, 0.0, 2.0, doc="how fast the ground itself shifts"),
        Param("fold", 0.0, 0.0, 4.0, doc="sine wavefolder on the height"),
        Param("attack", 0.01, 0.0, 4.0, unit="s"),
        Param("release", 0.4, 0.01, 8.0, unit="s"),
        Param("width", 0.4, 0.0, 3.1416, doc="how far ahead the right ear's orbit runs (radians)"),
        Param("level", 1.0, 0.0, 2.0),
    )
    PRESETS = {
        "desert-voice": {"terrain": "dunes", "waves": 8, "radius": 1.0, "drift": 0.07, "wander": 1.5,
                         "attack": 0.08, "release": 0.8},
        "pipe-lattice": {"terrain": "lattice", "waves": 12, "radius": 0.6, "roughness": 1.5, "drift": 0.0,
                         "width": 0.2},
        "crater-bell": {"terrain": "crater", "waves": 24, "radius": 1.4, "wander": 0.5, "drift": 0.02,
                        "release": 2.5, "attack": 0.002},
        "mountain-growl": {"terrain": "fractal", "waves": 32, "roughness": 0.8, "radius": 1.6, "fold": 1.2,
                           "drift": 0.3, "width": 1.0},
        "lissajous-lead": {"terrain": "lattice", "ratio": 3, "tilt": 0.6, "radius": 0.9, "fold": 0.6,
                           "attack": 0.005},
        "shifting-sands": {"terrain": "dunes", "waves": 20, "morph": 0.6, "wander": 3.0, "drift": 0.12,
                           "radius": 1.3, "attack": 0.6, "release": 3.0, "width": 1.5},
    }

    def init_state(self) -> None:
        self.clock = 0
        self.zi = np.zeros((2, 2))
        self._key = None

    def state(self) -> dict:
        return {"clock": self.clock, "zi": self.zi}

    def load_state(self, d: dict) -> None:
        self.clock = int(d.get("clock", 0))
        self.zi = np.asarray(d.get("zi", np.zeros((2, 2))), float).reshape(2, 2)

    def _surface(self) -> tuple:
        V = self.v
        key = (V["terrain"], int(V["waves"]), V["roughness"], V["scale"])
        if key != self._key:
            self._key, self._surf = key, surface(V["terrain"], self.seed, V["waves"], V["roughness"], V["scale"])
        return self._surf

    def height_map(self, size: int = 48) -> list:
        """For the Lab's display: the terrain around the origin as rows of heights."""
        self._controls()
        k, a, ph, sp = self._surface()
        g = np.linspace(-4, 4, size)
        X, Y = np.meshgrid(g, g)
        z = np.sin(X[..., None] * k[:, 0] + Y[..., None] * k[:, 1] + ph) @ a
        return z.round(3).tolist()

    def on_note(self, v: dict) -> None:
        v["th"] = self.rng.random() * 2 * np.pi

    def alive(self, v: dict) -> bool:
        return v["gate"] or v["rel"] < self.v["release"] * self.sr

    def synth(self, n: int, inp) -> np.ndarray:
        V = self.v
        k, a, ph0, sp = self._surface()
        kmag = np.hypot(k[:, 0], k[:, 1])
        rx, ry = V["radius"], V["radius"] * V["ellipse"]
        out = np.zeros((n, 2))
        pos = 0
        while pos < n:
            m = min(CTRL, n - pos)
            i = np.arange(m)
            t = (self.clock + pos + i) / self.sr
            ca = 2 * np.pi * V["drift"] * t
            cx, cy = V["wander"] * np.cos(ca), V["wander"] * np.sin(ca * 0.7 + 1.0)
            ph = ph0[None, :] + V["morph"] * sp[None, :] * t[:, None]
            for v in self.voices:
                f = hz(v["pitch"])
                top = f * (kmag * max(rx, ry) + 2) * V["ratio"]               # highest harmonic each wave makes
                g = a * np.clip((self.sr * 0.42 - top) / (self.sr * 0.1), 0, 1)
                th = v["th"] + 2 * np.pi * f * i / self.sr
                env = self._env(v, pos, m)
                for c, off in enumerate((0.0, V["width"])):
                    x = cx + rx * np.cos(th + off)
                    y = cy + ry * np.sin(V["ratio"] * (th + off) + V["tilt"])
                    z = np.sin(x[:, None] * k[:, 0] + y[:, None] * k[:, 1] + ph) @ g
                    if V["fold"] > 0:
                        z = np.sin(z * (1 + V["fold"]) * np.pi / 2) / (1 + 0.15 * V["fold"])
                    out[pos:pos + m, c] += z * env * v["vel"]
                v["th"] = float((v["th"] + 2 * np.pi * f * m / self.sr) % (2 * np.pi))
            pos += m
        self.clock += n
        mid = out.mean(1, keepdims=True)
        out = mid + (out - mid) * 0.55                                       # the ears differ, but stay mono-safe
        b, a2 = biquad("hp", 12.0, self.sr, 0.707)
        for c in range(2):
            out[:, c], self.zi[c] = filt(b, a2, out[:, c], self.zi[c])
        return (out * 0.25 * V["level"]).astype(np.float32)

    def _env(self, v: dict, pos: int, m: int) -> np.ndarray:
        i = np.arange(m)
        att = np.clip((v["age"] + pos + i) / max(self.v["attack"] * self.sr, 1.0), 0, 1)
        if v["gate"]:
            return att
        return att * np.exp(-6.9 * (v["rel"] + pos + i) / max(self.v["release"] * self.sr, 1.0))


ENGINE = Terrain
