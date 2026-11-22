"""First-run setup checks: pack states, missing programs and the advice given.  python -I tests/test_setup.py"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bountiful"))
import packs  # noqa: E402
import setup_check as SC  # noqa: E402


def check_packs():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        assert SC.pack_state("iowa", root) == "missing"
        for p in packs.PACKS["iowa"]["paths"]:
            (root / p).parent.mkdir(parents=True, exist_ok=True)
            (root / p).mkdir() if "." not in p else (root / p).write_text("")
        assert SC.pack_state("iowa", root) == "present"
        (root / ".packs").mkdir()
        (root / ".packs/iowa.json").write_text("{}")
        assert SC.pack_state("iowa", root) == "installed"


def check_missing():
    path, lmms = os.environ.get("PATH", ""), os.environ.pop("LMMS", None)
    os.environ["PATH"] = "/nonexistent"
    found, SC.find_library = SC.find_library, lambda name: None
    fluid, SC.find_fluidsynth = SC.find_fluidsynth, lambda: None
    try:
        r = SC.report()
        assert not r["ready"] and set(r["missing"]) == set(SC.TOOLS)
        if sys.platform == "win32":
            assert r["hint"].startswith("download fluidsynth from https://github.com/FluidSynth"), r["hint"]
        else:
            assert r["hint"] == f"install {', '.join(SC.TOOLS)} from your package manager", r["hint"]
        try:
            SC.need("fluidsynth")
            raise AssertionError("need() let a missing program through")
        except SC.Missing as e:
            assert "fluidsynth" in str(e) and "Setup" in str(e)
    finally:
        os.environ["PATH"] = path
        SC.find_library, SC.find_fluidsynth = found, fluid
        if lmms:
            os.environ["LMMS"] = lmms
    if sys.platform == "win32":   # (the fake package managers below are shell scripts)
        return
    with tempfile.TemporaryDirectory() as t:   # a package manager on PATH gets its own command and names
        (Path(t) / "apt").write_text("#!/bin/sh\n")
        (Path(t) / "apt").chmod(0o755)
        os.environ["PATH"] = t
        platform = sys.platform
        try:
            sys.platform = "linux"
            assert SC.install_hint(["node", "lame", "portaudio"]) == "sudo apt install nodejs lame libportaudio2"
            sys.platform = "win32"
            assert SC.install_hint(["node"]) == "download node from https://nodejs.org"
            (Path(t) / "brew").write_text("#!/bin/sh\n")
            (Path(t) / "brew").chmod(0o755)
            sys.platform = "darwin"
            assert SC.install_hint(["lmms", "node"]) == "brew install node && brew install --cask lmms"
        finally:
            os.environ["PATH"], sys.platform = path, platform


def check_optional():   # LMMS is never needed for the basics; Node and LAME only without the built-in composer / encoder
    assert not SC.TOOLS["lmms"][1]
    assert ("node" in SC.TOOLS) != SC.composer.available()
    assert ("lame" in SC.TOOLS) != SC._mp3_built_in()


if __name__ == "__main__":
    check_packs()
    check_optional()
    check_missing()
    print("all pass")
