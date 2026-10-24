#!/usr/bin/env python3
"""Arrange an Abundant Music song into a full track, in a chosen genre (config "genre"):

    python tools/arrange.py arrangements/kosmodrom.json

genre "house"    -> as tools/house_arrange.py (four-on-the-floor, congas, timbales, piano stabs)
genre "synthpop" -> mid-80s drum machine: kick on 1, 3 and the 'and' of 3, snare (+clap) on 2 and 4,
                    8th-note closed hats, open hat on the last 8th of choruses, synthetic 'pew' tom fills;
                    plus a 16th-note sequencer arpeggio built from the loop's chords.
Parts available in a block: bass, lead, lead_hi (lead an octave up, quiet), pad, stabs, arp.
Per loop: start_bar (0-based in the source song), bars, lead_transpose, bass_transpose.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import mido
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from analyze import notes_of  # noqa: E402
from house_arrange import GM, bass_line, chord_at, drum_bar, lift, stab_part  # noqa: E402

GM = dict(GM, syntom_hi=48, syntom_mid=47, syntom_lo=43, hat_pedal=44)


def arp_part(chords, bars, pattern, lo, hi, gate, accent_every=4):
    """16th-note sequencer arpeggio: the chord sounding on each beat, its tones in [lo, hi] ascending,
    played in `pattern` order (indices into that list, cycled), one note per 16th."""
    out = []
    for b in range(bars * 4):
        ps = chord_at(chords, b + 0.01) or chord_at(chords, (b // 4) * 4)
        if not ps:
            continue
        pcs = {p % 12 for p in ps}
        tones = sorted(p for p in range(lo, hi + 1) if p % 12 in pcs)
        if not tones:
            continue
        for s in range(4):
            k = (b * 4 + s) % len(pattern)
            p = tones[pattern[k] % len(tones)]
            vel = 0.78 if (b * 4 + s) % accent_every == 0 else 0.6
            out.append((b + s / 4, gate, p, vel))
    return out


def synthpop_bar(bar_i, kind, rng, fill=None):
    ev = []
    if "kick" in kind:
        ev += [(0, "kick", 1.0), (2, "kick", 0.95), (2.5, "kick", 0.8)]
    if "four" in kind:                                    # chorus: kick on every beat
        ev = [e for e in ev if e[1] != "kick"] + [(b, "kick", 1.0 if b % 2 == 0 else 0.9) for b in range(4)]
    if "snare" in kind:
        ev += [(1, "snare", 0.9), (3, "snare", 0.92)]
    if "clap" in kind:
        ev += [(1, "clap", 0.75), (3, "clap", 0.78)]
    if "hat" in kind:
        ev += [(s / 2, "hat", (0.62 if s % 2 else 0.45) + rng.normal(0, 0.03)) for s in range(8)]
    if "hat16" in kind:
        ev += [(s / 4, "hat", (0.5 if s % 4 == 2 else 0.3) + rng.normal(0, 0.03)) for s in range(16) if s % 2]
    if "open" in kind:
        ev += [(3.5, "open", 0.6)]
    if "rim" in kind:
        ev += [(1.75, "rim", 0.45), (3.25, "rim", 0.4)]
    if fill == "syntoms":
        ev = [e for e in ev if e[0] < 2] + [(2 + i / 2, t, 0.85) for i, t in enumerate(("syntom_hi", "syntom_mid", "syntom_lo", "syntom_lo"))]
    elif fill == "syntoms16":
        ev = [e for e in ev if e[0] < 3] + [(3 + i / 4, t, 0.8) for i, t in enumerate(("syntom_hi", "syntom_hi", "syntom_mid", "syntom_lo"))]
    elif fill == "snare_roll":
        ev = [e for e in ev if e[0] < 2] + [(2 + s / 4, "snare", 0.4 + 0.07 * s) for s in range(8)]
    return ev


def main():
    cfg = json.loads(Path(sys.argv[1]).read_text())
    base = Path(sys.argv[1]).resolve().parent
    src = notes_of((base / cfg["source"]).resolve())
    genre = cfg.get("genre", "house")
    bpm = cfg.get("bpm", 124)
    ppq = 480
    rng = np.random.default_rng(cfg.get("seed", 1))
    sw = (cfg.get("swing", 0.5) - 0.5) * 0.5
    loops = {}
    for name, L in cfg["loops"].items():
        lp = lift(src, L["start_bar"], L.get("bars", 8))
        chords = lp.get("pad", []) + lp.get("keys", [])
        lt = L.get("lead_transpose", cfg.get("lead_transpose", 0))
        lead = [(t, d, p + lt, v) for (t, d, p, v) in lp.get("lead", [])]
        loops[name] = {
            "bars": L.get("bars", 8),
            "bass": bass_line(lp.get("bass", []), L.get("bass_transpose", cfg.get("bass_transpose", 0))),
            "lead": lead,
            "lead_hi": [(t, d, p + 12, v * 0.6) for (t, d, p, v) in lead],
            "pad": chords,
            "stabs": stab_part(chords, L.get("bars", 8), cfg.get("stab_steps", [0, 3, 6, 10, 13]), cfg.get("stab_low", 56),
                               cfg.get("stab_high", 70), cfg.get("stab_gate", 0.22)),
            "arp": arp_part(chords, L.get("bars", 8), cfg.get("arp_pattern", [0, 1, 2, 3]), cfg.get("arp_low", 60), cfg.get("arp_high", 79),
                            cfg.get("arp_gate", 0.18)),
        }
    names = ["lead", "lead_hi", "arp", "stabs", "pad", "bass"]
    parts = {k: [] for k in names}
    drums, bar_map, bar = [], [], 0
    for blk in cfg["arrangement"]:
        L = loops[blk["loop"]]
        n = blk["bars"]
        for i in range(n):
            b = bar + i
            lb = i % L["bars"]
            for p in names:
                if p in blk["parts"]:
                    for (t, d, pitch, v) in L[p]:
                        if lb * 4 <= t < lb * 4 + 4:
                            parts[p].append((b * 4 + t - lb * 4, d, pitch, v * blk.get("vel", {}).get(p, 1.0)))
            fill = blk.get("fill") if i == n - 1 else ("snare_roll" if i == n - 2 and blk.get("fill") == "roll16" else None)
            kind = set(blk.get("drums", []))
            bar_ev = synthpop_bar(b, kind, rng, fill) if genre == "synthpop" else drum_bar(b, kind, rng, sw, fill)
            for (t, snd, v) in bar_ev:
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
    chans = {"lead": (0, 81), "lead_hi": (1, 81), "arp": (2, 87), "stabs": (3, 0), "pad": (4, 50), "bass": (5, 38), "drums": (9, 0)}
    for name, evs in list(parts.items()) + [("drums", drums)]:
        if not evs:
            continue
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
    lines = [f"{cfg['title']}  ({genre}, {bar} bars, {bpm} bpm, {int(secs // 60)}:{secs % 60:04.1f})",
             f"source: {cfg['source']} (Abundant Music seed {cfg.get('source_seed', '?')}); loops: " +
             ", ".join(f"{k} = source bars {v['start_bar'] + 1}-{v['start_bar'] + v.get('bars', 8)}" for k, v in cfg["loops"].items()), ""]
    for a, b, nm, lp, ps, dr in bar_map:
        lines.append(f"  {a:3d}-{b:3d}  {nm:28s} loop {lp}  parts: {', '.join(ps) or '-':34s} drums: {', '.join(dr) or '-'}")
    lines += ["", "tracks: " + ", ".join(f"{k} {len(v)} notes" for k, v in list(parts.items()) + [("drums", drums)] if v)]
    out.with_suffix(".txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
