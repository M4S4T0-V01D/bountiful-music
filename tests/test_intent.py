#!/usr/bin/env python3
"""The brief reader (intent.py): plain words become bounded, explained, reversible controls. No model, no network.
Run: python tests/test_intent.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bountiful"))
import electronium as EL  # noqa: E402
import electronium_song as ES  # noqa: E402
import intent as IN  # noqa: E402
import operator_ as OP  # noqa: E402

BRIEF = ("make the break more restless, keep the Rhodes intimate, let the last two minutes open into something huge; "
         "a bit darker in every chorus")
_PL = {}


def plan():
    if not _PL:
        _PL["p"] = ES.plan("1969")
    return _PL["p"]


def test_parse_reads_qualities_targets_and_scopes():
    pl = plan()
    got = IN.parse(BRIEF, pl["sections"], pl["bpm"])
    its = {it["quality"]: it for it in got["intents"]}
    assert {"restless", "intimate", "huge", "dark"} <= set(its), list(its)
    assert its["intimate"]["keep"] and "chords" in its["intimate"]["targets"]
    assert its["huge"]["ramp"], "open into ... ramps"
    assert its["dark"]["amount"] < 1, "a bit"
    total = sum(s["bars"] for s in pl["sections"])
    a, b = its["huge"]["spans"][0]
    assert b == total and a > 1, (a, b, total)
    assert IN.parse("make the break more restless", pl["sections"], pl["bpm"]) == \
        IN.parse("make the break more restless", pl["sections"], pl["bpm"]), "deterministic"
    neg = IN.parse("bars 9-16 less busy", pl["sections"], pl["bpm"])["intents"][0]
    assert neg["sign"] < 0 and neg["spans"] == [(9, 16)], neg


def test_unread_words_are_reported_not_guessed():
    pl = plan()
    got = IN.parse("zorp the flibbet", pl["sections"], pl["bpm"])
    assert not got["intents"] and got["unread"]


def test_deltas_are_bounded():
    pl = plan()
    for it in IN.parse("make everything extremely massively incredibly huge and dense and restless",
                       pl["sections"], pl["bpm"])["intents"]:
        d = IN.deltas(it)
        for k, v in d["machine"].items():
            assert abs(v) <= IN.LIMITS[k] + 1e-9, (k, v)
        for k, v in d["production"].items():
            assert abs(v) <= IN.LIMITS[k] + 1e-9, (k, v)


def test_operator_moves_are_clean_explained_and_switchable():
    pl = plan()
    p = EL.patch(pl["patch"])
    quiet = lambda *_: None  # noqa: E731
    base = OP.operate(pl["sections"], p, log=quiet)
    op = OP.operate(pl["sections"], p, BRIEF, log=quiet, bpm=pl["bpm"])
    assert base["by"] == "rules" and op["by"] == "rules + brief"
    assert not op["problems"], op["problems"]
    assert len(op["moves"]) > len(base["moves"])
    briefed = [m for m in op["moves"] if str(m.get("why", "")).startswith("brief:")]
    assert briefed, "every brief move says which words made it"
    for m in op["moves"]:
        for k, v in m.get("set", {}).items():
            if k in IN.RANGES:
                lo, hi = IN.RANGES[k]
                assert lo - 1e-9 <= v <= hi + 1e-9, (k, v)
    assert json.loads(json.dumps(op["intents"])) is not None
    # untick everything: back to the rules exactly
    off = [dict(it, on=False) for it in op["intents"]]
    again = OP.operate(pl["sections"], p, BRIEF, log=quiet, bpm=pl["bpm"], intents=off)
    assert again["moves"] == base["moves"] and again["drums"] == [], "unticked intents change nothing"


def test_brief_changes_the_performance_and_drums():
    pl = plan()
    p = EL.patch(pl["patch"])
    quiet = lambda *_: None  # noqa: E731
    a = ES.perform(pl, OP.operate(pl["sections"], p, log=quiet))
    op = OP.operate(pl["sections"], p, "make the break more restless", log=quiet, bpm=pl["bpm"])
    b = ES.perform(pl, op)
    assert op["drums"] and len(b["drums"]) > len(a["drums"])
    edited = IN.apply_drums(pl["sections"], op["drums"])
    assert edited is not pl["sections"] and pl["sections"] == ES.plan("1969")["sections"], "the plan is not mutated"


def test_production_notes_for_the_studio():
    pl = plan()
    its = IN.parse("the bass much punchier, the end wider", pl["sections"], pl["bpm"])["intents"]
    prod = IN.production(its, ["bass", "keys", "lead"])
    assert any(r["part"] == "bass" for r in prod) and any(r["part"] == "*" for r in prod), prod


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok    {name}")
            except Exception as ex:
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"FAIL  {name}: {ex}")
    sys.exit(1 if fails else 0)
