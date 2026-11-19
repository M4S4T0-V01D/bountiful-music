"""Bountiful's updater: fetch the newest version from the repository it was installed from, and reinstall.

The installed app (~/.local/lib/bountiful/app) is a git clone; its `origin` is where updates come from (the source
repo on this machine, or a GitHub repo: `git -C ~/.local/lib/bountiful/app remote set-url origin <url>`).
Updating is a fast-forward pull, then scripts/install.sh --refresh (dependencies, launcher, menu entry, icons).
Your music is not in the app folder, so an update never touches it.

The AppImage (scripts/appimage.sh) can't pull: it asks GitHub for the newest release tagged vX.Y.Z, and updating
downloads that release's AppImage, checks it against the .sha256 published beside it, and puts it in place of the
running one (which keeps running until it's restarted).

    python bountiful/updater.py            check
    python bountiful/updater.py --update   update
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from paths import APPIMAGE, CODE, REPO

VERSION_FILE = CODE / "bountiful" / "VERSION"   # written by scripts/appimage.sh: "<version> <commit> <date>"

LAUNCHER = os.path.expanduser("~/.local/bin/bountiful")


def git(*args, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(CODE), *args], capture_output=True, text=True, timeout=timeout)


def version() -> str:
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    r = git("log", "-1", "--format=%h %cs %s")
    return r.stdout.strip() if r.returncode == 0 else "unknown (not a git checkout)"


def vtuple(v: str) -> tuple:
    """"v1.2.3" or "1.2.3-dev" -> (1, 2, 3); anything else -> ()"""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", v.strip())
    return tuple(int(x) for x in m.groups()) if m else ()


def _get(url: str, timeout: float = 30):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Bountiful"})
    return urllib.request.urlopen(req, timeout=timeout)


def latest_release(releases: list | None = None) -> dict | None:
    """The newest published vX.Y.Z release that has an x86_64 AppImage: {tag, notes, page, url, sha256_url, size}."""
    if releases is None:
        with _get(f"https://api.github.com/repos/{REPO}/releases?per_page=30") as r:
            releases = json.load(r)
    best = None
    for rel in releases:
        if rel.get("draft") or rel.get("prerelease") or not re.fullmatch(r"v\d+\.\d+\.\d+", rel.get("tag_name", "")):
            continue
        assets = {a["name"]: a for a in rel.get("assets", [])}
        app = next((a for n, a in assets.items() if n.endswith("-x86_64.AppImage")), None)
        if app and (best is None or vtuple(rel["tag_name"]) > vtuple(best["tag"])):
            sha = assets.get(app["name"] + ".sha256")
            best = {"tag": rel["tag_name"], "notes": rel.get("body") or "", "page": rel.get("html_url", ""),
                    "url": app["browser_download_url"], "size": app.get("size", 0),
                    "sha256_url": sha["browser_download_url"] if sha else ""}
    return best


def check_release(fetch: bool = True, releases: list | None = None) -> dict:
    out = {"ok": False, "behind": 0, "ahead": 0, "changes": [], "remote": f"github.com/{REPO}", "branch": "",
           "message": "", "release": None}
    if not fetch:
        out["message"] = f"Bountiful {version()}"
        return out
    try:
        rel = latest_release(releases)
    except (OSError, ValueError) as e:
        out["message"] = f"Couldn't reach GitHub: {e}"
        return out
    out["ok"] = True
    mine = version().split()[0]
    if rel and vtuple(rel["tag"]) > vtuple(mine):
        out["behind"], out["release"] = 1, rel
        out["changes"] = [ln.strip() for ln in rel["notes"].splitlines() if ln.strip()][:25]
        out["message"] = f"Bountiful {rel['tag']} is out (you have {mine})"
    else:
        out["message"] = f"Up to date ({version()})"
    return out


def update_appimage(rel: dict, log=print, progress=None) -> bool:
    target = Path(APPIMAGE)
    part = target.with_name(target.name + ".part")
    try:
        want = ""
        if rel["sha256_url"]:
            with _get(rel["sha256_url"]) as r:
                want = r.read().decode().split()[0].lower()
        log(f"downloading {rel['url']} ({rel['size'] / 1e6:.0f} MB)")
        h = hashlib.sha256()
        with _get(rel["url"], timeout=60) as r, open(part, "wb") as fh:
            done = 0
            while chunk := r.read(1 << 20):
                fh.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, rel["size"])
        if want and h.hexdigest() != want:
            raise ValueError("the download doesn't match its published checksum")
        part.chmod(0o755)
        os.replace(part, target)   # the running copy is mounted already, so it keeps working until the restart
    except (OSError, ValueError) as e:
        part.unlink(missing_ok=True)
        log(f"Update failed: {e}. Get it from {rel['page']}")
        return False
    log(f"Updated to {rel['tag']}: restart to use it")
    return True


def check(fetch: bool = True) -> dict:
    """{"ok", "behind", "ahead", "changes": [...], "remote", "branch", "message"}"""
    if APPIMAGE:
        return check_release(fetch)
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
    if APPIMAGE and st["ok"] and st["behind"]:
        return update_appimage(st["release"], log)
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
    if APPIMAGE:
        subprocess.Popen([APPIMAGE], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
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
