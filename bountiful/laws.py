"""Musical laws a song can be held to: measured from its notes (features.py), each with a score 0-1, a verdict,
the evidence and the bars it points at, so every judgement can be traced and argued with.

    groove_identity        the drums and bass keep one recognisable groove through the song
    final_chorus_biggest   the last chorus is the most expansive section
    new_idea_every_16      something new arrives in every 16 bars: a part, a drum layer, a chord loop, a motif
    motifs_return          the opening's motifs come back transformed (transposed, inverted, re-rhythmed...)
    bridge_returns         the bridge departs, and the return feels inevitable

    judge(song) -> [{"law", "title", "score", "passed", "evidence", "bars", "detail"}]
    $PY bountiful/laws.py --bounty 1969 [--brief "..."]
"""
from __future__ import annotations

from collections import Counter

import numpy as np

import features as F

TITLES = {"groove_identity": "Groove identity", "final_chorus_biggest": "The final chorus is the most expansive",
          "new_idea_every_16": "One new idea every 16 bars", "motifs_return": "Motifs return transformed",
          "bridge_returns": "The bridge departs; the return feels inevitable"}
PASS = 0.6


def _res(law: str, score: float | None, evidence: str, bars=(), detail=None) -> dict:
    s = None if score is None else round(float(np.clip(score, 0, 1)), 3)
    return {"law": law, "title": TITLES[law], "score": s, "passed": s is None or s >= PASS, "evidence": evidence,
            "bars": sorted({int(b) for b in bars}), "detail": detail or {}}


def groove_identity(song: dict, rows: list[dict], secs: list[dict]) -> dict:
    """Bar by bar, how like the song's own groove (kick, snare, bass on the 16 steps) each drummed bar is. The
    reference is the most common kick-and-snare pattern's bars, so a song with no settled groove has no reference
    to be like."""
    drummed = [r for r in rows if r["drum_hits"] > 0]
    if len(drummed) < 8:
        return _res("groove_identity", None, "fewer than eight bars with drums: nothing to keep")
    key = lambda r: (tuple(x > 0 for x in r["kick16"]), tuple(x > 0 for x in r["snare16"]))  # noqa: E731
    common, n = Counter(key(r) for r in drummed).most_common(1)[0]
    ref = F.groove([r for r in drummed if key(r) == common])
    sims = np.array([F.cos(F.groove([r]), ref) for r in drummed])
    per = {}
    for s in secs:
        v = [sim for r, sim in zip(drummed, sims) if s["start"] - 1 <= r["bar"] < s["start"] - 1 + s["bars"]]
        if v:
            per[s["name"]] = round(float(np.mean(v)), 3)
    worst = min(per, key=per.get)
    mean = float(sims.mean())
    same = float(np.mean(sims > 0.995))
    ev = (f"bars like the main groove: mean {mean:.2f}, its exact pattern in {n}/{len(drummed)} bars, "
          f"weakest section {worst} {per[worst]:.2f}")
    if same > 0.9:
        ev += " (nearly identical everywhere: it holds, but never breathes)"
    lost = [r["bar"] + 1 for r, sim in zip(drummed, sims) if sim < 0.5]
    return _res("groove_identity", (mean - 0.45) / 0.35 - (0.1 if same > 0.9 else 0), ev, lost, {"likeness": per})


def final_chorus_biggest(song: dict, rows: list[dict], secs: list[dict]) -> dict:
    ch = [s for s in secs if s["kind"] == "chorus"]
    if not ch:
        return _res("final_chorus_biggest", None, "no chorus")
    last = ch[-1]
    others = [s for s in secs if s is not last]
    if not others:
        return _res("final_chorus_biggest", 1.0, "the chorus is the whole song")
    top = max(others, key=lambda s: s["breadth"])
    margin = last["breadth"] - top["breadth"]
    earlier = [s for s in ch[:-1]]
    grew = all(last["breadth"] > s["breadth"] for s in earlier)
    ev = (f"{last['name']} breadth {last['breadth']:.2f} (energy {last['energy']:.2f}, {len(last['parts'])} parts, "
          f"span {last['span']}) vs the biggest other, {top['name']}, {top['breadth']:.2f}")
    score = 0.6 + margin / 0.1 * 0.4 if margin >= 0 else 0.6 + margin / 0.1 * 0.6
    if not grew:
        score = min(score, 0.5)
        ev += "; an earlier chorus is as big"
    return _res("final_chorus_biggest", score, ev, range(last["start"], last["start"] + last["bars"]),
                {"breadth": {s["name"]: s["breadth"] for s in secs}})


