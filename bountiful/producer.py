"""The genre producer: performs a song skeleton the way a musician in that genre would.

What the composer gives away (measured by tools/tells.py) and what this module does about it:
  * octave-doubled, leapy melodies   -> one line; leaps beyond a set interval folded by octave (same note
                                        name, so the harmony is untouched); repeated-note runs held;
                                        busy bars thinned (weak, short, off-chord notes go first); a
                                        breath at each phrase end; legato or detached articulation
  * classical harmony                -> one chord per bar (or two, or one per two bars), coloured for the
                                        genre (m -> m9 in house ...), minor-key dominants made modal
                                        (G7 -> Gm7 in C minor) where the genre wants it, voice-led voicings
  * no feel                          -> velocity follows the phrase (rises to its peak note, accents on
                                        strong beats), timing breathes (humanize, push, swing)
Bass, chord parts (pad, stabs, comp, arp) and drums are generated per genre from the skeleton's chords.
Every event is (t, dur, pitch, vel, off): t on the grid in beats, off = performance offset in beats.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from skeleton import MAJOR, MINOR, Chord, Skeleton

INTERVALS = {"": (0, 4, 7), "m": (0, 3, 7), "7": (0, 4, 7, 10), "maj7": (0, 4, 7, 11), "m7": (0, 3, 7, 10), "dim": (0, 3, 6),
             "m7b5": (0, 3, 6, 10), "sus4": (0, 5, 7), "sus2": (0, 2, 7), "6": (0, 4, 7, 9), "m6": (0, 3, 7, 9),
             "m9": (0, 3, 7, 10, 14), "maj9": (0, 4, 7, 11, 14), "add9": (0, 4, 7, 14), "madd9": (0, 3, 7, 14), "9": (0, 4, 7, 10, 14),
             "7sus4": (0, 5, 7, 10), "m11": (0, 3, 7, 10, 14, 17), "6/9": (0, 4, 7, 9, 14), "5": (0, 7)}


@dataclass
class PChord:
    root: int
    quality: str
    start: float      # beats within the loop
    beats: float

    def pcs(self):
        return [(self.root + i) % 12 for i in INTERVALS[self.quality]]


# ------------------------------------------------------------------ harmony

# richer -> plainer: a colour is used only if every added tone belongs to the key
FALLBACK = {"m9": ["m9", "m7", "madd9", "m"], "m11": ["m11", "m9", "m7", "m"], "m7": ["m7", "m"], "maj9": ["maj9", "maj7", "add9", "6/9", "6", ""],
            "maj7": ["maj7", "add9", "6", ""], "add9": ["add9", ""], "6/9": ["6/9", "6", "add9", ""], "9": ["9", "7", "add9", ""],
            "7": ["7", ""], "7sus4": ["7sus4", "sus4", "7", ""], "madd9": ["madd9", "m"], "6": ["6", ""], "m6": ["m6", "m"]}


def key_scale(sk: Skeleton) -> set[int]:
    return {(sk.tonic + i) % 12 for i in (MINOR if sk.mode == "minor" else MAJOR)}


def is_minor(q: str) -> bool:
    return q.startswith("m") and not q.startswith("maj")


def colour(root: int, base_q: str, want: str, scale: set[int]) -> str:
    """The richest colour in `want`'s fallback chain that keeps the chord's major/minor third and adds
    only tones that belong to the key (so a colour never clashes with the melody)."""
    base = {(root + i) % 12 for i in INTERVALS.get(base_q, (0, 4, 7))}
    for q in FALLBACK.get(want, [want]) + [base_q]:
        if is_minor(q) != is_minor(base_q) and q not in ("5",):
            continue
        tones = {(root + i) % 12 for i in INTERVALS[q]}
        if tones - base <= scale:
            return q
    return base_q


def harmony(sk: Skeleton, start_bar: int, bars: int, cfg: dict) -> list[PChord]:
    """The loop's chords: harmonic rhythm, genre colours, modal dominants."""
    rhythm = cfg.get("rhythm", 1)
    out: list[PChord] = []
    for b in range(bars):
        h1, h2 = sk.halves[start_bar + b]
        if rhythm == 2 and (h2.root, h2.quality) != (h1.root, h1.quality):
            out += [PChord(h1.root, h1.quality, b * 4, 2), PChord(h2.root, h2.quality, b * 4 + 2, 2)]
        elif rhythm == 0.5 and b % 2 == 1:
            out[-1].beats += 4
        else:
            out.append(PChord(h1.root, h1.quality, b * 4, 4))
    merged: list[PChord] = []                  # the same chord twice in a row is one longer chord
    for c in out:
        if merged and (merged[-1].root, merged[-1].quality) == (c.root, c.quality):
            merged[-1].beats += c.beats
        else:
            merged.append(c)
    for c in merged:
        if sk.mode == "minor" and cfg.get("dominant", "keep") == "modal" and c.root == (sk.tonic + 7) % 12 and c.quality in ("", "7", "sus4", "7sus4"):
            c.quality = "m7" if c.quality == "7" else "m"
        if c.root == (sk.tonic + 11) % 12 and sk.mode == "minor" and cfg.get("dominant") == "modal" and c.quality in ("dim", "m7b5"):
            c.root, c.quality = (sk.tonic + 10) % 12, ""        # vii-dim -> bVII
        if sk.mode == "minor" and cfg.get("tonic_major") and c.root == sk.tonic and c.quality in ("", "maj7", "7", "6", "add9", "maj9"):
            c.quality = cfg["tonic_major"]                      # a picardy / secondary-dominant I in a minor key, e.g. -> "7sus4" (no bright third)
        want = cfg.get("colors", {}).get(c.quality)
        if want is not None and want != c.quality:      # "" is a real choice: the plain triad
            c.quality = colour(c.root, c.quality, want, key_scale(sk) | {(sk.tonic + 11) % 12} if c.root == (sk.tonic + 7) % 12 else key_scale(sk))
    return merged


