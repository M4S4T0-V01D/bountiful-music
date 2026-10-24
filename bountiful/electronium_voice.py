"""The Electronium's tone generators: one analog channel voice, as on Scott's machine (an oscillator, a filter and a
noise generator per channel, a few fixed envelopes, and per-channel accent, tremolo and reverb controls).

The renderer plays it as kind = "pyvoice" (intelligent-jungle studio/render_midi.py) with preset = { module = <this file>,
fn = "note", ...the knobs below }. Reverb is the channel's plate send, set in the track table, not here.

  wave        square | pulse | saw | triangle | sine      pw        pulse width (0.05-0.5)
  pwm         pulse-width wobble (0-0.4) at pwm_rate Hz   sub       a square an octave down (0-1)
  osc2        a second oscillator (0-1), detuned by detune cents      noise     white noise into the filter (0-1)
  cutoff      Hz, key_track (0-1), res (Q, 0.5-8), env_amount Hz on top of cutoff, falling by filter_decay s
  env         pluck | perc | organ | swell | gate (fixed envelopes), or attack/decay/sustain/release to set one
  accent      0-1: notes with velocity over accent_at hit harder and open the filter (the channel's accent switch)
  tremolo     depth 0-1 at tremolo_rate Hz                vibrato   cents, after vibrato_delay s, at 5.5 Hz
  drift       cents of slow pitch drift (a warm oscillator)            glide     s of portamento into a tied note
  bits        0 = off, else quantise to that many bits; hold: sample-and-hold factor (chip grit)
  level       output gain
"""
from __future__ import annotations

import numpy as np
from scipy import signal

SR = 44100
ENVS = {"pluck": (0.003, 0.18, 0.25, 0.12), "perc": (0.001, 0.09, 0.0, 0.06), "organ": (0.004, 0.05, 0.92, 0.05),
        "swell": (0.25, 0.4, 0.8, 0.45), "gate": (0.002, 0.02, 1.0, 0.02)}


def _blep(t, dt):
    """PolyBLEP residual for a unit step at phase 0 (t in [0, 1))."""
    r = np.zeros_like(t)
    a = t < dt
    x = t[a] / dt[a]
    r[a] = x + x - x * x - 1
    b = t > 1 - dt
    x = (t[b] - 1) / dt[b]
    r[b] = x * x + x + x + 1
    return r


def osc(wave: str, f: np.ndarray, pw: np.ndarray | float = 0.5, phase0: float = 0.0) -> np.ndarray:
    """A band-limited oscillator following the frequency curve f (Hz per sample)."""
    dt = np.clip(f / SR, 1e-6, 0.45)
    ph = (phase0 + np.cumsum(dt) - dt[0]) % 1.0
    if wave == "sine":
        return np.sin(2 * np.pi * ph)
    if wave == "triangle":
        return 1 - 4 * np.abs(ph - 0.5)          # mild aliasing only, the triangle's harmonics fall fast
    if wave == "saw":
        return 2 * ph - 1 - _blep(ph, dt)
    pw = np.clip(np.broadcast_to(pw, ph.shape), 0.05, 0.95)
    sq = np.where(ph < pw, 1.0, -1.0)
    return sq + _blep(ph, dt) - _blep((ph - pw) % 1.0, dt)


