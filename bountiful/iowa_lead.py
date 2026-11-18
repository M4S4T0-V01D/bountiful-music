"""Sampled lead instruments for the jazz-hop singles, built from the University of Iowa Musical Instrument
Samples (theremin.music.uiowa.edu, "may be downloaded and used for any projects, without restrictions").

The raw recordings are chromatic runs, one file per octave and dynamic (pp, mf, ff), recorded dry. `build()`
cuts them into one file per note under samples/iowa/<instrument>/<layer>/<midi>.wav and checks each note's
pitch. `render_lead()` plays a stem's notes (in beats, as the singles keep them) through those samples:

- a dynamic layer chosen by velocity, every note levelled to its layer so the run's uneven notes even out
- winds slur into notes that start where the last one ended (attack skipped, short crossfade) and tongue
  the rest; vibes ring until note-off (or the sustain pedal) and are then damped
- the stem's pitch bends (scoops, falls, scripted vibrato) and CC11 swells, as fluidsynth would apply them
- a synthetic stereo hall in place of the reverb send, since the samples are anechoic

Rebuild the slices: `.venv/bin/python bountiful/iowa_lead.py [instrument ...]` (after the raw files are in samples/iowa/raw).
"""
from __future__ import annotations

import re
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy import signal

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "samples" / "iowa"
SR = 44100
NAMES = {"C": 0, "Db": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "Gb": 6, "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11}
# instrument: (raw file prefix, kind, layer levels in dB)
INSTRUMENTS = {
    "alto": ("AltoSax.Vib", "wind", {"pp": -9.0, "mf": -4.0, "ff": 0.0}),
    "trumpet": ("Trumpet.novib", "wind", {"pp": -9.0, "mf": -4.0, "ff": 0.0}),
    "vibes": ("Vibraphone.sustain", "mallet", {"pp": -10.0, "mf": -4.5, "ff": 0.0}),
    "flute": ("Flute.vib", "wind", {"pp": -9.0, "mf": -4.0, "ff": 0.0}),
}
LAYERS = ("pp", "mf", "ff")


def midi_of(name: str) -> int:
    m = re.fullmatch(r"([A-G]b?)(\d)", name)
    return 12 * (int(m.group(2)) + 1) + NAMES[m.group(1)]


def f0(x: np.ndarray, lo: float = 100.0, hi: float = 1600.0) -> float:
    """Fundamental of a steady stretch by autocorrelation (first peak above 0.85 of the best)."""
    x = x - x.mean()
    n = len(x)
    ac = np.fft.irfft(np.abs(np.fft.rfft(x, 2 * n)) ** 2)[:n]
    a, b = int(SR / hi), int(SR / lo)
    seg = ac[a:b]
    best = seg.max()
    for k in range(1, len(seg) - 1):
        if seg[k] >= 0.85 * best and seg[k] >= seg[k - 1] and seg[k] >= seg[k + 1]:
            lag = a + k
            y0, y1, y2 = ac[lag - 1], ac[lag], ac[lag + 1]
            lag += 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2 + 1e-12)
            return SR / lag
    return SR / (a + int(np.argmax(seg)))


