"""Six judges of a song, and a fair way to rank many songs by all six at once.

    composition    the lead (steps, leaps, range, variety), the harmony (in key, harmonic rhythm, cadence), motifs, bridge
    rhythm         groove identity, syncopation, bar-to-bar variation, fills into sections, feel (micro-timing)
    arrangement    the final chorus, a new idea every 16 bars, section contrast, a lighter intro and outro, length
    sound          register clashes (low-end mud, crowded mids, parts on top of each other); a render's masking
                   and spectrum when studio.py has listened to one
    production     dynamics, section loudness, peak polyphony; LF, stereo and transients from a render
    taste          your ratings: the rated songs nearest this one, and your taste in the machine's ideas

Every score is 0-1 and comes with its trace: each measurement, its value, the range it aims for and what it gave,
so a ranking can always say why. Nothing here is learned except taste, and taste only from your own ratings.

    evaluate(song, audio=None) -> {"scores", "evaluators", "laws", "features", "total"}
    rank(candidates)           -> Pareto fronts (no candidate in a front is beaten on every judge by another), then
                                  the weighted total; each with who beats it and on what
"""
from __future__ import annotations

import numpy as np

import features as F
import laws as L

EVALUATORS = ("composition", "rhythm", "arrangement", "sound", "production", "taste")
WEIGHTS = {"composition": 1.0, "rhythm": 1.0, "arrangement": 1.0, "sound": 0.8, "production": 0.6, "taste": 1.0}


def band(x: float, lo: float, hi: float, soft: float) -> float:
    """1 inside [lo, hi], falling to 0 `soft` outside it."""
    if lo <= x <= hi:
        return 1.0
    d = lo - x if x < lo else x - hi
    return float(max(0.0, 1 - d / soft)) if soft > 0 else 0.0


class Judge:
    def __init__(self, name: str):
        self.name, self.trace = name, []

    def add(self, what: str, value, score: float | None, weight: float = 1.0, target: str = ""):
        if score is None:
            self.trace.append({"what": what, "value": value, "target": target, "score": None, "weight": 0.0})
            return
        self.trace.append({"what": what, "value": value if not isinstance(value, float) else round(value, 4),
                           "target": target, "score": round(float(np.clip(score, 0, 1)), 3), "weight": weight})

    def law(self, res: dict, weight: float = 1.0):
        self.add(f"law: {res['title']}", res["evidence"], res["score"], weight, f"≥ {L.PASS}")

    def done(self, note: str = "") -> dict:
        w = [t for t in self.trace if t["score"] is not None and t["weight"] > 0]
        s = sum(t["score"] * t["weight"] for t in w) / sum(t["weight"] for t in w) if w else 0.5
        return {"name": self.name, "score": round(float(s), 4), "trace": self.trace, **({"note": note} if note else {})}


def _laws(ctx) -> dict:
    return {r["law"]: r for r in ctx["laws"]}


def composition(song: dict, ctx: dict) -> dict:
    j, f, lw = Judge("composition"), ctx["features"], _laws(ctx)
    j.add("lead: share of moves by step", f["lead_stepwise"], band(f["lead_stepwise"], 0.45, 0.85, 0.3), 1.0, "0.45-0.85")
    j.add("lead: share of leaps over a fifth", f["lead_leaps"], band(f["lead_leaps"], 0.0, 0.12, 0.15), 0.5, "≤ 0.12")
    j.add("lead: range (semitones)", f["lead_range"], band(f["lead_range"], 10, 24, 8), 1.0, "10-24")
    j.add("lead: distinct pitches", f["lead_pitches"], band(f["lead_pitches"], 7, 20, 5), 0.5, "7-20")
    j.add("notes in key", f["in_key"], band(f["in_key"], 0.85, 1.0, 0.2), 1.0, "≥ 0.85")
    j.add("chord changes per bar", f["harmonic_rhythm"], band(f["harmonic_rhythm"], 0.2, 1.0, 0.3), 0.5, "0.2-1")
    last = ctx["rows"][-1]["func"] if ctx["rows"] else "T"
    j.add("ends at home (tonic)", last, 1.0 if last == "T" else 0.4, 0.5, "T")
    j.law(lw["motifs_return"], 1.5)
    j.law(lw["bridge_returns"], 1.0)
    return j.done()


