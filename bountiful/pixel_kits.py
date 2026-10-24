"""Chip drum kits for 'Put on the Pixel': each machine synthesised offline the way its sound chip makes drums.

  nes     triangle kick and toms (32-step), 15-bit LFSR noise snare and hats, 16-level envelopes on the 240 Hz frame clock
  gb      Game Boy: pulse-wave kick, 7-bit (short) LFSR hats, 4-bit DAC, envelopes stepping at 64 Hz
  c64     SID: pitch tables stepping per 50 Hz PAL frame, smooth ADSR, resonant filter on kick and snare, ring-modulated ride
  amiga   ProTracker: the C-Lizzy break (break_maker.py) at the song's tempo, mono, 8-bit, sample-and-hold at Paula's
          C-3 rate (no anti-alias filter, so it aliases like a MOD), with NES hats and crash on top

    kit = build("nes", dest, **params)   -> {sound: wav path}
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, lfilter

import pixel_dnb as P

SR = P.SR
n = lambda s: int(s * SR)
frames, noise, triangle, pulse, sweep, decay = P.frames, P.noise, P.triangle, P.pulse, P.sweep, P.decay


def save(dest: Path, name: str, x, gain=0.9, bits=8):
    x = np.asarray(x, dtype=float)
    x = x - x.mean() * 0.5
    x = x / (np.abs(x).max() + 1e-9) * gain
    if bits:
        q = 2 ** (bits - 1) - 1
        x = np.round(x * q) / q
    fade = min(int(0.002 * SR), len(x) // 4)
    x[-fade:] *= np.linspace(1, 0, fade)
    sf.write(str(dest / f"{name}.wav"), x.astype(np.float32), SR, subtype="PCM_16")


def filt(x, kind, hz, order=2):
    b, a = butter(order, np.array(hz) / (SR / 2), kind)
    return lfilter(b, a, x)


def table(n_, hz_per_frame, rate=50):
    """A pitch table: one frequency per player frame (C64 / tracker style), held for the frame."""
    hold = SR // rate
    f = np.repeat(np.asarray(hz_per_frame, dtype=float), hold)
    return np.concatenate([f, np.full(max(0, n_ - len(f)), f[-1])])[:n_]


def nes(dest, kick=(240, 46, 22), kick_len=0.36, snare_clock=26000, snare_ms=85, hat_clock=110000, ride_hz=1567.98, bits=8, crash_ms=450):
    k = n(kick_len)
    x = triangle(sweep(k, *kick)) * frames(decay(k, kick_len * 470) * np.where(np.arange(k) < n(kick_len * 0.72), 1, decay(k, 40)))
    x[:n(0.012)] += 0.5 * noise(n(0.012), 90000, seed=3) * frames(decay(n(0.012), 4))
    save(dest, "kick", x, 0.95, bits)
    s = n(0.24)
    save(dest, "snare", 0.75 * noise(s, snare_clock, seed=5) * frames(decay(s, snare_ms)) + 0.7 * triangle(sweep(s, 260, 150, 25)) * frames(decay(s, 45)), 0.9, bits)
    g = n(0.08)
    save(dest, "ghost", noise(g, snare_clock * 1.15, seed=9) * frames(decay(g, 22)) + 0.3 * triangle(sweep(g, 240, 180, 20)) * frames(decay(g, 18)), 0.5, bits)
    hats(dest, hat_clock, bits)
    r = n(0.6)
    save(dest, "ride", 0.7 * noise(r, hat_clock * 0.64, short=True, seed=29) * frames(decay(r, 160)) + 0.35 * pulse(np.full(r, ride_hz), 0.125) * frames(decay(r, 120)), 0.5, bits)
    m = n(0.04)
    save(dest, "rim", pulse(np.full(m, 1760.0), 0.125) * frames(decay(m, 10)) + 0.4 * noise(m, 50000, seed=37) * frames(decay(m, 5)), 0.5, bits)
    for name, f0, f1 in (("tom_hi", 360, 190), ("tom_mid", 270, 130), ("tom_lo", 190, 85)):
        t = n(0.28)
        save(dest, name, triangle(sweep(t, f0, f1, 60)) * frames(decay(t, 110)), 0.8, bits)
    c = n(1.5)
    save(dest, "crash", noise(c, 60000, seed=31) * frames(decay(c, crash_ms)), 0.6, bits)


def hats(dest, clock, bits):
    h, o = n(0.05), n(0.3)
    save(dest, "hat", noise(h, clock, short=True, seed=17) * frames(decay(h, 12)), 0.55, bits)
    save(dest, "open", noise(o, clock, short=True, seed=23) * frames(decay(o, 90)), 0.55, bits)


def gb(dest):
    f64 = lambda e: frames(e, 64)
    k = n(0.32)
    x = filt(pulse(sweep(k, 260, 44, 18), 0.5), "low", 1400, 2) * f64(decay(k, 120))
    save(dest, "kick", x, 0.95, 4)
    s = n(0.22)
    save(dest, "snare", noise(s, 21000, seed=41) * f64(decay(s, 70)) + 0.5 * filt(pulse(sweep(s, 210, 140, 20), 0.5), "low", 2500) * f64(decay(s, 35)), 0.9, 4)
    g = n(0.07)
    save(dest, "ghost", noise(g, 24000, seed=43) * f64(decay(g, 20)), 0.45, 4)
    h, o = n(0.04), n(0.2)
    save(dest, "hat", noise(h, 65000, short=True, seed=47) * f64(decay(h, 14)), 0.5, 4)
    save(dest, "open", noise(o, 65000, short=True, seed=53) * f64(decay(o, 70)), 0.5, 4)
    r = n(0.45)
    save(dest, "ride", 0.6 * noise(r, 42000, short=True, seed=59) * f64(decay(r, 140)) + 0.4 * pulse(np.full(r, 1046.5), 0.125) * f64(decay(r, 110)), 0.45, 4)
    m = n(0.035)
    save(dest, "rim", pulse(np.full(m, 2093.0), 0.25) * f64(decay(m, 10)), 0.45, 4)
    for name, f0, f1 in (("tom_hi", 330, 180), ("tom_mid", 250, 125), ("tom_lo", 180, 80)):
        t = n(0.26)
        save(dest, name, triangle(sweep(t, f0, f1, 55)) * f64(decay(t, 100)), 0.8, 4)
    c = n(1.1)
    save(dest, "crash", noise(c, 40000, seed=61) * f64(decay(c, 330)), 0.55, 4)


def c64(dest):
    sid = lambda x: np.tanh(1.4 * x)                 # the SID's output stage, a little warm, no hard steps
    k = n(0.34)
    f = table(k, [620, 240, 130, 92, 74, 63, 56, 52, 50])
    x = filt(0.8 * triangle(f) + 0.35 * pulse(f, 0.4), "low", 900) * decay(k, 150)
    x[:n(0.02)] += 0.4 * filt(noise(n(0.02), 80000, seed=71), "high", 2000) * decay(n(0.02), 6)
    save(dest, "kick", sid(x), 0.95, 0)
    s = n(0.26)
    body = triangle(table(s, [310, 230, 190, 180])) * decay(s, 40)
    save(dest, "snare", sid(filt(noise(s, 40000, seed=73), "band", [900, 7000]) * decay(s, 95) + 0.6 * body), 0.9, 0)
    g = n(0.08)
    save(dest, "ghost", filt(noise(g, 40000, seed=79), "band", [1200, 7000]) * decay(g, 24), 0.45, 0)
    h, o = n(0.05), n(0.32)
    save(dest, "hat", filt(noise(h, 90000, seed=83), "high", 7000) * decay(h, 11), 0.5, 0)
    save(dest, "open", filt(noise(o, 90000, seed=89), "high", 6000) * decay(o, 95), 0.5, 0)
    r = n(0.6)
    ring = pulse(np.full(r, 1180.0), 0.5) * pulse(np.full(r, 1730.0), 0.5)    # SID ring modulation: a bell-ish ping
    save(dest, "ride", 0.6 * filt(noise(r, 90000, seed=97), "high", 5000) * decay(r, 170) + 0.4 * filt(ring, "high", 800) * decay(r, 150), 0.45, 0)
    m = n(0.05)
    save(dest, "rim", filt(pulse(table(m, [1500, 1100]), 0.3), "band", [600, 5000]) * decay(m, 12), 0.45, 0)
    for name, tab in (("tom_hi", [440, 300, 240, 210, 200]), ("tom_mid", [330, 210, 170, 150, 140]), ("tom_lo", [240, 150, 115, 100, 95])):
        t = n(0.3)
        save(dest, name, sid(triangle(table(t, tab)) * decay(t, 120)), 0.8, 0)
    c = n(1.4)
    save(dest, "crash", filt(noise(c, 90000, seed=101), "high", 3000) * decay(c, 420), 0.55, 0)


AMIGA_SLICES = [f"a{i:02d}" for i in range(64)] + [f"r{k:02d}" for k in range(4)]


def amiga(dest, bpm, bits=8, rate=16726):
    import break_maker as BM
    sl = BM.OUT / f"slices_{bpm}"
    if not (sl / "s00.wav").exists():
        BM.make(bpm)

    def crush(x):
        x = x.mean(1) if x.ndim == 2 else x
        idx = (np.floor(np.arange(len(x)) * rate / SR) * SR / rate).astype(int)   # sample-and-hold at Paula's rate
        return x[np.minimum(idx, len(x) - 1)]
    peak = max(np.abs(sf.read(str(p))[0]).max() for p in sl.glob("s*.wav"))
    q = 2 ** (bits - 1) - 1
    for i, name in enumerate(AMIGA_SLICES):
        src = sl / (f"s{i:02d}.wav" if i < 64 else f"rb{i - 64:02d}.wav")
        x = crush(sf.read(str(src))[0]) / peak * 0.95                          # one gain for all slices, so the break stays level
        sf.write(str(dest / f"{name}.wav"), (np.round(x * q) / q).astype(np.float32), SR, subtype="PCM_16")
    hats(dest, 110000, 8)
    c = n(1.5)
    save(dest, "crash", noise(c, 60000, seed=31) * frames(decay(c, 450)), 0.6, 8)
    r = n(0.6)
    save(dest, "ride", 0.7 * noise(r, 70000, short=True, seed=29) * frames(decay(r, 160)) + 0.35 * pulse(np.full(r, 1567.98), 0.125) * frames(decay(r, 120)), 0.5, 8)


def build(machine: str, dest: Path, **params) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    {"nes": nes, "gb": gb, "c64": c64, "amiga": amiga}[machine](dest, **params)
    return dest
