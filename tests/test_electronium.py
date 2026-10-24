#!/usr/bin/env python3
"""Checks for the Electronium, the artist credit and the friends registry. Run: $PY tests/test_electronium.py"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bountiful"))
import electronium as EL  # noqa: E402

EL.DEFAULT["taste"] = 0.0          # the checks don't depend on anyone's ratings

CM = [0, 2, 3, 5, 7, 8, 10]
CHORDS = [(0, [0, 3, 7], 0), (8, [8, 0, 3], 8), (10, [10, 2, 5], 10), (7, [7, 11, 2], 7)]   # Cm Ab Bb G, a bar each


def timeline(bars=24, lead=True, sidekick=True):
    return [{"bar": b, "tr": 0, "act": 1.0, "kime": False, "lead": lead, "sidekick": sidekick, "tonic": 0, "key_pcs": CM,
             "chords": [(0, 4, CHORDS[b % 4][1], CHORDS[b % 4][2])]} for b in range(bars)]


def run(over=None, bars=24):
    m = EL.Machine(EL.patch(over), bars)
    return m, m.perform(timeline(bars))


def test_gates():
    s = EL.np.arange(32)
    ev = lambda e: list(s[EL.Gate(e).eval(s, lambda n: 0)])
    assert ev("c4")[:4] == [0, 4, 8, 12]
    assert ev("c8+4") == [4, 12, 20, 28]
    assert ev("c2 & c3") == [0, 6, 12, 18, 24, 30]
    assert ev("c2 ^ c3")[:5] == [2, 3, 4, 8, 9]
    assert ev("~c2 & c3") == [3, 9, 15, 21, 27]
    assert ev("c4 | c8 & c3") == ev("c4 | (c8 & c3)")          # & binds tighter than |
    for bad in ("c2 &", "c0", "c2 + c3", "(c2"):
        try:
            EL.Gate(bad).eval(s, lambda n: 0)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} should not parse")
    assert EL.lcm([2, 3, 4, 7, 8]) == 168


def test_seed_is_terrain():
    _, a = run({"bounty": 42})
    _, b = run({"bounty": 42})
    _, c = run({"bounty": 43})
    assert a["line"] == b["line"], "same Bounty, same music"
    assert a["line"] != c["line"], "another Bounty, other music"
    _, w = run({"bounty": "C-Lizzy"})
    _, w2 = run({"bounty": "C-Lizzy"})
    assert w["line"] == w2["line"]
    # a longer arrangement keeps the same start
    m1 = EL.Machine(EL.patch({"bounty": 5}), 16)
    m2 = EL.Machine(EL.patch({"bounty": 5}), 40)
    assert (m1.u_pitch == m2.u_pitch[:16 * 16]).all() and (m1.lead_trig == m2.lead_trig[:16 * 16]).all()


def test_density_is_a_threshold():
    """Turning Density down removes notes from the same terrain; it doesn't re-roll."""
    m = EL.Machine(EL.patch({"bounty": 9}), 16)
    hi = set(EL.np.flatnonzero(m.lead_trig & (m.u_dens < 0.8)))
    lo = set(EL.np.flatnonzero(m.lead_trig & (m.u_dens < 0.4)))
    assert lo < hi and len(lo) > 0
    off = {"behaviours": {k: 0 for k in EL.BEHAVIOURS}}
    _, a = run({"bounty": 9, "density": 0.4, **off})
    _, b = run({"bounty": 9, "density": 0.8, **off})
    steps = lambda r: {n[4] for n in r["line"]}
    assert steps(a) < steps(b)


def test_scale_constraint_and_intervals():
    _, r = run({"bounty": 3, "scale": "minor_pent", "root": "C", "behaviours": {k: 0 for k in EL.BEHAVIOURS}})
    pent = {0, 3, 5, 7, 10}
    assert r["line"] and all(n[2] % 12 in pent for n in r["line"])
    steps = {"intervals": {"repeat": 0.001, "step": 1.0, "third": 0.001, "fourth": 0.001, "fifth": 0.001, "sixth": 0.001, "octave": 0.001},
             "gravity": 0, "mutation": 0, "behaviours": {k: 0 for k in EL.BEHAVIOURS}}
    for think, share in ((0, 0.9), (200, 0.75)):          # the walk alone, then with themes (their sequences may leap)
        _, steps_only = run({"bounty": 3, "think": think, **steps})
        ps = [n[2] for n in steps_only["line"]]
        jumps = [abs(b - a) for a, b in zip(ps, ps[1:])]
        assert sum(1 <= j <= 2 for j in jumps) / len(jumps) > share, f"the step knob makes a stepwise line (think {think})"


