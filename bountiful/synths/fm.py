"""4-operator FM (phase modulation, as the DX7 and the Yamaha chips do it): electric pianos, bells, glassy pads, FM bass,
brass, organ, clav.

  ops         up to 4 operators, each {ratio, detune cents, fixed Hz (instead of ratio), level, a, d, s, r, vel 0-1,
              ks 0-1}; a modulator's level is its index in radians, a carrier's is its output level. ks lowers a
              modulator's index above C5 (the harsh, aliasing top end), vel is how much velocity scales it
  algo        {op: [ops modulating it]}, a modulator always numbered higher than the op it feeds; out = carrier ops
  fb / fb_op  self-feedback (0-1.5) on one operator (default the last): the sine turns saw-like, the DX's growl
  chorus      mix 0-1; vibrato / glide / arp / pitch as in core.pitch
"""
from __future__ import annotations

import numpy as np
from scipy import signal

from synths import core as C

RATE = 100.0
OVER = 2


def _op(ratio=1.0, level=1.0, a=0.001, d=1.0, s=1.0, r=0.2, **kw):
    return {"ratio": ratio, "level": level, "a": a, "d": d, "s": s, "r": r, **kw}


PRESETS = {
    "e-piano": {"ops": [_op(1, 1.0, d=1.4, s=0.12, r=0.35), _op(1, 1.6, d=0.6, s=0.2, r=0.3, vel=0.8),
                        _op(1, 0.5, detune=4, d=1.1, s=0.08, r=0.35), _op(14, 0.9, d=0.035, s=0.0, vel=1.0)],
                "algo": {0: [1], 2: [3]}, "out": [0, 2], "chorus": 0.35, "level": 0.5},
    "dyno-piano": {"ops": [_op(1, 1.0, d=1.0, s=0.15, r=0.3), _op(1, 2.4, d=0.35, s=0.25, r=0.3, vel=1.0),
                           _op(1, 0.4, detune=-5, d=0.9, s=0.1, r=0.3), _op(17, 1.4, d=0.02, s=0.0, vel=1.0)],
                   "algo": {0: [1], 2: [3]}, "out": [0, 2], "chorus": 0.2, "level": 0.48},
    "fm-bell": {"ops": [_op(1, 1.0, d=2.6, s=0.0, r=2.0), _op(3.5, 2.2, d=1.6, s=0.0, r=1.5),
                        _op(1, 0.6, detune=3, d=3.2, s=0.0, r=2.5), _op(1.41, 1.6, d=2.0, s=0.0, r=2.0)],
                "algo": {0: [1], 2: [3]}, "out": [0, 2], "level": 0.5},
    "glass-pad": {"ops": [_op(1, 1.0, a=0.6, d=2.0, s=0.8, r=1.3), _op(2.005, 1.0, a=0.8, d=2.0, s=0.7, r=1.3),
                          _op(2, 0.4, detune=-6, a=0.7, d=2.0, s=0.8, r=1.3), _op(7, 0.45, a=1.0, d=2.0, s=0.5, r=1.0)],
                  "algo": {0: [1], 2: [3]}, "out": [0, 2], "chorus": 0.55, "level": 0.45},
    "crystal-lead": {"ops": [_op(1, 1.0, a=0.01, d=0.6, s=0.8, r=0.3), _op(3, 1.1, d=0.5, s=0.6, r=0.3, vel=0.6),
                             _op(2, 0.35, a=0.01, d=0.6, s=0.7, r=0.3), _op(1, 0.7, d=0.6, s=0.5, r=0.3)],
                     "algo": {0: [1], 2: [3]}, "out": [0, 2], "vibrato": 22, "vibrato_delay": 0.3, "level": 0.45},
    "fm-bass": {"ops": [_op(1, 1.0, d=0.7, s=0.6, r=0.08), _op(1, 2.6, d=0.12, s=0.3, r=0.08, vel=0.7, ks=0.0),
                        _op(1, 0.45, d=0.8, s=0.7, r=0.08)],
                "algo": {0: [1]}, "out": [0, 2], "fb": 0.9, "fb_op": 1, "level": 0.55},
    "slap-bass": {"ops": [_op(1, 1.0, d=0.45, s=0.3, r=0.06), _op(3, 3.0, d=0.05, s=0.05, r=0.05, vel=1.0, ks=0.0),
                          _op(1, 1.0, d=0.3, s=0.2, r=0.05)],
                  "algo": {0: [1], 1: [2]}, "out": [0], "level": 0.55},
    "fm-brass": {"ops": [_op(1, 1.0, a=0.04, d=0.8, s=0.8, r=0.2), _op(1, 2.4, a=0.08, d=0.6, s=0.55, r=0.2),
                         _op(1, 0.5, detune=6, a=0.05, d=0.8, s=0.8, r=0.2), _op(1, 1.4, a=0.1, d=0.6, s=0.5, r=0.2)],
                 "algo": {0: [1], 2: [3]}, "out": [0, 2], "fb": 0.6, "fb_op": 1, "vibrato": 14, "vibrato_delay": 0.35,
                 "level": 0.45},
    "fm-organ": {"ops": [_op(0.5, 0.5, a=0.005, s=1.0, r=0.08), _op(1, 1.0, a=0.005, s=1.0, r=0.08),
                         _op(2, 0.6, a=0.005, s=1.0, r=0.08), _op(3, 0.4, a=0.005, s=1.0, r=0.08)],
                 "algo": {}, "out": [0, 1, 2, 3], "fb": 0.25, "fb_op": 3, "chorus": 0.4, "level": 0.45},
    "harp-pluck": {"ops": [_op(1, 1.0, d=1.4, s=0.0, r=0.6), _op(1, 2.5, d=0.07, s=0.1, r=0.4, vel=0.8),
                           _op(2, 0.3, d=0.8, s=0.0, r=0.4), _op(3, 1.0, d=0.05, s=0.0, r=0.3)],
                   "algo": {0: [1], 2: [3]}, "out": [0, 2], "level": 0.55},
    "clav": {"ops": [_op(1, 1.0, d=0.35, s=0.0, r=0.05), _op(3, 2.8, d=0.15, s=0.2, r=0.05, vel=0.8)],
             "algo": {0: [1]}, "out": [0], "fb": 0.5, "fb_op": 1, "level": 0.5},
}