def rhythm(song: dict, ctx: dict) -> dict:
    j, f, lw, rows = Judge("rhythm"), ctx["features"], _laws(ctx), ctx["rows"]
    j.law(lw["groove_identity"], 2.0)
    j.add("lead: share of notes off the beat", f["lead_offbeat"], band(f["lead_offbeat"], 0.15, 0.6, 0.25), 1.0, "0.15-0.6")
    j.add("drum hits per bar", f["drum_density"], band(f["drum_density"], 6, 40, 15), 0.5, "6-40")
    drummed = [r for r in rows if r["drum_hits"]]
    pat = [np.concatenate([np.array(r["kick16"]) > 0, np.array(r["snare16"]) > 0,
                           0.5 * (np.array(r["hat16"]) > 0)]).astype(float) for r in drummed]
    var = float(np.mean([1 - F.cos(a, b) for a, b in zip(pat, pat[1:])])) if len(pat) > 1 else 0.0
    j.add("change from bar to bar (1 - likeness of drum patterns)", var,
          band(var, 0.04, 0.3, 0.15) if drummed else None, 1.0, "0.04-0.3")
    secs = song["sections"]
    into, filled = 0, 0
    for s in secs[1:]:
        b = s["start"] - 2
        if 0 <= b < len(rows) and rows[b]["drum_hits"]:
            into += 1
            prev = rows[max(0, b - 4):b]
            mean = np.mean([r["drum_hits"] for r in prev]) if prev else 0
            filled += ("tom" in rows[b]["layers"]) or rows[b]["drum_hits"] > mean * 1.25
    j.add("sections entered with a fill", f"{filled}/{into}", filled / into if into else None, 0.5, "most")
    offs = [n[4] for v in song["parts"].values() for n in v] + [n[4] for n in song["drums"]]
    feel = float(np.std(offs)) if offs else 0.0
    j.add("feel: spread of micro-timing", feel, band(feel, 0.002, 0.03, 0.02), 0.5, "0.002-0.03")
    return j.done()


def arrangement(song: dict, ctx: dict) -> dict:
    j, f, lw, secs = Judge("arrangement"), ctx["features"], _laws(ctx), ctx["sections"]
    j.law(lw["final_chorus_biggest"], 2.0)
    j.law(lw["new_idea_every_16"], 1.5)
    j.add("section contrast (spread of energy)", f["contrast"], band(f["contrast"], 0.08, 0.3, 0.08), 1.0, "0.08-0.3")
    ch = [s["energy"] for s in secs if s["kind"] == "chorus"] or [max((s["energy"] for s in secs), default=0)]
    for kind in ("intro", "outro"):
        s = next((s for s in secs if s["kind"] == kind), None)
        if s:
            j.add(f"{kind} lighter than the choruses", round(s["energy"], 3), 1.0 if s["energy"] < np.mean(ch) - 0.05 else 0.3,
                  0.5, f"< {np.mean(ch) - 0.05:.2f}")
    j.add("length (seconds)", f["seconds"], band(f["seconds"], 150, 330, 90), 0.5, "150-330")
    full = np.mean([len(r["active"]) >= max(1, f["parts"]) for r in ctx["rows"]]) if ctx["rows"] else 0
    j.add("bars with every part playing", float(full), band(float(full), 0, 0.35, 0.3), 0.5, "≤ 0.35")
    return j.done()


def _sounding(song: dict, step: float = 0.5):
    """At each eighth: which parts sound and at what pitches."""
    n = int(song["bars"] * 4 / step)
    at = [dict() for _ in range(n)]
    for k, v in song["parts"].items():
        for e in v:
            for i in range(int(e[0] / step), min(n, int((e[0] + max(e[1], step)) / step))):
                at[i].setdefault(k, []).append(e[2])
    return at


