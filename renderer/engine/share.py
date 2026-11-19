"""Where LMMS is installed: its share folder (presets, samples) and its program. LMMS_SHARE and LMMS override the
lookup; when something is missing the error says what to install or set, instead of a bare file-not-found."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

_SHARES = ("/usr/share/lmms", "/usr/local/share/lmms", "/opt/lmms/share/lmms", "~/.local/share/lmms")


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


def lmms_bin() -> str:
    exe = os.environ.get("LMMS") or shutil.which("lmms")
    if not exe:
        raise RuntimeError("LMMS isn't installed (no lmms on PATH): install it from lmms.io or your package manager, "
                           "or set LMMS to the program")
    return exe