def chord_at(chords: list[PChord], beat: float) -> PChord:
    for c in chords:
        if c.start <= beat + 1e-6 < c.start + c.beats:
            return c
    return chords[-1]


def voicings(chords: list[PChord], lo: int, hi: int, top: float, n: int, prev: list[int] | None = None) -> list[list[int]]:
    """Close voicings of n notes (chord tones, root optional above 4 notes), each chosen to move as
    little as possible from the last one while the top voice stays near `top`."""
    out = []
    for c in chords:
        pcs = c.pcs()
        need = pcs if len(pcs) <= n else [p for p in pcs if p != c.root][:n]      # rootless when there are more tones than voices
        cands = []
        for base in range(lo, lo + 12):
            v = []
            for p in sorted(set(need), key=lambda q: (q - base) % 12):
                x = base + ((p - base) % 12)
                v.append(x)
            v = sorted(v)
            if v[-1] <= hi and len(v) == len(set(need)):
                cands.append(v)
        if not cands:
            cands = [sorted(lo + ((p - lo) % 12) for p in set(need))]
        def cost(v):
            c_top = abs(v[-1] - top) * 0.5
            if prev is None:
                return c_top
            a, b = sorted(prev), v
            m = min(len(a), len(b))
            return sum(abs(x - y) for x, y in zip(a[:m], b[:m])) + c_top
        best = min(cands, key=cost)
        out.append(best)
        prev = best
    return out


# ------------------------------------------------------------------ melody

