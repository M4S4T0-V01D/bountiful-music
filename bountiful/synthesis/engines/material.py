"""Material Memory: an instrument body that remembers how it has been played.

The material is a map over absolute frequency (64 log points, 30 Hz - 16 kHz), so the memory belongs to the object,
not to a note: playing a low C wears the same region a low C# does. Three quantities live on that map:
  wear     slow damage: worn regions ring shorter, sit flat (softened) and lose brightness
  fatigue  fast stress from recent hits: it shortens and dulls too, and recovers with `recovery` seconds
  cracks   where wear passes `threshold` the material cracks there; partials in a cracked region buzz and crackle
Each strike adds its partials' energy to the map (`wear_rate`, scaled by velocity and `hardness`); fatigue heals
continuously, wear heals `anneal` times as fast, and cracks only heal when `anneal` > 0 and wear falls well below
the threshold. So a riff repeated for a minute sounds different at the end, and a part left alone recovers.

`memory` chooses what happens to the history:
  wear      the map evolves (default)
  frozen    the current map is played but never changes: a worn instrument, non-mutating
  pristine  the map is ignored: the brand-new instrument, non-mutating
Materials set the partials' inharmonicity and base damping: wood, metal, glass, clay, stone.
The map is the state, so snapshots carry the instrument's whole history.
"""
from __future__ import annotations

import numpy as np

from synthesis.engine_api import Engine, Param
from synthesis.engines._dsp import hz

CTRL = 128
GRID = np.geomspace(30.0, 16000.0, 64)
LG = np.log(GRID)
#             inharmonicity  t60 (s)  hf damping  grit
MATERIALS = {"wood": (0.0004, 1.2, 1.6, 0.2), "metal": (0.002, 4.5, 0.3, 0.05), "glass": (0.008, 3.0, 0.5, 0.1),
             "clay": (0.0002, 0.5, 2.5, 0.4), "stone": (0.03, 1.8, 1.0, 0.3)}