def sound(song: dict, ctx: dict) -> dict:
    j = Judge("sound")
    at = ctx.setdefault("_sounding", _sounding(song))
    busy = [a for a in at if a] or [{}]
    mud = np.mean([sum(1 for ps in a.values() if min(ps) < 52) >= 2 for a in busy])
    j.add("low end: two or more parts below E3 at once", float(mud), band(float(mud), 0, 0.1, 0.3), 1.0, "≤ 0.1")
    mids = np.mean([sum(1 for ps in a.values() if any(55 <= p <= 72 for p in ps)) for a in busy])
    j.add("crowded mids: parts sounding in G3-C5", float(mids), band(float(mids), 0, 3, 2), 1.0, "≤ 3")
    med = sorted((float(np.median([e[2] for e in v])), k) for k, v in song["parts"].items() if v and k != "lead_hi")
    gaps = [b[0] - a[0] for a, b in zip(med, med[1:])]
    spread = np.mean([g >= 3 for g in gaps]) if gaps else 1.0
    j.add("parts in registers of their own (≥ 3 semitones apart)", float(spread), float(spread), 0.7, "all")
    unis = np.mean([any(len(set(ps) & set(qs)) for x, ps in a.items() for y, qs in a.items() if x < y
                        and {x, y} != {"lead", "sidekick"} and {x, y} != {"lead", "lead_hi"}) for a in busy])
    j.add("parts landing on the same pitch", float(unis), band(float(unis), 0, 0.15, 0.3), 0.5, "≤ 0.15")
    audio = (ctx.get("audio") or {}).get("sound") or {}
    for k, v in audio.items():
        j.add(f"render: {k}", v, v, 1.0, "high")
    return j.done("" if audio else "from the notes; render and run the studio for masking measured in sound")


def production(song: dict, ctx: dict) -> dict:
    j = Judge("production")
    vel = [n[3] for v in song["parts"].values() for n in v] + [n[3] for n in song["drums"]]
    dyn = float(np.std(vel)) if vel else 0.0
    j.add("dynamics: spread of velocities", dyn, band(dyn, 0.06, 0.25, 0.1), 1.0, "0.06-0.25")
    by_sec = []
    for s in song["sections"]:
        a, b = (s["start"] - 1) * 4, (s["start"] - 1 + s["bars"]) * 4
        v = [n[3] for x in song["parts"].values() for n in x if a <= n[0] < b] + [n[3] for n in song["drums"] if a <= n[0] < b]
        if v:
            by_sec.append(float(np.sum(v)) / s["bars"])
    loud = float(np.std(by_sec) / (np.mean(by_sec) or 1)) if by_sec else 0.0
    j.add("section loudness contrast (relative)", loud, band(loud, 0.15, 0.6, 0.2), 1.0, "0.15-0.6")
    at = ctx.setdefault("_sounding", _sounding(song))
    peak = max((sum(len(ps) for ps in a.values()) for a in at), default=0)
    j.add("peak notes at once", peak, band(peak, 0, 18, 10), 0.5, "≤ 18")
    audio = (ctx.get("audio") or {}).get("production") or {}
    for k, v in audio.items():
        j.add(f"render: {k}", v, v, 1.0, "high")
    if not audio:
        for k in ("low frequencies", "stereo image", "transients"):
            j.add(f"render: {k}", "needs a render (studio.py)", None)
    return j.done("" if audio else "from the notes; render and run the studio for LF, stereo and transients")


def taste_judge(song: dict, ctx: dict) -> dict:
    import taste as T
    j = Judge("taste")
    s, near = T.song_taste(ctx["features"])
    if s is not None:
        j.add("songs you rated, nearest first", ", ".join(f"{r} {y:+.1f}" for r, y, _ in near[:3]), (s + 1) / 2, 2.0, "liked")
    m = T.model()
    if m is not None and song.get("ideas"):
        b = float(np.mean([T.bonus(c) for c in song["ideas"]]))
        j.add("your taste in its ideas", round(b, 3), 0.5 + b / 4, 1.0, "> 0")
    if not [t for t in j.trace if t["score"] is not None]:
        j.add("songs you rated", "fewer than 3 ratings", None, 0.0, "≥ 3")
        out = j.done("no ratings yet: neutral (rate songs in the Observatory)")
        out["neutral"] = True
        return out
    return j.done()


JUDGES = {"composition": composition, "rhythm": rhythm, "arrangement": arrangement, "sound": sound,
          "production": production, "taste": taste_judge}


def evaluate(song: dict, audio: dict | None = None, weights: dict | None = None) -> dict:
    rows = F.grid(song)
    secs = F.sections(song, rows)
    ctx = {"rows": rows, "sections": secs, "features": F.features(song, rows), "audio": audio}
    ctx["laws"] = [fn(song, rows, secs) for fn in L.LAWS.values()]
    ev = [JUDGES[k](song, ctx) for k in EVALUATORS]
    scores = {e["name"]: e["score"] for e in ev}
    w = weights or WEIGHTS
    total = sum(scores[k] * w.get(k, 1) for k in scores) / sum(w.get(k, 1) for k in scores)
    return {"scores": scores, "evaluators": ev, "laws": ctx["laws"], "features": ctx["features"], "total": round(total, 4)}


# ---------------------------------------------------------------- ranking many

