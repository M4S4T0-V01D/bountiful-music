#!/usr/bin/env python3
"""The ecosystem's judges: song features, the musical laws, the six evaluators and Pareto ranking.
Each law must pass real songs and fail a song broken in exactly the way it guards against.
Run: python tests/test_ecosystem.py"""
from __future__ import annotations

import copy
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bountiful"))
import electronium as EL  # noqa: E402
import electronium_song as ES  # noqa: E402
import evaluators as V  # noqa: E402
import features as F  # noqa: E402
import laws as L  # noqa: E402
import operator_ as OP  # noqa: E402

_SONGS = {}


def song(bounty="1969"):
    if bounty not in _SONGS:
        pl = ES.plan(bounty)
        op = OP.operate(pl["sections"], EL.patch(pl["patch"]), "", log=lambda *_: None, bpm=pl["bpm"])
        _SONGS[bounty] = F.song_from(pl, ES.perform(pl, op))
    return copy.deepcopy(_SONGS[bounty])


def law(s, name):
    return L.judge(s, only=[name])[0]


def test_features_grid_and_sections():
    s = song()
    rows = F.grid(s)
    assert len(rows) == s["bars"] == 80
    assert all(0 <= r["energy"] <= 1 for r in rows)
    secs = F.sections(s, rows)
    assert [x["name"] for x in secs][0] == "Intro" and secs[-1]["kind"] == "outro"
    f = F.features(s, rows)
    assert 0.5 < f["in_key"] <= 1 and f["lead_notes"] > 50
    m = lambda p, ivs, steps, rh=(2, 2, 2): {"pitch": p, "ivs": ivs, "steps": steps, "rhythm": rh}  # noqa: E731
    a = m(60, (2, 2, 1), (1, 1, 1))
    assert F.transform(a, m(60, (2, 2, 1), (1, 1, 1))) == "exact"
    assert F.transform(a, m(65, (2, 2, 1), (1, 1, 1))) == "transposed"
    assert F.transform(a, m(62, (2, 1, 2), (1, 1, 1))) == "diatonic"
    assert F.transform(a, m(60, (2, 2, 1), (1, 1, 1), (4, 4, 4))) == "augmented"
    assert F.transform(a, m(60, (-2, -2, -1), (-1, -1, -1))) == "inverted"
    assert F.transform(a, m(60, (5, 0, -3), (2, 0, -2))) is None
    assert len(F.motifs(s)) > 20


def test_real_songs_keep_every_law():
    for b in ("1969", "77", "4242"):
        res = L.judge(song(b))
        bad = [r["law"] + " " + str(r["score"]) for r in res if not r["passed"]]
        assert not bad, (b, bad)
        assert all(r["evidence"] for r in res), "every verdict says why"


