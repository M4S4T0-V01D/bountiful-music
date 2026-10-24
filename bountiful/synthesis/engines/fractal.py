"""Fractal Rhythm: rhythms grown by recursive subdivision of the cycle, played on the notes you hold.

A cycle (`cycle` beats) is a cell. A seeded motif decides, for each child position, whether that child splits again
and into how many parts (`ratio`: 2, 3, mixed, or golden 0.618 / 0.382 cuts). The same motif is applied at every
level, so the rhythm is self-similar: the bar's shape reappears inside each beat and inside each half-beat. `chaos`
lets a level deviate from the motif, `split` scales how often cells divide, `density` thins the leaves. Every leaf is
a hit; its depth gives its voice: deeper hits are shorter (decay ∝ cell length), quieter, and `step` semitones higher,
so the levels of the tree sound as registers. Held notes are the pitches the hits cycle through, like an arpeggiator
whose pattern is a fractal. `mutate` re-grows the tree each cycle (a fresh seeded motif) by that probability.

Hard limits keep it bounded whatever the patch: depth ≤ 6, cells never shorter than `min_cell` beats nor 8 ms,
at most 128 hits per cycle and 24 sounding hits (the oldest are dropped). Hits land on absolute samples computed
from the tempo and the song beat, so rendering is block-size invariant; their noise comes from a seeded table.
"""
from __future__ import annotations

import numpy as np

from synthesis.engine_api import Engine, Param
from synthesis.engines._dsp import hz

MAX_DEPTH = 6
MAX_HITS = 128
MAX_SOUNDING = 24
NOISE = 1 << 16
GOLD = 0.6180339887


def grow(seed: int, cycle_no: int, P: dict, min_beats: float) -> list:
    """The cycle's leaves: (start, length, depth, accent), start and length in beats, sorted, hard-capped."""
    r = np.random.default_rng([seed & 0x7FFFFFFF, 71, cycle_no])
    motif_split = {k: r.permutation((np.arange(k) + r.random(k)) / k) for k in (2, 3)}   # per child position of a
                                                     # k-split: threshold, stratified so `split` is the share
    motif_ratio = r.integers(0, 2, 8)                          # per child position: 2 or 3 when "2-3"
    depth = int(min(P["depth"], MAX_DEPTH))
    leaves: list = []
    stack = [(0.0, float(P["cycle"]), 0, 0, 2, 1.0)]           # start, length, depth, child index, siblings, accent
    while stack and len(leaves) < MAX_HITS:
        s, L, d, ci, sib, acc = stack.pop()
        dev = r.random() < P["chaos"]
        thr = r.random() if dev else motif_split[sib][ci]
        can = d < depth and L / 2 >= min_beats
        if can and (d == 0 or thr < P["split"]):
            ratio = P["ratio"]
            if ratio == "golden":
                cuts = [0.0, GOLD, 1.0] if (ci + d) % 2 == 0 else [0.0, 1 - GOLD, 1.0]
            else:
                k = 2 if ratio == "2" else 3 if ratio == "3" else (2, 3)[(motif_ratio[ci % 8] + dev) % 2]
                if L / k < min_beats:
                    k = 2
                cuts = list(np.linspace(0, 1, k + 1))
            kids = [(s + L * a, L * (b - a), d + 1, j, len(cuts) - 1, acc * (1.0 if j == 0 else 0.7))
                    for j, (a, b) in enumerate(zip(cuts, cuts[1:]))]
            stack.extend(reversed(kids))
        else:
            leaves.append((s, L, d, acc))
    leaves.sort()
    keep = r.random(len(leaves)) < P["density"]
    keep[:1] = True                                            # the downbeat always sounds
    return [lf for lf, k in zip(leaves, keep) if k]


