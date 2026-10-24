"""Virtual analog: the modern subtractive synth. Unison oscillators, a sub, noise, a resonant filter with its own
envelope, drive and an ensemble chorus. Supersaw leads, plucks, pads, brass, reese and acid basses.

  osc         saw | square | pulse | tri | sine (osc 1); unison 1-9 voices spread over detune cents (the supersaw)
  osc2        a second oscillator or None; osc2_semi, osc2_detune cents, osc2_mix 0-1
  sub         a square an octave down, level 0-1; noise, white noise level 0-1
  pw          pulse width; pwm depth 0-1, pwm_rate Hz
  filter      lp | lp24 | hp | bp | None; cutoff Hz, res 0-1, key_track 0-1, env_amt octaves the filter envelope opens
              by (fa / fd / fs / fr: its attack, decay time constant, sustain 0-1, release), vel_filter 0-1
  a / d / s / r                amp envelope (attack s, decay time constant s, sustain 0-1, release s)
  drive 0-1, chorus mix 0-1 (chorus_rate Hz), vibrato / glide / arp / pitch as in core.pitch
"""
from __future__ import annotations

import numpy as np
from scipy import signal

from synths import core as C

RATE = 100.0                         # macro frames per second
OVER = 2

PRESETS = {
    "supersaw-lead": {"osc": "saw", "unison": 7, "detune": 28, "filter": "lp", "cutoff": 7000, "res": 0.1,
                      "a": 0.005, "d": 0.4, "s": 0.85, "r": 0.25, "chorus": 0.3, "vibrato": 18, "vibrato_delay": 0.3,
                      "level": 0.42},
    "trance-pluck": {"osc": "saw", "unison": 5, "detune": 18, "filter": "lp", "cutoff": 350, "res": 0.25,
                     "env_amt": 4.5, "fa": 0.001, "fd": 0.16, "fs": 0.0, "fr": 0.2, "a": 0.001, "d": 0.35, "s": 0.0,
                     "r": 0.2, "chorus": 0.25, "level": 0.5},
    "synthwave-lead": {"osc": "saw", "osc2": "square", "osc2_detune": 9, "osc2_mix": 0.6, "filter": "lp",
                       "cutoff": 2600, "res": 0.3, "env_amt": 1.0, "fd": 0.3, "fs": 0.3, "a": 0.01, "d": 0.5, "s": 0.8,
                       "r": 0.3, "glide": 0.04, "vibrato": 20, "vibrato_delay": 0.35, "chorus": 0.35, "level": 0.42},
    "square-lead": {"osc": "square", "unison": 2, "detune": 8, "filter": "lp", "cutoff": 5000, "a": 0.003, "d": 0.3,
                    "s": 0.75, "r": 0.15, "vibrato": 25, "vibrato_delay": 0.25, "level": 0.38},
    "hero-lead": {"osc": "pulse", "pw": 0.3, "pwm": 0.3, "pwm_rate": 0.8, "osc2": "saw", "osc2_semi": 12,
                  "osc2_mix": 0.35, "filter": "lp", "cutoff": 3500, "res": 0.2, "a": 0.004, "d": 0.4, "s": 0.8, "r": 0.25,
                  "vibrato": 28, "vibrato_delay": 0.25, "vibrato_rate": 6.0, "drive": 0.2, "level": 0.4},
    "warm-pad": {"osc": "saw", "unison": 4, "detune": 14, "filter": "lp", "cutoff": 1100, "res": 0.15, "key_track": 0.5,
                 "a": 0.9, "d": 1.0, "s": 0.9, "r": 1.6, "chorus": 0.6, "level": 0.4},
    "dream-pad": {"osc": "pulse", "pw": 0.5, "pwm": 0.6, "pwm_rate": 0.3, "osc2": "saw", "osc2_detune": 7,
                  "osc2_mix": 0.5, "filter": "lp", "cutoff": 900, "res": 0.2, "env_amt": 1.5, "fa": 1.5, "fd": 2.0,
                  "fs": 0.5, "fr": 1.5, "a": 1.2, "d": 1.5, "s": 0.9, "r": 2.0, "chorus": 0.7, "level": 0.42},
    "string-machine": {"osc": "saw", "osc2": "pulse", "pw": 0.35, "pwm": 0.3, "pwm_rate": 0.5, "osc2_mix": 0.5,
                       "filter": "lp", "cutoff": 3200, "a": 0.35, "d": 1.0, "s": 1.0, "r": 0.8, "chorus": 0.8,
                       "chorus_rate": 0.6, "level": 0.4},
    "synth-brass": {"osc": "saw", "osc2": "saw", "osc2_detune": 8, "osc2_mix": 0.8, "filter": "lp", "cutoff": 450,
                    "res": 0.15, "env_amt": 3.0, "fa": 0.07, "fd": 0.45, "fs": 0.45, "fr": 0.3, "a": 0.03, "d": 0.6,
                    "s": 0.85, "r": 0.25, "vibrato": 12, "vibrato_delay": 0.4, "chorus": 0.3, "level": 0.42},
    "poly-stab": {"osc": "saw", "unison": 3, "detune": 12, "filter": "lp", "cutoff": 600, "res": 0.3, "env_amt": 3.2,
                  "fd": 0.12, "fs": 0.1, "a": 0.001, "d": 0.25, "s": 0.0, "r": 0.12, "chorus": 0.4, "level": 0.5},
    "lofi-keys": {"osc": "tri", "osc2": "sine", "osc2_semi": 12, "osc2_mix": 0.25, "filter": "lp", "cutoff": 1800,
                  "a": 0.004, "d": 0.9, "s": 0.25, "r": 0.35, "vibrato": 8, "vibrato_rate": 0.9, "vibrato_delay": 0,
                  "vibrato_ramp": 0.001, "drive": 0.15, "level": 0.55},
    "reese-bass": {"osc": "saw", "osc2": "saw", "osc2_detune": 22, "osc2_mix": 1.0, "sub": 0.4, "filter": "lp24",
                   "cutoff": 750, "res": 0.2, "a": 0.004, "d": 0.5, "s": 0.9, "r": 0.12, "drive": 0.35, "glide": 0.03,
                   "level": 0.45},
    "sub-bass": {"osc": "sine", "osc2": "tri", "osc2_mix": 0.2, "filter": "lp", "cutoff": 400, "a": 0.003, "d": 0.3,
                 "s": 0.9, "r": 0.08, "drive": 0.1, "level": 0.6},
    "pluck-bass": {"osc": "saw", "osc2": "square", "osc2_semi": -12, "osc2_mix": 0.5, "filter": "lp24", "cutoff": 220,
                   "res": 0.3, "env_amt": 3.0, "fd": 0.1, "fs": 0.05, "a": 0.001, "d": 0.3, "s": 0.4, "r": 0.08,
                   "level": 0.55},
    "acid-bass": {"osc": "saw", "filter": "lp24", "cutoff": 260, "res": 0.75, "env_amt": 3.3, "fd": 0.18, "fs": 0.0,
                  "a": 0.002, "d": 0.4, "s": 0.7, "r": 0.06, "drive": 0.45, "glide": 0.07, "vel_filter": 0.6,
                  "level": 0.42},
    "riser": {"osc": "saw", "unison": 5, "detune": 30, "noise": 0.6, "filter": "lp", "cutoff": 200, "res": 0.4,
              "env_amt": 5.5, "fa": 3.0, "fs": 1.0, "a": 1.5, "d": 1.0, "s": 1.0, "r": 0.4, "sweep": 2.0,
              "chorus": 0.4, "level": 0.35},
}


