"""AppImage updates: which GitHub release is picked, and the download that replaces the running AppImage.
No network: GitHub's answers are made up here.  python -I tests/test_updater.py
"""
import hashlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bountiful"))
import updater as U  # noqa: E402


def rel(tag, assets=("x86_64.AppImage",), draft=False, pre=False, body="notes"):
    names = [f"Bountiful-{tag[1:]}-{a}" for a in assets]
    return {"tag_name": tag, "draft": draft, "prerelease": pre, "body": body, "html_url": f"https://example/{tag}",
            "assets": [{"name": n, "browser_download_url": f"https://example/{n}", "size": 7} for n in names]}


def check_pick():
    releases = [rel("packs-v1", ()), rel("v0.2.0"), rel("v0.10.0", draft=True), rel("v0.9.0", pre=True),
                rel("v0.3.0", ("x86_64.AppImage", "x86_64.AppImage.sha256")), rel("v0.4.0", ("aarch64.AppImage",)),
                rel("v1.0", ())]
    best = U.latest_release(releases)
    assert best["tag"] == "v0.3.0" and best["sha256_url"].endswith(".sha256"), best
    assert U.latest_release([rel("packs-v1", ())]) is None
    # each platform picks its own download; a release without one is skipped
    both = [rel("v0.5.0", ("windows-x86_64-setup.exe", "macos-arm64.dmg")), rel("v0.6.0", ("macos-arm64.dmg",))]
    assert U.latest_release(both, "-windows-x86_64-setup.exe")["tag"] == "v0.5.0"
    assert U.latest_release(both, "-macos-arm64.dmg")["url"].endswith("0.6.0-macos-arm64.dmg")
    assert U.latest_release(both, "-x86_64.AppImage") is None
    assert U.vtuple("v0.10.0") > U.vtuple("0.9.9-3-gabc") > U.vtuple("garbage")


def check_status():
    version = U.version
    try:
        U.version = lambda: "0.2.0 abc1234 2026-11-19"
        st = U.check_release(releases=[rel("v0.3.0", body="- faster\n\n- prettier")])
        assert st["ok"] and st["behind"] == 1 and st["changes"] == ["- faster", "- prettier"], st
        st = U.check_release(releases=[rel("v0.2.0")])
        assert st["ok"] and not st["behind"] and "Up to date" in st["message"], st
    finally:
        U.version = version


def check_download():
    new = b"new appimage"
    served = {"https://example/app": new, "https://example/app.sha256": hashlib.sha256(new).hexdigest().encode() + b"  x\n"}
    get = U._get
    U._get = lambda url, timeout=30: io.BytesIO(served[url])
    try:
        with tempfile.TemporaryDirectory() as t:
            target = Path(t) / "Bountiful.AppImage"
            target.write_bytes(b"old")
            U.APPIMAGE = str(target)
            r = {"tag": "v0.3.0", "url": "https://example/app", "sha256_url": "https://example/app.sha256",
                 "size": len(new), "page": "https://example/page"}
            logs = []
            assert U.update_appimage(r, logs.append), logs
            assert target.read_bytes() == new and (target.stat().st_mode & 0o111 or sys.platform == "win32")  # no exec bit there
            served["https://example/app"] = b"tampered"
            assert not U.update_appimage(r, logs.append)
            assert target.read_bytes() == new and not (Path(t) / "Bountiful.AppImage.part").exists()
            assert "https://example/page" in logs[-1]
    finally:
        U._get, U.APPIMAGE = get, None



def check_bundle():
    """Windows/macOS: the new installer lands in Downloads and is opened, nothing is replaced in place."""
    new = b"new installer"
    served = {"https://example/Bountiful-0.3.0-macos-arm64.dmg": new,
              "https://example/x.sha256": hashlib.sha256(new).hexdigest().encode()}
    get, popen, platform = U._get, U.subprocess.Popen, U.sys.platform
    opened = []
    U._get = lambda url, timeout=30: io.BytesIO(served[url])
    U.subprocess.Popen = lambda cmd, **kw: opened.append(cmd)
    U.sys.platform = "darwin"
    try:
        with tempfile.TemporaryDirectory() as t:
            home = U.Path.home
            U.Path.home = staticmethod(lambda: Path(t))
            (Path(t) / "Downloads").mkdir()
            try:
                r = {"tag": "v0.3.0", "url": "https://example/Bountiful-0.3.0-macos-arm64.dmg",
                     "sha256_url": "https://example/x.sha256", "size": len(new), "page": "https://example/page"}
                logs = []
                assert U.update_bundle(r, logs.append), logs
                got = Path(t) / "Downloads" / "Bountiful-0.3.0-macos-arm64.dmg"
                assert got.read_bytes() == new and opened == [["open", str(got)]], (opened, logs)
            finally:
                U.Path.home = home
    finally:
        U._get, U.subprocess.Popen, U.sys.platform = get, popen, platform


if __name__ == "__main__":
    real = U.asset_suffix()
    assert real == "-x86_64.AppImage" or sys.platform != "linux", real
    U.asset_suffix = lambda: "-x86_64.AppImage"  # the made-up releases are AppImage ones, whatever runs the test
    check_pick()
    check_status()
    check_download()
    check_bundle()
    print("all pass")
