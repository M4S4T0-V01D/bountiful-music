"""Sound packs: the shippable parts of samples/ (docs/sample-audit.md), as archives on the GitHub release
packs-v1, installed into the data folder's samples/.

  packs.py list                         # what's installed
  packs.py build [pack ...] [--out D]   # make the archives from samples/ and record their checksums in packs.json
  packs.py install pack [--from FILE]   # download (or take FILE), check the checksum, unpack

WAVs travel as lossless FLAC (`x.wav.flac`) and are turned back into WAVs on install. FLAC has no float
format, so float WAVs (the Iowa notes) go as 24-bit, scaled by a power of two when they peak at 1 or more;
packs.json keeps that exponent and install undoes it. packs.json is committed, so a download is checked
against a checksum the app already has, not one that came with it.
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

REPO = paths.REPO
RELEASE = "packs-v1"
URL = f"https://github.com/{REPO}/releases/download/{RELEASE}/"
MANIFEST = Path(__file__).resolve().parent / "packs.json"

PACKS = {
    "starter": {
        "title": "Starter sounds",
        "about": "General MIDI voices, drum machines, pixel kits, lofi and phonk one-shots, and our own breaks",
        "paths": ["sf2", "drummachines", "pixel", "lofi", "phonk", "breaks/clizzy", "breaks/haze174", "breaks/velvet162"],
        "credits": [
            "sf2/GeneralUser-GS.sf2: GeneralUser GS by S. Christian Collins, licence in sf2/LICENSE.txt",
            "drummachines/: rendered from the DrumSynth patches that ship with LMMS (GPL-2), lmms.io",
            "pixel/, lofi/, phonk/, breaks/: made for Bountiful by M4S4T0",
        ],
    },
    "iowa": {
        "title": "Iowa instruments",
        "about": "Alto sax, trumpet, vibraphone, flute and Steinway piano, one note per file",
        "paths": ["iowa/alto", "iowa/trumpet", "iowa/vibes", "iowa/flute", "iowa/piano", "iowa/README.md"],
        "credits": [
            "University of Iowa Electronic Music Studios, Musical Instrument Samples "
            "(https://theremin.music.uiowa.edu/MIS.html), free to use in any project. Cut and levelled by Bountiful",
        ],
    },
}


def manifest() -> dict:
    try:
        return json.loads(MANIFEST.read_text())
    except FileNotFoundError:
        return {}


def dest() -> Path:
    return paths.DATA / "samples"


def installed(root: Path | None = None) -> dict:
    """pack -> the manifest entry it was installed from."""
    d = (root or dest()) / ".packs"
    return {f.stem: json.loads(f.read_text()) for f in sorted(d.glob("*.json"))} if d.is_dir() else {}


def _files(src: Path, pack: str) -> list[Path]:
    out = []
    for p in PACKS[pack]["paths"]:
        f = src / p
        if not f.exists():
            raise FileNotFoundError(f"{pack}: {f} is missing")
        out += [f] if f.is_file() else sorted(x for x in f.rglob("*") if x.is_file() and x.name != ".DS_Store")
    return out


def _add(tar: tarfile.TarFile, name: str, data: bytes):
    ti = tarfile.TarInfo(name)
    ti.size, ti.mtime, ti.mode = len(data), 0, 0o644
    tar.addfile(ti, io.BytesIO(data))


def _flac(f: Path) -> tuple[bytes, int | None]:
    """A WAV as FLAC bytes, and the power-of-two exponent it was scaled down by (None if it wasn't float)."""
    info = sf.info(str(f))
    x, sr = sf.read(str(f), dtype="float64" if info.subtype in ("FLOAT", "DOUBLE") else "int32", always_2d=True)
    k, sub = None, info.subtype
    if info.subtype in ("FLOAT", "DOUBLE"):
        peak = float(np.abs(x).max())
        k = 0
        while peak * 2.0 ** -k >= 1.0:
            k += 1
        x, sub = x * 2.0 ** -k, "PCM_24"
    elif sub not in ("PCM_16", "PCM_24"):
        raise ValueError(f"{f}: can't pack {sub}")
    buf = io.BytesIO()
    sf.write(buf, x, sr, format="FLAC", subtype=sub)
    return buf.getvalue(), k


def build(pack: str, out: Path, src: Path | None = None, log=print) -> dict:
    """Write <pack>.tar.gz to out (byte-identical for the same sounds) and return its manifest entry."""
    src = src or paths.SAMPLES
    files = _files(src, pack)
    out.mkdir(parents=True, exist_ok=True)
    arc = out / f"bountiful-{pack}.tar.gz"
    floats = {}
    with open(arc, "wb") as fh:
        import gzip
        with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, filename="") as gz, tarfile.open(fileobj=gz, mode="w") as tar:
            for i, f in enumerate(files):
                rel = f.relative_to(src).as_posix()
                if f.suffix.lower() == ".wav":
                    data, k = _flac(f)
                    if k is not None:
                        floats[rel] = k
                    _add(tar, rel + ".flac", data)
                else:
                    _add(tar, rel, f.read_bytes())
                if i % 100 == 0:
                    log(f"{pack}: {i}/{len(files)}")
            credits = f"{PACKS[pack]['title']}: {PACKS[pack]['about']}\n\n" + "\n".join(PACKS[pack]["credits"]) + "\n"
            _add(tar, f".packs/{pack}-CREDITS.txt", credits.encode())
    entry = {"file": arc.name, "sha256": hashlib.sha256(arc.read_bytes()).hexdigest(), "size": arc.stat().st_size,
             "files": len(files), "title": PACKS[pack]["title"], "about": PACKS[pack]["about"], "float": floats}
    log(f"{pack}: {arc} {entry['size'] / 1e6:.1f} MB, {len(files)} files")
    return entry


