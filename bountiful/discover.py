"""The discovery machine: write hundreds of candidate songs, throw out the broken ones, rank the rest, show a few.

    candidates  for each origin (a bounty, with the brief and intents you gave): the plain song, a "doctored"
                version (changes aimed at its weakest judged points: fills into sections that enter without one,
                a lift for a last chorus that is not the biggest, a motif callback when motifs do not return,
                a breath before choruses when sections do not contrast), and children bred from both with
                one to three random changes from evolve.py.
    rejection   a candidate that breaks any musical law, or scores under the floor on any judge, is dropped,
                and the reason counted.
    ranking     the survivors are Pareto-ranked on the six judges (evaluators.rank): front 0 holds the songs
                nothing else beats on every judge. Ties within a front go to the weighted total.
    presenting  the top `keep`, at most `per_origin` from one origin so the shortlist is varied, each with why
                it ranks where it does, its weakest points, and its DNA id.

Every candidate is a DNA (lineage.py): origin plus seeded changes. A run is deterministic for the same
arguments, and any song it showed you can be grown again from its id, exported and rendered.
"""
from __future__ import annotations

import json
import time

import numpy as np

import evaluators as V
import evolve as EV
import lineage as G
from paths import DATA

LAST = DATA / "discover_last.json"
FLOOR = 0.35          # a candidate under this on any judge is rejected
MAX_CANDIDATES = 2000


def weakest(res: dict, n: int = 3) -> list[dict]:
    """The trace items costing the most: (1 - score) x weight, judged items only."""
    items = [dict(t, judge=e["name"]) for e in res["evaluators"] for t in e["trace"] if t["score"] is not None]
    items.sort(key=lambda t: (-(1 - t["score"]) * t["weight"], t["what"]))
    short = lambda v: v if not isinstance(v, str) or len(v) <= 90 else v[:87] + "..."  # noqa: E731
    return [{"judge": t["judge"], "what": t["what"], "value": short(t["value"]), "target": t["target"], "score": round(t["score"], 3)}
            for t in items[:n] if t["score"] < 0.95]


def doctor(song: dict, res: dict, seed: int = 0) -> list[dict]:
    """Changes aimed at what the judges found weakest. Each says which finding it answers."""
    rng = np.random.default_rng([seed & 0xFFFFFFFF, 11])
    laws = {r["law"]: r for r in res["laws"]}
    rows_drum = {i for i, n in enumerate(_drum_bars(song)) if n}
    out = []
    secs = song["sections"]
    unfilled = []
    for s in secs[1:]:
        b = s["start"] - 2
        if b in rows_drum and not _toms_in(song, b):
            unfilled.append(s)
    for s in unfilled[:3]:
        out.append({"op": "fill", "args": {"bar": s["start"] - 1, "length": 1}, "seed": int(rng.integers(1, 2**31)),
                    "why": f"rhythm: {s['name']} entered without a fill"})
    if laws.get("final_chorus_biggest", {}).get("score", 1) < 0.85:
        out.append({"op": "lift_last_chorus", "args": {"amount": 1.0}, "seed": int(rng.integers(1, 2**31)),
                    "why": "arrangement: the last chorus should be the biggest"})
    if laws.get("motifs_return", {}).get("score", 1) < 0.8:
        later = [s for s in secs if s["kind"] in ("chorus", "bridge") and s["start"] > 16] or secs[-2:]
        out.append({"op": "motif_callback", "args": {"to_bar": later[-1]["start"], "which": 0, "how": "diatonic", "steps": 2},
                    "seed": int(rng.integers(1, 2**31)), "why": "composition: an early motif should come back"})
    var = next((t["value"] for e in res["evaluators"] for t in e["trace"] if t["what"].startswith("change from bar to bar")), 0)
    if isinstance(var, (int, float)) and var > 0.3:
        for s in _restless(song)[:3]:
            out.append({"op": "steady_groove", "args": {"bars": [s["start"], s["start"] + s["bars"] - 1], "amount": 0.7},
                        "seed": int(rng.integers(1, 2**31)), "why": f"rhythm: the drums in {s['name']} wander bar to bar"})
    contrast = res["features"].get("contrast", 0.2)
    if contrast < 0.1:
        for s in [x for x in secs[1:] if x["kind"] == "chorus"][:2]:
            out.append({"op": "breathe", "args": {"bars": [s["start"] - 1, s["start"] - 1], "drums": "thin"},
                        "seed": int(rng.integers(1, 2**31)), "why": f"arrangement: make room before {s['name']}"})
    return out