def melody(sk: Skeleton, start_bar: int, bars: int, chords: list[PChord], cfg: dict, rng) -> list[tuple]:
    a, b = start_bar * 4, (start_bar + bars) * 4
    src = [(n.t - a, n.d, n.p, n.v) for n in sk.melody if a <= n.t < b - 1e-6]
    if not src:
        return []
    lo, hi = cfg.get("register", [60, 81])
    grid = cfg.get("grid", 0.25)
    # 1. quantize to the genre grid
    notes = []
    for (t, d, p, v) in src:
        q = round(t / grid) * grid
        if notes and abs(notes[-1][0] - q) < 1e-6:
            continue
        notes.append([q, max(grid, d), p, v])
    # 2. modal minor: the raised leading tone becomes the natural seventh
    if sk.mode == "minor" and cfg.get("modal", False):
        for x in notes:
            if x[2] % 12 == (sk.tonic + 11) % 12:
                x[2] -= 1
    # 3. register: whole melody by octaves towards the middle of the register
    med = float(np.median([x[2] for x in notes]))
    shift = 12 * round(((lo + hi) / 2 - med) / 12)
    for x in notes:
        x[2] += shift
    # 4. fold leaps by octave (keeps the note name, so the harmony is unchanged); every note inside the register
    max_leap = cfg.get("max_leap", 7)
    while notes[0][2] < lo:
        notes[0][2] += 12
    while notes[0][2] > hi:
        notes[0][2] -= 12
    for i in range(1, len(notes)):
        prev, p = notes[i - 1][2], notes[i][2]
        if abs(p - prev) > max_leap:
            cands = [p + k for k in (-24, -12, 12, 24) if lo <= p + k <= hi] + ([p] if lo <= p <= hi else [])
            if cands:
                notes[i][2] = min(cands, key=lambda c: abs(c - prev))
        while notes[i][2] < lo:
            notes[i][2] += 12
        while notes[i][2] > hi:
            notes[i][2] -= 12
    # 5. repeated-note runs (3+) become one held note
    if cfg.get("merge_repeats", True):
        out, i = [], 0
        while i < len(notes):
            j = i
            while j + 1 < len(notes) and notes[j + 1][2] == notes[i][2] and notes[j + 1][0] - (notes[j][0] + notes[j][1]) < 0.3:
                j += 1
            if j - i >= 2:
                x = list(notes[i])
                x[1] = notes[j][0] + notes[j][1] - x[0]
                out.append(x)
            else:
                out += [list(n) for n in notes[i:j + 1]]
            i = j + 1
        notes = out
    # 6. thin busy bars: weak position, short, off-chord notes go first
    cap = cfg.get("max_notes_per_bar", 8)
    for bar in range(bars):
        inbar = [x for x in notes if bar * 4 <= x[0] < bar * 4 + 4]
        while len(inbar) > cap:
            def weakness(x):
                pos = x[0] % 1
                strength = 0 if pos == 0 else 1 if pos == 0.5 else 2
                off_chord = x[2] % 12 not in chord_at(chords, x[0]).pcs()
                return (strength, off_chord, -x[1])
            victim = max(inbar[1:], key=weakness) if len(inbar) > 1 else inbar[0]
            notes.remove(victim)
            inbar.remove(victim)
    notes.sort()
    # 7. articulation and phrase breaths
    art = cfg.get("articulation", "legato")
    phrase = cfg.get("phrase_bars", 4) * 4
    for i, x in enumerate(notes):
        nxt = notes[i + 1][0] if i + 1 < len(notes) else bars * 4
        gap = nxt - x[0]
        if art == "legato":
            x[1] = min(gap - 0.04, max(x[1], min(gap - 0.04, 2.0))) if gap <= 2.5 else min(x[1], 2.0)
        elif art == "detached":
            x[1] = min(x[1], gap * 0.7)
        if cfg.get("breath", True):
            end_phrase = (math.floor(x[0] / phrase) + 1) * phrase
            if x[0] + x[1] > end_phrase - 0.25 and nxt >= end_phrase:
                x[1] = max(grid, min(x[1], end_phrase - 0.5 - x[0]))
        x[1] = max(0.1, x[1])
    # 8. dynamics: rise to the phrase's peak note, strong beats accented
    vlo, vhi = cfg.get("velocity", [0.6, 0.92])
    for ph in range(0, bars * 4, phrase):
        grp = [x for x in notes if ph <= x[0] < ph + phrase]
        if not grp:
            continue
        plo, phi = min(x[2] for x in grp), max(x[2] for x in grp)
        for x in grp:
            height = (x[2] - plo) / max(1, phi - plo)
            pos = x[0] % 4
            acc = 1.0 if pos == 0 else 0.6 if pos == 2 else 0.3 if pos % 1 == 0 else 0.0
            x[3] = float(np.clip(vlo + (vhi - vlo) * (0.3 + 0.45 * height + 0.25 * acc) + rng.normal(0, 0.03), 0.2, 1.0))
    # 9. timing: swing, push and a human spread (all as offsets from the grid)
    return [(x[0], x[1], int(x[2]), x[3], timing(x[0], cfg, rng)) for x in notes]


