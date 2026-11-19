#!/usr/bin/env python3
"""Our own break: an original four-bar funk drum performance in the rhythmic style of the classic 'Amen' break (the
rhythm, not the recording), played on LMMS acoustic drum sounds, recorded through a room, a bus compressor, saturation
and a 12-bit sampler, then treated the way jungle producers treated a break: sped up on a sampler (pitch rises with
tempo), chopped into 16th slices and reversed beats, mapped across keys.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/break_maker.py [--bpm 168]
    -> samples/breaks/clizzy/  break_140.wav (the performance), break_<bpm>.wav, ride_<bpm>.wav,
                               slices_<bpm>/s00..s63.wav, rb00..rb15.wav (reversed beats), rideNN.wav (ride-only bars)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import ENGINE  # noqa: E402
sys.path.insert(0, str(ENGINE))
from engine import fx  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DM = ROOT / "samples" / "drummachines"
LMMS = Path("/usr/share/lmms/samples/drums")
OUT = ROOT / "samples" / "breaks" / "clizzy"
SR = 44100
PLAY_BPM = 140

# the performance, 16 steps a bar, 4 bars: (step, velocity). Bars 1-2 the main figure, bar 3 the displaced snare,
# bar 4 our own turnaround (not the original's): a pushed kick, a three-snare pickup and a crash on the 'and' of 3.
KICK = [[(0, 1.0), (2, 0.85), (10, 0.9), (11, 0.75)], [(0, 1.0), (2, 0.85), (10, 0.9), (11, 0.75)],
        [(0, 1.0), (2, 0.85), (10, 0.9), (11, 0.7)], [(0, 1.0), (3, 0.8), (10, 0.9)]]
SNARE = [[(4, 0.95), (12, 0.95)], [(4, 0.95), (12, 0.95)], [(4, 0.95), (14, 0.9)], [(4, 0.95), (9, 0.8), (12, 0.95), (15, 0.85)]]
GHOST = [[(7, 0.32), (9, 0.3), (15, 0.36)], [(7, 0.3), (9, 0.32), (15, 0.34)], [(7, 0.32), (9, 0.3)], [(7, 0.3), (13, 0.34)]]
CRASH = [[], [], [], [(10, 0.7)]]


def load(p, gain_db=0.0):
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    m = x.mean(1)
    if sr != SR:
        m = fx.resample(m, sr / SR)
    return (m / (np.abs(m).max() + 1e-9) * fx.db(gain_db)).astype(np.float32)


def layer(*parts):
    n = max(len(p) for p in parts)
    return sum(np.pad(p, (0, n - len(p))) for p in parts).astype(np.float32)


def perform(bpm=PLAY_BPM, seed=1994, pattern=None, bars=4, ride_on=True, mute=()):
    """A drum performance. pattern (optional): {"kick"|"snare"|"ghost"|"hat"|"open"|"crash": [bar: [(step, vel), ...]]};
    without one, the C-Lizzy break (KICK/SNARE/GHOST/CRASH + ride). mute: buses to leave silent (e.g. a hats-only take)."""
    rng = np.random.default_rng(seed)
    P = pattern or {"kick": KICK, "snare": SNARE, "ghost": GHOST, "crash": CRASH}
    kick = layer(load(DM / "acoustic" / "jazzkick.wav"), load(LMMS / "bassdrum_acoustic01.ogg", -6))
    snare = layer(load(DM / "acoustic" / "jazzsnr.wav"), load(LMMS / "snare_acoustic01.ogg", -4))
    ghost = fx.lp(load(DM / "acoustic" / "jazzsnr_h.wav"), 5500)
    ride = layer(load(DM / "acoustic" / "ride2.wav", -2), load(LMMS / "ride02.ogg", -5))
    bell = layer(ride, fx.hp(load(DM / "acoustic" / "ride3.wav", -6), 3000))
    crash = load(LMMS / "crash01.ogg")
    hat = layer(load(LMMS / "hihat_closed02.ogg", -1), fx.hp(load(DM / "acoustic" / "brush1.wav", -10), 2000))
    open_ = load(LMMS / "hihat_opened03.ogg", -3)
    step = 60 / bpm / 4
    n = int((16 * step * bars + 1.5) * SR)
    bus = {k: np.zeros(n, np.float32) for k in ("kick", "snare", "ride")}

    def hit(buf, smp, t, v):
        i = max(0, int(t * SR))
        k = min(len(smp), n - i)
        if k > 0:
            buf[i:i + k] += smp[:k] * v

    rideon = ride_on
    for b in range(bars):
        t0 = b * 16 * step
        get = lambda k: (P.get(k) or [[]] * bars)[b % len(P.get(k) or [[]])]
        for s, v in get("kick"):
            hit(bus["kick"], kick, t0 + s * step + rng.normal(0, 0.002), v * (1 + rng.normal(0, 0.03)))
        for s, v in get("snare"):
            hit(bus["snare"], snare, t0 + s * step + 0.004 + rng.normal(0, 0.002), v * (1 + rng.normal(0, 0.03)))     # laid back
        for s, v in get("ghost"):
            hit(bus["snare"], ghost, t0 + s * step + rng.normal(0, 0.005), v * (1 + rng.normal(0, 0.08)))
        if rideon:
            for s in range(0, 16, 2):                                 # the ride: 8ths, the off-beats lightly swung, a bell on the beat
                off = 0.008 if s % 4 == 2 else 0.0
                sm = bell if s % 4 == 0 else ride
                hit(bus["ride"], sm, t0 + s * step + off + rng.normal(0, 0.003), (0.62 if s % 4 == 0 else 0.48) * (1 + rng.normal(0, 0.06)))
        for s, v in get("hat"):                                       # closed hats: small, selective timing drift
            hit(bus["ride"], hat, t0 + s * step + rng.normal(0, 0.003 if s % 2 else 0.0015), v * (1 + rng.normal(0, 0.1)))
        for s, v in get("open"):
            hit(bus["ride"], open_, t0 + s * step, v)
        for s, v in get("crash"):
            hit(bus["ride"], crash, t0 + s * step, v)
    for k in mute:
        bus[k][:] = 0
    return bus, step


def record(bus):
    """Room, bus compression, saturation, a little tape, a 12-bit sampler: the break as it would come off a record."""
    room = fx.reverb_ir(0.55, predelay=0.006, damp=0.55, size=0.35, seed=11)
    kit = (fx.pan(bus["kick"], 0.0) + fx.pan(bus["snare"], 0.05) + fx.pan(bus["ride"], 0.25)).astype(np.float32)
    kit = kit + fx.convolve(fx.hp(kit, 200) * 0.22, room)
    kit = fx.eq(kit, [("peak", 120, 2.0, 0.9), ("peak", 900, 1.5, 1.0), ("peak", 4500, 2.0, 0.8), ("lp", 13000, 2)])
    kit = kit / (np.abs(kit).max() + 1e-9) * 0.5
    kit = fx.compress(kit, threshold_db=-20, ratio=4.0, attack=0.004, release=0.09)
    kit = fx.saturate(kit * 1.6, 1.4)
    kit = fx.crush(kit, bits=12, rate=26040, filtered=True)
    return (kit / (np.abs(kit).max() + 1e-9) * 0.89).astype(np.float32)


def speed(x, from_bpm, to_bpm):
    """Sampler speed-up: play the recording faster, so it is shorter and higher (+3.2 semitones for 140 -> 168)."""
    return fx.resample(x, to_bpm / from_bpm).astype(np.float32)


def make(bpm=168):
    OUT.mkdir(parents=True, exist_ok=True)
    bus, step = perform()
    brk = record(bus)
    ride_only = record({"kick": bus["kick"] * 0, "snare": bus["snare"] * 0, "ride": bus["ride"]})
    bars4 = int(64 * step * SR)
    sf.write(str(OUT / f"break_{PLAY_BPM}.wav"), brk[:bars4], SR, subtype="PCM_24")
    fast = speed(brk, PLAY_BPM, bpm)
    fride = speed(ride_only, PLAY_BPM, bpm)
    st = 60 / bpm / 4
    L = int(round(64 * st * SR))
    sf.write(str(OUT / f"break_{bpm}.wav"), fast[:L], SR, subtype="PCM_24")
    sl = OUT / f"slices_{bpm}"
    sl.mkdir(exist_ok=True)
    n1 = st * SR
    fade = int(0.0015 * SR)
    for i in range(64):                                   # 16th slices, each exactly one step (+ a short fade), so a sequence of them is seamless
        a, b = int(round(i * n1)), int(round((i + 1) * n1))
        s = fast[a:b + fade].copy()
        s[-fade:] *= np.linspace(1, 0, fade)[:, None]
        if i > 0:                                         # matching linear crossfade with the previous slice's tail
            s[:fade] *= np.linspace(0, 1, fade)[:, None]
        sf.write(str(sl / f"s{i:02d}.wav"), s, SR, subtype="PCM_24")
    for k in range(16):                                   # reversed beats (four slices backwards): the swell into a hit
        a, b = int(round(4 * k * n1)), int(round(4 * (k + 1) * n1))
        s = fast[a:b][::-1].copy()
        s[-fade:] *= np.linspace(1, 0, fade)[:, None]
        sf.write(str(sl / f"rb{k:02d}.wav"), s, SR, subtype="PCM_24")
    for k in range(4):                                    # ride-only bars (intros, breakdowns)
        a, b = int(round(16 * k * n1)), int(round(16 * (k + 1) * n1))
        s = fride[a:b + fade].copy()
        s[-fade:] *= np.linspace(1, 0, fade)[:, None]
        sf.write(str(sl / f"ride{k}.wav"), s, SR, subtype="PCM_24")
    return OUT, sl


if __name__ == "__main__":
    bpm = int(sys.argv[sys.argv.index("--bpm") + 1]) if "--bpm" in sys.argv else 168
    out, sl = make(bpm)
    x, _ = sf.read(str(out / f"break_{bpm}.wav"))
    print(f"{out}: break_{PLAY_BPM}.wav, break_{bpm}.wav ({len(x) / SR:.3f} s = 4 bars at {bpm}), {len(list(sl.glob('*.wav')))} slices in {sl.name}")