def test_scrambled_drums_lose_the_groove():
    s = song()
    rnd = random.Random(3)
    s["drums"] = [(int(b // 4) * 4 + rnd.randrange(16) / 4, d, g, v, o) for b, d, g, v, o in s["drums"]]
    assert not law(s, "groove_identity")["passed"]


def test_random_lead_has_no_returning_motifs():
    s = song()
    rnd = random.Random(5)
    s["parts"]["lead"] = [(b, d, rnd.randrange(55, 84), v, o) for b, d, p, v, o in s["parts"]["lead"]]
    for k in ("lead_hi", "sidekick"):
        s["parts"].pop(k, None)
    assert not law(s, "motifs_return")["passed"]


def test_hollow_last_chorus_fails():
    s = song()
    last = next(x for x in reversed(s["sections"]) if x["kind"] == "chorus")
    a, b = (last["start"] - 1) * 4, (last["start"] - 1 + last["bars"]) * 4
    s["parts"] = {k: [n for n in v if not (a <= n[0] < b) or k.startswith("bass")] for k, v in s["parts"].items()}
    assert not law(s, "final_chorus_biggest")["passed"]


def test_a_flat_loop_brings_nothing_new():
    s = song()
    loop = 8 * 4
    s["parts"] = {k: [(b + r * loop, d, p, v, o) for r in range(10) for b, d, p, v, o in ns if b < loop]
                  for k, ns in s["parts"].items()}
    s["drums"] = [(b + r * loop, d, g, v, o) for r in range(10) for b, d, g, v, o in s["drums"] if b < loop]
    s["sections"] = [dict(x, kind="verse", loop="V", name="Loop") for x in s["sections"]]
    s["chords"] = [c for c in s["chords"] if c[0] < loop]
    s["chords"] = [(c[0] + r * loop,) + tuple(c[1:]) for r in range(10) for c in s["chords"]]
    res = law(s, "new_idea_every_16")
    assert not res["passed"], res["evidence"]


def test_evaluators_are_traceable_and_deterministic():
    s = song()
    a, b = V.evaluate(s), V.evaluate(song())
    assert a == b
    assert set(a["scores"]) == set(V.EVALUATORS)
    for e in a["evaluators"]:
        assert 0 <= e["score"] <= 1 and e["trace"], e["name"]
        for t in e["trace"]:
            assert t["what"] and (t["score"] is None or 0 <= t["score"] <= 1)
    assert any(t["what"].startswith("law:") for e in a["evaluators"] for t in e["trace"])
    assert "taste" in V.text(a)


def test_broken_songs_score_lower():
    good = V.evaluate(song())
    s = song()
    rnd = random.Random(3)
    s["drums"] = [(int(b // 4) * 4 + rnd.randrange(16) / 4, d, g, v, o) for b, d, g, v, o in s["drums"]]
    s["parts"]["lead"] = [(b, d, rnd.randrange(40, 96), v, o) for b, d, p, v, o in s["parts"]["lead"]]
    bad = V.evaluate(s)
    assert bad["scores"]["rhythm"] < good["scores"]["rhythm"]
    assert bad["scores"]["composition"] < good["scores"]["composition"]
    assert bad["total"] < good["total"]


def test_audio_diagnostics_enter_the_trace():
    res = V.evaluate(song(), audio={"sound": {"kick/bass separation": 0.4}, "production": {"lf balance": 0.9}})
    tr = {t["what"]: t for e in res["evaluators"] for t in e["trace"]}
    assert tr["render: kick/bass separation"]["score"] == 0.4 and tr["render: lf balance"]["score"] == 0.9


def test_pareto_ranking():
    rnd = random.Random(1)
    c = [{"id": "c%d" % i, "scores": {k: rnd.random() for k in V.EVALUATORS}} for i in range(200)]
    c.append({"id": "best", "scores": {k: 1.0 for k in V.EVALUATORS}})
    c.append({"id": "worst", "scores": {k: 0.0 for k in V.EVALUATORS}})
    out = V.rank(c)
    assert out[0]["id"] == "best" and out[-1]["id"] == "worst"
    assert [x["front"] for x in out] == sorted(x["front"] for x in out)
    for x in out:
        if x["front"] > 0:
            assert "is at least as good on every judge" in x["why"]
    by = {x["id"]: x for x in out}
    assert by["best"]["front"] == 0 and all(x["front"] > 0 for x in out if x["id"] != "best"), \
        "a candidate best at everything dominates all"
    # a trade-off: two candidates each best at something share the front
    two = V.rank([{"id": "a", "scores": {"composition": 1, "rhythm": 0}}, {"id": "b", "scores": {"composition": 0, "rhythm": 1}}])
    assert {x["front"] for x in two} == {0}


def test_changes_are_deterministic_and_leave_the_parent_alone():
    import evolve as EV
    s = song()
    before = copy.deepcopy(s)
    a = EV.breed(s, 12, seed=9, depth=2)
    b = EV.breed(song(), 12, seed=9, depth=2)
    assert s == before, "breeding must not touch the parent"
    assert [c for c, _ in a] == [c for c, _ in b]
    assert all(x[1]["parts"] == y[1]["parts"] and x[1]["drums"] == y[1]["drums"] for x, y in zip(a, b))
    assert len(a) == 12 and all(k["parts"] != s["parts"] or k["drums"] != s["drums"] for _, k in a)
    try:
        EV.apply(s, {"op": "no_such_op", "args": {}, "seed": 1})
        raise AssertionError("unknown op accepted")
    except ValueError:
        pass


def test_every_op_keeps_the_laws_it_must():
    import evolve as EV
    s = song()
    ch = next(x for x in s["sections"] if x["kind"] == "chorus")
    span = [ch["start"], ch["start"] + ch["bars"] - 1]
    cases = [{"op": "vary_phrase", "args": {"bars": [span[0], span[0] + 1], "how": "diatonic", "steps": 2}},
             {"op": "ornament", "args": {"bars": span, "amount": 0.7}},
             {"op": "motif_callback", "args": {"to_bar": span[0] + 4, "which": 0, "how": "invert"}},
             {"op": "groove_mutate", "args": {"bars": span, "amount": 0.8}},
             {"op": "steady_groove", "args": {"bars": [9, 24], "amount": 0.8}},
             {"op": "bass_push", "args": {"bars": span, "amount": 0.5}},
             {"op": "fill", "args": {"bar": ch["start"] - 1}},
             {"op": "reharmonize", "args": {"section": s["sections"].index(ch), "share": 0.5}},
             {"op": "lift_last_chorus", "args": {"amount": 1.0}},
             {"op": "breathe", "args": {"bars": [ch["start"] - 1, ch["start"] - 1], "drums": "thin"}}]
    assert {c["op"] for c in cases} == set(EV.OPS)
    for c in cases:
        k = EV.apply(s, dict(c, seed=3))
        assert k is not s, c["op"] + " did nothing"
        assert k["changes"][-1]["note"], c["op"]
        bad = [r["law"] for r in L.judge(k) if not r["passed"]]
        assert not bad, (c["op"], bad)
        assert all(len(v) <= EV.LIMIT_NOTES for v in k["parts"].values())


def test_groove_mutation_keeps_the_groove_and_fill_uses_toms():
    import evolve as EV
    s = song()
    k = EV.apply(s, {"op": "groove_mutate", "args": {"bars": [1, s["bars"]], "amount": 1.0}, "seed": 5})
    assert law(k, "groove_identity")["passed"]
    kick = lambda x: sorted(n[0] for n in x["drums"] if F.DRUM.get(n[2]) == "kick" and n[3] > 0.4)  # noqa: E731
    assert set(kick(s)) <= set(kick(k)), "strong kicks are anchors"
    f = EV.apply(s, {"op": "fill", "args": {"bar": 8, "length": 2}, "seed": 1})
    assert any(F.DRUM.get(n[2]) == "tom" and 28 <= n[0] < 32 for n in f["drums"])


def test_reharmonize_moves_chords_and_stays_in_key():
    import evolve as EV
    s = song()
    i = next(i for i, x in enumerate(s["sections"]) if x["kind"] == "chorus")
    k = EV.apply(s, {"op": "reharmonize", "args": {"section": i, "share": 0.5}, "seed": 2})
    assert k["chords"] != s["chords"]
    assert "→" in k["changes"][-1]["note"]
    sc = set(EV.scale(k))
    out = lambda x: {(part, n[0]) for part, ns in x["parts"].items() for n in ns if n[2] % 12 not in sc}  # noqa: E731
    assert out(k) <= out(s), "no new out-of-key notes (the bass's own chromatic approaches may stay)"
    assert V.evaluate(k)["scores"]["composition"] > 0.7


def test_dna_recovers_a_song_note_for_note():
    import json
    import tempfile

    import evolve as EV
    import lineage as G
    d = G.origin("1969")
    assert G.grow(d)["parts"] == song()["parts"]
    ch, kid = EV.breed(G.grow(d), 4, seed=11, depth=3)[2]
    c = G.child(d, ch, label="test")
    c2 = json.loads(json.dumps(c))
    assert G.dna_id(c2) == G.dna_id(c) and c["parent"] == G.dna_id(d)
    g = G.grow(c2)
    assert g["parts"] == kid["parts"] and g["drums"] == kid["drums"] and g["chords"] == kid["chords"]
    assert G.dna_id(G.child(d, ch, label="other name")) == G.dna_id(c), "labels do not change identity"
    st = Path(tempfile.mkdtemp()) / "lineage.jsonl"
    G.save(d, store=st)
    G.save(c, store=st, total=0.8)
    gc = G.child(c, ch[:1])
    G.save(gc, store=st)
    G.save(c, store=st, rating=4)
    with st.open("a") as f:
        f.write("not json\n")
    recs = G.load(st)
    assert recs[G.dna_id(c)]["total"] == 0.8 and recs[G.dna_id(c)]["rating"] == 4
    assert [r["id"] for r in G.ancestry(G.dna_id(gc), st)] == [G.dna_id(d), G.dna_id(c), G.dna_id(gc)]
    assert len(G.descendants(G.dna_id(d), st)) == 2
    df = G.diff(c, gc)
    assert df["same_origin"] and len(df["shared"]) == 3 and len(df["only_b"]) == 1 and not df["only_a"]
    assert not G.diff(d, G.origin("77"))["same_origin"]


def test_the_doctor_answers_the_judges():
    import discover as D
    import evolve as EV
    s = song()
    res = V.evaluate(s)
    fixes = D.doctor(s, res, seed=1)
    assert fixes and all(c["why"] and c["op"] in EV.OPS for c in fixes)
    k = EV.apply_all(s, fixes)
    after = V.evaluate(k)
    assert all(r["passed"] for r in after["laws"])
    assert after["scores"]["rhythm"] > res["scores"]["rhythm"] and after["total"] > res["total"]
    assert D.weakest(res) and all(w["score"] < 0.95 for w in D.weakest(res))


def test_discovery_rejects_ranks_and_can_be_recovered():
    import tempfile

    import discover as D
    import lineage as G
    st = Path(tempfile.mkdtemp()) / "lineage.jsonl"
    run = D.discover(40, seed=3, bounties=["1969", "77"], keep=4, per_origin=2, save=True, store=st, write_last=False,
                     workers=1)
    assert run["considered"] == 40 and run["survivors"] + sum(run["rejected"].values()) <= 40
    shown = run["presented"]
    assert 1 <= len(shown) <= 4 and [c["rank"] for c in shown] == list(range(1, len(shown) + 1))
    assert max(sum(c["bounty"] == b for c in shown) for b in ("1969", "77")) <= 2, "the shortlist is varied"
    for c in shown:
        assert c["why"] and c["describe"].startswith("Bounty ")
        r = V.evaluate(G.grow(c["dna"]))
        assert r["scores"] == c["scores"], "a presented song grows back exactly as judged"
    assert set(G.load(st)) == {c["id"] for c in shown}
    again = D.discover(40, seed=3, bounties=["1969", "77"], keep=4, per_origin=2, write_last=False, workers=1)
    assert [c["id"] for c in again["presented"]] == [c["id"] for c in shown]


def test_the_network_listens_within_its_limits():
    import network as N
    s = song()
    before = copy.deepcopy(s)
    t, rep = N.apply(s)
    assert s == before, "the network leaves its input alone"
    assert N.apply(s) == (t, rep), "deterministic"
    kinds = {r["kind"] for r in rep["edges"]}
    assert {"duck", "answer", "follow", "accent"} <= kinds
    for p, notes in s["parts"].items():
        kept = t["parts"][p]
        assert len(notes) - len(kept) <= int(N.MAX_DROP * len(notes))
        assert {(n[0], n[1], n[2]) for n in kept} <= {(n[0], n[1], n[2]) for n in notes}, "no pitch or timing moves"
        old = {(n[0], n[2]): n[3] for n in notes}
        assert all(abs(n[3] - old[(n[0], n[2])]) <= N.MAX_VEL + 1e-9 for n in kept)
    assert [d[:3] for d in t["drums"]] == [d[:3] for d in s["drums"]]
    assert all(r["passed"] for r in L.judge(t)) == all(r["passed"] for r in L.judge(s))
    # under the lead the answerer is softer than where the lead rests
    ctx = N.context(s)
    on = [n[3] for n in t["parts"]["arp"] if N._lead_on(ctx, n[0], n[0] + max(0.125, n[1]))]
    off = [n[3] for n in t["parts"]["arp"] if not N._lead_on(ctx, n[0], n[0] + max(0.125, n[1]))]
    o_on = [n[3] for n in s["parts"]["arp"] if N._lead_on(ctx, n[0], n[0] + max(0.125, n[1]))]
    o_off = [n[3] for n in s["parts"]["arp"] if not N._lead_on(ctx, n[0], n[0] + max(0.125, n[1]))]
    assert sum(off) / len(off) - sum(on) / len(on) > sum(o_off) / len(o_off) - sum(o_on) / len(o_on)
    # an amount past the limit is clipped, and the mix side stays inside its bounds
    t2, rep2 = N.apply(s, [N.edge("duck", "kick", "bass", 0.9), N.edge("swell", "energy", "keys", 12)])
    m = N.mix(rep2)
    assert m["tracks"]["bass"]["duck"]["depth"] == N.LIMITS["duck"]
    assert all(abs(v) <= N.LIMITS["swell"] for _, v in m["automation"][0]["points"])
    imap = {"tracks": {"bass": {"duck": {"depth": 0.1}}, "keys": {}}}
    merged = N.merge_mix(imap, m)
    assert merged["tracks"]["bass"]["duck"]["depth"] == 0.5 and merged["automation"][0]["tracks"] == ["keys"]
    assert imap == {"tracks": {"bass": {"duck": {"depth": 0.1}}, "keys": {}}}


def test_a_dna_exports_as_a_track_folder_with_the_network_mix():
    import tempfile
    import tomllib

    import lineage as G
    out = G.export(G.origin(1969), Path(tempfile.mkdtemp()) / "t")
    names = {p.name for p in out.iterdir()}
    assert {"instruments.toml", "dna.json", "notes.txt", "source.json"} <= names and any(n.endswith(".mid") for n in names)
    cfg = tomllib.loads((out / "instruments.toml").read_text())
    assert cfg["tracks"]["bass"]["duck"]["depth"] >= 0.35
    assert "Instrument network" in (out / "notes.txt").read_text()


# ---------------------------------------------------------------- the virtual record producer (studio.py)

def _kit(duck=0.0, bass_amp=0.5, secs=4.0, bpm=120):
    """Synthetic passage: kick on every beat, a sustained bass under it (ducked by `duck`), a wide 1 kHz pad."""
    import numpy as np

    import studio as S
    t = np.arange(int(secs * S.SR)) / S.SR
    beat = 60 / bpm
    ph = t % beat
    kick = np.sin(2 * np.pi * 55 * ph) * np.exp(-ph / 0.06)
    env = 1 - duck * 2 * np.exp(-ph / 0.1)
    bass = bass_amp * np.sin(2 * np.pi * 50 * t) * np.clip(env, 0, 1)
    pad = 0.6 * np.stack([np.sin(2 * np.pi * 1000 * t), np.sin(2 * np.pi * 1000 * t + 0.9)], 1)
    st = {"kick": np.stack([kick, kick], 1), "bass": np.stack([bass, bass], 1), "pad": pad}
    return {"bars": [1, 2], "kind": "verse", "mix": sum(st.values()), "stems": st, "bpm": bpm}


def _cfg():
    return {"tracks": {"bass": {"gain_db": 0.0}, "pad": {}, "drums": {"channel": 9, "stems": {"kick": {"gain_db": 0.0}}}}}


def test_the_producer_hears_the_bass_on_the_kick_and_ducking_clears_it():
    import studio as S
    raw = S.analyse([_kit(0.0)], 120)
    ducked = S.analyse([_kit(0.4)], 120)
    assert raw["values"]["kick/bass masking"] > 0.5 > ducked["values"]["kick/bass masking"], (raw["values"], ducked["values"])
    assert ducked["scores"]["kick/bass masking"] > raw["scores"]["kick/bass masking"]
    assert S.onsets(_kit()["stems"]["kick"]) and len(S.onsets(_kit()["stems"]["kick"])) == 8
    assert 0.9 < raw["values"]["low end mono"] <= 1.0 and raw["values"]["stereo image"] > 0.08
    ev = S.for_evaluators(raw)
    assert "kick/bass masking" in ev["sound"] and "dynamics" not in ev["production"]


def test_the_producer_changes_one_thing_at_a_time_within_its_limits():
    import studio as S
    a = S.analyse([_kit(0.0)], 120)
    cfg = _cfg()
    ch = S.prescribe(a, cfg, cfg)
    assert 1 <= len(ch) <= S.MAX_CHANGES and {c["metric"] for c in ch} == {"kick/bass masking"}
    assert ch[0]["path"] == ["tracks", "bass", "duck"] and ch[0]["to"]["depth"] == S.STEP["duck"]
    # the sidechain never goes past its limit, and then the kick is raised instead, never past its own
    cfg2 = S.apply_changes(cfg, [dict(ch[0], to={"depth": S.LIMITS["duck"], "release": 0.12})])
    ch2 = S.prescribe(a, cfg2, cfg)
    assert ch2 and ch2[0]["path"] == ["tracks", "drums", "stems", "kick", "gain_db"] and ch2[0]["to"] == 1.0
    cfg3 = S.apply_changes(cfg2, [dict(ch2[0], to=S.LIMITS["gain_db"])])
    assert S.prescribe(a, cfg3, cfg) == []
    # refused paths are not tried again
    assert S.prescribe(a, cfg, cfg, tried={("tracks", "bass", "duck")})[0]["path"][-1] == "gain_db"
    # undo puts every setting back
    assert S.apply_changes(S.apply_changes(cfg, ch), ch, undo=True) == cfg
    # an EQ dip deepens an existing one near the frequency, down to the limit, then stops
    c = {"tracks": {"pad": {"eq": [["peak", 1000.0, -4.0, 1.0]]}}}
    d = S._dip(c, "pad", 1100, "lead masking", "")
    assert d["to"] == [["peak", 1000.0, -6.0, 1.0]]
    assert S._dip(S.apply_changes(c, [d]), "pad", 1100, "lead masking", "") is None


def test_the_producer_keeps_only_what_measures_better():
    import studio as S
    base = {"scores": {"a": 0.5, "b": 0.9, "dynamics": 0.9}, "score": 0.7}
    ch = [{"metric": "a", "path": ["x"]}]
    assert S.better(base, {"scores": {"a": 0.7, "b": 0.88, "dynamics": 0.1}, "score": 0.79}, ch)[0]
    assert not S.better(base, {"scores": {"a": 0.5, "b": 0.9}, "score": 0.7}, ch)[0]
    assert S.better(base, {"scores": {"a": 0.8, "b": 0.7}, "score": 0.75}, ch) == (False, "hurt b")


def test_a_producer_session_versions_every_kept_step_and_can_be_undone():
    import json
    import tempfile
    import tomllib

    import studio as S
    track = Path(tempfile.mkdtemp())
    import build as B
    sys.path.insert(0, str(B.ENGINE / "studio"))
    from midi_studio import to_toml
    (track / "instruments.toml").write_text(to_toml(_cfg()))
    seen = []

    def fake(cfg, tag):                             # the "render": the bass ducks as far as the mix says
        seen.append(tag)
        return [_kit((cfg["tracks"]["bass"].get("duck") or {}).get("depth", 0.0))]

    run = S.produce(track, rounds=3, passages=[[1, 2]], log=lambda *_: None, render_fn=fake)
    kept = [r for r in run["rounds"] if r["kept"]]
    assert seen[0] == "r0" and kept and run["after"]["score"] >= run["before"]["score"]
    depth = tomllib.loads((track / "instruments.toml").read_text())["tracks"]["bass"]["duck"]["depth"]
    assert depth == round(S.STEP["duck"] * len(kept), 2)
    assert len(S._versions(track)) == len(kept) + 1
    hist = S.history(track)
    assert len(hist) == 1 and "detail" not in hist[0]["before"] and json.dumps(hist)
    S.revert(track, 0)
    assert "duck" not in tomllib.loads((track / "instruments.toml").read_text())["tracks"]["bass"]
    # a render that does not respond: the round is refused and the mix is left alone
    t2 = Path(tempfile.mkdtemp())
    (t2 / "instruments.toml").write_text(to_toml(_cfg()))
    before = (t2 / "instruments.toml").read_text()
    run2 = S.produce(t2, rounds=2, passages=[[1, 2]], log=lambda *_: None, render_fn=lambda cfg, tag: [_kit(0.0)])
    assert run2["rounds"] and not any(r["kept"] for r in run2["rounds"])
    assert (t2 / "instruments.toml").read_text() == before and not S._versions(t2)


def _tone(f0=220.0, secs=1.2, decay=3.0, partials=8, noise=0.0, attack=0.003, seed=1):
    import numpy as np
    import timbre as T
    t = np.arange(int(secs * T.SR)) / T.SR
    y = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, partials + 1)) if f0 else 0 * t
    y = y + noise * np.random.default_rng(seed).standard_normal(len(t))
    env = np.minimum(1, t / attack) * np.exp(-t * decay)
    return 0.3 * y * env


def test_the_timbre_lab_hears_what_a_sound_is():
    import numpy as np
    import timbre as T
    pluck = T.fingerprint(_tone(220, decay=4))
    assert abs(pluck["f0"] - 220) < 3 and "pluck" in T.tags(pluck), T.describe(pluck)
    pad = T.fingerprint(_tone(110, secs=2.0, decay=0.05, partials=3, attack=0.4))
    assert {"pad", "sustained"} <= set(T.tags(pad)), T.tags(pad)
    hit = T.fingerprint(_tone(0, secs=0.6, decay=20, noise=1.0))
    assert hit["f0"] is None and {"hit", "noisy", "unpitched"} <= set(T.tags(hit)), T.tags(hit)
    t = np.arange(T.SR) / T.SR                       # the fundamental missing, its harmonics still say 150 Hz
    ghost = T.fingerprint(sum(np.sin(2 * np.pi * 150 * k * t) for k in (2, 3, 4, 5)) * 0.1)
    assert abs(ghost["f0"] - 150) < 3, ghost["f0"]
    assert T.fingerprint(np.zeros(T.SR))["silent"]


def test_timbre_distance_is_a_fair_ruler():
    import timbre as T
    a, b, c = (T.fingerprint(_tone(220, decay=4)), T.fingerprint(_tone(233, decay=4)), T.fingerprint(_tone(0, noise=1, decay=20)))
    assert T.distance(a, a) == 0 and T.distance(a, b) == T.distance(b, a)
    assert T.distance(a, b) < T.distance(a, c), (T.distance(a, b), T.distance(a, c))
    assert T.distance(a, T.fingerprint(_tone(0, secs=0.5) * 0)) == float("inf")
    assert T.differences(a, a) == [] and T.differences(a, c)


def test_a_sound_finds_the_instrument_that_made_it_and_the_library_keeps_it():
    import tempfile
    import timbre as T
    real_root, real_index = T.ROOT, T.index
    picks = [("ghost", "afterimage-pad"), ("gravity", "slack-bass"), ("weather", "thunderhead"),
             ("phase_garden", "drift-choir"), ("material", "tiring-glass"), ("terrain", "shifting-sands")]
    entries = []
    for e, p in picks:
        patch = {"engine": e, "preset": p}
        fp = T.fingerprint(T.audition(patch))
        entries.append({"id": f"{e}/{p}", "patch": patch, "fingerprint": fp, "tags": T.tags(fp)})
    try:
        T.ROOT, T.index = Path(tempfile.mkdtemp()), lambda **_: entries
        for target in (entries[1], entries[4]):
            r = T.match(T.audition(target["patch"], 64), budget=6)
            assert r["best"]["id"] == target["id"], (target["id"], [(c["id"], c["distance"]) for c in r["candidates"]])
            assert r["renders"] <= 6 and len({c["patch"]["engine"] for c in r["candidates"]}) == len(r["candidates"])
            assert r == T.match(T.audition(target["patch"], 64), budget=6)          # deterministic
        tr = T.to_track(r["best"]["patch"])
        assert tr["kind"] == "synthesis" and tr["engine"] == "material" and tr["version"]
        f = T.add("Glass Bell", r["best"]["patch"], source="/somewhere/bell.wav")
        f2 = T.add("Glass Bell", entries[0]["patch"])                              # never overwrites
        assert f == f2 and f.with_name("glass-bell.1.json").exists()
        lib = T.library()
        assert [x["name"] for x in lib] == ["Glass Bell"] and lib[0]["patch"]["engine"] == "ghost"
        hits = T.search("glass")
        assert hits[0]["where"] == "library" and any(h["name"] == "material/tiring-glass" for h in hits)
        near = T.search(like=entries[2]["fingerprint"], presets=True, k=3)
        assert near[0]["name"] == "weather/thunderhead", near
    finally:
        T.ROOT, T.index = real_root, real_index


def test_the_observatory_reads_the_clocks_and_branches_only_the_passage():
    import lineage as G
    import observatory as O
    dna = G.origin(1969)
    s = G.grow(dna)
    clocks = O.clocks(s)
    assert len(clocks) == s["bars"] and [c["bar"] for c in clocks] == list(range(1, s["bars"] + 1))
    for sec in s["sections"]:
        mine = [c for c in clocks if sec["start"] <= c["bar"] < sec["start"] + sec["bars"]]
        assert {c["section"] for c in mine} == {sec["name"]} and [c["in_section"] for c in mine] == list(range(1, sec["bars"] + 1))
    assert all(0.0 <= c["energy"] <= 1.0 for c in clocks) and any(c["chord"] for c in clocks)
    assert O.chord_name([0, 4, 7], 0) == "C" and O.chord_name([9, 0, 4], 9) == "Am"
    r = O.branch(dna, 9, n=6, seed=3)
    assert r == O.branch(dna, 9, n=6, seed=3), "branching is deterministic"
    assert list(r["passage"]) == [9, 12] and r["presented"] and len(r["presented"]) <= 6
    outside = O._outside(s, 9, 12)
    for c in r["presented"]:
        child = G.grow(c["dna"])
        assert O._outside(child, 9, 12) == outside, "a branch changed notes outside its passage"
        assert child != s and "front" in c and c["total"] is not None


def test_the_observatory_keeps_ratings_and_reads_the_producer_and_the_mix():
    import json
    import tempfile
    import numpy as np
    import lineage as G
    import observatory as O
    from scipy.io import wavfile
    tmp = Path(tempfile.mkdtemp())
    store = tmp / "lineage.jsonl"
    a, b = G.origin(1969), G.origin(4242)
    assert O.ratings(store) == [] and O.ideas(store, tmp / "none.json") == []
    O.rate(a, 9, store=store)                      # clipped to five stars
    G.save(b, total=0.61, store=store)
    rows = O.ratings(store)
    assert [r.get("rating") for r in rows] == [5.0, None] and rows[1]["total"] == 0.61
    ids = {i["id"] for i in O.ideas(store, tmp / "none.json")}
    assert ids == {G.dna_id(a), G.dna_id(b)}
    track = tmp / "t"
    track.mkdir()
    ch = {"path": ["mix", "bass", "gain_db"], "from": 0.0, "to": -2.0, "why": "bass on the kick"}
    (track / "studio.json").write_text(json.dumps([{"time": 1.0, "before": {"score": 0.5}, "rounds": [
        {"changes": [ch], "kept": True, "verdict": "better", "after": {"score": 0.6}},
        {"changes": [ch], "kept": False, "verdict": "worse", "after": {"score": 0.55}}]}]))
    prod = O.producer(track)
    assert [(p["round"], p["kept"], p["before"], p["after"]) for p in prod] == [(1, True, 0.5, 0.6), (2, False, 0.6, 0.55)]
    assert "bass on the kick" in prod[0]["change"]
    sr = 44100
    t = np.arange(sr * 2) / sr
    wavfile.write(str(tmp / "a.wav"), sr, (0.3 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32))
    sp = O.spectrum(tmp / "a.wav")
    peak = sp["bands"][int(np.argmax(sp["db"]))]
    assert 800 <= peak <= 1260 and len(sp["db"]) == len(O.BANDS), peak
    bs = O.bar_spectra(tmp / "a.wav", 120)        # 2 s at 120 bpm is one 4/4 bar
    assert len(bs["db"]) == 1 and len(bs["db"][0]) == len(O.BANDS)


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
