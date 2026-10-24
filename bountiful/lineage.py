"""Lineage: every song's DNA, and its family tree.

A song's DNA is where it came from and what was done to it, as plain data:

    {"v": 1,
     "origin": {"kind": "electronium", "bounty": "1969", "key": null, "bpm": null, "length": "normal",
                "reharm": 0.25, "brief": "", "intents": null},
     "changes": [{"op": "reharmonize", "args": {"section": 1, "share": 0.35}, "seed": 812, "why": "harmony"}, ...],
     "parent": "a3f09c12e1" | null,
     "label": "..."}

`grow(dna)` rebuilds the song from it, note for note: the origin is the Electronium's deterministic plan and
performance, each change is an evolve.py op seeded by its own seed. So any candidate the discovery machine
ever showed you can be recovered from its id, exported, rendered, or bred further, and two songs can be
compared change by change. Ids are the first ten hex digits of the DNA's SHA-1 (parent and label excluded).

The family tree lives in <data>/lineage.jsonl, one line per saved song: {"id", "dna", "scores", "total",
"time", "note", "rating"}. Nothing is ever rewritten; a later line for the same id adds to the earlier one.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from functools import lru_cache
from pathlib import Path

from paths import DATA

STORE = DATA / "lineage.jsonl"
ORIGIN_KEYS = ("kind", "bounty", "key", "bpm", "length", "reharm", "brief", "intents")


def origin(bounty, key=None, bpm=None, length="normal", reharm=0.25, brief="", intents=None) -> dict:
    return {"v": 1, "origin": {"kind": "electronium", "bounty": str(bounty), "key": key, "bpm": bpm, "length": length,
                               "reharm": reharm, "brief": brief or "", "intents": intents},
            "changes": [], "parent": None, "label": ""}


def canon(dna: dict) -> str:
    core = {"v": dna.get("v", 1), "origin": {k: dna["origin"].get(k) for k in ORIGIN_KEYS},
            "changes": [{k: c[k] for k in ("op", "args", "seed") if k in c} for c in dna.get("changes", [])]}
    return json.dumps(core, sort_keys=True, separators=(",", ":"))


def dna_id(dna: dict) -> str:
    return hashlib.sha1(canon(dna).encode()).hexdigest()[:10]


def child(dna: dict, changes, label: str = "") -> dict:
    changes = [changes] if isinstance(changes, dict) else list(changes)
    return {"v": 1, "origin": copy.deepcopy(dna["origin"]), "changes": copy.deepcopy(dna.get("changes", [])) + copy.deepcopy(changes),
            "parent": dna_id(dna), "label": label}


@lru_cache(maxsize=32)
def _base(origin_json: str):
    import electronium as EL
    import electronium_song as ES
    import features as F
    import operator_ as OP
    o = json.loads(origin_json)
    if o.get("kind", "electronium") != "electronium":
        raise ValueError(f"unknown origin {o.get('kind')!r}")
    pl = ES.plan(o["bounty"], o.get("key"), o.get("bpm"), o.get("length") or "normal", o.get("reharm", 0.25))
    op = OP.operate(pl["sections"], EL.patch(pl["patch"]), o.get("brief", ""), log=lambda *_: None, bpm=pl["bpm"],
                    intents=o.get("intents"))
    perf = ES.perform(pl, op)
    song = F.song_from(pl, perf)
    return pl, perf, song


def base(dna: dict):
    """(plan, performance, song) of the origin, before any change. Cached; callers get copies of the song."""
    pl, perf, song = _base(json.dumps({k: dna["origin"].get(k) for k in ORIGIN_KEYS}, sort_keys=True))
    return pl, perf, copy.deepcopy(song)


def grow(dna: dict) -> dict:
    import evolve as EV
    song = base(dna)[2]
    song = EV.apply_all(song, dna.get("changes", []))
    song["dna"] = {"id": dna_id(dna), "parent": dna.get("parent"), "label": dna.get("label", "")}
    return song


def change_text(c: dict) -> str:
    """A change in words: why it was made when that is specific, and what the op reported doing."""
    why, note = c.get("why") or "", c.get("note") or ""
    generic = why.endswith(": " + c["op"]) or not why
    if generic:
        return note or c["op"]
    return why + (f" ({note})" if note and note not in why else "")


def describe(dna: dict, song: dict | None = None) -> str:
    """One line: the origin and every change. Pass the grown song to include what each op reported."""
    o = dna["origin"]
    head = f"Bounty {o['bounty']}" + (f", {o['key']}" if o.get("key") else "") + (f", {o['bpm']:g} bpm" if o.get("bpm") else "") \
        + (f", brief “{o['brief']}”" if o.get("brief") else "")
    done = (song or {}).get("changes") or []
    ch = [change_text(dict(c, note=c.get("note") or (done[k].get("note") if k < len(done) and done[k]["op"] == c["op"] else "")))
          for k, c in enumerate(dna.get("changes", []))]
    return head + (": " + "; ".join(ch) if ch else "")


def diff(a: dict, b: dict) -> dict:
    """What two songs share and where they part: the common origin (or not) and changes."""
    same_origin = canon({"origin": a["origin"], "changes": []}) == canon({"origin": b["origin"], "changes": []})
    ca, cb = a.get("changes", []), b.get("changes", [])
    k = 0
    if same_origin:
        while k < min(len(ca), len(cb)) and canon({"origin": {}, "changes": [ca[k]]}) == canon({"origin": {}, "changes": [cb[k]]}):
            k += 1
    return {"same_origin": same_origin, "shared": ca[:k] if same_origin else [],
            "only_a": ca[k:] if same_origin else ca, "only_b": cb[k:] if same_origin else cb,
            "origin_a": a["origin"], "origin_b": b["origin"]}


# ---------------------------------------------------------------- the family tree on disk

def save(dna: dict, scores: dict | None = None, total: float | None = None, note: str = "", rating: float | None = None,
         store: Path | None = None) -> str:
    store = store or STORE
    store.parent.mkdir(parents=True, exist_ok=True)
    i = dna_id(dna)
    rec = {"id": i, "dna": dna, "time": round(time.time(), 1)}
    if scores is not None:
        rec["scores"] = scores
    if total is not None:
        rec["total"] = total
    if note:
        rec["note"] = note
    if rating is not None:
        rec["rating"] = rating
    with store.open("a") as f:
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")
    return i


def load(store: Path | None = None) -> dict[str, dict]:
    """{id: record}, later lines for an id merged over earlier ones. Unreadable lines are skipped."""
    store = store or STORE
    out = {}
    if not store.exists():
        return out
    for line in store.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and "id" in r:
            out[r["id"]] = {**out.get(r["id"], {}), **r}
    return out


def get(i: str, store: Path | None = None) -> dict | None:
    recs = load(store)
    if i in recs:
        return recs[i]
    hits = [r for k, r in recs.items() if k.startswith(i)]
    return hits[0] if len(hits) == 1 else None


def ancestry(i: str, store: Path | None = None) -> list[dict]:
    """The record and its parents back to the first saved ancestor, oldest first."""
    recs = load(store)
    out, seen = [], set()
    while i and i in recs and i not in seen:
        seen.add(i)
        out.append(recs[i])
        i = recs[i]["dna"].get("parent")
    return out[::-1]


def descendants(i: str, store: Path | None = None) -> list[dict]:
    recs = load(store)
    kids = {}
    for r in recs.values():
        kids.setdefault(r["dna"].get("parent"), []).append(r)
    out, todo = [], [i]
    while todo:
        for r in kids.get(todo.pop(), []):
            out.append(r)
            todo.append(r["id"])
    return out


def export(dna: dict, out: Path | None = None, song: dict | None = None, network: bool = True) -> Path:
    """Write the song as a track folder (MIDI, instruments.toml, dna.json, notes.txt) the renderer plays.
    With `network`, the instrument network (network.py) shapes dynamics and adds its ducking and swells to the mix."""
    import sys

    import build as B
    import electronium as EL
    import electronium_song as ES
    import network as N
    pl, perf, _ = base(dna)
    song = song or grow(dna)
    net = None
    if network:
        song, net = N.apply(song)
    i = dna_id(dna)
    title = (dna.get("label") or pl["title"]) + (f" ({i[:6]})" if dna.get("changes") else "")
    name = B.slug(title)
    out = out or DATA / "tracks" / name
    out.mkdir(parents=True, exist_ok=True)
    B.write_midi(out / f"{name}.mid", title, song["bpm"], {**{k: [] for k in B.PART_ORDER}, **song["parts"]}, song["drums"])
    sys.path.insert(0, str(B.ENGINE / "studio"))
    from midi_studio import to_toml
    g = ES.genre_for(pl, perf["patch"])
    imap = B.instrument_map(g, title, name, EL.bounty_int(dna["origin"]["bounty"]) % 100000)
    if net:
        imap = N.merge_mix(imap, N.mix(net))
    (out / "instruments.toml").write_text(to_toml(imap))
    (out / "dna.json").write_text(json.dumps(dict(dna, id=i), indent=1))
    (out / "notes.txt").write_text(f"{title}\nDNA {i}: {describe(dna)}\n"
                                   + (f"\nInstrument network:\n{N.text(net)}\n" if net else ""))
    (out / "source.json").write_text(json.dumps({"kind": "lineage", "id": i, "bounty": dna["origin"]["bounty"],
                                                 "title": title, "bpm": song["bpm"]}, indent=1))
    return out