def timing(t: float, cfg: dict, rng, bpm: float | None = None) -> float:
    """Performance offset in beats: swing on off-beat 16ths, a push, gaussian spread (ms at the genre tempo)."""
    bpm = bpm or cfg.get("_bpm", 120)
    ms = 60000 / bpm
    off = 0.0
    sw = cfg.get("swing", 0.5)
    if sw != 0.5 and abs((t * 4) % 2 - 1) < 1e-6:
        off += (sw - 0.5) * 0.5
    off += (cfg.get("push_ms", 0) + rng.normal(0, cfg.get("humanize_ms", 0))) / ms if cfg.get("humanize_ms", 0) or cfg.get("push_ms") else 0
    return off


# ------------------------------------------------------------------ bass

def degree(c: PChord, d: str, octave_base: int) -> int:
    pcs = c.pcs()
    third = next((p for p in pcs if (p - c.root) % 12 in (3, 4)), (c.root + 7) % 12)
    fifth = next((p for p in pcs if (p - c.root) % 12 in (6, 7)), (c.root + 7) % 12)
    seventh = next((p for p in pcs if (p - c.root) % 12 in (10, 11)), c.root)
    base = octave_base + ((c.root - octave_base) % 12)
    return {"R": base, "O": base + 12, "5": base + ((fifth - c.root) % 12), "3": base + ((third - c.root) % 12),
            "7": base + ((seventh - c.root) % 12), "5-": base + ((fifth - c.root) % 12) - 12}[d]


