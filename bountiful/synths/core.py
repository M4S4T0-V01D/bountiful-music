"""Bountiful's synth core: the parts every instrument in synths/ is built from. Our own code, no samples, no plug-ins.

  phase(f)              running phase (0-1) of a frequency curve (Hz per sample)
  blep / pulse / saw    band-limited (PolyBLEP) edges, so high notes don't alias
  stepped(table, ph)    a stepped wave read from a table (NES triangle, Game Boy wave RAM), oversampled then decimated
  macro(spec, ...)      a frame-rate sequence (volume, arpeggio, duty, pitch) with loop and release points, as in a tracker
  pitch(midi, ...)      the frequency curve of a note: arpeggio and pitch macros, vibrato, glide from the last note
  biquad(x, kind, cut)  a resonant low/band/high-pass whose cutoff may move, redesigned every block with state carried
  lfsr(bits, tap)       one period of a linear-feedback shift register (chip noise), computed once and cached
  adsr / finish         a smooth envelope; the last fade, level and float32 out

A synth module has PRESETS = {name: {...knobs}} and note(midi, vel, dur, p, rng, from_midi=None) -> mono float32,
the renderer's pyvoice signature (see voice.py).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy import signal

SR = 44100
NTSC, PAL = 60.0988, 50.007              # frame rates: macros step once per video frame, as the drivers did


def hz(midi) -> float | np.ndarray:
    return 440.0 * 2 ** ((np.asarray(midi, float) - 69) / 12)


def phase(f: np.ndarray, phase0: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Phase (0-1) and phase step of the frequency curve f, starting at phase0."""
    dt = np.clip(f / SR, 1e-7, 0.49)
    return (phase0 + np.cumsum(dt) - dt[0]) % 1.0, dt


def blep(t: np.ndarray, dt: np.ndarray) -> np.ndarray:
    """PolyBLEP residual for a unit step at phase 0 (t in [0, 1))."""
    r = np.zeros_like(t)
    a = t < dt
    x = t[a] / dt[a]
    r[a] = x + x - x * x - 1
    b = t > 1 - dt
    x = (t[b] - 1) / dt[b]
    r[b] = x * x + x + x + 1
    return r


def pulse(ph: np.ndarray, dt: np.ndarray, pw: np.ndarray | float = 0.5) -> np.ndarray:
    pw = np.clip(np.broadcast_to(pw, ph.shape), 0.01, 0.99)
    return np.where(ph < pw, 1.0, -1.0) + blep(ph, dt) - blep((ph - pw) % 1.0, dt)


def saw(ph: np.ndarray, dt: np.ndarray) -> np.ndarray:
    return 2 * ph - 1 - blep(ph, dt)


def stepped(table, f: np.ndarray, phase0: float = 0.0, over: int = 4) -> np.ndarray:
    """A wave read step by step from table (values -1..1) at frequency f, rendered `over` times faster and decimated:
    the steps stay (that is the sound) but each edge gets a polyBLEP and their images above Nyquist are filtered out."""
    tab = np.asarray(table, float)
    L = len(tab)
    over = max(1, over, int(np.ceil(4 * np.max(f) * L / SR)))   # at most a step per 4 samples, so the bleps fit
    ph, dt = phase(np.repeat(f, over) / over, phase0)
    sp, ds = ph * L, np.minimum(dt * L, 0.5)       # phase and increment counted in table steps
    i = sp.astype(int) % L
    t = sp % 1.0
    y = tab[i]
    a = t < ds                                     # just past the edge into this step
    x = t[a] / ds[a]
    y[a] += (tab[i[a]] - tab[i[a] - 1]) / 2 * (x + x - x * x - 1)
    b = t > 1 - ds                                 # just before the edge into the next step
    x = (t[b] - 1) / ds[b]
    y[b] += (tab[(i[b] + 1) % L] - tab[i[b]]) / 2 * (x * x + x + x + 1)
    return y if over == 1 else signal.resample_poly(y, 1, over)[:len(f)]