def test_behaviours_and_register():
    m, r = run({"bounty": 11}, 48)
    tags = set(m.log)
    assert "G" in tags and len(tags & {"R", "Rv", "T", "I", "O"}) >= 3, m.log
    lo, hi = m.p["register"]
    assert all(lo - 12 <= n[2] <= hi + 12 for n in r["line"])


def test_freeze_and_populate():
    fz = [{"bar": 9, "notes": 8, "bars": 4, "transform": "transpose", "amount": 1}]
    m, r = run({"bounty": 21, "freeze": fz})
    assert m.log[8:12] == ["F"] * 4 and m.log[12] != "F", m.log
    fz_mod = [{"bar": 9, "notes": 8, "bars": 6, "transform": "mutate", "amount": 0.5, "modify": 0.5}]
    m2, r2 = run({"bounty": 21, "freeze": fz_mod})
    assert m2.log[8:14] == ["F"] * 6
    bars = lambda res, b: [n[2] for n in res["line"] if int(n[0] // 4) == b]
    assert any(bars(r2, 8 + k) for k in range(6))
    # the frozen loop is what was in the ring buffer before bar 9 (same Bounty, nothing differs before the freeze)
    _, plain = run({"bounty": 21})
    assert [n for n in plain["line"] if n[0] < 32] == [n for n in r["line"] if n[0] < 32]


def test_sidekick_rules():
    for rule in EL.SIDEKICK[1:]:
        m, r = run({"bounty": 4, "sidekick": rule})
        lo, hi = m.p["sidekick_register"]
        assert r["sidekick"], rule
        assert all(lo <= n[2] <= hi for n in r["sidekick"]), rule
    m, r = run({"bounty": 4, "sidekick": "fifth_below"})
    lead = {round(n[0], 3): n[2] for n in r["line"]}
    for t, d, p, v, o in r["sidekick"]:
        assert (lead[round(t, 3)] - p) % 12 in (7, 8), "a fifth below (or the scale tone under it)"
    m, r = run({"bounty": 4, "sidekick": "root_on_downbeat"})
    assert all(n[0] % 4 == 0 and n[2] % 12 == CHORDS[int(n[0] // 4) % 4][2] for n in r["sidekick"])
    m, r = run({"bounty": 4, "sidekick": "off"})
    assert r["sidekick"] == []


def test_drums():
    m = EL.Machine(EL.patch({"bounty": 2}), 8)
    bar = m.drum_steps({"kick", "snare", "hat"}, 0)
    assert sorted(s for s, snd, v in bar if snd == "snare") == [4, 12]
    assert (0, "kick") in {(s, snd) for s, snd, v in bar}
    assert m.drum_steps({"kick"}, 3) == EL.Machine(EL.patch({"bounty": 2}), 8).drum_steps({"kick"}, 3)


def test_grid_with_electronium_layers():
    """A grid song: the grid's lanes play as written, the lanes it doesn't have come off the Electronium's clocks."""
    import producer as PR
    m = EL.Machine(EL.patch({"bounty": 2, "drums": {"el_hat": {"gate": "c2", "sound": "hat", "vel": 0.5}}}), 8)
    cfg = {"grid": {"kick": [[0, 1.0], [10, 0.9]]}, "electronium": m, "_bpm": 130}
    ev = PR.drum_bar("grid", {"kick", "el_hat"}, None, 0, EL.np.random.default_rng(0), cfg)
    assert sorted(t * 4 for t, snd, v, o in ev if snd == "kick") == [0, 10]
    assert sorted(round(t * 4) for t, snd, v, o in ev if snd == "hat") == list(range(0, 16, 2))
    assert not PR.drum_bar("grid", {"el_hat"}, None, 0, EL.np.random.default_rng(0), dict(cfg, electronium=None))


def test_patch_roundtrip():
    p = EL.patch({"bounty": 77, "freeze": [{"bar": 5, "notes": 8, "bars": 2, "transform": "invert"}], "drums": {"kick": {"density": 0.5}}})
    q = EL.patch(EL.tomllib.loads(EL.dump(p)))
    assert q == p, {k: (p[k], q.get(k)) for k in p if p[k] != q.get(k)}


CHANNELS = [{"name": "lead", "role": "melody"}, {"name": "sidekick", "role": "harmony", "interval": "sixth_below"},
            {"name": "bass", "role": "bass"}, {"name": "arp", "role": "ostinato", "length": 5},
            {"name": "counter", "role": "counter"}]


def test_presets_and_channels():
    s = EL.np.arange(32)
    ev = lambda e: list(s[EL.Gate(e).eval(s, lambda n: 0)])
    assert ev("p1") == ev("c4") and ev("p2 & c8") == [0, 8, 16, 24] and ev("~p12") == ev("~(c1 & ~c4)")
    for bad in ("p0", "p13"):
        try:
            EL.Gate(bad)
            raise AssertionError(f"{bad} parsed")
        except ValueError:
            pass
    m, r = run({"bounty": 8, "channels": CHANNELS}, 16)
    assert set(r["parts"]) == {"lead", "sidekick", "bass", "arp", "counter"} and all(r["parts"].values())
    tl = {c["bar"]: c for c in timeline(16)}
    for t, d, q, v, o in r["parts"]["bass"]:                 # roots on the bar lines, in the bass register
        assert 28 <= q <= 47
        if t % 4 == 0:
            assert q % 12 == tl[int(t // 4)]["chords"][0][3] % 12
    arp = r["parts"]["arp"]                                     # one cell per 8th, so 5 cells come round every 2.5 beats
    assert all(round(n[0] * 2) == n[0] * 2 for n in arp) and all(n[2] % 12 in tl[int(n[0] // 4)]["chords"][0][2] for n in arp)
    lead = {round(n[0], 3): n[2] for n in r["lead"]}
    clash = sum(1 for n in r["parts"]["counter"] if lead.get(round(n[0], 3), -99) % 12 == n[2] % 12)
    assert clash <= len(r["parts"]["counter"]) * 0.1, "the counter line keeps off the melody's notes"
    sc = set(CM)
    assert all(n[2] % 12 in sc for n in r["sidekick"])


def test_recorder_moves():
    base = {"bounty": 8, "channels": CHANNELS}
    _, a = run(base, 16)
    _, b = run({**base, "moves": [{"bar": 5, "to_bar": 8, "channel": "arp", "set": {"density": 0.2}},
                                  {"bar": 9, "channel": "bass", "set": {"mute": True}},
                                  {"bar": 13, "set": {"gate": "p1"}}]}, 16)
    cnt = lambda r, part, b0, b1: sum(1 for n in r["parts"][part] if b0 * 4 <= n[0] < b1 * 4)
    assert cnt(a, "arp", 0, 4) == cnt(b, "arp", 0, 4) and cnt(b, "arp", 7, 16) < cnt(a, "arp", 7, 16), "the ramp thins the ostinato"
    assert cnt(b, "bass", 8, 16) == 0 and cnt(b, "bass", 0, 8) == cnt(a, "bass", 0, 8), "muted from bar 9"
    m = EL.Machine(EL.patch({**base, "moves": [{"bar": 5, "to_bar": 8, "channel": "arp", "set": {"density": 0.2}}]}), 16)
    arp = next(c for c in m.chans if c["name"] == "arp")
    ds = [round(m.at(k, arp)["density"], 3) for k in range(3, 9)]
    assert ds[0] == 1.0 and ds[1] > ds[2] > ds[3] > ds[4] == 0.2 == ds[5], ds
    try:
        EL.Machine(EL.patch({"moves": [{"bar": 1, "channel": "nobody", "set": {"density": 0.1}}]}), 4)
        raise AssertionError("a move on a missing channel")
    except ValueError:
        pass


def test_thinking_and_themes():
    p = EL.patch({"bounty": 12})
    ideas = EL.think(p)
    assert len(ideas) == 200 and ideas == EL.think(p), "the same Bounty thinks the same thoughts"
    best = EL.kept(p, ideas)
    assert len(best) == 3 and best[0]["score"] == max(d["score"] for d in ideas)
    assert [d["n"] for d in EL.kept(EL.patch({"bounty": 12, "keep": [5, 9]}))] == [5, 9]
    # the theme comes back: the theme bars of two 8-bar phrases share their rhythm
    m, r = run({"bounty": 12}, 16)
    assert m.log[0] == "Th" and m.log[8] in ("Th", "Th~") and m.log[7] == "C", m.log
    on = lambda b: [round(n[0] - b * 4, 3) for n in r["line"] if b * 4 <= n[0] < b * 4 + 4]
    assert on(0) and on(0) == on(8), (on(0), on(8))
    _, plain = run({"bounty": 12, "think": 0}, 16)
    assert plain["line"] != r["line"] and EL.Machine(EL.patch({"bounty": 12, "think": 0}), 16).kept == []


def test_tone_generator_and_tracks():
    import electronium_voice as V
    rng = EL.np.random.default_rng(1)
    for name in EL.TONES:
        y = V.note(69, 0.9, 0.3, EL.TONES[name], rng)
        assert EL.np.isfinite(y).all() and 0.01 < abs(y).max() < 2.0, name
    y = V.note(69, 0.8, 0.5, {"wave": "sine", "drift": 0, "vibrato": 0, "cutoff": 18000, "env": "organ"}, rng)
    spec = abs(EL.np.fft.rfft(y[:V.SR // 2]))
    assert abs(EL.np.argmax(spec) * 2 - 440) <= 4, "A4 is 440 Hz"
    import build as B
    g = B.genres()["electronium-69"]
    g = dict(g, electronium={"channels": CHANNELS[:3] + [{"name": "plain", "role": "counter", "tone": None}]})
    tr = B.channel_tracks(g)
    assert set(tr) == {"lead", "lead_hi", "sidekick", "bass"} and tr["bass"]["kind"] == "pyvoice" and tr["bass"].get("mono")
    assert Path(tr["lead"]["preset"]["module"]).exists() and tr["lead"]["preset"]["wave"] == "square"
    for bad in ({"channels": [{"role": "drummer"}]}, {"channels": [{"role": "harmony", "interval": "ninth"}]},
                {"channels": [{"name": "x", "tone": "kazoo"}]}):
        try:
            [EL.tone(c) for c in EL.channels(EL.patch(bad))]
            raise AssertionError(bad)
        except ValueError:
            pass


def test_artist_is_always_m4s4t0():
    import build as B
    import credits
    assert credits.ARTIST == B.ARTIST == "M4S4T0"
    g = B.genres()["electronium-69"]
    assert B.instrument_map(g, "T", "t", 1)["meta"]["artist"] == "M4S4T0"
    assert credits.stamp({"artist": "someone else", "album": "X"}) == {"artist": "M4S4T0", "album": "X", "album_artist": "M4S4T0"}
    import re
    for f in (ROOT / "bountiful").glob("*.py"):           # no script writes another artist name
        for m in re.finditer(r"""["']artist["']\s*:\s*["']([^"']+)["']""", f.read_text()):
            assert m.group(1) == "M4S4T0", (f.name, m.group(0))


def test_friends():
    import friends as F
    with tempfile.TemporaryDirectory() as d:
        F.FILE = Path(d) / "friends.toml"
        F.save({"c-lizzy": {"name": "C-Lizzy", "role": "composer", "always": True, "soundcloud": "clizzy", "bandcamp": "clizzy"},
                "pal": {"name": "Pal", "instagram": "pal.makes", "mastodon": "pal@toot.example"}})
        assert F.clean("instagram", "https://www.instagram.com/pal.makes/") == "pal.makes"
        assert F.clean("bandcamp", "https://clizzy.bandcamp.com/album/x") == "clizzy"
        assert F.clean("x", "@pal") == "pal"
        try:
            F.clean("bluesky", "not a handle")
            raise AssertionError("bad handle accepted")
        except ValueError:
            pass
        tr = Path(d) / "song"
        tr.mkdir()
        (tr / "instruments.toml").write_text('[meta]\ntitle = "Song"\nartist = "M4S4T0"\ngenre = "Electronium \'69"\n')
        out = F.share(tr, ["Pal", "Newcomer"], log=lambda s: None)
        assert "@clizzy" in out["soundcloud"] and "Pal" in out["soundcloud"] and "@pal" not in out["soundcloud"]
        assert "@pal.makes" in out["instagram"] and "@clizzy" not in out["instagram"] and "C-Lizzy" in out["instagram"]
        assert "@pal@toot.example" in out["mastodon"]
        assert "@" not in out["bandcamp"].split("\n")[1] and "https://clizzy.bandcamp.com" in out["bandcamp"]
        assert all(t.startswith("Song by M4S4T0") for t in out.values())
        assert json.loads((tr / "friends.json").read_text()) == ["Pal", "Newcomer"]
        assert F.find(F.load(), "Newcomer"), "a new name is remembered"
        again = F.share(tr, log=lambda s: None)                 # the track remembers who's on it
        assert again == out


def test_chords_development_and_ending():
    chans = [{"name": "lead", "role": "melody"}, {"name": "keys", "role": "chords", "voices": 3}]
    m, res = run({"bounty": 9, "channels": chans, "phrase": ["theme", "develop", "augment", "mirror"] * 2}, bars=16)
    keys = res["parts"]["keys"]
    assert keys, "the chord sequencer played nothing"
    by = {}
    for (t, d, q, v, o) in keys:
        by.setdefault(t, []).append(q)
    for t, qs in by.items():
        b = int(t // 4)
        pcs = set(CHORDS[b % 4][1])
        assert all(q % 12 in pcs for q in qs), (t, qs)                # every voice a chord tone
        assert all(52 <= q <= 74 for q in qs) and len(set(q % 12 for q in qs)) == len(qs) == 3
    starts = sorted(by)
    moves = [sum(abs(a - b) for a, b in zip(sorted(by[x]), sorted(by[y]))) for x, y in zip(starts, starts[1:])]
    assert sum(moves) / len(moves) < 6, moves                        # voice-led: small moves
    assert {"D", "A", "M"} <= set(m.log), m.log
    assert m.log[-1] == "E"
    last = max(res["lead"], key=lambda n: n[0])
    assert last[2] % 12 == 0 and last[0] + last[1] > 15 * 4 + 3.5    # home: the tonic, held to the end
    try:
        EL.channels(EL.patch({"channels": [{"name": "x", "role": "pads"}]}))
    except ValueError:
        return
    raise AssertionError("a bad role got through")

def test_taste_learns():
    import importlib
    import taste
    with tempfile.TemporaryDirectory() as tmp:
        old = taste.FILE
        taste.FILE = Path(tmp) / "taste.json"
        taste._cache.clear()
        try:
            p = EL.patch({"bounty": 5, "think": 60})
            ideas = EL.think(p)
            assert taste.model() is None and taste.bonus(ideas[0]["cells"]) == 0.0
            # someone who loves busy, syncopated ideas and dislikes sparse ones
            busy = sorted(ideas, key=lambda d: -len(d["cells"]))
            for d in busy[:8]:
                taste.rate(d, 1, bounty=5)
            for d in busy[-8:]:
                taste.rate(d, -1, bounty=5)
            m = taste.model()
            assert m is not None and m["n"] == 16
            assert taste.bonus(busy[0]["cells"]) > taste.bonus(busy[-1]["cells"])
            pt = EL.patch({"bounty": 5, "think": 60, "taste": 1.0})
            mean_n = lambda ks: sum(len(k["cells"]) for k in ks) / len(ks)
            assert mean_n(EL.kept(pt)) >= mean_n(EL.kept(p))
            y = taste.audition(ideas[0], 0, "minor", 120)
            assert y.ndim == 1 and len(y) > 44100 and EL.np.isfinite(y).all() and EL.np.abs(y).max() <= 0.81
            assert taste.write_wav(Path(tmp) / "a.wav", y).stat().st_size > 1000
        finally:
            taste.FILE = old
            taste._cache.clear()

def test_live_plays_and_records_moves():
    import numpy as np
    import live as LV
    lv = LV.Live("77", lookahead_bars=2)
    b0, y = lv.next_block()
    assert b0 == 0 and y.shape == (2 * lv.bar_n, 2) and np.isfinite(y).all() and np.abs(y).max() > 0.01
    lv.turn("density", 0.95)
    lv.turn("mute", True, "arp")
    assert lv.user_moves[0]["bar"] == 3 and lv.user_moves[1]["channel"] == "arp"
    b1, y = lv.next_block()
    assert b1 == 2 and lv.patch()["moves"]
    try:
        lv.turn("gate", "nonsense((", "lead")
        raise AssertionError("a bad gate went through")
    except ValueError:
        ...
    lv.seek(lv.bars - 1)
    lv.next_block()
    b, _ = lv.next_block()                 # past the end: the next Bounty
    assert b == 0 and str(lv.pl["bounty"]) == "78"

def test_batch_day_of_ideas():
    import batch
    with tempfile.TemporaryDirectory() as tmp:
        d = batch.day(4, start=300, songs=1, out=Path(tmp) / "s", log=lambda *_: None)
        idx = json.loads((d / "index.json").read_text())
        rows = idx["rows"]
        assert [r["rank"] for r in rows] == [1, 2, 3, 4]
        assert all(a["score"] >= b["score"] for a, b in zip(rows, rows[1:]))
        assert (d / rows[0]["audition"]).exists() and (d / rows[0]["track"] / "notes.txt").exists()
        assert "| 1 |" in (d / "index.md").read_text()

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
