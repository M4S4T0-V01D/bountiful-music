#!/usr/bin/env python3
"""Score generated songs for house use, from their .mid (am2mid output) and .am.json (section times).

    python tools/analyze.py songs/batch/*.mid           -> table + songs/batch/scores.json

Per song and per section: which roles play, notes per bar, how often the harmony changes, how
syncopated the bass is (onsets off the quarter-note grid), how much the melody repeats itself
(a hook is a phrase that comes back). The 'house' score favours: minor key, steady harmony (one chord
per bar or slower), a busy but syncopated bass, a melody that repeats, and sections with everything playing.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import mido
import numpy as np


def notes_of(mid: Path):
    mf = mido.MidiFile(str(mid))
    ppq = mf.ticks_per_beat
    out = {}
    for tr in mf.tracks:
        name = next((m.name for m in tr if m.type == "track_name"), "")
        t, held = 0, {}
        for m in tr:
            t += m.time
            if m.type == "note_on" and m.velocity > 0:
                held[m.note] = (t, m.velocity)
            elif m.type in ("note_off", "note_on") and m.note in held:
                t0, v = held.pop(m.note)
                out.setdefault(name, []).append((t0 / ppq, (t - t0) / ppq, m.note, v))
    return out


def role(name):
    return name.rstrip("0123456789")


def analyse(mid: Path) -> dict:
    doc = json.loads(mid.with_name(mid.name.replace(".mid", ".am.json")).read_text())
    st = doc["structure"]
    notes = notes_of(mid)
    total = doc["lengthBeats"]
    bars = int(np.ceil(total / 4))
    by_role: dict[str, list] = {}
    for n, ns in notes.items():
        if n:
            by_role.setdefault(role(n), []).extend(ns)
    # harmony: pitch-class set per bar from pads + keys + bass
    chordy = by_role.get("pad", []) + by_role.get("keys", [])
    pcs = [frozenset(p % 12 for (t, d, p, v) in chordy if int(t // 4) == b) for b in range(bars)]
    changes = sum(1 for a, b in zip(pcs, pcs[1:]) if a and b and len(a ^ b) > 1)
    bass = by_role.get("bass", [])
    bass_off = sum(1 for (t, d, p, v) in bass if abs(t - round(t)) > 0.05) / max(1, len(bass))
    bass_per_bar = len(bass) / max(1, bars)
    lead = sorted(by_role.get("lead", []))
    # melodic repetition: share of 2-bar interval+rhythm cells that occur more than once
    cells = []
    for b in range(0, bars, 2):
        seg = [(round(t - b * 4, 2), p) for (t, d, p, v) in lead if b * 4 <= t < b * 4 + 8]
        if len(seg) >= 3:
            cells.append(tuple((t, p - seg[0][1]) for t, p in seg))
    cnt = Counter(cells)
    rep = sum(c for c in cnt.values() if c > 1) / max(1, len(cells))
    minor = any(t in (1, 2, 3) for t in (st.get("scaleTypes") or [])) if st.get("scaleTypes") else None
    sec_t = [0.0]
    secs = []
    # sections: rebuild boundaries from tempo events (one per section) in the .mid
    mf = mido.MidiFile(str(mid))
    t = 0
    for m in mf.tracks[0]:
        t += m.time
        if m.type == "set_tempo":
            sec_t.append(t / mf.ticks_per_beat)
    bounds = sorted(set(round(x, 3) for x in sec_t[1:] + [total]))
    if bounds and bounds[0] > 0:
        bounds = [0.0] + bounds
    for a, b in zip(bounds, bounds[1:]):
        if b - a < 4:
            continue
        playing = {r: sum(1 for (tt, d, p, v) in ns if a <= tt < b) for r, ns in by_role.items()}
        secs.append({"start_beat": a, "bars": round((b - a) / 4, 2), "roles": {r: c for r, c in playing.items() if c}})
    full = [s for s in secs if {"lead", "bass", "drums"} <= set(s["roles"]) and ({"pad", "keys"} & set(s["roles"]))]
    hr = changes / max(1, bars)
    score = (1.0 if minor else 0.4) + (1 - min(1, abs(hr - 0.6) / 0.6)) + min(1, bass_per_bar / 4) * 0.8 + bass_off * 1.5 \
        + rep * 1.5 + min(1, len(full) / 4)
    return {"song": mid.stem, "seed": doc["seed"], "bars": bars, "minor": minor, "chord_changes_per_bar": round(hr, 2),
            "bass_notes_per_bar": round(bass_per_bar, 1), "bass_syncopation": round(bass_off, 2), "melody_repetition": round(rep, 2),
            "full_sections": len(full), "sections": secs, "score": round(score, 2)}


def main():
    rows = [analyse(Path(a)) for a in sys.argv[1:]]
    rows.sort(key=lambda r: -r["score"])
    print(f"{'song':28s} {'score':>5} {'bars':>4} {'minor':>5} {'chg/bar':>7} {'bass/bar':>8} {'b.sync':>6} {'mel.rep':>7} {'full':>4}")
    for r in rows:
        print(f"{r['song']:28s} {r['score']:5.2f} {r['bars']:4d} {str(r['minor']):>5} {r['chord_changes_per_bar']:7.2f} {r['bass_notes_per_bar']:8.1f} "
              f"{r['bass_syncopation']:6.2f} {r['melody_repetition']:7.2f} {r['full_sections']:4d}")
    if rows:
        Path(sys.argv[1]).parent.joinpath("scores.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
