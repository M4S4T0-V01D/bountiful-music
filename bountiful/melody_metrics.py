#!/usr/bin/env python3
"""Measure a song's lead melody from its MIDI: does it sound written, or generated?

    range        lowest to highest note (semitones)          good: an octave or more
    pitches      distinct pitches used
    notes/bar    density
    offbeat      share of notes off the beat (syncopation)    house melodies live off the beat
    stepwise     share of moves by a step (1-2 semitones)     singable lines are mostly steps
    big leaps    share of moves larger than a fifth           rare
    repeats      share of 4-bar spans heard exactly before (any alignment)      good: some, not all (~30-50%)
    chord tones  share of strong-beat notes on a chord tone of what the band plays there

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/melody_metrics.py tracks/<slug>/<slug>.mid [...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import ENGINE  # noqa: E402
sys.path.insert(0, str(ENGINE / "studio"))
from render_midi import read_midi  # noqa: E402

HARMONY = ("pad", "comp", "stab", "vox", "arp", "bass")


def measure(mid: Path, track: str = "lead") -> dict:
    notes, bpm, _ = read_midi(Path(mid))
    beat = 60 / bpm
    lead = sorted((n for n in notes if n["track"] == track), key=lambda n: n["start"])
    if len(lead) < 4:
        return {}
    p = np.array([n["pitch"] for n in lead])
    t = np.array([n["start"] / beat for n in lead])
    iv = np.abs(np.diff(p))
    moves = iv[iv > 0]
    bars = {}
    for n in lead:
        bars.setdefault(int(n["start"] / beat // 4), []).append(n["pitch"])
    # alignment-free: every 4-bar span that has melody, repeated exactly somewhere at least 4 bars earlier?
    lead_bars = sorted(bars)
    win = {b: tuple(tuple(bars.get(b + k, ())) for k in range(4)) for b in lead_bars}
    reps = [any(win[a] == win[b] for a in lead_bars if a <= b - 4) for b in lead_bars if sum(map(len, win[b])) >= 4]
    rep = sum(reps) / max(1, len(reps))
    harm = [n for n in notes if n["track"] in HARMONY]
    strong = [n for n in lead if abs((n["start"] / beat) % 2) < 0.12 or (n["end"] - n["start"]) / beat >= 1.0]
    hit = 0
    for n in strong:
        pcs = {h["pitch"] % 12 for h in harm if h["start"] <= n["start"] + 0.05 < h["end"]}
        hit += (not pcs) or (n["pitch"] % 12 in pcs)
    return {"range": int(p.max() - p.min()), "pitches": int(len(set(p))), "notes/bar": round(len(lead) / max(1, len(bars)), 1),
            "offbeat": round(float(np.mean((np.round(t * 4) % 4) != 0)), 2), "stepwise": round(float(np.mean(moves <= 2)) if len(moves) else 0, 2),
            "big leaps": round(float(np.mean(iv > 7)), 2), "repeats": round(rep, 2), "chord tones": round(hit / max(1, len(strong)), 2)}


def score(m: dict) -> float:
    """one number for ranking candidates: rewards range, syncopation, steps, chord tones, moderate repetition"""
    if not m:
        return 0.0
    return (min(m["range"], 17) / 17 * 2 + min(m["offbeat"], 0.5) / 0.5 * 1.5 + m["stepwise"] * 1.5 + m["chord tones"] * 2
            - abs(m["repeats"] - 0.4) * 2 - m["big leaps"] * 3 + min(m["pitches"], 12) / 12)


if __name__ == "__main__":
    print(f"{'file':40s} {'range':>5} {'pitch':>5} {'n/bar':>5} {'offbt':>5} {'steps':>5} {'leaps':>5} {'reps':>5} {'chord':>5} {'score':>5}")
    for f in sys.argv[1:]:
        m = measure(Path(f))
        if m:
            print(f"{Path(f).name[:40]:40s} {m['range']:5d} {m['pitches']:5d} {m['notes/bar']:5.1f} {m['offbeat']:5.2f} {m['stepwise']:5.2f} "
                  f"{m['big leaps']:5.2f} {m['repeats']:5.2f} {m['chord tones']:5.2f} {score(m):5.2f}")
