"""Game Boy (DMG APU): two pulse channels, the 4-bit wave channel and a noise channel.

  channel     pulse | wave | noise
  duty        pulse duty 0-3 (12.5, 25, 50, 75 %), a number or a macro
  env         the hardware envelope [start 0-15, direction +1/-1, period 1-7 (a step every period/64 s)], or
  vol         a 0-15 volume macro instead (as a tracker driver rewrites the register each frame)
  wave        wave RAM: 32 hex digits (4-bit samples), e.g. "0123456789ABCDEFFEDCBA9876543210", or a name in WAVES
  shift       wave output level: 0 = 100 %, 1 = 50 %, 2 = 25 %
  width       noise: 15 (hiss) or 7 (buzzy, pitched); noise_pitch "note" or a fixed divisor shift 0-13
  arp / pitch / vibrato / glide / sweep        as in core.pitch (sweep = the channel-1 sweep unit, semitones/s)
  tuning      "hardware" (pitch snaps to the 11-bit frequency register) or "exact"
"""
from __future__ import annotations

import numpy as np

from synths import core as C

RATE = 59.7275                       # the DMG's frame rate
DUTY = [0.125, 0.25, 0.5, 0.75]
WAVES = {
    "triangle": "0123456789ABCDEFFEDCBA9876543210",
    "saw": "00112233445566778899AABBCCDDEEFF",
    "square": "FFFFFFFFFFFFFFFF0000000000000000",
    "thin": "FFFFFFFF000000000000000000000000",
    "sine": "89BCDEEFFFFEEDCB9875432110000112",
    "organ": "9CEFEC9878ACA8741243100234120023",
    "bass": "FFEECCAA887766554433221100000000",
    "bell": "F0C3E1A587695B4D3C2E1F0F1E2D3C4B",
}

PRESETS = {
    "lead": {"channel": "pulse", "duty": 2, "env": [13, -1, 7], "vibrato": 20, "vibrato_delay": 0.25, "level": 0.5},
    "lead-thin": {"channel": "pulse", "duty": 0, "env": [14, -1, 5], "vibrato": 15, "level": 0.5},
    "town": {"channel": "pulse", "duty": 1, "vol": {"seq": [12, 12, 11, 11, 10, 10, 9], "release": 7},
             "vibrato": 12, "vibrato_delay": 0.3, "level": 0.48},
    "blip": {"channel": "pulse", "duty": 1, "env": [15, -1, 1], "level": 0.5},
    "coin": {"channel": "pulse", "duty": 2, "arp": {"seq": [0, 0, 0, 0, 5]}, "env": [15, -1, 3], "level": 0.5},
    "jump": {"channel": "pulse", "duty": 2, "sweep": 30, "env": [14, -1, 2], "level": 0.5},
    "arp": {"channel": "pulse", "duty": 1, "arp": {"seq": [0, 4, 7, 12], "loop": 0}, "env": [11, -1, 7], "level": 0.42},
    "swell": {"channel": "pulse", "duty": 2, "env": [2, 1, 2], "vibrato": 15, "level": 0.45},
    "wave-bass": {"channel": "wave", "wave": "bass", "shift": 0, "level": 0.6},
    "wave-sine": {"channel": "wave", "wave": "sine", "shift": 0, "vibrato": 15, "vibrato_delay": 0.3, "level": 0.55},
    "wave-organ": {"channel": "wave", "wave": "organ", "shift": 0, "level": 0.5},
    "wave-saw": {"channel": "wave", "wave": "saw", "shift": 0, "level": 0.5},
    "wave-bell": {"channel": "wave", "wave": "bell", "shift": 1, "vol_decay": 0.6, "level": 0.6},
    "wave-soft": {"channel": "wave", "wave": "triangle", "shift": 1, "level": 0.6},
    "hat": {"channel": "noise", "width": 15, "noise_pitch": 1, "env": [9, -1, 1], "level": 0.4},
    "snare": {"channel": "noise", "width": 15, "noise_pitch": 4, "env": [15, -1, 2], "level": 0.5},
    "kick": {"channel": "noise", "width": 7, "noise_pitch": {"seq": [9, 10, 11, 12, 13]}, "env": [15, -1, 2], "level": 0.55},
    "buzz": {"channel": "noise", "width": 7, "noise_pitch": "note", "env": [12, -1, 3], "level": 0.4},
    "crash": {"channel": "noise", "width": 15, "noise_pitch": 2, "env": [12, -1, 6], "level": 0.4},
}


