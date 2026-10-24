"""Patches on disk: the Lab saves a patch as JSON; user presets live in <data>/synthesis/presets/<engine>/<name>.json.

A patch: {"format": "bountiful-synthesis-patch", "engine": id, "version": n, "params": {...}, "seed": n, "name"?}
Patches from other engine versions load: unknown params are dropped, missing ones take the engine's defaults.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

FORMAT = "bountiful-synthesis-patch"


def root() -> Path:
    import paths
    return paths.DATA / "synthesis" / "presets"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "patch"


def save_patch(patch: dict, path: Path, name: str | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    d = {"format": FORMAT, **patch}
    if name:
        d["name"] = name
    path.write_text(json.dumps(d, indent=1, sort_keys=True))
    return path


def load_patch(path: Path) -> dict:
    d = json.loads(Path(path).read_text())
    if d.get("format", FORMAT) != FORMAT or "engine" not in d:
        raise ValueError(f"{path} is not a Bountiful synthesis patch")
    return d


def save_user_preset(patch: dict, name: str) -> Path:
    return save_patch(patch, root() / patch["engine"] / f"{_slug(name)}.json", name)


def user_presets(engine: str) -> dict:
    d = root() / engine
    out = {}
    if d.is_dir():
        for f in sorted(d.glob("*.json")):
            try:
                out[f.stem] = load_patch(f).get("params", {})
            except (ValueError, json.JSONDecodeError):
                continue
    return out