class Fractal(Engine):
    ID = "fractal"
    NAME = "Fractal Rhythm"
    VERSION = 1
    DESCRIPTION = "Self-similar recursive subdivision of the cycle; depth sets register and decay; hard limits."
    POLY = 8
    PARAMS = (
        Param("cycle", 4.0, 0.5, 16.0, unit="beats", doc="length of the cell that is subdivided"),
        Param("depth", 4, 1, MAX_DEPTH, "int", doc="levels of subdivision (hard limit 6)"),
        Param("split", 0.6, 0.0, 1.0, doc="how often a cell divides"),
        Param("ratio", "2-3", kind="choice", choices=("2", "3", "2-3", "golden")),
        Param("chaos", 0.1, 0.0, 1.0, doc="chance a level deviates from the motif"),
        Param("density", 0.85, 0.05, 1.0, doc="share of leaves that sound"),
        Param("min_cell", 0.125, 0.03125, 1.0, unit="beats", doc="shortest cell (hard limit; also never < 8 ms)"),
        Param("mutate", 0.0, 0.0, 1.0, doc="chance per cycle that the tree regrows"),
        Param("step", 7.0, -12.0, 12.0, unit="st", doc="pitch added per level of depth"),
        Param("decay", 0.8, 0.05, 2.0, doc="hit length relative to its cell"),
        Param("tone", 0.15, 0.0, 1.0, doc="sine (0) to noise (1)"),
        Param("fm", 0.5, 0.0, 4.0, doc="self-FM index of each hit, falling as it decays"),
        Param("accent", 0.6, 0.0, 1.0, doc="how much quieter the off-children are"),
        Param("swing", 0.0, 0.0, 0.5, doc="delays odd leaves by a share of their length"),
        Param("width", 0.6, 0.0, 1.0),
        Param("level", 1.0, 0.0, 2.0),
    )
    PRESETS = {
        "binary-tree": {"ratio": "2", "depth": 4, "split": 0.7, "step": 12.0, "tone": 0.1, "fm": 0.3},
        "triplet-fern": {"ratio": "3", "depth": 3, "split": 0.55, "step": 5.0, "fm": 1.2, "cycle": 3.0},
        "golden-clock": {"ratio": "golden", "depth": 5, "split": 0.8, "step": -5.0, "decay": 1.2, "tone": 0.0,
                         "fm": 0.8},
        "fractal-machine": {"ratio": "2-3", "depth": 6, "split": 0.75, "chaos": 0.25, "mutate": 0.5,
                            "min_cell": 0.0625, "step": 7.0, "tone": 0.35, "fm": 2.0, "accent": 0.8},
        "dust-snare": {"ratio": "2", "depth": 5, "split": 0.6, "tone": 0.85, "decay": 0.7, "step": 0.0,
                       "swing": 0.2, "density": 0.7},
        "slow-bloom": {"cycle": 16.0, "depth": 6, "ratio": "golden", "split": 0.9, "decay": 2.0, "fm": 0.2,
                       "step": 3.0, "tone": 0.0},
    }

    def init_state(self) -> None:
        self.noise = np.random.default_rng([self.seed & 0x7FFFFFFF, 73]).standard_normal(NOISE)
        self.hits: list = []
        self.n_hits = 0
        self._cache: dict = {}

    def state(self) -> dict:
        return {"hits": self.hits, "n_hits": self.n_hits}

    def load_state(self, d: dict) -> None:
        self.hits = [dict(h) for h in d.get("hits", [])]
        self.n_hits = int(d.get("n_hits", 0))
        self._cache = {}

    def _pattern(self, cycle_no: int) -> list:
        V = self.v
        key = (cycle_no, V["cycle"], V["depth"], V["split"], V["ratio"], V["chaos"], V["density"], V["min_cell"],
               V["mutate"])
        if key not in self._cache:
            if len(self._cache) > 32:
                self._cache.clear()
            grown = 0                                         # the latest cycle at or before this one that regrew
            if V["mutate"] > 0:
                for c in range(cycle_no, max(-1, cycle_no - 64), -1):
                    if c > 0 and np.random.default_rng([self.seed & 0x7FFFFFFF, 83, c]).random() < V["mutate"]:
                        grown = c
                        break
            min_beats = max(V["min_cell"], 0.008 * self.bpm / 60.0)
            self._cache[key] = grow(self.seed, grown, V, min_beats)
        return self._cache[key]

    def pattern_info(self) -> dict:
        """For the Lab's display: the current cycle's leaves."""
        self._controls()
        cyc = int(np.floor(self.beat() / self.v["cycle"]))
        return {"cycle": cyc, "leaves": [[round(s, 4), round(L, 4), d] for s, L, d, _ in self._pattern(cyc)]}

    def _trigger(self, at_rel: int, leaf: tuple, k: int) -> None:
        V = self.v
        held = [v for v in self.voices if v["gate"]]
        if not held:
            return
        s, L, d, acc = leaf
        v = held[k % len(held)]
        spb = self.sr * 60.0 / self.bpm
        self.n_hits += 1
        pitch = v["pitch"] + V["step"] * d
        while hz(pitch) > self.sr * 0.3:
            pitch -= 12
        self.hits.append({"f": float(hz(pitch)), "amp": float(v["vel"] * (1 - V["accent"] * (1 - acc)) * 0.85 ** d),
                          "dec": float(max(L * spb * V["decay"], 0.008 * self.sr)), "age": -int(at_rel),
                          "ph": 0.0, "nid": int(self.n_hits * 7919 % NOISE),
                          "pan": float(((self.n_hits * 0.618) % 1.0 - 0.5) * 2 * V["width"])})
        if len(self.hits) > MAX_SOUNDING:
            self.hits = self.hits[-MAX_SOUNDING:]

    def synth(self, n: int, inp) -> np.ndarray:
        V = self.v
        spb = self.sr * 60.0 / self.bpm
        b0 = self.beat()
        b1 = self.beat(self.t + n)
        cyc = V["cycle"]
        for c in range(int(np.floor(b0 / cyc)), int(np.floor(b1 / cyc)) + 1):
            for k, leaf in enumerate(self._pattern(c)):
                s, L = leaf[0], leaf[1]
                hb = c * cyc + s + (V["swing"] * L if k % 2 else 0.0)
                at = self._start + int(round((hb - self.t0_beats) * spb))
                if self.t <= at < self.t + n:
                    self._trigger(at - self.t, leaf, k)
        out = np.zeros((n, 2))
        i = np.arange(n)
        keep = []
        for h in self.hits:
            age = h["age"] + i
            on = age >= 0
            a = np.where(on, np.exp(-np.maximum(age, 0) * 4.6 / h["dec"]), 0.0) * h["amp"]
            ph = h["ph"] + np.cumsum(on) * h["f"] / self.sr
            sig = np.sin(2 * np.pi * ph + V["fm"] * a / max(h["amp"], 1e-6) * np.sin(2 * np.pi * ph))
            nz = self.noise[(h["nid"] + np.maximum(age, 0)) % NOISE]
            y = ((1 - V["tone"]) * sig + V["tone"] * nz * 0.6) * a
            pa = (np.clip(h["pan"], -1, 1) + 1) * np.pi / 4
            out[:, 0] += y * np.cos(pa)
            out[:, 1] += y * np.sin(pa)
            h["ph"] = float(ph[-1] % 1.0)
            h["age"] += n
            if h["age"] < h["dec"] * 2.5:
                keep.append(h)
        self.hits = keep
        return (out * 0.9 * V["level"]).astype(np.float32)


ENGINE = Fractal
