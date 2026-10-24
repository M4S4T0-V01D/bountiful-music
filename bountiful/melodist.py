#!/usr/bin/env python3
"""The melody writer: writes a loop's melody the way a songwriter does, instead of filtering the composer's line.

  rhythm    a vocabulary of one-bar cells per character (house, smooth, bouncy, latin, dub, fresh): syncopations, pushes,
            held notes; a two-bar motif rhythm is drawn from it (call), with a related answer rhythm (response)
  motif     a short scale-degree shape seeded from the composer's own melody (its first note and direction), mostly steps,
            at most one leap and it is filled back (gap-fill)
  phrases   the loop is built from two-bar phrases with a plan: call, response, climax (the motif lifted towards the top of
            the register), cadence (down to a stable chord tone, a long last note); 8-bar loops get call / response /
            call' / cadence, 16-bar loops a second half that climbs higher
  harmony   strong-beat and long notes land on chord tones of the chord sounding; weak notes move by scale step
            (passing and neighbour tones)
  variants  for repeats: 'base', 'ornament' (pickups and passing 16ths), 'answer' (a new ending), 'lift' (the climax
            phrase up), 'sparse' (strong beats only, held, for breakdowns)

melody cfg (genre / song): writer = "motif", rhythm = "house" | ..., register, range_min (semitones), density (0-1),
articulation, velocity, swing / humanize / push (as producer.timing).
"""
from __future__ import annotations

import numpy as np

import producer as PR

# one-bar rhythm cells: (16th step, length in 16ths); a negative step is a pickup from the bar before
CELLS = {
    "house":  [[(0, 3), (3, 3), (6, 4), (12, 2), (14, 2)], [(2, 2), (4, 2), (6, 3), (10, 2), (12, 4)], [(0, 2), (3, 1), (4, 3), (10, 6)],
               [(-1, 3), (3, 2), (6, 2), (8, 4), (14, 2)], [(0, 4), (6, 2), (8, 2), (11, 5)]],
    "smooth": [[(0, 6), (6, 2), (8, 8)], [(2, 4), (6, 2), (8, 6), (14, 2)], [(0, 3), (3, 5), (10, 6)], [(-2, 4), (4, 4), (8, 8)]],
    "bouncy": [[(0, 2), (2, 2), (6, 2), (8, 2), (11, 2), (14, 2)], [(2, 1), (3, 2), (6, 2), (10, 2), (12, 1), (14, 2)],
               [(0, 2), (3, 2), (6, 2), (8, 3), (12, 2), (14, 2)]],
    "latin":  [[(0, 3), (3, 3), (6, 2), (8, 4), (12, 4)], [(0, 2), (3, 2), (6, 4), (10, 2), (12, 4)], [(-1, 3), (3, 3), (8, 3), (11, 5)]],
    "dub":    [[(0, 6), (8, 4), (14, 2)], [(3, 5), (10, 6)], [(0, 8), (10, 2), (12, 4)]],
    "phonk":  [[(0, 3), (3, 3), (6, 2), (8, 3), (11, 3), (14, 2)], [(0, 2), (2, 2), (4, 2), (6, 1), (7, 1), (8, 2), (11, 2), (14, 2)],
               [(0, 2), (3, 2), (6, 2), (8, 2), (10, 2), (12, 1), (13, 1), (14, 2)], [(0, 3), (3, 3), (6, 4), (12, 2), (14, 2)]],
    "fresh":  [[(0, 2), (2, 2), (4, 4), (10, 2), (12, 4)], [(0, 4), (6, 2), (8, 2), (10, 6)], [(-2, 2), (2, 2), (6, 3), (10, 2), (12, 4)]],
}
PLANS = {1: ["call"], 2: ["call", "cadence"], 3: ["call", "response", "cadence"], 4: ["call", "response", "call", "cadence"],
         8: ["call", "response", "call2", "cadence", "call", "response", "climax", "cadence"]}
LIFT = {"call": 0, "call2": 0, "response": 1, "climax": 4, "cadence": 0}


def _scale(sk, lo, hi):
    pcs = PR.key_scale(sk)
    return [p for p in range(lo, hi + 1) if p % 12 in pcs]


def _nearest_idx(scale, p):
    return int(np.argmin([abs(s - p) for s in scale]))


def _motif_shape(rng, n, direction):
    """scale-degree offsets for n notes: mostly steps, one leap that is filled back"""
    steps = [0]
    leap_at = rng.integers(1, max(2, n)) if n > 2 and rng.random() < 0.6 else -1
    d = direction
    for i in range(1, n):
        if i == leap_at:
            s = d * int(rng.choice([2, 3]))
        elif i == leap_at + 1:
            s = -d * int(rng.choice([1, 1, 2]))          # gap-fill: step back against the leap
        else:
            s = int(rng.choice([1, -1, 2], p=[0.58, 0.28, 0.14])) * d
        if rng.random() < 0.25:
            d = -d
        steps.append(steps[-1] + s)
    return steps


