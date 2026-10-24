"""The contract every Synthesis Lab engine keeps. An engine is a stateful instrument rendered in blocks:

    e = ghost.Engine(params={"memory": 0.8}, seed=7)
    e.begin(events, bpm=172, automation={"memory": [[0, 0.2], [16, 0.9]]})
    while ...: block = e.block(256)           # (256, 2) float32, live-capable: no look-ahead past the block
    y = e.render(events, n, bpm=172)          # offline: begin + every block, the same samples

  events      (sample, kind, a, b) with kind "on" (pitch, vel 0-1), "off" (pitch, 0), "cc" (number, value 0-1)
  params      a schema of Param; values are clamped, automated by beat, and offset by the modulation matrix
  seed        all randomness comes from self.rng (numpy PCG64 seeded here), so a render is reproducible
  snapshot()  params + seed + clock + rng state + the engine's own state (JSON-safe); restore() resumes exactly
  patch()     what a preset or a song stores: engine id, version, params, seed
  diagnostics() blocks, CPU ms, real-time factor, voices

Subclasses set ID, NAME, VERSION, PARAMS, PRESETS and implement init_state(), on_note(), on_off(), synth(n, inp)
and, when they keep state worth saving, state() / load_state().
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

SR = 44100
BLOCK = 256
CAPS_BASE = frozenset({"offline", "block", "midi", "automation", "modulation", "snapshot", "seed"})


@dataclass(frozen=True)
class Param:
    name: str
    default: float
    lo: float = 0.0
    hi: float = 1.0
    kind: str = "float"            # float | int | bool | choice
    choices: tuple = ()
    unit: str = ""
    doc: str = ""

    def clamp(self, v):
        if self.kind == "choice":
            return v if v in self.choices else self.default
        if self.kind == "bool":
            return bool(v)
        v = float(np.clip(float(v), self.lo, self.hi)) if np.isfinite(float(v)) else float(self.default)
        return int(round(v)) if self.kind == "int" else v

    def schema(self) -> dict:
        d = {"name": self.name, "default": self.default, "kind": self.kind, "unit": self.unit, "doc": self.doc}
        if self.kind == "choice":
            d["choices"] = list(self.choices)
        else:
            d.update(lo=self.lo, hi=self.hi)
        return d


def note_events(notes: list, t0: float = 0.0, sr: int = SR) -> list:
    """render_midi.py notes ({start, end, pitch, vel} in seconds) -> engine events, sorted, offsets from t0."""
    ev = []
    for nt in notes:
        i0 = int(round((nt["start"] - t0) * sr))
        i1 = max(i0 + 1, int(round((nt["end"] - t0) * sr)))
        ev.append((i0, "on", int(nt["pitch"]), float(nt["vel"])))
        ev.append((i1, "off", int(nt["pitch"]), 0.0))
    return sorted(ev, key=lambda e: (e[0], e[1] != "off"))        # an off before an on at the same sample


def beat_events(notes: list, bpm: float, sr: int = SR) -> list:
    """(beat, length beats, pitch, vel) -> engine events, for tests, demos and the Lab keyboard."""
    s = 60.0 / bpm
    return note_events([{"start": b * s, "end": (b + d) * s, "pitch": p, "vel": v} for b, d, p, v in notes], 0.0, sr)


class Engine:
    ID = "engine"
    NAME = "Engine"
    VERSION = 1
    DESCRIPTION = ""
    PARAMS: tuple = ()
    PRESETS: dict = {}
    CAPS = CAPS_BASE
    POLY = 8                       # voices before the oldest is stolen

    def __init__(self, params: dict | None = None, seed: int = 0, sr: int = SR, assets: dict | None = None):
        self.sr = sr
        self.seed = int(seed)
        self.assets = dict(assets or {})          # file references (Oracle's source WAV): {name: path}
        self.schema = {p.name: p for p in self.PARAMS}
        self.p = {p.name: p.default for p in self.PARAMS}
        for k, v in (params or {}).items():
            if k in self.schema:
                self.p[k] = self.schema[k].clamp(v)
        self.v = dict(self.p)
        self.automation: dict = {}
        self.modulation = None
        self.bpm = 120.0
        self.t0_beats = 0.0
        self.events: list = []
        self._ei = 0
        self._start = 0
        self.reset()

    # ------------------------------------------------------------------ parameters
    def set(self, name: str, value) -> None:
        if name not in self.schema:
            raise KeyError(f"{self.ID} has no parameter {name!r}")
        self.p[name] = self.schema[name].clamp(value)
        self.v[name] = self.p[name]

    def get(self, name: str):
        return self.p[name]

    @classmethod
    def describe(cls) -> dict:
        return {"id": cls.ID, "name": cls.NAME, "version": cls.VERSION, "description": cls.DESCRIPTION,
                "params": [p.schema() for p in cls.PARAMS], "presets": sorted(cls.PRESETS), "caps": sorted(cls.CAPS),
                "poly": cls.POLY}

    # ------------------------------------------------------------------ state
    def reset(self) -> None:
        """Back to the state a fresh engine with these params and seed has."""
        self.rng = np.random.default_rng(self.seed)
        self.t = 0
        self.voices: list = []
        self.cc: dict = {}
        self.gate = 0.0
        self._vid = 0
        self._diag = {"blocks": 0, "cpu_s": 0.0, "samples": 0, "peak_voices": 0}
        self.init_state()

    def init_state(self) -> None:
        pass

    def state(self) -> dict:
        return {}

    def load_state(self, d: dict) -> None:
        pass

    def snapshot(self) -> dict:
        return {"engine": self.ID, "version": self.VERSION, "params": dict(self.p), "seed": self.seed, "t": self.t,
                "rng": _jsonable(self.rng.bit_generator.state), "voices": _jsonable(self.voices), "cc": dict(self.cc),
                "gate": self.gate, "vid": self._vid, "state": _jsonable(self.state())}

    def restore(self, snap: dict) -> None:
        if snap.get("engine") != self.ID:
            raise ValueError(f"snapshot is for {snap.get('engine')!r}, not {self.ID!r}")
        self.seed = int(snap.get("seed", self.seed))
        self.reset()
        for k, v in snap.get("params", {}).items():
            if k in self.schema:
                self.p[k] = self.schema[k].clamp(v)
        self.v = dict(self.p)
        self.t = int(snap.get("t", 0))
        if snap.get("rng"):
            self.rng.bit_generator.state = snap["rng"]
        self.voices = [_unjson(v) for v in snap.get("voices", [])]
        self.cc = {int(k): v for k, v in snap.get("cc", {}).items()}
        self.gate = snap.get("gate", 0.0)
        self._vid = int(snap.get("vid", len(self.voices)))
        self.load_state(_unjson(snap.get("state", {})))

    def patch(self) -> dict:
        d = {"engine": self.ID, "version": self.VERSION, "params": dict(self.p), "seed": self.seed}
        if self.assets:
            d["assets"] = dict(self.assets)
        return d

    @classmethod
    def from_patch(cls, patch: dict, sr: int = SR) -> "Engine":
        return cls(params=patch.get("params", {}), seed=patch.get("seed", 0), sr=sr, assets=patch.get("assets"))

    def diagnostics(self) -> dict:
        d = self._diag
        secs = d["samples"] / self.sr
        return {"blocks": d["blocks"], "cpu_ms": round(d["cpu_s"] * 1000, 2), "audio_s": round(secs, 3),
                "rt_factor": round(d["cpu_s"] / secs, 4) if secs else 0.0, "voices": len(self.voices),
                "peak_voices": d["peak_voices"]}

    # ------------------------------------------------------------------ events
    def note_on(self, pitch: int, vel: float) -> None:
        if len(self.voices) >= self.POLY:
            pool = [v for v in self.voices if not v["gate"]] or self.voices   # steal a released voice first, then the oldest
            self.voices.remove(max(pool, key=lambda v: v["age"]))
        v = {"pitch": int(pitch), "vel": float(vel), "age": 0, "gate": True, "rel": 0, "id": self._next_id()}
        self.voices.append(v)
        self.gate = 1.0
        self.on_note(v)

    def note_off(self, pitch: int) -> None:
        for v in self.voices:
            if v["pitch"] == pitch and v["gate"]:
                v["gate"] = False
                self.on_off(v)
                break
        self.gate = 1.0 if any(v["gate"] for v in self.voices) else 0.0

    def control(self, number: int, value: float) -> None:
        self.cc[int(number)] = float(value)

    def _next_id(self) -> int:
        self._vid += 1
        return self._vid

    def on_note(self, v: dict) -> None:
        pass

    def on_off(self, v: dict) -> None:
        pass

    # ------------------------------------------------------------------ rendering
    def begin(self, events: list | None = None, bpm: float = 120.0, automation: dict | None = None, modulation=None,
              t0_beats: float = 0.0) -> None:
        """Arm a render: events in samples from now, automation {param: [[beat, value], ...]} in song beats."""
        self.events = sorted(events or [], key=lambda e: (e[0], e[1] != "off"))
        self._ei = 0
        self.bpm = float(bpm)
        self.automation = {k: sorted(v) for k, v in (automation or {}).items() if k in self.schema and v}
        self.modulation = modulation
        self.t0_beats = t0_beats
        self._start = self.t

    def beat(self, at: int | None = None) -> float:
        return self.t0_beats + ((self.t if at is None else at) - self._start) / self.sr * self.bpm / 60.0

    def _controls(self) -> None:
        """Effective values for the next block: base -> automation -> modulation, clamped."""
        b = self.beat()
        for k, lane in self.automation.items():
            self.p[k] = self.schema[k].clamp(_lane(lane, b))
        v = dict(self.p)
        if self.modulation is not None:
            for k, off in self.modulation.offsets(self, b).items():
                s = self.schema.get(k)
                if s is not None and s.kind in ("float", "int"):
                    v[k] = s.clamp(v[k] + off * (s.hi - s.lo))
        self.v = v

    def block(self, n: int = BLOCK, inp: np.ndarray | None = None) -> np.ndarray:
        """The next n samples, (n, 2). Events falling inside the block split it so they land on their sample."""
        t_cpu = time.perf_counter()
        out = np.zeros((n, 2), np.float32)
        pos = 0
        while pos < n:
            while self._ei < len(self.events) and self._start + self.events[self._ei][0] <= self.t:
                self._event(self.events[self._ei])
                self._ei += 1
            nxt = self._start + self.events[self._ei][0] if self._ei < len(self.events) else None
            m = n - pos if nxt is None else int(min(n - pos, max(1, nxt - self.t)))
            self._controls()
            y = self.synth(m, None if inp is None else inp[pos:pos + m])
            out[pos:pos + m] = y
            for v in self.voices:
                v["age"] += m
                if not v["gate"]:
                    v["rel"] += m
            self.voices = [v for v in self.voices if self.alive(v)]
            self.t += m
            pos += m
        np.nan_to_num(out, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        np.clip(out, -4.0, 4.0, out=out)                          # a broken patch can't blow up the mix
        d = self._diag
        d["blocks"] += 1
        d["samples"] += n
        d["cpu_s"] += time.perf_counter() - t_cpu
        d["peak_voices"] = max(d["peak_voices"], len(self.voices))
        return out

    def _event(self, e) -> None:
        _, kind, a, b = e
        if kind == "on":
            self.note_on(a, b)
        elif kind == "off":
            self.note_off(a)
        elif kind == "cc":
            self.control(a, b)

    def render(self, events: list | None, n: int, bpm: float = 120.0, automation: dict | None = None, modulation=None,
               t0_beats: float = 0.0, inp: np.ndarray | None = None, block: int = BLOCK) -> np.ndarray:
        self.begin(events, bpm, automation, modulation, t0_beats)
        out = np.zeros((n, 2), np.float32)
        for i in range(0, n, block):
            m = min(block, n - i)
            out[i:i + m] = self.block(m, None if inp is None else inp[i:i + m])
        return out

    # ------------------------------------------------------------------ subclasses
    def alive(self, v: dict) -> bool:
        """A released voice is dropped once its tail is done (default 2 s)."""
        return v["gate"] or v["rel"] < 2.0 * self.sr

    def synth(self, n: int, inp: np.ndarray | None) -> np.ndarray:
        return np.zeros((n, 2), np.float32)


def _lane(lane: list, beat: float) -> float:
    if beat <= lane[0][0]:
        return lane[0][1]
    for (b0, v0), (b1, v1) in zip(lane, lane[1:]):
        if beat < b1:
            if isinstance(v0, str) or b1 == b0:
                return v0
            return v0 + (v1 - v0) * (beat - b0) / (b1 - b0)
    return lane[-1][1]


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, np.ndarray):
        return {"__nd__": x.astype(float).tolist(), "dtype": str(x.dtype)}
    if isinstance(x, np.generic):
        return x.item()
    return x


def _unjson(x):
    if isinstance(x, dict):
        if "__nd__" in x:
            return np.asarray(x["__nd__"], dtype=x.get("dtype", "float64"))
        return {k: _unjson(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_unjson(v) for v in x]
    return x


def voice_env(v: dict, n: int, sr: int, attack: float, release: float) -> np.ndarray:
    """A voice's amplitude over the next n samples from its age and release count (no stored phase: restorable)."""
    i = np.arange(n)
    att = np.clip((v["age"] + i) / max(attack * sr, 1.0), 0, 1)
    if v["gate"]:
        return att
    return att * np.clip(1 - (v["rel"] + i) / max(release * sr, 1.0), 0, 1)
