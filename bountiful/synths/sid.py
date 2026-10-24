"""Commodore 64 SID (6581 / 8580): one voice with its oscillator, ADSR and the chip's resonant multimode filter.

  wave        tri | saw | pulse | noise | tri+saw | pulse+saw | pulse+tri | pulse+tri+saw (combined waves, the oscillators'
              bits ANDed), or a macro of those names per frame: {"seq": ["noise", "pulse"], "loop": 1} (the drum trick)
  pw          pulse width 0-1; pwm = sweep depth, pwm_rate Hz (the slow PWM of every C64 lead)
  sync        hard sync: the oscillator restarts every cycle of the note, running `sync` times faster (1-8);
              sync_to / sync_time sweep it (the sync lead)
  ring        ring modulation: the triangle flips with a square `ring` times the note's frequency (bells, gongs)
  attack / decay / sustain / release        SID register values 0-15 (attack 0 = 2 ms ... 15 = 8 s; decay, release x3)
  filter      off | lp | bp | hp | notch | lp+bp | bp+hp; cutoff Hz, res 0-15, cutoff_env Hz on top falling over
              cutoff_decay s, key_track 0-1; cutoff may also be a macro in Hz per frame
  chip        6581 (darker, the filter drives) | 8580 (clean)
  arp / pitch / vibrato / glide / sweep        as in core.pitch; region pal | ntsc (frame rate)
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy import signal

from synths import core as C

ATTACK_MS = [2, 8, 16, 24, 38, 56, 68, 80, 100, 250, 500, 800, 1000, 3000, 5000, 8000]
WAVE_IDS = ["tri", "saw", "pulse", "noise", "tri+saw", "pulse+saw", "pulse+tri", "pulse+tri+saw"]

PRESETS = {
    "hubbard-lead": {"wave": "pulse", "pw": 0.35, "pwm": 0.25, "pwm_rate": 0.6, "attack": 0, "decay": 9, "sustain": 10,
                     "release": 6, "vibrato": 35, "vibrato_delay": 0.25, "vibrato_rate": 6.0, "level": 0.45},
    "galway-pluck": {"wave": "pulse", "pw": 0.25, "attack": 0, "decay": 6, "sustain": 0, "release": 5,
                     "filter": "lp", "cutoff": 600, "cutoff_env": 3500, "cutoff_decay": 0.12, "res": 8, "level": 0.5},
    "acid-bass": {"wave": "saw", "attack": 0, "decay": 7, "sustain": 6, "release": 3, "filter": "lp", "cutoff": 260,
                  "cutoff_env": 2200, "cutoff_decay": 0.15, "res": 12, "glide": 0.06, "level": 0.5},
    "fat-bass": {"wave": "pulse+saw", "pw": 0.5, "attack": 0, "decay": 8, "sustain": 9, "release": 3, "filter": "lp",
                 "cutoff": 700, "res": 4, "level": 0.55},
    "tri-bass": {"wave": "tri", "attack": 0, "decay": 9, "sustain": 12, "release": 2, "level": 0.6},
    "sync-lead": {"wave": "saw", "sync": 1.5, "sync_to": 4.0, "sync_time": 0.6, "attack": 1, "decay": 8, "sustain": 11,
                  "release": 6, "vibrato": 25, "vibrato_delay": 0.3, "level": 0.4},
    "ring-bell": {"wave": "tri", "ring": 2.76, "attack": 0, "decay": 10, "sustain": 0, "release": 10, "level": 0.55},
    "pwm-pad": {"wave": "pulse", "pw": 0.5, "pwm": 0.4, "pwm_rate": 0.35, "attack": 9, "decay": 9, "sustain": 12,
                "release": 10, "filter": "lp", "cutoff": 1800, "res": 3, "level": 0.4},
    "arp-chord": {"wave": "pulse", "pw": 0.4, "arp": {"seq": [0, 4, 7], "loop": 0}, "attack": 0, "decay": 9,
                  "sustain": 10, "release": 5, "level": 0.42},
    "minor-arp": {"wave": "pulse", "pw": 0.4, "arp": {"seq": [0, 3, 7], "loop": 0}, "attack": 0, "decay": 9,
                  "sustain": 10, "release": 5, "level": 0.42},
    "buzz-lead": {"wave": "pulse+tri", "pw": 0.4, "attack": 0, "decay": 8, "sustain": 11, "release": 5,
                  "vibrato": 30, "vibrato_delay": 0.2, "level": 0.6},
    "flute": {"wave": "tri", "attack": 5, "decay": 8, "sustain": 12, "release": 7, "vibrato": 20,
              "vibrato_delay": 0.35, "vibrato_rate": 5.0, "level": 0.6},
    "brass": {"wave": "saw", "attack": 4, "decay": 8, "sustain": 10, "release": 5, "filter": "lp", "cutoff": 500,
              "cutoff_env": 2500, "cutoff_decay": 0.35, "res": 2, "vibrato": 15, "vibrato_delay": 0.35, "level": 0.45},
    "laser": {"wave": "pulse", "pw": 0.5, "pitch": {"seq": [2400, 1800, 1200, 600, 0, -600, -1200, -1800, -2400]},
              "attack": 0, "decay": 6, "sustain": 0, "release": 4, "level": 0.45},
    "kick": {"wave": {"seq": ["noise", "pulse", "tri", "tri", "tri"], "loop": 4}, "pw": 0.5,
             "pitch": {"seq": [1200, 600, 0, -800, -1600, -2400, -3000]}, "attack": 0, "decay": 6, "sustain": 0,
             "release": 0, "level": 0.7},
    "snare": {"wave": {"seq": ["noise", "pulse", "noise"], "loop": 2}, "pw": 0.5,
              "pitch": {"seq": [1900, 400, 2800]}, "attack": 0, "decay": 6, "sustain": 0, "release": 0, "level": 0.55},
    "hat": {"wave": "noise", "pitch": 2400, "attack": 0, "decay": 2, "sustain": 0, "release": 0, "filter": "hp",
            "cutoff": 6000, "level": 0.4},
}


def _rate_s(v, scale=1.0) -> float:
    return ATTACK_MS[int(np.clip(v, 0, 15))] / 1000 * scale


def _adsr(n: int, dur: float, p: dict) -> np.ndarray:
    """SID envelope: linear attack, exponential-looking decay and release (the chip's piecewise counter), times from
    the register tables."""
    a, d, r = _rate_s(p.get("attack", 0)), _rate_s(p.get("decay", 8), 3), _rate_s(p.get("release", 6), 3)
    s = int(np.clip(p.get("sustain", 10), 0, 15)) / 15
    t = np.arange(n) / C.SR
    env = np.where(t < a, t / a, s + (1 - s) * np.exp(-np.maximum(t - a, 0) * 4.6 / d))
    held = float(env[min(int(dur * C.SR), n - 1)])
    return np.where(t < dur, env, held * np.exp(-np.maximum(t - dur, 0) * 4.6 / max(r, 0.004)))


@lru_cache(maxsize=None)
def _noise_seq() -> np.ndarray:
    """The SID's noise: 8 bits of a 23-bit LFSR, a new value as bit 19 of the oscillator steps (16 per cycle)."""
    reg, out = 0x7FFFF8, np.empty(1 << 16)
    for i in range(len(out)):
        bit = ((reg >> 22) ^ (reg >> 17)) & 1
        reg = ((reg << 1) | bit) & 0x7FFFFF
        v = (((reg >> 22) & 1) << 7 | ((reg >> 20) & 1) << 6 | ((reg >> 16) & 1) << 5 | ((reg >> 13) & 1) << 4 |
             ((reg >> 11) & 1) << 3 | ((reg >> 7) & 1) << 2 | ((reg >> 4) & 1) << 1 | ((reg >> 2) & 1))
        out[i] = v / 127.5 - 1
    return out


def _waves(ph: np.ndarray, pw: np.ndarray, ring_sign: np.ndarray | None) -> dict:
    """The oscillator's 12-bit outputs at phase ph (oversampled, so plain arithmetic is clean enough)."""
    acc = (ph * 4096).astype(np.int64) & 0xFFF
    saw = acc
    tri = np.where(acc < 2048, acc * 2, (4095 - acc) * 2) & 0xFFF
    if ring_sign is not None:                                     # ring mod: the triangle's fold follows the modulator
        tri = np.where(ring_sign, 4095 - tri, tri)
    pul = np.where(acc >= (pw * 4096).astype(np.int64), 0xFFF, 0)
    return {"tri": tri, "saw": saw, "pulse": pul, "tri+saw": tri & saw, "pulse+saw": pul & saw,
            "pulse+tri": pul & tri, "pulse+tri+saw": pul & tri & saw}


def _wave_index(spec, nf: int, gate: int) -> np.ndarray:
    if isinstance(spec, str):
        return np.full(nf, WAVE_IDS.index(spec))
    seq = {"seq": [WAVE_IDS.index(w) for w in spec["seq"]], "loop": spec.get("loop"), "release": spec.get("release")}
    return C.macro(seq, nf, gate).astype(int)


def note(midi, vel, dur, p, rng, from_midi=None) -> np.ndarray:
    rate = C.PAL if p.get("region", "pal") == "pal" else C.NTSC
    gate = int(np.ceil(dur * rate))
    rel_s = _rate_s(p.get("release", 6), 3)
    n = int((dur + min(rel_s, 6.0)) * C.SR) + 64
    nf = int(n * rate / C.SR) + 2
    m = C.pitch(midi, n, p, rate, gate, from_midi)
    f = C.hz(m)
    over = 8 if f.max() > 1200 else 4
    fo = np.repeat(f, over)
    no = len(fo)
    t = np.arange(no) / (C.SR * over)

    ph = np.cumsum(fo / (C.SR * over)) % 1.0
    if p.get("sync"):
        ratio = np.full(no, float(p["sync"]))
        if p.get("sync_to") is not None:
            ratio = p["sync"] + (p["sync_to"] - p["sync"]) * np.clip(t / max(p.get("sync_time", 0.5), 1e-3), 0, 1)
        osc_ph = (ph * ratio) % 1.0                               # restarts each time the note's own cycle wraps
        dto = fo / (C.SR * over) * ratio
    else:
        osc_ph, dto = ph, fo / (C.SR * over)
    pw = np.full(no, float(p.get("pw", 0.5)))
    if p.get("pwm"):
        lfo = 2 * np.abs((t * p.get("pwm_rate", 0.5) + 0.25) % 1.0 - 0.5) * 2 - 1
        pw = pw + p["pwm"] * 0.5 * lfo
    pw = np.clip(pw, 0.02, 0.98)
    ring = ((ph * p["ring"]) % 1.0) >= 0.5 if p.get("ring") else None

    W = _waves(osc_ph, pw, ring)
    idx = np.repeat(C.per_sample(_wave_index(p.get("wave", "pulse"), nf, gate).astype(float), n, rate), over)[:no]
    y = np.zeros(no)
    for k, name in enumerate(WAVE_IDS):
        sel = idx == k
        if not sel.any():
            continue
        if name == "noise":
            seq = _noise_seq()
            steps = (np.cumsum(fo * 16 / (C.SR * over)) + rng.integers(len(seq))).astype(np.int64) % len(seq)
            y[sel] = seq[steps[sel]]
        else:
            y[sel] = W[name][sel] / 2047.5 - 1
            if name in ("saw", "pulse"):                          # band-limit the plain waves' edges (combined ones stay raw)
                edge = -C.blep(osc_ph[sel], dto[sel])
                if name == "pulse":
                    edge = edge + C.blep((osc_ph[sel] - pw[sel]) % 1.0, dto[sel])
                y[sel] += edge
    y = signal.resample_poly(y, 1, over)[:n]

    if p.get("filter", "off") != "off":
        tn = np.arange(n) / C.SR
        cut = p.get("cutoff", 1200)
        cut = (C.per_sample(C.macro(cut, nf, gate), n, rate) if isinstance(cut, (dict, list)) else np.full(n, float(cut)))
        cut = cut * (C.hz(midi) / 261.6) ** p.get("key_track", 0.0)
        if p.get("cutoff_env"):
            cut = cut + p["cutoff_env"] * (0.5 + 0.5 * vel) * np.exp(-tn / max(p.get("cutoff_decay", 0.2), 1e-3))
        chip6581 = str(p.get("chip", "6581")) == "6581"
        cut = np.clip(cut * (0.8 if chip6581 else 1.0), 30, 12000)
        q = 0.707 + int(np.clip(p.get("res", 0), 0, 15)) / 15 * (3.3 if chip6581 else 2.6)
        parts = p["filter"].split("+") if p["filter"] != "notch" else ["lp", "hp"]
        kinds = {"lp": "lowpass", "bp": "bandpass", "hp": "highpass"}
        y = sum(C.biquad(y, kinds[k], cut, q) for k in parts)
        if chip6581:
            y = np.tanh(y * 1.4) / np.tanh(1.4)
    y = y * _adsr(n, dur, p) * (0.45 + 0.55 * vel)
    y = C.onepole(y, 16.0, high=True)
    return C.finish(y * 0.8, p)
