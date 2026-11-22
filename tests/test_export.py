"""MP3 export without the lame program (renderer/engine/export.py): 320 kbps CBR through libsndfile, ID3v2.3 tags
and the cover through mutagen, the audio intact.

    $PY -I tests/test_export.py
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "renderer"))

from engine import export as E  # noqa: E402

fails = 0


def check(name, problems):
    global fails
    problems = list(problems)
    print(f"{'ok  ' if not problems else 'FAIL'} {name}")
    for p in problems[:12]:
        print(f"     {p}")
    fails += bool(problems)


SR = 44100
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    t = np.arange(SR * 4) / SR
    x = np.stack([0.4 * np.sin(2 * np.pi * 440 * t), 0.4 * np.sin(2 * np.pi * 660 * t)], 1)
    sf.write(str(d / "a.wav"), x, SR, subtype="PCM_24")
    cover = d / "cover.png"
    cover.write_bytes(bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63f8"
                                    "ffff3f0005fe02fea7d6a4b80000000049454e44ae426082"))
    meta = {"title": "Fröst Wïndow", "artist": "M4S4T0", "album": "Test", "year": 2026, "track": 4, "composer": "C", "cover": str(cover)}
    ok = E.mp3(d / "a.wav", d / "a.mp3", meta)
    from mutagen.mp3 import MP3
    m = MP3(str(d / "a.mp3"))
    y, ysr = sf.read(str(d / "a.mp3"))
    f = lambda ch: np.argmax(np.abs(np.fft.rfft(ch[SR:SR * 3] * np.hanning(SR * 2)))) / 2
    tags = {k: str(v) for k, v in m.tags.items()}
    check("mp3", [p for p in [
        not ok and "mp3() returned False",
        (m.info.bitrate, str(m.info.bitrate_mode)) != (320000, "BitrateMode.CBR") and f"{m.info.bitrate} {m.info.bitrate_mode}",
        m.tags.version[:2] != (2, 3) and f"ID3 {m.tags.version}",
        (tags.get("TIT2"), tags.get("TPE1"), tags.get("TALB"), tags.get("TRCK"), tags.get("TCOM"), tags.get("TPE2"))
        != ("Fröst Wïndow", "M4S4T0", "Test", "4", "C", "M4S4T0") and f"tags {tags}",
        not any(k.startswith("APIC") for k in tags) and "no cover",
        (ysr, y.shape[1]) != (SR, 2) and f"{ysr} Hz, {y.shape[1]} channels",
        abs(len(y) - len(x)) > 1152 and f"length {len(y)} vs {len(x)}",
        (abs(f(y[:, 0]) - 440) > 1 or abs(f(y[:, 1]) - 660) > 1) and f"pitches {f(y[:, 0])} {f(y[:, 1])}",
        abs(np.abs(y).max() - 0.4) > 0.02 and f"peak {np.abs(y).max():.3f}"] if p])

print("all pass" if not fails else f"{fails} failing")
sys.exit(bool(fails))
