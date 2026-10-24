#!/usr/bin/env python3
"""Hear every Bountiful synth preset: each plays a phrase that suits it (a melody, a bass line, chords, keys comping,
a held note, a drum pattern or fill, or a sound effect), dry, written to <data>/gallery/<synth>/<preset>.wav with an index.html.

    python tools/synth_gallery.py                 -> every synth
    python tools/synth_gallery.py --synth nes     -> one synth
    python tools/synth_gallery.py --synth sid --preset acid-bass --bpm 140
"""
from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bountiful"))
import paths  # noqa: E402
import synths  # noqa: E402
from synths import core as C  # noqa: E402

# (beat, length in beats, midi, velocity)
MELODY = [(0, 1, 72, 1), (1, 0.5, 74, .8), (1.5, 0.5, 76, .8), (2, 1.5, 79, 1), (3.5, 0.5, 77, .7), (4, 1, 76, 1),
          (5, 1, 72, .8), (6, 2, 74, 1), (8, 0.5, 76, .9), (8.5, 0.5, 77, .7), (9, 1, 79, 1), (10, 1, 84, 1),
          (11, 1, 83, .8), (12, 4, 79, 1)]
BASS = [(b + o, 0.45, r + d, 1 if o == 0 else .7) for b, r in ((0, 36), (4, 33), (8, 29), (12, 31))
        for o, d in ((0, 0), (0.5, 12), (1, 0), (1.5, 12), (2, 0), (2.5, 12), (3, 7), (3.5, 12))]
HELD = [(0, 3.9, 60, 1), (4, 3.9, 57, 1), (8, 3.9, 53, 1), (12, 3.9, 55, 1)]
DRUMS = [(b * 0.5, 0.25, 60, 1 if b % 2 == 0 else .7) for b in range(32)]
FX = [(0, 0.5, 60, 1), (2, 0.5, 67, 1), (4, 0.5, 72, 1), (6, 1, 79, 1)]
TRIADS = ((60, 64, 67), (57, 60, 64), (53, 57, 60), (55, 59, 62))
CHORDS = [(i * 4, 3.9, m, .9) for i, t in enumerate(TRIADS) for m in t]
KEYS = [(i * 4 + o, d, m, v) for i, t in enumerate(TRIADS) for o, d, v in ((0, 1.4, 1), (1.5, 0.4, .7), (2.5, 1.3, .8))
        for m in t]
RISE = [(0, 6, 48, 1)]
FILL = [(b * 0.5, 0.25, m, 1) for b, m in enumerate((67, 67, 62, 62, 57, 57, 55, 53))]
HITS = [(0, 1, 60, 1), (4, 1, 60, .8), (8, 1, 60, 1)]
OPEN = [(b + 0.5, 0.2 if b % 2 else 0.45, 60, .9) for b in range(8)]
DRUM_WORDS = ("kick", "snare", "hat", "crash", "explosion", "metal", "buzz")
FX_WORDS = ("power-up", "coin", "jump", "laser", "blip")
CHORD_WORDS = ("pad", "chord", "strings", "string-machine", "choir", "cello")
KEY_WORDS = ("piano", "keys", "stab", "clav", "organ")


def phrase_for(name: str, p: dict, synth: str = "") -> list:
    if synth == "drums":
        if "tom" in name:
            return FILL
        if any(w in name for w in ("crash", "impact", "boom")):
            return HITS
        return OPEN if "open" in name else DRUMS
    if any(w in name for w in DRUM_WORDS) or p.get("channel") == "noise":
        return DRUMS
    if any(w in name for w in FX_WORDS):
        return FX
    if "riser" in name:
        return RISE
    if "bass" in name:
        return BASS
    if any(w in name for w in KEY_WORDS):
        return KEYS
    if synth not in ("nes", "gb", "sid") and any(w in name for w in CHORD_WORDS):
        return CHORDS
    if p.get("arp") is not None or "pad" in name or "chord" in name:
        return HELD
    return MELODY


def render(synth: str, name: str, bpm: float, seed: int = 7) -> np.ndarray:
    p = synths.preset(synth, name)
    beat = 60.0 / bpm
    ph = phrase_for(name, p, synth)
    out = np.zeros(int((max(b + d for b, d, _, _ in ph) * beat + 3.0) * C.SR))
    rng = np.random.default_rng(seed)
    mod = synths.get(synth)
    prev, last = None, -1.0
    for b, d, m, v in ph:
        y = mod.note(m, v, d * beat, p, rng, from_midi=prev if b > last else None)   # no glide inside a chord
        i = int(b * beat * C.SR)
        y = y[:len(out) - i]
        out[i:i + len(y)] += y
        prev, last = m, b
    end = len(out) - np.argmax(np.abs(out[::-1]) > 1e-4) + int(0.2 * C.SR)
    return out[:min(end, len(out))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synth", choices=synths.SYNTHS)
    ap.add_argument("--preset")
    ap.add_argument("--bpm", type=float, default=132)
    ap.add_argument("--out", type=Path, default=paths.DATA / "gallery")
    a = ap.parse_args()
    rows = {}
    for s in ([a.synth] if a.synth else synths.SYNTHS):
        for name in ([a.preset] if a.preset else synths.presets(s)):
            y = render(s, name, a.bpm)
            peak = float(np.abs(y).max())
            dest = a.out / s / f"{name}.wav"
            dest.parent.mkdir(parents=True, exist_ok=True)
            sf.write(dest, (y / max(peak, 1.0)).astype(np.float32), C.SR, subtype="PCM_16")
            rows.setdefault(s, []).append((name, dest.relative_to(a.out)))
            print(f"{s}/{name}: {len(y) / C.SR:.1f}s peak {peak:.2f}")
    page = ["<!doctype html><meta charset=utf-8><title>Bountiful synths</title>",
            "<style>body{font:15px system-ui;background:#111;color:#ddd;max-width:900px;margin:2em auto}"
            "h2{color:#9f6}div{display:flex;align-items:center;gap:1em;margin:.3em 0}span{width:12em}</style>",
            "<h1>Bountiful synths</h1>"]
    for s, items in rows.items():
        page.append(f"<h2>{html.escape(s)}</h2>")
        page += [f"<div><span>{html.escape(n)}</span><audio controls preload=none src='{html.escape(str(f))}'></audio></div>"
                 for n, f in items]
    (a.out / "index.html").write_text("\n".join(page))
    print(a.out / "index.html")


if __name__ == "__main__":
    main()
