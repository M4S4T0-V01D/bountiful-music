"""Music theory: notes, chord symbols, chord scales, voicings and voice leading.

Everything downstream (bass, comping, melody, solo) asks this module what a chord *is* (its tones, its
guide tones, its scale), so the parts agree with each other harmonically instead of picking notes
independently.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def note(name: str) -> int:
    """'F2' -> 41, 'Eb5' -> 75 (MIDI, C4 = 60)."""
    m = re.fullmatch(r"([A-G])(#|b)?(-?\d)", name.strip())
    if not m:
        raise ValueError(f"bad note name {name!r}")
    return 12 * (int(m[3]) + 1) + PC[m[1]] + {"#": 1, "b": -1, None: 0}[m[2]]


def name(midi: int) -> str:
    return f"{NAMES[midi % 12]}{midi // 12 - 1}"


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


SCALES = {
    "ionian": [0, 2, 4, 5, 7, 9, 11],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "aeolian": [0, 2, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "lydian_dominant": [0, 2, 4, 6, 7, 9, 10],
    "altered": [0, 1, 3, 4, 6, 8, 10],
    "half_whole": [0, 1, 3, 4, 6, 7, 9, 10],
    "locrian_n2": [0, 2, 3, 5, 6, 8, 10],
    "melodic_minor": [0, 2, 3, 5, 7, 9, 11],
    "whole_half": [0, 2, 3, 5, 6, 8, 9, 11],
    # Japanese pentatonic modes. yo (bright, folk/festival) and in / miyako-bushi (dark, koto music),
    # each also listed from the other degrees, so a chord on any degree keeps the same global mode.
    "yo": [0, 2, 5, 7, 9],            # D: D E G A B
    "minpent": [0, 3, 5, 7, 10],      # yo from its 2nd degree (E)
    "majpent": [0, 2, 4, 7, 9],       # yo from its 4th degree (G)
    "egyptian": [0, 2, 5, 7, 10],     # yo from its 5th degree (A)
    "in": [0, 1, 5, 7, 8],            # D: D Eb G A Bb (miyako-bushi)
    "hirajoshi": [0, 2, 3, 7, 8],     # in from G
    "iwato": [0, 1, 5, 6, 10],        # in from A
    "kumoi": [0, 4, 5, 9, 11],        # in from Bb
    "lydpent": [0, 4, 6, 7, 11],      # in from Eb
}

MODAL = {"yo", "minpent", "majpent", "egyptian", "in", "hirajoshi", "iwato", "kumoi", "lydpent"}

# quality -> (all chord tones as intervals, preferred rootless voicing intervals, chord scale)
# Rootless voicings are the Rhodes player's left hand: guide tones (3rd + 7th) plus colour tones,
# leaving the root to the bass.
QUALITIES = {
    "maj7":    ([0, 4, 7, 11],          [4, 7, 11, 14],  "ionian"),
    "maj9":    ([0, 4, 7, 11, 14],      [4, 7, 11, 14],  "ionian"),
    "maj7#11": ([0, 4, 7, 11, 18],      [4, 11, 14, 18], "lydian"),
    "maj9#11": ([0, 4, 7, 11, 14, 18],  [4, 11, 14, 18], "lydian"),
    "6/9":     ([0, 4, 7, 9, 14],       [4, 9, 14, 19],  "ionian"),
    "6":       ([0, 4, 7, 9],           [4, 7, 9, 14],   "ionian"),
    "sus2":    ([0, 2, 7],              [2, 7, 12, 14],  "ionian"),
    "add9":    ([0, 4, 7, 14],          [4, 7, 12, 14],  "ionian"),
    "m7":      ([0, 3, 7, 10],          [3, 7, 10, 14],  "dorian"),
    "m9":      ([0, 3, 7, 10, 14],      [3, 7, 10, 14],  "dorian"),
    "m11":     ([0, 3, 7, 10, 14, 17],  [5, 10, 15, 19], "dorian"),   # the "So What" voicing: 4th, b7, b3, 5th stacked
    "m6":      ([0, 3, 7, 9],           [3, 7, 9, 14],   "dorian"),
    "mmaj9":   ([0, 3, 7, 11, 14],      [3, 7, 11, 14],  "melodic_minor"),
    "7":       ([0, 4, 7, 10],          [4, 7, 10, 14],  "mixolydian"),
    "9":       ([0, 4, 7, 10, 14],      [4, 10, 14, 19], "mixolydian"),
    "13":      ([0, 4, 7, 10, 14, 21],  [4, 10, 14, 21], "mixolydian"),
    "9#11":    ([0, 4, 7, 10, 14, 18],  [4, 10, 14, 18], "lydian_dominant"),
    "13sus":   ([0, 5, 7, 10, 14, 21],  [5, 10, 14, 21], "mixolydian"),
    "7sus":    ([0, 5, 7, 10],          [5, 10, 14, 19], "mixolydian"),
    "7b9":     ([0, 4, 7, 10, 13],      [4, 10, 13, 19], "half_whole"),
    "13b9":    ([0, 4, 7, 10, 13, 21],  [4, 10, 13, 21], "half_whole"),
    "7#9":     ([0, 4, 7, 10, 15],      [4, 10, 15, 19], "half_whole"),
    "7alt":    ([0, 4, 10, 13, 15, 20], [4, 10, 15, 20], "altered"),
    "m7b5":    ([0, 3, 6, 10],          [3, 6, 10, 14],  "locrian_n2"),
    "m9b5":    ([0, 3, 6, 10, 14],      [3, 6, 10, 14],  "locrian_n2"),
    "dim7":    ([0, 3, 6, 9],           [3, 6, 9, 14],   "whole_half"),
    # modal 'chords' (open fifths / fourths) carrying a Japanese mode; voicings are koto-style dyads + octave
    "5y":      ([0, 7],                 [7, 12, 14],     "yo"),
    "5m":      ([0, 7],                 [7, 10, 12],     "minpent"),
    "5M":      ([0, 7],                 [7, 12, 16],     "majpent"),
    "5e":      ([0, 7],                 [5, 7, 12],      "egyptian"),
    "5i":      ([0, 7],                 [7, 8, 12],      "in"),
    "5h":      ([0, 7],                 [3, 7, 12],      "hirajoshi"),
    "4w":      ([0, 5],                 [5, 10, 13],     "iwato"),
    "3k":      ([0, 4],                 [4, 9, 12],      "kumoi"),
    "5l":      ([0, 7],                 [7, 11, 12],     "lydpent"),
}


@dataclass(frozen=True)
class Chord:
    symbol: str
    root: int          # pitch class
    quality: str
    bass: int          # pitch class of the bass note (slash chords)

    @property
    def tones(self) -> list[int]:
        return [(self.root + i) % 12 for i in QUALITIES[self.quality][0]]

    @property
    def scale(self) -> list[int]:
        return sorted({(self.root + i) % 12 for i in SCALES[QUALITIES[self.quality][2]]})

    @property
    def scale_name(self) -> str:
        return QUALITIES[self.quality][2]

    @property
    def guide(self) -> list[int]:
        """3rd (or sus 4th) and 7th (or 6th): the notes that define the chord's function."""
        iv = QUALITIES[self.quality][0]
        if self.scale_name in MODAL:
            # no 3rd/7th in a modal fifth: the mode's 'colour' degrees play that role
            sc = SCALES[self.scale_name]
            return [(self.root + sc[2]) % 12, (self.root + sc[-1]) % 12]
        third = next(i for i in iv if i in (3, 4, 5))
        seventh = next((i for i in iv if i in (9, 10, 11) and not (self.quality.startswith("6") and i == 9)), 9)
        return [(self.root + third) % 12, (self.root + seventh) % 12]

    @property
    def is_dominant(self) -> bool:
        iv = QUALITIES[self.quality][0]
        return 4 in iv and 10 in iv or self.quality in ("7sus", "13sus")

    def degree_of(self, midi: int) -> tuple[int, int]:
        """Express a pitch as (scale degree index, chromatic offset) relative to this chord's scale."""
        rel = (midi - self.root) % 12
        sc = SCALES[QUALITIES[self.quality][2]]
        best = min(range(len(sc)), key=lambda i: (abs(rel - sc[i]), sc[i] > rel))
        return best, rel - sc[best]


