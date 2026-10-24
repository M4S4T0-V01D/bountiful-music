#!/usr/bin/env python3
"""Checks for Bountiful's own synths (bountiful/synths). Run: $PY tests/test_synths.py"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bountiful"))
import synths  # noqa: E402
from synths import core as C  # noqa: E402

STILL = {"vibrato": 0, "arp": 0, "pitch": 0, "sweep": 0, "tuning": "exact"}


def every():
    for s in synths.SYNTHS:
        for name in synths.presets(s):
            yield s, name, synths.preset(s, name)


def render(s, p, midi=60, dur=0.5, seed=1, vel=1.0):
    return synths.get(s).note(midi, vel, dur, p, np.random.default_rng(seed))


def test_every_preset_renders_clean():
    for s, name, p in every():
        for midi in (36, 60, 84):
            y = render(s, p, midi)
            assert y.dtype == np.float32 and y.ndim == 1, (s, name)
            assert np.isfinite(y).all(), (s, name, midi)
            assert np.abs(y).max() <= 0.95, (s, name, midi, float(np.abs(y).max()))
            assert np.abs(y).max() > 0.01, (s, name, midi, "silent")
            assert abs(y[0]) < 0.05 and abs(y[-1]) < 0.01, (s, name, midi, "click at an edge")


def test_deterministic():
    for s, name, p in every():
        assert np.array_equal(render(s, p, seed=3), render(s, p, seed=3)), (s, name)


def test_length_follows_duration():
    for s, name, p in every():
        if p.get("fixed_frames") or getattr(synths.get(s), "ONE_SHOT", False):   # one-shots ring as long as they ring
            continue
        short, long = len(render(s, p, dur=0.2)), len(render(s, p, dur=1.0))
        assert long - short >= 0.75 * C.SR, (s, name, short, long)
        assert short < 0.2 * C.SR + 4 * C.SR, (s, name, short)


def test_through_the_renderer_entry_point():
    spec = importlib.util.spec_from_file_location("bountiful_voice", synths.VOICE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    t = synths.track("gb", "lead", level=0.3)
    assert t["kind"] == "pyvoice" and Path(t["preset"]["module"]).exists()
    y = mod.note(64, 0.9, 0.4, t["preset"], np.random.default_rng(0), from_midi=60)
    assert np.isfinite(y).all() and 0.01 < np.abs(y).max() <= 0.95


def _below_f0_db(y, f0):
    y = y[int(0.05 * C.SR):int(0.45 * C.SR)].astype(float)
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    f = np.fft.rfftfreq(len(y), 1 / C.SR)
    low = spec[(f > 40) & (f < 0.9 * f0)].sum()
    return 10 * np.log10(low / spec.sum() + 1e-20)


def test_no_aliasing_on_high_notes():
    waves = [("nes", {"channel": "pulse", "duty": d, "vol": 15}) for d in range(4)]
    waves += [("nes", {"channel": "triangle"}), ("gb", {"channel": "pulse", "duty": 1, "env": [15, 0, 0]})]
    waves += [("gb", {"channel": "wave", "wave": w}) for w in synths.get("gb").WAVES]
    waves += [("sid", {"wave": w, "attack": 0, "sustain": 15}) for w in ("tri", "saw", "pulse")]
    waves += [("va", {"osc": w, "s": 1.0}) for w in ("saw", "square", "tri")]
    waves += [("ensemble", {"kind": "strings", "voices": 1, "vibrato": 0, "detune": 0, "bow": 0, "cutoff": 20000})]
    for midi in (96, 103):
        for s, p in waves:
            p = {**p, **STILL, "level": 0.5}
            db = _below_f0_db(render(s, p, midi), C.hz(midi))
            assert db < -40, (s, p, midi, round(db, 1))


def test_one_shots_damp_and_choke():
    vib = synths.preset("modal", "vibraphone")
    assert len(render("modal", vib, dur=0.2)) < len(render("modal", vib, dur=1.5))
    hat = synths.preset("drums", "hat-open")
    assert len(render("drums", hat, dur=0.05)) < len(render("drums", hat, dur=0.4))
    kick = synths.preset("drums", "kick-808")
    assert len(render("drums", kick, dur=0.05)) == len(render("drums", kick, dur=2.0))


def test_toms_follow_the_note():
    p = synths.preset("drums", "tom-mid")
    lo, hi = render("drums", p, 55), render("drums", p, 67)
    zc = lambda y: np.count_nonzero(np.diff(np.sign(y[2000:12000])))     # noqa: E731
    assert zc(hi) > 1.5 * zc(lo)


def test_hardware_tuning_snaps():
    gb = synths.get("gb")
    f = gb._snap(np.array([60.0, 96.0]), 131072.0)
    x = 2048 - 131072.0 / f
    assert np.allclose(x, np.round(x))
    assert abs(1200 * np.log2(f[0] / C.hz(60))) < 5


def test_macro_semantics():
    m = C.macro({"seq": [1, 2, 3], "loop": 1, "release": 3}, 8, 5)
    assert list(m[:5]) == [1, 2, 3, 2, 3]
    assert C.macro(7, 4, 2).tolist() == [7, 7, 7, 7]


def test_fast_enough():
    for s, name, p in every():
        t = time.perf_counter()
        render(s, p, 60, 1.0)
        ms = (time.perf_counter() - t) * 1000
        assert ms < 150, (s, name, round(ms))


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
