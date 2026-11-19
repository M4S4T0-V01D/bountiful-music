"""Where things live. The code (this repo, or its installed clone in ~/.local/lib/bountiful/app) is separate from the
music: tracks, songs, albums, sessions, samples, friends and taste live in the data folder, so updating the app never
touches them.

  ~/.config/bountiful/config.toml
    data   = "~/Documents/Projects/bountiful-music"     # the music (default: the repo itself when run from source)
    engine = "~/Documents/Projects/intelligent-jungle"  # the renderer (studio/render_midi.py and its .venv)
Environment variables BOUNTIFUL_DATA and BOUNTIFUL_ENGINE override the file.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

CODE = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "bountiful"
CONFIG_FILE = CONFIG_DIR / "config.toml"


def config() -> dict:
    try:
        return tomllib.loads(CONFIG_FILE.read_text())
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return {}


def _p(s) -> Path:
    return Path(os.path.expanduser(str(s)))


def _data() -> Path:
    c = config()
    if os.environ.get("BOUNTIFUL_DATA"):
        return _p(os.environ["BOUNTIFUL_DATA"])
    if c.get("data"):
        return _p(c["data"])
    if (CODE / "tracks").exists():
        return CODE
    return Path.home() / "Music" / "Bountiful"


def _engine() -> Path:
    c = config()
    for cand in (os.environ.get("BOUNTIFUL_ENGINE"), c.get("engine"), CODE.parent / "intelligent-jungle",
                 Path.home() / "Documents" / "Projects" / "intelligent-jungle"):
        if cand and (_p(cand) / "studio" / "render_midi.py").exists():
            return _p(cand)
    return _p(c.get("engine") or CODE.parent / "intelligent-jungle")


DATA = _data()
ENGINE = _engine()
TRACKS, SONGS, SESSIONS = DATA / "tracks", DATA / "songs", DATA / "sessions"
SAMPLES = DATA / "samples" if (DATA / "samples").is_dir() else CODE / "samples"   # not in git: it lives with the data


def _toml_val(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def save_config(**changes):
    """Merge changes into the config file (one level of tables, e.g. lab={"last": ...})."""
    c = config()
    for k, v in changes.items():
        c[k] = {**c.get(k, {}), **v} if isinstance(v, dict) else v
    lines = [f"{k} = {_toml_val(v)}" for k, v in c.items() if not isinstance(v, dict)]
    for k, v in c.items():
        if isinstance(v, dict):
            lines += ["", f"[{k}]"] + [f"{a} = {_toml_val(b)}" for a, b in v.items()]
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text("\n".join(lines) + "\n")