def _download(url: str, to: Path, progress=None):
    with urllib.request.urlopen(url, timeout=60) as r, open(to, "wb") as fh:
        total, done = int(r.headers.get("Content-Length") or 0), 0
        while chunk := r.read(1 << 20):
            fh.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)


def install(pack: str, archive: Path | None = None, root: Path | None = None, overwrite: bool = False,
            progress=None, log=print) -> int:
    """Unpack a pack into root (the data folder's samples/), keeping files that are already there unless
    overwrite. Downloads it when no archive is given. Returns the number of files written."""
    entry = manifest().get(pack)
    if not entry:
        raise KeyError(f"no pack called {pack} (packs: {', '.join(manifest()) or 'none built'})")
    root = root or dest()
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        if archive is None:
            archive = Path(tmp) / entry["file"]
            log(f"downloading {URL}{entry['file']} ({entry['size'] / 1e6:.0f} MB)")
            _download(URL + entry["file"], archive, progress)
        h = hashlib.sha256()
        with open(archive, "rb") as fh:
            while chunk := fh.read(1 << 20):
                h.update(chunk)
        if h.hexdigest() != entry["sha256"]:
            raise ValueError(f"{pack}: checksum doesn't match, the download is damaged or not the real pack")
        n = 0
        with tarfile.open(archive, "r:gz") as tar:
            for m in tar:
                rel = Path(m.name)
                if not m.isfile() or rel.is_absolute() or ".." in rel.parts:
                    raise ValueError(f"{pack}: unsafe entry {m.name}")
                wav = m.name.endswith(".wav.flac")
                to = root / (m.name[:-5] if wav else m.name)
                if to.exists() and not overwrite and not m.name.startswith(".packs/"):
                    continue
                to.parent.mkdir(parents=True, exist_ok=True)
                data = tar.extractfile(m).read()
                part = to.with_name(to.name + ".part")
                if wav:
                    k = entry["float"].get(m.name[:-5])
                    x, sr = sf.read(io.BytesIO(data), dtype="float64" if k is not None else "int32", always_2d=True)
                    sub = sf.info(io.BytesIO(data)).subtype
                    if k is not None:
                        x, sub = x * 2.0 ** k, "FLOAT"
                    sf.write(str(part), x, sr, format="WAV", subtype=sub)
                else:
                    part.write_bytes(data)
                part.replace(to)
                n += 1
    (root / ".packs").mkdir(exist_ok=True)
    (root / ".packs" / f"{pack}.json").write_text(json.dumps(entry, indent=1) + "\n")
    log(f"{pack}: {n} files into {root}")
    return n


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "list":
        have = installed()
        for name, e in manifest().items():
            print(f"{name:8} {e['size'] / 1e6:6.0f} MB  {'installed' if name in have else '-':9}  {e['title']}: {e['about']}")
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "build":
        out = Path(rest[rest.index("--out") + 1]) if "--out" in rest else paths.DATA / "dist" / "packs"
        names = [a for a in rest if a in PACKS] or list(PACKS)
        m = manifest()
        for p in names:
            m[p] = build(p, out)
        MANIFEST.write_text(json.dumps(m, indent=1, sort_keys=True) + "\n")
        return 0
    if cmd == "install" and rest:
        arc = Path(rest[rest.index("--from") + 1]) if "--from" in rest else None
        install(rest[0], arc, overwrite="--overwrite" in rest)
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
