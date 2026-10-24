"""NES (Ricoh 2A03): two pulse channels, a triangle and a noise channel, played the way a tracker driver plays them.

  channel     pulse | triangle | noise
  duty        pulse duty 0-3 (12.5, 25, 50, 75 %), a number or a macro (duty cycling is the NES's signature)
  vol         4-bit volume 0-15, a number or a macro {"seq": [...], "loop": i, "release": j}; the triangle has none
  arp         arpeggio macro in semitones (fast chords: [0, 4, 7] with loop 0); pitch macro in cents
  vibrato / vibrato_rate / vibrato_delay, glide (s), sweep (semitones/s, the pulse sweep unit)
  tuning      "hardware": pitch snaps to the 11-bit period register (high notes go flat or sharp as on the console);
              "exact": in tune
  mode        noise: "long" (15-bit LFSR, hiss) or "short" (93-step loop, metallic, pitched)
  noise_pitch noise: "note" (the note picks the period, as trackers map it) or a fixed period index 0-15
  region      ntsc | pal (CPU clock and frame rate)
  console     true: the console's output stage (high-pass 90 Hz, low-pass 14 kHz); hp440 adds its thin 440 Hz high-pass
  release     s of volume fade after note-off when vol has no release part (0.015 = the usual cut)
"""
from __future__ import annotations

import numpy as np

from synths import core as C

CPU = {"ntsc": 1789773.0, "pal": 1662607.0}
RATE = {"ntsc": C.NTSC, "pal": C.PAL}
DUTY = [0.125, 0.25, 0.5, 0.75]
TRI = np.concatenate([np.arange(15, -1, -1), np.arange(16)]) / 7.5 - 1.0
NOISE_PERIOD = {"ntsc": [4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068],
                "pal": [4, 8, 14, 30, 60, 88, 118, 148, 188, 236, 354, 472, 708, 944, 1890, 3778]}

PRESETS = {
    "lead-12": {"channel": "pulse", "duty": 0, "vol": {"seq": [15, 14, 13, 12, 12, 11], "release": 6},
                "vibrato": 18, "vibrato_delay": 0.22, "level": 0.5},
    "lead-25": {"channel": "pulse", "duty": 1, "vol": {"seq": [13, 13, 12, 12, 11, 11, 10, 9, 8, 6, 4, 2, 0], "release": 8},
                "vibrato": 22, "vibrato_delay": 0.25, "level": 0.5},
    "hero-square": {"channel": "pulse", "duty": {"seq": [2, 2, 1], "loop": 2}, "vol": {"seq": [15, 14, 13, 12], "release": 4},
                    "vibrato": 25, "vibrato_delay": 0.3, "level": 0.48},
    "echo-lead": {"channel": "pulse", "duty": 1, "vol": {"seq": [6, 6, 5, 5, 4], "release": 5}, "vibrato": 18, "level": 0.45},
    "pluck": {"channel": "pulse", "duty": {"seq": [0, 1], "loop": 1},
              "vol": {"seq": [15, 12, 10, 8, 7, 6, 5, 4, 3, 3, 2, 2, 1, 1, 0]}, "level": 0.5},
    "major-arp": {"channel": "pulse", "duty": 2, "arp": {"seq": [0, 4, 7], "loop": 0},
                  "vol": {"seq": [12, 11, 10, 10, 9], "release": 5}, "level": 0.42},
    "minor-arp": {"channel": "pulse", "duty": 2, "arp": {"seq": [0, 3, 7], "loop": 0},
                  "vol": {"seq": [12, 11, 10, 10, 9], "release": 5}, "level": 0.42},
    "chorus-pad": {"channel": "pulse", "duty": {"seq": [1, 1, 2, 2], "loop": 0}, "vol": {"seq": [4, 7, 9, 10], "release": 4},
                   "vibrato": 12, "vibrato_delay": 0.0, "vibrato_rate": 4.0, "level": 0.42},
    "power-up": {"channel": "pulse", "duty": 1, "arp": {"seq": [0, 4, 7, 12, 16, 19, 24]},
                 "vol": {"seq": [15, 15, 14, 13, 12, 10, 8, 6, 4, 2, 0]}, "level": 0.5},
    "tri-bass": {"channel": "triangle", "release": 0.01, "level": 0.9},
    "tri-slap": {"channel": "triangle", "pitch": {"seq": [1200, 600, 200, 0]}, "release": 0.01, "level": 0.9},
    "tri-kick": {"channel": "triangle", "pitch": {"seq": [2400, 1200, 400, -400, -1200, -2400]},
                 "fixed_frames": 6, "level": 0.9},
    "pulse-bass": {"channel": "pulse", "duty": 2, "vol": {"seq": [15, 13, 12, 11], "release": 4}, "level": 0.45},
    "hat": {"channel": "noise", "mode": "long", "noise_pitch": 2, "vol": {"seq": [10, 6, 3, 1, 0]}, "level": 0.4},
    "open-hat": {"channel": "noise", "mode": "long", "noise_pitch": 2,
                 "vol": {"seq": [10, 9, 8, 7, 6, 5, 4, 3, 2, 2, 1, 1, 0]}, "level": 0.4},
    "snare": {"channel": "noise", "mode": "long", "noise_pitch": {"seq": [5, 7, 8, 8]},
              "vol": {"seq": [15, 13, 11, 9, 7, 6, 5, 4, 3, 2, 1, 0]}, "level": 0.5},
    "metal": {"channel": "noise", "mode": "short", "noise_pitch": "note", "vol": {"seq": [12, 10, 8, 6, 4, 2, 0]},
              "level": 0.4},
    "explosion": {"channel": "noise", "mode": "long", "noise_pitch": {"seq": [9, 10, 11, 12, 13, 14, 15]},
                  "vol": {"seq": [15, 15, 14, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0]}, "level": 0.55},
}


