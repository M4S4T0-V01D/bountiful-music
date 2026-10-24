#!/usr/bin/env python3
"""Render a song whose instruments.toml has kind = "synthesis" tracks: the renderer (ENGINE/studio/render_midi.py)
does everything as usual, and this wrapper lends it the Lab's engines for those tracks. Same arguments as
render_midi.py, same outputs (stems, premaster, master, mp3, render_info.json). build.render() uses it only when a
song has synthesis tracks, so every other song renders by the very same command as before.

    python bountiful/synthesis/render.py song.mid instruments.toml --out exports [--stems stems] [--bars 5-8] ...
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import numpy as np  # noqa: E402

import paths  # noqa: E402
from synthesis import rendering as R  # noqa: E402

sys.path.insert(0, str(paths.ENGINE / "studio"))
import render_midi as RM  # noqa: E402

_orig_engine = RM.render_engine
_orig_process = RM.process
_orig_read = RM.read_midi
_SIDE: dict = {}
_CTX = {"bpm": 120.0, "seed": 1, "base": None}


def _read_midi(path):
    notes, bpm, tmap = _orig_read(path)
    _CTX["bpm"] = bpm
    return notes, bpm, tmap


def render_engine(notes, cfg, dirs, n, rng, t0):
    if not R.is_synthesis(cfg):
        return _orig_engine(notes, cfg, dirs, n, rng, t0)
    name = cfg.get("_name", "")
    try:
        y = R.render_part(cfg, notes, n, t0, _CTX["bpm"], R.track_seed(cfg, _CTX["seed"], name), _CTX["base"])
    except Exception as ex:                                   # the part still plays: on its fallback sound
        fb = cfg.get("fallback") or RM.DEFAULT_FALLBACK
        print(f"  {name or cfg.get('engine')}: synthesis engine failed ({ex}); using {fb['kind']}", flush=True)
        return _orig_engine(notes, {**fb, "transpose": cfg.get("transpose", 0)}, dirs, n, rng, t0)
    mid = ((y[:, 0] + y[:, 1]) * 0.5).astype(np.float32)
    side = ((y[:, 0] - y[:, 1]) * 0.5).astype(np.float32)
    if float(cfg.get("stereo", 1.0)) > 0 and np.abs(side).max() > 1e-6:
        _SIDE[id(cfg)] = side * float(cfg.get("stereo", 1.0))
    return mid


def process(name, x, cfg, auto, bpm, n, t0, sends, kick_times):
    y = _orig_process(name, x, cfg, auto, bpm, n, t0, sends, kick_times)
    side = _SIDE.pop(id(cfg), None)
    if side is not None and not cfg.get("mono"):
        dry = {k: v for k, v in cfg.items() if k not in ("sends", "pan", "chorus", "width", "leslie", "autopan", "mono")}
        s = _orig_process(name, side, dry, [a for a in auto if a.get("type") != "pan"], bpm, n, t0, {}, kick_times)[:, 0]
        y = y + np.stack([s, -s], 1)
    return y.astype(np.float32)


def install(seed: int, base: Path | None) -> None:
    _CTX["seed"], _CTX["base"] = seed, base
    RM.render_engine, RM.process, RM.read_midi = render_engine, process, _read_midi


def render(midi: Path, cfg: dict, base: Path, out: Path, stems: Path | None, bars=None, only=None, do_mp3=True,
           slug=None, log=print) -> dict:
    """render_midi.render() with the Lab's engines lent to the synthesis tracks."""
    for k, t in cfg.get("tracks", {}).items():
        if R.is_synthesis(t):
            t["_name"] = k
    install(int(cfg.get("seed", 1)), base)
    return RM.render(midi, cfg, base, out, stems, bars, only, do_mp3, slug, log=log)


def main():
    """The same command line as render_midi.py."""
    import argparse
    import tomllib
    ap = argparse.ArgumentParser()
    ap.add_argument("midi", type=Path)
    ap.add_argument("instruments", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--stems", type=Path)
    ap.add_argument("--no-stems", action="store_true")
    ap.add_argument("--no-mp3", action="store_true")
    ap.add_argument("--bars")
    ap.add_argument("--only")
    ap.add_argument("--name")
    a = ap.parse_args()
    cfg = tomllib.loads(a.instruments.read_text())
    base = Path(cfg.get("base_dir", a.instruments.resolve().parent))
    stems = None if a.no_stems else (a.stems or base / "stems")
    bars = tuple(int(x) for x in a.bars.split("-")) if a.bars else None
    render(a.midi, cfg, base, a.out or base / "exports", stems, bars, a.only.split(",") if a.only else None,
           not a.no_mp3, a.name, log=lambda m: print(m, flush=True))


if __name__ == "__main__":
    main()
