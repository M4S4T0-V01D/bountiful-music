"""The built-in players (renderer/engine/native.py) that stand in for LMMS's sf2player and AudioFileProcessor:
note events, the sampler's pitch / level / note-off, and, where FluidSynth, the GeneralUser GS pack and LMMS are
all installed, a sample-for-sample match with LMMS.

    $PY -I tests/test_native.py
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "renderer"))

from engine import lmms as LM  # noqa: E402
from engine import native as NV  # noqa: E402
from engine.share import find_lmms  # noqa: E402

SR, BPM, TPB = 44100, 120, LM.TPB
SPB = 60 / BPM / TPB * SR
SF2 = ROOT / "samples" / "sf2" / "GeneralUser-GS.sf2"
fails = 0


def check(name, problems):
    global fails
    problems = list(problems)
    print(f"{'ok  ' if not problems else 'FAIL'} {name}")
    for p in problems[:12]:
        print(f"     {p}")
    fails += bool(problems)


def pitch(x):
    m = x.mean(1) * np.hanning(len(x))
    f = np.abs(np.fft.rfft(m, SR * 8))
    return np.argmax(f) / 8


# events: LMMS keys sit an octave below MIDI, velocity = vol x 63 / 100, a key held twice ends with its last note
ev = NV._events({"transpose": 0}, [(0, 48, 57, 100), (24, 48, 57, 200), (96, 1, 60, 1)], SPB)
check("events", [f"got {ev}"] * (ev != [(0, 1, 69, 63), (int(24 * SPB), 1, 69, 126), (int(72 * SPB), 0, 69, 0),
                                       (int(96 * SPB), 1, 72, 1), (int(97 * SPB), 0, 72, 0)]))
check("can_play", [f"{v}" for v, want in [({"sample": "x.wav"}, True), ({"sample": "x.wav", "fx": [1]}, False),
                                           ({"zyn": "x.xiz"}, False), ({"sample": "x.wav", "xpf": "y"}, False)]
                   if NV.can_play(v) != want])

# sampler: a 220 Hz tone with root 57 (A3) played at A3 and A4, at vol 100 and 50, cut at note-off with a short fade
with tempfile.TemporaryDirectory() as d:
    t = np.arange(SR * 2) / SR
    wav = Path(d) / "tone.wav"
    sf.write(str(wav), 0.5 * np.sin(2 * np.pi * 220 * t), SR)
    v = {"sample": str(wav), "root": 57}
    n = SR * 4
    y = NV.sampler(v, [(0, 48, 45, 100), (96, 48, 57, 50)], BPM, n, SR)
    a, b = y[: int(48 * SPB)], y[int(96 * SPB): int(144 * SPB)]
    tail = y[int(48 * SPB) + NV.DEFAULT_RELEASE + 8: int(96 * SPB)]
    check("sampler", [p for p in [
        abs(pitch(a) - 220) > 0.5 and f"A3 at {pitch(a):.1f} Hz",
        abs(pitch(b) - 440) > 1 and f"A4 at {pitch(b):.1f} Hz",
        abs(np.abs(a).max() - 0.5) > 0.01 and f"vol 100 peak {np.abs(a).max():.3f}",
        abs(np.abs(b).max() - 0.25) > 0.01 and f"vol 50 peak {np.abs(b).max():.3f}",
        np.abs(tail).max() > 1e-6 and "sound after note-off",
        y.shape != (n, 2) and f"shape {y.shape}"] if p])

# sf2player: needs libfluidsynth and the GeneralUser GS pack
if NV._fluid() is None or not SF2.is_file():
    print(f"skip sf2 ({'no libfluidsynth' if NV._fluid() is None else 'no GeneralUser GS pack'})")
else:
    v = {"plugin": "sf2player", "attrs": {"src": str(SF2), "bank": 0, "patch": 0, "gain": 3.0, "reverbOn": 0, "chorusOn": 0}}
    notes = [(i * 48, 40, k, vol) for i, (k, vol) in enumerate([(45, 60), (52, 100), (57, 160)])] + [(192, 96, 45, 100)]
    n = int(6 * SR)
    x = NV.sf2(v, notes, BPM, n, SR)
    first = int(np.argmax(np.abs(x[:, 0]) > 1e-4))
    peaks = [np.abs(x[int(i * 48 * SPB): int((i * 48 + 40) * SPB)]).max() for i in range(3)]
    check("sf2", [p for p in [
        not 0 <= first < 64 + 64 and f"first sound at frame {first}",
        abs(pitch(x[int(192 * SPB) + 2000: int(192 * SPB) + 2000 + SR]) - 220) > 1.5 and "A3 (LMMS key 45) off pitch",
        not peaks[0] < peaks[1] < peaks[2] and f"velocity ladder {peaks}",
        np.abs(x[-SR // 2:]).max() > 1e-3 and "still sounding at the end",
        not np.array_equal(x, NV.sf2(v, notes, BPM, n, SR)) and "not deterministic"] if p])
    if find_lmms():
        ref = LM.render_parts({"x": (v, notes)}, BPM, n, SR)["x"]
        c = np.corrcoef(ref.mean(1), x.mean(1))[0, 1]
        check("sf2 matches LMMS", [f"correlation {c:.4f}"] * bool(c < 0.999))
    else:
        print("skip sf2 vs LMMS (no LMMS)")

print("all pass" if not fails else f"{fails} failing")
sys.exit(bool(fails))
