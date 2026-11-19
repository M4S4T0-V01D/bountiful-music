"""What Bountiful needs on this computer, what is there, and what to do about what isn't. The first-run setup
(daw/setup.py) shows this; need() is the guard features call before they start.

  python bountiful/setup_check.py      # print the report
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import packs  # noqa: E402
import paths  # noqa: E402

# tool -> (what it's for, needed for the basics?)
TOOLS = {
    "lmms": ("the LMMS instruments most songs are played on, and rendering", True),
    "fluidsynth": ("the General MIDI voices, and hearing them in the sound picker", True),
    "node": ("writing new songs from a Bounty (the composer runs in Node)", True),
    "lame": ("exporting MP3s (WAV export works without it)", False),
}
PACKAGES = {   # package manager -> install command prefix, and package names that differ from the tool's
    "pacman": ("sudo pacman -S", {"node": "nodejs"}),
    "apt": ("sudo apt install", {"node": "nodejs"}),
    "dnf": ("sudo dnf install", {"node": "nodejs"}),
    "zypper": ("sudo zypper install", {"node": "nodejs"}),
    "brew": ("brew install", {}),
}


def which(tool: str) -> str | None:
    if tool == "lmms" and os.environ.get("LMMS"):
        return os.environ["LMMS"] if Path(os.environ["LMMS"]).exists() else None
    return shutil.which(tool)


def version(exe: str) -> str:
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
        line = (r.stdout or r.stderr).strip().splitlines()
        return line[0][:60] if line else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def install_hint(missing: list[str]) -> str:
    for pm, (cmd, names) in PACKAGES.items():
        if shutil.which(pm):
            return f"{cmd} {' '.join(names.get(t, t) for t in missing)}"
    return "install " + ", ".join(missing) + " from your package manager"


def pack_state(name: str, root: Path | None = None) -> str:
    """"installed" (by the pack tool), "present" (the files are there, e.g. from a source checkout) or "missing"."""
    roots = [root] if root else [packs.dest(), paths.SAMPLES]   # where packs install, and where the app looks now
    if any(name in packs.installed(r) for r in roots):
        return "installed"
    present = any(all((r / p).exists() for p in packs.PACKS[name]["paths"]) for r in roots)
    return "present" if present else "missing"


def data_ok() -> tuple[bool, str]:
    d = paths.DATA
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".bountiful-write-test"
        probe.write_text("")
        probe.unlink()
        return True, str(d)
    except OSError as e:
        return False, f"{d}: {e.strerror or e}"


def report() -> dict:
    tools = {}
    for t, (why, basic) in TOOLS.items():
        exe = which(t)
        tools[t] = {"ok": bool(exe), "why": why, "basic": basic, "path": exe or "", "version": version(exe) if exe else ""}
    ok, where = data_ok()
    pk = {n: pack_state(n) for n in packs.PACKS}
    missing = [t for t, v in tools.items() if not v["ok"]]
    return {"data": {"ok": ok, "where": where}, "tools": tools, "packs": pk,
            "lmms_share": str(paths.LMMS_SAMPLES.parent) if paths.LMMS_SAMPLES.is_dir() else "",
            "missing": missing, "hint": install_hint(missing) if missing else "",
            "ready": ok and pk["starter"] != "missing" and all(v["ok"] for v in tools.values() if v["basic"])}


class Missing(RuntimeError):
    pass


def need(*what: str):
    """Raise Missing with a plain message when a tool or pack a feature needs isn't there."""
    gone = [w for w in what if (w in packs.PACKS and pack_state(w) == "missing") or (w in TOOLS and not which(w))]
    if gone:
        parts = [f"the {packs.PACKS[w]['title'].lower()} pack" if w in packs.PACKS else w for w in gone]
        tools = [w for w in gone if w in TOOLS]
        fix = f" Install with: {install_hint(tools)}." if tools else ""
        raise Missing(f"This needs {', '.join(parts)}, which isn't on this computer.{fix} Settings → Setup shows what's missing.")


def main() -> int:
    r = report()
    print(f"music folder  {'ok ' if r['data']['ok'] else 'NO '} {r['data']['where']}")
    for n, st in r["packs"].items():
        print(f"pack {n:8} {st:9} {packs.PACKS[n]['title']}")
    for t, v in r["tools"].items():
        print(f"{t:13} {'ok ' if v['ok'] else 'NO '} {v['version'] or v['why']}")
    print(f"LMMS sounds   {r['lmms_share'] or 'not found (set LMMS_SHARE)'}")
    if r["hint"]:
        print("to install:", r["hint"])
    print("ready" if r["ready"] else "not ready")
    return 0 if r["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