def new_idea_every_16(song: dict, rows: list[dict], secs: list[dict], window: int = 16) -> dict:
    """An idea: a part first heard, a drum layer first heard, a chord loop first heard, a section kind first heard,
    or a lead motif that repeats inside the window and was never heard before."""
    seen_parts, seen_layers, seen_loops, seen_kinds, seen_shapes = set(), set(), set(), set(), set()
    mot = F.motifs(song)
    ideas, windows = [], []
    for a in range(0, song["bars"], window):
        b = min(song["bars"], a + window)
        found = []
        for r in rows[a:b]:
            for p in r["active"]:
                if p not in seen_parts:
                    seen_parts.add(p)
                    found.append((r["bar"], f"{p} enters"))
            for g in r["layers"]:
                if g not in seen_layers:
                    seen_layers.add(g)
                    found.append((r["bar"], f"{g} joins the drums"))
        for s in song["sections"]:
            if a <= s["start"] - 1 < b:
                if s.get("loop") and s["loop"] not in seen_loops:
                    seen_loops.add(s["loop"])
                    found.append((s["start"] - 1, f"chord loop {s['loop']}"))
                if s["kind"] not in seen_kinds:
                    seen_kinds.add(s["kind"])
                    found.append((s["start"] - 1, f"first {s['kind']}"))
        here = Counter(m["ivs"] for m in mot if a <= m["bar"] < b and any(m["ivs"]))
        for shape, n in here.most_common():
            if n >= 2 and shape not in seen_shapes:
                first = next(m["bar"] for m in mot if m["ivs"] == shape and a <= m["bar"] < b)
                found.append((first, f"motif {shape}"))
                break
        seen_shapes |= set(here)
        windows.append({"bars": (a + 1, b), "ideas": [t for _, t in found]})
        ideas += [(bar, t) for bar, t in found]
    judged = windows[1:] or windows
    dry = [w for w in judged if not w["ideas"]]
    score = 1 - len(dry) / max(1, len(judged))
    ev = (f"{len(judged) - len(dry)}/{len(judged)} sixteen-bar spans bring something new"
          + ("; nothing new in bars " + ", ".join("%d-%d" % w["bars"] for w in dry) if dry else ""))
    return _res("new_idea_every_16", score, ev, [bar + 1 for bar, _ in ideas],
                {"windows": windows, "ideas": [{"bar": bar + 1, "idea": t} for bar, t in ideas]})


def motifs_return(song: dict, rows: list[dict], secs: list[dict]) -> dict:
    mot = F.motifs(song)
    if len(mot) < 8:
        return _res("motifs_return", None, "too few lead notes for motifs")
    first_bar = mot[0]["bar"]
    # a motif worth following has at least two real moves and isn't its own inversion or retrograde
    opening = [m for m in mot if m["bar"] < first_bar + 8 and sum(1 for x in m["steps"] if x) >= 2]
    if not opening:
        return _res("motifs_return", 0.2, "the opening has no motif: its lead only repeats notes")
    top = [s for s, _ in Counter(m["steps"] for m in opening).most_common(4)]
    reps = [next(m for m in opening if m["steps"] == s) for s in top]
    later = [m for m in mot if m["bar"] >= first_bar + 16]
    found, points, bars = [], 0.0, []
    for a in reps:
        kinds = Counter()
        where = {}
        for b in later:
            t = F.transform(a, b)
            if t:
                kinds[t] += 1
                where.setdefault(t, b["bar"] + 1)
        changed = [k for k in kinds if k != "exact"]
        strong = [k for k in changed if k != "contour"]
        points += 1.0 if strong else 0.6 if changed else 0.3 if kinds else 0.0
        found.append({"motif": list(a["steps"]), "from_bar": a["bar"] + 1, "returns": dict(kinds), "first": where})
        bars += list(where.values())
    score = points / max(1, len(reps))
    names = [f"{tuple(f['motif'])}: " + (", ".join(f"{k} ×{n}" for k, n in f["returns"].items()) or "never") for f in found]
    return _res("motifs_return", score, "opening motifs → " + "; ".join(names), bars, {"motifs": found})