def dominates(a: dict, b: dict, keys=EVALUATORS, eps: float = 1e-9) -> bool:
    return all(a[k] >= b[k] - eps for k in keys) and any(a[k] > b[k] + eps for k in keys)


def fronts(scores: list[dict], keys=EVALUATORS) -> list[list[int]]:
    """Non-dominated sorting: front 0 holds the candidates no other beats on every judge, front 1 those beaten
    only by front 0, and so on. O(n²); hundreds of candidates take milliseconds."""
    n = len(scores)
    beaten_by = [[] for _ in range(n)]
    beats = [0] * n
    for i in range(n):
        for k in range(n):
            if i != k and dominates(scores[k], scores[i], keys):
                beaten_by[i].append(k)
                beats[k] += 1
    left, out = set(range(n)), []
    while left:
        f = sorted(i for i in left if not any(k in left for k in beaten_by[i]))
        out.append(f)
        left -= set(f)
    return out


def crowding(scores: list[dict], idx: list[int], keys=EVALUATORS) -> dict[int, float]:
    d = {i: 0.0 for i in idx}
    if len(idx) <= 2:
        return {i: float("inf") for i in idx}
    for k in keys:
        o = sorted(idx, key=lambda i: scores[i][k])
        span = scores[o[-1]][k] - scores[o[0]][k] or 1.0
        d[o[0]] = d[o[-1]] = float("inf")
        for a, b, c in zip(o, o[1:], o[2:]):
            d[b] += (scores[c][k] - scores[a][k]) / span
    return d


def rank(cands: list[dict], keys=EVALUATORS, weights: dict | None = None) -> list[dict]:
    """cands: [{"id", "scores": {judge: 0-1}, ...}] -> the same dicts, best first, each with "front" (0 = Pareto
    best), "total" (the weighted mean), "crowding" and "why" (its place, in words)."""
    keys = [k for k in keys if len({c["scores"].get(k, 0.5) for c in cands}) > 1] or list(keys)
    w = weights or WEIGHTS
    sc = [{k: float(c["scores"].get(k, 0.5)) for k in EVALUATORS} for c in cands]
    fr = fronts(sc, keys)
    for f_i, f in enumerate(fr):
        cd = crowding(sc, f, keys)
        for i in f:
            c = cands[i]
            c["front"] = f_i
            c["crowding"] = cd[i]
            c["total"] = round(sum(sc[i][k] * w.get(k, 1) for k in EVALUATORS) / sum(w.get(k, 1) for k in EVALUATORS), 4)
            if f_i == 0:
                best = [k for k in keys if sc[i][k] >= max(s[k] for s in sc) - 1e-9]
                c["why"] = "no candidate beats it on every judge" + (f"; best of all at {', '.join(best)}" if best else "")
            else:
                k = next(k for k in fr[f_i - 1] if dominates(sc[k], sc[i], keys))
                gaps = sorted(((sc[k][x] - sc[i][x], x) for x in keys), reverse=True)
                c["why"] = (f"front {f_i + 1}: {cands[k].get('id', k)} is at least as good on every judge, better at "
                            + ", ".join(f"{x} (+{g:.2f})" for g, x in gaps[:3] if g > 1e-9))
    order = sorted(range(len(cands)), key=lambda i: (cands[i]["front"], -cands[i]["total"], str(cands[i].get("id", i))))
    return [cands[i] for i in order]


def text(res: dict) -> str:
    out = [f"total {res['total']:.2f}  " + "  ".join(f"{k} {v:.2f}" for k, v in res["scores"].items())]
    for e in res["evaluators"]:
        out.append(f"\n{e['name']} {e['score']:.2f}" + (f"  ({e['note']})" if e.get("note") else ""))
        for t in e["trace"]:
            mark = "    —" if t["score"] is None else "%5.2f" % t["score"]
            out.append("  " + mark + " " + str(t["what"]) + ": " + str(t["value"])
                       + ("  [" + t["target"] + "]" if t["target"] else ""))
    return "\n".join(out)


if __name__ == "__main__":
    import argparse

    import electronium as EL
    import electronium_song as ES
    import operator_ as OP
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bounty", default="1969")
    ap.add_argument("--brief", default="")
    a = ap.parse_args()
    pl = ES.plan(a.bounty)
    op = OP.operate(pl["sections"], EL.patch(pl["patch"]), a.brief, log=lambda *_: None, bpm=pl["bpm"])
    print(text(evaluate(F.song_from(pl, ES.perform(pl, op)))))