def bass(sk: Skeleton, start_bar: int, bars: int, chords: list[PChord], cfg: dict, rng) -> list[tuple]:
    style = cfg.get("style", "line")
    lo, hi = cfg.get("register", [33, 55])
    out = []
    if style == "line":                            # the composer's line, anchored and folded into the register
        a = start_bar * 4
        src = [n for n in sk.bass if a <= n.t < a + bars * 4 - 1e-6]
        grid = cfg.get("grid", 0.25)
        scale = {(sk.tonic + i) % 12 for i in (MINOR if sk.mode == "minor" else MAJOR)}
        prev = None
        for n in src:
            t = round((n.t - a) / grid) * grid
            c = chord_at(chords, t)
            p = n.p
            if abs(t - c.start) < 1e-6:            # chord changes land on the root
                p = p + ((c.root - p) % 12) if (c.root - p) % 12 <= 6 else p - ((p - c.root) % 12)
            elif p % 12 not in scale and p % 12 not in c.pcs():
                p = min((p + k for k in range(-2, 3) if (p + k) % 12 in c.pcs()), key=lambda q: abs(q - p))
            while p < lo:
                p += 12
            while p > hi:
                p -= 12
            if prev is not None and abs(p - prev) > 12:
                p += 12 if p < prev else -12
            vel = (0.9 if t % 4 == 0 else 0.8 if t % 1 == 0 else 0.68) + rng.normal(0, 0.03)
            out.append((t, max(grid * 0.9, min(n.d, 2.0)), p, vel, timing(t, cfg, rng)))
            prev = p
        out = [(t, min(d, (out[i + 1][0] - t) - 0.02) if i + 1 < len(out) else d, p, v, o) for i, (t, d, p, v, o) in enumerate(out)]
        return out
    pattern = cfg.get("pattern")
    for c in chords:
        base = lo
        if style == "octave8":                     # italo / synth-pop: low-high octaves on every 8th
            k = 0
            t = c.start
            while t < c.start + c.beats - 1e-6:
                p = degree(c, "R" if k % 2 == 0 else "O", base)
                out.append((t, cfg.get("gate", 0.4), p, (0.88 if k % 2 == 0 else 0.72) + rng.normal(0, 0.02), timing(t, cfg, rng)))
                t += 0.5
                k += 1
        elif style == "pattern":                   # a 16th-step pattern of degrees, repeated per bar
            cycle = cfg.get("patterns") or [pattern]   # or several, one per bar in turn (counted from the song's bar 1)
            for bar_t in np.arange(c.start, c.start + c.beats - 1e-6, 4):
                for entry in cycle[(start_bar + int(round(bar_t / 4))) % len(cycle)]:
                    step, d, dur = entry[:3]
                    t = bar_t + step / 4
                    if t >= c.start + c.beats - 1e-6:
                        continue
                    p = degree(c, d, base)
                    vel = (entry[3] if len(entry) > 3 else (0.9 if step == 0 else 0.76)) + rng.normal(0, 0.03)
                    out.append((t, dur, p, vel, timing(t, cfg, rng)))
        elif style == "sub":                       # jungle / dub: long roots
            out.append((c.start, c.beats - 0.1, degree(c, "R", base), 0.85, 0.0))
        elif style == "walking":                   # jazzy: root, chord tones, approach into the next root
            nxt = chords[(chords.index(c) + 1) % len(chords)]
            for k in range(int(c.beats)):
                t = c.start + k
                if k == 0:
                    p = degree(c, "R", base)
                elif k == int(c.beats) - 1:
                    tgt = degree(nxt, "R", base)
                    p = tgt + (1 if rng.random() < 0.5 else -1)
                else:
                    p = degree(c, ("5", "3", "7", "O")[k % 4], base)
                out.append((t, 0.85, p, (0.85 if k == 0 else 0.72) + rng.normal(0, 0.04), timing(t, cfg, rng)))
    return out


# ------------------------------------------------------------------ chord parts

def pad(chords, voic, cfg, rng):
    return [(c.start, c.beats - cfg.get("release_gap", 0.1), p, cfg.get("vel", 0.55) + rng.normal(0, 0.02), 0.0)
            for c, v in zip(chords, voic) for p in v]


def comp(chords, voic, cfg, rng):
    """Rhythmic chords: `steps` = 16th positions in each bar (stabs, offbeat chords, two-feel comping)."""
    out = []
    strum = cfg.get("strum_ms", 0) / (60000 / cfg.get("_bpm", 120))
    for c, v in zip(chords, voic):
        for bar_t in np.arange(math.floor(c.start / 4) * 4, c.start + c.beats - 1e-6, 4):
            for i, s in enumerate(cfg["steps"]):
                t = bar_t + s / 4
                if not (c.start - 1e-6 <= t < c.start + c.beats - 1e-6):
                    continue
                vel = (cfg.get("accent", 0.8) if i == 0 else cfg.get("vel", 0.68)) + rng.normal(0, 0.03)
                off = timing(t, cfg, rng)
                for k, p in enumerate(v):
                    out.append((t, cfg.get("gate", 0.22), p, vel - 0.015 * k, off + k * strum))
    return out