def bridge_returns(song: dict, rows: list[dict], secs: list[dict]) -> dict:
    br = [s for s in secs if s["kind"] in ("bridge", "break")]
    if not br:
        return _res("bridge_returns", None, "no bridge")
    b = br[-1]
    nxt = next((s for s in secs if s["start"] == b["start"] + b["bars"]), None)
    a0, a1 = b["start"] - 1, b["start"] - 1 + b["bars"]
    rest = np.mean([F.pcs_hist(song, s["start"] - 1, s["start"] - 1 + s["bars"]) for s in secs if s is not b], axis=0)
    pc_far = 1 - F.cos(F.pcs_hist(song, a0, a1), rest)
    loops = {s.get("loop") for s in secs if s is not b}
    new_loop = 1.0 if b.get("loop") not in loops else 0.0
    others = [s["energy"] for s in secs if s is not b and s["kind"] not in ("intro", "outro")]
    e_far = abs(b["energy"] - float(np.mean(others))) if others else 0.0
    g_far = 1 - F.cos(F.groove(rows[a0:a1]), F.groove([r for r in rows if not a0 <= r["bar"] < a1]))
    depart = float(np.clip(0.35 * min(1.0, pc_far * 4) + 0.3 * new_loop + 0.2 * min(1.0, e_far * 4) + 0.15 * min(1.0, g_far * 3), 0, 1))
    if nxt is None:
        return _res("bridge_returns", depart * 0.5, f"the bridge departs ({depart:.2f}) but the song ends there",
                    range(b["start"], b["start"] + b["bars"]))
    tail = rows[a1 - 2:a1]
    dominant = 1.0 if tail[-1]["func"] == "D" else 0.5 if tail[-1]["func"] == "S" else 0.0
    rise = 1.0 if tail[-1]["energy"] > rows[a0]["energy"] or "tom" in tail[-1]["layers"] else 0.0
    twin = next((s for s in secs if s["kind"] == nxt["kind"] and s is not nxt and s["start"] < b["start"]), None)
    if twin:
        n0 = nxt["start"] - 1
        t0 = twin["start"] - 1
        k = min(8, nxt["bars"], twin["bars"])
        like = 0.5 * F.cos(F.groove(rows[n0:n0 + k]), F.groove(rows[t0:t0 + k])) + \
            0.5 * F.cos(F.pcs_hist(song, n0, n0 + k), F.pcs_hist(song, t0, t0 + k))
    else:
        like = 0.5
    home = 1.0 if rows[nxt["start"] - 1]["func"] == "T" else 0.5
    inevitable = 0.35 * dominant + 0.2 * rise + 0.3 * like + 0.15 * home
    ev = (f"{b['name']} departs {depart:.2f} (pitch {pc_far:.2f}, {'new' if new_loop else 'same'} chords, energy Δ{e_far:.2f}, "
          f"groove Δ{g_far:.2f}); return into {nxt['name']} {inevitable:.2f} (ends on {tail[-1]['func']}, "
          f"{'rises' if rise else 'flat'}, like {twin['name'] if twin else '—'} {like:.2f}, lands on {rows[nxt['start'] - 1]['func']})")
    score = min(depart, inevitable) * 0.5 + 0.5 * (depart + inevitable) / 2
    return _res("bridge_returns", score / 0.85, ev, [a1 - 1, a1, a1 + 1],
                {"depart": round(depart, 3), "inevitable": round(inevitable, 3)})


LAWS = {"groove_identity": groove_identity, "final_chorus_biggest": final_chorus_biggest,
        "new_idea_every_16": new_idea_every_16, "motifs_return": motifs_return, "bridge_returns": bridge_returns}


def judge(song: dict, only: list[str] | None = None) -> list[dict]:
    rows = F.grid(song)
    secs = F.sections(song, rows)
    return [fn(song, rows, secs) for k, fn in LAWS.items() if not only or k in only]


def score(results: list[dict]) -> float:
    s = [r["score"] for r in results if r["score"] is not None]
    return round(float(np.mean(s)), 4) if s else 0.0


def text(results: list[dict]) -> str:
    return "\n".join(("✓" if r["passed"] else "✗") + f" {r['title']}: "
                     + ("n/a" if r["score"] is None else "%.2f" % r["score"]) + f" — {r['evidence']}" for r in results)


def main():
    import argparse

    import electronium as EL
    import electronium_song as ES
    import operator_ as OP
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bounty", default="1969")
    ap.add_argument("--brief", default="")
    ap.add_argument("--mid", help="judge a .mid instead")
    a = ap.parse_args()
    if a.mid:
        song = F.from_midi(a.mid)
    else:
        pl = ES.plan(a.bounty)
        op = OP.operate(pl["sections"], EL.patch(pl["patch"]), a.brief, log=lambda *_: None, bpm=pl["bpm"])
        song = F.song_from(pl, ES.perform(pl, op))
    res = judge(song)
    print(text(res))
    print(f"laws: {score(res):.2f}")


if __name__ == "__main__":
    main()