def macro(spec, n_frames: int, gate_frames: int, default: float = 0.0) -> np.ndarray:
    """A tracker macro, one value per frame. spec is a number, a list, or {"seq": [...], "loop": i, "release": j}.
    While the note is held the sequence plays up to the release point (or its end), looping back to `loop` if set,
    else holding its last value; when the note is let go it jumps to `release` and plays on to the end and holds."""
    if spec is None:
        return np.full(n_frames, float(default))
    if isinstance(spec, (int, float)):
        return np.full(n_frames, float(spec))
    if isinstance(spec, (list, tuple)):
        spec = {"seq": spec}
    seq = [float(v) for v in spec["seq"]] or [float(default)]
    loop, rel = spec.get("loop"), spec.get("release")
    held_end = len(seq) if rel is None else max(1, min(int(rel), len(seq)))
    out = np.empty(n_frames)
    i, released = 0, False
    for k in range(n_frames):
        if not released and k >= gate_frames:
            released = True
            if rel is not None:
                i = min(int(rel), len(seq) - 1)
        out[k] = seq[i]
        i += 1
        if not released and i >= held_end:
            i = int(loop) if loop is not None and loop < held_end else held_end - 1
        elif released and i >= len(seq):
            i = len(seq) - 1
    return out


def tail_frames(spec) -> int:
    """How many frames a macro plays after the note is let go (its release part), 0 if it has none."""
    if isinstance(spec, dict) and spec.get("release") is not None:
        return max(0, len(spec["seq"]) - int(spec["release"]))
    return 0


def per_sample(frames: np.ndarray, n: int, rate: float) -> np.ndarray:
    """Frame values held for each sample (a step every 1/rate s), as a sound chip register is."""
    idx = np.minimum((np.arange(n) * (rate / SR)).astype(int), len(frames) - 1)
    return frames[idx]


def pitch(midi: float, n: int, p: dict, rate: float, gate_frames: int, from_midi=None) -> np.ndarray:
    """Note number per sample: arpeggio macro (semitones), pitch macro (cents), delayed vibrato, glide."""
    nf = int(n * rate / SR) + 2
    m = np.full(n, float(midi))
    if p.get("arp") is not None:
        m += per_sample(macro(p["arp"], nf, gate_frames), n, rate)
    if p.get("pitch") is not None:
        m += per_sample(macro(p["pitch"], nf, gate_frames), n, rate) / 100
    t = np.arange(n) / SR
    if p.get("vibrato"):
        ramp = np.clip((t - p.get("vibrato_delay", 0.2)) / max(p.get("vibrato_ramp", 0.15), 1e-3), 0, 1)
        m += p["vibrato"] / 100 * np.sin(2 * np.pi * p.get("vibrato_rate", 5.5) * t) * ramp
    if from_midi is not None and p.get("glide", 0) > 0:
        m += (from_midi - midi) * np.exp(-t / (p["glide"] / 3))
    if p.get("sweep"):                                   # semitones per second, a hardware sweep unit
        m += p["sweep"] * t
    return m