def _osc(kind: str, f: np.ndarray, ph0: float, pw) -> np.ndarray:
    ph, dt = C.phase(f, ph0)
    if kind == "saw":
        return C.saw(ph, dt)
    if kind == "square":
        return C.pulse(ph, dt, 0.5)
    if kind == "pulse":
        return C.pulse(ph, dt, pw)
    if kind == "tri":
        return 4 * np.abs(ph - 0.5) - 1
    return np.sin(2 * np.pi * ph)


def _bank(kind, f, voices, detune, rng, pw) -> np.ndarray:
    """`voices` copies of an oscillator spread over +-detune cents, free-running (random start phases)."""
    if voices <= 1:
        return _osc(kind, f, rng.random(), pw)
    out = np.zeros_like(f)
    for k, s in enumerate(np.linspace(-1, 1, voices)):
        gain = 1.0 if abs(s) < 1e-9 else 0.75
        out += gain * _osc(kind, f * 2 ** (s * detune / 1200), rng.random(), pw)
    return out / np.sqrt(voices)


def note(midi, vel, dur, p, rng, from_midi=None) -> np.ndarray:
    a, d, s, r = p.get("a", 0.005), p.get("d", 0.3), p.get("s", 0.8), p.get("r", 0.2)
    n = int((dur + r) * C.SR) + 256
    m = C.pitch(midi, n, p, RATE, int(np.ceil(dur * RATE)), from_midi)
    fo = np.repeat(C.hz(m), OVER) / OVER                           # run OVER times faster, then decimate
    no = len(fo)
    t = np.arange(no) / (C.SR * OVER)
    pw = p.get("pw", 0.5)
    if p.get("pwm"):
        pw = np.clip(pw + p["pwm"] * 0.45 * np.sin(2 * np.pi * p.get("pwm_rate", 0.5) * t), 0.05, 0.95)

    y = _bank(p.get("osc", "saw"), fo, int(p.get("unison", 1)), p.get("detune", 15), rng, pw)
    mix = 1.0
    if p.get("osc2"):
        f2 = fo * 2 ** ((p.get("osc2_semi", 0) * 100 + p.get("osc2_detune", 0)) / 1200)
        y = y + p.get("osc2_mix", 0.5) * _bank(p["osc2"], f2, int(p.get("unison", 1)), p.get("detune", 15), rng, pw)
        mix += p.get("osc2_mix", 0.5)
    if p.get("sub"):
        y = y + p["sub"] * _osc("square", fo / 2, 0.0, 0.5)
        mix += p["sub"]
    if p.get("noise"):
        y = y + p["noise"] * rng.uniform(-1, 1, no)
        mix += p["noise"]
    y = signal.resample_poly(y / mix, 1, OVER)[:n]

    if p.get("filter"):
        cut = p.get("cutoff", 2000) * (C.hz(midi) / 261.6) ** p.get("key_track", 0.0)
        if p.get("env_amt"):
            fenv = C.adsr(n, dur, p.get("fa", 0.001), p.get("fd", 0.3), p.get("fs", 0.0), p.get("fr", r))
            vf = 1 - p.get("vel_filter", 0.4) * (1 - vel)
            cut = cut * 2 ** (p["env_amt"] * vf * fenv)
        q = 0.707 + 11 * p.get("res", 0.0) ** 1.5
        kind = p["filter"]
        if kind == "lp24":
            y = C.biquad(C.biquad(y, "lowpass", cut, 0.707), "lowpass", cut, q)
        else:
            y = C.biquad(y, {"lp": "lowpass", "hp": "highpass", "bp": "bandpass"}[kind], cut, q)
    y = C.drive(y, p.get("drive", 0.0))
    y = y * C.adsr(n, dur, a, d, s, r) * (0.4 + 0.6 * vel)
    y = C.chorus(y, p.get("chorus", 0.0), p.get("chorus_rate", 0.7))
    return C.finish(y, p)
