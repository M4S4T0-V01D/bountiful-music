"""Composition: harmony variation, comping, basslines, melody development, counter-lines and solos.

Positions are in beats from the start of the song; one 16th = 0.25 beat. Every generator takes a
seeded numpy Generator so a song re-renders identically from its config.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from . import theory as th
from .theory import Chord, Slot


@dataclass
class Note:
    beat: float            # grid position (beats from song start)
    dur: float             # beats
    pitch: int
    vel: float             # 0..1
    part: str
    slide: bool = False    # glide/slur from the previous note
    shift: float = 0.0     # microtiming in seconds (humanisation), on top of swing
    tag: str = ""


S16 = 0.25


def humanize(notes: list[Note], rng, ms: float = 6.0, vel: float = 0.06) -> list[Note]:
    for n in notes:
        n.shift += rng.normal(0, ms / 1000)
        n.vel = float(np.clip(n.vel + rng.normal(0, vel), 0.05, 1.0))
    return notes


# ======================================================================== harmony variation

def vary_progression(slots: list[Slot], rng, amount: float, melody: list[tuple[float, int]] | None = None) -> list[Slot]:
    """Re-harmonise a progression the way a jazz player would on a repeat:
    colour swaps (m9 <-> m11, maj9 <-> maj7#11 / 6/9, 13 <-> 9 / 13sus->13), tritone substitution of
    dominants resolving down a fifth, and chromatic approach chords a half-step above the next chord.

    With a `melody` ((beat, pitch) pairs), a substitution is only accepted if every melody note it
    sits under still belongs to the new chord's scale: the harmony bends to the tune, never the reverse."""
    if amount <= 0:
        return [replace(s) for s in slots]
    melody = melody or []

    def fits(ch: Chord, start: float, beats: float, orig: Chord) -> bool:
        for b, p in melody:
            if start - 1e-6 <= b < start + beats - 1e-6:
                if p % 12 not in ch.scale and p % 12 in orig.scale:
                    return False
        return True

    out: list[Slot] = []
    swaps = {"m9": ["m11"], "m11": ["m9"], "maj9": ["maj7#11", "6/9"], "maj7#11": ["maj9#11"],
             "13": ["9", "13sus|13"], "9": ["13"], "7alt": ["7#9", "13b9"], "7#9": ["7alt"], "7b9": ["7alt", "13b9"]}
    for i, s in enumerate(slots):
        nxt = slots[i + 1] if i + 1 < len(slots) else None
        ch = s.chord
        name_root = th.NAMES[ch.root]
        r = rng.random()
        # tritone sub: X7 -> (X+6)9#11 when it resolves down a fifth
        if ch.is_dominant and nxt and (nxt.chord.root - ch.root) % 12 == 5 and r < amount * 0.5:
            for q in ("9#11", "7alt", "13"):
                sub = th.chord(f"{th.NAMES[(ch.root + 6) % 12]}{q}")
                if fits(sub, s.start, s.beats, ch):
                    out.append(Slot(sub, s.start, s.beats))
                    break
            else:
                out.append(Slot(ch, s.start, s.beats))
            continue
        q = ch.quality
        if q in swaps and r < amount * 0.9:
            choice = swaps[q][int(rng.integers(len(swaps[q])))]
            if "|" in choice and s.beats >= 2 and fits(th.chord(name_root + choice.split("|")[0]), s.start, s.beats / 2, ch):
                a, b = choice.split("|")
                out.append(Slot(th.chord(name_root + a), s.start, s.beats / 2))
                out.append(Slot(th.chord(name_root + b), s.start + s.beats / 2, s.beats / 2))
                continue
            if "|" not in choice and fits(th.chord(name_root + choice), s.start, s.beats, ch):
                ch = th.chord(name_root + choice)
        # chromatic approach chord on the last beat of a long chord
        if nxt and s.beats >= 4 and rng.random() < amount * 0.35 and not ch.is_dominant:
            above = th.chord(f"{th.NAMES[(nxt.chord.root + 1) % 12]}{nxt.chord.quality}")
            if not fits(above, s.start + s.beats - 1, 1, ch):
                out.append(Slot(ch, s.start, s.beats))
                continue
            out.append(Slot(ch, s.start, s.beats - 1))
            out.append(Slot(above, s.start + s.beats - 1, 1))
            continue
        out.append(Slot(ch, s.start, s.beats))
    return out


# ======================================================================== comping

COMP = {
    # (step, length in 16ths, velocity, push) — push=True anticipates the next chord.
    # Patient by design: a strike on the change, held, and at most one answer in the bar.
    "sparse": [[(0, 14, .55, 0)], [(0, 8, .5, 0)], [(2, 12, .5, 0)]],
    "vamp": [[(0, 8, .58, 0)], [(0, 3, .58, 0), (10, 6, .5, 0)], [(3, 8, .52, 0)], [(0, 6, .58, 0), (14, 2, .55, 1)]],
    "funk": [[(0, 4, .66, 0), (10, 4, .56, 0)], [(0, 3, .64, 0), (6, 6, .56, 0)], [(3, 6, .58, 0)], [(0, 8, .64, 0), (14, 2, .6, 1)]],
    "jazz": [[(0, 8, .58, 0)], [(3, 6, .54, 0)], [(0, 3, .58, 0), (10, 6, .5, 0)], [(6, 8, .52, 0)]],
    "lift": [[(0, 6, .66, 0), (10, 4, .56, 0)], [(0, 3, .64, 0), (6, 8, .58, 0)], [(2, 6, .6, 0), (14, 2, .6, 1)]],
    "ballad": [[(0, 16, .5, 0)], [(0, 8, .5, 0), (8, 8, .42, 0)], [(0, 12, .48, 0), (12, 4, .4, 0)]],
}


def section_voicings(slots: list[Slot], prev: list[int] | None, lo=50, hi=79, top=72) -> tuple[list[list[int]], list[int]]:
    vs = th.voice_lead([s.chord for s in slots], lo, hi, top, prev)
    return vs, vs[-1]


def comp(slots: list[Slot], voicings: list[list[int]], start: float, bars: int, style: str, rng,
         part: str = "rhodes", strum_ms: float = 9.0, motion: float = 0.0, cycle: bool = False) -> list[Note]:
    pats = COMP[style]
    notes: list[Note] = []
    skip_first = False
    for bar in range(bars):
        if cycle:   # a fixed, recognisable figure: pattern 1, 2, 1, 2 ...
            pat = pats[bar % len(pats)]
        else:
            pat = pats[int(rng.integers(len(pats)))] if bar % 4 != 0 else pats[0]
        b0 = bar * 4
        hits = list(pat)
        # make sure every chord in the bar is struck at least once
        for s in slots:
            if b0 <= s.start < b0 + 4 and s.start > b0:
                st = int(round((s.start - b0) / S16))
                if not any(abs(h[0] - st) <= 1 for h in hits):
                    hits = [h for h in hits if h[0] < st] + [(st, int(s.beats / S16) - 1, .62, 0)] + [h for h in hits if h[0] > st + 2]
        for step, length, vel, push in hits:
            if step == 0 and skip_first:
                continue
            pos = b0 + step * S16
            slot = th.chord_at(slots, pos)
            if push:
                nx = th.next_slot(slots, slot)
                if nx is None or abs(nx.start - (b0 + 4)) > 1e-6:
                    push = 0
                else:
                    slot = nx
            vi = slots.index(slot)
            v = voicings[vi]
            if push:
                length = length + 4  # tie into the next bar
            end = min(pos + length * S16, (slot.start + slot.beats) if not push else slot.start + min(slot.beats, 2))
            dur = max(end - pos, S16) * 0.95
            moving = motion and dur >= 0.5 and rng.random() < motion
            for k, pitch in enumerate(v):
                top = k == len(v) - 1
                d = dur / 2 if (moving and top) else dur
                notes.append(Note(start + pos, d, pitch, vel * (0.92 + 0.1 * top), part,
                                  shift=k * strum_ms / 1000 * rng.uniform(0.5, 1.2)))
            if moving:
                # the top voice steps to a neighbouring chord-scale tone halfway through the chord
                ch = slot.chord
                top_p = v[-1]
                cands = [x for x in th.scale_notes(ch, top_p - 3, top_p + 3) if x != top_p and x not in v]
                if cands:
                    down = [x for x in cands if x < top_p]
                    nxt_p = (down[-1] if down and rng.random() < 0.7 else min(cands, key=lambda x: abs(x - top_p)))
                    half = max(S16, round((dur / 2) / S16) * S16)      # on the 16th grid, in the groove
                    for n_ in notes[-len(v):]:
                        if n_.pitch == top_p and abs(n_.beat - (start + pos)) < 1e-6:
                            n_.dur = half
                    notes.append(Note(start + pos + half, max(dur - half, S16), nxt_p, vel * 0.85, part, tag="legato"))
        skip_first = any(h[3] for h in hits)
    return notes


def pad_part(slots: list[Slot], voicings, start: float, part="pad", vel=0.5) -> list[Note]:
    out = []
    for s, v in zip(slots, voicings):
        for pitch in v:
            out.append(Note(start + s.start, s.beats, pitch, vel, part))
        out.append(Note(start + s.start, s.beats, v[-1] - 12 if v[-1] - 12 > v[0] else v[0], vel * 0.7, part))
    return out


def stabs(slots: list[Slot], voicings, start: float, bars: int, rng, part="piano") -> list[Note]:
    """Rave-piano stabs: the voicing raised an octave with the top note doubled, in a house rhythm."""
    pats = [[0, 3, 6, 10], [0, 6, 10, 14], [2, 6, 8, 12]]
    out = []
    for bar in range(bars):
        pat = pats[bar % len(pats)] if rng.random() < 0.8 else pats[0]
        for st in pat:
            pos = bar * 4 + st * S16
            slot = th.chord_at(slots, pos)
            v = [p + 12 for p in voicings[slots.index(slot)]]
            v = v + [v[-1] - 12 if v[-1] - 12 not in v else v[-1] + 12]
            for p in v:
                out.append(Note(start + pos, S16 * 1.6, p, 0.62 + 0.15 * (st == 0), part))
    return out


# ======================================================================== bass

BASS = {
    # (step, token, length 16ths, velocity)
    "sub": [[(0, "R", 10, .9), (10, "R", 3, .6), (14, "N", 2, .8)], [(0, "R", 14, .9), (14, "A", 2, .7)]],
    "hook": [[(0, "R", 3, 1.0), (3, "O", 1, .5), (6, "7", 2, .8), (8, "5", 3, .85), (11, "R", 2, .7), (14, "A", 2, .8)],
             [(0, "R", 4, 1.0), (4, "R", 1, .45), (6, "5", 2, .75), (10, "O", 2, .7), (12, "7", 2, .7), (14, "A", 2, .8)]],
    "response": [[(0, "R", 3, 1.0), (4, "5", 2, .7), (7, "S", 1, .6), (8, "S", 2, .75), (10, "S", 2, .75), (12, "S", 2, .8), (14, "A", 2, .85)],
                 [(0, "R", 2, 1.0), (3, "O", 2, .6), (6, "7", 2, .7), (8, "5", 2, .75), (10, "S", 2, .75), (12, "S", 1, .7), (13, "S", 1, .7), (14, "A", 2, .85)]],
    "walk": [[(0, "R", 4, .9), (4, "W", 4, .72), (8, "W", 4, .78), (12, "A", 4, .8)],
             [(0, "R", 4, .9), (4, "W", 3, .7), (7, "W", 1, .45), (8, "W", 4, .76), (12, "A", 4, .8)]],
    "lift": [[(0, "R", 3, 1.0), (3, "R", 1, .5), (6, "O", 2, .7), (8, "5", 3, .8), (11, "9", 1, .55), (12, "7", 2, .7), (14, "A", 2, .8)],
             [(0, "R", 2, 1.0), (2, "O", 2, .6), (4, "R", 2, .7), (6, "5", 2, .7), (8, "7", 4, .8), (12, "5", 2, .7), (14, "A", 2, .8)]],
    "half": [[(0, "R", 6, .95), (6, "R", 2, .55), (10, "5", 4, .7), (14, "N", 2, .8)]],
}


def _bass_root(pc: int, prev: int | None, lo=28, hi=40) -> int:
    near = prev if prev is not None else 34
    m = th.fit(pc, near)
    while m < lo:
        m += 12
    while m > hi:
        m -= 12
    return m


def bassline(slots: list[Slot], start: float, bars: int, style: str, rng, part="bass",
             response_every: int = 4, prev_root: int | None = None) -> tuple[list[Note], int | None]:
    """A syncopated, chord-aware bassline: cells of scale-degree tokens resolved against the chord at
    each step, with chromatic approach notes into chord changes and an answering run every few bars."""
    notes: list[Note] = []
    root_prev = prev_root
    skip_first = False
    walk_note: int | None = None
    for bar in range(bars):
        b0 = bar * 4
        is_resp = style in ("hook", "lift") and response_every and bar % response_every == response_every - 1
        cells = BASS["response"] if is_resp else BASS[style]
        cell = cells[int(rng.integers(len(cells)))] if bar % 2 else cells[0]
        hits = list(cell)
        for s in slots:
            if b0 < s.start < b0 + 4:
                st = int(round((s.start - b0) / S16))
                if not any(h[0] == st for h in hits):
                    hits = [h for h in hits if h[0] < st] + [(st, "R", 2, .9)] + [(h[0], h[1], h[2], h[3]) for h in hits if h[0] > st]
        hits.sort(key=lambda h: h[0])
        for i, (step, tok, length, vel) in enumerate(hits):
            if step == 0 and skip_first:
                continue
            pos = b0 + step * S16
            slot = th.chord_at(slots, pos)
            ch = slot.chord
            nx = th.next_slot(slots, slot)
            root = _bass_root(ch.bass, root_prev)
            next_root = _bass_root(nx.chord.bass, root) if nx else root
            if tok == "R":
                p = root
            elif tok == "O":
                p = root + 12
            elif tok == "5":
                p = root + 7 if 7 in th.QUALITIES[ch.quality][0] else root + 6
            elif tok == "7":
                iv = th.QUALITIES[ch.quality][0]
                sev = next((x for x in iv if x in (9, 10, 11)), 10)
                p = root + sev
            elif tok == "9":
                p = root + 14 if root + 14 <= 52 else root + 2
            elif tok == "N":
                p = next_root
            elif tok == "A":
                tgt = next_root if (nx and nx.start <= b0 + 4 + 1e-6) else root
                prev_p = notes[-1].pitch if notes else root
                p = tgt - 1 if prev_p < tgt or rng.random() < 0.4 else tgt + 1
                if rng.random() < 0.3:  # scale-step approach instead of chromatic
                    sc = th.scale_notes(ch, tgt - 3, tgt + 3)
                    cand = [x for x in sc if x != tgt and abs(x - tgt) <= 2]
                    if cand:
                        p = cand[int(rng.integers(len(cand)))]
            elif tok in ("S", "W"):
                # step through the chord scale towards the next root
                prev_p = notes[-1].pitch if notes else root
                tgt = next_root + (12 if next_root < prev_p - 7 else 0)
                sc = th.scale_notes(ch, 26, 55)
                direction = 1 if tgt >= prev_p else -1
                cand = [x for x in sc if (x - prev_p) * direction > 0]
                if tok == "W":  # walking: favour chord tones
                    ct = [x for x in cand if x % 12 in ch.tones]
                    cand = (ct[:2] if direction > 0 else ct[-2:]) or cand
                if not cand:
                    cand = [prev_p + direction * 2]
                p = cand[0] if direction > 0 else cand[-1]
            else:
                p = root
            while p > 55:
                p -= 12
            while p < 26:
                p += 12
            dur = length * S16
            if tok == "N":
                dur += 4 * S16 * 0.5
            slide = tok in ("A", "S") and rng.random() < 0.25
            notes.append(Note(start + pos, dur * 0.92, p, vel, part, slide=slide))
            if tok == "R":
                root_prev = root
        skip_first = any(h[1] == "N" for h in hits)
    # trim overlaps: monophonic line
    for a, b in zip(notes, notes[1:]):
        if a.beat + a.dur > b.beat:
            a.dur = max(b.beat - a.beat - 0.02, 0.1)
    return notes, root_prev


# ======================================================================== melody: phrases and development

def parse_phrase(bars: list[str], part: str, start: float = 0.0) -> list[Note]:
    """['2:C5:2 4:Eb5:2', '0:F5:5'] -> notes. Each token is step:note:length (16ths) within its bar;
    an optional 4th field is velocity (0..1)."""
    out = []
    for i, bar in enumerate(bars):
        for tok in bar.split():
            f = tok.split(":")
            vel = float(f[3]) if len(f) > 3 else 0.72
            out.append(Note(start + i * 4 + int(f[0]) * S16, int(f[2]) * S16, th.note(f[1]), vel, part))
    return out


def refit(phrase: list[Note], src: list[Slot], dst: list[Slot], src_start: float, dst_start: float) -> list[Note]:
    """Move a phrase written over `src` changes onto `dst` changes, degree by degree."""
    out = []
    for n in phrase:
        rel = n.beat - src_start
        a = th.chord_at(src, rel).chord
        b = th.chord_at(dst, rel).chord
        out.append(replace(n, beat=dst_start + rel, pitch=th.map_degree(n.pitch, a, b)))
    return out


def fix_avoid(phrase: list[Note], slots: list[Slot], start: float) -> list[Note]:
    """On strong positions, nudge 'avoid notes' (e.g. the natural 11th over a major/dominant chord,
    a b9 over a minor chord) to the nearest chord tone."""
    for n in phrase:
        pos = n.beat - start
        ch0 = th.chord_at(slots, max(pos, 0)).chord
        if ch0.scale_name in th.MODAL and n.pitch % 12 not in ch0.scale:
            # modal music: every note (graces included) comes from the mode; take the neighbour below
            below = [x for x in th.scale_notes(ch0, n.pitch - 4, n.pitch) if x < n.pitch]
            n.pitch = below[-1] if below else min(th.scale_notes(ch0, n.pitch, n.pitch + 4))
            continue
        strong = abs((pos * 2) - round(pos * 2)) < 1e-6 and n.dur >= 0.5
        if not strong:
            continue
        ch = th.chord_at(slots, pos).chord
        rel = (n.pitch - ch.root) % 12
        major = 4 in th.QUALITIES[ch.quality][0]
        bad = (major and rel == 5 and "sus" not in ch.quality) or (not major and rel == 1) or (rel == 11 and ch.quality.endswith(("7", "9", "13")) and ch.is_dominant)
        if ch.scale_name in th.MODAL:
            bad = False   # modal music: anything in the mode is fair, only out-of-mode notes move
        if bad or n.pitch % 12 not in ch.scale:
            cands = th.chord_notes(ch, n.pitch - 3, n.pitch + 3)
            if cands:
                n.pitch = min(cands, key=lambda c: abs(c - n.pitch))
    return phrase


def displace(phrase: list[Note], steps: int) -> list[Note]:
    return [replace(n, beat=n.beat + steps * S16) for n in phrase]


def transpose(phrase: list[Note], semis: int) -> list[Note]:
    return [replace(n, pitch=n.pitch + semis) for n in phrase]


def ornament(phrase: list[Note], rng, prob: float = 0.3) -> list[Note]:
    """Jazz ornaments: chromatic grace notes from below and occasional 'fall' repeats on long notes."""
    out = []
    for n in phrase:
        if n.dur >= 0.5 and rng.random() < prob:
            g = replace(n, beat=n.beat - S16 / 2, dur=S16 / 2, pitch=n.pitch - (1 if rng.random() < 0.7 else 2), vel=n.vel * 0.7, tag="grace")
            out.append(g)
        out.append(n)
    return out


def rhythm_vary(phrase: list[Note], rng, prob: float = 0.3) -> list[Note]:
    """Split some long notes into a syncopated repeated-note figure, and anticipate some downbeats."""
    out = []
    for n in phrase:
        if n.dur >= 1.0 and rng.random() < prob:
            a = replace(n, dur=S16 * 3)
            b = replace(n, beat=n.beat + S16 * 3, dur=n.dur - S16 * 3, vel=n.vel * 0.85)
            out += [a, b]
        elif abs(n.beat % 4) < 1e-6 and rng.random() < prob * 0.6:
            out.append(replace(n, beat=n.beat - S16, dur=n.dur + S16))
        else:
            out.append(n)
    return out


def window(phrase: list[Note], a: float, b: float) -> list[Note]:
    return [n for n in phrase if a - 1e-6 <= n.beat < b - 1e-6]


# ======================================================================== counter-melody (call and response)

def answers(lead: list[Note], slots: list[Slot], start: float, length: float, rng, part="vibes",
            lo=60, hi=86, min_gap=1.5, density=0.8) -> list[Note]:
    """Fill the lead's breathing spaces with short replies: an imitation of the lead's last gesture a
    third or sixth away (refitted to the harmony), or a descending chord-tone figure."""
    out: list[Note] = []
    lead = sorted(lead, key=lambda n: n.beat)
    gaps = []
    for i, n in enumerate(lead):
        end = n.beat + n.dur
        nxt = lead[i + 1].beat if i + 1 < len(lead) else start + length
        if nxt - end >= min_gap:
            gaps.append((end, nxt, i))
    if not lead:
        gaps = [(start + b * 4 + 2, start + b * 4 + 4, -1) for b in range(int(length // 4)) if b % 2 == 1]
    for a, b, i in gaps:
        if rng.random() > density:
            continue
        t0 = np.ceil((a + S16) / S16 * 0.5) * S16 * 2  # land on an 8th after the lead stops
        if b - t0 < 0.75:
            continue
        ch = th.chord_at(slots, t0 - start).chord
        if i >= 0 and rng.random() < 0.55 and i >= 2:
            gest = lead[i - 2:i + 1]
            shift = rng.choice([-3, -4, 3, 4, -8, -9])
            g0 = gest[0].beat
            for g in gest:
                pos = t0 + (g.beat - g0)
                if pos >= b - S16:
                    break
                c2 = th.chord_at(slots, pos - start).chord
                p = th.fit(int(rng.choice(c2.tones)), g.pitch + shift)
                cands = th.scale_notes(c2, g.pitch + shift - 2, g.pitch + shift + 2)
                if cands:
                    p = min(cands, key=lambda c: abs(c - (g.pitch + shift)))
                out.append(Note(pos, min(g.dur, b - pos), int(np.clip(p, lo, hi)), 0.55, part))
        else:
            tones = th.chord_notes(ch, lo + 7, hi - 5)
            top = tones[int(rng.integers(len(tones) // 2, len(tones)))] if tones else 74
            figure = [x for x in tones if x <= top][-int(rng.integers(2, 5)):][::-1]
            rhythms = [[0, 2, 3], [0, 1, 3], [0, 2, 4, 6], [0, 3, 6]]
            rhythm = rhythms[int(rng.integers(len(rhythms)))]
            for k, p in enumerate(figure):
                if k >= len(rhythm):
                    break
                pos = t0 + rhythm[k] * S16
                if pos >= b - S16:
                    break
                out.append(Note(pos, S16 * 2, p, 0.5 - 0.05 * k, part))
    return out


# ======================================================================== solo

RHYTHMS = [
    [0, 2, 3, 4, 6, 8],                # 8ths with a 16th kick
    [0, 1, 2, 3, 4, 6, 7],             # run then breath
    [2, 4, 6, 7, 8, 10, 12],           # off-beat entry
    [0, 3, 6, 8, 10],                  # syncopated
    [0, 2, 4, 5, 6, 7, 8, 10, 12, 14],  # long line
    [1, 2, 4, 6, 9, 10, 12],
]


def solo(slots: list[Slot], start: float, bars: int, rng, part="rhodes_solo", lo=62, hi=89,
         motif: list[Note] | None = None, motif_slots: list[Slot] | None = None) -> list[Note]:
    """A phrase-based improvisation: 1–2 bar phrases separated by breaths, built as a guided walk over
    the chord scale (chord tones on strong beats, enclosures into new chords, leaps answered by steps
    the other way), climbing in register and density through the solo, with one quote of the theme."""
    out: list[Note] = []
    bar = 0
    cur = 70
    quoted = False
    while bar < bars:
        progress = bar / max(bars - 1, 1)
        plen = 2 if rng.random() < 0.55 + 0.3 * progress else 1
        plen = min(plen, bars - bar)
        if motif and not quoted and bar >= bars // 2 - 1 and motif_slots:
            q = [n for n in motif if n.beat - motif[0].beat < 8]
            q0 = q[0].beat
            src_start = q0 - (q0 % 4)
            moved = []
            for n in q:
                rel = n.beat - src_start
                a = th.chord_at(motif_slots, rel % (motif_slots[-1].start + motif_slots[-1].beats)).chord
                b_ = th.chord_at(slots, bar * 4 + rel).chord
                moved.append(Note(start + bar * 4 + rel, n.dur, th.map_degree(n.pitch, a, b_) + 12 * (n.pitch < lo), 0.7, part, tag="quote"))
            out += moved
            quoted = True
            bar += 2
            cur = moved[-1].pitch if moved else cur
            continue
        centre = lo + 6 + int((hi - lo - 12) * progress)
        for b in range(plen):
            rhythm = RHYTHMS[int(rng.integers(len(RHYTHMS)))]
            if progress > 0.6 and rng.random() < 0.5:
                rhythm = sorted(set(rhythm + [s + 1 for s in rhythm if s + 1 < 16 and rng.random() < 0.5]))
            for k, step in enumerate(rhythm):
                pos = (bar + b) * 4 + step * S16
                slot = th.chord_at(slots, pos)
                ch = slot.chord
                sc = th.scale_notes(ch, lo, hi)
                strong = step % 4 == 0
                # move
                r = rng.random()
                pull = np.sign(centre - cur) if abs(centre - cur) > 5 else 0
                if r < 0.62:
                    stepsz = 1
                elif r < 0.88:
                    stepsz = 2
                else:
                    stepsz = int(rng.integers(3, 6))
                direction = pull if pull and rng.random() < 0.6 else (1 if rng.random() < 0.5 else -1)
                idx = min(range(len(sc)), key=lambda i: abs(sc[i] - cur))
                idx = int(np.clip(idx + direction * stepsz, 0, len(sc) - 1))
                p = sc[idx]
                if strong:
                    ct = th.chord_notes(ch, p - 2, p + 2)
                    if ct:
                        p = min(ct, key=lambda c: abs(c - p))
                # enclosure into a chord change on the next beat
                nx = th.next_slot(slots, slot)
                if nx and 0 < nx.start - pos <= 0.5 and rng.random() < 0.5:
                    tgt = th.fit(nx.chord.guide[0], p)
                    p = tgt + (1 if rng.random() < 0.5 else -1)
                dur = ((rhythm[k + 1] - step) if k + 1 < len(rhythm) else 2) * S16
                vel = 0.62 + 0.14 * (step % 2 == 1 and step % 4 == 3) + 0.1 * strong - 0.12 * (step % 2 == 1) + 0.08 * progress
                out.append(Note(start + pos, dur * 0.9, int(p), float(np.clip(vel, 0.3, 0.95)), part))
                cur = p
        # phrase end: land on a 3rd / 9th of the chord, held
        last_pos = (bar + plen) * 4 - 1.0
        ch = th.chord_at(slots, last_pos).chord
        land = [th.fit(pc, cur) for pc in (ch.guide[0], (ch.root + 14) % 12)]
        p = min(land, key=lambda c: abs(c - cur))
        if lo <= p <= hi:
            out.append(Note(start + last_pos, 1.0, int(p), 0.66, part))
            cur = p
        bar += plen
        if bar < bars and rng.random() < 0.75:
            bar += 1  # breathe
    # remove overlaps (monophonic right hand)
    out.sort(key=lambda n: n.beat)
    clean = []
    for n in out:
        if clean and n.beat < clean[-1].beat + 1e-6:
            continue
        if clean and clean[-1].beat + clean[-1].dur > n.beat:
            clean[-1].dur = n.beat - clean[-1].beat
        clean.append(n)
    return clean


# ======================================================================== guide-tone line

def guide_line(slots: list[Slot], start: float, rng, part="horn", near: int = 70, vel: float = 0.5) -> list[Note]:
    """Long notes on each chord's 3rd or 7th, always taking the closer one: the smoothest possible
    line through the changes (builds tension in a breakdown without adding a new melody)."""
    out = []
    cur = near
    for s in slots:
        cands = [th.fit(pc, cur) for pc in s.chord.guide]
        p = min(cands, key=lambda c: (abs(c - cur), rng.random()))
        out.append(Note(start + s.start, s.beats * 0.96, int(p), vel + 0.05 * (s.chord.is_dominant), part))
        cur = p
    return out


def diatonic(phrase: list[Note], slots: list[Slot], start: float, steps: int) -> list[Note]:
    """Move a line by `steps` scale steps of the chord sounding under each note: a harmony voice
    in diatonic thirds (±2) or sixths (±5) that stays inside the changes."""
    out = []
    for n in phrase:
        ch = th.chord_at(slots, n.beat - start).chord
        sc = th.scale_notes(ch, n.pitch - 24, n.pitch + 24)
        i = min(range(len(sc)), key=lambda k: abs(sc[k] - n.pitch))
        j = int(np.clip(i + steps, 0, len(sc) - 1))
        out.append(replace(n, pitch=sc[j]))
    return out


# ======================================================================== floating lead

FLOAT_RHYTHMS = [  # (step, length) in 16ths: long tones, space, the odd short run
    [(0, 6), (6, 2), (8, 8)], [(2, 4), (6, 6), (12, 4)], [(0, 3), (3, 3), (6, 10)], [(4, 4), (8, 4), (12, 4)],
    [(0, 10), (10, 2), (12, 4)], [(2, 2), (4, 2), (6, 2), (8, 8)], [(0, 16)], [(6, 2), (8, 2), (10, 6)],
    [(0, 4), (5, 3), (8, 2), (10, 6)], [(3, 5), (8, 8)],
]


def colour_tones(ch: Chord) -> list[int]:
    """What a lead should lean on over a deep sub: 3rd, 7th, 9th, and the 11th/#11/13 the chord
    scale allows. Never the root (the sub owns it), never the avoid note."""
    iv = th.QUALITIES[ch.quality][0]
    major = 4 in iv
    sc = th.SCALES[th.QUALITIES[ch.quality][2]]
    out = set(ch.guide)
    for rel in (2, 9):                      # 9th, 13th
        if rel in sc:
            out.add((ch.root + rel) % 12)
    if 6 in sc:                             # #11 in lydian colours
        out.add((ch.root + 6) % 12)
    if not major and 5 in sc:               # natural 11 on minor chords
        out.add((ch.root + 5) % 12)
    for alt in (1, 3, 8):                   # altered dominants: b9, #9, b13
        if alt in sc and ch.is_dominant and (alt in iv or ch.quality in ("7alt", "7b9", "13b9", "7#9")):
            out.add((ch.root + alt) % 12)
    out.discard(ch.root % 12)
    return sorted(out)


def float_solo(slots: list[Slot], start: float, bars: int, rng, part: str = "rhodes_solo",
               lo: int = 64, hi: int = 84) -> list[Note]:
    """A floating, non-repeating lead: 2-bar phrases with breaths, long notes on colour tones,
    stepwise passing notes, slides between neighbours and slides up into held notes, hammer-ons
    within a phrase. No bar reuses a recent rhythm or an earlier interval shape."""
    out: list[Note] = []
    cur = (lo + hi) // 2 - 3
    recent_r: list[int] = []
    shapes: set[tuple] = set()
    bar = 0
    while bar < bars:
        plen = int(min(rng.choice([2, 2, 3, 4]), bars - bar))
        for b in range(plen):
            ab = bar + b
            arc = 0.5 - 0.5 * np.cos(np.pi * (ab / max(bars - 1, 1)))      # rise to the middle, settle
            centre = lo + 4 + (hi - lo - 10) * (0.35 + 0.5 * np.sin(np.pi * ab / max(bars, 1)))
            for attempt in range(6):
                ri = int(rng.integers(len(FLOAT_RHYTHMS)))
                if ri not in recent_r[-3:]:
                    break
            rhythm = FLOAT_RHYTHMS[ri]
            for attempt in range(6):
                trial, c = [], cur
                for step, length in rhythm:
                    pos = ab * 4 + step * S16
                    ch = th.chord_at(slots, pos).chord
                    long_note = length >= 4 or step % 4 == 0
                    if long_note:
                        pool = [th.fit(pc, c) + o for pc in colour_tones(ch) for o in (-12, 0, 12)]
                    else:
                        pool = th.scale_notes(ch, c - 4, c + 4)
                    pool = [x for x in pool if lo <= x <= hi and x != c] or [c]
                    pull = (centre - c) * 0.15
                    w = np.array([np.exp(-abs(x - c - pull) / (3.5 if long_note else 2.0)) for x in pool])
                    x = int(pool[int(rng.choice(len(pool), p=w / w.sum()))])
                    trial.append((step, length, x, long_note))
                    c = x
                shape = tuple(np.sign(np.diff([cur] + [t[2] for t in trial])).tolist()) + (ri,)
                if shape not in shapes:
                    break
            shapes.add(shape)
            recent_r.append(ri)
            for k, (step, length, x, long_note) in enumerate(trial):
                pos = start + ab * 4 + step * S16
                vel = float(np.clip(0.56 + 0.16 * arc + 0.06 * long_note + rng.normal(0, 0.03), 0.4, 0.85))
                prev = out[-1] if out else None
                touching = prev is not None and abs(prev.beat + prev.dur - pos) < 0.13
                slide = touching and abs(prev.pitch - x) <= 2 and rng.random() < 0.6
                if long_note and not touching and rng.random() < 0.35:
                    # slide up into the held note from a step below
                    g = Note(pos - S16 * 0.5, S16 * 0.5, x - int(rng.choice([1, 2])), vel * 0.8, part, tag="grace")
                    out.append(g)
                    slide = True
                    touching = True
                tag = "legato" if touching and not slide and rng.random() < 0.45 else ""
                out.append(Note(pos, length * S16 * 0.97, x, vel, part, slide=slide, tag=tag))
            cur = trial[-1][2]
        bar += plen
        if bar < bars:
            bar += 1 if rng.random() < 0.7 else 2       # breathe
    out.sort(key=lambda n: n.beat)
    for a, b in zip(out, out[1:]):
        if a.beat + a.dur > b.beat:
            a.dur = max(b.beat - a.beat, 0.05)
    return out


def make_room(comp: list[Note], leads: list[Note], slots: list[Slot], start: float, soften: float = 0.82) -> list[Note]:
    """Keys get out of the melody's way: a comping strike that would land on (or just around) a melody
    note is dropped, unless it marks a chord change; strikes under a sounding melody note are softer.
    A chord strike is all notes sharing one onset."""
    if not leads:
        return comp
    onsets = np.array(sorted(n.beat for n in leads))
    spans = [(n.beat, n.beat + n.dur) for n in leads]
    changes = {round(start + s.start, 4) for s in slots}
    groups: dict[float, list[Note]] = {}
    for n in comp:
        groups.setdefault(round(n.beat, 4), []).append(n)
    out = []
    for b, g in groups.items():
        on_change = b in changes
        near = len(onsets) and np.min(np.abs(onsets - b)) <= 0.26
        if near and not on_change:
            continue
        if any(a <= b < e for a, e in spans):
            for n in g:
                n.vel *= soften
        out += g
    return sorted(out, key=lambda n: n.beat)
