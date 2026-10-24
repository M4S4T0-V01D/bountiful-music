"""The living instrument network: the parts of a song listening to each other, within strict limits.

A song's parts and drums are nodes; a shared context (energy per bar, the section of each bar, where the
lead rests, how busy each part is, where the kick lands) is read by every edge. An edge is typed and bounded:

    duck    kick -> bass/pad/keys    sidechain in the mix (the renderer's duck), depth <= 0.5
    answer  lead -> counter/arp      the answerer is softened under the lead and kept where it rests
    follow  lead -> lead_hi/sidekick the double's dynamics follow the lead's
    thin    lead -> accompaniment    where the lead is busy, the weakest off-beat accompaniment notes drop out
    accent  energy -> hats           hat velocity rides the section energy
    swell   energy -> pad/keys       gain automation in the mix, rising into high-energy sections, <= 3 dB

Every edge's amount is clipped to LIMITS, no note's velocity moves more than MAX_VEL from where it started,
no part loses more than MAX_DROP of its notes, and no note's pitch or timing is ever touched, so harmony,
melody and groove belong to the composition. The pass is deterministic and logs every change it made.

    song, report = network.apply(song)               # the default graph for the parts the song has
    mix = network.mix(report)                        # {"tracks": {name: {"duck": ...}}, "automation": [...]}
"""
from __future__ import annotations

import copy
from collections import defaultdict

LIMITS = {"duck": 0.5, "answer": 0.35, "follow": 0.6, "thin": 0.25, "accent": 0.2, "swell": 3.0}
MAX_VEL = 0.2          # the most any note's velocity may move, all edges together
MAX_DROP = 0.15        # the most of a part's notes all edges together may remove
KINDS = tuple(LIMITS)

ENERGY = {"intro": 0.35, "verse": 0.55, "pre": 0.65, "chorus": 0.9, "bridge": 0.5, "break": 0.3, "drop": 1.0,
          "outro": 0.3}


def edge(kind, src, dst, amount, **kw) -> dict:
    if kind not in LIMITS:
        raise ValueError(f"unknown edge {kind!r}")
    return {"kind": kind, "src": src, "dst": dst, "amount": amount, **kw}


# ---------------------------------------------------------------- shared context

