#!/usr/bin/env python3
"""Turn an Abundant Music song into a DJ-length house track.

    python tools/house_arrange.py arrangements/downtown-protocol.json

Abundant Music composes the harmony, bass line and melody; this script lifts its best 8-bar sections as
loops and arranges them the way an early-90s New York house record is built:
  * bass   - Abundant's bass line, lowest voice of its octave pairs, moved down an octave for weight
  * lead   - Abundant's melody as written (octave doubling kept)
  * pad    - Abundant's sustained chords (strings)
  * stabs  - Abundant's harmony re-played as piano/organ stabs on a house rhythm (16th steps from config)
  * drums  - four-on-the-floor kick, clap on 2 and 4, swung 16th hats, off-beat open hats, shaker,
             congas and timbales, crashes and short fills (GM channel 10)
The config names the loops (0-based start bar in the source song, 8 bars each) and the arrangement
(16-bar blocks: which loop, which parts). Writes <out>.mid (one track per part), <out>.txt (bar map).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import mido
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from analyze import notes_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NOTE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
GM = {"kick": 36, "rim": 37, "snare": 38, "clap": 39, "hat": 42, "open": 46, "crash": 49, "ride": 51, "conga_hi": 62,
      "conga_lo": 64, "timbale_hi": 65, "timbale_lo": 66, "shaker": 70, "tom_lo": 45, "tom_mid": 47, "tom_hi": 50}


def role(n):
    return n.rstrip("0123456789")


def lift(src: dict, start_bar: int, bars: int) -> dict[str, list]:
    """Notes of each role in an 8-bar window, as (beat, dur, pitch, vel 0-1), beat relative to the window."""
    out: dict[str, list] = {}
    a, b = start_bar * 4, (start_bar + bars) * 4
    for tr, ns in src.items():
        r = role(tr)
        for (t, d, p, v) in ns:
            if a <= t < b - 1e-6:
                out.setdefault(r, []).append((t - a, min(d, b - t), p, v / 127))
    return out


def bass_line(ns, transpose):
    """Lowest voice of simultaneous notes (octave pairs), shifted down."""
    by_t: dict[float, tuple] = {}
    for n in ns:
        k = round(n[0], 3)
        if k not in by_t or n[2] < by_t[k][2]:
            by_t[k] = n
    return [(t, d, p + transpose, v) for (t, d, p, v) in sorted(by_t.values())]


def chord_at(chords, beat):
    """Pitch set sounding at `beat` in the loop's chord parts (pad + keys)."""
    ps = sorted({p for (t, d, p, v) in chords if t <= beat + 0.01 < t + d})
    return ps


def stab_part(chords, bars, steps, lo, hi, gate):
    out = []
    for bar in range(bars):
        for i, s in enumerate(steps):
            beat = bar * 4 + s / 4
            ps = chord_at(chords, beat) or chord_at(chords, bar * 4)
            if not ps:
                continue
            pcs = sorted({p % 12 for p in ps})
            voic = sorted(p for p in range(lo, hi + 1) if p % 12 in pcs)       # every chord tone in the stab register
            vel = 0.82 if i == 0 else 0.7 if s % 4 else 0.76
            out.extend((beat, gate, p, vel) for p in voic)
    return out


def drum_bar(bar_i, kind, rng, sw, fill=None):
    """One bar of house drums: list of (beat, sound, vel). kind: set of drum layers."""
    ev = []
    sw16 = lambda s: s / 4 + (sw if s % 2 else 0.0)
    if "kick" in kind:
        ev += [(b, "kick", 1.0) for b in range(4)]
    if "clap" in kind:
        ev += [(1, "clap", 0.9), (3, "clap", 0.9)]
    if "hat" in kind:
        ev += [(sw16(s), "hat", (0.62 if s % 4 == 2 else 0.4 if s % 2 else 0.5) + rng.normal(0, 0.05)) for s in range(16)]
    if "open" in kind:
        ev += [(b + 0.5, "open", 0.62 + rng.normal(0, 0.03)) for b in range(4)]
    if "shaker" in kind:
        ev += [(sw16(s), "shaker", (0.38 if s % 2 else 0.26) + rng.normal(0, 0.03)) for s in range(16)]
    if "congas" in kind:                       # a tumbao-ish conga figure, 2 bars long
        fig = [(3, "conga_lo"), (6, "conga_hi"), (7, "conga_hi"), (10, "conga_lo"), (14, "conga_hi")] if bar_i % 2 == 0 else \
              [(2, "conga_hi"), (3, "conga_lo"), (6, "conga_hi"), (11, "conga_lo"), (12, "conga_hi"), (14, "conga_hi"), (15, "conga_lo")]
        ev += [(sw16(s), snd, 0.55 + rng.normal(0, 0.05)) for s, snd in fig]
    if "timbales" in kind:                     # Morales-style timbale accents, answering the clap
        ev += [(sw16(s), snd, v) for s, snd, v in ((5, "timbale_hi", 0.5), (9, "timbale_lo", 0.45), (13, "timbale_hi", 0.55), (15, "timbale_hi", 0.4))]
    if "rim" in kind:
        ev += [(sw16(s), "rim", 0.45) for s in (6, 11)]
    if fill == "snare_roll":
        ev = [e for e in ev if e[0] < 2] + [(2 + s / 4, "snare", 0.4 + 0.07 * s) for s in range(8)]
    elif fill == "toms":
        ev = [e for e in ev if e[0] < 3 or e[1] == "kick"] + [(3 + i / 4, t, 0.7) for i, t in enumerate(("tom_hi", "tom_mid", "tom_lo", "tom_lo"))]
    elif fill == "roll16":
        ev = [e for e in ev if e[1] in ("kick",)] + [(s / 4, "snare", 0.35 + 0.04 * s) for s in range(16)]
    return ev