_SYMBOL = re.compile(r"([A-G])(#|b)?(5y|5m|5M|5e|5i|5h|4w|3k|5l|maj9#11|add9|sus2|maj7#11|maj9|maj7|6/9|mmaj9|m11|m9b5|m9|m7b5|m7|m6|13sus|7sus|13b9|7b9|7#9|7alt|9#11|13|9|7|dim7|6)(?:/([A-G](?:#|b)?))?$")


def chord(symbol: str) -> Chord:
    m = _SYMBOL.fullmatch(symbol.strip())
    if not m:
        raise ValueError(f"unknown chord symbol {symbol!r}")
    root = (PC[m[1]] + {"#": 1, "b": -1, None: 0}[m[2]]) % 12
    bass = root
    if m[4]:
        bass = (PC[m[4][0]] + {"#": 1, "b": -1}.get(m[4][1:], 0)) % 12
    return Chord(symbol.strip(), root, m[3], bass)


def fit(pc: int, near: float) -> int:
    """The MIDI note with pitch class `pc` closest to `near`."""
    base = int(round(near))
    up = base + ((pc - base) % 12)
    return up if up - near <= near - (up - 12) else up - 12


def scale_notes(ch: Chord, lo: int, hi: int) -> list[int]:
    pcs = set(ch.scale)
    return [n for n in range(lo, hi + 1) if n % 12 in pcs]


def chord_notes(ch: Chord, lo: int, hi: int) -> list[int]:
    pcs = set(ch.tones)
    return [n for n in range(lo, hi + 1) if n % 12 in pcs]


