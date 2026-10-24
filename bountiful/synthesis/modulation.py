"""Shared modulation: sources any engine parameter can follow, through one matrix.

    m = Matrix([{"source": {"type": "lfo", "rate_beats": 4}, "target": "memory", "amount": 0.3}, ...], seed=3)
    engine.render(events, n, modulation=m)

Each route adds source x amount x (the parameter's range) to the parameter, block by block, after automation.
Sources (all deterministic; random ones draw from the matrix's own seed):

  lfo       shape sine|tri|saw|square|sh, rate_hz or rate_beats (tempo-synced), phase 0-1, bipolar (default true)
  envelope  attack / decay / sustain / release s, following the engine's gate (any key held)
  step      values [...], step_beats: a step sequencer
  cc        number: a MIDI controller's last value (0-1) on that engine
  song      position: beat / length_beats (0-1 over the song), or bar_phase / beat_phase
  random    rate_beats, smooth 0-1: a seeded random walk (sample-and-hold, glided)
  moves     Electronium operator moves [{bar, to_bar?, set {param: value}}]: absolute values (amount ignored; target
            = which key of `set` to follow); converted by moves_lane() to an automation lane instead when possible
"""
from __future__ import annotations

import zlib

import numpy as np

SHAPES = ("sine", "tri", "saw", "square", "sh")


def stable_seed(*parts) -> int:
    """A seed from names and numbers that is the same on every run and machine (not Python's salted hash)."""
    return zlib.crc32("/".join(map(str, parts)).encode()) & 0x7FFFFFFF


class Source:
    def __init__(self, spec: dict, seed: int):
        self.s = spec
        self.seed = seed
        self.kind = spec.get("type", "lfo")
        self.env = 0.0
        self.stage_t = 0.0
        self.held = 0.0
        self._sh: dict = {}
        self.last = None

    def value(self, engine, beat: float) -> float:
        s, k = self.s, self.kind
        if k == "lfo":
            if "rate_hz" in s:
                ph = beat * 60.0 / engine.bpm * s["rate_hz"]
            else:
                ph = beat / max(s.get("rate_beats", 4.0), 1e-3)
            ph = ph + s.get("phase", 0.0)
            f = ph % 1.0
            shape = s.get("shape", "sine")
            if shape == "sine":
                y = np.sin(2 * np.pi * f)
            elif shape == "tri":
                y = 1 - 4 * abs(f - 0.5)
            elif shape == "saw":
                y = 2 * f - 1
            elif shape == "square":
                y = 1.0 if f < 0.5 else -1.0
            else:                                           # sample and hold, one value per cycle, seeded by cycle number
                c = int(np.floor(ph))
                if c not in self._sh:
                    self._sh = {c: float(np.random.default_rng(stable_seed("sh", self.seed, c, s.get("seed", 0))).uniform(-1, 1))}
                y = self._sh[c]
            return float(y if s.get("bipolar", True) else (y + 1) / 2)
        if k == "envelope":
            dt = max(0.0, beat - self.last) * 60.0 / engine.bpm if self.last is not None else 0.0
            self.last = beat
            a, d, su, r = s.get("attack", 0.01), s.get("decay", 0.3), s.get("sustain", 0.6), s.get("release", 0.5)
            if engine.gate:
                self.stage_t += dt
                t = self.stage_t
                self.env = min(1.0, t / max(a, 1e-4)) if t < a else su + (1 - su) * np.exp(-(t - a) / max(d, 1e-4))
                self.held = self.env
            else:
                self.stage_t = 0.0
                self.env = max(0.0, self.env - dt * max(self.held, 1e-3) / max(r, 1e-4))
            return float(self.env)
        if k == "step":
            vals = s.get("values", [0.0])
            return float(vals[int(beat // max(s.get("step_beats", 1.0), 1e-3)) % len(vals)])
        if k == "cc":
            return float(engine.cc.get(int(s.get("number", 1)), s.get("default", 0.0)))
        if k == "song":
            pos = s.get("position", "song")
            if pos == "bar_phase":
                return float((beat / 4.0) % 1.0)
            if pos == "beat_phase":
                return float(beat % 1.0)
            return float(np.clip(beat / max(s.get("length_beats", 256.0), 1.0), 0, 1))
        if k == "random":
            rb = max(s.get("rate_beats", 1.0), 1e-3)
            c = int(beat // rb)
            for i in (c, c + 1):
                if i not in self._sh:
                    self._sh[i] = float(np.random.default_rng(stable_seed("rw", self.seed, s.get("seed", 0), i)).uniform(-1, 1))
            if len(self._sh) > 64:
                self._sh = {i: self._sh[i] for i in (c, c + 1)}
            f = (beat / rb) % 1.0
            sm = float(s.get("smooth", 0.5))
            g = min(1.0, f / max(sm, 1e-3)) if sm > 0 else 1.0
            prev = self._sh.get(c - 1, self._sh[c])
            return prev + (self._sh[c] - prev) * g
        if k == "moves":
            lane = moves_lane(s.get("moves", []), s.get("key", ""))
            from synthesis.engine_api import _lane
            return float(_lane(lane, beat)) if lane else 0.0
        raise ValueError(f"unknown modulation source {k!r}")


class Matrix:
    """Routes: [{"source": {...}, "target": param, "amount": -1..1, "engine": id?}]. Deterministic for a seed."""

    def __init__(self, routes: list | None = None, seed: int = 0):
        self.seed = seed
        self.routes = []
        for r in routes or []:
            if not r.get("target"):
                continue
            self.routes.append((Source(r.get("source", {}), seed + len(self.routes)), r["target"],
                                float(np.clip(r.get("amount", 0.0), -1, 1)), r.get("engine")))
        self.spec = list(routes or [])

    def offsets(self, engine, beat: float) -> dict:
        out: dict = {}
        for src, target, amt, only in self.routes:
            if only and only != engine.ID:
                continue
            if src.kind == "moves":
                continue                                    # absolute values: applied as automation (moves_lane)
            out[target] = out.get(target, 0.0) + src.value(engine, beat) * amt
        return out

    def to_json(self) -> dict:
        return {"routes": self.spec, "seed": self.seed}

    @classmethod
    def from_json(cls, d: dict | None) -> "Matrix | None":
        return cls(d.get("routes", []), d.get("seed", 0)) if d and d.get("routes") else None


def moves_lane(moves: list, key: str, beats_per_bar: float = 4.0, start=None) -> list:
    """Electronium moves -> an automation lane [[beat, value], ...] for one key. A move with to_bar ramps from the
    value before it (bar) to its value (to_bar), as Machine.at does; without, it jumps at its bar. Bars are 0-based.
    start: the value before the first move (the patch's), so a first ramp ramps from it instead of jumping."""
    lane: list = []
    cur = start
    for m in sorted((m for m in moves if key in m.get("set", {})), key=lambda m: m.get("bar", 0)):
        v = m["set"][key]
        b0 = m.get("bar", 0) * beats_per_bar
        if m.get("to_bar") is not None and cur is not None:
            lane += [[b0, cur], [m["to_bar"] * beats_per_bar, v]]
        else:
            if cur is not None:
                lane.append([b0 - 1e-3, cur])
            lane.append([b0, v])
        cur = v
    return lane