def arp(chords, voic, cfg, rng):
    out = []
    lo, hi = cfg.get("low", 60), cfg.get("high", 79)
    pat = cfg.get("pattern", [0, 1, 2, 3])
    rate = cfg.get("rate", 0.25)
    k = 0
    for c in chords:
        tones = sorted(p for p in range(lo, hi + 1) if p % 12 in c.pcs())
        t = c.start
        while t < c.start + c.beats - 1e-6:
            p = tones[pat[k % len(pat)] % len(tones)]
            vel = (0.78 if k % 4 == 0 else 0.6) + rng.normal(0, 0.02)
            out.append((t, cfg.get("gate", 0.16), p, vel, timing(t, cfg, rng)))
            t += rate
            k += 1
    return out


# ------------------------------------------------------------------ drums (GM notes)

GM = {"kick": 36, "rim": 37, "snare": 38, "clap": 39, "hat": 42, "pedal": 44, "open": 46, "crash": 49, "ride": 51, "conga_hi": 62,
      "conga_lo": 64, "timbale_hi": 65, "timbale_lo": 66, "shaker": 70, "tom_lo": 45, "tom_mid": 47, "tom_hi": 50,
      "syntom_hi": 48, "syntom_mid": 47, "syntom_lo": 43, "ghost": 40, "brk_kick": 35, "brk_snare": 40, "brk_hat": 44,
      "cowbell": 56, "clave": 75, "tamb": 54, "bongo_hi": 60, "bongo_lo": 61, "timbale": 65, "cymbal": 52, "cabasa": 69, "guiro": 73,
      "perc1": 76, "perc2": 77, "swell": 55}