def map_degree(midi: int, src: Chord, dst: Chord) -> int:
    """Diatonic transposition: move a melody note to the same chord-scale degree over another chord.

    This is how a motif written over one chord is re-fitted to a different chord while keeping its
    contour and its relationship to the harmony (a 9th stays a 9th, a guide tone stays a guide tone).
    """
    deg, off = src.degree_of(midi)
    sc = SCALES[QUALITIES[dst.quality][2]]
    rel = sc[deg % len(sc)] + off
    target = (dst.root + rel) % 12
    return fit(target, midi)


# ---------------------------------------------------------------- voicings and voice leading

LOW_INTERVAL_LIMIT = {52: 3, 47: 4, 0: 7}  # below E3 no seconds, below B2 nothing tighter than a 4th


def _muddy(v: list[int]) -> bool:
    for a, b in zip(v, v[1:]):
        for floor, limit in LOW_INTERVAL_LIMIT.items():
            if a < floor + 12 and a >= floor and b - a < limit:
                return True
    return False


def voicing_candidates(ch: Chord, lo: int, hi: int, spread: bool = False) -> list[list[int]]:
    """All close and drop-2 placements of the chord's rootless voicing inside [lo, hi]."""
    ivs = QUALITIES[ch.quality][1]
    pcs = [(ch.root + i) % 12 for i in ivs]
    out = []
    for rot in range(len(pcs)):
        order = pcs[rot:] + pcs[:rot]
        for start in range(lo, hi + 1):          # every octave the bottom note can sit in, not just the lowest
            if start % 12 != order[0]:
                continue
            v = [start]
            for pc in order[1:]:
                v.append(v[-1] + ((pc - v[-1]) % 12 or 12))
            forms = [v]
            if len(v) >= 4:
                d2 = sorted(v[:-2] + [v[-2] - 12] + v[-1:])
                forms.append(d2)
            if spread and len(v) >= 4:
                forms.append(sorted([v[0] - 12] + v[1:]))
            for f in forms:
                if f[0] >= lo and f[-1] <= hi and not _muddy(f):
                    out.append(f)
    uniq = {tuple(f) for f in out}
    return [list(f) for f in sorted(uniq)]


def lead_cost(prev: list[int] | None, nxt: list[int], top_target: float | None, top_weight: float = 0.6) -> float:
    cost = 0.0
    if prev:
        a, b = sorted(prev), sorted(nxt)
        if len(a) == len(b):
            cost += sum(abs(x - y) for x, y in zip(a, b))
        else:
            cost += sum(min(abs(x - y) for y in b) for x in a) + sum(min(abs(x - y) for x in a) for y in b)
        common = len(set(a) & set(b))
        cost -= 1.5 * common          # reward common tones held over
    if top_target is not None:
        cost += top_weight * abs(nxt[-1] - top_target)
    return cost


def voice_lead(chords: list[Chord], lo: int = 50, hi: int = 79, top_target: float = 72,
               start: list[int] | None = None, top_weight: float = 0.6) -> list[list[int]]:
    """Pick a voicing for every chord so the voices move as little as possible (smooth voice leading),
    while the top voice stays near a target register."""
    out: list[list[int]] = []
    prev = start
    for i, ch in enumerate(chords):
        cands = voicing_candidates(ch, lo, hi)
        if not cands:
            cands = voicing_candidates(ch, lo - 6, hi + 6)
        tt = top_target[i % len(top_target)] if isinstance(top_target, (list, tuple)) else top_target
        best = min(cands, key=lambda v: lead_cost(prev, v, tt, top_weight))
        out.append(best)
        prev = best
    return out


# ---------------------------------------------------------------- progressions


@dataclass
class Slot:
    """One chord occupying a span of a section, in beats from the section start."""
    chord: Chord
    start: float
    beats: float


def parse_progression(bars: list[str], beats_per_bar: int = 4) -> list[Slot]:
    """['Fm9', 'Gm7b5 C7alt', 'Eb13sus:3 Eb13:1', 'Dbmaj9:8'] -> slots.

    A bar holding several chords splits evenly unless durations are given; '-' holds the previous
    chord through another bar.
    """
    slots: list[Slot] = []
    pos = 0.0
    for bar in bars:
        bar = bar.strip()
        if bar == "-":
            slots[-1].beats += beats_per_bar
            pos += beats_per_bar
            continue
        toks = bar.split()
        given = [float(t.split(":")[1]) if ":" in t else None for t in toks]
        free = beats_per_bar - sum(g for g in given if g is not None)
        n_free = sum(g is None for g in given)
        span = 0.0
        for tok, g in zip(toks, given):
            b = g if g is not None else free / n_free
            slots.append(Slot(chord(tok.split(":")[0]), pos + span, b))
            span += b
        pos += max(span, beats_per_bar)
    return slots


def chord_at(slots: list[Slot], beat: float) -> Slot:
    for s in slots:
        if s.start <= beat + 1e-6 < s.start + s.beats:
            return s
    return slots[-1] if beat >= slots[-1].start else slots[0]


def next_slot(slots: list[Slot], s: Slot) -> Slot | None:
    i = slots.index(s)
    return slots[i + 1] if i + 1 < len(slots) else None
