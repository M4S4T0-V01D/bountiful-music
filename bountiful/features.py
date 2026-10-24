"""What a song is made of, measured: the common ground for the laws, the evaluators, the producer and the Observatory.

A *song* here is plain data, from a performance or from any .mid:

    {"title", "bpm", "bars", "tonic", "mode",
     "sections": [{name, kind, loop, start (1-based bar), bars, parts, drums}],
     "parts": {name: [(beat, dur, pitch, vel, offset), ...]},     # pitched parts
     "drums": [(beat, dur, gm_note, vel, offset), ...],
     "chords": [(beat, dur, pcs, root), ...]}                     # absolute beats; may be empty (estimated)

    grid(song)        one row per bar: notes per part, parts playing, drum layers, 16-step patterns, energy
    sections(song)    the same per section: energy, breadth, layers, register
    motifs(song)      the lead's 4-note shapes: intervals and rhythm, where they are
    features(song)    a flat {name: number} summary, for ranking and taste

Everything is deterministic and costs milliseconds; nothing here listens to audio (studio.py does that).
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np

DRUM = {35: "kick", 36: "kick", 37: "snare", 38: "snare", 39: "snare", 40: "snare", 42: "hat", 44: "hat", 46: "hat",
        51: "hat", 54: "hat", 69: "hat", 70: "hat", 43: "tom", 45: "tom", 47: "tom", 48: "tom", 50: "tom",
        49: "crash", 52: "crash", 55: "crash"}
GROUPS = ("kick", "snare", "hat", "tom", "crash", "perc")
MAJOR, MINOR = (0, 2, 4, 5, 7, 9, 11), (0, 2, 3, 5, 7, 8, 10)
FUNC = {0: "T", 1: "S", 2: "T", 3: "S", 4: "D", 5: "S", 6: "D"}
BASSY = ("bass", "bass2")
MELODIC = ("lead", "lead_hi", "melody", "vox")


def drum_group(gm: int) -> str:
    return DRUM.get(int(gm), "perc")


# ---------------------------------------------------------------- building a song

def song_from(pl: dict, perf: dict) -> dict:
    """A planned and performed Electronium song (electronium_song.plan / perform)."""
    chords = []
    for s in pl["sections"]:
        loop = pl["loops"].get(s["loop"], [])
        base = (s["start"] - 1) * 4
        for k in range(0, s["bars"] * 4, 32):
            for (t, d, pcs, root) in loop:
                if k + t < s["bars"] * 4:
                    chords.append((base + k + t, d, list(pcs), root))
    return {"title": pl.get("title", ""), "bpm": pl["bpm"], "bars": sum(s["bars"] for s in pl["sections"]),
            "tonic": pl["tonic"], "mode": pl["mode"], "sections": [dict(s) for s in pl["sections"]],
            "parts": {k: list(v) for k, v in perf["parts"].items() if v}, "drums": list(perf["drums"]), "chords": chords,
            "ideas": [[tuple(c) for c in i["cells"]] for i in getattr(perf.get("machine"), "kept", None) or []]}


def from_midi(path: Path, sections: list[dict] | None = None, tonic: int | None = None, mode: str | None = None) -> dict:
    """Any .mid Bountiful wrote (or another), track names as part names; a track called drums is the kit.
    Without sections the song is cut into 8-bar sections by its energy."""
    import mido
    mf = mido.MidiFile(str(path))
    ppq, bpm = mf.ticks_per_beat, 120.0
    parts: dict[str, list] = {}
    drums: list = []
    for i, tr in enumerate(mf.tracks):
        name = next((m.name for m in tr if m.type == "track_name"), "") or f"track{i}"
        tick, held = 0, {}
        for m in tr:
            tick += m.time
            if m.type == "set_tempo" and bpm == 120.0:
                bpm = float(mido.tempo2bpm(m.tempo))
            elif m.type == "note_on" and m.velocity > 0:
                held[(m.channel, m.note)] = (tick, m.velocity / 127)
            elif m.type in ("note_off", "note_on") and (m.channel, m.note) in held:
                t0, v = held.pop((m.channel, m.note))
                ev = (t0 / ppq, max(1, tick - t0) / ppq, m.note, v, 0.0)
                (drums if (m.channel == 9 or name.lower().startswith("drum")) else parts.setdefault(name, [])).append(ev)
    end = max([n[0] + n[1] for v in parts.values() for n in v] + [n[0] for n in drums] + [4])
    bars = int(np.ceil(end / 4))
    pcs = Counter(n[2] % 12 for v in parts.values() for n in v)
    if tonic is None or mode is None:
        tonic, mode = estimate_key(pcs)
    song = {"title": Path(path).stem, "bpm": bpm, "bars": bars, "tonic": tonic, "mode": mode,
            "parts": {k: sorted(v) for k, v in parts.items()}, "drums": sorted(drums), "chords": [],
            "sections": sections or []}
    if not song["sections"]:
        song["sections"] = auto_sections(song)
    return song


def estimate_key(pcs: Counter) -> tuple[int, str]:
    """Krumhansl-style: the major or minor scale that covers the most notes, tonic weighted."""
    best = (-1.0, 0, "minor")
    tot = sum(pcs.values()) or 1
    for t in range(12):
        for mode, sc in (("major", MAJOR), ("minor", MINOR)):
            cover = sum(pcs[(t + i) % 12] for i in sc) / tot + 0.15 * pcs[t] / tot + 0.05 * pcs[(t + 7) % 12] / tot
            if cover > best[0]:
                best = (cover, t, mode)
    return best[1], best[2]


def auto_sections(song: dict) -> list[dict]:
    rows = grid(dict(song, sections=[{"name": "all", "kind": "verse", "loop": "A", "start": 1, "bars": song["bars"],
                                      "parts": [], "drums": []}]))
    out, n = [], song["bars"]
    for i, a in enumerate(range(0, n, 8)):
        e = float(np.mean([r["energy"] for r in rows[a:a + 8]]))
        kind = "intro" if i == 0 else "outro" if a + 8 >= n else ("chorus" if e > 0.6 else "verse")
        out.append({"name": f"{kind} {i + 1}", "kind": kind, "loop": "A", "start": a + 1, "bars": min(8, n - a),
                    "parts": [], "drums": []})
    return out


# ---------------------------------------------------------------- per bar

def section_at(song: dict, bar0: int) -> dict | None:
    for s in song["sections"]:
        if s["start"] - 1 <= bar0 < s["start"] - 1 + s["bars"]:
            return s
    return None


def chords_by_bar(song: dict) -> list[tuple[int, list[int]]]:
    """(root, pcs) of the chord sounding at each bar's downbeat; estimated from the notes when the song has none."""
    out = []
    ch = sorted(song.get("chords") or [])
    j = 0
    for b in range(song["bars"]):
        t = b * 4
        while j + 1 < len(ch) and ch[j + 1][0] <= t:
            j += 1
        if ch and ch[j][0] <= t < ch[j][0] + ch[j][1] + 4:
            out.append((int(ch[j][3]), sorted({int(p) % 12 for p in ch[j][2]})))
            continue
        pcs = Counter()
        for k, v in song["parts"].items():
            for n in v:
                if t <= n[0] < t + 4:
                    pcs[n[2] % 12] += n[1] * (2 if k in BASSY else 1)
        low = [n[2] for k in BASSY for n in song["parts"].get(k, []) if t <= n[0] < t + 4]
        root = (min(low) % 12) if low else (pcs.most_common(1)[0][0] if pcs else song.get("tonic", 0))
        out.append((root, sorted(p for p, _ in pcs.most_common(4))))
    return out


