"""The evolution engine: small, musical, reversible changes to a song, and a loop that breeds better songs from them.

A change is plain data, {"op", "args", "seed", "why"}, and every op is a pure function of (song, args, seed):
the same change on the same song always gives the same notes, so a song is recoverable from its origin and its
list of changes (lineage.py keeps those). Bars in args are 1-based, as everywhere in Bountiful.

    melody       vary_phrase    a lead phrase moved in the key, inverted, played backwards, or with neighbour notes
                 ornament       passing tones between notes a third apart
                 motif_callback an opening motif brought back, transformed, later in the song
    rhythm       groove_mutate  hats, ghost snares and an extra kick change; the bar's kick-and-snare anchor never
                                does, and a bar that drifts too far from its groove is put back
                 bass_push      some bass notes anticipate the beat by an eighth
                 fill           a tom fill into the next section
    harmony      reharmonize    a search over diatonic substitutes for some chords of a section, scored by the
                                melody over them, voice leading and harmonic flow; the parts follow the new chords
    arrangement  lift_last_chorus  the lead doubled an octave up, a crash and a little more weight
                 breathe        parts drop out for a bar or two before a section arrives

    apply(song, change) -> song (a new dict; the old one is untouched)
    random_change(song, rng, family=None) -> change
    breed(song, n, seed) -> [(change, song)]
"""
from __future__ import annotations

import copy

import numpy as np

import features as F

FAMILIES = {"melody": ("vary_phrase", "ornament", "motif_callback"),
            "rhythm": ("groove_mutate", "steady_groove", "bass_push", "fill"),
            "harmony": ("reharmonize",),
            "arrangement": ("lift_last_chorus", "breathe")}
FAMILY_OF = {op: fam for fam, ops in FAMILIES.items() for op in ops}
ACCOMP = ("keys", "arp", "counter", "sidekick", "pad", "comp", "chords")
LIMIT_NOTES = 4000            # no op may grow a part past this


# ---------------------------------------------------------------- helpers

def scale(song: dict) -> list[int]:
    sc = F.MINOR if song.get("mode") == "minor" else F.MAJOR
    return sorted((song.get("tonic", 0) + i) % 12 for i in sc)


def snap(pitch: int, pcs, up: bool | None = None) -> int:
    """The nearest pitch whose pitch class is in pcs (ties go down unless up)."""
    pcs = set(p % 12 for p in pcs)
    for d in range(0, 7):
        for c in ((pitch + d, pitch - d) if up else (pitch - d, pitch + d)):
            if c % 12 in pcs:
                return c
    return pitch


def step(song: dict, pitch: int, n: int) -> int:
    """Move a pitch n steps along the song's scale."""
    sc = scale(song)
    p = snap(pitch, sc)
    k = 0
    while k != n:
        p += 1 if n > 0 else -1
        if p % 12 in sc:
            k += 1 if n > 0 else -1
    return p


def span_beats(args: dict) -> tuple[float, float]:
    a, b = args["bars"]
    return (a - 1) * 4.0, b * 4.0


def chord_at(song: dict, beat: float):
    for c in song.get("chords") or []:
        if c[0] <= beat < c[0] + c[1]:
            return c
    return None


def _fresh(song: dict) -> dict:
    s = dict(song)
    s["parts"] = {k: list(v) for k, v in song["parts"].items()}
    s["drums"] = list(song["drums"])
    s["chords"] = list(song.get("chords") or [])
    s["sections"] = [dict(x) for x in song["sections"]]
    return s


def _follow_lead(s: dict, old: list, new: list):
    """The sidekick and the octave double move with the lead: same onset, same step shift."""
    moved = {(round(a[0], 4), a[2]): b[2] for a, b in zip(old, new) if a[2] != b[2] and a[0] == b[0]}
    if not moved:
        return
    shift = {k[0]: F.degree(s, v) - F.degree(s, k[1]) for k, v in moved.items()}
    if s["parts"].get("sidekick"):
        s["parts"]["sidekick"] = [(t, d, step(s, p, shift[round(t, 4)]) if round(t, 4) in shift else p, v, o)
                                  for t, d, p, v, o in s["parts"]["sidekick"]]
    if s["parts"].get("lead_hi"):
        lo = {round(t, 4): p for t, d, p, v, o in s["parts"]["lead"]}
        s["parts"]["lead_hi"] = [(t, d, lo[round(t, 4)] + 12 if round(t, 4) in lo else p, v, o)
                                 for t, d, p, v, o in s["parts"]["lead_hi"]]


