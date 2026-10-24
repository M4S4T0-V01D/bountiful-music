"""Tests for the app side: the updater, the DAW's audio sources and track model, and a headless run of the window.
Run with the app's Python (it has PySide6):  .venv/bin/python tests/test_app.py   (or ~/.local/lib/bountiful/venv/bin/python)"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bountiful"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True).stdout


def test_updater_pulls_new_commits():
    import updater
    with tempfile.TemporaryDirectory() as tmp:
        src, app = Path(tmp) / "src", Path(tmp) / "app"
        src.mkdir()
        git(src, "init", "-q", "-b", "main")
        git(src, "config", "user.email", "t@example.invalid")
        git(src, "config", "user.name", "t")
        (src / "a.txt").write_text("1")
        git(src, "add", "a.txt")
        git(src, "commit", "-qm", "one")
        subprocess.run(["git", "clone", "-q", str(src), str(app)], check=True)
        old = updater.CODE
        updater.CODE = app
        try:
            st = updater.check()
            assert st["ok"] and st["behind"] == 0, st
            (src / "a.txt").write_text("2")
            git(src, "commit", "-qam", "two: a new feature")
            st = updater.check()
            assert st["behind"] == 1 and "two: a new feature" in st["changes"][0], st
            logs = []
            assert updater.update(log=logs.append)
            assert (app / "a.txt").read_text() == "2" and updater.check()["behind"] == 0
            updater.CODE = src                      # the source repo itself: nothing to update from
            assert not updater.check()["ok"]
        finally:
            updater.CODE = old


def test_audio_sources():
    import soundfile as sf
    from bountiful.daw import audio as A
    with tempfile.TemporaryDirectory() as tmp:
        t = np.linspace(0, 1, 44100, dtype=np.float32)
        a = np.stack([np.sin(2 * np.pi * 220 * t)] * 2, 1) * 0.3
        sf.write(f"{tmp}/a.wav", a, 44100)
        sf.write(f"{tmp}/b.wav", a * 0.5, 44100)
        s = A.StemsSource({"a": Path(f"{tmp}/a.wav"), "b": Path(f"{tmp}/b.wav")})
        y = s.render(1000, 512)
        assert y.shape == (512, 2) and np.abs(y).max() > 0.1
        s.mute.add("a")
        assert np.abs(s.render(1000, 512)).max() < np.abs(y).max()
        s.solo.add("a")
        assert np.allclose(s.render(1000, 512), a[1000:1512], atol=1e-3)
        assert np.abs(s.render(44100 + 10, 64)).max() == 0          # past the end: silence
        s.mute.clear()
        s.solo.clear()
        out = s.bounce(Path(tmp) / "mix.wav", log=lambda *_: None)
        assert sf.info(str(out)).frames == 44100
        p = A.Player(log=lambda *_: None)
        p.set_source(A.ArraySource(np.zeros(4410, np.float32)))
        assert A.wait_until(lambda: len(p.q) >= 1, 3)                 # the feeder renders ahead
        p.close()


def test_game_music_preview_loops_glides_and_waits_for_the_beat():
    import gamemusic as GM
    from bountiful.daw import gamemusic as GP
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        n, bar = 4000, 1000
        GM.write_wav(out / "bed.wav", np.full((n, 2), 0.01), (0, n - 1))
        GM.write_wav(out / "beat.wav", np.full((n, 2), 0.02) * (np.arange(n) % 2 * 2 - 1)[:, None], (0, n - 1))
        GM.write_wav(out / "hit.wav", np.r_[[0.3], np.zeros(9)])
        man = {"beats_per_bar": 4, "loop": {"samples": n, "bar_samples": bar},
               "layers": {"bed": {"file": "bed.wav"}, "beat": {"file": "beat.wav"}},
               "states": {"calm": {"mix": {"bed": 1.0}, "rms_db": -40.0},
                          "combat": {"mix": {"bed": 1.0, "beat": 1.0}, "rms_db": -30.0}},
               "stingers": {"pickup": {"file": "hit.wav", "quantize": "beat"}}}
        src = GP.GameSource(out, man)
        assert src.length is None and src.state == "calm"
        a = src.render(0, 100)
        assert np.allclose(a, a[0]) and abs(GM.rms(a) - 0.01) < 1e-3          # calm: the bed at -40 dB
        src.stinger("pickup")                                                 # asked for at frame 100 ...
        b = src.render(0, 400)
        assert np.argmax(np.abs(b[:, 0] - 0.01)) == 150                       # ... heard on the next beat, frame 250
        src.set_state("combat")
        c = np.vstack([src.render(0, 500) for _ in range(200)])               # 100000 frames: round the loop 25 times
        early, late = np.abs(np.diff(c[:2000, 0])).max(), np.abs(np.diff(c[-2000:, 0])).max()
        assert early < 0.01 < late                                            # the beat fades in, it doesn't jump in
        assert abs(GM.rms(c[-n:]) - 10 ** (-30 / 20)) < 3e-3                  # and settles at combat's level


def test_track_model_round_trip():
    from bountiful.daw import model as M
    with tempfile.TemporaryDirectory() as tmp:
        tr = M.Track(Path(tmp), "Round Trip", 101.0, {"lead": [M.Note(0, 1, 64, 0.8), M.Note(1.5, 0.5, 67, 0.6)],
                                                       "counter": [M.Note(2, 2, 55, 0.7)], "drums": [M.Note(0, 0.25, 36, 1.0)]})
        tr.save_midi()
        back = M.load(Path(tmp))
        assert abs(back.bpm - 101.0) < 0.01
        assert [(n.t, n.p) for n in back.parts["lead"]] == [(0.0, 64), (1.5, 67)]
        assert "counter" in back.parts and "drums" in back.parts


def test_window_smoke():
    r = subprocess.run([sys.executable, str(ROOT / "bountiful" / "daw" / "main.py"), "--smoke"], capture_output=True, text=True,
                       timeout=180, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    assert r.returncode == 0 and "smoke ok" in r.stdout, r.stdout[-2000:] + r.stderr[-2000:]


if __name__ == "__main__":
    bad = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok    {name}")
            except Exception as e:
                bad += 1
                print(f"FAIL  {name}: {e}")
    sys.exit(1 if bad else 0)
