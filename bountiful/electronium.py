#!/usr/bin/env python3
"""The Electronium: Bountiful's composing-performing machine, after Raymond Scott's (1959-1994).

Scott's machine was "guided, not played": a console of pushbuttons and switches over a 12-channel sequencer, each
channel its own analog tone generator with accent, tremolo and reverb; a bassline sequencer and a rhythm generator
built in; preset rhythms that combine into "millions of permutations"; a recorder that keeps the settings and plays
them back. "It thinks of 200 things every day. You keep the ones that are good." This one works the same way:

  bounty        the seed. Every random number is drawn up front, per step and per subsystem, from the Bounty alone:
                the same Bounty gives the same terrain, the knobs only set thresholds and weights over it, so turning a
                knob reshapes the music instead of re-rolling it
  clock matrix  one master clock (16ths) into dividers; logic gates over them make every channel's triggers:
                  cN    fires every N steps on the grid        cN+k  the same, k steps late
                  rN    every N steps at the Bounty's phase    pN    rhythm preset N (1-12, the preset buttons)
                  &  AND   |  OR   ^  XOR   ~  NOT   ( )
  channels      up to 12, all playing at once, each with a role, its own gate, register, density and tone generator:
                  melody    the Markov walk over the scale, its themes and behaviours (below)
                  harmony   follows another channel by an interval button (third_below, sixth_below, fifth_below,
                            octave_below, third_above, fourth_above, canon, contrary, root_on_downbeat)
                  bass      the bassline sequencer: roots on the chord changes, fifths, octaves, approach notes
                  ostinato  a stepping sequence of chord tones, `length` cells long, one cell per trigger, so it
                            phases against the bar (5 cells over 8ths come round every 5 beats); the LFSR rewrites cells
                  counter   a slow second line in contrary motion, keeping off the melody's notes
                With no [[channels]], the machine has its two classic ones: a melody (lead) and a harmony (sidekick).
  thinking      before it plays, the melody channel thinks of `think` (200) two-bar ideas from the terrain and a
                critic scores them (shape, range, steps and leaps, a long last note, call and answer, one high point).
                It keeps the best `keep` (3) or the idea numbers you list (`keep = [17, 42, 108]`, see --ideas).
                Each section of the song gets its own kept idea as its theme, so a theme comes back with its section.
  phrase        the 8-bar plan the melody follows in each section: theme (the section's idea), answer (a behaviour on
                the last bar), free (the walk), cadence (the walk, landing on the chord root)
  behaviours    repeat, reverse (retrograde), transpose, invert, ornament: what an answer or a free bar does
  register      a ring buffer of the last notes. Freeze & Populate captures the last 8 or 16 into a loop, transposes,
                inverts or mutates it (a 16-bit LFSR picks which cell, Turing-machine style); Modify adds step offsets
  recorder      [[moves]]: the operator's button presses and knob turns, played back: at a bar set any knob (or a
                channel's: gate, density, mute, transpose, register ...), or ramp it to a value by `to_bar`
  tones         each channel's tone generator (electronium_voice.py): oscillator, noise, filter, fixed envelopes,
                accent, tremolo, drift, glide; reverb is its plate send

    $PY bountiful/electronium.py --bounty 7 [--bars 16] [--patch electronium.toml]    the terrain, as text
    $PY bountiful/electronium.py --bounty 7 --ideas [20]                               what it thought of, best first
In a genre: [melody] writer = "electronium", drums = "electronium" (optional) and an [electronium] table (see DEFAULT).
"""
from __future__ import annotations

import argparse
import copy
import math
import tomllib
import zlib
from collections import Counter, deque
from functools import reduce
from pathlib import Path

import numpy as np

SCALES = {"major": (0, 2, 4, 5, 7, 9, 11), "minor": (0, 2, 3, 5, 7, 8, 10), "dorian": (0, 2, 3, 5, 7, 9, 10),
          "phrygian": (0, 1, 3, 5, 7, 8, 10), "lydian": (0, 2, 4, 6, 7, 9, 11), "mixolydian": (0, 2, 4, 5, 7, 9, 10),
          "harmonic_minor": (0, 2, 3, 5, 7, 8, 11), "minor_pent": (0, 3, 5, 7, 10), "major_pent": (0, 2, 4, 7, 9),
          "blues": (0, 3, 5, 6, 7, 10), "whole_tone": (0, 2, 4, 6, 8, 10), "chromatic": tuple(range(12))}
NOTE = {n: i for i, n in enumerate(("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"))} | \
       {"Db": 1, "Eb": 3, "Gb": 6, "Ab": 8, "Bb": 10}
INTERVALS = ("repeat", "step", "third", "fourth", "fifth", "sixth", "octave")
DEG = (0, 1, 2, 3, 4, 5, 7)                       # each interval class as scale steps
SIDEKICK = ("off", "fifth_below", "third_below", "root_on_downbeat", "contrary", "canon")
HARMONY = SIDEKICK + ("sixth_below", "octave_below", "third_above", "fourth_above")
BEHAVIOURS = ("repeat", "reverse", "transpose", "invert", "ornament")
ROLES = ("melody", "harmony", "bass", "ostinato", "counter")
PHRASE_TOKENS = ("theme", "answer", "free", "cadence")
# the preset buttons: twelve rhythms, combined in gates as p1 ... p12
RHYTHMS = {1: "c4", 2: "c8 | c8+3 | c8+6", 3: "c2", 4: "c4+2", 5: "c16 | c16+6 | c16+10", 6: "c3",
           7: "c16 | c16+3 | c16+6 | c16+10 | c16+12", 8: "c2 & ~c8+4", 9: "c6 | c4+2", 10: "c5",
           11: "c8+2 | c16+14 | c16", 12: "c1 & ~c4"}
RHYTHM_NAMES = {1: "quarters", 2: "tresillo", 3: "eighths", 4: "offbeats", 5: "two-step", 6: "dotted 8ths",
                7: "son clave", 8: "8ths round the backbeat", 9: "sixes on the offbeats", 10: "fives", 11: "pushes", 12: "16ths off the beat"}
# the tone generators' presets (electronium_voice.py knobs); a channel's tone is one of these names, or a table over "base"
TONES = {
    "scott-lead": {"wave": "square", "pwm": 0.15, "osc2": 0.3, "detune": 6, "cutoff": 1700, "env_amount": 3600, "res": 1.6,
                   "attack": 0.005, "decay": 0.3, "sustain": 0.6, "release": 0.15, "vibrato": 12, "drift": 3, "glide": 0.04, "accent": 0.5},
    "pulse-sidekick": {"wave": "pulse", "pw": 0.25, "cutoff": 2200, "env": "pluck", "tremolo": 0.15, "tremolo_rate": 6.0, "drift": 4, "accent": 0.3},
    "bloop": {"wave": "triangle", "env": "perc", "decay": 0.16, "cutoff": 7000, "env_amount": 0, "drift": 2, "level": 0.6},
    "bass-sequencer": {"wave": "saw", "sub": 0.5, "cutoff": 420, "env_amount": 1800, "filter_decay": 0.12, "res": 2.4, "attack": 0.002,
                       "decay": 0.25, "sustain": 0.5, "release": 0.06, "accent": 0.7, "glide": 0.03, "key_track": 0.3},
    "ostinato-bell": {"wave": "triangle", "osc2": 0.35, "detune": 1200, "env": "perc", "decay": 0.28, "cutoff": 6000, "env_amount": 2000, "level": 0.55},
    "counter-reed": {"wave": "pulse", "pw": 0.15, "env": "swell", "cutoff": 1400, "env_amount": 600, "tremolo": 0.25, "tremolo_rate": 4.5, "vibrato": 8, "drift": 3},
}
ROLE_DEFAULTS = {     # what a channel of each role starts from
    "melody": {"tone": "scott-lead", "mix": {"gain_db": -8.0, "hp": 200, "reverb": 0.2, "echo": 0.2}},
    "harmony": {"follow": "lead", "interval": "third_below", "tone": "pulse-sidekick", "mix": {"gain_db": -12.0, "pan": -0.25, "hp": 180, "reverb": 0.25}},
    "bass": {"gate": "p5 | (r7 & c2 & ~c4)", "register": [28, 47], "density": 0.9, "legato": 0.8, "tone": "bass-sequencer",
             "mix": {"gain_db": -6.0, "hp": 28, "mono": True}},
    "ostinato": {"gate": "c2", "length": 5, "register": [60, 84], "density": 1.0, "legato": 0.5, "tone": "ostinato-bell",
                 "mix": {"gain_db": -16.0, "pan": 0.3, "hp": 300, "reverb": 0.3, "echo": 0.15}},
    "counter": {"gate": "c8 | (r16 & c4)", "register": [55, 74], "density": 0.85, "legato": 0.95, "tone": "counter-reed",
                "mix": {"gain_db": -15.0, "pan": -0.35, "hp": 180, "reverb": 0.35}},
}