def _lead_key(s: dict) -> str:
    return next((k for k in F.MELODIC if s["parts"].get(k)), "lead")


# ---------------------------------------------------------------- melody

def vary_phrase(song: dict, args: dict, rng) -> tuple[dict, str]:
    s, k = _fresh(song), _lead_key(song)
    a, b = span_beats(args)
    lead = sorted(s["parts"].get(k, []))
    idx = [i for i, n in enumerate(lead) if a <= n[0] < b]
    if len(idx) < 3:
        return song, "too few lead notes there"
    how = args.get("how", "diatonic")
    old = list(lead)
    ps = [lead[i][2] for i in idx]
    if how == "diatonic":
        n = int(args.get("steps", 1)) or 1
        ps = [step(s, p, n) for p in ps]
    elif how == "invert":
        axis = F.degree(s, ps[0])
        ps = [step(s, ps[0], axis - F.degree(s, p)) for p in ps]
    elif how == "retrograde":
        ps = ps[::-1]
    elif how == "neighbor":
        for j in range(1, len(ps) - 1):
            if ps[j - 1] == ps[j] or rng.random() < 0.35:
                ps[j] = step(s, ps[j], int(rng.choice([-1, 1])))
    lo, hi = min(p for _, _, p, _, _ in old), max(p for _, _, p, _, _ in old)
    ps = [p - 12 if p > hi + 2 else p + 12 if p < lo - 2 else p for p in ps]           # stay in the lead's range
    for i, p in zip(idx, ps):
        t, d, _, v, o = lead[i]
        ch = chord_at(s, t)
        if ch and t % 1 == 0 and (p - ch[3]) % 12 not in [(c - ch[3]) % 12 for c in ch[2]] and t % 4 == 0:
            p = snap(p, ch[2])                                     # downbeats land on chord tones
        lead[i] = (t, d, int(p), v, o)
    s["parts"][k] = lead
    _follow_lead(s, old, lead)
    return s, f"lead bars {args['bars'][0]}-{args['bars'][1]} {how}"