def main():
    cfg = json.loads(Path(sys.argv[1]).read_text())
    base = Path(sys.argv[1]).resolve().parent
    src_mid = (base / cfg["source"]).resolve()
    src = notes_of(src_mid)
    bpm = cfg.get("bpm", 124)
    ppq = 480
    rng = np.random.default_rng(cfg.get("seed", 1))
    sw = (cfg.get("swing", 0.54) - 0.5) * 0.5
    loops = {}
    for name, L in cfg["loops"].items():
        lp = lift(src, L["start_bar"], L.get("bars", 8))
        chords = lp.get("pad", []) + lp.get("keys", [])
        loops[name] = {
            "bars": L.get("bars", 8),
            "bass": bass_line(lp.get("bass", []), cfg.get("bass_transpose", -12)),
            "lead": [n for n in lp.get(L.get("lead_role", "lead"), [])],
            "pad": chords if cfg.get("pad_from", "pad+keys") == "pad+keys" else lp.get("pad", []),
            "stabs": stab_part(chords, L.get("bars", 8), cfg["stab_steps"], cfg.get("stab_low", 55), cfg.get("stab_high", 72), cfg.get("stab_gate", 0.2)),
        }
    parts = {k: [] for k in ("lead", "stabs", "pad", "bass")}
    drums = []
    bar_map = []
    bar = 0
    for blk in cfg["arrangement"]:
        L = loops[blk["loop"]]
        n = blk["bars"]
        for i in range(n):
            b = bar + i
            lb = i % L["bars"]
            for p in parts:
                if p in blk["parts"]:
                    for (t, d, pitch, v) in L[p]:
                        if lb * 4 <= t < lb * 4 + 4:
                            parts[p].append((b * 4 + t - lb * 4, d, pitch, v * blk.get("vel", {}).get(p, 1.0)))
            fill = None
            if i == n - 1 and blk.get("fill"):
                fill = blk["fill"]
            elif i == n - 2 and blk.get("fill") == "roll16":
                fill = "snare_roll"
            kind = set(blk.get("drums", []))
            if i < blk.get("drums_delay", {}).get("clap", 0):
                kind.discard("clap")
            for (t, snd, v) in drum_bar(b, kind, rng, sw, fill):
                drums.append((b * 4 + t, 0.2, GM[snd], float(np.clip(v, 0.05, 1))))
            if i == 0 and blk.get("crash"):
                drums.append((b * 4, 0.5, GM["crash"], 0.7))
        bar_map.append((bar + 1, bar + n, blk["name"], blk["loop"], blk["parts"], sorted(blk.get("drums", []))))
        bar += n

    out = (base / cfg["out"]).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    mf = mido.MidiFile(type=1, ticks_per_beat=ppq)
    meta = mido.MidiTrack()
    meta += [mido.MetaMessage("track_name", name=cfg["title"], time=0), mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0),
             mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0)]
    mf.tracks.append(meta)
    chans = {"lead": (0, 81), "stabs": (1, 0), "pad": (2, 49), "bass": (3, 38), "drums": (9, 0)}
    for name, evs in list(parts.items()) + [("drums", drums)]:
        ch, prog = chans[name]
        tr = mido.MidiTrack()
        tr.append(mido.MetaMessage("track_name", name=name, time=0))
        if ch != 9:
            tr.append(mido.Message("program_change", channel=ch, program=prog, time=0))
        msgs = []
        for (t, d, p, v) in evs:
            on = round(t * ppq)
            msgs.append((on, 1, mido.Message("note_on", channel=ch, note=int(p), velocity=int(np.clip(round(v * 127), 1, 127)))))
            msgs.append((max(on + 1, round((t + d) * ppq)), 0, mido.Message("note_off", channel=ch, note=int(p), velocity=0)))
        msgs.sort(key=lambda m: (m[0], m[1]))
        now = 0
        for tk, _, m in msgs:
            tr.append(m.copy(time=tk - now))
            now = tk
        mf.tracks.append(tr)
    mf.save(str(out))
    secs = bar * 4 * 60 / bpm
    lines = [f"{cfg['title']}  ({bar} bars, {bpm} bpm, {int(secs // 60)}:{secs % 60:04.1f})",
             f"source: {cfg['source']} (Abundant Music seed {cfg.get('source_seed', '?')}); loops: " +
             ", ".join(f"{k} = source bars {v['start_bar'] + 1}-{v['start_bar'] + v.get('bars', 8)}" for k, v in cfg["loops"].items()), ""]
    for a, b, nm, lp, ps, dr in bar_map:
        lines.append(f"  {a:3d}-{b:3d}  {nm:26s} loop {lp}  parts: {', '.join(ps) or '-':28s} drums: {', '.join(dr) or '-'}")
    lines += ["", "tracks: " + ", ".join(f"{k} {len(v)} notes" for k, v in list(parts.items()) + [("drums", drums)])]
    out.with_suffix(".txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