DEFAULT = {
    "bounty": 1,                 # the Bounty Selector: an integer (or any word)
    "scale": "key",              # key (the song's own scale) or one of SCALES
    "root": "key",               # key or a note name (C, Eb ...)
    "register": [60, 84],
    "density": 0.75,             # activity: the share of gate triggers that play
    "mutation": 0.15,            # how fast the interval weights drift (and the ostinato's cells)
    "clocks": [2, 3, 4, 7, 8],   # the dividers that make the accents (and what lcm is reported for)
    "gate": "(c2 & ~r3) | (r7 ^ c4) | c8",
    "intervals": {"repeat": 0.25, "step": 1.0, "third": 0.8, "fourth": 0.45, "fifth": 0.55, "sixth": 0.2, "octave": 0.08},
    "up": 0.5,                   # up/down bias of each jump
    "gravity": 0.6,              # pull to chord tones on strong pulses
    "accent": 0.5,               # how much clock coincidence lifts velocity
    "legato": 0.85,              # a note lasts this share of the time to the next trigger ...
    "max_steps": 6,              # ... up to this many 16ths
    "behaviours": {"repeat": 0.16, "reverse": 0.07, "transpose": 0.1, "invert": 0.06, "ornament": 0.1},
    "think": 200,                # ideas the melody thinks of before playing (0: no themes, the walk alone)
    "keep": 3,                   # how many to keep (the critic's best), or a list of idea numbers
    "phrase": ["theme", "theme", "answer", "answer", "theme", "theme", "free", "cadence"],
    "memory": 16,                # the ring buffer
    "modify": 0.0,               # step-quantized offsets on frozen loops (0-1)
    "freeze": [],                # [{bar = 17, notes = 8, bars = 4, transform = "transpose", amount = 2, modify = 0.3}]
    "sidekick": "fifth_below",   # the classic second channel (when there are no [[channels]])
    "sidekick_register": [43, 67],
    "canon_beats": 2.0,
    "channels": [],              # [[channels]] name, role, gate, register, density, tone, mix ... (see ROLE_DEFAULTS)
    "moves": [],                 # [[moves]] bar, to_bar (a ramp), channel, set = { knob = value }, freeze = {...}
    "drums": {                   # drum style "electronium": each layer is a gate over the same clocks
        "kick": {"gate": "c8 | (r7 & c2 & ~c4)", "density": 0.9},
        "snare": {"gate": "c8+4", "density": 1.0},
        "clap": {"gate": "c8+4 & r3", "density": 0.8},
        "hat": {"gate": "c2 | r3", "density": 0.7, "vel": 0.55},
        "open": {"gate": "c8+6 & ~r5", "density": 0.5, "vel": 0.6},
        "rim": {"gate": "r5 & ~c2", "density": 0.6, "vel": 0.5},
        "syntom_hi": {"gate": "r7 & r3", "density": 0.5, "vel": 0.6},
        "syntom_lo": {"gate": "r11 & ~c4", "density": 0.5, "vel": 0.6},
    },
}
KNOBS = ("density", "mutation", "gravity", "up", "accent", "legato", "max_steps", "modify", "gate", "register", "intervals", "behaviours")


def patch(*layers: dict | None) -> dict:
    """DEFAULT with each layer merged over it (tables merge one level deep, lists are replaced)."""
    p = copy.deepcopy(DEFAULT)
    for lay in layers:
        for k, v in (lay or {}).items():
            if isinstance(v, dict) and isinstance(p.get(k), dict):
                if k == "drums":
                    for d, dv in v.items():
                        p["drums"][d] = {**p["drums"].get(d, {}), **dv}
                else:
                    p[k] = {**p[k], **v}
            else:
                p[k] = copy.deepcopy(v)
    return p


def channels(p: dict) -> list[dict]:
    """The machine's channels, each filled in from its role's defaults. No [[channels]]: lead + sidekick."""
    raw = p.get("channels") or [{"name": "lead", "role": "melody", "tone": None},
                                {"name": "sidekick", "role": "harmony", "follow": "lead", "interval": p["sidekick"],
                                 "register": p["sidekick_register"], "tone": None}]
    out = []
    for i, c in enumerate(raw[:12]):
        role = c.get("role", "melody")
        if role not in ROLES:
            raise ValueError(f"channel {c.get('name', i + 1)}: role {role!r} is not one of {', '.join(ROLES)}")
        d = copy.deepcopy(ROLE_DEFAULTS[role])
        ch = {**d, **copy.deepcopy(c), "role": role, "name": c.get("name") or f"el{i + 1}", "n": i}
        ch["mix"] = {**d.get("mix", {}), **c.get("mix", {})}
        if role == "harmony" and ch.get("interval", "third_below") not in HARMONY:
            raise ValueError(f"channel {ch['name']}: interval {ch['interval']!r} is not one of {', '.join(HARMONY)}")
        out.append(ch)
    if p.get("sidekick") == "off" and not p.get("channels"):
        out = out[:1]
    names = [c["name"] for c in out]
    if len(set(names)) < len(names):
        raise ValueError(f"channel names must differ: {names}")
    return out


def tone(ch: dict) -> dict | None:
    """A channel's tone generator settings (electronium_voice.py), or None if the song's own sound plays it."""
    t = ch.get("tone")
    if not t:
        return None
    if isinstance(t, str):
        if t not in TONES:
            raise ValueError(f"channel {ch['name']}: no tone {t!r} (tones: {', '.join(TONES)})")
        return dict(TONES[t])
    return {**TONES.get(t.get("base", ""), {}), **{k: v for k, v in t.items() if k != "base"}}


def note_pc(name) -> int:
    """'C', 'eb', 'F#' -> pitch class."""
    s = str(name).strip()
    return NOTE[s[0].upper() + s[1:].replace("B", "b")]


def bounty_int(b) -> int:
    """The Bounty as an integer: numbers as they are, words by their CRC (so 'C-Lizzy' is a seed too)."""
    try:
        return int(b)
    except (TypeError, ValueError):
        return zlib.crc32(str(b).encode())


def _crc(s: str) -> int:
    return zlib.crc32(s.encode())


# ------------------------------------------------------------------ the clock matrix

class Gate:
    """A logic expression over clock dividers and rhythm presets, evaluated for every step at once.
    Precedence: ~ then & then ^ then |."""

    def __init__(self, expr: str, _depth: int = 0):
        self.expr = str(expr)
        self.depth = _depth
        self.toks = self._lex(self.expr)
        self.divs: set[int] = {int(t[1]) for t in self.toks if t[0] == "clk"}
        for t in self.toks:
            if t[0] == "preset":
                self.divs |= Gate(RHYTHMS[t[1]], _depth + 1).divs

    def _lex(self, s):
        toks, i = [], 0
        while i < len(s):
            ch = s[i]
            if ch.isspace():
                i += 1
            elif ch in "&|^~!()":
                toks.append(("op", "~" if ch == "!" else ch))
                i += 1
            elif ch in "crp" and i + 1 < len(s) and s[i + 1].isdigit():
                j = i + 1
                while j < len(s) and s[j].isdigit():
                    j += 1
                n, k = s[i + 1:j], 0
                if ch == "p":
                    if int(n) not in RHYTHMS:
                        raise ValueError(f"gate {s!r}: preset p{n} doesn't exist (p1-p{len(RHYTHMS)})")
                    if self.depth > 2:
                        raise ValueError(f"gate {s!r}: presets nest too deep")
                    toks.append(("preset", int(n)))
                    i = j
                    continue
                if ch == "c" and j < len(s) and s[j] == "+":
                    m = j + 1
                    while m < len(s) and s[m].isdigit():
                        m += 1
                    k, j = int(s[j + 1:m] or 0), m
                if int(n) < 1:
                    raise ValueError(f"gate {s!r}: divider must be 1 or more")
                toks.append(("clk", n, ch, k))
                i = j
            elif ch in "01":
                toks.append(("const", ch == "1"))
                i += 1
            else:
                raise ValueError(f"gate {s!r}: unexpected {ch!r} (use cN, cN+k, rN, pN, &, |, ^, ~, parentheses)")
        return toks

    def eval(self, steps: np.ndarray, phase) -> np.ndarray:
        toks, pos = self.toks, [0]

        def peek():
            return toks[pos[0]] if pos[0] < len(toks) else None

        def take(op=None):
            t = peek()
            if t is None or (op and t != ("op", op)):
                raise ValueError(f"gate {self.expr!r}: expected {op or 'a clock'}")
            pos[0] += 1
            return t

        def atom():
            t = take()
            if t == ("op", "~"):
                return ~atom()
            if t == ("op", "("):
                v = orx()
                take(")")
                return v
            if t[0] == "const":
                return np.full(len(steps), t[1])
            if t[0] == "preset":
                return Gate(RHYTHMS[t[1]], self.depth + 1).eval(steps, phase)
            if t[0] != "clk":
                raise ValueError(f"gate {self.expr!r}: unexpected {t[1]!r}")
            n = int(t[1])
            ph = phase(n) if t[2] == "r" else t[3]
            return (steps - ph) % n == 0

        def binary(sub, op):
            def f():
                v = sub()
                while peek() == ("op", op):
                    take(op)
                    w = sub()
                    v = {"&": np.logical_and, "^": np.logical_xor, "|": np.logical_or}[op](v, w)
                return v
            return f
        orx = binary(binary(binary(atom, "&"), "^"), "|")
        v = orx()
        if peek() is not None:
            raise ValueError(f"gate {self.expr!r}: unexpected {peek()[1]!r}")
        return v


