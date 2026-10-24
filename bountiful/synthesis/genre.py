"""A genre's [experimental_synthesis] table: which parts the Lab's engines may play, applied only when asked for.

    [experimental_synthesis]
    enabled = false                       # off: the genre renders exactly as it always has
    drums = "breakforge"                  # Breakforge writes and plays the drums (style + kit, one stem per drum)
    breakforge = { preset = "afterimage-rollers", tune = -1 }

    [experimental_synthesis.tracks.pad]   # a part played by an engine instead of its usual sound
    engine = "ghost"
    preset = "afterimage-pad"
    params = { memory = 14 }
    gain_db = -14                         # the renderer's usual track settings (gain_db, pan, sends, hp, duck, ...)

apply(g) is a no-op unless the table says enabled = true or the caller forces it (build.py --experimental), and
never when the experimental engines are switched off (synthesis.enabled()). The part's original sound stays on as
the track's fallback, so a song still renders if an engine cannot run.
"""
from __future__ import annotations

import copy

import synthesis as S

TRACK_KEYS = ("engine", "preset", "params", "seed", "automation", "modulation", "graph", "assets", "stereo")


def table(g: dict) -> dict:
    return g.get("experimental_synthesis") or {}


def wanted(g: dict, force: bool = False) -> bool:
    t = table(g)
    return bool(t) and (bool(t.get("enabled")) or force) and S.enabled()


def breakforge_params(spec: dict | None) -> dict:
    """{preset = ..., param = ...} -> Breakforge params (preset first, then the table's own values on top)."""
    spec = dict(spec or {})
    out = dict(S.presets("breakforge").get(spec.pop("preset", None), {}))
    out.update(spec)
    out.pop("generate", None)
    return out


def track(spec: dict, original: dict | None) -> dict:
    """One synthesis track for instruments.toml: the engine, then the renderer's settings, the old sound as fallback."""
    tr = {k: v for k, v in (original or {}).items() if k not in ("kind", "preset", "fn", "module", "variants", "layers")}
    tr.update({k: copy.deepcopy(v) for k, v in spec.items()})
    tr["kind"] = "synthesis"
    tr.setdefault("version", S.engine_class(spec["engine"]).VERSION if "engine" in spec else 1)
    if original and original.get("kind") != "synthesis":
        tr["fallback"] = dict(original)
    return tr


def apply(g: dict, force: bool = False) -> dict:
    """The genre with its experimental parts switched on (a new dict), or g itself when they are not wanted."""
    if not wanted(g, force):
        return g
    t = table(g)
    g = dict(g)
    if t.get("drums") == "breakforge":
        from synthesis.engines import breakforge
        g["drums"] = "breakforge"
        g["kit"] = "breakforge"
        g["breakforge"] = breakforge_params(t.get("breakforge"))
        g["_kit"] = breakforge.kit(g["breakforge"])
        if "swing" in g["breakforge"]:
            g["swing"] = g["breakforge"]["swing"]
    sounds = dict(g.get("sounds", {}))
    for name, spec in (t.get("tracks") or {}).items():
        if spec.get("engine") not in S.ENGINES and not spec.get("graph"):
            continue
        sounds[name] = track(spec, sounds.get(name))
    g["sounds"] = sounds
    g["_experimental"] = True
    return g
