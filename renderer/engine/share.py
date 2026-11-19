"""Where LMMS is installed: its share folder (presets, samples) and its program. LMMS_SHARE and LMMS override the
lookup; when something is missing the error says what to install or set, instead of a bare file-not-found."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

if sys.platform == "win32":   # the LMMS installer's folder: lmms.exe, with its sounds in data/
    _PF = [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
    _SHARES = tuple(str(Path(d) / sub / "data") for d in _PF if d for sub in ("LMMS", "Programs/LMMS"))
    _BINS = tuple(str(Path(d).parent / "lmms.exe") for d in _SHARES)
elif sys.platform == "darwin":
    _SHARES = ("/Applications/LMMS.app/Contents/share/lmms", "~/Applications/LMMS.app/Contents/share/lmms")
    _BINS = ("/Applications/LMMS.app/Contents/MacOS/lmms", "~/Applications/LMMS.app/Contents/MacOS/lmms")
else:
    _SHARES = ("/usr/share/lmms", "/usr/local/share/lmms", "/opt/lmms/share/lmms", "~/.local/share/lmms")
    _BINS = ()


def lmms_share() -> Path:
    for cand in (os.environ.get("LMMS_SHARE"), *_SHARES):
        if cand and (Path(os.path.expanduser(cand)) / "samples").is_dir():
            return Path(os.path.expanduser(cand))
    return Path(_SHARES[0])   # absent: sample() and preset lookups say so when used


SHARE = lmms_share()
SAMPLES = SHARE / "samples"
PRESETS = SHARE / "presets"


def sample(rel) -> Path:
    """A sample by absolute path or by its path inside LMMS's sample library."""
    p = Path(rel)
    if not p.is_absolute():
        p = SAMPLES / rel
    if not p.exists():
        if not SAMPLES.is_dir():
            raise FileNotFoundError(f"sample {rel}: LMMS's sample library isn't installed "
                                    f"(looked in {', '.join(_SHARES)}); install LMMS or set LMMS_SHARE")
        raise FileNotFoundError(f"sample {rel}: not found at {p}")
    return p


def find_lmms() -> str | None:
    """$LMMS, lmms on PATH, or where the Windows / macOS installers put it."""
    if os.environ.get("LMMS"):
        return os.environ["LMMS"] if Path(os.environ["LMMS"]).exists() else None
    return shutil.which("lmms") or next((os.path.expanduser(b) for b in _BINS if Path(os.path.expanduser(b)).exists()), None)


def niced(cmd: list, n: int = 15) -> list:
    """cmd at a lower priority where `nice` exists (not on Windows)."""
    return ["nice", "-n", str(n), *cmd] if shutil.which("nice") else cmd


def lmms_bin() -> str:
    exe = find_lmms()
    if not exe:
        raise RuntimeError("LMMS isn't installed (no lmms on PATH): install it from lmms.io or your package manager, "
                           "or set LMMS to the program")
    return exe