def biquad(x: np.ndarray, kind: str, cut, q: float = 0.707, block: int = 32) -> np.ndarray:
    """Resonant 2-pole filter (RBJ): kind = lowpass | highpass | bandpass. cut is a number or a curve per sample."""
    def coeffs(f):
        w = 2 * np.pi * float(np.clip(f, 20, SR * 0.45)) / SR
        al, cw = np.sin(w) / (2 * q), np.cos(w)
        if kind == "lowpass":
            b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
        elif kind == "highpass":
            b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        else:
            b = [al, 0.0, -al]
        a = [1 + al, -2 * cw, 1 - al]
        return np.divide(b, a[0]), np.divide(a, a[0])

    if np.ndim(cut) == 0:                                  # a fixed cutoff: one pass
        return signal.lfilter(*coeffs(cut), x)
    cut = np.broadcast_to(np.asarray(cut, float), x.shape)
    out = np.empty_like(x)
    zi = np.zeros(2)
    for i in range(0, len(x), block):
        b, a = coeffs(cut[min(i + block // 2, len(x) - 1)])
        out[i:i + block], zi = signal.lfilter(b, a, x[i:i + block], zi=zi)
    return out


def chorus(x: np.ndarray, mix: float = 0.5, rate: float = 0.7, depth: float = 0.0025, delay: float = 0.011,
           voices: int = 3) -> np.ndarray:
    """An ensemble chorus: `voices` copies read through delays swept by sines a third of a cycle apart (the string
    machine's BBD trick), mixed in. The whole note is known, so the reads are vectorised."""
    if mix <= 0:
        return x
    t = np.arange(len(x)) / SR
    wet = np.zeros_like(x)
    for v in range(voices):
        d = (delay + depth * np.sin(2 * np.pi * (rate * (1 + 0.13 * v) * t + v / voices))) * SR
        pos = np.arange(len(x)) - d
        i = np.floor(pos).astype(int)
        fr = pos - i
        ok = i >= 0
        a = np.where(ok, x[np.clip(i, 0, len(x) - 1)], 0.0)
        b = np.where(i + 1 >= 0, x[np.clip(i + 1, 0, len(x) - 1)], 0.0)
        wet += a * (1 - fr) + b * fr
    return x * (1 - mix * 0.5) + wet / voices * mix


def drive(x: np.ndarray, amount: float) -> np.ndarray:
    """Soft saturation, 0 = clean; the level stays about the same as it gets dirtier."""
    if amount <= 0:
        return x
    k = 1 + 8 * amount
    return np.tanh(x * k) / np.tanh(k)


def onepole(x: np.ndarray, f: float, high: bool = False) -> np.ndarray:
    a = np.exp(-2 * np.pi * f / SR)
    y = signal.lfilter([1 - a], [1, -a], x)
    return x - y if high else y


@lru_cache(maxsize=None)
def lfsr(bits: int, tap: int) -> np.ndarray:
    """One period of a Fibonacci LFSR as -1/1: bit 0 XOR bit `tap` shifted in at the top (NES: 15, 1 or 6; GB: 15/7, 1)."""
    reg, out = 1, []
    for _ in range(2 ** bits):
        out.append(1.0 - 2.0 * (reg & 1))
        fb = (reg ^ (reg >> tap)) & 1
        reg = (reg >> 1) | (fb << (bits - 1))
        if reg == 1:
            break
    return np.array(out)


def clocked(seq: np.ndarray, clock: np.ndarray | float, n: int) -> np.ndarray:
    """A noise sequence stepped at `clock` Hz (a number or a curve), one value held per step."""
    steps = np.cumsum(np.broadcast_to(np.asarray(clock, float), (n,)) / SR)
    return seq[steps.astype(np.int64) % len(seq)]


def adsr(n: int, dur: float, a: float, d: float, s: float, r: float) -> np.ndarray:
    t = np.arange(n) / SR
    att = np.clip(t / max(a, 1e-4), 0, 1)
    dec = s + (1 - s) * np.exp(-np.maximum(t - a, 0) / max(d, 1e-4))
    env = np.where(t < a, att, dec)
    held = float(env[min(int(dur * SR), n - 1)]) if n else 0.0
    return np.where(t < dur, env, held * np.clip(1 - (t - dur) / max(r, 1e-4), 0, 1))


def dac(x: np.ndarray, bits: int) -> np.ndarray:
    q = 2 ** (bits - 1)
    return np.round(x * q) / q


def finish(y: np.ndarray, p: dict, fade: int = 48) -> np.ndarray:
    """De-click the ends, apply the preset's level, return float32."""
    fade = min(fade, len(y))
    y = np.asarray(y, float)
    y[:min(8, len(y))] *= np.linspace(0, 1, min(8, len(y)))
    y[-fade:] *= np.linspace(1, 0, fade)
    return (y * p.get("level", 0.5)).astype(np.float32)
