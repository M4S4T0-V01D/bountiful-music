#!/usr/bin/env python3
"""Show a generated song's sections (start bar, length, which roles play) and its chords bar by bar,
to pick loops for tools/arrange.py.

    python tools/sections.py songs/batch/song.mid [more ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from analyze import analyse, notes_of, role  # noqa: E402

NOTE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
TEMPL = {"": [0, 4, 7], "m": [0, 3, 7], "7": [0, 4, 7, 10], "m7": [0, 3, 7, 10], "maj7": [0, 4, 7, 11], "dim": [0, 3, 6],
         "sus4": [0, 5, 7], "sus2": [0, 2, 7], "m7b5": [0, 3, 6, 10], "6": [0, 4, 7, 9], "m6": [0, 3, 7, 9], "add9": [0, 4, 7, 2],
         "m9": [0, 3, 7, 10, 2]}


def chord_name(pcw: dict, bass_pc) -> str:
    best = None
    for r in range(12):
        for q, iv in TEMPL.items():
            s = {(r + i) % 12 for i in iv}
            sc = sum(pcw.get(p, 0) for p in s) - 1.2 * sum(w for p, w in pcw.items() if p not in s) - 0.3 * len(s) + (0.5 * pcw.get(r, 0) if bass_pc == r else 0)
            if best is None or sc > best[0]:
                best = (sc, NOTE[r] + q)
    return best[1]


def chords_per_bar(mid: Path, bars: int, half: bool = False) -> list[str]:
    ns = notes_of(mid)
    byr: dict[str, list] = {}
    for n, v in ns.items():
        byr.setdefault(role(n), []).extend(v)
    step = 2 if half else 4
    out = []
    for i in range(bars * 4 // step):
        a, b = i * step, i * step + step
        pcw: dict = {}
        for rl in ("pad", "keys", "bass"):
            for (t, d, p, v) in byr.get(rl, []):
                ov = min(b, t + d) - max(a, t)
                if ov > 0:
                    pcw[p % 12] = pcw.get(p % 12, 0) + ov * (1.5 if rl == "bass" else 1)
        bs = [p for (t, d, p, v) in sorted(byr.get("bass", [])) if a <= t < b]
        out.append(chord_name(pcw, bs[0] % 12 if bs else None) if pcw else "-")
    return out


def main():
    for a in sys.argv[1:]:
        mid = Path(a)
        r = analyse(mid)
        ch = chords_per_bar(mid, r["bars"])
        print(f"\n== {mid.stem}  score {r['score']}  ({r['bars']} bars, melody repetition {r['melody_repetition']})")
        for s in r["sections"]:
            b0 = int(s["start_beat"] // 4)
            n = int(round(s["bars"]))
            print(f"  bar {b0:3d} (0-based) len {s['bars']:5.2f}  {', '.join(f'{k}:{v}' for k, v in s['roles'].items()):52s} "
                  + " ".join(ch[b0:b0 + n]))


if __name__ == "__main__":
    main()
