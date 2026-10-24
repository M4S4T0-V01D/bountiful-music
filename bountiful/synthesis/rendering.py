"""The adapter between the Lab's engines and the song renderer: a whole part rendered by a stateful engine, handed
back in the renderer's own stem format, so mixing, sends, ducking, stems, mastering and export are untouched.

A synthesis track in instruments.toml (one table, the same file every song already has):

    [tracks.pad]
    kind = "synthesis"
    engine = "ghost"                    # an id from synthesis.ENGINES
    version = 1                         # the engine version it was made with (informational; patches load across versions)
    preset = "afterimage-pad"           # optional, then params on top
    params = { memory = 0.8 }
    seed = 7                            # optional; else derived from the song seed and the track name
    automation = { memory = [[0, 0.2], [64, 0.9]] }      # song beats -> value
    modulation = { seed = 0, routes = [{ source = { type = "lfo", rate_beats = 8 }, target = "freeze", amount = 0.2 }] }
    graph = { nodes = {...}, edges = [...], out = {...}, notes = ["a", "b"] }   # several engines for this part instead
    assets = { source = "/abs/or/relative.wav" }          # Oracle
    stereo = 1.0                        # how much of the engine's own stereo image survives the renderer's pan
    fallback = { kind = "pad", preset = "pad-night.json" }   # if the engine cannot run, the part still renders
    gain_db / pan / sends / hp / lp / duck / ...           # the renderer's usual track processing

render_part() returns (n, 2): mid goes through the renderer's process() as every track does; the side is processed
by the same chain (without sends and pan) and added back, so the engine's stereo survives in the same stem.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

import synthesis as S
from synthesis.engine_api import note_events
from synthesis.modulation import Matrix, moves_lane, stable_seed


def track_seed(cfg: dict, song_seed: int, name: str) -> int:
    return int(cfg["seed"]) if "seed" in cfg else stable_seed(song_seed, name, cfg.get("engine", "graph"))


def _start_value(cfg: dict, key: str):
    """A track's value for an engine parameter before any move: its params, its preset's, the default."""
    import synthesis as S
    eid = cfg.get("engine")
    if eid not in S.ENGINES:
        return None
    p = next((p for p in S.engine_class(eid).PARAMS if p.name == key), None)
    if p is None:
        return None
    pre = S.presets(eid).get(cfg.get("preset") or "", {})
    pre = pre.get("params", pre) if isinstance(pre, dict) else {}
    v = (cfg.get("params") or {}).get(key, pre.get(key, p.default))
    return p.clamp(v) if isinstance(v, (int, float)) else None


def automation_of(cfg: dict) -> dict:
    """The track's automation lanes, with Electronium engine moves (set = {"synth.<param>" = v}) merged in."""
    auto = {k: [list(p) for p in v] for k, v in cfg.get("automation", {}).items()}
    for m in cfg.get("moves", []):
        for key in m.get("set", {}):
            if key.startswith("synth."):
                auto.setdefault(key[6:], [])
    for key in list(auto):
        lane = moves_lane(cfg.get("moves", []), "synth." + key, start=_start_value(cfg, key))
        if lane:
            auto[key] = sorted(auto[key] + lane)
    return {k: v for k, v in auto.items() if v}


def resolve_assets(assets: dict, base: Path | None) -> dict:
    out = {}
    for k, v in (assets or {}).items():
        p = Path(str(v)).expanduser()
        if not p.is_absolute() and base is not None:
            p = base / p
        out[k] = str(p)
    return out


def render_part(cfg: dict, notes: list, n: int, t0: float, bpm: float, seed: int, base: Path | None = None) -> np.ndarray:
    """A whole part: notes in seconds (render_midi format), n samples starting at t0 seconds. Returns (n, 2)."""
    t0_beats = t0 * bpm / 60.0
    tr = int(cfg.get("transpose", 0))
    events = note_events([{**nt, "pitch": int(nt["pitch"]) + tr} for nt in notes] if tr else notes, t0)
    if cfg.get("graph"):
        from synthesis.routing import Graph
        g = Graph(cfg["graph"], seed)
        targets = cfg["graph"].get("notes") or list(g.nodes)
        return g.render({k: events for k in targets}, n, bpm, t0_beats)
    e = S.create(cfg["engine"], cfg.get("preset"), cfg.get("params"), seed, assets=resolve_assets(cfg.get("assets"), base))
    return e.render(events, n, bpm, automation_of(cfg), Matrix.from_json(cfg.get("modulation")), t0_beats)


def is_synthesis(cfg: dict) -> bool:
    return isinstance(cfg, dict) and cfg.get("kind") == "synthesis"


def uses_synthesis(instruments: dict) -> bool:
    return any(is_synthesis(t) for t in instruments.get("tracks", {}).values())
