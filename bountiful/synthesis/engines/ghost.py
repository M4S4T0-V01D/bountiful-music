"""Ghost Engine: an instrument that remembers what it played.

Three layers, all from one memory:
  live       the played notes, a band-limited additive tone
  ghosts     every released note leaves afterimages: fainter replays `spacing` beats apart, each one detuned at
             random (detune) and drifting further from the original (drift), panned somewhere new: a memory going soft
  residue    a running magnitude spectrum of everything played (analysed every 1024 samples over the last 2048),
             leaking at a rate set by `memory`, resynthesised with fresh random phases into a pad: the room's memory of
             the music. `freeze` slows the leak to nothing, holding the residue while new notes play over it;
             capture() stores the memory (residue + remembered notes) and recall() brings it back later.

State (all in snapshots): remembered notes, scheduled and sounding ghosts, the residue spectrum, the analysis
history, the overlap-add tail and any captured memory.
"""
from __future__ import annotations

import numpy as np

from synthesis.engine_api import Engine, Param, voice_env
from synthesis.engines._dsp import additive, cents, hz, phases, stereo

N_FFT = 2048
HOP = 1024
WIN = np.sqrt(np.hanning(N_FFT + 1)[:N_FFT])           # sqrt-Hann in and out: overlap-add at 50 % sums to 1