def lowpass(x: np.ndarray, cut: np.ndarray, q: float, block: int = 64) -> np.ndarray:
    """A resonant 2-pole low-pass (RBJ biquad) redesigned every block, state carried across."""
    out = np.empty_like(x)
    zi = np.zeros(2)
    for i in range(0, len(x), block):
        f = float(np.clip(cut[min(i + block // 2, len(cut) - 1)], 30, SR * 0.45))
        w = 2 * np.pi * f / SR
        al = np.sin(w) / (2 * q)
        cw = np.cos(w)
        b = np.array([(1 - cw) / 2, 1 - cw, (1 - cw) / 2])
        a = np.array([1 + al, -2 * cw, 1 - al])
        out[i:i + block], zi = signal.lfilter(b / a[0], a / a[0], x[i:i + block], zi=zi)
    return out


def envelope(n: int, dur: float, a: float, d: float, s: float, r: float) -> np.ndarray:
    t = np.arange(n) / SR
    att = np.clip(t / max(a, 1e-4), 0, 1)
    dec = s + (1 - s) * np.exp(-np.maximum(t - a, 0) / max(d, 1e-4))
    env = np.where(t < a, att, dec)
    held = float(env[min(int(dur * SR), n - 1)]) if n else 0.0
    return np.where(t < dur, env, held * np.clip(1 - (t - dur) / max(r, 1e-4), 0, 1))


def note(midi, vel, dur, p, rng, from_midi=None) -> np.ndarray:
    g = lambda k, d: p.get(k, d)
    a, d, s, r = ENVS.get(g("env", "pluck"), ENVS["pluck"])
    a, d, s, r = g("attack", a), g("decay", d), g("sustain", s), g("release", r)
    n = int((dur + r) * SR) + 64
    t = np.arange(n) / SR
    f0 = 440.0 * 2 ** ((midi - 69) / 12)
    # pitch: glide from the last note, slow analog drift, delayed vibrato
    cents = np.zeros(n)
    if from_midi is not None and g("glide", 0) > 0:
        cents += (from_midi - midi) * 100 * np.exp(-t / (g("glide", 0) / 3))
    if g("drift", 0):
        k = max(2, int(n / (SR * 0.25)) + 2)
        cents += np.interp(t, np.linspace(0, t[-1] + 1e-9, k), rng.normal(0, 1, k)) * g("drift", 0)
    if g("vibrato", 0):
        cents += g("vibrato", 0) * np.sin(2 * np.pi * 5.5 * t) * np.clip((t - g("vibrato_delay", 0.25)) / 0.3, 0, 1)
    f = f0 * 2 ** (cents / 1200)
    wave = g("wave", "square")
    pw = g("pw", 0.5 if wave == "square" else 0.3)
    if g("pwm", 0):
        pw = pw + g("pwm", 0) * np.sin(2 * np.pi * g("pwm_rate", 0.7) * t + rng.random() * 6.28)
    y = osc("pulse" if wave in ("square", "pulse") else wave, f, pw, rng.random())
    if g("osc2", 0):
        y = y + g("osc2", 0) * osc("pulse" if wave in ("square", "pulse") else wave, f * 2 ** (g("detune", 7) / 1200), pw, rng.random())
    if g("sub", 0):
        y = y + g("sub", 0) * osc("pulse", f / 2, 0.5, rng.random())
    if g("noise", 0):
        y = y + g("noise", 0) * rng.uniform(-1, 1, n)
    # accent: the channel's accent switch lifts hot notes and opens their filter
    acc = g("accent", 0.4) * max(0.0, (vel - g("accent_at", 0.8)) / max(1e-3, 1 - g("accent_at", 0.8)))
    cut = g("cutoff", 2400) * (f0 / 440) ** g("key_track", 0.5)
    cut = cut + (g("env_amount", 2500) * (0.4 + 0.6 * vel) * (1 + 1.5 * acc)) * np.exp(-t / g("filter_decay", 0.15))
    y = lowpass(y, cut, g("res", 1.2))
    amp = envelope(n, dur, a, d * (1 + acc), s, r)
    if g("tremolo", 0):
        amp = amp * (1 - g("tremolo", 0) * 0.5 * (1 + np.sin(2 * np.pi * g("tremolo_rate", 5.0) * t)))
    y = y * amp * (0.5 + 0.5 * vel) * (1 + 0.5 * acc)
    y = np.tanh(y * g("drive", 1.1)) / np.tanh(g("drive", 1.1))
    if g("hold", 1) > 1:                                        # sample-and-hold: the rate drops, the grit comes in
        h = int(g("hold", 1))
        y = np.repeat(y[::h], h)[:n]
    if g("bits", 0):
        q = 2 ** (int(g("bits", 0)) - 1)
        y = np.round(y * q) / q
    fade = min(64, n)
    y[-fade:] *= np.linspace(1, 0, fade)
    return (y * g("level", 0.5)).astype(np.float32)