def _fit(scale, chords, t, dur, idx, strong, prev=None):
    """the pitch for scale index idx at beat t: on a strong (or long) note the chord tone within two steps that moves least
    from the previous note; otherwise the scale tone"""
    if not strong:
        return scale[idx]
    pcs = PR.chord_at(chords, t).pcs()
    cands = [j for j in range(idx - 2, idx + 3) if 0 <= j < len(scale) and scale[j] % 12 in pcs]
    if not cands:
        return scale[idx]
    ref = prev if prev is not None else scale[idx]
    return scale[min(cands, key=lambda j: abs(scale[j] - ref) + 0.6 * abs(j - idx))]


def write(sk, start_bar, bars, chords, cfg, rng, seed_line=None):
    """the loop's melody notes [t, d, pitch, vel] (beats) and the phrase each belongs to"""
    lo, hi = cfg.get("register", [60, 81])
    scale = _scale(sk, lo, hi)
    cells = CELLS.get(cfg.get("rhythm", "house"), CELLS["house"])
    density = cfg.get("density", 0.85)
    # the composer's identity: its first note and direction seed the motif
    src = seed_line or [(n.t - start_bar * 4, n.p) for n in sk.melody if start_bar * 4 <= n.t < (start_bar + bars) * 4]
    mid = (lo + hi) / 2 - 3
    if src:
        p0 = src[0][1]
        while p0 < lo + 2:
            p0 += 12
        while p0 > mid + 5:
            p0 -= 12
        rises = sum(1 for a, b in zip(src, src[1:4]) if b[1] > a[1])
        direction = 1 if rises >= 1 else -1
    else:
        p0, direction = int(mid), 1
    base_idx = _nearest_idx(scale, p0)
    call_r = [cells[rng.integers(len(cells))], cells[rng.integers(len(cells))]]
    resp_r = [call_r[0], cells[rng.integers(len(cells))]]
    phrase_bars = 2 if bars >= 2 else 1
    n_ph = max(1, bars // phrase_bars)
    plan = PLANS.get(n_ph) or (PLANS[8] * (n_ph // 8 + 1))[:n_ph]
    if n_ph == 8 and bars >= 16:
        plan = PLANS[8]
    if n_ph > 8:
        plan = (PLANS[8][:4] + PLANS[8])[:n_ph]
    motif = _motif_shape(rng, max(len(call_r[0]) + len(call_r[1]), 4), direction)
    notes, tags = [], []
    climax_done = 0
    for ph, kind in enumerate(plan):
        t0 = ph * phrase_bars * 4
        rr = resp_r if kind in ("response", "cadence") else call_r
        if phrase_bars == 1:
            rr = rr[:1]
        lift = LIFT.get(kind, 0) + (2 if kind == "climax" and climax_done else 0)
        if kind == "climax":
            climax_done += 1
        shape = motif if kind in ("call",) else (motif[:-2] + _motif_shape(rng, 3, -direction)[1:]) if kind == "call2" else motif
        k = 0
        evs = [(bi, st, ln) for bi, cell in enumerate(rr) for st, ln in cell]
        for j, (bi, st, ln) in enumerate(evs):
            last = j == len(evs) - 1
            if not last and j > 0 and rng.random() > density:
                continue                                   # breathing room
            t = t0 + bi * 4 + st / 4
            if t < 0:
                continue
            d = ln / 4
            if kind == "cadence" and last:
                d = max(d, 2.0)
            off = shape[k % len(shape)] + lift
            if kind == "cadence":                          # the answer settles downward into the last note
                off = shape[k % len(shape)] - (1 if j >= len(evs) // 2 else 0)
            idx = int(np.clip(base_idx + off, 0, len(scale) - 1))
            strong = (abs((t % 2)) < 1e-6) or d >= 1.0 or last
            p = _fit(scale, chords, t, d, idx, strong, notes[-1][2] if notes else None)
            if notes and p == notes[-1][2] and (len(notes) > 1 and notes[-2][2] == p or rng.random() < 0.6):
                p = _away(scale, chords, t, p, strong, direction if rng.random() < 0.7 else -direction)   # no note-on-note runs
            if kind == "cadence" and last:                 # resolve: the nearest root or fifth of the last chord
                c = PR.chord_at(chords, t)
                stable = [q for q in range(max(lo, p - 7), min(hi, p + 7) + 1) if (q - c.root) % 12 in (0, 7)]
                p = min(stable, key=lambda q: abs(q - p)) if stable else p
            notes.append([t, d, int(p), 0.8])
            tags.append(kind)
            k += 1
    # no overlaps, inside the loop
    notes.sort()
    for i in range(len(notes) - 1):
        notes[i][1] = min(notes[i][1], notes[i + 1][0] - notes[i][0] - 0.02)
    notes = [x for x in notes if x[0] < bars * 4 and x[1] > 0.05]
    _ensure_range(notes, cfg.get("range_min", 12), lo, hi, scale, chords)
    return notes


def _away(scale, chords, t, p, strong, dirn):
    """the next pitch from p in direction dirn: a scale step, or on a strong note the nearest other chord tone"""
    i = _nearest_idx(scale, p)
    pcs = PR.chord_at(chords, t).pcs()
    for k in (1, 2, 3):
        for sgn in (dirn, -dirn):
            j = i + sgn * k
            if 0 <= j < len(scale) and scale[j] != p and (not strong or scale[j] % 12 in pcs):
                return scale[j]
    return p


def _ensure_range(notes, want, lo, hi, scale, chords):
    """if the line is cramped, lift its peak phrase so the melody spans at least `want` semitones"""
    if not notes:
        return
    span = max(n[2] for n in notes) - min(n[2] for n in notes)
    if span >= want:
        return
    peak = max(range(len(notes)), key=lambda i: notes[i][2])
    for i in range(max(0, peak - 2), min(len(notes), peak + 3)):
        up = notes[i][2] + (want - span)
        if up <= hi:
            notes[i][2] = _fit(scale, chords, notes[i][0], notes[i][1], _nearest_idx(scale, up), True)


# ------------------------------------------------------------------ variations for repeats
def variant(notes, kind, sk, chords, cfg, rng):
    lo, hi = cfg.get("register", [60, 81])
    scale = _scale(sk, lo, hi)
    out = [list(x) for x in notes]
    if kind == "ornament":                       # pickups and passing 16ths into strong notes
        add = []
        for a, b in zip(out, out[1:]):
            gap = b[0] - (a[0] + a[1])
            if (b[0] % 1 == 0) and b[0] - a[0] >= 0.75 and rng.random() < 0.4:
                i = _nearest_idx(scale, b[2])
                step = scale[min(len(scale) - 1, i + 1)] if rng.random() < 0.5 else scale[max(0, i - 1)]
                add.append([b[0] - 0.25, 0.22, step, 0.62])
                a[1] = min(a[1], b[0] - 0.27 - a[0])
            elif gap >= 0.5 and rng.random() < 0.25:
                add.append([a[0] + a[1] + 0.02, 0.22, scale[min(len(scale) - 1, _nearest_idx(scale, a[2]) + 1)], 0.58])
        out = sorted(out + [x for x in add if x[1] > 0.05])
    elif kind == "answer":                       # the last phrase gets a different ending
        if len(out) > 4:
            for x in out[-3:-1]:
                i = _nearest_idx(scale, x[2]) + int(rng.choice([-2, -1, 1, 2]))
                x[2] = _fit(scale, chords, x[0], x[1], int(np.clip(i, 0, len(scale) - 1)), x[0] % 2 == 0)
    elif kind == "lift":                         # the highest phrase up (an octave if it fits, otherwise a third)
        peak_t = max(out, key=lambda x: x[2])[0] if out else 0
        ph = int(peak_t // 8) * 8
        for x in out:
            if ph <= x[0] < ph + 8:
                if x[2] + 12 <= hi + 3:
                    x[2] += 12
                else:
                    i = _nearest_idx(scale, x[2]) + 2
                    x[2] = _fit(scale, chords, x[0], x[1], min(len(scale) - 1, i), x[0] % 2 == 0)
    elif kind == "sparse":                       # strong beats only, held
        keep = [x for x in out if x[0] % 2 == 0 or x[1] >= 1.0]
        for a, b in zip(keep, keep[1:]):
            a[1] = max(a[1], min(b[0] - a[0] - 0.05, 2.0))
        out = keep
    for i in range(len(out) - 1):
        out[i][1] = max(0.08, min(out[i][1], out[i + 1][0] - out[i][0] - 0.02))
    return out


def perform(notes, cfg, rng, bars):
    """articulation, phrase dynamics and timing -> producer note tuples (t, d, pitch, vel, offset)"""
    vlo, vhi = cfg.get("velocity", [0.6, 0.92])
    art = cfg.get("articulation", "legato")
    out = []
    for ph in range(0, bars * 4, 8):
        grp = [x for x in notes if ph <= x[0] < ph + 8]
        if not grp:
            continue
        plo, phi = min(x[2] for x in grp), max(x[2] for x in grp)
        for x in grp:
            h = (x[2] - plo) / max(1, phi - plo)
            pos = x[0] % 4
            acc = 1.0 if pos == 0 else 0.6 if pos == 2 else 0.35 if pos % 1 == 0 else 0.15
            v = float(np.clip(vlo + (vhi - vlo) * (0.3 + 0.45 * h + 0.25 * acc) * (x[3] / 0.8) + rng.normal(0, 0.03), 0.2, 1.0))
            d = x[1] * (0.7 if art == "detached" else 0.97)
            out.append((x[0], max(0.08, d), int(x[2]), v, PR.timing(x[0], cfg, rng)))
    return out


VARIANT_CYCLE = ["base", "ornament", "answer", "lift"]


def loop_melodies(sk, start_bar, bars, chords, cfg, rng):
    """every variant of a loop's melody, performed: {name: [(t, d, p, v, o), ...]}"""
    base = write(sk, start_bar, bars, chords, cfg, rng)
    out = {"base": perform(base, cfg, rng, bars)}
    for k in ("ornament", "answer", "lift", "sparse"):
        out[k] = perform(variant(base, k, sk, chords, cfg, rng), cfg, rng, bars)
    return out