def lcm(ns) -> int:
    return reduce(lambda a, b: a * b // math.gcd(a, b), [int(n) for n in ns], 1)


class LFSR:
    """A 16-bit Galois LFSR (taps 16, 14, 13, 11): the shift register that decides which cell of a loop mutates."""

    def __init__(self, seed: int):
        self.s = (seed & 0xFFFF) or 0xACE1

    def step(self) -> int:
        lsb = self.s & 1
        self.s >>= 1
        if lsb:
            self.s ^= 0xB400
        return self.s

    def bits(self, n: int) -> list[bool]:
        return [bool(self.step() & 1) for _ in range(n)]


# ------------------------------------------------------------------ thinking: ideas and the critic

def rhythm_sig(cells) -> tuple:
    return tuple(c[0] for c in cells)


def critic(cells: list[tuple]) -> tuple[float, dict]:
    """Score a two-bar idea [(step 0-31, dur beats, degree, vel)]: what a composer listens for in a phrase."""
    n = len(cells)
    if n < 3:
        return -9.0, {"notes": n}
    degs = [c[2] for c in cells]
    moves = [b - a for a, b in zip(degs, degs[1:])]
    sc = {}
    sc["notes"] = 1.0 if 5 <= n <= 12 else 1.0 - 0.25 * min(abs(n - 5), abs(n - 12))
    rng_ = max(degs) - min(degs)
    sc["range"] = 1.0 if 3 <= rng_ <= 8 else 0.3 if rng_ in (2, 9) else -0.5
    steps = sum(abs(m) <= 1 for m in moves) / len(moves)
    sc["steps"] = 1.0 if 0.5 <= steps <= 0.85 else 0.4 if steps > 0.85 else steps
    leaps = [i for i, m in enumerate(moves) if abs(m) >= 3]
    sc["gap fill"] = 0.5 * (sum(1 for i in leaps if i + 1 < len(moves) and moves[i + 1] * moves[i] < 0) / len(leaps)) if leaps else 0.25
    last = cells[-1]
    sc["ending"] = (0.5 if last[1] >= 0.5 else 0.0) + (0.5 if degs[-1] % 7 in (0, 2, 4) else 0.0)
    a = {c[0] for c in cells if c[0] < 16}
    b = {c[0] - 16 for c in cells if c[0] >= 16}
    sim = len(a & b) / max(1, len(a | b))
    sc["call and answer"] = 1.0 if 0.35 <= sim <= 0.8 else 0.5 if sim > 0.8 else sim
    sc["one high point"] = 0.5 if degs.count(max(degs)) == 1 else 0.0
    off = sum(1 for c in cells if c[0] % 2) / n
    sc["syncopation"] = 0.5 if 0.1 <= off <= 0.4 else 0.0
    sc["starts"] = 0.5 if cells[0][0] <= 2 else 0.0
    return round(sum(sc.values()), 3), sc


def think(p: dict) -> list[dict]:
    """The ideas the melody thinks of: `think` two-bar phrases in scale degrees, from the Bounty, scored by the critic.
    The knobs shape them (interval weights, up/down bias, legato), the terrain picks."""
    bounty = bounty_int(p["bounty"])
    w = np.array([max(1e-3, float(p["intervals"].get(k, 0))) for k in INTERVALS])
    w = w / w.sum()
    ideas = []
    for i in range(int(p.get("think", 0))):
        r = np.random.default_rng([bounty, _crc("ideas"), i])
        k = int(r.integers(1, 3))
        ps = sorted(int(x) for x in r.choice(list(RHYTHMS), k, replace=False))
        op = " | " if k == 1 or r.random() < 0.7 else " & "
        trig = Gate(op.join(f"p{x}" for x in ps)).eval(np.arange(32), lambda n: 0)
        if trig.sum() < 4:
            trig = Gate(" | ".join(f"p{x}" for x in ps)).eval(np.arange(32), lambda n: 0)
        dens = r.uniform(0.45, 0.9)
        on = [s for s in range(32) if trig[s] and (r.random() < dens or s == 0)]
        if not any(s <= 3 for s in on):
            on = [0] + on
        echo = r.random() < 0.55                       # bar 2 answers bar 1's rhythm
        if echo:
            first = [s for s in on if s < 16]
            on = first + [s + 16 for s in first if r.random() < 0.8] + [s for s in on if s >= 16 and r.random() < 0.25]
            on = sorted(set(on))
        deg, degs = 0, []
        for j, s in enumerate(on):
            if j:
                cls = int(r.choice(len(INTERVALS), p=w))
                step = DEG[cls] * (1 if r.random() < float(p["up"]) else -1)
                if abs(deg + step) > 7:
                    step = -step
                deg += step
            degs.append(deg)
        if echo and r.random() < 0.5:                  # a sequence: bar 2 repeats bar 1's contour a step or two away
            shift = int(r.choice([-2, -1, 1, 2]))
            first = {s: d for s, d in zip(on, degs) if s < 16}
            degs = [first[s - 16] + shift if s >= 16 and (s - 16) in first else d for s, d in zip(on, degs)]
        cells = []
        for j, s in enumerate(on):
            gap = (on[j + 1] if j + 1 < len(on) else 32) - s
            dur = min(gap, 8) * 0.25 * (float(p["legato"]) if j + 1 < len(on) else 1.0)
            v = 0.7 + 0.15 * (s % 4 == 0) + 0.1 * (s % 8 == 0)
            cells.append((s, round(dur, 3), degs[j], round(v, 3)))
        score, parts = critic(cells)
        ideas.append({"n": i, "cells": cells, "score": round(score + r.random() * 0.01, 3), "parts": parts, "rhythm": " | ".join(RHYTHM_NAMES[x] for x in ps)})
    return ideas


def kept(p: dict, ideas: list[dict] | None = None) -> list[dict]:
    """The ideas the machine keeps: the idea numbers in `keep`, or the critic's best `keep` that differ from each other."""
    ideas = think(p) if ideas is None else ideas
    if not ideas:
        return []
    k = p.get("keep", 3)
    if isinstance(k, (list, tuple)):
        bad = [x for x in k if not 0 <= int(x) < len(ideas)]
        if bad:
            raise ValueError(f"keep {bad}: the machine thought of ideas 0-{len(ideas) - 1}")
        return [ideas[int(x)] for x in k]
    out, seen = [], set()
    for idea in sorted(ideas, key=lambda d: (-d["score"], d["n"])):
        sig = (rhythm_sig(idea["cells"]), tuple(c[2] for c in idea["cells"]))
        if rhythm_sig(idea["cells"]) in {s[0] for s in seen}:
            continue
        seen.add(sig)
        out.append(idea)
        if len(out) >= int(k):
            break
    return out


def notation(cells) -> str:
    row = ["."] * 32
    for c in cells:
        row[c[0]] = "x"
    return "".join(row[:16]) + "|" + "".join(row[16:]) + "  " + " ".join(f"{c[2]:+d}" for c in cells)


# ------------------------------------------------------------------ the machine

class Machine:
    """One song's Electronium: the terrain for `bars` bars, drums per bar, then every channel over the arrangement."""

    def __init__(self, p: dict, bars: int, swing: float = 0.5, bpm: float = 120, humanize_ms: float = 0.0):
        self.p = p
        self.bounty = bounty_int(p["bounty"])
        self.bars, self.S = bars, bars * 16
        self.swing, self.bpm, self.hum_ms = swing, bpm, humanize_ms
        self.steps = np.arange(self.S)
        self.clocks = [int(c) for c in p["clocks"]]
        self.chans = channels(p)
        self._phase: dict[int, int] = {}
        self._drums: dict[str, tuple] = {}
        self._trig: dict[str, np.ndarray] = {}
        self._at: dict = {}
        self._drift: dict = {}
        self.log: list[str] = []
        self.moves = sorted(p.get("moves", []), key=lambda m: m["bar"])
        for m in self.moves:
            if m.get("channel") and m["channel"] not in {c["name"] for c in self.chans}:
                raise ValueError(f"move at bar {m['bar']}: no channel {m['channel']!r}")
            if "gate" in m.get("set", {}):
                Gate(m["set"]["gate"]).eval(np.arange(16), lambda n: 0)
        self.T = lambda tag: np.random.default_rng([self.bounty, _crc(tag)])
        # the terrain: fixed draws per subsystem; prefix-stable, so a longer arrangement keeps the same start
        self.u_dens = self.T("density").random(self.S)
        self.u_pitch = self.T("pitch").random(self.S)
        self.u_orn = self.T("ornament").random(self.S)
        self.u_hum = self.T("humanize").normal(0, 1, self.S)
        self.u_beh = self.T("behaviour").random((bars, 2))
        self.n_mut = self.T("mutation").normal(0, 1, (bars, len(INTERVALS)))
        self.u_mod = self.T("modify").random((bars, 64, 3))
        self.lfsr_seed = int(self.T("lfsr").integers(1, 0xFFFF))
        self.coinc = np.mean([(self.steps - self.phase(n)) % n == 0 for n in self.clocks], axis=0) if self.clocks else np.zeros(self.S)
        self.lead_trig = self.trig(p["gate"])
        self.cycle = lcm(self.clocks + sorted(Gate(p["gate"]).divs))
        self.ideas = think(p) if any(c["role"] == "melody" for c in self.chans) else []
        self.kept = kept(p, self.ideas)

    def phase(self, n: int) -> int:
        if n not in self._phase:      # each divider's phase depends on the Bounty and the divider only
            self._phase[n] = int(np.random.default_rng([self.bounty, 7919, n]).integers(0, n))
        return self._phase[n]

    def trig(self, expr: str) -> np.ndarray:
        if expr not in self._trig:
            self._trig[expr] = Gate(expr).eval(self.steps, self.phase)
        return self._trig[expr]

    def terrain(self, ch: dict, what: str) -> np.ndarray:
        """A channel's own draws; the first melody channel uses the classic ones (so old patches keep their lead)."""
        if ch["n"] == self.first_melody() and what in ("density", "pitch"):
            return self.u_dens if what == "density" else self.u_pitch
        key = f"{what}:{ch['name']}"
        if key not in self._trig:
            self._trig[key] = self.T(key).random(self.S)
        return self._trig[key]

    def first_melody(self) -> int:
        return next((c["n"] for c in self.chans if c["role"] == "melody"), -1)

    def _off(self, s: int) -> float:
        o = (self.swing - 0.5) * 0.5 if s % 2 else 0.0
        if self.hum_ms:
            o += self.u_hum[s % self.S] * self.hum_ms / (60000 / self.bpm)
        return o

    # -------------------------------------------------------------- the recorder: knobs per bar
    def at(self, b: int, ch: dict) -> dict:
        """Every knob of a channel at bar b (0-based): the patch, the channel's own settings, then the recorder's moves
        (bars in moves are 1-based, like the arrangement): a move sets its knobs from its bar, or ramps them to `to_bar`."""
        key = (b, ch["name"])
        if key in self._at:
            return self._at[key]
        v = {k: copy.deepcopy(self.p[k]) for k in KNOBS}
        v.update({"mute": False, "transpose": 0, "octave": 0})
        v.update({k: copy.deepcopy(x) for k, x in ch.items() if k not in ("name", "role", "n", "tone", "mix")})
        for m in self.moves:
            if m.get("channel") not in (None, ch["name"]) or b < m["bar"] - 1:
                continue
            for k, target in m.get("set", {}).items():
                head, _, sub = k.partition(".")
                cur = v.get(head) if not sub else v.get(head, {}).get(sub)
                val = target
                if m.get("to_bar") and b < m["to_bar"] - 1 and isinstance(target, (int, float)) and isinstance(cur, (int, float)) \
                        and not isinstance(target, bool):
                    frac = (b - (m["bar"] - 1) + 1) / (m["to_bar"] - m["bar"] + 1)
                    val = cur + (target - cur) * frac
                if sub:
                    v[head] = {**v.get(head, {}), sub: val}
                else:
                    v[head] = val
        self._at[key] = v
        return v

    # -------------------------------------------------------------- drums
    def drum_steps(self, layers: set, bar: int) -> list[tuple]:
        """(step in bar, sound, vel) for one bar: every layer is a gate over the clock matrix with its own threshold."""
        out = []
        if bar >= self.bars:
            return out
        sl = slice(bar * 16, bar * 16 + 16)
        for layer in sorted(layers):
            d = self.p["drums"].get(layer)
            if not d:
                continue
            if layer not in self._drums:
                u = np.random.default_rng([self.bounty, _crc("drum:" + layer)]).random(self.S)
                self._drums[layer] = (Gate(d["gate"]).eval(self.steps, self.phase), u)
            trig, u = self._drums[layer]
            for i, s in enumerate(range(sl.start, sl.stop)):
                if trig[s] and u[s] < d.get("density", 1.0):
                    v = d.get("vel", 0.85) * (0.8 + 0.4 * self.coinc[s]) * (1.08 if i % 4 == 0 else 1.0)
                    out.append((i, d.get("sound", layer), float(np.clip(v, 0.08, 1.0))))
        return out

    # -------------------------------------------------------------- pitch helpers
    def bar_scale(self, ctx: dict) -> list[int]:
        """The scale constraint as MIDI notes over the whole useful range, moved by the block's transpose."""
        p = self.p
        if p["scale"] == "key":
            pcs = set(ctx["key_pcs"])
        else:
            root = ctx["tonic"] if p["root"] == "key" else note_pc(p["root"])
            pcs = {(root + i) % 12 for i in SCALES[p["scale"]]}
        pcs = {(x + ctx["tr"]) % 12 for x in pcs}
        return [m for m in range(12, 116) if m % 12 in pcs]

    @staticmethod
    def snap(scale: list[int], p: int) -> int:
        return min(scale, key=lambda m: (abs(m - p), m))

    @staticmethod
    def steps_from(scale: list[int], p: int, k: int) -> int:
        i = scale.index(Machine.snap(scale, p))
        return scale[int(np.clip(i + k, 0, len(scale) - 1))]

    @staticmethod
    def fold(p: int, lo: int, hi: int) -> int:
        while p < lo:
            p += 12
        while p > hi:
            p -= 12
        return p

    @staticmethod
    def chord_at(ctx: dict, beat: float) -> tuple:
        """(pcs, root) of the chord sounding at a beat of the bar."""
        for c in ctx["chords"]:
            if c[0] <= beat < c[0] + c[1]:
                return set((x + ctx["tr"]) % 12 for x in c[2]), (c[3] + ctx["tr"]) % 12
        if ctx["chords"]:
            c = ctx["chords"][-1]
            return set((x + ctx["tr"]) % 12 for x in c[2]), (c[3] + ctx["tr"]) % 12
        return set(ctx["key_pcs"]), ctx["tonic"]

    def weights(self, bar: int, ch: dict | None = None) -> np.ndarray:
        """The interval weights for a bar: the knobs, drifted by a mean-reverting walk scaled by the mutation rate."""
        ch = ch or self.chans[0]
        name = ch["name"]
        if name not in self._drift:
            d, out = np.zeros(len(INTERVALS)), []
            for b in range(self.bars):
                d = 0.9 * d + self.n_mut[b] * 0.45 * float(self.at(b, ch)["mutation"])
                out.append(d.copy())
            self._drift[name] = np.array(out)
        cp = self.at(min(bar, self.bars - 1), ch)
        w0 = np.array([max(1e-3, float(cp["intervals"].get(k, 0))) for k in INTERVALS])
        return w0 * np.exp(self._drift[name][min(bar, self.bars - 1)] * 2.0)

    @staticmethod
    def iclass(semis: int) -> int:
        a = abs(semis)
        return 0 if a == 0 else 1 if a <= 2 else 2 if a <= 4 else 3 if a <= 6 else 4 if a == 7 else 5 if a <= 11 else 6

    def markov(self, cur: int, s: int, scale: list[int], chord_pcs: set, strong: bool, w: np.ndarray, cp: dict | None = None, u=None) -> int:
        cp = cp or self.p
        lo, hi = cp["register"]
        cand = [m for m in scale if lo <= m <= hi and abs(m - cur) <= 12]
        if not cand:
            return self.fold(cur, lo, hi)
        centre, span = (lo + hi) / 2, max(6.0, (hi - lo) / 2)
        up, g = float(cp["up"]), float(cp["gravity"])
        ws = []
        for m in cand:
            x = w[self.iclass(m - cur)]
            x *= 2 * up if m > cur else 2 * (1 - up) if m < cur else 1.0
            if strong:
                x *= (1 + 4 * g) if m % 12 in chord_pcs else (1 - 0.6 * g)
            x *= math.exp(-1.2 * ((m - centre) / span) ** 2)
            ws.append(max(x, 1e-9))
        c = np.cumsum(ws) / sum(ws)
        uu = (self.u_pitch if u is None else u)[s % self.S]
        return cand[int(np.searchsorted(c, uu, side="right").clip(0, len(cand) - 1))]

    # -------------------------------------------------------------- the performance
    def perform(self, timeline: list[dict]) -> dict:
        """timeline: one dict per arranged bar {bar, chords [(beat, beats, pcs, root)], tr, key_pcs, tonic, lead, sidekick,
        act, kime, loop, parts}. Returns {"parts": {channel: notes}, "lead", "sidekick", "line"}; notes as (t, d, pitch, vel, off)."""
        lines: dict[str, list] = {}
        order = sorted(self.chans, key=lambda c: (c["role"] == "harmony", c["n"]))     # harmonies follow the others
        for ch in order:
            role = ch["role"]
            if role == "melody":
                lines[ch["name"]] = self._melody(timeline, ch)
            elif role == "harmony":
                src = lines.get(ch.get("follow", "lead")) or next(iter(lines.values()), [])
                lines[ch["name"]] = self._harmony(src, timeline, ch)
            elif role == "bass":
                lines[ch["name"]] = self._bass(timeline, ch)
            elif role == "ostinato":
                lines[ch["name"]] = self._ostinato(timeline, ch)
            elif role == "counter":
                mel = lines.get(ch.get("against", "lead")) or next((lines[c["name"]] for c in order if c["role"] == "melody" and c["name"] in lines), [])
                lines[ch["name"]] = self._counter(timeline, ch, mel)
        parts = {ch["name"]: self._emit(lines[ch["name"]], timeline, ch) for ch in self.chans}
        first = next((c["name"] for c in self.chans if c["role"] == "melody"), None)
        side = next((c["name"] for c in self.chans if c["role"] == "harmony"), None)
        return {"parts": parts, "lead": parts.get(first, []), "sidekick": parts.get(side, []),
                "line": [n[:4] + (n[4],) for n in lines.get(first, [])]}

    def plays(self, ch: dict, ctx: dict, timeline_lists: set) -> bool:
        """Is the channel heard in this bar: where the arrangement lists its part, else with the part in `with` (lead)."""
        name = ch["name"]
        if ctx.get("kime"):                                # the band's unison hits: the machine sits them out
            return False
        if name == "lead" or (name not in timeline_lists and ch.get("with", "lead") == "lead" and name != "sidekick"):
            on = ctx.get("lead", True)
        elif name == "sidekick" and "sidekick" in ctx:
            on = ctx["sidekick"]
        elif name in timeline_lists:
            on = name in ctx.get("parts", ())
        else:
            on = ch["with"] in ctx.get("parts", ()) or (ch["with"] == "sidekick" and ctx.get("sidekick", False))
        return bool(on) and not self.at(ctx["bar"], ch)["mute"]

    def _emit(self, line, timeline, ch) -> list[tuple]:
        listed = {x for c in timeline for x in c.get("parts", ())}
        on = {c["bar"] for c in timeline if c["bar"] < self.bars and self.plays(ch, c, listed)}
        return [(t, d, q, v, self._off(s % self.S)) for (t, d, q, v, s) in line if int(t // 4) in on]

    # ---- melody: themes, answers, the walk, cadences, frozen loops
    def _melody(self, timeline: list[dict], ch: dict) -> list[tuple]:
        p = self.p
        main = ch["n"] == self.first_melody()
        ring: deque = deque(maxlen=int(p["memory"]))
        line: list[tuple] = []
        prev_bar: list[tuple] = []
        cur = None
        run = 0
        fz = list(p.get("freeze", [])) + [dict(m["freeze"], bar=m["bar"]) for m in self.moves if "freeze" in m and m.get("channel") in (None, ch["name"])]
        freezes = {int(f["bar"]) - 1: f for f in fz} if main else {}
        frozen = None
        beh_names = [k for k in BEHAVIOURS if p["behaviours"].get(k, 0) > 0]
        plan = [t for t in p.get("phrase", []) if t in PHRASE_TOKENS] if self.kept else []
        sec_loop, sec_start, themes, passes, anchor = None, 0, {}, Counter(), {}
        was_on = False
        for ctx in timeline:
            b = ctx["bar"]
            if b >= self.bars:
                break
            cp = self.at(b, ch)
            lo, hi = cp["register"]
            scale = self.bar_scale(ctx)
            loop = ctx.get("loop", "A")
            entry = ctx.get("lead", True) and not was_on      # the lead comes in: its phrase starts over (a theme opens it)
            was_on = bool(ctx.get("lead", True))
            if loop != sec_loop or ctx.get("restart") or entry:
                sec_loop, sec_start = loop, b
            pos = (b - sec_start) % len(plan) if plan else -1
            token = plan[pos] if plan else "free"
            notes: list[tuple] = []
            tag = "·"
            if b in freezes and ring:                                  # Freeze & Populate: the last N notes become a loop
                f = freezes[b]
                cells = list(ring)[-int(f.get("notes", 8)):]
                t0 = math.floor(cells[0][0] / 4) * 4
                rel = [(t - t0, d, q, v) for (t, d, q, v) in cells]
                span = max(t + d for t, d, _, _ in rel)
                period = int(f.get("period") or min(4, max(1, math.ceil(span / 4 - 1e-6))))
                frozen = {"cells": rel, "start": b, "until": b + int(f.get("bars", 4)), "period": period, "f": f,
                          "pofs": [0] * len(rel), "vofs": [0.0] * len(rel), "lfsr": LFSR(self.lfsr_seed ^ (b * 2654435761 & 0xFFFF)),
                          "pitches": [c[2] for c in rel], "rep": -1}
            if frozen and b >= frozen["until"]:
                frozen = None                                          # break back into generation
            if frozen:
                tag = "F"
                k = b - frozen["start"]
                rep, fpos = divmod(k, frozen["period"])
                f = frozen["f"]
                if rep != frozen["rep"]:                                # a new pass through the loop: transform, then modify
                    frozen["rep"] = rep
                    if rep > 0:
                        self._evolve(frozen, f, b, scale, ch)
                for i, (t, d, _, v) in enumerate(frozen["cells"]):
                    if fpos * 4 <= t < fpos * 4 + 4:
                        q = frozen["pitches"][i]
                        tf = f.get("transform", "transpose")
                        if tf == "transpose":
                            q = self.steps_from(scale, q, int(f.get("amount", 2)) * rep)
                        elif tf == "invert" and rep % 2 == 1:
                            q = self.steps_from(scale, frozen["pitches"][0], scale.index(self.snap(scale, frozen["pitches"][0])) - scale.index(self.snap(scale, q)))
                        q = self.steps_from(scale, q, frozen["pofs"][i])
                        q = self.fold(q, lo, hi)
                        notes.append((t - fpos * 4, d, q, float(np.clip(v + frozen["vofs"][i], 0.1, 1.0))))
            elif token == "theme":
                if loop not in themes:
                    themes[loop] = self.kept[len(themes) % len(self.kept)]
                half = 0
                while pos - half - 1 >= 0 and plan[pos - half - 1] == "theme":
                    half += 1
                half %= 2
                if half == 0:
                    passes[loop] += 1
                notes, cur = self._theme(themes[loop], half, b, ctx, scale, cp, cur, anchor, loop, passes[loop])
                tag = "Th" if passes[loop] % 3 == 1 or pos < 4 else "Th~"
            elif token == "answer" and prev_bar and beh_names:
                bp = np.array([p["behaviours"][k_] for k_ in beh_names])
                j = int(np.searchsorted(np.cumsum(bp) / bp.sum(), self.u_beh[b, 0], side="right").clip(0, len(beh_names) - 1))
                notes = self._treat(beh_names[j], prev_bar, b, scale)
                tag = {"repeat": "R", "reverse": "Rv", "transpose": "T", "invert": "I", "ornament": "O"}[beh_names[j]]
            else:
                beh = "generate"
                if token == "free" and prev_bar and beh_names and run < 2:
                    edges = np.cumsum([p["behaviours"][k_] for k_ in beh_names])
                    j = int(np.searchsorted(edges, self.u_beh[b, 0], side="right"))
                    beh = beh_names[j] if j < len(beh_names) else "generate"
                if beh == "generate":
                    run = 0
                    notes, cur = self._generate(b, ctx, scale, cur, ch, cp)
                    tag = "G"
                    if token == "cadence" and notes:            # land on the chord root, held to the bar line
                        pcs, root = self.chord_at(ctx, notes[-1][0])
                        t, d, q, v = notes[-1]
                        q = min((m for m in scale if m % 12 == root and lo - 5 <= m <= hi), key=lambda m: abs(m - q), default=q)
                        notes[-1] = (t, max(d, 4 - t - 0.1), q, v)
                        tag = "C"
                else:
                    run += 1
                    notes = self._treat(beh, prev_bar, b, scale)
                    tag = {"repeat": "R", "reverse": "Rv", "transpose": "T", "invert": "I", "ornament": "O"}[beh]
            tr = int(cp.get("transpose", 0))
            notes = [(t, d, self.fold(self.steps_from(scale, q, tr) if tr else q, lo - 12, hi + 12) + 12 * int(cp.get("octave", 0)), v)
                     for (t, d, q, v) in notes if 0 <= t < 4]
            if notes:
                cur = notes[-1][2]
            prev_bar = notes
            for (t, d, q, v) in notes:
                ring.append((b * 4 + t, d, q, v))
                line.append((b * 4 + t, d, q, v, int(round((b * 4 + t) * 4))))
            if main:
                self.log.append(tag)
        return line

    def _theme(self, idea, half, b, ctx, scale, cp, cur, anchor, loop, npass):
        """One bar of a kept idea, on this bar's chords: degree 0 is a chord tone near where the line is (pulled towards
        where the theme first sat, so it comes back recognisably), strong beats lean on chord tones. Every third
        statement is lifted a step, every other one ornamented."""
        lo, hi = cp["register"]
        pcs, _ = self.chord_at(ctx, 0)
        if half == 0 or loop not in anchor:
            home = anchor.get(("home", loop))
            ref = cur if cur is not None else (lo + hi) // 2
            tones = [m for m in scale if m % 12 in pcs and lo <= m <= hi - 4] or [self.snap(scale, ref)]
            near = [m for m in tones if abs(m - ref) <= 4] or tones
            a = min(near, key=lambda m: (abs(m - (home if home is not None else lo + (hi - lo) * 0.4)), abs(m - ref)))
            anchor[loop] = a
            anchor.setdefault(("home", loop), a)
        a = anchor[loop]
        lift = 1 if npass % 3 == 0 else 0
        ai = scale.index(self.snap(scale, a)) + lift
        out = []
        for (s, d, deg, v) in idea["cells"]:
            if s // 16 != half:
                continue
            st = s % 16
            q = scale[int(np.clip(ai + deg, 0, len(scale) - 1))]
            cpcs, _ = self.chord_at(ctx, st / 4)
            if st % 8 == 0 and float(cp["gravity"]) >= 0.5 and q % 12 not in cpcs:
                near = [m for m in (self.steps_from(scale, q, -1), self.steps_from(scale, q, 1)) if m % 12 in cpcs]
                q = near[0] if near else q
            out.append((st / 4, d, q, v))
        if out:                                            # out of range: the whole bar moves an octave, the shape stays
            top, bot = max(n[2] for n in out), min(n[2] for n in out)
            sh = -12 if top > hi + 5 and bot - 12 >= lo - 12 else 12 if bot < lo - 5 and top + 12 <= hi + 12 else 0
            out = [(t, d, q + sh, v) for (t, d, q, v) in out]
        if npass % 2 == 0 and npass > 0:
            out = self._treat("ornament", out, b, scale)
        return out, (out[-1][2] if out else cur)

    def _generate(self, b: int, ctx: dict, scale: list[int], cur, ch: dict | None = None, cp: dict | None = None):
        ch = ch or self.chans[0]
        cp = cp or self.at(b, ch)
        lo, hi = cp["register"]
        if cur is None:                                    # start on a chord tone near the middle of the register
            pcs, _ = self.chord_at(ctx, 0)
            cur = self.snap([m for m in scale if m % 12 in pcs and lo <= m <= hi] or scale, (lo + hi) // 2)
        w = self.weights(b, ch)
        dens = float(cp["density"]) * ctx.get("act", 1.0)
        trig_a, u_d, u_p = self.trig(cp["gate"]), self.terrain(ch, "density"), self.terrain(ch, "pitch")
        trig = [s for s in range(b * 16, b * 16 + 16) if trig_a[s] and u_d[s] < dens]
        nxt = [s for s in range(b * 16, min(self.S, b * 16 + 32)) if trig_a[s] and u_d[s] < dens]
        out = []
        for s in trig:
            i = s - b * 16
            later = [x for x in nxt if x > s]
            gap = (later[0] - s) if later else int(cp["max_steps"])
            dur = max(1, min(gap, int(cp["max_steps"]))) * 0.25 * float(cp["legato"])
            chord_pcs, _ = self.chord_at(ctx, i / 4)
            strong = i % 8 == 0 or self.coinc[s] >= 0.6
            cur = self.markov(cur, s, scale, chord_pcs, strong, w, cp, u_p)
            v = 0.62 + float(cp["accent"]) * 0.45 * self.coinc[s] + (0.06 if i % 4 == 0 else 0.0)
            out.append((i / 4, dur, cur, float(np.clip(v, 0.2, 1.0))))
        return out, cur

    def _treat(self, beh: str, last: list[tuple], b: int, scale: list[int]) -> list[tuple]:
        if not last:
            return []
        if beh == "repeat":
            return list(last)
        if beh == "reverse":                               # retrograde: the bar backwards in time, rhythm and pitch
            return sorted((max(0.0, round((4 - t - d) * 4) / 4), d, q, v) for (t, d, q, v) in last)
        if beh == "transpose":
            k = [-3, -2, 2, 3, 4, -4, 1, -1][int(self.u_beh[b, 1] * 8)]
            return [(t, d, self.steps_from(scale, q, k), v) for (t, d, q, v) in last]
        if beh == "invert":                                # mirror the bar's pitches around its first note, in scale steps
            ax = scale.index(self.snap(scale, last[0][2]))
            return [(t, d, scale[int(np.clip(2 * ax - scale.index(self.snap(scale, q)), 0, len(scale) - 1))], v) for (t, d, q, v) in last]
        if beh == "ornament":                              # the bar again with grace notes and turns on its longer notes
            out = []
            for j, (t, d, q, v) in enumerate(last):
                s = (b * 16 + int(t * 4)) % self.S
                if d >= 0.4 and self.u_orn[s] < 0.6:
                    nb = self.steps_from(scale, q, 1 if self.u_orn[(s + 1) % self.S] < 0.5 else -1)
                    if self.u_orn[(s + 2) % self.S] < 0.5:
                        out += [(t, 0.12, nb, v * 0.75), (t + 0.125, d - 0.125, q, v)]            # a mordent
                    else:
                        out += [(t, 0.1, q, v), (t + 0.125, 0.1, nb, v * 0.7), (t + 0.25, max(0.12, d - 0.25), q, v)]   # a turn
                else:
                    out.append((t, d, q, v))
            return out
        return list(last)

    def _evolve(self, fr: dict, f: dict, b: int, scale: list[int], ch: dict):
        """Between passes of a frozen loop: 'mutate' lets the LFSR swap cells for fresh Markov choices; Modify nudges
        pitch (by a scale step) and velocity (by 0.08) and the nudges accumulate."""
        n = len(fr["cells"])
        cp = self.at(b, ch)
        if f.get("transform") == "mutate":
            amt = float(f.get("amount", 0.25))
            bits = fr["lfsr"].bits(n)
            w = self.weights(b, ch)
            for i in range(n):
                s = (b * 16 + int(fr["cells"][i][0] * 4)) % self.S
                if bits[i] and (fr["lfsr"].s & 0xFF) / 255 < amt * 2:
                    fr["pitches"][i] = self.markov(fr["pitches"][i], s, scale, set(), False, w, cp)
        mod = float(f.get("modify", cp["modify"]))
        if mod > 0:
            for i in range(min(n, 64)):
                u = self.u_mod[b, i]
                if u[0] < mod:
                    fr["pofs"][i] += 1 if u[1] < 0.5 else -1
                if u[2] < mod:
                    fr["vofs"][i] = float(np.clip(fr["vofs"][i] + (0.08 if u[1] >= 0.5 else -0.08), -0.32, 0.24))

    # ---- harmony: the interval buttons
    def _harmony(self, line, timeline, ch) -> list[tuple]:
        rule = ch.get("interval", "third_below")
        if rule == "off" or not line:
            return []
        lo, hi = ch.get("register", self.p["sidekick_register"])
        bars = {c["bar"]: c for c in timeline}
        out = []

        def scale_at(t):
            c = bars.get(int(t // 4))
            return self.bar_scale(c) if c else None
        steps = {"third_below": -2, "sixth_below": -5, "third_above": 2, "fourth_above": 3}
        if rule in steps or rule in ("fifth_below", "octave_below"):
            for (t, d, q, v, s) in line:
                sc = scale_at(t)
                if not sc:
                    continue
                if rule == "fifth_below":
                    r = q - 7
                    r = max(m for m in sc if m <= r) if any(m <= r for m in sc) else r
                elif rule == "octave_below":
                    r = q - 12
                else:
                    r = self.steps_from(sc, q, steps[rule])
                out.append((t, d, self.fold(r, lo, hi), v * 0.8, s))
        elif rule == "canon":
            k = float(ch.get("canon_beats", self.p["canon_beats"]))
            for (t, d, q, v, s) in line:
                sc = scale_at(t + k)
                if sc:
                    out.append((t + k, d, self.fold(self.snap(sc, q - 12), lo, hi), v * 0.78, s + int(k * 4)))
        elif rule == "contrary":                            # every jump of the lead mirrored, in scale steps
            prev = cur = None
            for (t, d, q, v, s) in line:
                sc = scale_at(t)
                if not sc:
                    continue
                if cur is None:
                    cur = self.fold(self.steps_from(sc, q, -5), lo, hi)
                else:
                    k = sc.index(self.snap(sc, q)) - sc.index(self.snap(sc, prev))
                    cur = self.steps_from(sc, cur, -k)
                    if not lo <= cur <= hi:
                        cur = self.fold(cur, lo, hi)
                prev = q
                out.append((t, d, cur, v * 0.8, s))
        elif rule == "root_on_downbeat":                    # once the lead has spoken, the chord root lands on the next downbeat
            played = {int(t // 4) for (t, *_ ) in line}
            for b in sorted(bars):
                c = bars[b]
                if b - 1 not in played and b not in played:
                    continue
                for (beat, beats, pcs, root) in c["chords"] or [(0, 4, c["key_pcs"], c["tonic"])]:
                    if beat % 1:
                        continue
                    v = 0.7 + 0.2 * (beat == 0)
                    rt = self.fold(lo + ((root + c["tr"] - lo) % 12), lo, hi)
                    out.append((b * 4 + beat, beats * 0.92, rt, v, int((b * 4 + beat) * 4)))
        return out

    # ---- bass: the bassline sequencer
    def _bass(self, timeline, ch) -> list[tuple]:
        out = []
        u_d, u_p = self.terrain(ch, "density"), self.terrain(ch, "pitch")
        for ctx in timeline:
            b = ctx["bar"]
            if b >= self.bars:
                break
            cp = self.at(b, ch)
            lo, hi = cp["register"]
            trig = self.trig(cp["gate"])
            hits = [s for s in range(b * 16, min(self.S, b * 16 + 16)) if trig[s] and (u_d[s] < float(cp["density"]) or s % 16 == 0)]
            nxt_bar = next((c for c in timeline if c["bar"] == b + 1), None)
            for j, s in enumerate(hits):
                i = s - b * 16
                pcs, root = self.chord_at(ctx, i / 4)
                base = self.fold(lo + ((root - lo) % 12), lo, hi - 7)
                gap = ((hits[j + 1] if j + 1 < len(hits) else b * 16 + 16) - s)
                # is the next hit on a new chord? then maybe walk into it
                nb = (i + gap) / 4
                if nb < 4:
                    _, nroot = self.chord_at(ctx, nb)
                else:
                    _, nroot = self.chord_at(nxt_bar, 0) if nxt_bar else (None, root)
                starts = any(abs(c[0] * 4 - i) < 0.5 for c in ctx["chords"]) or i == 0
                u = u_p[s]
                if starts:
                    q = base
                elif nroot != root and u < 0.55:
                    tgt = self.fold(lo + ((nroot - lo) % 12), lo, hi - 7)
                    q = tgt - 1 if u < 0.2 else self.steps_from(self.bar_scale(ctx), tgt, 1 if u < 0.38 else -1)
                else:
                    fifth = root + 7 if (root + 7) % 12 in pcs or len(pcs) < 3 else root + 6
                    third = next((root + k for k in (3, 4) if (root + k) % 12 in pcs), root + 7)
                    q = base + [0, (fifth - root), 12, (third - root), 0][int(u * 5) % 5]
                dur = max(1, min(gap, int(cp["max_steps"]) + 2)) * 0.25 * float(cp["legato"])
                v = 0.78 + float(cp["accent"]) * 0.3 * self.coinc[s] + (0.1 if starts else 0.0)
                out.append((b * 4 + i / 4, dur, self.fold(int(q), lo, hi), float(np.clip(v, 0.3, 1.0)), s))
        return out

    # ---- ostinato: the stepping sequencer
    def _ostinato(self, timeline, ch) -> list[tuple]:
        L = max(2, int(ch.get("length", 5)))
        r = self.T(f"ostinato:{ch['name']}")
        cells = [int(x) for x in r.integers(0, 4, L)]
        octs = [int(x) for x in (r.random(L) < 0.2)]
        lf = LFSR(self.lfsr_seed ^ _crc(ch["name"]) & 0xFFFF)
        u_d = self.terrain(ch, "density")
        out, k = [], 0
        for ctx in timeline:
            b = ctx["bar"]
            if b >= self.bars:
                break
            cp = self.at(b, ch)
            lo, hi = cp["register"]
            if b and b % 4 == 0 and (lf.step() & 0xFF) / 255 < float(cp["mutation"]) * 2:       # the shift register rewrites a cell
                cells[(lf.step() >> 4) % L] = lf.step() % 4
            trig = self.trig(cp["gate"])
            hits = [s for s in range(b * 16, min(self.S, b * 16 + 16)) if trig[s] and u_d[s] < float(cp["density"])]
            for j, s in enumerate(hits):
                i = s - b * 16
                pcs, root = self.chord_at(ctx, i / 4)
                tones = sorted(pcs, key=lambda x: (x - root) % 12)
                pc = tones[cells[k % L] % len(tones)]
                q = self.fold(lo + ((pc - lo) % 12) + 12 * octs[k % L], lo, hi)
                gap = (hits[j + 1] if j + 1 < len(hits) else b * 16 + 16) - s
                v = 0.62 + float(cp["accent"]) * 0.35 * self.coinc[s] + (0.12 if k % L == 0 else 0.0)    # the sequence's first cell accented
                out.append((b * 4 + i / 4, max(0.1, gap * 0.25 * float(cp["legato"])), q, float(np.clip(v, 0.2, 1.0)), s))
                k += 1
        return out

    # ---- counter: the slow second line
    def _counter(self, timeline, ch, mel) -> list[tuple]:
        out, cur, prev_mel = [], None, None
        u_d, u_p = self.terrain(ch, "density"), self.terrain(ch, "pitch")
        mel_at = {}
        for (t, d, q, v, s) in mel:
            for x in range(int(t * 4), int((t + d) * 4) + 1):
                mel_at[x] = q
        for ctx in timeline:
            b = ctx["bar"]
            if b >= self.bars:
                break
            cp = self.at(b, ch)
            lo, hi = cp["register"]
            scale = self.bar_scale(ctx)
            trig = self.trig(cp["gate"])
            hits = [s for s in range(b * 16, min(self.S, b * 16 + 16)) if trig[s] and u_d[s] < float(cp["density"])]
            nxt = [s for s in range(b * 16, min(self.S, b * 16 + 48)) if trig[s] and u_d[s] < float(cp["density"])]
            for s in hits:
                i = s - b * 16
                pcs, _ = self.chord_at(ctx, i / 4)
                m_now = mel_at.get(s)
                if cur is None:
                    cur = self.snap([m for m in scale if m % 12 in pcs and lo <= m <= hi] or scale, (lo + hi) // 2)
                cand = [m for m in scale if lo <= m <= hi and abs(m - cur) <= 5]
                ws = []
                for m in cand:
                    x = 1.0 if m != cur else 0.4
                    x *= 2.5 if abs(m - cur) <= 2 else 1.0
                    x *= 3.0 if (i % 8 == 0 and m % 12 in pcs) else 1.0
                    if m_now is not None and prev_mel is not None and m_now != prev_mel:
                        x *= 2.5 if (m - cur) * (m_now - prev_mel) < 0 else 0.6             # move against the melody
                    if m_now is not None and (m % 12 == m_now % 12 or abs(m - m_now) < 3):
                        x *= 0.15                                                            # keep off its notes
                    ws.append(x)
                c = np.cumsum(ws) / sum(ws)
                cur = cand[int(np.searchsorted(c, u_p[s], side="right").clip(0, len(cand) - 1))] if cand else cur
                if m_now is not None:
                    prev_mel = m_now
                later = [x for x in nxt if x > s]
                gap = (later[0] - s) if later else 16
                out.append((b * 4 + i / 4, max(0.25, min(gap, 16) * 0.25 * float(cp["legato"])), cur, 0.55 + 0.2 * (i % 8 == 0), s))
        return out

    def summary(self) -> list[str]:
        p = self.p
        counts = Counter(self.log)
        names = {"G": "generate", "R": "repeat", "Rv": "reverse", "T": "transpose", "I": "invert", "O": "ornament", "F": "frozen loop",
                 "Th": "theme", "Th~": "theme varied", "C": "cadence", "·": "rest"}
        out = [f"Electronium: bounty {p['bounty']}, scale {p['scale']}{'' if p['root'] == 'key' else ' on ' + str(p['root'])}, "
               f"density {p['density']}, mutation {p['mutation']}",
               f"  lead gate {p['gate']!r}; clock cycle {self.cycle} steps ({self.cycle / 16:g} bars)",
               "  channels: " + "; ".join(f"{c['n'] + 1} {c['name']} ({c['role']}"
                                          + (f" {c.get('interval')} of {c.get('follow')}" if c['role'] == 'harmony' else "")
                                          + (f", {c['length']} cells" if c['role'] == 'ostinato' else "")
                                          + (f", gate {c['gate']!r}" if c['role'] != 'harmony' and 'gate' in c else "")
                                          + (f", tone {c['tone'] if isinstance(c.get('tone'), str) else 'own'}" if c.get('tone') else "") + ")"
                                          for c in self.chans)]
        if self.ideas:
            out.append(f"  thought of {len(self.ideas)} ideas, kept " + ", ".join(f"#{d['n']} ({d['score']:.2f})" for d in self.kept)
                       + ("  (chosen)" if isinstance(p.get("keep"), (list, tuple)) else "  (the critic's pick)"))
            out += [f"    #{d['n']:<3d} {notation(d['cells'])}" for d in self.kept]
            out.append("  phrase: " + " ".join(p.get("phrase", [])))
        if self.moves:
            out.append("  recorder: " + "; ".join(f"bar {m['bar']}" + (f"-{m['to_bar']}" if m.get('to_bar') else "")
                                                  + (f" {m['channel']}" if m.get('channel') else "")
                                                  + (" " + ", ".join(f"{k}={v}" for k, v in m.get('set', {}).items()) if m.get('set') else "")
                                                  + (" freeze" if m.get('freeze') else "") for m in self.moves))
        out += ["  melody per bar: " + " ".join(self.log),
                "  " + ", ".join(f"{names[k]} {v}" for k, v in counts.most_common())]
        return out


# ------------------------------------------------------------------ patch files

def _val(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{_key(k)} = {_val(x)}" for k, x in v.items()) + " }"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_val(x) for x in v) + "]"
    if isinstance(v, (np.floating, float)):
        return repr(float(v))
    return str(int(v))


def _key(k: str) -> str:
    return k if k.replace("_", "").replace("-", "").isalnum() else _val(k)


def dump(p: dict) -> str:
    """The patch as TOML: plain values first, then the tables, the drums, then channels, moves and freezes."""
    out = ["# Electronium patch (bountiful/electronium.py): load it with produce --patch, or put it in a genre as [electronium]"]
    arrays = {k for k, v in p.items() if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)}
    tables = {k: v for k, v in p.items() if isinstance(v, dict)}
    for k, v in p.items():
        if k not in tables and k not in arrays and not (isinstance(v, list) and not v and k in ("freeze", "channels", "moves")):
            out.append(f"{k} = {_val(v)}")
    for k, v in tables.items():
        if k == "drums":
            for d, dv in v.items():
                out += ["", f"[drums.{d}]"] + [f"{a} = {_val(b)}" for a, b in dv.items()]
        else:
            out += ["", f"[{k}]"] + [f"{_key(a)} = {_val(b)}" for a, b in v.items()]
    for k in ("channels", "moves", "freeze"):
        for f in p.get(k, []) if k in arrays else []:
            out += ["", f"[[{k}]]"] + [f"{_key(a)} = {_val(b)}" for a, b in f.items()]
    return "\n".join(out) + "\n"


def load(path: Path) -> dict:
    return tomllib.loads(Path(path).read_text())


# ------------------------------------------------------------------ the terrain as text

def sketch(p: dict, bars: int = 8) -> str:
    """The clock matrix and every channel's triggers for a Bounty, one row per divider, '#' where it fires."""
    m = Machine(p, bars)
    row = lambda arr, mark="#": "|".join("".join(mark if arr[b * 16 + i] else "." for i in range(16)) for b in range(bars))
    lines = [f"bounty {p['bounty']} -> {m.bounty}; clock cycle {m.cycle} steps = {m.cycle / 16:g} bars"]
    for n in sorted(set(m.clocks) | Gate(p["gate"]).divs):
        lines.append(f"  r{n:<3d} phase {m.phase(n):2d}  " + row((m.steps - m.phase(n)) % n == 0))
    lines.append(f"  gate          " + row(m.lead_trig, "x"))
    lines.append(f"  plays @{p['density']:<5}  " + row(m.lead_trig & (m.u_dens < p["density"]), "o"))
    for c in m.chans:
        if c["role"] not in ("melody", "harmony"):
            lines.append(f"  {c['name'][:12]:12s}  " + row(m.trig(c["gate"]), "o"))
    for d, dv in p["drums"].items():
        trig = Gate(dv["gate"]).eval(m.steps, m.phase)
        lines.append(f"  {d:12s}  " + row(trig, "*"))
    return "\n".join(lines)


def ideas_text(p: dict, n: int = 20) -> str:
    ideas = think(p)
    keep = {d["n"] for d in kept(p, ideas)}
    best = sorted(ideas, key=lambda d: (-d["score"], d["n"]))[:n]
    out = [f"bounty {p['bounty']}: thought of {len(ideas)} ideas; best {len(best)} (* kept). Keep others with keep = [n, ...]",
           "  #    score  bar 1           | bar 2            degrees               rhythm presets"]
    out += [f"{'*' if d['n'] in keep else ' '} {d['n']:<4d} {d['score']:5.2f}  {notation(d['cells']):60s} {d['rhythm']}" for d in best]
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bounty", default=None)
    ap.add_argument("--bars", type=int, default=8)
    ap.add_argument("--patch", type=Path)
    ap.add_argument("--density", type=float)
    ap.add_argument("--gate")
    ap.add_argument("--ideas", type=int, nargs="?", const=20, help="list what the machine thought of, best first")
    a = ap.parse_args()
    over = {k: v for k, v in (("bounty", a.bounty), ("density", a.density), ("gate", a.gate)) if v is not None}
    pp = patch(load(a.patch) if a.patch else None, over)
    print(ideas_text(pp, a.ideas) if a.ideas else sketch(pp, a.bars))