def _restless(song) -> list[dict]:
    """Sections with drums, most restless first (mean pattern change between neighbouring bars, over 0.3)."""
    import features as F
    out = []
    for s in song["sections"]:
        if s["kind"] in ("intro", "outro"):
            continue       # these are meant to sound unlike the body of the song
        bars = [b for b in range(s["start"] - 1, s["start"] - 1 + s["bars"]) if EV._bar_drums(song["drums"], b)]
        pats = [EV._pattern(EV._bar_drums(song["drums"], b), b) for b in bars]
        if len(pats) > 2:
            v = float(np.mean([1 - F.cos(x, y) for x, y in zip(pats, pats[1:])]))
            if v > 0.3:
                out.append((v, s))
    return [s for v, s in sorted(out, key=lambda x: (-x[0], x[1]["start"]))]


def _drum_bars(song):
    n = [0] * song["bars"]
    for t, *_ in song["drums"]:
        if 0 <= int(t // 4) < song["bars"]:
            n[int(t // 4)] += 1
    return n


def _toms_in(song, bar0):
    import features as F
    return [x for x in song["drums"] if bar0 * 4 <= x[0] < bar0 * 4 + 4 and F.DRUM.get(x[2]) == "tom"]


def origins(n: int, seed: int, bounties=None, brief: str = "", intents=None, **kw) -> list[dict]:
    if bounties:
        names = [str(b) for b in bounties][:n] if n else [str(b) for b in bounties]
    else:
        rng = np.random.default_rng([seed & 0xFFFFFFFF, 3])
        names = sorted({str(int(x)) for x in rng.integers(1, 100000, size=n * 2)}, key=lambda s: _h(s, seed))[:n]
    return [G.origin(b, brief=brief, intents=intents, **kw) for b in names]


def _h(s, seed):
    import zlib
    return zlib.crc32(f"{seed}:{s}".encode())


def _reject(res: dict) -> str | None:
    bad = [r["law"] for r in res["laws"] if not r["passed"]]
    if bad:
        return "breaks " + bad[0]
    low = [k for k, v in res["scores"].items() if v < FLOOR]
    if low:
        return "too weak at " + low[0]
    return None


def _slim(res: dict) -> dict:
    return {"scores": res["scores"], "laws": res["laws"], "evaluators": res["evaluators"], "features": res["features"]}


def _eval_one(song):
    return _slim(V.evaluate(song))


def _evaluate_all(songs: list, workers: int | None) -> list[dict]:
    """Judge many songs, in worker processes when there are enough to pay for them. Order is kept, and evaluate
    is pure, so the result is the same either way."""
    import os
    w = min(workers if workers is not None else 4, os.cpu_count() or 1)
    if w <= 1 or len(songs) < 40:
        return [_eval_one(s) for s in songs]
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor
    try:
        with ProcessPoolExecutor(w, mp_context=mp.get_context("spawn")) as ex:
            return list(ex.map(_eval_one, songs, chunksize=max(1, len(songs) // (w * 4))))
    except (OSError, RuntimeError):
        return [_eval_one(s) for s in songs]


def discover(n: int = 300, seed: int = 0, bounties=None, brief: str = "", intents=None, n_origins: int | None = None,
             keep: int = 8, per_origin: int = 2, depth=(1, 3), families=None, progress=None, save: bool = False,
             store=None, write_last: bool = True, workers: int | None = None) -> dict:
    """Run the machine. Returns {"presented": [...], "rejected": {reason: count}, "considered", "survivors",
    "seconds", "args"}. Every presented entry carries its DNA; nothing else is needed to recover it."""
    t0 = time.time()
    n = int(np.clip(n, 1, MAX_CANDIDATES))
    n_origins = n_origins or (len(bounties) if bounties else max(1, min(24, n // 15)))
    ors = origins(n_origins, seed, bounties, brief, intents)
    per = max(1, n // len(ors))
    rng = np.random.default_rng([seed & 0xFFFFFFFF, 5])
    cands, rejected, seen, todo = [], {}, set(), []

    def judge(dna, song, kind, res):
        why = _reject(res)
        if why:
            rejected[why] = rejected.get(why, 0) + 1
            return
        cands.append({"id": G.dna_id(dna), "dna": dna, "kind": kind, "scores": res["scores"], "weakest": weakest(res),
                      "laws": sum(r["passed"] for r in res["laws"]), "describe": G.describe(dna, song),
                      "bounty": dna["origin"]["bounty"]})

    def queue(dna, song, kind):
        i = G.dna_id(dna)
        if i not in seen:
            seen.add(i)
            todo.append((dna, song, kind))

    total = 0
    for k, o in enumerate(ors):
        if progress:
            progress(k, len(ors) + 1, f"writing from bounty {o['origin']['bounty']}")
        song = G.grow(o)
        res = V.evaluate(song)
        seen.add(G.dna_id(o))
        judge(o, song, "origin", res)
        made = 1
        fixes = doctor(song, res, seed=int(rng.integers(1, 2**31)))
        parents = [(o, song)]
        if fixes:
            d2 = G.child(o, fixes)
            s2 = EV.apply_all(song, fixes)
            queue(d2, s2, "doctored")
            made += 1
            parents.append((d2, s2))
        total += made
        for j in range(max(0, per - made)):
            pd, ps = parents[j % len(parents)]
            dep = int(rng.integers(depth[0], depth[1] + 1))
            kids = EV.breed(ps, 1, seed=int(rng.integers(1, 2**31)), families=families, depth=dep)
            total += 1
            if kids:
                ch, ks = kids[0]
                queue(G.child(pd, ch), ks, "bred")
            else:
                rejected["no change took"] = rejected.get("no change took", 0) + 1
    if progress:
        progress(len(ors), len(ors) + 1, f"judging {len(todo)} candidates")
    for (dna, song, kind), res in zip(todo, _evaluate_all([s for _, s, _ in todo], workers)):
        judge(dna, song, kind, res)
    ranked = V.rank(cands) if cands else []
    shown, by_origin = [], {}
    for c in ranked:
        if by_origin.get(c["bounty"], 0) >= per_origin:
            continue
        by_origin[c["bounty"]] = by_origin.get(c["bounty"], 0) + 1
        shown.append(c)
        if len(shown) >= keep:
            break
    for r, c in enumerate(shown):
        c["rank"] = r + 1
        if save:
            G.save(c["dna"], scores=c["scores"], total=c["total"], note=f"discovery seed {seed}, rank {r + 1}", store=store)
    out = {"presented": shown, "rejected": dict(sorted(rejected.items(), key=lambda kv: -kv[1])), "considered": total,
           "survivors": len(cands), "fronts": max((c["front"] for c in ranked), default=-1) + 1,
           "seconds": round(time.time() - t0, 2),
           "args": {"n": n, "seed": seed, "bounties": bounties, "brief": brief, "intents": intents, "keep": keep}}
    if write_last:
        try:
            LAST.parent.mkdir(parents=True, exist_ok=True)
            LAST.write_text(json.dumps(out, default=str))
        except OSError:
            pass
    return out


def text(run: dict) -> str:
    lines = [f"considered {run['considered']}, kept {run['survivors']}, rejected "
             + (", ".join(f"{v} {k}" for k, v in run["rejected"].items()) or "none") + f"  ({run['seconds']} s)"]
    for c in run["presented"]:
        sc = " ".join("%s %.2f" % (k[:4], v) for k, v in c["scores"].items())
        lines.append(f"\n#{c['rank']}  {c['id']}  total {c['total']:.3f}  front {c['front']}  [{c['kind']}]")
        lines.append("    " + c["describe"])
        lines.append("    " + sc)
        lines.append("    why: " + c["why"])
        if c["weakest"]:
            lines.append("    weakest: " + "; ".join("%s (%s, wants %s)" % (w["what"], w["value"], w["target"]) for w in c["weakest"]))
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--bounty", action="append")
    ap.add_argument("--brief", default="")
    ap.add_argument("--keep", type=int, default=8)
    ap.add_argument("--save", action="store_true", help="add the shortlist to the lineage")
    a = ap.parse_args()
    print(text(discover(a.n, a.seed, a.bounty, a.brief, keep=a.keep, save=a.save)))