class Ghost(Engine):
    ID = "ghost"
    NAME = "Ghost Engine"
    VERSION = 1
    DESCRIPTION = "Remembers recent pitches, levels and spectrum: afterimages, a residue pad, freeze, capture, recall."
    POLY = 10
    PARAMS = (
        Param("memory", 8.0, 0.5, 30.0, unit="s", doc="how long the residue and the note memory last"),
        Param("afterimage", 0.5, 0.0, 1.0, doc="level of the ghost replays"),
        Param("echoes", 3, 0, 6, "int", doc="ghosts per released note"),
        Param("spacing", 0.75, 0.25, 4.0, unit="beats", doc="time between ghosts"),
        Param("fade", 0.6, 0.1, 0.95, doc="each ghost's level relative to the one before"),
        Param("detune", 8.0, 0.0, 50.0, unit="cents", doc="random mistuning of each ghost"),
        Param("drift", -6.0, -50.0, 50.0, unit="cents", doc="steady drift per generation of ghost"),
        Param("residue", 0.35, 0.0, 1.0, doc="level of the spectral residue pad"),
        Param("freeze", 0.0, 0.0, 1.0, doc="0 = the residue follows the music, 1 = held as it is"),
        Param("smear", 0.3, 0.0, 1.0, doc="blur of the residue across frequency"),
        Param("tone", 0.5, 0.0, 1.0, doc="brightness of the live tone"),
        Param("attack", 0.02, 0.001, 2.0, unit="s"),
        Param("release", 0.6, 0.01, 6.0, unit="s"),
        Param("width", 0.7, 0.0, 1.0),
        Param("level", 1.0, 0.0, 2.0),
    )
    PRESETS = {
        "afterimage-pad": {"memory": 14, "afterimage": 0.55, "echoes": 3, "spacing": 1.5, "fade": 0.62, "detune": 10,
                           "drift": -8, "residue": 0.5, "smear": 0.5, "tone": 0.35, "attack": 0.4, "release": 2.0},
        "haunted-keys": {"memory": 6, "afterimage": 0.7, "echoes": 4, "spacing": 0.75, "fade": 0.55, "detune": 14,
                         "drift": -12, "residue": 0.2, "tone": 0.6, "attack": 0.005, "release": 0.5},
        "frozen-choir": {"memory": 20, "afterimage": 0.3, "residue": 0.8, "freeze": 0.85, "smear": 0.7, "tone": 0.3,
                         "attack": 0.8, "release": 3.0, "width": 1.0},
        "memory-lead": {"memory": 4, "afterimage": 0.45, "echoes": 2, "spacing": 0.5, "detune": 4, "drift": 5,
                        "residue": 0.1, "tone": 0.8, "attack": 0.01, "release": 0.3},
        "residue-wash": {"memory": 25, "afterimage": 0.2, "echoes": 1, "residue": 1.0, "smear": 0.9, "tone": 0.4,
                         "attack": 0.2, "release": 1.5},
        "ghost-bells": {"memory": 5, "afterimage": 0.8, "echoes": 6, "spacing": 0.25, "fade": 0.7, "detune": 25,
                        "drift": 18, "residue": 0.15, "tone": 0.9, "attack": 0.002, "release": 0.25},
    }

    def init_state(self) -> None:
        self.memory: list = []
        self.sched: list = []
        self.ghosts: list = []
        self.res = np.zeros(N_FFT // 2 + 1)
        self.hist = np.zeros(N_FFT)
        self.ola = np.zeros((N_FFT, 2))
        self.queue = np.zeros((0, 2))
        self.count = 0                                  # samples since the last analysis boundary
        self.captured = None

    def state(self) -> dict:
        return {"memory": self.memory, "sched": self.sched, "ghosts": self.ghosts, "res": self.res, "hist": self.hist,
                "ola": self.ola, "queue": self.queue, "count": self.count, "captured": self.captured}

    def load_state(self, d: dict) -> None:
        self.init_state()
        for k in ("memory", "sched", "ghosts", "captured"):
            if k in d:
                setattr(self, k, d[k])
        for k in ("res", "hist", "ola", "queue"):
            if k in d:
                setattr(self, k, np.asarray(d[k], float))
        self.count = int(d.get("count", 0))

    # ------------------------------------------------------------------ memory
    def capture(self) -> dict:
        """Store the present memory; recall() puts it back (in the Lab: the Capture / Recall buttons)."""
        self.captured = {"res": self.res.copy(), "memory": [dict(m) for m in self.memory]}
        return self.captured

    def recall(self) -> bool:
        if not self.captured:
            return False
        self.res = np.asarray(self.captured["res"], float).copy()
        self.memory = [dict(m) for m in self.captured["memory"]]
        return True

    def on_note(self, v: dict) -> None:
        v["ph"] = float(self.rng.random())
        v["t_on"] = self.t

    def on_off(self, v: dict) -> None:
        v_ = self.v
        dur = (self.t - v.get("t_on", self.t)) / self.sr
        self.memory.append({"pitch": v["pitch"], "vel": v["vel"], "t": self.t, "dur": round(dur, 4)})
        horizon = self.t - v_["memory"] * self.sr
        self.memory = [m for m in self.memory if m["t"] >= horizon][-32:]
        beat_s = 60.0 / self.bpm
        amp = v["vel"] * v_["afterimage"]
        for k in range(1, int(v_["echoes"]) + 1):
            amp *= v_["fade"]
            if amp < 1e-3:
                break
            off = self.rng.normal(0, v_["detune"]) + v_["drift"] * k
            self.sched.append({"at": int(self.t + k * v_["spacing"] * beat_s * self.sr), "pitch": v["pitch"] + off / 100.0,
                               "amp": float(amp), "pan": float(self.rng.uniform(-1, 1) * v_["width"]),
                               "life": float(min(max(dur, 0.15), 2.0) + v_["release"]), "age": 0, "ph": float(self.rng.random())})

    def alive(self, v: dict) -> bool:
        return v["gate"] or v["rel"] < self.v["release"] * self.sr

    # ------------------------------------------------------------------ sound
    def _live(self, n: int) -> np.ndarray:
        out = np.zeros((n, 2))
        v_ = self.v
        for v in self.voices:
            f = hz(v["pitch"])
            p, v["ph"] = phases(v["ph"], f / self.sr, n)
            env = voice_env(v, n, self.sr, v_["attack"], v_["release"])
            pan = ((v["pitch"] - 60) / 30.0) * v_["width"] * 0.5
            out += stereo(additive(p, f, self.sr, v_["tone"]) * env * v["vel"] * 0.3, pan)
        return out

    def _ghosts(self, n: int, t: int) -> np.ndarray:
        out = np.zeros((n, 2))
        due = [g for g in self.sched if g["at"] < t + n]
        self.sched = [g for g in self.sched if g["at"] >= t + n]
        for g in due:
            g["age"] = min(0, t - g["at"])             # negative: starts inside this chunk
            self.ghosts.append(g)
        keep = []
        for g in self.ghosts:
            f = hz(g["pitch"])
            i = np.arange(n) + g["age"]
            t = np.maximum(i, 0) / self.sr
            env = np.where(i >= 0, np.minimum(t / 0.03, 1.0) * np.exp(-3.0 * t / g["life"]), 0.0)
            p, g["ph"] = phases(g["ph"], f / self.sr, n)
            out += stereo(additive(p, f, self.sr, self.v["tone"] * 0.4, 8) * env * g["amp"] * 0.3, g["pan"])
            g["age"] += n
            if g["age"] < g["life"] * self.sr * 1.6:
                keep.append(g)
        self.ghosts = keep[-48:]
        return out

    def _analyse(self) -> None:
        mag = np.abs(np.fft.rfft(self.hist * WIN))
        sm = self.v["smear"]
        if sm > 0.01:
            w = int(1 + sm * 12)
            mag = np.convolve(mag, np.hanning(2 * w + 1) / np.hanning(2 * w + 1).sum(), mode="same")
        leak = np.exp(-HOP / (self.v["memory"] * self.sr))
        leak = leak + (1 - leak) * self.v["freeze"] ** 0.5
        self.res = leak * self.res + (1 - leak) * mag

    def _frame(self) -> None:
        for c in range(2):
            ph = np.exp(2j * np.pi * self.rng.random(len(self.res)))
            self.ola[:, c] += np.fft.irfft(self.res * ph, N_FFT) * WIN
        self.queue = np.concatenate([self.queue, self.ola[:HOP]])
        self.ola = np.concatenate([self.ola[HOP:], np.zeros((HOP, 2))])

    def synth(self, n: int, inp) -> np.ndarray:
        out = np.zeros((n, 2))
        pos = 0
        while pos < n:
            m = min(n - pos, HOP - self.count)
            live = self._live(m)
            ghosts = self._ghosts(m, self.t + pos)
            mix = live + ghosts
            self.hist = np.concatenate([self.hist[m:], mix.mean(1)])
            if len(self.queue) < m:
                self._frame()
            res, self.queue = self.queue[:m], self.queue[m:]
            out[pos:pos + m] = mix + res * self.v["residue"] * 1.5
            self.count += m
            if self.count >= HOP:
                self.count = 0
                self._analyse()
                self._frame()
            pos += m
        return (out * self.v["level"]).astype(np.float32)


ENGINE = Ghost