class Material(Engine):
    ID = "material"
    NAME = "Material Memory"
    VERSION = 1
    DESCRIPTION = "Body whose frequency map wears, tires, recovers and cracks with use; frozen and pristine modes."
    POLY = 8
    PARAMS = (
        Param("material", "wood", kind="choice", choices=tuple(MATERIALS)),
        Param("memory", "wear", kind="choice", choices=("wear", "frozen", "pristine"),
              doc="wear evolves the map; frozen plays it unchanged; pristine ignores it"),
        Param("wear_rate", 0.15, 0.0, 1.0, doc="damage per strike"),
        Param("fatigue", 0.5, 0.0, 1.0, doc="how much recent hits stress the material"),
        Param("recovery", 3.0, 0.1, 60.0, unit="s", doc="fatigue's recovery time"),
        Param("anneal", 0.02, 0.0, 1.0, doc="how fast wear heals, relative to fatigue (0: permanent)"),
        Param("threshold", 0.6, 0.1, 1.0, doc="wear at which the material cracks"),
        Param("age", 0.0, 0.0, 1.0, doc="pre-wear the whole instrument (an old one), applied at start"),
        Param("hardness", 0.5, 0.0, 1.0, doc="mallet: brighter hits, and they wear the highs more"),
        Param("partials", 16, 1, 32, "int"),
        Param("decay", 1.0, 0.1, 6.0, doc="scales the material's ring time"),
        Param("buzz", 0.5, 0.0, 1.0, doc="how loudly cracks rattle"),
        Param("release", 0.3, 0.01, 6.0, unit="s"),
        Param("width", 0.5, 0.0, 1.0),
        Param("level", 1.0, 0.0, 2.0),
    )
    PRESETS = {
        "new-marimba": {"material": "wood", "memory": "pristine", "hardness": 0.4, "partials": 8},
        "practice-room-piano": {"material": "metal", "wear_rate": 0.25, "fatigue": 0.6, "recovery": 8.0,
                                "hardness": 0.6, "decay": 0.8, "release": 0.6},
        "cracked-bell": {"material": "metal", "age": 0.7, "threshold": 0.5, "buzz": 0.8, "decay": 1.5,
                         "memory": "frozen", "release": 2.0},
        "tiring-glass": {"material": "glass", "wear_rate": 0.4, "fatigue": 0.9, "recovery": 2.0, "anneal": 0.1,
                         "hardness": 0.8},
        "clay-pots": {"material": "clay", "wear_rate": 0.3, "threshold": 0.45, "buzz": 0.6, "hardness": 0.3},
        "old-stone": {"material": "stone", "age": 0.4, "wear_rate": 0.1, "anneal": 0.0, "decay": 1.2,
                      "partials": 12},
    }

    def init_state(self) -> None:
        r = np.random.default_rng([self.seed & 0x7FFFFFFF, 61])
        grain = 0.6 + 0.8 * r.random(64)                    # the object's own uneven grain
        self.wear = np.clip(self.p.get("age", 0.0) * grain, 0, 1)
        self.fat = np.zeros(64)
        self.crack = (self.wear > self.p.get("threshold", 0.6)).astype(float)
        self.strikes = 0

    def state(self) -> dict:
        return {"wear": self.wear, "fat": self.fat, "crack": self.crack, "strikes": self.strikes}

    def load_state(self, d: dict) -> None:
        self.wear = np.asarray(d["wear"], float)
        self.fat = np.asarray(d["fat"], float)
        self.crack = np.asarray(d["crack"], float)
        self.strikes = int(d.get("strikes", 0))

    def memory_map(self) -> dict:
        """For the Lab's display: the map as plain lists."""
        return {"hz": GRID.round(1).tolist(), "wear": self.wear.round(3).tolist(),
                "fatigue": self.fat.round(3).tolist(), "crack": self.crack.tolist(), "strikes": self.strikes}

    def _at(self, f: np.ndarray) -> tuple:
        if self.v["memory"] == "pristine":
            z = np.zeros(len(f))
            return z, z, z
        lf = np.log(np.clip(f, GRID[0], GRID[-1]))
        return (np.interp(lf, LG, self.wear), np.interp(lf, LG, self.fat),
                np.interp(lf, LG, self.crack))

    def on_note(self, v: dict) -> None:
        V = self.v
        B, t60, hfd, grit = MATERIALS[V["material"]]
        f0 = hz(v["pitch"])
        k = np.arange(1, int(V["partials"]) + 1)
        f = f0 * k * np.sqrt(1 + B * k * k)
        f = f[f < self.sr * 0.45]
        if not len(f):
            f = np.array([min(f0, self.sr * 0.4)])
        k = k[:len(f)]
        w, fa, cr = self._at(f)
        a = k ** -(2.2 - 1.6 * V["hardness"]) * (1 - 0.6 * w) * (1 - 0.4 * fa)
        a = a / np.sqrt((a ** 2).sum()) * v["vel"]
        v["f"] = f * (1 - 0.015 * w - 0.005 * fa)            # worn and tired regions go soft and flat
        v["t60"] = V["decay"] * t60 / (1 + hfd * (k - 1) * 0.3) / (1 + 3 * w + 2 * fa)
        v["a"] = a
        v["cr"] = cr * V["buzz"]
        v["grit"] = grit
        v["ph"] = self.rng.random(len(f))
        v["pan"] = (self.rng.random(len(f)) - 0.5) * 2
        if V["memory"] == "wear":
            self._strike(f, a)

    def _strike(self, f: np.ndarray, a: np.ndarray) -> None:
        V = self.v
        e = np.zeros(64)
        idx = np.clip(np.searchsorted(GRID, f), 0, 63)
        np.add.at(e, idx, a ** 2)
        e = np.convolve(e, [0.25, 0.5, 0.25], "same")       # a hit spreads into the neighbouring grain
        e *= 1 + V["hardness"] * np.linspace(0, 1.5, 64)    # hard mallets wear the highs
        self.wear = np.clip(self.wear + V["wear_rate"] * 0.3 * e * (1 - self.wear), 0, 1)
        self.fat = np.clip(self.fat + V["fatigue"] * e, 0, 1)
        self.crack = np.maximum(self.crack, (self.wear > V["threshold"]).astype(float))
        self.strikes += 1

    def alive(self, v: dict) -> bool:
        return v["gate"] or (float(np.abs(v["a"]).max()) > 1e-4 and v["rel"] < 8 * self.sr)

    def synth(self, n: int, inp) -> np.ndarray:
        V = self.v
        out = np.zeros((n, 2))
        pos = 0
        while pos < n:
            m = min(CTRL, n - pos)
            i = np.arange(m)
            for v in self.voices:
                t60 = v["t60"] if v["gate"] else np.minimum(v["t60"], V["release"])
                dec = np.exp(-6.9078 * np.outer(i, 1.0 / (t60 * self.sr)))
                s = np.sin(2 * np.pi * (v["ph"][None, :] + np.outer(i, v["f"] / self.sr))) * dec * v["a"][None, :]
                if v["cr"].any():                            # cracked partials rattle against themselves
                    rat = np.sign(s) * np.abs(s) ** 0.5 * 0.3 - s
                    crackle = (self.rng.random((m, len(v["f"]))) < 0.004 * (1 + v["grit"] * 4)) \
                        * self.rng.standard_normal((m, len(v["f"])))
                    s = s + v["cr"][None, :] * (rat + crackle * np.abs(v["a"])[None, :] * dec)
                pa = (np.clip(v["pan"] * V["width"], -1, 1) + 1) * np.pi / 4
                out[pos:pos + m, 0] += s @ np.cos(pa)
                out[pos:pos + m, 1] += s @ np.sin(pa)
                v["ph"] = (v["ph"] + v["f"] / self.sr * m) % 1.0
                v["a"] = v["a"] * dec[-1] * np.exp(-6.9078 / (t60 * self.sr))
            pos += m
        if V["memory"] == "wear":                            # the material heals between hits
            heal = np.exp(-n / (V["recovery"] * self.sr))
            self.fat *= heal
            if V["anneal"] > 0:
                self.wear *= heal ** V["anneal"]
                self.crack *= (self.wear > V["threshold"] * 0.5)
        return (out * 0.35 * V["level"]).astype(np.float32)


ENGINE = Material