def _sine_fb(theta: np.ndarray, beta: float) -> np.ndarray:
    """y = sin(theta + beta*y), solved per sample all at once by relaxed fixed-point steps (feedback with no delay)."""
    y = np.sin(theta)
    for _ in range(10):
        y = 0.5 * y + 0.5 * np.sin(theta + beta * y)
    return y


def note(midi, vel, dur, p, rng, from_midi=None) -> np.ndarray:
    ops, algo, out = p["ops"], {int(k): v for k, v in p.get("algo", {}).items()}, p.get("out", [0])
    tail = max(ops[i].get("r", 0.2) for i in out)
    n = int((dur + tail) * C.SR) + 256
    f = np.repeat(C.hz(C.pitch(midi, n, p, RATE, int(np.ceil(dur * RATE)), from_midi)), OVER)
    no = len(f)
    f0 = float(C.hz(midi))
    fb_op = p.get("fb_op", len(ops) - 1)
    sig = {}
    for i in range(len(ops) - 1, -1, -1):
        o = ops[i]
        fi = np.full(no, float(o["fixed"])) if o.get("fixed") else f * o["ratio"] * 2 ** (o.get("detune", 0) / 1200)
        theta = 2 * np.pi * np.cumsum(fi) / (C.SR * OVER)              # every op starts at phase 0: the same attack
        theta = theta + sum(sig[j] for j in algo.get(i, []))
        env = np.repeat(C.adsr(n, dur, o["a"], o["d"], o["s"], o["r"]), OVER)
        y = _sine_fb(theta, p["fb"]) if p.get("fb") and i == fb_op else np.sin(theta)
        if i in out:
            sig[i] = y * env * o["level"]
        else:
            idx = o["level"] * (1 - o.get("vel", 0.5) * (1 - vel)) * min(1.0, (523.0 / f0) ** o.get("ks", 0.5))
            sig[i] = y * env * idx
    y = sum(sig[i] for i in out) / sum(ops[i]["level"] for i in out)
    y = signal.resample_poly(y, 1, OVER)[:n] * (0.4 + 0.6 * vel)
    y = C.chorus(y, p.get("chorus", 0.0))
    return C.finish(y, p)
