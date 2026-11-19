"""Sound packs: build is reproducible, install restores the WAVs (float ones within 24-bit), keeps what's there,
and refuses damaged or unsafe archives.  python -I tests/test_packs.py"""
import io
import sys
import tarfile
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bountiful"))
import packs  # noqa: E402


def check():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        src = t / "src"
        (src / "kit").mkdir(parents=True)
        rng = np.random.default_rng(1)
        sf.write(src / "kit/a.wav", rng.uniform(-0.9, 0.9, (800, 2)), 44100, subtype="PCM_24")
        sf.write(src / "kit/b.wav", rng.uniform(-1, 1, 500), 44100, subtype="PCM_16")
        loud = rng.uniform(-1.6, 1.6, 600).astype("float32")
        sf.write(src / "kit/c.wav", loud, 44100, subtype="FLOAT")
        (src / "kit/LICENSE.txt").write_text("free")
        packs.PACKS["t"] = {"title": "T", "about": "test", "paths": ["kit"], "credits": ["us"]}
        packs.MANIFEST = t / "packs.json"

        e = packs.build("t", t / "out", src, log=lambda *a: None)
        assert packs.build("t", t / "out2", src, log=lambda *a: None)["sha256"] == e["sha256"], "not reproducible"
        assert e["float"] == {"kit/c.wav": 1} and e["files"] == 4
        packs.MANIFEST.write_text(packs.json.dumps({"t": e}))
        arc = t / "out" / e["file"]

        root = t / "data"
        assert packs.install("t", arc, root, log=lambda *a: None) == 5   # 4 files + credits
        for n in ("a", "b"):
            assert (sf.read(src / f"kit/{n}.wav")[0] == sf.read(root / f"kit/{n}.wav")[0]).all(), n
        c, _ = sf.read(root / "kit/c.wav", dtype="float32")
        assert sf.info(str(root / "kit/c.wav")).subtype == "FLOAT" and np.abs(c - loud).max() < 2e-7
        assert (root / "kit/LICENSE.txt").read_text() == "free" and "t" in packs.installed(root)

        (root / "kit/LICENSE.txt").write_text("mine")
        packs.install("t", arc, root, log=lambda *a: None)
        assert (root / "kit/LICENSE.txt").read_text() == "mine", "overwrote a file that was there"

        bad = t / "bad.tar.gz"
        bad.write_bytes(arc.read_bytes()[:-10] + b"0123456789")
        try:
            packs.install("t", bad, t / "d2", log=lambda *a: None)
            raise AssertionError("damaged archive accepted")
        except ValueError as err:
            assert "checksum" in str(err)

        evil = t / "evil.tar.gz"
        with tarfile.open(evil, "w:gz") as tar:
            ti = tarfile.TarInfo("../escape.txt")
            ti.size = 2
            tar.addfile(ti, io.BytesIO(b"hi"))
        packs.MANIFEST.write_text(packs.json.dumps({"t": {**e, "sha256": packs.hashlib.sha256(evil.read_bytes()).hexdigest()}}))
        try:
            packs.install("t", evil, t / "d3", log=lambda *a: None)
            raise AssertionError("unsafe entry accepted")
        except ValueError as err:
            assert "unsafe" in str(err) and not (t / "escape.txt").exists()


def check_manifest():
    """The committed packs.json names every pack, with a checksum."""
    m = packs.manifest()
    for p in ("starter", "iowa"):
        assert len(m[p]["sha256"]) == 64 and m[p]["size"] > 0 and m[p]["file"] == f"bountiful-{p}.tar.gz", p


if __name__ == "__main__":
    check_manifest()
    check()
    print("all pass")
