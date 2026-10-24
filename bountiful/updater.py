"""Bountiful's updater: fetch the newest version from the repository it was installed from, and reinstall.

The installed app (~/.local/lib/bountiful/app) is a git clone; its `origin` is where updates come from (the source
repo on this machine, or a GitHub repo: `git -C ~/.local/lib/bountiful/app remote set-url origin <url>`).
Updating is a fast-forward pull, then scripts/install.sh --refresh (dependencies, launcher, menu entry, icons).
Your music is not in the app folder, so an update never touches it.

    python bountiful/updater.py            check
    python bountiful/updater.py --update   update
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

from paths import CODE

LAUNCHER = os.path.expanduser("~/.local/bin/bountiful")


def git(*args, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(CODE), *args], capture_output=True, text=True, timeout=timeout)


def version() -> str:
    r = git("log", "-1", "--format=%h %cs %s")
    return r.stdout.strip() if r.returncode == 0 else "unknown (not a git checkout)"


def check(fetch: bool = True) -> dict:
    """{"ok", "behind", "ahead", "changes": [...], "remote", "branch", "message"}"""
    out = {"ok": False, "behind": 0, "ahead": 0, "changes": [], "remote": "", "branch": "", "message": ""}
    if not (CODE / ".git").exists():
        out["message"] = "This copy isn't a git checkout, so it can't update itself. Reinstall with scripts/install.sh."
        return out
    out["branch"] = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    up = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if up.returncode != 0:
        out["message"] = ("This is the source repository (no upstream to update from): "
                          "the installed app updates from it. Commit here, then click Update in the installed app.")
        return out
    remote = up.stdout.strip().split("/")[0]
    out["remote"] = git("remote", "get-url", remote).stdout.strip()
    if fetch:
        f = git("fetch", "--quiet", remote, timeout=120)
        if f.returncode != 0:
            out["message"] = f"Couldn't reach {out['remote']}: {f.stderr.strip()[:300]}"
            return out
    counts = git("rev-list", "--left-right", "--count", "HEAD...@{u}").stdout.split()
    out["ahead"], out["behind"] = (int(counts[0]), int(counts[1])) if len(counts) == 2 else (0, 0)
    out["changes"] = [ln for ln in git("log", "--format=%h %cs  %s", "HEAD..@{u}").stdout.splitlines() if ln]
    out["ok"] = True
    out["message"] = (f"{out['behind']} update{'s' if out['behind'] != 1 else ''} available from {out['remote']}"
                      if out["behind"] else f"Up to date ({version()})")
    return out


def update(log=print) -> bool:
    st = check()
    if not st["ok"]:
        log(st["message"])
        return False
    if not st["behind"]:
        log(st["message"])
        return True
    if git("status", "--porcelain", "--untracked-files=no").stdout.strip():
        log("The app folder has local edits; not updating over them. (git -C ~/.local/lib/bountiful/app status)")
        return False
    r = git("pull", "--ff-only", "--quiet", timeout=300)
    if r.returncode != 0:
        log(f"Update failed: {r.stderr.strip()[:500]}")
        return False
    log(f"Updated to {version()}")
    script = CODE / "scripts" / "install.sh"
    if script.exists():
        log("Refreshing dependencies, menu entry and icons ...")
        p = subprocess.Popen(["bash", str(script), "--refresh"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:
            log(line.rstrip())
        if p.wait() != 0:
            log("The refresh step failed (the new code is in place; run scripts/install.sh --refresh to retry).")
            return False
    return True


def restart():
    """Start the app again (a fresh process, so the new code loads) and leave this one."""
    exe = LAUNCHER if os.path.exists(LAUNCHER) else sys.executable
    args = [exe] if exe == LAUNCHER else [exe, str(CODE / "bountiful" / "daw" / "main.py")]
    subprocess.Popen(args, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true")
    a = ap.parse_args()
    if a.update:
        sys.exit(0 if update() else 1)
    st = check()
    print(st["message"])
    for c in st["changes"]:
        print("  " + c)


if __name__ == "__main__":
    main()