def segments_wind(x: np.ndarray, count: int) -> list[tuple[int, int]]:
    """Notes separated by silence: the `count` longest stretches above -40 dB of the loudest 10 ms."""
    hop = SR // 100
    e = np.abs(x[: len(x) // hop * hop]).reshape(-1, hop).max(1)
    on = 20 * np.log10(e / e.max() + 1e-9) > -40
    edges = np.flatnonzero(np.diff(np.r_[0, on.astype(int), 0]))
    segs = [(a, b) for a, b in zip(edges[::2], edges[1::2]) if b - a > 20]
    segs = sorted(sorted(segs, key=lambda s: s[1] - s[0])[-count:])
    return [(max(a * hop - hop, 0), min(b * hop + hop, len(x))) for a, b in segs]


def strikes_mallet(x: np.ndarray, gap_s: float = 1.5) -> list[tuple[int, int]]:
    """Struck notes that ring into each other: every strike (level jump over the quietest moment of the
    0.5 s before) at least `gap_s` apart, strongest first; which note each one is gets decided by pitch."""
    hop = 256
    env = np.sqrt((x[: len(x) // hop * hop].reshape(-1, hop).astype(np.float64) ** 2).mean(1)) + 1e-6
    look = int(0.5 * SR / hop)
    floor = np.array([env[max(k - look, 0): k].min() if k else env[0] for k in range(len(env))])
    ahead = np.r_[env[3:], np.repeat(env[-1], 3)]
    rise = np.where(ahead > env.max() * 10 ** (-35 / 20), np.log(ahead) - np.log(floor), 0)
    gap = int(gap_s * SR / hop)
    picks = []
    for k in np.argsort(rise)[::-1]:
        if rise[k] < 1.0:                                          # under about 9 dB: not a strike
            break
        if all(abs(k - p) > gap for p in picks):
            picks.append(k)
    order = sorted(picks)
    ends = {p: e for p, e in zip(order, order[1:] + [len(env)])}
    return [(max(p * hop - 2 * hop, 0), min(ends[p] * hop - 4 * hop, p * hop + 9 * SR)) for p in picks]


def peak_midi(y: np.ndarray, lo: int, hi: int) -> float:
    """Fractional MIDI pitch of the strongest spectral peak between lo-1 and hi+1 (a bar's fundamental)."""
    w = y * np.hanning(len(y))
    spec = np.abs(np.fft.rfft(w, 8 * len(w)))
    freqs = np.fft.rfftfreq(8 * len(w), 1 / SR)
    band = (freqs > 440 * 2 ** ((lo - 70) / 12)) & (freqs < 440 * 2 ** ((hi - 68) / 12))
    k = np.flatnonzero(band)[np.argmax(spec[band])]
    return 69 + 12 * np.log2(freqs[k] / 440)


def build(only: list[str] | None = None) -> int:
    bad = 0
    for inst, (prefix, kind, levels) in INSTRUMENTS.items():
        if only and inst not in only:
            continue
        for raw in sorted((BASE / "raw").glob(prefix + ".*")):
            m = re.fullmatch(re.escape(prefix) + r"\.(pp|mf|ff)\.([A-G]b?\d)([A-G]b?\d)\.aiff?", raw.name)
            if not m:
                continue
            layer, lo, hi = m.group(1), midi_of(m.group(2)), midi_of(m.group(3))
            x, sr = sf.read(raw, dtype="float32", always_2d=True)
            assert sr == SR
            x = signal.sosfiltfilt(signal.butter(2, 50, "highpass", fs=SR, output="sos"), x.mean(1)).astype(np.float32)
            count = hi - lo + 1
            out = BASE / inst / layer
            out.mkdir(parents=True, exist_ok=True)
            if kind == "wind":
                segs = [(lo + k, a, b) for k, (a, b) in enumerate(segments_wind(x, count))]
            else:                                                  # strongest strike of each pitch
                segs, seen = [], set()
                for a, b in strikes_mallet(x):
                    if b - a < SR:
                        continue
                    m2 = peak_midi(x[a + int(0.08 * SR): a + int(0.6 * SR)], lo, hi)
                    if abs(m2 - round(m2)) < 0.4 and lo <= round(m2) <= hi and round(m2) not in seen:
                        seen.add(round(m2))
                        segs.append((round(m2), a, b))
                if len(segs) != count:
                    print(f"{raw.name}: found {sorted(seen)}, {count - len(segs)} missing")
                segs.sort()
            for k, (midi, a, b) in enumerate(segs):
                y = x[a:b].copy()
                steady = y[int(0.25 * SR): int(0.85 * SR)] if kind == "wind" else y[int(0.05 * SR): int(0.45 * SR)]
                if kind == "wind":
                    cents = 1200 * np.log2(f0(steady) / (440 * 2 ** ((midi - 69) / 12)))
                else:
                    cents = 100 * (peak_midi(y[int(0.08 * SR): int(0.6 * SR)], lo, hi) - midi)
                cents = (cents + 600) % 1200 - 600                    # octave errors of the estimate are fine
                if abs(cents) > 70 or (kind == "wind" and len(segs) != count):
                    print(f"pitch? {raw.name} note {k} expected {midi}: {cents:+.0f} cents, {len(segs)}/{count} notes")
                    bad += 1
                elif abs(cents) > 3:                                   # retune to the exact note
                    r = 2 ** (-cents / 1200)
                    y = np.interp(np.arange(0, len(y) - 1, r), np.arange(len(y)), y).astype(np.float32)
                    steady = y[int(0.25 * SR): int(0.85 * SR)] if kind == "wind" else y[int(0.05 * SR): int(0.45 * SR)]
                # level: winds by their sustain, mallets by the strike, to the layer's level
                ref = steady if kind == "wind" else y[: int(0.15 * SR)]
                y *= 10 ** (levels[layer] / 20) * 0.25 / (np.sqrt(np.mean(ref ** 2)) + 1e-9)
                y[-256:] *= np.linspace(1, 0, 256, dtype=np.float32)
                sf.write(out / f"{midi}.wav", y, SR, subtype="FLOAT")
    print("all notes pitched as expected" if not bad else f"{bad} notes off")
    return 1 if bad else 0


@lru_cache(maxsize=None)
def bank(inst: str) -> dict[str, dict[int, np.ndarray]]:
    return {layer: {int(p.stem): sf.read(p, dtype="float32")[0] for p in (BASE / inst / layer).glob("*.wav")}
            for layer in LAYERS}


def attack_end(y: np.ndarray) -> int:
    """Where the tongued attack has settled: the envelope first reaches 60 % of its sustain."""
    hop = 220
    e = np.abs(y[: len(y) // hop * hop]).reshape(-1, hop).max(1)
    target = 0.6 * np.median(e[int(0.3 * SR / hop): int(1.0 * SR / hop)])
    k = int(np.argmax(e >= target))
    return min(k * hop, int(0.12 * SR))


def ctrl_curves(ctrl, spb: float, length: int, bend_range: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    """Pitch bend (semitones) and CC11 gain per sample from (beat, msg) controller events, held like MIDI."""
    bends, expr = [(0.0, 0.0)], [(0.0, 1.0)]
    for beat, msg in sorted(ctrl, key=lambda e: e[0]):
        t = beat * spb
        if msg[0] & 0xF0 == 0xE0:
            bends.append((t, ((msg[2] << 7 | msg[1]) - 8192) / 8192 * bend_range))
        elif msg[0] & 0xF0 == 0xB0 and msg[1] == 11:
            expr.append((t, (msg[2] / 127) ** 2))                  # the SF2 default: concave CC11 attenuation
    out = []
    for pts in (bends, expr):
        ts = np.array([p[0] for p in pts])
        vs = np.array([p[1] for p in pts], np.float32)
        idx = np.searchsorted(ts, np.arange(length) / SR, side="right") - 1
        curve = vs[np.clip(idx, 0, len(vs) - 1)]
        out.append(signal.sosfiltfilt(signal.butter(1, 40, fs=SR, output="sos"), curve).astype(np.float32))
    return out[0], out[1]


def pedal_ups(ctrl, spb: float) -> list[tuple[float, float]]:
    """Sustain pedal down/up spans in seconds."""
    spans, down = [], None
    for beat, msg in sorted(ctrl, key=lambda e: e[0]):
        if msg[0] & 0xF0 == 0xB0 and msg[1] == 64:
            if msg[2] >= 64 and down is None:
                down = beat * spb
            elif msg[2] < 64 and down is not None:
                spans.append((down, beat * spb))
                down = None
    return spans


def pick(inst: str, midi: int, vel: int) -> tuple[np.ndarray, float]:
    """The layer for this velocity and the nearest recorded note; returns (sample, transpose in semitones)."""
    layer = "pp" if vel < 56 else "mf" if vel < 92 else "ff"
    notes = bank(inst)[layer]
    near = min(notes, key=lambda p: (abs(p - midi), p))
    return notes[near], float(midi - near)


def hall(length: int, rt60: float, seed: int) -> np.ndarray:
    """Stereo hall impulse: early reflections, then noise decaying faster in the highs."""
    rng = np.random.default_rng(seed)
    n = int(rt60 * 1.3 * SR)
    t = np.arange(n) / SR
    ir = np.zeros((n, 2), np.float32)
    for (lo, hi), k in (((20, 500), 1.15), ((500, 2500), 1.0), ((2500, 7000), 0.7), ((7000, 16000), 0.4)):
        noise = rng.standard_normal((n, 2)).astype(np.float32)
        band = signal.sosfilt(signal.butter(2, (lo, hi), "bandpass", fs=SR, output="sos"), noise, axis=0)
        ir += (band * np.exp(-6.91 * t / (rt60 * k))[:, None]).astype(np.float32)
    pre = int(0.022 * SR)
    ir[:pre] = 0
    ir[pre: pre + int(0.03 * SR)] *= np.linspace(0, 1, int(0.03 * SR))[:, None]
    for d, g, side in ((0.011, 0.5, 0), (0.017, 0.42, 1), (0.026, 0.33, 0), (0.034, 0.3, 1), (0.047, 0.22, 0)):
        ir[int(d * SR), side] += g * 8
    return ir / np.sqrt(np.sum(ir ** 2) / 2)


def render_lead(inst: str, notes, ctrl, spb: float, length: int, send: int, rt60: float = 1.9,
                seed: int = 7) -> np.ndarray:
    """Render one stem's (start beat, dur beats, midi, vel) notes through the sampled instrument."""
    kind = INSTRUMENTS[inst][1]
    bend, expr = ctrl_curves(ctrl, spb, length)
    pedal = pedal_ups(ctrl, spb)
    dry = np.zeros(length, np.float32)
    rel = 0.09 if kind == "wind" else 0.35
    prev_end = -9.0
    for start, dur, midi, vel in sorted(notes):
        s, e = start * spb, (start + dur) * spb
        if kind == "mallet":                                         # the pedal holds the bar ringing
            e = max([e] + [up for down, up in pedal if down <= e <= up])
        y, trans = pick(inst, midi, vel)
        legato = kind == "wind" and -0.05 <= s - prev_end < 0.06
        offset = attack_end(y) if legato else 0
        xf = int(0.03 * SR) if legato else int(0.004 * SR)
        a = int(s * SR) - (xf if legato else 0)
        stop = min(int((e + rel) * SR), length)
        if a >= stop:
            continue
        span = np.arange(a, stop)
        ratio = 2 ** ((trans + bend[span]) / 12)
        pos = offset + np.cumsum(ratio) - ratio[0]
        if pos[-1] >= len(y) - 2:                                    # longer than the take: hold on its end
            span, pos = span[pos < len(y) - 2], pos[pos < len(y) - 2]
        x = np.interp(pos, np.arange(len(y)), y).astype(np.float32)
        g = np.ones(len(x), np.float32)
        g[:xf] = np.linspace(0, 1, min(xf, len(x)))[: len(g[:xf])]
        tail = np.clip((span / SR - e) / rel, 0, 1)
        g *= (1 - tail) ** 2 if kind == "wind" else np.exp(-5 * tail)
        g[-64:] *= np.linspace(1, 0, len(g[-64:]))
        vgain = (vel / 100) ** 0.8
        if kind == "wind" and legato:                                # fade the last note under the slur
            dry[a: a + xf] *= np.linspace(1, 0, len(dry[a: a + xf]))
            tail_from = a + xf
            dry[tail_from: tail_from + int(rel * SR)] = 0
        dry[span] += x * g * vgain
        prev_end = e
    dry *= expr
    wet = signal.fftconvolve(dry[:, None], hall(length, rt60, seed), axes=0)[:length]
    pan = 0.5
    st = np.stack([dry * np.sqrt(1 - pan) * 1.41, dry * np.sqrt(pan) * 1.41], 1)
    return (st + wet * (send / 127) * 0.55).astype(np.float32)


def harmon(x: np.ndarray) -> np.ndarray:
    """A Harmon mute on an open trumpet: thin lows, the nasal bump near 1.6 kHz, a dark top."""
    sos = np.vstack([signal.butter(2, 350, "highpass", fs=SR, output="sos"),
                     signal.butter(2, 6500, "lowpass", fs=SR, output="sos")])
    y = signal.sosfilt(sos, x, axis=0)
    bump = signal.sosfilt(signal.butter(2, (1100, 2300), "bandpass", fs=SR, output="sos"), y, axis=0)
    return (y + bump * (10 ** (5 / 20) - 1)).astype(np.float32)


def sampled_stem(inst: str, notes, ctrl, spb: float, ref: np.ndarray, send: int,
                 mute: bool = False) -> np.ndarray:
    """A song's stem through the sampled instrument, at the loudness of its General MIDI render `ref` so
    the song's mix gains still hold."""
    y = render_lead(inst, notes, ctrl, spb, len(ref), send)
    if mute:
        y = harmon(y)
    meter = pyln.Meter(SR)
    have, want = meter.integrated_loudness(y), meter.integrated_loudness(ref)
    if np.isfinite(have) and np.isfinite(want):
        y *= 10 ** ((want - have) / 20)
    return y.astype(np.float32)


if __name__ == "__main__":
    sys.exit(build(sys.argv[1:]))