def context(song: dict) -> dict:
    import features as F
    bars = int(song["bars"])
    section = [None] * (bars + 1)
    for s in song["sections"]:
        for b in range(s["start"], min(bars, s["start"] + s["bars"] - 1) + 1):
            section[b] = s
    density = {p: [0] * (bars + 1) for p in song["parts"]}
    for p, notes in song["parts"].items():
        for n in notes:
            b = int(n[0] // 4) + 1
            if 1 <= b <= bars:
                density[p][b] += 1
    total = [sum(density[p][b] for p in density) for b in range(bars + 1)]
    peak = max(total) or 1
    energy = [0.0] * (bars + 1)
    for b in range(1, bars + 1):
        base = ENERGY.get((section[b] or {}).get("kind", "verse"), 0.55)
        energy[b] = round(0.7 * base + 0.3 * total[b] / peak, 3)
    lead = song["parts"].get("lead") or song["parts"].get("melody") or []
    sounding = [(n[0], n[0] + n[1]) for n in lead]
    kicks = sorted(d[0] for d in song["drums"] if F.DRUM.get(d[2]) == "kick")
    return {"bars": bars, "section": section, "density": density, "energy": energy, "lead": sounding, "kicks": kicks}


def _lead_on(ctx, t0, t1) -> bool:
    return any(a < t1 and t0 < b for a, b in ctx["lead"])


def default_graph(song: dict) -> list[dict]:
    p = set(song["parts"])
    g = []
    for d in ("bass", "bass2"):
        if d in p:
            g.append(edge("duck", "kick", d, 0.35, release=0.12))
    for d in ("pad", "keys", "chords"):
        if d in p:
            g.append(edge("duck", "kick", d, 0.2, release=0.18))
    lead = "lead" if "lead" in p else "melody" if "melody" in p else None
    if lead:
        for d in ("counter", "arp"):
            if d in p:
                g.append(edge("answer", lead, d, 0.25))
        for d in ("lead_hi", "sidekick"):
            if d in p:
                g.append(edge("follow", lead, d, 0.4))
        for d in ("keys", "comp", "pad"):
            if d in p:
                g.append(edge("thin", lead, d, 0.15, busy=6))
    g.append(edge("accent", "energy", "hat", 0.12))
    for d in ("pad", "keys"):
        if d in p:
            g.append(edge("swell", "energy", d, 2.0))
    return g


# ---------------------------------------------------------------- the pass

def _clip(e):
    return max(0.0, min(LIMITS[e["kind"]], float(e["amount"])))


def apply(song: dict, graph: list[dict] | None = None) -> tuple[dict, dict]:
    """Run the graph over the song. Returns (new song, report). The input song is left alone."""
    import features as F
    graph = default_graph(song) if graph is None else graph
    out = copy.deepcopy(song)
    ctx = context(song)
    orig = {p: [n[3] for n in notes] for p, notes in out["parts"].items()}
    orig_drums = [d[3] for d in out["drums"]]
    vel = {p: list(v) for p, v in orig.items()}
    dvel = list(orig_drums)
    drop = {p: set() for p in out["parts"]}
    log, mixes = [], []

    for e in graph:
        amt, k, dst = _clip(e), e["kind"], e["dst"]
        rec = {"kind": k, "src": e["src"], "dst": dst, "amount": round(amt, 3), "asked": e["amount"], "changed": 0}
        if k in ("duck", "swell"):
            if dst in out["parts"] and amt > 0:
                rec["changed"] = len(out["parts"][dst])
                if k == "duck":
                    rec["mix"] = {"duck": {"depth": round(amt, 3), "release": float(e.get("release", 0.12))}}
                else:
                    pts = []
                    for s in out["sections"]:
                        en = ctx["energy"][s["start"]] if s["start"] <= ctx["bars"] else 0.5
                        pts.append([s["start"], round((en - 0.6) * 2 * amt, 2)])
                    pts = [[b, max(-amt, min(amt, v))] for b, v in pts]
                    pts.append([ctx["bars"] + 1, pts[-1][1]])
                    rec["mix"] = {"automation": {"type": "gain", "tracks": [dst], "points": pts}}
                mixes.append(rec)
        elif k == "accent":
            for i, d in enumerate(out["drums"]):
                if F.DRUM.get(d[2]) != dst:
                    continue
                b = min(ctx["bars"], max(1, int(d[0] // 4) + 1))
                dvel[i] *= 1 + (ctx["energy"][b] - 0.6) * 2 * amt
                rec["changed"] += 1
        elif dst in out["parts"] and amt > 0:
            notes = out["parts"][dst]
            if k == "answer":
                for i, n in enumerate(notes):
                    on = _lead_on(ctx, n[0], n[0] + max(0.125, n[1]))
                    vel[dst][i] *= (1 - amt) if on else (1 + amt / 2)
                    rec["changed"] += 1
            elif k == "follow":
                src = out["parts"].get(e["src"], [])
                starts = sorted((n[0], n[3]) for n in src)
                mean = sum(v for _, v in starts) / len(starts) if starts else 0
                j = 0
                for i, n in enumerate(notes):
                    while j + 1 < len(starts) and starts[j + 1][0] <= n[0]:
                        j += 1
                    if starts and abs(starts[j][0] - n[0]) <= 0.5 and mean:
                        vel[dst][i] *= 1 + (starts[j][1] / mean - 1) * amt
                        rec["changed"] += 1
            elif k == "thin":
                busy = int(e.get("busy", 6))
                lead = ctx["density"].get(e["src"], [0] * (ctx["bars"] + 1))
                per_bar = defaultdict(list)
                for i, n in enumerate(notes):
                    b = int(n[0] // 4) + 1
                    if 1 <= b <= ctx["bars"] and lead[b] >= busy and n[0] % 1:
                        per_bar[b].append(i)
                budget = int(MAX_DROP * len(notes)) - len(drop[dst])
                for b in sorted(per_bar):
                    cand = sorted(per_bar[b], key=lambda i: (vel[dst][i], i))
                    for i in cand[:int(amt * len([n for n in notes if int(n[0] // 4) + 1 == b]))]:
                        if budget <= 0:
                            break
                        drop[dst].add(i)
                        budget -= 1
                        rec["changed"] += 1
        log.append(rec)

    def bound(v, v0):
        return round(max(0.05, min(1.0, v0 + max(-MAX_VEL, min(MAX_VEL, v - v0)))), 4)

    for p, notes in out["parts"].items():
        out["parts"][p] = [(n[0], n[1], n[2], bound(vel[p][i], orig[p][i])) + tuple(n[4:])
                           for i, n in enumerate(notes) if i not in drop[p]]
    out["drums"] = [(d[0], d[1], d[2], bound(dvel[i], orig_drums[i])) + tuple(d[4:]) for i, d in enumerate(out["drums"])]
    report = {"edges": log, "mix": mixes, "dropped": {p: len(s) for p, s in drop.items() if s},
              "energy": ctx["energy"][1:]}
    out["network"] = {"edges": len(log), "dropped": report["dropped"]}
    return out, report


def mix(report: dict) -> dict:
    """The mix side of the network: per-track settings and automation to merge into instruments.toml."""
    tracks, auto = {}, []
    for r in report.get("mix", []):
        m = r["mix"]
        if "duck" in m:
            tracks.setdefault(r["dst"], {})["duck"] = m["duck"]
        if "automation" in m:
            auto.append(m["automation"])
    return {"tracks": tracks, "automation": auto}


def merge_mix(imap: dict, m: dict) -> dict:
    """instrument_map(...) with the network's mix merged in. A track's own duck is kept if it is deeper."""
    out = copy.deepcopy(imap)
    for name, cfg in m.get("tracks", {}).items():
        tr = out.get("tracks", {}).get(name)
        if tr is None:
            continue
        if "duck" in cfg and cfg["duck"]["depth"] > tr.get("duck", {}).get("depth", 0):
            tr["duck"] = cfg["duck"]
    have = {a2["tracks"][0] for a2 in out.get("automation", []) if a2.get("type") == "gain" and a2.get("tracks")}
    out.setdefault("automation", [])
    for a in m.get("automation", []):
        if a["tracks"][0] in out.get("tracks", {}) and a["tracks"][0] not in have:
            out["automation"].append(a)
    if not out["automation"]:
        out.pop("automation")
    return out


def text(report: dict) -> str:
    lines = []
    for r in report["edges"]:
        lim = " (clipped)" if r["amount"] < r["asked"] else ""
        lines.append(f"{r['kind']:7} {r['src']:>8} -> {r['dst']:<9} {r['amount']:.2f}{lim}  {r['changed']} touched")
    if report["dropped"]:
        lines.append("dropped: " + ", ".join(f"{p} {n}" for p, n in report["dropped"].items()))
    return "\n".join(lines)
