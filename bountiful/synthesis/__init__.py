"""Bountiful's Experimental Synthesis Lab: eleven engines that are instruments with memory, physics and weather,
not note-at-a-time voices. Each is a stateful block renderer with one API (engine_api.Engine): a parameter schema,
MIDI events, tempo, seed, automation, modulation, patch, snapshot / restore / reset, CPU diagnostics.

  ghost        Ghost Engine      remembers recent pitches, levels and spectral residue; freeze, capture, restore
  gravity      Gravity           mass-spring chains, resonator and membrane networks (normal modes, tension)
  weather      Spectral Weather  a pressure field across the spectrum: wind, humidity, storms
  breakforge   Breakforge        procedural drums and a mutating breakbeat generator (170-174 BPM jungle)
  phase_garden Phase Garden      Kuramoto-coupled oscillators drifting in and out of sync
  prismatic    Prismatic         interference: sources and a moving listener, path lengths and dispersion
  echo         Echo Organism     a feedback graph of delays and resonators that keeps itself alive, bounded
  oracle       Oracle            analyses a local WAV (envelope, pitch, onsets, partials) and resynthesises it
  material     Material Memory   a struck material that wears, fatigues and recovers (or stays as it is)
  fractal      Fractal Rhythm    recursive subdivision of the beat, hard-limited, retriggering held notes
  terrain      Terrain           a deformable surface traversed by an orbit (wave terrain synthesis)

    import synthesis as S
    e = S.create("ghost", preset="afterimage-pad", seed=7)
    S.engines()          -> ids          S.describe("ghost") -> schema, presets, caps

Off switch: BOUNTIFUL_EXPERIMENTAL=0 (or config experimental_synthesis = false) makes enabled() false; songs then
render exactly as before, with their [experimental_synthesis] tables ignored.
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

from synthesis.engine_api import BLOCK, SR, Engine, Param, beat_events, note_events  # noqa: F401

ENGINES = ("ghost", "gravity", "weather", "breakforge", "phase_garden", "prismatic", "echo", "oracle", "material",
           "fractal", "terrain")
HERE = Path(__file__).resolve().parent


def enabled() -> bool:
    env = os.environ.get("BOUNTIFUL_EXPERIMENTAL")
    if env is not None:
        return env.strip().lower() not in ("0", "false", "no", "off", "")
    try:
        import paths
        cfg = paths.config() if hasattr(paths, "config") else {}
        return bool(cfg.get("experimental_synthesis", True))
    except Exception:
        return True


def engine_class(eid: str) -> type[Engine]:
    if eid not in ENGINES:
        raise KeyError(f"unknown engine {eid!r} (have {', '.join(ENGINES)})")
    cls = importlib.import_module(f"synthesis.engines.{eid}").ENGINE
    globals()["engines"] = _engines    # importing the subpackage rebinds this name to it; keep the function
    return cls


def engines() -> tuple:
    return ENGINES


_engines = engines


def describe(eid: str) -> dict:
    return engine_class(eid).describe()


def presets(eid: str) -> dict:
    """Built-in presets, then the user's saved ones (<data>/synthesis/presets/<engine>/*.json) on top."""
    out = dict(engine_class(eid).PRESETS)
    out.update(importlib.import_module("synthesis.patches").user_presets(eid))
    return out


def create(eid: str, preset: str | None = None, params: dict | None = None, seed: int = 0, sr: int = SR,
           assets: dict | None = None) -> Engine:
    cls = engine_class(eid)
    p = {}
    if preset:
        all_ = presets(eid)
        if preset not in all_:
            raise KeyError(f"{eid} has no preset {preset!r} (have {', '.join(sorted(all_))})")
        p.update(all_[preset])
    p.update(params or {})
    return cls(params=p, seed=seed, sr=sr, assets=assets)


def from_patch(patch: dict, sr: int = SR) -> Engine:
    """A patch from any version: unknown params are dropped, missing ones take defaults (engine_api clamps)."""
    return engine_class(patch["engine"]).from_patch(patch, sr)


def dumps(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True)