def ornament(song: dict, args: dict, rng) -> tuple[dict, str]:
    s, k = _fresh(song), _lead_key(song)
    a, b = span_beats(args)
    lead = sorted(s["parts"].get(k, []))
    sc, add = scale(s), []
    for x, y in zip(lead, lead[1:]):
        gap = y[0] - x[0]
        if a <= x[0] < b and abs(y[2] - x[2]) in (3, 4) and gap >= 0.5 and rng.random() < args.get("amount", 0.6):
            mid = snap((x[2] + y[2]) // 2, sc, up=y[2] > x[2])
            if min(x[2], y[2]) < mid < max(x[2], y[2]):
                half = max(0.25, round(gap / 2 * 4) / 4)
                add.append((x, (x[0], min(x[1], half), x[2], x[3], x[4]),
                            (x[0] + half, max(0.1, min(x[1], gap) - half), mid, x[3] * 0.85, x[4])))
    if not add:
        return song, "no thirds to fill there"
    drop = {id(t[0]) for t in add}
    lead = [n for n in lead if id(n) not in drop] + [n for t in add for n in t[1:]]
    s["parts"][k] = sorted(lead)[:LIMIT_NOTES]
    return s, f"{len(add)} passing tones in bars {args['bars'][0]}-{args['bars'][1]}"


def motif_callback(song: dict, args: dict, rng) -> tuple[dict, str]:
    s, k = _fresh(song), _lead_key(song)
    lead0 = F.lead_of(s)
    first = int(lead0[0][0] // 4) if lead0 else 0             # the lead's first eight bars, after any intro
    mot = [m for m in F.motifs(s) if first <= m["bar"] < first + 8 and sum(1 for x in m["steps"] if x) >= 2]
    if not mot:
        return song, "no opening motif"
    m = mot[int(args.get("which", 0)) % len(mot)]
    lead = sorted(s["parts"][k])
    src = [n for n in lead if n[0] >= m["beat"]][:len(m["ivs"]) + 1]
    t0 = (args["to_bar"] - 1) * 4.0
    span = src[-1][0] + src[-1][1] - src[0][0]
    if span > 8:
        return song, "motif too long"
    how = args.get("how", "diatonic")
    base = [n[2] for n in src]
    if how == "diatonic":
        ps = [step(s, p, int(args.get("steps", 2))) for p in base]
    elif how == "invert":
        ps = [step(s, base[0], F.degree(s, base[0]) - F.degree(s, p)) for p in base]
    else:                                                          # augmented: same pitches, twice as slow
        ps = base
    stretch = 2.0 if how == "augment" else 1.0
    if span * stretch > 8:
        stretch = 1.0
    new = [(t0 + (n[0] - src[0][0]) * stretch, n[1] * stretch, int(p), n[3], 0.0) for n, p in zip(src, ps)]
    end = new[-1][0] + new[-1][1]
    lead = [n for n in lead if not (t0 <= n[0] < end)] + new
    s["parts"][k] = sorted(lead)
    for part in ("sidekick", "lead_hi"):
        if s["parts"].get(part):
            s["parts"][part] = [n for n in s["parts"][part] if not (t0 <= n[0] < end)]
    return s, f"opening motif from bar {m['bar'] + 1} returns {how} at bar {args['to_bar']}"


# ---------------------------------------------------------------- rhythm

def _bar_drums(drums, bar0):
    return [n for n in drums if bar0 * 4 <= n[0] < bar0 * 4 + 4]


def _ks(hits, bar0) -> np.ndarray:
    v = np.zeros(32)
    for t, d, g, vel, o in hits:
        st = int(round((t - bar0 * 4) * 4)) % 16
        kind = F.DRUM.get(g, "perc")
        if kind == "kick":
            v[st] = 1
        elif kind == "snare" and vel > 0.4:
            v[16 + st] = 1
    return v


def groove_mutate(song: dict, args: dict, rng) -> tuple[dict, str]:
    s = _fresh(song)
    a, b = args["bars"]
    amt = float(np.clip(args.get("amount", 0.5), 0, 1))
    hat, snare, kick = 42, 38, 36
    for g, kind in F.DRUM.items():
        if kind == "hat":
            hat = g
            break
    changed, kept = 0, 0
    out = [n for n in s["drums"] if not ((a - 1) * 4 <= n[0] < b * 4)]
    for bar0 in range(a - 1, min(b, s["bars"])):
        hits = _bar_drums(s["drums"], bar0)
        if not hits:
            continue
        before = _ks(hits, bar0)
        anchor = {int(round((t - bar0 * 4) * 4)) % 16 for t, d, g, v, o in hits if F.DRUM.get(g) in ("kick", "snare") and v > 0.4}
        new = [n for n in hits if not (F.DRUM.get(n[2]) == "hat" and rng.random() < amt * 0.3)]   # drop some hats
        steps = {int(round((t - bar0 * 4) * 4)) % 16 for t, *_ in new}
        for st in range(16):
            if st in steps:
                continue
            r = rng.random()
            if st % 2 == 1 and r < amt * 0.25:
                new.append((bar0 * 4 + st / 4, 0.1, hat, 0.3 + 0.15 * rng.random(), 0.0))
            elif st % 4 in (1, 3) and st not in anchor and r < amt * 0.12:
                new.append((bar0 * 4 + st / 4, 0.1, snare, 0.22 + 0.1 * rng.random(), 0.0))     # ghost snare
        if amt > 0.6 and rng.random() < (amt - 0.6):
            free = [st for st in (3, 6, 7, 10, 11, 14) if st not in steps and st not in anchor]
            if free:
                st = int(rng.choice(free))
                new.append((bar0 * 4 + st / 4, 0.2, kick, 0.6, 0.0))
        if F.cos(before, _ks(new, bar0)) >= 0.8:
            out += new
            changed += new != hits
        else:
            out += hits
            kept += 1
    s["drums"] = sorted(out)[:LIMIT_NOTES]
    return s, f"groove varied in {changed} bars of {a}-{b}" + (f", {kept} put back to keep the groove" if kept else "")


def _pattern(hits, bar0) -> np.ndarray:
    """The bar as the rhythm judge hears it: kick, snare and (half weight) hat on sixteen steps."""
    v = np.zeros(48)
    for t, d, g, vel, o in hits:
        st = int(round((t - bar0 * 4) * 4)) % 16
        k = F.DRUM.get(g)
        if k in ("kick", "snare", "hat"):
            v[("kick", "snare", "hat").index(k) * 16 + st] = 1 if k != "hat" else 0.5
    return v


def steady_groove(song: dict, args: dict, rng) -> tuple[dict, str]:
    """Settle a restless span back to the song's groove: of the bars in the span playing the song's most common
    kick-and-snare pattern (the groove the laws hold it to), the one most like its neighbours is the model; with
    none, the bar most like all the others. Bars that wander far from the model take its kick, snare and hats
    back (toms, crashes and percussion stay). The bar before each section is left alone: fills live there."""
    s = _fresh(song)
    a, b = args["bars"]
    amt = float(np.clip(args.get("amount", 0.6), 0, 1))
    every = [b0 for b0 in range(s["bars"]) if _bar_drums(s["drums"], b0)]
    bars = [b0 for b0 in every if a - 1 <= b0 < b]
    if len(bars) < 3:
        return song, "too few drum bars"
    ks = {b0: tuple(_ks(_bar_drums(s["drums"], b0), b0) > 0) for b0 in every}
    common = max(sorted(set(ks.values())), key=lambda k: sum(v == k for v in ks.values()))
    pats = {b0: _pattern(_bar_drums(s["drums"], b0), b0) for b0 in bars}
    pool = [x for x in bars if ks[x] == common] or bars
    main = max(pool, key=lambda x: (sum(F.cos(pats[x], pats[y]) for y in bars), -x))
    fills = {x["start"] - 2 for x in s["sections"]}
    core = ("kick", "snare", "hat")
    groove = [n for n in _bar_drums(s["drums"], main) if F.DRUM.get(n[2]) in core]
    redo = [b0 for b0 in bars if b0 != main and b0 not in fills and F.cos(pats[b0], pats[main]) < 0.9 and rng.random() < amt]
    if not redo:
        return song, "the groove is already steady"
    r = set(redo)
    out = [n for n in s["drums"] if not (int(n[0] // 4) in r and F.DRUM.get(n[2]) in core)]
    for b0 in redo:
        out += [(t + (b0 - main) * 4, d, g, v, o) for t, d, g, v, o in groove]
    s["drums"] = sorted(out)
    return s, f"{len(redo)} restless bars of {a}-{b} settle back to the groove of bar {main + 1}"


def bass_push(song: dict, args: dict, rng) -> tuple[dict, str]:
    s = _fresh(song)
    a, b = span_beats(args)
    k = next((x for x in F.BASSY if s["parts"].get(x)), None)
    if not k:
        return song, "no bass"
    n, out = 0, []
    for t, d, p, v, o in s["parts"][k]:
        if a <= t < b and t % 4 == 0 and t > 0 and rng.random() < args.get("amount", 0.4):
            out.append((t - 0.5, d + 0.5, p, min(1.0, v * 1.05), o))
            n += 1
        else:
            out.append((t, d, p, v, o))
    out.sort()
    out = [(t, min(d, max(0.25, nx[0] - t)) if nx else d, p, v, o) for (t, d, p, v, o), nx in
           zip(out, out[1:] + [None])]
    s["parts"][k] = out
    return s, f"{n} bass notes anticipate the bar"


def fill(song: dict, args: dict, rng) -> tuple[dict, str]:
    s = _fresh(song)
    bar0 = int(args["bar"]) - 1
    if not (0 <= bar0 < s["bars"]):
        return song, "no such bar"
    toms = [50, 48, 47, 45, 43]
    start = 12 - 4 * int(args.get("length", 1))
    keep = [n for n in s["drums"] if not (bar0 * 4 + start / 4 <= n[0] < bar0 * 4 + 4 and F.DRUM.get(n[2]) in ("hat", "snare"))]
    hits = [(bar0 * 4 + st / 4, 0.15, toms[min(len(toms) - 1, (st - start) * len(toms) // (16 - start))],
             0.55 + 0.3 * (st - start) / (16 - start), 0.0) for st in range(start, 16) if st % 2 == 0 or rng.random() < 0.5]
    s["drums"] = sorted(keep + hits)
    return s, f"tom fill at bar {bar0 + 1}"


# ---------------------------------------------------------------- harmony

def _candidates(song: dict, ch) -> list[tuple[int, list[int]]]:
    sc = F.MINOR if song.get("mode") == "minor" else F.MAJOR
    out = []
    for deg in range(7):
        for sev in (False, True):
            root = (song["tonic"] + sc[deg]) % 12
            pcs = [(song["tonic"] + sc[(deg + k) % 7]) % 12 for k in (0, 2, 4)] + \
                  ([(song["tonic"] + sc[(deg + 6) % 7]) % 12] if sev else [])
            if song.get("mode") == "minor" and deg == 4:
                pcs = [(root + 4) % 12 if x == pcs[1] else x for x in pcs]
            if root != ch[3] and len(set(pcs) & set(ch[2])) >= 2:
                out.append((root, pcs))
    return out


def _vl(a, b) -> int:
    return sum(min(min((x - y) % 12, (y - x) % 12) for y in b) for x in a)


def reharmonize(song: dict, args: dict, rng) -> tuple[dict, str]:
    """Search: every diatonic substitute sharing two notes with the old chord, scored by how the melody sits on it
    (strong beats on chord tones), voice leading from the chord before and into the chord after, and functional
    flow (T→S→D→T). The best one or two win, the seed picks between near ties."""
    import electronium_song as ES
    s = _fresh(song)
    sec = s["sections"][int(args["section"]) % len(s["sections"])]
    a, b = (sec["start"] - 1) * 4.0, (sec["start"] - 1 + sec["bars"]) * 4.0
    chords = sorted(s["chords"])
    idx = [i for i, c in enumerate(chords) if a <= c[0] < b]
    if not idx:
        return song, "no chords there"
    lead = F.lead_of(s)
    share = float(np.clip(args.get("share", 0.35), 0.1, 0.6))
    # the same chord recurs each time the loop repeats; reharmonize a loop position everywhere in the section
    pos = sorted({round(chords[i][0] - a, 3) % 32 for i in idx})
    pick = sorted(rng.choice(len(pos), size=max(1, int(round(len(pos) * share))), replace=False).tolist())
    changes, log = {}, []
    for pi in pick:
        p0 = pos[pi]
        i = next(i for i in idx if round(chords[i][0] - a, 3) % 32 == p0)
        ch = chords[i]
        prev = chords[i - 1] if i > 0 else None
        nxt = chords[i + 1] if i + 1 < len(chords) else None
        mel = [n for n in lead if ch[0] <= n[0] < ch[0] + ch[1]]
        best = []
        for root, pcs in _candidates(s, ch):
            on = sum((1.5 if n[0] % 1 == 0 else 0.5) * (n[2] % 12 in pcs) for n in mel)
            off = sum((1.5 if n[0] % 1 == 0 else 0.5) * any((n[2] - x) % 12 in (1, 11) for x in pcs) and n[2] % 12 not in pcs
                      for n in mel)
            tot = sum(1.5 if n[0] % 1 == 0 else 0.5 for n in mel) or 1
            fa = F.function_of(s, root)
            flow = (ES.NEXT[F.function_of(s, prev[3])][fa] if prev else 0.4) + (ES.NEXT[fa][F.function_of(s, nxt[3])] if nxt else 0.4)
            vl = (_vl(prev[2], pcs) if prev else 3) + (_vl(pcs, nxt[2]) if nxt else 3)
            score = 1.2 * (on - off) / tot + 0.8 * flow - 0.06 * vl
            best.append((round(score, 4), root, pcs))
        if not best:
            continue
        best.sort(key=lambda x: (-x[0], x[1]))
        top = [x for x in best[:2] if x[0] >= best[0][0] - 0.1]
        sc, root, pcs = top[int(rng.integers(len(top)))]
        changes[p0] = (root, pcs)
        log.append(f"{ES.NAMES[ch[3]]}→{ES.NAMES[root]}")
    if not changes:
        return song, "no substitutes fit"
    new_chords = []
    remap = []
    for c in chords:
        p0 = round(c[0] - a, 3) % 32
        if a <= c[0] < b and p0 in changes:
            root, pcs = changes[p0]
            new_chords.append((c[0], c[1], list(pcs), root))
            remap.append((c[0], c[0] + c[1], c, root, pcs))
        else:
            new_chords.append(c)
    s["chords"] = new_chords

    def moved(t, p, part):
        for t0, t1, old, root, pcs in remap:
            if t0 <= t < t1:
                if part in F.BASSY:
                    return snap(p, [root]) if p % 12 == old[3] else (snap(p, pcs) if p % 12 in old[2] else p)
                if part in ACCOMP:
                    return snap(p, pcs) if p % 12 in old[2] else p
                if part in F.MELODIC and t % 1 == 0 and p % 12 not in pcs and any((p - x) % 12 in (1, 11) for x in pcs):
                    return snap(p, pcs)
                return p
        return p
    for part, notes in s["parts"].items():
        s["parts"][part] = [(t, d, int(moved(t, p, part)), v, o) for t, d, p, v, o in notes]
    return s, f"{sec['name']}: " + ", ".join(log)


# ---------------------------------------------------------------- arrangement

def lift_last_chorus(song: dict, args: dict, rng) -> tuple[dict, str]:
    s = _fresh(song)
    sec = next((x for x in reversed(s["sections"]) if x["kind"] == "chorus"), None)
    if not sec:
        return song, "no chorus"
    a, b = (sec["start"] - 1) * 4.0, (sec["start"] - 1 + sec["bars"]) * 4.0
    k = _lead_key(s)
    have = {round(n[0], 4) for n in s["parts"].get("lead_hi", []) if a <= n[0] < b}
    dbl = [(t, d, p + 12, v * 0.55, o) for t, d, p, v, o in s["parts"].get(k, []) if a <= t < b and round(t, 4) not in have]
    s["parts"]["lead_hi"] = sorted(s["parts"].get("lead_hi", []) + dbl)
    w = 1 + 0.08 * float(np.clip(args.get("amount", 1.0), 0, 1))
    for part, notes in s["parts"].items():
        s["parts"][part] = [(t, d, p, min(1.0, v * w) if a <= t < b else v, o) for t, d, p, v, o in notes]
    s["drums"] = sorted(s["drums"] + [(a, 0.5, 49, 0.8, 0.0), (a + 32, 0.5, 49, 0.7, 0.0)] if sec["bars"] > 8 else
                        s["drums"] + [(a, 0.5, 49, 0.8, 0.0)])
    return s, f"{sec['name']} lifted: lead doubled up an octave, more weight"


def breathe(song: dict, args: dict, rng) -> tuple[dict, str]:
    s = _fresh(song)
    a, b = span_beats(args)
    keep = set(args.get("keep", ["bass"]))
    drums = args.get("drums", "thin")
    gone = []
    for part, notes in s["parts"].items():
        if part in keep or part in F.MELODIC and args.get("keep_lead", True):
            continue
        n0 = len(notes)
        s["parts"][part] = [n for n in notes if not (a <= n[0] < b)]
        if len(s["parts"][part]) < n0:
            gone.append(part)
    if drums == "none":
        s["drums"] = [n for n in s["drums"] if not (a <= n[0] < b)]
    elif drums == "thin":
        s["drums"] = [n for n in s["drums"] if not (a <= n[0] < b) or F.DRUM.get(n[2]) in ("kick", "hat")]
    return s, f"bars {args['bars'][0]}-{args['bars'][1]} breathe: {', '.join(gone) or 'nothing'} drop out"


OPS = {"vary_phrase": vary_phrase, "ornament": ornament, "motif_callback": motif_callback,
       "groove_mutate": groove_mutate, "steady_groove": steady_groove, "bass_push": bass_push, "fill": fill,
       "reharmonize": reharmonize, "lift_last_chorus": lift_last_chorus, "breathe": breathe}


def apply(song: dict, change: dict) -> dict:
    """The song with one change made. Unknown ops are refused loudly, so a lineage never silently drifts."""
    fn = OPS.get(change["op"])
    if fn is None:
        raise ValueError(f"unknown change {change['op']!r}")
    rng = np.random.default_rng([int(change.get("seed", 0)) & 0xFFFFFFFF, _crc(change["op"])])
    out, note = fn(song, copy.deepcopy(change.get("args", {})), rng)
    if out is not song:
        out["changes"] = list(song.get("changes", [])) + [dict(change, note=note)]
    return out


def apply_all(song: dict, changes: list[dict]) -> dict:
    for c in changes:
        song = apply(song, c)
    return song


def _crc(s: str) -> int:
    import zlib
    return zlib.crc32(s.encode()) & 0xFFFFFFFF


# ---------------------------------------------------------------- proposing changes

def random_change(song: dict, rng, family: str | None = None) -> dict:
    fam = family or str(rng.choice(list(FAMILIES)))
    op = str(rng.choice(FAMILIES[fam]))
    secs = song["sections"]
    sec = secs[int(rng.integers(len(secs)))]
    a = sec["start"] + int(rng.integers(0, max(1, sec["bars"] - 1) // 2 * 2 + 1)) // 2 * 2
    a = min(a, sec["start"] + sec["bars"] - 2)
    two = [a, min(sec["start"] + sec["bars"] - 1, a + 1)]
    four = [sec["start"], min(sec["start"] + sec["bars"] - 1, sec["start"] + 3)]
    if op == "vary_phrase":
        how = str(rng.choice(["diatonic", "invert", "retrograde", "neighbor"]))
        args = {"bars": two, "how": how, **({"steps": int(rng.choice([-2, -1, 1, 2]))} if how == "diatonic" else {})}
    elif op == "ornament":
        args = {"bars": four, "amount": round(float(rng.uniform(0.3, 0.8)), 2)}
    elif op == "motif_callback":
        later = [x for x in secs if x["start"] > 16] or secs
        to = later[int(rng.integers(len(later)))]
        args = {"to_bar": to["start"] + 2 * int(rng.integers(0, max(1, to["bars"] // 2))), "which": int(rng.integers(4)),
                "how": str(rng.choice(["diatonic", "invert", "augment"])), "steps": int(rng.choice([-2, 2, 3, 4]))}
    elif op == "groove_mutate":
        args = {"bars": [sec["start"], sec["start"] + sec["bars"] - 1], "amount": round(float(rng.uniform(0.2, 0.8)), 2)}
    elif op == "steady_groove":
        args = {"bars": [sec["start"], sec["start"] + sec["bars"] - 1], "amount": round(float(rng.uniform(0.4, 0.9)), 2)}
    elif op == "bass_push":
        args = {"bars": [sec["start"], sec["start"] + sec["bars"] - 1], "amount": round(float(rng.uniform(0.2, 0.6)), 2)}
    elif op == "fill":
        nxt = [x for x in secs[1:]]
        to = nxt[int(rng.integers(len(nxt)))]
        args = {"bar": to["start"] - 1, "length": int(rng.choice([1, 1, 2]))}
    elif op == "reharmonize":
        args = {"section": secs.index(sec), "share": round(float(rng.uniform(0.2, 0.5)), 2)}
    elif op == "lift_last_chorus":
        args = {"amount": round(float(rng.uniform(0.5, 1.0)), 2)}
    else:
        nxt = [x for x in secs[1:] if x["kind"] in ("chorus", "bridge")] or secs[1:]
        to = nxt[int(rng.integers(len(nxt)))]
        n = int(rng.choice([1, 2]))
        args = {"bars": [to["start"] - n, to["start"] - 1], "drums": str(rng.choice(["thin", "none"]))}
    return {"op": op, "args": args, "seed": int(rng.integers(1, 2**31)), "why": f"{fam}: {op}"}


def breed(song: dict, n: int = 24, seed: int = 0, families=None, depth: int = 1) -> list[tuple[list[dict], dict]]:
    """n children, each `depth` random changes away from song: [(changes, child)]. Changes that do nothing are
    redrawn (up to a bound), so every child differs from its parent."""
    rng = np.random.default_rng([seed & 0xFFFFFFFF, 7])
    fams = list(families or FAMILIES)
    out = []
    tries = 0
    while len(out) < n and tries < n * 4:
        tries += 1
        cur, ch = song, []
        for _ in range(depth):
            c = random_change(cur, rng, str(rng.choice(fams)))
            nxt = apply(cur, c)
            if nxt is not cur:
                cur, ch = nxt, ch + [c]
        if ch:
            out.append((ch, cur))
    return out