def _mixer(v: np.ndarray, channel: str) -> np.ndarray:
    """The 2A03's non-linear DAC, normalised so full volume is 1 (pulse and noise are compressed a little at the top)."""
    if channel == "triangle":
        return v
    k = 8128.0 if channel == "pulse" else 12241.0
    curve = lambda x: 95.88 / (k / np.maximum(x, 1e-6) + 100) * (x > 0)
    return curve(v) / curve(np.array(15.0))


def _snap(m: np.ndarray, cpu: float, div: int) -> np.ndarray:
    """Note numbers to the frequencies the 11-bit period register can actually make (f = cpu / (div * (t + 1)))."""
    t = np.clip(np.round(cpu / (div * C.hz(m)) - 1), 8 if div == 16 else 2, 2047)
    return cpu / (div * (t + 1))


def note(midi, vel, dur, p, rng, from_midi=None) -> np.ndarray:
    ch = p.get("channel", "pulse")
    region = p.get("region", "ntsc")
    rate, cpu = RATE[region], CPU[region]
    gate = int(np.ceil(dur * rate))
    if p.get("fixed_frames"):
        gate = int(p["fixed_frames"])
    tail = C.tail_frames(p.get("vol"))
    rel = 0.0 if tail else p.get("release", 0.015)
    n = int(((gate + tail) / rate + rel) * C.SR) + 64
    nf = int(n * rate / C.SR) + 2

    m = C.pitch(midi, n, p, rate, gate, from_midi)
    if ch == "noise":
        spec = p.get("noise_pitch", "note")
        idx = (np.full(nf, 15 - (round(midi) % 16), float) if spec == "note" else C.macro(spec, nf, gate))
        clock = cpu / np.take(NOISE_PERIOD[region], np.clip(idx, 0, 15).astype(int))
        seq = C.lfsr(15, 6 if p.get("mode", "long") == "short" else 1)
        y = C.clocked(-seq, C.per_sample(clock, n, rate), n)    # the channel outputs when bit 0 is clear
        y = (y + 1) / 2                                          # unipolar, as the DAC sees it
    elif ch == "triangle":
        f = _snap(m, cpu, 32) if p.get("tuning", "hardware") == "hardware" else C.hz(m)
        y = C.stepped(TRI, f, 0.0)
    else:
        f = _snap(m, cpu, 16) if p.get("tuning", "hardware") == "hardware" else C.hz(m)
        pw = C.per_sample(np.take(DUTY, np.clip(C.macro(p.get("duty", 2), nf, gate), 0, 3).astype(int)), n, rate)
        ph, dt = C.phase(f, rng.random() if p.get("free_phase") else 0.0)
        y = (C.pulse(ph, dt, pw) + 1) / 2

    if ch == "triangle":
        env = C.per_sample((np.arange(nf) < gate).astype(float) * 0.8, n, rate)   # no volume: the linear counter gates it
        y = y * 0.5                                                                # on the pulse's scale (±0.5)
    else:
        vol = np.clip(np.round(C.macro(p.get("vol", 15), nf, gate, 15)), 0, 15)
        if p.get("velocity", True):
            vol = np.round(vol * (0.55 + 0.45 * vel))
        if not tail and gate > 0:
            vol[gate:] = vol[min(gate, nf) - 1]                  # held through the short release fade below
        env = C.per_sample(_mixer(vol, ch), n, rate)
        y = y - 0.5                                              # centre the unipolar wave
    t = np.arange(n) / C.SR
    end = (gate + tail) / rate
    env = env * (np.clip(1 - (t - end) / rel, 0, 1) if rel else (t < end))
    y = y * env
    if p.get("console", True):                                   # the console's output stage
        y = C.onepole(y, 90.0, high=True)
        if p.get("hp440"):
            y = C.onepole(y, 440.0, high=True)
        y = C.onepole(y, 14000.0)
    return C.finish(y * 1.6, p)
