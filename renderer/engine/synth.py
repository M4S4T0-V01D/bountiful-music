"""Instruments: every voice is synthesised from scratch (no third-party samples), so the whole track is
original and reproducible. Each `*_note` function renders one note as a mono float32 array; the
parameters come from a preset dict (see presets/*.json).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import fx
from .theory import hz

TAU = 2 * np.pi


def load_preset(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def _t(n: int) -> np.ndarray:
    return np.arange(n, dtype=np.float64) / fx.SR


def _release(t: np.ndarray, off: float, rel: float) -> np.ndarray:
    return np.where(t < off, 1.0, np.exp(-(t - off) / max(rel, 1e-4) * 5))


def _attack(t: np.ndarray, a: float) -> np.ndarray:
    return np.minimum(1.0, t / max(a, 1e-5))


# ---------------------------------------------------------------- Rhodes (2-op FM + tine)

def rhodes_note(midi: float, vel: float, dur: float, p: dict, rng: np.random.Generator) -> np.ndarray:
    f = hz(midi) * 2 ** (rng.normal(0, p.get("detune_cents", 2.0)) / 1200)
    n = int((dur + p["release"]) * fx.SR)
    t = _t(n)
    tau = p["decay"] * (220 / f) ** 0.35
    amp = np.exp(-t / tau) * _attack(t, 0.0015) * _release(t, dur, p["release"])
    v = vel ** 1.4
    index = p["index"] * (0.25 + 0.75 * v) * np.exp(-t / p["index_decay"]) + p["index_floor"] * v
    mod = np.sin(TAU * f * p["ratio"] * t)
    y = np.sin(TAU * f * t + index * mod)
    tr = min(p["tine_ratio"], 9000 / f)
    y += p["tine"] * v * np.sin(TAU * f * tr * t) * np.exp(-t / p["tine_decay"])
    y *= amp
    y = y + p.get("pickup", 0.18) * (0.5 + v) * y * y     # the pickup's asymmetry: warm even harmonics
    bark = 1 + p["bark"] * v * v
    y = np.tanh(y * bark) / np.tanh(bark)
    return (y * (0.35 + 0.65 * vel)).astype(np.float32)


# ---------------------------------------------------------------- bass: sub sine + plucked body

def bass_note(midi: float, vel: float, dur: float, p: dict, rng: np.random.Generator,
              from_midi: float | None = None, bright: float = 1.0) -> np.ndarray:
    n = int((dur + p["release"]) * fx.SR)
    t = _t(n)
    f1 = hz(midi)
    if from_midi is not None:
        f0 = hz(from_midi)
        g = p["glide"]
        f = f1 + (f0 - f1) * np.exp(-t / (g / 3))
    else:
        f = np.full(n, f1)
    phase = np.cumsum(TAU * f / fx.SR)
    env_sub = _attack(t, p["sub_attack"]) * np.exp(-t / p["sub_decay"]) * _release(t, dur, p["release"])
    sub = (np.sin(phase) + p["sub_h2"] * np.sin(2 * phase)) * env_sub
    body = np.zeros(n)
    kmax = int(min(28, 5000 / f1))
    bd = p["body_decay"] / max(bright, 0.2)
    for k in range(2, kmax + 1):
        body += np.sin(k * phase + rng.random() * 0.3) / k ** p["tilt"] * np.exp(-t * bd * k ** 0.85)
    body += 0.5 * np.sin(phase) * np.exp(-t / 0.5)
    body *= _attack(t, 0.003) * _release(t, dur, p["release"] * 0.7)
    # finger / pluck noise
    nn = min(n, int(0.04 * fx.SR))
    pluck = np.zeros(n)
    noise = rng.standard_normal(nn)
    pluck[:nn] = fx.bp(noise.astype(np.float32), 600, 2400) * np.exp(-np.arange(nn) / (0.008 * fx.SR))
    y = p["sub"] * sub + p["body"] * bright * body * (0.5 + 0.5 * vel) + p["pluck"] * vel * pluck
    y = np.tanh(y * p["drive"]) / np.tanh(p["drive"])
    return (y * (0.55 + 0.45 * vel)).astype(np.float32)


# ---------------------------------------------------------------- vibraphone

def vibes_note(midi: float, vel: float, dur: float, p: dict, rng: np.random.Generator) -> np.ndarray:
    f = hz(midi)
    ring = dur + p["ring"]
    n = int(ring * fx.SR)
    t = _t(n)
    y = np.zeros(n)
    for ratio, amp, dec in zip(p["ratios"], p["amps"], p["decays"]):
        if f * ratio > fx.SR * 0.45:
            continue
        d = dec * (440 / f) ** 0.3
        y += amp * (vel ** (1 + ratio * 0.1)) * np.sin(TAU * f * ratio * t + rng.random()) * np.exp(-t / d)
    y *= _attack(t, 0.001) * _release(t, ring - p["ring"] * 0.3, p["ring"] * 0.3)
    nn = int(0.01 * fx.SR)
    click = fx.lp(rng.standard_normal(nn).astype(np.float32), 3500) * np.exp(-np.arange(nn) / (0.002 * fx.SR))
    y[:nn] += p["click"] * vel * click
    return (y * vel).astype(np.float32)


# ---------------------------------------------------------------- muted horn (additive, breathy)

def horn_note(midi: float, vel: float, dur: float, p: dict, rng: np.random.Generator,
              from_midi: float | None = None) -> np.ndarray:
    rel = p["release"]
    n = int((dur + rel) * fx.SR)
    t = _t(n)
    cents = -p["scoop"] * (0.6 + 0.4 * rng.random()) * np.exp(-t / 0.045)
    vib_on = np.clip((t - p["vibrato_delay"]) / 0.35, 0, 1)
    cents = cents + p["vibrato_cents"] * vib_on * np.sin(TAU * p["vibrato_rate"] * t + rng.random() * 6)
    f0 = hz(midi)
    if from_midi is not None:  # legato slur
        cents = cents + (from_midi - midi) * 100 * np.exp(-t / 0.03)
    f = f0 * 2 ** (cents / 1200)
    phase = np.cumsum(TAU * f / fx.SR)
    swell = _attack(t, p["attack"]) * _release(t, dur, rel)
    long_note = min(1.0, dur / 0.6)
    swell *= 1 + p["swell"] * long_note * np.clip(t / max(dur, 0.01), 0, 1) * (t < dur)
    bright = p["bright_min"] + (p["bright_max"] - p["bright_min"]) * vel * (_attack(t, 0.07) * (1 - 0.3 * np.clip(t / 1.5, 0, 1)))
    y = np.zeros(n)
    k = 1
    while f0 * k < 8000 and k <= 40:
        y += np.sin(k * phase) / k * np.exp(-(k - 1) / bright)
        k += 1
    y *= swell
    breath = fx.bp(rng.standard_normal(n).astype(np.float32), 1400, 4200) * swell * p["breath"]
    y = y + breath
    return (y * (0.4 + 0.6 * vel)).astype(np.float32)


# ---------------------------------------------------------------- pad (detuned saws, filtered)

def pad_chord(midis: list[int], dur: float, p: dict, rng: np.random.Generator) -> np.ndarray:
    n = int((dur + p["release"]) * fx.SR)
    t = _t(n)
    y = np.zeros(n)
    for m in midis:
        for det in p["detune"]:
            f = hz(m) * 2 ** (det / 1200)
            ph = (f * t + rng.random()) % 1.0
            y += 2 * ph - 1
    y /= max(1, len(midis) * len(p["detune"])) ** 0.5
    env = _attack(t, p["attack"]) * _release(t, dur, p["release"])
    y = fx.lp((y * env).astype(np.float32), p["cutoff"], 2)
    return y


# ---------------------------------------------------------------- piano (inharmonic additive)

def piano_note(midi: float, vel: float, dur: float, p: dict, rng: np.random.Generator) -> np.ndarray:
    f = hz(midi)
    n = int((dur + p["release"]) * fx.SR)
    t = _t(n)
    y = np.zeros(n)
    for k in range(1, 16):
        fk = k * f * np.sqrt(1 + p["inharm"] * k * k)
        if fk > fx.SR * 0.45:
            break
        tau = p["decay"] * (262 / f) ** 0.5 / k ** 0.7
        y += (vel ** (0.5 + k * 0.08)) / k ** 1.1 * np.sin(TAU * fk * t + rng.random()) * np.exp(-t / tau)
    y *= _attack(t, 0.002) * _release(t, dur, p["release"])
    nn = int(0.015 * fx.SR)
    y[:nn] += p["hammer"] * vel * fx.bp(rng.standard_normal(nn).astype(np.float32), 800, 5000) * np.exp(-np.arange(nn) / (0.003 * fx.SR))
    return y.astype(np.float32)


# ---------------------------------------------------------------- drum kit

def _metal(t: np.ndarray, base: float, rng) -> np.ndarray:
    ratios = np.array([1.0, 1.4827, 1.8003, 2.5464, 2.6303, 3.8971])
    y = np.zeros(len(t))
    for r in ratios:
        y += np.sign(np.sin(TAU * base * r * t + rng.random() * 6))
    return y


def kick(rng, vel=1.0, start=125.0, end=52.0, decay=0.24, click=0.25, body=0.25, sweep=0.034) -> np.ndarray:
    n = int(decay * 4 * fx.SR)
    t = _t(n)
    f = end + (start - end) * np.exp(-t / sweep)
    ph = np.cumsum(TAU * f / fx.SR)
    y = np.sin(ph) * np.exp(-t / decay) * _attack(t, 0.0008)
    nz = rng.standard_normal(n).astype(np.float32)
    y += click * fx.hp(nz, 2000) * np.exp(-t / 0.003)
    y += body * fx.lp(nz, 900) * np.exp(-t / 0.045)
    y = np.tanh(y * 1.6) / np.tanh(1.6)
    return (y * vel).astype(np.float32)


def snare(rng, vel=1.0, tone=188.0, decay=0.15, crack=1.0, dark=False) -> np.ndarray:
    """A drum, not a noise burst: the head's inharmonic modes carry the body, the wires are excited
    by it and stay darker, the stick adds a short click."""
    n = int(0.6 * fx.SR)
    t = _t(n)
    v = vel
    modes = [(1.0, 1.0, 0.075), (1.59, 0.55, 0.05), (2.14, 0.38, 0.04), (2.30, 0.3, 0.035), (2.65, 0.2, 0.03), (2.92, 0.14, 0.025)]
    body = np.zeros(n)
    for r, a, d in modes:
        f = tone * r * (1 + 0.08 * np.exp(-t / 0.008))
        body += a * np.sin(TAU * np.cumsum(f) / fx.SR + rng.random() * 6) * np.exp(-t / (d * (1.4 if dark else 1.0)))
    nz = rng.standard_normal(n).astype(np.float32)
    top = 4200 if dark or v < 0.4 else 6800
    wires = fx.lp(fx.bp(nz, 1200, top), top, 2) * np.exp(-t / (decay * (0.6 + 0.4 * v)))
    wires *= 0.55 + 0.45 * np.exp(-t / 0.03)
    snap = fx.bp(nz, 1000, 5000) * np.exp(-t / 0.004) * crack
    y = 0.95 * body * (0.7 + 0.3 * v) + 0.62 * wires + 0.3 * snap * v
    y = np.tanh(y * 1.4) / np.tanh(1.4)
    return (y * v).astype(np.float32)


def hat(rng, vel=1.0, open_=False, base=410.0) -> np.ndarray:
    dec = 0.22 if open_ else 0.028 + 0.012 * rng.random()
    n = int(dec * 5 * fx.SR)
    t = _t(n)
    y = _metal(t, base * (1 + 0.01 * rng.standard_normal()), rng) * 0.5
    y += rng.standard_normal(n) * 0.3
    y = fx.lp(fx.bp(y.astype(np.float32), 5500, 13000), 11500, 2) * np.exp(-t / dec) * _attack(t, 0.0008)
    return (y * vel).astype(np.float32)


def ride(rng, vel=1.0, bell=0.3) -> np.ndarray:
    n = int(2.2 * fx.SR)
    t = _t(n)
    y = _metal(t, 610.0, rng) * 0.4 + rng.standard_normal(n) * 0.5
    y = fx.bp(y.astype(np.float32), 3500, 13000) * (np.exp(-t / 0.7) * 0.5 + 0.5 * np.exp(-t / 0.06))
    y += bell * (np.sin(TAU * 2310 * t) + 0.6 * np.sin(TAU * 3480 * t)) * np.exp(-t / 0.4)
    return (y * vel * 0.7).astype(np.float32)


def crash(rng, vel=1.0) -> np.ndarray:
    n = int(3.0 * fx.SR)
    t = _t(n)
    y = _metal(t, 520.0, rng) * 0.3 + rng.standard_normal(n)
    y = fx.bp(y.astype(np.float32), 2500, 15000) * np.exp(-t / 1.1) * _attack(t, 0.001)
    return (y * vel * 0.6).astype(np.float32)


def shaker(rng, vel=1.0) -> np.ndarray:
    n = int(0.12 * fx.SR)
    t = _t(n)
    env = _attack(t, 0.009) * np.exp(-t / 0.035)
    y = fx.bp(rng.standard_normal(n).astype(np.float32), 4500, 11000) * env
    return (y * vel).astype(np.float32)


def rim(rng, vel=1.0) -> np.ndarray:
    n = int(0.1 * fx.SR)
    t = _t(n)
    y = np.sin(TAU * 1720 * t) * np.exp(-t / 0.012) + 0.5 * fx.hp(rng.standard_normal(n).astype(np.float32), 2500) * np.exp(-t / 0.004)
    return (y * vel * 0.8).astype(np.float32)


def bongo(rng, vel=1.0, pitch=330.0) -> np.ndarray:
    n = int(0.35 * fx.SR)
    t = _t(n)
    f = pitch * (1 + 0.35 * np.exp(-t / 0.008))
    y = np.sin(np.cumsum(TAU * f / fx.SR)) * np.exp(-t / 0.09)
    y += 0.3 * fx.bp(rng.standard_normal(n).astype(np.float32), 1500, 5000) * np.exp(-t / 0.006)
    return (y * vel * 0.8).astype(np.float32)


# ---------------------------------------------------------------- atmosphere

def vinyl(n: int, rng, crackle: float = 1.0, hiss: float = 1.0) -> np.ndarray:
    out = np.zeros((n, 2), np.float32)
    clicks = rng.random(n) < 9.0 / fx.SR
    for c in range(2):
        imp = np.where(clicks & (rng.random(n) < 0.6), rng.standard_normal(n) * rng.random(n) ** 3, 0).astype(np.float32)
        out[:, c] = fx.bp(imp, 900, 9000) * 3.0 * crackle
        out[:, c] += fx.lp(rng.standard_normal(n).astype(np.float32), 6000) * 0.012 * hiss
    rumble = fx.lp(rng.standard_normal(n).astype(np.float32), 40) * 0.05
    return out + rumble[:, None] * 0.0  # rumble left out: keep the low end clean


def haze(n: int, rng) -> np.ndarray:
    """Distant night-city air: two slowly wandering band-passed noises."""
    t = np.arange(n) / fx.SR
    out = np.zeros((n, 2), np.float32)
    for c in range(2):
        nz = rng.standard_normal(n).astype(np.float32)
        curve = 700 + 500 * np.sin(TAU * 0.031 * t + c) + 250 * np.sin(TAU * 0.11 * t + 2 * c)
        x = fx.sweep(nz, "lowpass", curve[:: 512], block=512)
        out[:, c] = fx.hp(x, 180) * (0.6 + 0.4 * np.sin(TAU * 0.05 * t + c * 1.7))
    return out * 0.08


def signal_blip(midi: float, dur: float, rng) -> np.ndarray:
    """A short radio 'signal': a sine through a narrow band with a little AM, like distant shortwave."""
    n = int((dur + 0.05) * fx.SR)
    t = _t(n)
    f = hz(midi)
    y = np.sin(TAU * f * t + 0.6 * np.sin(TAU * f * 2.0 * t)) * _attack(t, 0.004) * _release(t, dur, 0.04)
    y *= 1 - 0.3 * (0.5 + 0.5 * np.sin(TAU * 31 * t))
    y = fx.bp(y.astype(np.float32), f * 0.7, min(f * 3.2, 12000))
    return y.astype(np.float32)


# ---------------------------------------------------------------- organ (drawbars + key click)

DRAWBAR_RATIOS = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0]   # 16' 8' 5 1/3' 4' 2 2/3' 2' 1 3/5' 1 1/3' 1'


def organ_note(midi: float, vel: float, dur: float, p: dict, rng: np.random.Generator) -> np.ndarray:
    f = hz(midi)
    n = int((dur + p["release"]) * fx.SR)
    t = _t(n)
    y = np.zeros(n)
    for r, a in zip(DRAWBAR_RATIOS, p["drawbars"]):
        if a <= 0 or f * r > fx.SR * 0.45:
            continue
        y += a / 8 * np.sin(TAU * f * r * t + rng.random() * 6)
    perc = p.get("percussion", 0.0)
    if perc:
        y += perc * np.sin(TAU * f * 3 * t) * np.exp(-t / 0.12)
    y *= _attack(t, 0.004) * _release(t, dur, p["release"])
    nn = int(0.006 * fx.SR)
    y[:nn] += p["click"] * fx.hp(rng.standard_normal(nn).astype(np.float32), 2000) * np.linspace(1, 0, nn)
    y = np.tanh(y * p.get("drive", 1.0)) / np.tanh(p.get("drive", 1.0))
    return (y * (0.5 + 0.5 * vel)).astype(np.float32)


# ---------------------------------------------------------------- vox (formant voice: wordless 'ooh / aah' chops and pads)

VOWELS = {  # formant centre frequencies (Hz) and bandwidths
    "aa": ([800, 1150, 2900], [80, 90, 120]),
    "ah": ([700, 1220, 2600], [80, 90, 120]),
    "oo": ([350, 600, 2400], [60, 80, 120]),
    "oh": ([450, 800, 2830], [70, 80, 100]),
    "ee": ([270, 2300, 3000], [60, 90, 100]),
    "eh": ([530, 1840, 2480], [60, 90, 100]),
}


def vox_note(midi: float, vel: float, dur: float, p: dict, rng: np.random.Generator,
             from_midi: float | None = None) -> np.ndarray:
    """A sung vowel: harmonic source shaped by three formants, gliding from one vowel to another
    across the note, with scoop, delayed vibrato and breath. Short notes become 'chops'."""
    rel = p["release"]
    n = int((dur + rel) * fx.SR)
    t = _t(n)
    vs = p["vowels"]
    a_v = vs[int(rng.integers(len(vs)))]
    b_v = vs[int(rng.integers(len(vs)))] if p.get("morph", True) else a_v
    cents = -p["scoop"] * np.exp(-t / 0.04)
    if from_midi is not None:
        cents = cents + (from_midi - midi) * 100 * np.exp(-t / 0.035)
    vib = np.clip((t - p["vibrato_delay"]) / 0.3, 0, 1) * p["vibrato_cents"] * np.sin(TAU * 5.2 * t + rng.random() * 6)
    f0 = hz(midi)
    f = f0 * 2 ** ((cents + vib) / 1200)
    phase = np.cumsum(TAU * f / fx.SR)
    # formants interpolated over the note (coarse: per-harmonic gains at start and end)
    m = np.clip(t / max(dur, 0.05), 0, 1)
    y = np.zeros(n)
    k = 1
    while f0 * k < 7000 and k <= 60:
        fk = f0 * k
        ga = sum(np.exp(-0.5 * ((fk - c) / b) ** 2) * w for c, b, w in zip(*VOWELS[a_v], (1.0, 0.7, 0.35)))
        gb = sum(np.exp(-0.5 * ((fk - c) / b) ** 2) * w for c, b, w in zip(*VOWELS[b_v], (1.0, 0.7, 0.35)))
        g = (ga * (1 - m) + gb * m) + 0.02 / k
        y += g * np.sin(k * phase) / k ** 0.3
        k += 1
    env = _attack(t, p["attack"]) * _release(t, dur, rel)
    breath = fx.bp(rng.standard_normal(n).astype(np.float32), 2500, 7000) * p["breath"]
    y = (y / max(np.abs(y).max(), 1e-6) + breath) * env
    return (y * (0.4 + 0.6 * vel)).astype(np.float32)


# ---------------------------------------------------------------- rave stab (detuned saw stack, decaying filter)

def stab_note(midi: float, vel: float, dur: float, p: dict, rng: np.random.Generator) -> np.ndarray:
    """Detuned saw stack; `chord` (semitone offsets) stacks a fixed shape on every note, like the
    one-finger chord stabs of early-90s samplers."""
    n = int((dur + p["release"]) * fx.SR)
    t = _t(n)
    y = np.zeros(n)
    nv = p["voices"]
    shape = p.get("chord", [0])
    for off in shape:
        f = hz(midi + off)
        for i in range(nv):
            det = (i - (nv - 1) / 2) / max(nv - 1, 1) * 2 * p["detune_cents"]
            fi = f * 2 ** (det / 1200)
            y += 2 * ((fi * t + rng.random()) % 1.0) - 1
    y /= np.sqrt(nv * len(shape))
    y = y.astype(np.float32)
    bright = fx.lp(y, p["cutoff_hi"], 2)
    dark = fx.lp(y, p["cutoff_lo"], 2)
    fenv = np.exp(-t / p["filter_decay"]).astype(np.float32)
    out = bright * fenv + dark * (1 - fenv)
    out *= (_attack(t, 0.002) * np.exp(-t / p["amp_decay"]) * _release(t, dur, p["release"])).astype(np.float32)
    return (out * vel).astype(np.float32)


def clap(rng, vel=1.0, tail=0.12) -> np.ndarray:
    n = int(0.5 * fx.SR)
    t = _t(n)
    nz = fx.bp(rng.standard_normal(n).astype(np.float32), 900, 7000)
    env = np.zeros(n)
    for k, off in enumerate((0.0, 0.009, 0.019, 0.027)):
        env += (t >= off) * np.exp(-np.maximum(t - off, 0) / (0.006 if k < 3 else tail))
    return (nz * env * vel * 0.7).astype(np.float32)


# ---------------------------------------------------------------- reese: dingy, gritty jungle bass

def reese_note(midi: float, vel: float, dur: float, p: dict, rng: np.random.Generator,
               from_midi: float | None = None) -> np.ndarray:
    """Clean sine sub underneath; above it two detuned saws beating against each other, filtered,
    then driven hard and bit-reduced, so the grit lives in the mids and the low end stays solid."""
    n = int((dur + p["release"]) * fx.SR)
    t = _t(n)
    f1 = hz(midi)
    if from_midi is not None:
        f = f1 + (hz(from_midi) - f1) * np.exp(-t / (p["glide"] / 3))
    else:
        f = np.full(n, f1)
    ph = np.cumsum(f / fx.SR)
    env = _attack(t, 0.006) * _release(t, dur, p["release"])
    sub = np.sin(TAU * ph) * env
    det = p["detune_cents"] / 1200
    saws = sum(2 * ((ph * 2 ** (d * det) + rng.random()) % 1.0) - 1 for d in (-1, 1)) / 2
    mid = (saws * env).astype(np.float32)
    bright = fx.lp(mid, p["cutoff_hi"], 2)
    dark = fx.lp(mid, p["cutoff_lo"], 2)
    m = (0.5 + 0.5 * np.sin(TAU * p["lfo_hz"] * t + rng.random() * 6)) * np.exp(-t / p["env_decay"]) * 0.6 + 0.25
    mid = bright * m + dark * (1 - m)
    mid = fx.hp(mid.astype(np.float32), 110, 2)
    mid = np.tanh(mid * p["drive"]) / np.tanh(p["drive"])
    if p.get("bits"):
        q = 2 ** (p["bits"] - 1)
        mid = np.round(mid * q) / q
    y = p["sub"] * sub + p["mid"] * mid * (0.6 + 0.4 * vel)
    return y.astype(np.float32)


# ---------------------------------------------------------------- nylon guitar (Karplus–Strong, tuned)

def guitar_note(midi: float, vel: float, dur: float, p: dict, rng: np.random.Generator,
                from_midi: float | None = None, legato: bool = False, keep_pluck: bool = False) -> np.ndarray:
    """Plucked nylon string: a soft noise excitation through a tuned feedback loop (two-point
    average for string damping + first-order all-pass for exact tuning), run as one IIR filter.

    Expression is added afterwards by varispeed (reading the string back along a pitch curve):
    `from_midi` slides in from the previous note like a left-hand slide, `legato` replaces the pluck
    with a soft hammer-on, and long notes get a delayed finger vibrato. Lifting the finger damps."""
    from scipy.signal import lfilter
    f = hz(midi) * 2 ** (rng.normal(0, 1.5) / 1200)
    period = fx.SR / f
    N = int(np.floor(period - 0.5 - 0.15))
    d = period - 0.5 - N                         # all-pass supplies the fraction (0.15 .. 1.15)
    C = (1 - d) / (1 + d)
    g = p["sustain"] ** (1 / max(f / 110, 0.5))  # higher strings lose energy a bit faster
    n = int((dur + p["release"]) * fx.SR * 1.06) + 64
    soft = (legato or from_midi is not None) and not keep_pluck
    amp = (0.5 + 0.5 * vel) * (p.get("legato_level", 0.45) if soft else 1.0)
    exc = rng.standard_normal(N + 2) * amp
    tone = p["pluck_tone"] * (0.6 + 0.4 * vel) * (0.55 if soft else 1.0)
    exc = fx.lp(exc.astype(np.float32), tone, 2)
    pos = max(1, int(N * p["pluck_pos"]))         # plucking point comb
    exc = exc - np.concatenate([np.zeros(pos), exc[:-pos]]) * 0.8
    x = np.zeros(n)
    x[:len(exc)] = exc[:n]
    a = np.zeros(N + 3)
    a[0], a[1] = 1.0, C
    a[N] -= 0.5 * g * C
    a[N + 1] -= 0.5 * g * (1 + C)
    a[N + 2] -= 0.5 * g
    y = lfilter([1.0, C], a, x)
    # expression by varispeed: glide from the previous note, then finger vibrato
    m = int((dur + p["release"]) * fx.SR)
    t = _t(m)
    cents = np.zeros(m)
    if from_midi is not None:
        gl = p.get("bend_time", 0.14) if keep_pluck else p.get("glide", 0.09)
        cents += (from_midi - midi) * 100 * np.clip(1 - t / gl, 0, 1) ** 2
    if dur > p.get("vib_min_dur", 0.45):
        on = np.clip((t - p.get("vib_delay", 0.3)) / 0.25, 0, 1)
        cents += p.get("vib_cents", 9) * on * np.sin(TAU * p.get("vib_rate", 5.2) * t + rng.random() * 6)
    rate = 2 ** (cents / 1200)
    posr = np.cumsum(rate) - rate[0]
    y = np.interp(posr, np.arange(len(y)), y)
    if soft:   # a hammer-on or slide has no pick attack
        y *= np.minimum(1.0, t / 0.012)
    y *= _release(t, dur, p["release"])
    body = [tuple(b) for b in p.get("body", [["peak", 110, 4.0, 1.2], ["peak", 220, 2.0, 1.0], ["hp", 70]])]
    y = fx.eq(y.astype(np.float32), body)  # the instrument's body
    return (y * p["level"]).astype(np.float32)



# ---------------------------------------------------------------- Japanese instruments

def shamisen_note(midi: float, vel: float, dur: float, p: dict, rng: np.random.Generator,
                  from_midi: float | None = None) -> np.ndarray:
    """Shamisen: a bright, short-sustain string (Karplus-Strong), the bachi's slap on the skin-covered
    body, and sawari, the deliberate buzz of the open string against the neck."""
    y = guitar_note(midi, vel, dur, p, rng, from_midi=from_midi, keep_pluck=True)
    n = len(y)
    t = _t(n)
    buzz = fx.hp(np.tanh(6 * y / max(np.abs(y).max(), 1e-6)).astype(np.float32), 1800, 2) * np.exp(-t / p.get("sawari_decay", 0.35))
    y = y + p.get("sawari", 0.25) * buzz * np.abs(y).max()
    m = min(n, int(0.05 * fx.SR))
    nz = rng.standard_normal(m).astype(np.float32)
    slap = fx.bp(nz, 700, 4500) * np.exp(-np.arange(m) / (0.006 * fx.SR))
    thump = np.sin(TAU * 165 * np.arange(m) / fx.SR) * np.exp(-np.arange(m) / (0.02 * fx.SR))
    y[:m] += (p.get("slap", 0.5) * slap + 0.3 * thump) * vel * np.abs(y).max()
    return y.astype(np.float32)


def taiko(rng, kind: str = "odaiko", vel: float = 1.0) -> np.ndarray:
    """Taiko from membrane modes: the big ōdaiko (deep, long), the chū-daiko (mid), the tight shime-daiko,
    plus 'kara' (stick on the rim) and the kane (small hand gong)."""
    if kind == "kara":
        n = int(0.08 * fx.SR)
        t = _t(n)
        y = np.sin(TAU * 1450 * t) * np.exp(-t / 0.01) + 0.6 * fx.bp(rng.standard_normal(n).astype(np.float32), 1500, 6000) * np.exp(-t / 0.004)
        return (y * vel * 0.7).astype(np.float32)
    if kind == "kane":
        n = int(0.9 * fx.SR)
        t = _t(n)
        y = np.zeros(n)
        for r, a, d in ((1.0, 1.0, 0.35), (2.76, 0.6, 0.2), (5.4, 0.4, 0.09), (8.9, 0.25, 0.05)):
            y += a * np.sin(TAU * 1180 * r * t + rng.random() * 6) * np.exp(-t / d)
        y += 0.3 * fx.hp(rng.standard_normal(n).astype(np.float32), 5000) * np.exp(-t / 0.01)
        return (y * vel * 0.35).astype(np.float32)
    spec = {"odaiko": (58, 0.9, 0.55), "chu": (112, 0.45, 0.4), "shime": (330, 0.12, 0.9)}[kind]
    f0, dec, slap = spec
    n = int(dec * 4 * fx.SR)
    t = _t(n)
    f0 *= 1 + 0.02 * rng.standard_normal()
    y = np.zeros(n)
    for r, a, d in ((1.0, 1.0, 1.0), (1.59, 0.5, 0.6), (2.14, 0.3, 0.45), (2.65, 0.18, 0.3), (3.16, 0.1, 0.2)):
        f = f0 * r * (1 + 0.15 * np.exp(-t / 0.02))          # skin pitch drops after the hit
        y += a * np.sin(np.cumsum(TAU * f / fx.SR) + rng.random() * 6) * np.exp(-t / (dec * d))
    nz = rng.standard_normal(n).astype(np.float32)
    y += slap * fx.bp(nz, 400, 5000 if kind == "shime" else 2500) * np.exp(-t / 0.008)
    y += 0.25 * fx.lp(nz, 300) * np.exp(-t / (dec * 0.5)) * (kind == "odaiko")
    y = np.tanh(y * 1.3) / np.tanh(1.3)
    return (y * vel).astype(np.float32)


def koto_bend_ok(p: dict, rng) -> float | None:
    """How far below to start a press-bend (oshide), or None."""
    if rng.random() < p.get("oshi_prob", 0.0):
        return float(rng.choice([1, 2]))
    return None


# ---------------------------------------------------------------- Python sampler (no LMMS needed)

_smp_cache: dict = {}


def sampler_note(midi: float, vel: float, dur: float, p: dict, rng: np.random.Generator) -> np.ndarray:
    """A recorded one-shot played chromatically like a 90s sampler: resampled to pitch (so it gets
    shorter and brighter going up, longer and darker going down), velocity sets level and brightness,
    a release envelope at note-off."""
    import soundfile as sf
    from pathlib import Path
    key = p["sample"]
    if key not in _smp_cache:
        path = Path(key) if Path(key).is_absolute() else Path("/usr/share/lmms/samples") / key
        x, sr = sf.read(str(path), dtype="float32", always_2d=True)
        m = x.mean(1)
        if sr != fx.SR:
            m = fx.resample(m, sr / fx.SR)
        on = int(np.argmax(np.abs(m) > np.abs(m).max() * 0.01))
        m = m[max(0, on - 16):]
        _smp_cache[key] = (m / (np.abs(m).max() + 1e-9)).astype(np.float32)
    src = _smp_cache[key]
    ratio = 2 ** ((midi - p["root"]) / 12) * 2 ** (rng.normal(0, 2) / 1200)
    n = int((dur + p.get("release", 0.25)) * fx.SR)
    need = int(n * ratio) + 2
    seg = src[:need]
    y = fx.resample(seg, ratio)[:n]
    if len(y) < n:
        y = np.pad(y, (0, n - len(y)))
    t = _t(n)
    y *= _release(t, dur, p.get("release", 0.25))
    if vel < 0.85:
        y = fx.lp(y.astype(np.float32), 2500 + 9000 * vel, 2)
    return (y * (0.25 + 0.75 * vel)).astype(np.float32)


# ---------------------------------------------------------------- analog mono bass (house)

def analog_bass_note(midi: float, vel: float, dur: float, p: dict, rng: np.random.Generator,
                     from_midi: float | None = None) -> np.ndarray:
    """A rounded analog-style bass: saw + square through a resonant low-pass whose cutoff snaps open
    and closes fast (the 'pluck'), a clean sine sub underneath, punchy amp envelope, light drive."""
    rel = p["release"]
    n = int((dur + rel) * fx.SR)
    t = _t(n)
    f1 = hz(midi)
    f = np.full(n, f1) if from_midi is None else f1 + (hz(from_midi) - f1) * np.exp(-t / (p["glide"] / 3))
    ph = np.cumsum(f / fx.SR)
    saw = 2 * (ph % 1.0) - 1
    sq = np.sign(np.sin(2 * np.pi * ph))
    osc = (p["saw"] * saw + p["square"] * sq).astype(np.float32)
    env_f = np.exp(-t / p["filter_decay"])
    cutoff = p["cutoff"] + p["env_amount"] * (0.4 + 0.6 * vel) * env_f
    y = fx.sweep(osc, "lowpass", cutoff, block=64, order=2)
    if p.get("resonance"):
        y = y + p["resonance"] * fx.bp(y, max(60, p["cutoff"] * 0.8), p["cutoff"] * 1.6)
    sub = np.sin(2 * np.pi * ph) * p["sub"]
    amp = _attack(t, 0.003) * (p["sustain"] + (1 - p["sustain"]) * np.exp(-t / p["amp_decay"])) * _release(t, dur, rel)
    out = (y + sub) * amp
    out = np.tanh(out * p["drive"]) / np.tanh(p["drive"])
    return (out * (0.55 + 0.45 * vel)).astype(np.float32)