def function_of(song: dict, root: int) -> str:
    sc = MINOR if song.get("mode") == "minor" else MAJOR
    deg = (root - song.get("tonic", 0)) % 12
    if deg in sc:
        return FUNC[sc.index(deg)]
    return "D" if deg in (11, 1, 6) else "S"         # leading-tone and tritone chords lean to the tonic; borrowed ones colour


def _steps(evs, bar0: int) -> list[float]:
    s = [0.0] * 16
    for e in evs:
        st = int(round((e[0] - bar0 * 4) * 4))
        if 0 <= st < 16:
            s[st] = max(s[st], float(e[3]))
    return s


def grid(song: dict) -> list[dict]:
    bars = song["bars"]
    by_bar: dict[int, dict[str, list]] = {}
    for k, v in song["parts"].items():
        for n in v:
            b = int(n[0] // 4)
            if 0 <= b < bars:
                by_bar.setdefault(b, {}).setdefault(k, []).append(n)
    drums_by: dict[int, list] = {}
    for n in song["drums"]:
        b = int(n[0] // 4)
        if 0 <= b < bars:
            drums_by.setdefault(b, []).append(n)
    harm = chords_by_bar(song)
    rows = []
    for b in range(bars):
        pb = by_bar.get(b, {})
        db = drums_by.get(b, [])
        groups = {g: [n for n in db if drum_group(n[2]) == g] for g in GROUPS}
        pitches = [n[2] for k, v in pb.items() for n in v]
        sec = section_at(song, b) or {}
        rows.append({
            "bar": b, "section": sec.get("name", ""), "kind": sec.get("kind", ""),
            "notes": {k: len(v) for k, v in pb.items()}, "active": sorted(pb),
            "onsets": sum(len(v) for v in pb.values()), "drum_hits": len(db),
            "layers": sorted(g for g, v in groups.items() if v),
            "kick16": _steps(groups["kick"], b), "snare16": _steps(groups["snare"], b), "hat16": _steps(groups["hat"], b),
            "bass16": _steps([n for k in BASSY for n in pb.get(k, [])], b),
            "lo": min(pitches) if pitches else 0, "hi": max(pitches) if pitches else 0,
            "vel": float(np.mean([n[3] for v in pb.values() for n in v] + [n[3] for n in db])) if (pb or db) else 0.0,
            "root": harm[b][0], "pcs": harm[b][1], "func": function_of(song, harm[b][0]),
        })
    n_parts = max(1, len(song["parts"]))
    mo = max([r["onsets"] for r in rows] + [1])
    md = max([r["drum_hits"] for r in rows] + [1])
    for r in rows:
        span = (r["hi"] - r["lo"]) / 48 if r["active"] else 0.0
        r["span"] = round(min(1.0, span), 3)
        r["energy"] = round(0.3 * len(r["active"]) / n_parts + 0.25 * r["onsets"] / mo + 0.25 * r["drum_hits"] / md
                            + 0.1 * min(1.0, r["vel"]) + 0.1 * r["span"], 4)
    return rows


# ---------------------------------------------------------------- per section

def sections(song: dict, rows: list[dict] | None = None) -> list[dict]:
    rows = rows or grid(song)
    out = []
    for i, s in enumerate(song["sections"]):
        rr = rows[s["start"] - 1: s["start"] - 1 + s["bars"]]
        if not rr:
            continue
        parts = sorted({p for r in rr for p in r["active"]})
        layers = sorted({g for r in rr for g in r["layers"]})
        lo = min((r["lo"] for r in rr if r["active"]), default=0)
        hi = max((r["hi"] for r in rr if r["active"]), default=0)
        e = float(np.mean([r["energy"] for r in rr]))
        out.append({"i": i, "name": s["name"], "kind": s["kind"], "loop": s.get("loop", ""), "start": s["start"],
                    "bars": s["bars"], "energy": round(e, 4), "peak": round(max(r["energy"] for r in rr), 4),
                    "parts": parts, "layers": layers, "lo": lo, "hi": hi, "span": hi - lo,
                    "onsets": round(float(np.mean([r["onsets"] for r in rr])), 2),
                    "drum_hits": round(float(np.mean([r["drum_hits"] for r in rr])), 2),
                    "breadth": round(0.6 * e + 0.2 * min(1.0, (hi - lo) / 48) + 0.2 * len(parts) / max(1, len(song["parts"])), 4)})
    return out


def groove(rows: list[dict]) -> np.ndarray:
    """The rhythm's fingerprint over some bars: kick, snare and bass onsets on the 16 steps (hats weigh less)."""
    drummed = [r for r in rows if r["drum_hits"] or r["bass16"] != [0.0] * 16]
    if not drummed:
        return np.zeros(64)
    v = np.mean([np.r_[r["kick16"], r["snare16"], 0.4 * np.array(r["hat16"]), 0.6 * np.array(r["bass16"])]
                 for r in drummed], axis=0)
    return v


def cos(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return float(a @ b / (na * nb)) if na > 1e-9 and nb > 1e-9 else 0.0


def pcs_hist(song: dict, a: int, b: int) -> np.ndarray:
    """Duration-weighted pitch classes between bars a and b (0-based, b exclusive)."""
    h = np.zeros(12)
    for v in song["parts"].values():
        for n in v:
            if a * 4 <= n[0] < b * 4:
                h[n[2] % 12] += n[1]
    return h / (h.sum() or 1)


# ---------------------------------------------------------------- the lead's motifs

def lead_of(song: dict) -> list:
    for k in MELODIC:
        if song["parts"].get(k):
            return sorted(song["parts"][k], key=lambda n: n[0])
    best = max(song["parts"].items(), key=lambda kv: np.mean([n[2] for n in kv[1]]) if kv[1] else 0, default=(None, []))
    return sorted(best[1], key=lambda n: n[0])


def degree(song: dict, pitch: int) -> int:
    """A pitch as a step count in the song's scale (out-of-key notes round down), so a line moved within the key
    keeps its steps even when its semitones change."""
    sc = MINOR if song.get("mode") == "minor" else MAJOR
    rel = int(pitch) - song.get("tonic", 0)
    o, pc = divmod(rel, 12)
    return o * 7 + max(i for i, d in enumerate(sc) if d <= pc)


def motifs(song: dict, size: int = 4, part: str | None = None) -> list[dict]:
    """Every run of `size` consecutive lead notes within two bars: its intervals (semitones and scale steps), its
    rhythm (onset gaps in sixteenths), its first pitch and where it starts."""
    notes = sorted(song["parts"].get(part, []), key=lambda n: n[0]) if part else lead_of(song)
    out = []
    for i in range(len(notes) - size + 1):
        w = notes[i:i + size]
        if w[-1][0] - w[0][0] > 8:
            continue
        dg = [degree(song, n[2]) for n in w]
        out.append({"beat": float(w[0][0]), "bar": int(w[0][0] // 4), "pitch": int(w[0][2]),
                    "ivs": tuple(int(w[j + 1][2] - w[j][2]) for j in range(size - 1)),
                    "steps": tuple(dg[j + 1] - dg[j] for j in range(size - 1)),
                    "rhythm": tuple(int(round((w[j + 1][0] - w[j][0]) * 4)) for j in range(size - 1))})
    return out


def transform(a: dict, b: dict) -> str | None:
    """How motif b relates to motif a: exact, transposed (same semitones), diatonic (same scale steps, moved
    within the key), inverted, retrograde, augmented or rhythm (same steps, new rhythm), contour (same ups and
    downs and rhythm, sizes off by a step), or None."""
    sa, sb = a.get("steps", a["ivs"]), b.get("steps", b["ivs"])
    if not any(sa):
        return None
    if sa == sb:
        if a["rhythm"] == b["rhythm"]:
            return ("exact" if a["pitch"] == b["pitch"] else "transposed") if a["ivs"] == b["ivs"] else "diatonic"
        if all(y == 2 * x for x, y in zip(a["rhythm"], b["rhythm"])) or all(2 * y == x for x, y in zip(a["rhythm"], b["rhythm"])):
            return "augmented"
        return "rhythm"
    if tuple(-x for x in sa) == sb:
        return "inverted"
    if tuple(-x for x in reversed(sa)) == sb:
        return "retrograde"
    if tuple(np.sign(sa)) == tuple(np.sign(sb)) and sum(abs(x - y) for x, y in zip(sa, sb)) <= 1 and a["rhythm"] == b["rhythm"]:
        return "contour"
    return None


# ---------------------------------------------------------------- summary

def features(song: dict, rows: list[dict] | None = None) -> dict:
    rows = rows or grid(song)
    secs = sections(song, rows)
    lead = lead_of(song)
    lp = np.array([n[2] for n in lead]) if lead else np.zeros(0)
    iv = np.abs(np.diff(lp)) if len(lp) > 1 else np.zeros(0)
    mv = iv[iv > 0]
    on = np.array([(n[0] * 4) % 4 for n in lead]) if lead else np.zeros(0)
    e = np.array([r["energy"] for r in rows]) if rows else np.zeros(1)
    harm = [r["root"] for r in rows]
    changes = sum(1 for a, b in zip(harm, harm[1:]) if a != b)
    sc = MINOR if song.get("mode") == "minor" else MAJOR
    inkey = {(song.get("tonic", 0) + i) % 12 for i in sc}
    allp = [n[2] % 12 for v in song["parts"].values() for n in v]
    return {
        "bars": song["bars"], "seconds": round(song["bars"] * 240 / song["bpm"], 1), "bpm": song["bpm"],
        "parts": len(song["parts"]), "sections": len(secs),
        "energy_mean": round(float(e.mean()), 4), "energy_range": round(float(e.max() - e.min()), 4),
        "energy_arc": round(float(np.corrcoef(np.arange(len(e)), e)[0, 1]) if len(e) > 2 and e.std() > 0 else 0.0, 4),
        "contrast": round(float(np.std([s["energy"] for s in secs])) if secs else 0.0, 4),
        "lead_notes": len(lead), "lead_range": int(lp.max() - lp.min()) if len(lp) else 0,
        "lead_stepwise": round(float(np.mean(mv <= 2)) if len(mv) else 0.0, 4),
        "lead_leaps": round(float(np.mean(mv > 7)) if len(mv) else 0.0, 4),
        "lead_offbeat": round(float(np.mean(on != 0)) if len(on) else 0.0, 4),
        "lead_pitches": int(len(set(lp.tolist()))),
        "harmonic_rhythm": round(changes / max(1, song["bars"]), 4),
        "in_key": round(sum(p in inkey for p in allp) / max(1, len(allp)), 4),
        "drum_density": round(float(np.mean([r["drum_hits"] for r in rows])) if rows else 0.0, 3),
        "note_density": round(float(np.mean([r["onsets"] for r in rows])) if rows else 0.0, 3),
    }
