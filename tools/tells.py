#!/usr/bin/env python3
"""Measure the 'tells': what makes generated MIDI sound machine-composed. Per part, from a .mid:

    python tools/tells.py songs/batch/*.mid           (averages over the files, plus per-file with -v)

  velocity spread     identical velocities = a sequencer, not a player (std of velocity, 0-127)
  grid exactness      share of onsets exactly on the 16th grid (1.0 = no human timing at all)
  same-length notes   share of notes whose length equals the most common length
  octave doubling     share of melody notes with another note exactly 12 semitones away at the same time
  fast notes          share of melody notes shorter than an 8th (busy, ornamental runs)
  triplets            share of melody onsets on a triplet grid but off the 16th grid
  repeated-note runs  runs of 3+ identical pitches per 8 bars (the 'B B B B B' figures)
  leaps               share of melodic intervals larger than a 5th
  leading tone        in minor keys, share of bars with the raised 7th (classical V7 cadences)
  chord changes/bar   harmonic rhythm (classical style changes chords often, pop/dance rarely)
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import mido
import numpy as np


def load(mid: Path):
    mf = mido.MidiFile(str(mid))
    ppq = mf.ticks_per_beat
    parts: dict[str, list] = {}
    for tr in mf.tracks:
        name = next((m.name for m in tr if m.type == "track_name"), "")
        t, held = 0, {}
        for m in tr:
            t += m.time
            if m.type == "note_on" and m.velocity > 0:
                held[(m.channel, m.note)] = (t, m.velocity)
            elif m.type in ("note_off", "note_on") and (m.channel, m.note) in held:
                t0, v = held.pop((m.channel, m.note))
                parts.setdefault(name.rstrip("0123456789"), []).append((t0 / ppq, (t - t0) / ppq, m.note, v))
    return {k: sorted(v) for k, v in parts.items()}


def melody_line(ns):
    """Top voice: one note per onset (the highest)."""
    by: dict[float, tuple] = {}
    for n in ns:
        k = round(n[0], 3)
        if k not in by or n[2] > by[k][2]:
            by[k] = n
    return [by[k] for k in sorted(by)]


def tells(mid: Path) -> dict:
    P = load(mid)
    allp = [n for k, v in P.items() if k != "drums" for n in v]
    out = {}
    if not allp:
        return out
    vel = np.array([n[3] for n in allp])
    out["velocity spread"] = float(vel.std())
    on = np.array([n[0] for n in allp])
    out["grid exactness"] = float(np.mean(np.abs(on * 4 - np.round(on * 4)) < 1e-3))
    lens = Counter(round(n[1], 3) for n in allp)
    out["same-length notes"] = lens.most_common(1)[0][1] / len(allp)
    lead = P.get("lead", [])
    if lead:
        line = melody_line(lead)
        bars = max(1, (line[-1][0] - line[0][0]) / 4)
        starts = {}
        for n in lead:
            starts.setdefault(round(n[0], 3), set()).add(n[2])
        out["octave doubling"] = float(np.mean([any((p + 12) in s or (p - 12) in s for p in s) for s in starts.values()]))
        out["fast notes"] = float(np.mean([n[1] < 0.45 for n in line]))
        trip = [n for n in line if abs(n[0] * 4 - round(n[0] * 4)) > 0.05 and abs(n[0] * 3 - round(n[0] * 3)) < 0.05]
        out["triplets"] = len(trip) / len(line)
        runs = 0
        k = 0
        for a, b in zip(line, line[1:]):
            if a[2] == b[2]:
                k += 1
                if k == 2:
                    runs += 1
            else:
                k = 0
        out["repeated-note runs /8 bars"] = runs / bars * 8
        iv = np.abs(np.diff([n[2] for n in line]))
        out["leaps > 5th"] = float(np.mean(iv > 7)) if len(iv) else 0
        out["melody notes/bar"] = len(line) / bars
    harm = P.get("pad", []) + P.get("keys", []) + P.get("bass", [])
    if harm:
        total_bars = int(max(n[0] for n in harm) // 4) + 1
        pcs = Counter()
        for n in harm:
            pcs[n[2] % 12] += n[1]
        # key: best natural-minor/major fit
        best = max(((sum(pcs[(r + i) % 12] for i in sc), r, nm) for r in range(12) for nm, sc in
                    (("minor", (0, 2, 3, 5, 7, 8, 10)), ("major", (0, 2, 4, 5, 7, 9, 11)))))
        _, root, mode = best
        if mode == "minor":
            lt = (root + 11) % 12
            out["leading-tone bars"] = len({int(n[0] // 4) for n in harm + lead if n[2] % 12 == lt}) / total_bars
        sets = []
        for b in range(total_bars * 2):
            s = frozenset(n[2] % 12 for n in harm if n[0] <= b * 2 + 0.01 < n[0] + n[1])
            sets.append(s)
        ch = sum(1 for a, b in zip(sets, sets[1:]) if a and b and len(a ^ b) > 1)
        out["chord changes/bar"] = ch / total_bars
    return out


def main():
    files = [Path(a) for a in sys.argv[1:] if not a.startswith("-")]
    rows = [tells(f) for f in files]
    keys = [k for k in rows[0]]
    if "-v" in sys.argv:
        for f, r in zip(files, rows):
            print(f.stem, {k: round(v, 2) for k, v in r.items()})
    print(f"{len(files)} files")
    for k in keys:
        vals = [r[k] for r in rows if k in r]
        print(f"  {k:28s} {np.mean(vals):7.2f}   (min {np.min(vals):.2f}, max {np.max(vals):.2f})")


if __name__ == "__main__":
    main()