def drum_bar(style: str, layers: set, fill: str | None, bar: int, rng, cfg) -> list[tuple]:
    """One bar of drums as (beat, sound, vel). Styles: house, synthpop, italo, breakbeat, boombap."""
    ev = []
    sw = cfg.get("swing", 0.5)
    s16 = lambda s: s / 4 + ((sw - 0.5) * 0.5 if s % 2 else 0.0)
    rnd = lambda v, sd=0.04: float(np.clip(v + rng.normal(0, sd), 0.05, 1.0))
    if style in ("house", "italo"):
        if "kick" in layers:
            ev += [(b, "kick", 1.0) for b in range(4)]
        if "clap" in layers:
            ev += [(1, "clap", rnd(0.88, 0.02)), (3, "clap", rnd(0.9, 0.02))]
        if "hat" in layers:
            ev += [(s16(s), "hat", rnd(0.6 if s % 4 == 2 else 0.4 if s % 2 else 0.48)) for s in range(16)]
        if "open" in layers:
            ev += [(b + 0.5, "open", rnd(0.6, 0.03)) for b in range(4)]
        if "shaker" in layers:
            ev += [(s16(s), "shaker", rnd(0.34 if s % 2 else 0.24, 0.03)) for s in range(16)]
        if "congas" in layers:
            fig = [(3, "conga_lo"), (6, "conga_hi"), (7, "conga_hi"), (10, "conga_lo"), (14, "conga_hi")] if bar % 2 == 0 else \
                  [(2, "conga_hi"), (3, "conga_lo"), (6, "conga_hi"), (11, "conga_lo"), (12, "conga_hi"), (14, "conga_hi"), (15, "conga_lo")]
            ev += [(s16(s), snd, rnd(0.55, 0.05)) for s, snd in fig]
        if "timbales" in layers:
            ev += [(s16(s), snd, v) for s, snd, v in ((5, "timbale_hi", 0.5), (9, "timbale_lo", 0.45), (13, "timbale_hi", 0.55))]
        if "break" in layers:                    # a filtered breakbeat riding on top of the four-to-the-floor (deep house)
            A = [(0, "brk_kick", 0.8), (2, "brk_kick", 0.6), (4, "brk_snare", 0.85), (7, "brk_snare", 0.35), (9, "brk_snare", 0.3),
                 (10, "brk_kick", 0.7), (12, "brk_snare", 0.85), (15, "brk_snare", 0.4)]
            B = [(2, "brk_kick", 0.7), (4, "brk_snare", 0.85), (6, "brk_snare", 0.35), (10, "brk_kick", 0.65), (11, "brk_snare", 0.3),
                 (12, "brk_snare", 0.85), (14, "brk_snare", 0.4), (15, "brk_snare", 0.5)]
            ev += [(s16(s), snd, rnd(v, 0.05)) for s, snd, v in (A if bar % 2 == 0 else B)]
            ev += [(s16(s), "brk_hat", rnd(0.5 if s % 4 == 2 else 0.32, 0.05)) for s in range(0, 16, 2)]
    elif style == "synthpop":
        if "kick" in layers:
            ev += [(0, "kick", 1.0), (2, "kick", 0.95), (2.5, "kick", 0.8)]
        if "four" in layers:
            ev = [e for e in ev if e[1] != "kick"] + [(b, "kick", 1.0 if b % 2 == 0 else 0.9) for b in range(4)]
        if "snare" in layers:
            ev += [(1, "snare", rnd(0.9, 0.02)), (3, "snare", rnd(0.92, 0.02))]
        if "clap" in layers:
            ev += [(1, "clap", 0.75), (3, "clap", 0.78)]
        if "hat" in layers:
            ev += [(s / 2, "hat", rnd(0.62 if s % 2 else 0.45, 0.03)) for s in range(8)]
        if "open" in layers:
            ev += [(3.5, "open", 0.6)]
    elif style == "breakbeat":                    # a two-bar jungle break: K . K . S . . S | . S K . S . . S
        A = [(0, "kick", 1.0), (2, "kick", 0.85), (4, "snare", 0.95), (7, "ghost", 0.35), (9, "ghost", 0.3), (10, "kick", 0.9),
             (12, "snare", 0.95), (15, "ghost", 0.4)]
        B = [(2, "kick", 0.9), (4, "snare", 0.95), (6, "ghost", 0.35), (10, "kick", 0.85), (11, "ghost", 0.3), (12, "snare", 0.95),
             (14, "ghost", 0.35), (15, "snare", 0.6)]
        if "break" in layers:
            ev += [(s16(s), snd, rnd(v, 0.05)) for s, snd, v in (A if bar % 2 == 0 else B)]
        if "ride" in layers:
            ev += [(s / 2, "ride", rnd(0.5 if s % 2 == 0 else 0.38)) for s in range(8)]
        if "hat" in layers:
            ev += [(s16(s), "hat", rnd(0.4 if s % 2 else 0.3)) for s in range(16)]
    elif style == "boombap":                      # lazy hip-hop: kick 1 and the 'a' of 2, snare 2 and 4
        if "kick" in layers:
            ev += [(0, "kick", rnd(0.95, 0.03)), (s16(7), "kick", rnd(0.75)), (2.5, "kick", rnd(0.8))]
        if "snare" in layers:
            ev += [(1, "snare", rnd(0.9, 0.03)), (3, "snare", rnd(0.92, 0.03))]
        if "hat" in layers:
            ev += [(s16(s * 2), "hat", rnd(0.55 if s % 2 == 0 else 0.4, 0.06)) for s in range(8)]
        if "rim" in layers:
            ev += [(s16(10), "rim", rnd(0.4))]
    elif style == "fusion":                       # 80s Japanese fusion: syncopated kick, ghost-note snare, 16th hats, open-hat pickups
        if "kick" in layers:
            ks = [0, 6, 8, 11] if bar % 2 == 0 else [0, 3, 8, 10, 14]
            ev += [(s16(s), "kick", rnd(1.0 if s in (0, 8) else 0.82, 0.03)) for s in ks]
        if "snare" in layers:
            ev += [(1, "snare", rnd(0.95, 0.02)), (3, "snare", rnd(0.95, 0.02))]
            ev += [(s16(s), "ghost", rnd(0.3, 0.05)) for s in ((2, 7, 9, 15) if bar % 2 == 0 else (5, 7, 13))]
        if "hat" in layers:
            ev += [(s16(s), "hat", rnd(0.62 if s % 4 == 0 else 0.5 if s % 2 == 0 else 0.34, 0.05)) for s in range(16)
                   if not ("open" in layers and s == 14 and bar % 2 == 1)]
        if "open" in layers and bar % 2 == 1:
            ev += [(s16(14), "open", rnd(0.6, 0.03))]
        if "ride" in layers:
            ev = [e for e in ev if e[1] != "hat"] + [(s / 2, "ride", rnd(0.62 if s % 2 == 0 else 0.45)) for s in range(8)]
    if style == "breakforge":                    # Breakforge's seeded, mutating break (synthesis/engines/breakforge.py)
        from synthesis.engines import breakforge
        ev += [(s16(int(s)) if float(s).is_integer() else s / 4, snd, v)
               for s, snd, v in breakforge.bar_steps(bar, cfg.get("seed", 0), cfg.get("breakforge"), layers)]
    if style == "electronium":                   # the Electronium's clock matrix plays the kit (electronium.py)
        ev += [(s16(s), snd, rnd(v, 0.03)) for s, snd, v in cfg["electronium"].drum_steps(layers, bar)]
    if style == "grid":                          # the song writes its own beat: {layer: [[step, vel, sound?], ...] or {"A": [...], "B": [...]}}
        grid = cfg.get("grid", {})
        if cfg.get("electronium"):               # layers the grid doesn't write, the Electronium's clocks play
            el = {x for x in layers if x not in grid}
            ev += [(s16(s), snd, rnd(v, 0.03)) for s, snd, v in cfg["electronium"].drum_steps(el, bar)]
        for layer in [x for x in grid if x in layers]:   # the grid's order: a set's order changes with the hash seed, and with it every rnd() draw
            pat = grid.get(layer)
            if pat is None:
                continue
            if isinstance(pat, dict):
                keys = sorted(pat)
                pat = pat[keys[bar % len(keys)]]
            for e in pat:
                snd = e[2] if len(e) > 2 else layer
                shift = (e[3] / (60000 / cfg.get("_bpm", 120))) if len(e) > 3 else 0.0     # a hit's own timing offset (ms)
                ev.append((s16(e[0]) + shift, snd, rnd(e[1], 0.04)))
    if fill == "fusion_fill":                     # a 16th run down the toms over beats 3-4, crash on the next downbeat
        ev = [e for e in ev if e[0] < 2] + [(2 + i / 4, t, 0.6 + 0.04 * i) for i, t in enumerate(
            ("snare", "snare", "tom_hi", "tom_hi", "tom_mid", "tom_mid", "tom_lo", "tom_lo"))]
    if fill == "toms":
        ev = [e for e in ev if e[0] < 3 or e[1] == "kick"] + [(3 + i / 4, t, 0.7) for i, t in enumerate(("tom_hi", "tom_mid", "tom_lo", "tom_lo"))]
    elif fill == "syntoms":
        ev = [e for e in ev if e[0] < 2] + [(2 + i / 2, t, 0.85) for i, t in enumerate(("syntom_hi", "syntom_mid", "syntom_lo", "syntom_lo"))]
    elif fill == "snare_roll":
        ev = [e for e in ev if e[0] < 2] + [(2 + s / 4, "snare", 0.4 + 0.07 * s) for s in range(8)]
    elif fill == "roll16":
        ev = [e for e in ev if e[1] == "kick"] + [(s / 4, "snare", 0.35 + 0.04 * s) for s in range(16)]
    elif fill == "drop":
        ev = [e for e in ev if e[0] < 3]
    hum = cfg.get("drum_humanize_ms", 0) / (60000 / cfg.get("_bpm", 120))
    return [(t, snd, v, rng.normal(0, hum) if hum and snd != "kick" else 0.0) for t, snd, v in ev]
