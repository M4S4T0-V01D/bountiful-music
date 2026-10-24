"""The Experimental Synthesis Lab: every engine's contract (presets, determinism, snapshot / restore, patches,
automation, bounded output), routing, the genre table and its off switch, and Breakforge's generator, stems and MIDI.

Run with the engine venv: .../intelligent-jungle/.venv/bin/python tests/test_synthesis.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bountiful"))
import synthesis as S  # noqa: E402
from synthesis import audio_utils as AU  # noqa: E402
from synthesis.engine_api import CAPS_BASE, note_events  # noqa: E402

SR = S.SR
CHORD = [(0.0, 1.2, 57, 0.8), (0.0, 1.2, 64, 0.7), (0.4, 1.2, 69, 0.9), (1.4, 0.4, 45, 1.0)]   # (t, dur, pitch, vel)
BEATS = [(0.0, 0.25, 36, 1.0), (0.5, 0.25, 42, 0.6), (1.0, 0.25, 38, 0.9), (1.5, 0.25, 46, 0.7)]


def available() -> list:
    """The engines written so far (the registry names all eleven; each test covers whichever exist)."""
    return [e for e in S.ENGINES if importlib.util.find_spec(f"synthesis.engines.{e}") is not None]


def events_for(eid: str) -> list:
    cls = S.engine_class(eid)
    notes = BEATS if "drums" in cls.CAPS else CHORD
    return note_events([{"start": t, "end": t + d, "pitch": p, "vel": v} for t, d, p, v in notes])


def assets_for(eid: str) -> dict:
    return dict(getattr(S.engine_class(eid), "TEST_ASSETS", {}) or {})


def run(eid: str, preset=None, seed=3, secs=2.0, bpm=172.0, **kw):
    e = S.create(eid, preset, seed=seed, assets=assets_for(eid), **kw)
    return e, e.render(events_for(eid), int(secs * SR), bpm)


# ---------------------------------------------------------------------- every engine
def test_registry_and_schema():
    have = available()
    assert {"ghost", "phase_garden", "breakforge"} <= set(have), have
    for eid in have:
        d = S.describe(eid)
        assert d["id"] == eid and d["params"] and len(d["presets"]) >= 4, eid
        assert CAPS_BASE <= set(d["caps"]), eid
        names = [p["name"] for p in d["params"]]
        assert len(names) == len(set(names)), eid


def test_every_preset_renders_bounded():
    for eid in available():
        for pr in S.engine_class(eid).PRESETS:
            _, y = run(eid, pr)
            assert y.shape == (2 * SR, 2) and y.dtype == np.float32, (eid, pr)
            assert np.isfinite(y).all(), (eid, pr)
            m = AU.metrics(y)
            assert m["peak"] < 2.0, (eid, pr, m)
            assert m["rms_db"] > -60, (eid, pr, m)          # it makes a sound


def test_deterministic_and_seeded():
    for eid in available():
        _, a = run(eid)
        _, b = run(eid)
        _, c = run(eid, seed=4)
        assert np.array_equal(a, b), eid
        assert not np.array_equal(a, c), eid


def test_snapshot_restore_continues_exactly():
    for eid in available():
        n = SR
        e = S.create(eid, seed=5, assets=assets_for(eid))
        ev = events_for(eid)
        e.begin(ev, 172.0)
        e.block(n // 2)
        snap = e.snapshot()
        ei, start = e._ei, e._start
        rest = e.block(n // 2)
        f = S.create(eid, seed=99, assets=assets_for(eid))
        f.begin(ev, 172.0)
        f.restore(snap)
        f._ei, f._start = ei, start
        assert np.array_equal(rest, f.block(n // 2)), eid


def test_reset_and_patch_roundtrip():
    for eid in available():
        e, a = run(eid)
        e.reset()
        assert np.array_equal(a, e.render(events_for(eid), 2 * SR, 172.0)), eid
        p = e.patch()
        p["params"]["no_such_param"] = 1                    # a patch from a newer version: unknown keys dropped
        f = S.from_patch(p)
        assert f.p == e.p and f.seed == e.seed, eid


def test_params_clamp():
    for eid in available():
        cls = S.engine_class(eid)
        num = [p for p in cls.PARAMS if p.kind in ("float", "int")]
        e = S.create(eid, params={p.name: p.hi * 10 + 10 for p in num}, assets=assets_for(eid))
        for p in num:
            assert p.lo <= e.p[p.name] <= p.hi, (eid, p.name)
        y = e.render(events_for(eid), SR // 2, 172.0)
        assert np.isfinite(y).all() and np.abs(y).max() <= 4.0, eid


def test_automation_moves_the_sound():
    for eid in available():
        cls = S.engine_class(eid)
        p = next(p for p in cls.PARAMS if p.name == "level")
        e = S.create(eid, seed=1, assets=assets_for(eid))
        y = e.render(events_for(eid), 2 * SR, 172.0, automation={"level": [[0, p.default], [5.7, 0.0]]})
        _, ref = run(eid, seed=1)
        assert np.abs(y[-SR // 4:]).max() < np.abs(ref[-SR // 4:]).max() * 0.5 + 1e-6, eid


def test_realtime_capable():
    for eid in available():
        e, _ = run(eid, secs=2.0)
        assert e.diagnostics()["rt_factor"] < 0.6, (eid, e.diagnostics())


# ---------------------------------------------------------------------- routing
def test_routing_cycles_and_feedback():
    from synthesis.routing import CycleError, Graph
    nodes = {"a": {"engine": "phase_garden", "preset": "bloom"}, "b": {"engine": "ghost"}}
    try:
        Graph({"nodes": nodes, "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}]})
        raise AssertionError("cycle not caught")
    except CycleError as ex:
        assert "a" in str(ex) and "b" in str(ex)
    g = Graph({"nodes": nodes, "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a", "gain": 5, "feedback": True}]},
              seed=2)
    assert max(abs(e["gain"]) for e in g.edges if e.get("feedback")) <= 0.9
    ev = {"a": events_for("phase_garden"), "b": events_for("ghost")}
    y = g.render(ev, SR, 120.0)
    g2 = Graph(g.spec, seed=2)
    assert np.isfinite(y).all() and np.array_equal(y, g2.render(ev, SR, 120.0))


# ---------------------------------------------------------------------- genre table and the off switch
def _jungle():
    import tomllib
    with open(ROOT / "genres" / "atmospheric-jungle-95.toml", "rb") as f:
        return tomllib.load(f)


def test_genre_table_off_by_default_and_forceable():
    from synthesis import genre as SG
    g = _jungle()
    assert SG.table(g) and not SG.table(g).get("enabled")
    assert SG.apply(g) is g
    h = SG.apply(g, force=True)
    assert h["drums"] == "breakforge" and h["_kit"]["stems"]
    assert h["sounds"]["pad"]["kind"] == "synthesis" and h["sounds"]["pad"]["engine"] == "ghost"
    assert "fallback" in h["sounds"]["pad"] or g.get("sounds", {}).get("pad") is None
    assert g.get("drums") != "breakforge"                    # the original is untouched


def test_switched_off_means_untouched():
    from synthesis import genre as SG
    old = os.environ.get("BOUNTIFUL_EXPERIMENTAL")
    os.environ["BOUNTIFUL_EXPERIMENTAL"] = "0"
    try:
        g = _jungle()
        assert not S.enabled() and SG.apply(g, force=True) is g
    finally:
        if old is None:
            os.environ.pop("BOUNTIFUL_EXPERIMENTAL")
        else:
            os.environ["BOUNTIFUL_EXPERIMENTAL"] = old


# ---------------------------------------------------------------------- Breakforge
def test_breakforge_block_size_invariant():
    a = S.create("breakforge", "afterimage-rollers", seed=8).render(None, 3 * SR, 172.0, block=256)
    b = S.create("breakforge", "afterimage-rollers", seed=8).render(None, 3 * SR, 172.0, block=97)
    assert np.array_equal(a, b)


def test_breakforge_stems_sum_to_mix():
    e = S.create("breakforge", "tearout", seed=2)
    st = e.render_stems(None, 3 * SR, 172.0)
    assert set(st) == {"kick", "snare", "hats", "perc", "cymbals"}
    mix = S.create("breakforge", "tearout", seed=2).render(None, 3 * SR, 172.0)
    assert np.allclose(sum(st.values()), mix, atol=1e-4)
    assert AU.metrics(st["kick"])["rms_db"] > -50 and AU.metrics(st["snare"])["rms_db"] > -50


def test_breakforge_hits_land_on_the_grid():
    from synthesis.engines import breakforge as B
    e = S.create("breakforge", "steppers", params={"swing": 0.5}, seed=1)
    e.render(None, int(4 * 60 / 172 * SR) + 1, 172.0)        # one bar: every hit at a sixteenth
    steps = B.bar_steps(0, 1, e.p)
    assert steps and all(0 <= s < 16 for s, _, _ in steps)
    assert all(abs(s * 4 - round(s * 4)) < 1e-9 for s, _, _ in steps)    # quarter-sixteenths at most (stutters)


def test_breakforge_mutation_grows_through_the_phrase():
    from synthesis.engines import breakforge as B
    p = dict(S.presets("breakforge")["tearout"])
    tags = [len(B.phrase(i, 11, p)[1]) for i in range(4)]
    assert tags[-1] >= tags[0], tags
    base = B.phrase(0, 11, {**p, "intensity": 0.0, "chop": 0, "stutter": 0, "reverse": 0, "halftime": 0, "drop": 0,
                            "rolls": 0, "ghosts": 0})[0]
    pat = B.BREAKS[p["pattern"]]
    assert sorted(base) == sorted(pat) or len(base) == len(pat)
    assert B.phrase(2, 11, p) == B.phrase(2, 11, p) and B.phrase(2, 11, p) != B.phrase(2, 12, p)


def test_breakforge_midi_export():
    import mido
    from synthesis.engines import breakforge as B
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "break.mid"
        B.export_midi(path, bars=8, bpm=172.0, seed=4, params=S.presets("breakforge")["afterimage-rollers"])
        mf = mido.MidiFile(path)
        notes = [m for t in mf.tracks for m in t if m.type == "note_on" and m.velocity > 0]
        tempo = [m.tempo for t in mf.tracks for m in t if m.type == "set_tempo"]
        assert notes and all(m.channel == 9 for m in notes)
        assert tempo and abs(mido.tempo2bpm(tempo[0]) - 172.0) < 0.01
        assert {m.note for m in notes} <= set(B.NOTE.values())
        assert {36, 38} <= {m.note for m in notes}


def test_breakforge_drives_the_song_drums():
    import producer as PR
    from synthesis.engines import breakforge as B
    cfg = {"swing": 0.5, "_bpm": 172, "seed": 7, "breakforge": S.presets("breakforge")["afterimage-rollers"]}
    ev = PR.drum_bar("breakforge", {"break", "hat", "ride"}, False, 3, np.random.default_rng(0), cfg)
    assert ev
    kit = B.kit(cfg["breakforge"])
    names = {snd for _, snd, *_ in ev}
    assert names <= set(kit["sounds"]) | set(PR.GM), names
    ev2 = PR.drum_bar("breakforge", {"break", "hat", "ride"}, False, 3, np.random.default_rng(99), cfg)
    assert ev == ev2                                          # the seed in cfg decides, not the song's rng


def test_breakforge_voices_play_in_render_midi():
    from synthesis.engines import breakforge_voices as BV
    rng = np.random.default_rng(0)
    for name in ("kick", "snare", "ghost", "hat", "open_hat", "ride", "crash", "rim", "tom", "swell"):
        y = getattr(BV, name)(rng, 0.8)
        assert y.dtype == np.float32 and y.ndim == 1 and len(y) > 100 and np.isfinite(y).all(), name
        assert 0.1 < np.abs(y).max() <= 1.0 + 1e-6, name


# ---------------------------------------------------------------------- the engines' own mechanisms
def _peak_hz(y: np.ndarray, lo: float = 30.0) -> float:
    x = y.mean(1) * np.hanning(len(y))
    X = np.abs(np.fft.rfft(x))
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X[f < lo] = 0
    return float(f[X.argmax()])


def test_second_render_keeps_note_timing():
    from synthesis.engine_api import beat_events
    e = S.create("material", "new-marimba")
    e.render(beat_events([(0, 0.5, 60, 0.9)], 120.0), SR // 2)
    y = e.render(beat_events([(1, 0.5, 60, 0.9)], 120.0), SR)        # beat 1 = 0.5 s into the second render
    assert np.abs(y[: SR // 2 - 64]).max() < 0.05 and np.abs(y[SR // 2: SR // 2 + 2000]).max() > 0.1


def test_gravity_modes_come_from_the_physics():
    from synthesis.engines.gravity import mode_ratios
    n = 8
    chain = mode_ratios("chain", n, 0.0)
    k = np.arange(1, n + 1)
    assert np.allclose(chain, np.sin(k * np.pi / (2 * (n + 1))) / np.sin(np.pi / (2 * (n + 1))))
    assert np.isclose(mode_ratios("bar", 4, 0.0)[1], 25 / 9)            # free beam: (2k+1)^2
    ring = mode_ratios("ring", 12, 0.5)
    assert ring[0] != ring[1] and abs(ring[0] / ring[1] - 1) < 0.05    # degenerate pair split by the flaw
    slack = S.create("gravity", "slack-bass", params={"nonlinear": 1.0, "decay": 6.0})
    y = slack.render(note_events([{"start": 0, "end": 2.0, "pitch": 45, "vel": 1.0}]), 2 * SR)
    assert _peak_hz(y[: SR // 4]) > _peak_hz(y[SR:]) * 1.002             # tension bend: starts sharp, falls


def test_weather_lives_without_notes_and_condenses_at_them():
    e = S.create("weather", "monsoon-front", seed=2)
    y = e.render(None, 3 * SR)
    assert AU.metrics(y)["rms_db"] > -45                                   # the climate is audible on its own
    a, b = AU.spectrum(y[:SR]), AU.spectrum(y[2 * SR:])
    assert np.abs(np.log(a[1] + 1e-9) - np.log(b[1] + 1e-9)).mean() > 0.05  # and it changes
    f = S.create("weather", "aurora", seed=2, params={"condense": 1.0, "clarity": 1.0})
    z = f.render(note_events([{"start": 0, "end": 3, "pitch": 69, "vel": 1.0}]), 3 * SR)
    assert abs(_peak_hz(z[SR:], 200) / 440.0 - round(_peak_hz(z[SR:], 200) / 440.0)) < 0.03


def test_prismatic_listener_motion_makes_interference():
    ev = note_events([{"start": 0, "end": 3, "pitch": 60, "vel": 1.0}])
    still = S.create("prismatic", "still-water", seed=1).render(ev, 3 * SR)
    moving = S.create("prismatic", "doppler-swarm", seed=1).render(ev, 3 * SR)
    def wobble(y):
        env = np.sqrt((y[SR // 2: SR // 2 + 1024 * 80, 0].reshape(-1, 1024) ** 2).mean(1))
        return env.std() / (env.mean() + 1e-9)
    assert wobble(moving) > 2 * wobble(still)


def test_echo_hears_its_input_and_stays_bounded():
    noise = np.zeros((2 * SR, 2), np.float32)
    noise[: SR // 10] = np.random.default_rng(0).standard_normal((SR // 10, 2)) * 0.5
    e = S.create("echo", "input-eater", seed=1)
    y = e.render(None, 2 * SR, inp=noise)
    assert np.abs(y[SR // 2: SR]).max() > 0.01                         # echoes long after the input stopped
    wild = S.create("echo", "hungry-swarm", params={"hunger": 1.0, "feedback": 0.97, "skin": 4.0})
    z = wild.render(note_events([{"start": 0, "end": 0.2, "pitch": 50, "vel": 1.0}]), 8 * SR)
    assert np.isfinite(z).all() and np.abs(z).max() < 1.5


def test_oracle_analyses_a_wav_and_resynthesises_at_the_note():
    from scipy.io import wavfile
    t = np.arange(2 * SR) / SR
    src = 0.5 * np.sin(2 * np.pi * 220 * t) + 0.2 * np.sin(2 * np.pi * 440 * t)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "src.wav")
        wavfile.write(p, SR, (src * 30000).astype(np.int16))
        e = S.create("oracle", "transposed-instrument", assets={"source": p})
        info = e.describe_source()
        assert abs(info["median_f0"] - 220) < 8 and info["source"] == "src.wav", info
        y = e.render(note_events([{"start": 0, "end": 1.5, "pitch": 57, "vel": 1.0}]), 2 * SR)   # A3 = 220
        assert abs(_peak_hz(y[: int(1.4 * SR)]) - 220) < 6
    assert S.create("oracle").describe_source()["source"].startswith("synthetic")    # no file: still plays


def test_material_remembers_and_its_frozen_modes_do_not():
    from synthesis.engine_api import beat_events
    hit = beat_events([(0, 0.5, 60, 0.9)], 120.0)
    tails = {}
    for mem in ("wear", "frozen", "pristine"):
        e = S.create("material", "tiring-glass", params={"memory": mem, "age": 0.3})
        w0 = e.wear.copy()
        ys = [e.render(hit, SR // 2) for _ in range(10)]
        tails[mem] = [float(np.sqrt((y[2000:] ** 2).mean())) for y in (ys[0], ys[-1])]
        if mem != "wear":
            assert np.array_equal(e.wear, w0) and abs(tails[mem][1] / tails[mem][0] - 1) < 0.03, mem
        else:
            assert np.abs(e.wear - w0).sum() > 0.5 and e.memory_map()["strikes"] == 10
    assert tails["wear"][1] < tails["wear"][0] * 0.9                     # a worn instrument rings shorter


def test_fractal_hard_limits_and_self_similarity():
    from synthesis.engines.fractal import MAX_DEPTH, MAX_HITS, grow
    wild = {"cycle": 16.0, "depth": 99, "split": 1.0, "ratio": "3", "chaos": 0.0, "density": 1.0}
    for seed in range(4):
        leaves = grow(seed, 0, wild, 0.03125)
        assert len(leaves) <= MAX_HITS and max(d for _, _, d, _ in leaves) <= MAX_DEPTH
        assert min(L for _, L, _, _ in leaves) >= 0.03125 - 1e-9
    full = grow(1, 0, {"cycle": 4.0, "depth": 2, "split": 1.0, "ratio": "2", "chaos": 0.0, "density": 1.0}, 0.01)
    assert [s for s, *_ in full] == [0.0, 1.0, 2.0, 3.0]                # split everywhere: the regular grid
    e = S.create("fractal", "fractal-machine", params={"depth": 6, "min_cell": 0.03125, "decay": 2.0})
    y = e.render(note_events([{"start": 0, "end": 4, "pitch": 60, "vel": 1}]), 4 * SR, 174.0)
    assert np.isfinite(y).all() and np.abs(y).max() < 2.0 and e.diagnostics()["rt_factor"] < 0.6


def test_terrain_is_band_limited():
    f0 = 440.0 * 2 ** ((100 - 69) / 12)
    e = S.create("terrain", "mountain-growl", params={"radius": 4.0, "fold": 0.0, "drift": 0.0, "morph": 0.0})
    y = e.render(note_events([{"start": 0, "end": 1.0, "pitch": 100, "vel": 1}]), SR)[SR // 4: 3 * SR // 4]
    X = np.abs(np.fft.rfft(y.mean(1) * np.hanning(len(y)))) ** 2
    f = np.fft.rfftfreq(len(y), 1 / SR)
    harm = np.abs(f / f0 - np.round(f / f0)) * f0 < 25
    assert X[harm].sum() / X.sum() > 0.97                                 # energy sits on harmonics: no aliasing
    assert len(e.height_map(16)) == 16


def test_first_ramp_starts_from_the_patch():
    from synthesis.modulation import moves_lane
    mv = [{"bar": 2, "to_bar": 4, "set": {"synth.x": 1.0}}]
    assert moves_lane(mv, "synth.x") == [[8.0, 1.0]]                    # no start known: jump
    assert moves_lane(mv, "synth.x", start=0.2) == [[8.0, 0.2], [16.0, 1.0]]


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
