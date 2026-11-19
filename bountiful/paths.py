"""Where things live. The code (this repo, or its installed clone in ~/.local/lib/bountiful/app) is separate from the
music: tracks, songs, albums, sessions, samples, friends and taste live in the data folder, so updating the app never
touches them.

  ~/.config/bountiful/config.toml
    data   = "~/Documents/Projects/bountiful-music"     # the music (default: the repo itself when run from source)
    engine = "~/Documents/Projects/intelligent-jungle"  # the renderer (default: the copy in renderer/)
Environment variables BOUNTIFUL_DATA and BOUNTIFUL_ENGINE override the file. PY runs the renderer: the engine's own
.venv when it has one, else the Python running the app.
"""
from __future__ import annotations

import os
import sys
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


BUNDLED = CODE / "renderer"


def _engine() -> Path:
    c = config()
    for cand in (os.environ.get("BOUNTIFUL_ENGINE"), c.get("engine"), BUNDLED):
        if cand and (_p(cand) / "studio" / "render_midi.py").exists():
            return _p(cand)
    return BUNDLED


def _python(engine: Path) -> Path:
    venv = engine / ".venv" / "bin" / "python"
    return venv if venv.exists() else Path(sys.executable)


DATA = _data()
ENGINE = _engine()
PY = _python(ENGINE)
TRACKS, SONGS, SESSIONS = DATA / "tracks", DATA / "songs", DATA / "sessions"
SAMPLES = DATA / "samples" if (DATA / "samples").is_dir() else CODE / "samples"   # not in git: it lives with the data


def _lmms_share() -> Path:   # same lookup as the renderer's engine/share.py
    for cand in (os.environ.get("LMMS_SHARE"), "/usr/share/lmms", "/usr/local/share/lmms", "/opt/lmms/share/lmms",
                 "~/.local/share/lmms"):
        if cand and (_p(cand) / "samples").is_dir():
            return _p(cand)
    return Path("/usr/share/lmms")


LMMS_SAMPLES = _lmms_share() / "samples"
FONT_DIRS = ("/usr/share/fonts", "/usr/local/share/fonts", "~/.local/share/fonts", "~/.fonts")


def font(name: str, size: int):
    """A PIL font by file name (e.g. "DejaVuSans-Bold.ttf") from the system font folders, else PIL's default."""
    from PIL import ImageFont
    for d in FONT_DIRS:
        hit = next(_p(d).rglob(name), None) if _p(d).is_dir() else None
        if hit:
            return ImageFont.truetype(str(hit), size)
    return ImageFont.load_default(size)


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