def _snap(m: np.ndarray, base: float) -> np.ndarray:
    """Frequencies the 11-bit register can make: f = base / (2048 - x)."""
    x = np.clip(np.round(2048 - base / C.hz(m)), 0, 2047)
    return base / (2048 - x)


def _hw_env(env, n: int, dur: float) -> np.ndarray:
    v0, direction, period = env
    t = np.arange(n) / C.SR
    if not period:
        return np.full(n, float(v0))
    return np.clip(v0 + direction * np.floor(t * 64 / period), 0, 15)


def _wave_table(spec) -> np.ndarray:
    s = WAVES.get(spec, spec) if isinstance(spec, str) else "".join(f"{int(v):X}" for v in spec)
    return np.array([int(c, 16) for c in s[:32].ljust(32, "0")]) / 7.5 - 1.0


def note(midi, vel, dur, p, rng, from_midi=None) -> np.ndarray:
    ch = p.get("channel", "pulse")
    gate = int(np.ceil(dur * RATE))
    tail = C.tail_frames(p.get("vol"))
    rel = 0.0 if tail else p.get("release", 0.012)
    n = int(((gate + tail) / RATE + rel) * C.SR) + 64
    nf = int(n * RATE / C.SR) + 2
    m = C.pitch(midi, n, p, RATE, gate, from_midi)
    hw = p.get("tuning", "hardware") == "hardware"

    if ch == "noise":
        spec = p.get("noise_pitch", "note")
        s = (np.full(nf, max(0, 13 - (round(midi) - 36) // 4), float) if spec == "note" else C.macro(spec, nf, gate))
        clock = 524288.0 / 2 ** (np.clip(s, 0, 13) + 1)
        seq = C.lfsr(7 if p.get("width", 15) == 7 else 15, 1)
        y = (C.clocked(seq, C.per_sample(clock, n, RATE), n) + 1) / 2
    elif ch == "wave":
        f = _snap(m, 65536.0) if hw else C.hz(m)
        y = (C.stepped(_wave_table(p.get("wave", "triangle")), f) + 1) / 2
        y = y / 2 ** int(p.get("shift", 0))
    else:
        f = _snap(m, 131072.0) if hw else C.hz(m)
        pw = C.per_sample(np.take(DUTY, np.clip(C.macro(p.get("duty", 2), nf, gate), 0, 3).astype(int)), n, RATE)
        ph, dt = C.phase(f)
        y = (C.pulse(ph, dt, pw) + 1) / 2

    if ch == "wave":                                             # no envelope on the wave channel: on, off, a level
        env = np.ones(n)
        if p.get("vol_decay"):
            env = np.clip(np.floor(4 * np.exp(-np.arange(n) / C.SR / p["vol_decay"]) + 0.999) / 4, 0, 1)
    elif p.get("vol") is not None:
        vol = np.clip(np.round(C.macro(p["vol"], nf, gate, 15)), 0, 15)
        env = C.per_sample(vol, n, RATE) / 15
    else:
        env = _hw_env(p.get("env", [15, 0, 0]), n, dur) / 15
    if p.get("velocity", True) and ch != "wave":
        env = np.round(env * 15 * (0.55 + 0.45 * vel)) / 15
    t = np.arange(n) / C.SR
    end = (gate + tail) / RATE if tail else dur
    env = env * (np.clip(1 - (t - end) / rel, 0, 1) if rel else (t < end))
    centre = 0.5 / 2 ** int(p.get("shift", 0)) if ch == "wave" else 0.5
    y = (y - centre) * env
    y = C.onepole(C.onepole(y, 30.0, high=True), 12000.0)       # the DMG's coupling capacitor and its speaker-amp roll-off
    return C.finish(y * 1.6, p)
