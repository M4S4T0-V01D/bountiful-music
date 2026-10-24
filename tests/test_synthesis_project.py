#!/usr/bin/env python3
"""The Synthesis Lab's project format: round trip, forgiving loads, snapshots, deterministic renders, and the same
track tables a song's instruments.toml uses. Run: python tests/test_synthesis_project.py"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bountiful"))
import synthesis as S  # noqa: E402
from synthesis import project as P  # noqa: E402
from synthesis import rendering as R  # noqa: E402

ARP = [(b * 0.5, 0.4, 57 + (0, 3, 7, 10)[b % 4], 0.8) for b in range(16)]


def demo() -> dict:
    proj = P.new("test", bpm=150, seed=5)
    proj["render"].update(beats=8, tail_s=0.5)
    P.add_track(proj, "lead", "terrain", "lissajous-lead", {"radius": 1.1}, ARP, gain_db=-3, pan=-0.3,
                automation={"radius": [[0, 0.6], [8, 1.4]]})
    P.add_track(proj, "bells", "material", "practice-room-piano", clip=ARP[::2])
    P.add_track(proj, "web", graph={"nodes": {"src": {"engine": "phase_garden", "preset": "bloom"},
                                              "eco": {"engine": "echo", "preset": "tuned-coral"}},
                                    "edges": [{"from": "src", "to": "eco", "gain": 0.7},
                                              {"from": "eco", "to": "src", "gain": 2.0, "feedback": True}],
                                    "out": {"src": 0.5, "eco": 0.7}},
                clip=[(0, 6, 60, 0.7), (2, 4, 67, 0.6)])
    return proj


def test_roundtrip_and_deterministic_render():
    proj = demo()
    with tempfile.TemporaryDirectory() as d:
        path = P.save(proj, Path(d) / "p.bflab")
        back = P.load(path)
    assert back["tracks"]["lead"]["version"] == S.engine_class("terrain").VERSION
    assert P.engines_used(back) == {"terrain": 1, "material": 1, "phase_garden": 1, "echo": 1}
    m1, st1 = P.render(proj)
    m2, st2 = P.render(back)
    assert m1.shape == (P.length(proj), 2) and set(st1) == {"lead", "bells", "web"}
    assert np.array_equal(m1, m2), "a saved and loaded project renders the same samples"
    assert np.isfinite(m1).all() and 1e-3 < np.abs(m1).max() < 4
    for k, y in st1.items():
        assert np.abs(y).max() > 1e-4, f"{k} is silent"
    assert np.abs(st1["lead"][:, 1]).sum() < np.abs(st1["lead"][:, 0]).sum(), "pan left"


def test_forgiving_load():
    d = demo()
    d["format_version"] = 1
    d["future_key"] = {"x": 1}
    d["tracks"]["lead"]["mystery"] = 3
    d["tracks"]["lead"]["version"] = 99
    d["tracks"]["gone"] = {"kind": "synthesis", "engine": "no-such-engine", "clip": [(0, 1, 60, 1)]}
    d["tracks"]["late"] = {"kind": "synthesis", "engine": "ghost", "start": "missing", "clip": [(0, 2, 60, 1)]}
    del d["render"]["block"]
    proj = P.normalise(json.loads(json.dumps(d)))
    assert proj["future_key"] == {"x": 1} and proj["tracks"]["lead"]["mystery"] == 3, "unknown keys survive"
    assert proj["render"]["block"] == S.BLOCK
    probs = P.problems(proj)
    assert any("gone" in p and "skipped" in p for p in probs)
    assert any("lead" in p and "v99" in p for p in probs)
    assert any("late" in p and "missing" in p for p in probs)
    mix, stems = P.render(proj)
    assert "gone" not in stems and "late" in stems and np.isfinite(mix).all()
    try:
        P.normalise({"format": "something-else"})
        raise AssertionError("foreign file accepted")
    except ValueError:
        pass


def test_snapshot_start_carries_engine_state():
    proj = P.new("snap", bpm=120, seed=2)
    proj["render"].update(beats=4, tail_s=0.0)
    hits = [(b, 0.25, 72, 1.0) for b in range(0, 16)]
    P.add_track(proj, "m", "material", "tiring-glass", clip=hits)
    fresh = P.build(proj, "m")
    P.capture(proj, "after-a-minute", beats=16)
    worn = proj["snapshots"]["after-a-minute"]["m"]
    assert worn["state"]["strikes"] == 16
    proj["tracks"]["m"]["start"] = "after-a-minute"
    eng = P.build(proj, "m")
    assert eng.strikes == 16 and fresh.strikes == 0
    assert not np.allclose(eng.wear, fresh.wear), "the starting snapshot brings the worn map"
    a, _ = P.render(proj)
    b, _ = P.render(json.loads(json.dumps(proj)))
    assert np.array_equal(a, b), "snapshots survive JSON"


def test_graph_snapshot_and_feedback_bounded():
    proj = demo()
    for k in ("lead", "bells"):
        proj["tracks"][k]["mute"] = True
    P.capture(proj, "s")
    assert set(proj["snapshots"]["s"]["web"]) == {"src", "eco"}
    proj["tracks"]["web"]["start"] = "s"
    mix, stems = P.render(proj)
    assert set(stems) == {"web"} and np.isfinite(mix).all() and np.abs(mix).max() < 4


def test_same_tables_as_a_song():
    proj = demo()
    proj["assets"]["voice"] = "media/voice.wav"
    proj["tracks"]["bells"]["assets"] = {"source": "voice"}
    inst = P.to_instruments(proj)
    for name, tr in inst["tracks"].items():
        assert R.is_synthesis(tr) and not set(P.LAB_KEYS) & set(tr), name
    assert inst["tracks"]["bells"]["assets"] == {"source": "media/voice.wav"}
    back = P.from_instruments({"tracks": {**inst["tracks"], "kick": {"kind": "drums"}}}, bpm=150, seed=5)
    assert set(back["tracks"]) == {"lead", "bells", "web"} and back["tracks"]["lead"]["clip"] == []
    # the song renderer's adapter plays a Lab track exactly as the Lab does
    lab = demo()
    tr = lab["tracks"]["lead"]
    notes = [{"start": b * 60 / 150, "end": (b + ln) * 60 / 150, "pitch": p, "vel": v} for b, ln, p, v in tr["clip"]]
    seed = R.track_seed(tr, lab["seed"], "lead")
    song = R.render_part(P.to_instruments(lab)["tracks"]["lead"], notes, P.length(lab), 0.0, 150, seed)
    mine = P.render_track(lab, "lead")
    assert np.allclose(song, mine, atol=1e-6), float(np.abs(song - mine).max())


def test_wav_export_never_clips():
    with tempfile.TemporaryDirectory() as d:
        from scipy.io import wavfile
        p = P.write_wav(Path(d) / "x.wav", np.full((100, 2), 3.0, np.float32))
        sr, y = wavfile.read(p)
    assert sr == S.SR and y.shape == (100, 2) and np.abs(y).max() < 32767 * 0.9


def test_clips_are_deterministic_and_valid():
    for kind in P.CLIPS:
        a, b = P.clip(kind, 16, 57, seed=4), P.clip(kind, 16, 57, seed=4)
        assert a == b and a, kind
        for n in a:
            assert 0 <= n[0] < 16 and n[1] > 0 and 0 <= int(n[2]) <= 127, (kind, n)
    try:
        P.clip("kazoo")
        raise AssertionError("unknown clip kind accepted")
    except ValueError:
        pass


def test_demos_build_and_mix_six_engines():
    from synthesis import demos as D
    for name, make in D.DEMOS.items():
        proj = make()
        assert proj == make(), name                                   # deterministic
        assert not P.problems(proj), (name, P.problems(proj))
        assert json.loads(json.dumps(proj)) == proj, name             # plain data, saves as .bflab
        assert set(P.engines_used(proj)) <= set(S.ENGINES), name
    assert len(P.engines_used(D.mixed_production())) >= 6
    assert D.afterimage()["bpm"] == 174


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
