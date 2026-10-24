"""The Game music tab: turn the open track into a seamless loop with intensity states, layers and stingers
(bountiful/gamemusic.py does the work), then try it the way a game would: switch states while it plays, fire stingers."""
from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path

import numpy as np
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

import gamemusic as GM

from . import audio as A

FADE_S = 1.5                         # a state change fades over this long, like the engine players


def help_label(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet("color: #8c87a3; padding: 2px 2px 6px 2px")
    return lab


def bars_arg(text: str) -> tuple[int, int] | None:
    """'9-16' or '9' (one bar) -> (9, 16); '' -> None. Raises ValueError on anything else."""
    t = text.strip().replace(" ", "")
    if not t:
        return None
    a, _, b = t.partition("-")
    a, b = int(a), int(b or a)
    if a < 1 or b < a:
        raise ValueError("bars go like 9-16")
    return a, b


def stereo(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, np.float32)
    return np.stack([x, x], 1) if x.ndim == 1 else x


class GameSource(A.Source):
    """The exported layers looping for ever. The mix glides to the chosen state's levels; a stinger waits for the next
    beat or bar (its quantize) and plays on top. render() runs on the audio feeder thread."""
    length = None

    def __init__(self, folder: Path, man: dict):
        self.n = int(man["loop"]["samples"])
        self.bar = float(man["loop"]["bar_samples"])
        self.beat = self.bar / max(1, int(man.get("beats_per_bar", 4)))
        self.names = [k for k in GM.LAYERS if k in man["layers"]]
        self.x = np.stack([stereo(GM.read_wav(folder / man["layers"][k]["file"])[0][:self.n])
                           for k in self.names])                                    # (layers, n, 2)
        self.targets = {}
        for st, v in man["states"].items():                  # the layer levels that make each exported state loop
            g = np.array([v["mix"].get(k, 0.0) for k in self.names], np.float32)
            raw = GM.rms(np.tensordot(g, self.x, 1))
            self.targets[st] = g * (10 ** (v["rms_db"] / 20) / max(raw, 1e-9))
        self.state = "calm" if "calm" in self.targets else next(iter(self.targets))
        self.gain = self.targets[self.state].copy()
        self.step = 1.0 / (FADE_S * self.sr)
        self.stingers = {k: stereo(GM.read_wav(folder / v["file"])[0]) for k, v in man["stingers"].items()}
        self.quant = {k: v["quantize"] for k, v in man["stingers"].items()}
        self.playing_st: list[list] = []                  # [samples, at] with at = absolute frame it starts
        self.pending: list[str] = []
        self.made = 0
        self.lock = threading.Lock()

    def set_state(self, st: str):
        if st in self.targets:
            self.state = st

    def stinger(self, name: str):
        if name in self.stingers:
            with self.lock:
                self.pending.append(name)

    def render(self, pos, n):
        with self.lock:
            for name in self.pending:                     # start on the next grid line after what's queued now
                q = self.bar if self.quant[name] == "bar" else self.beat
                at = int(np.ceil(self.made / q) * q)
                self.playing_st.append([self.stingers[name], at])
            self.pending.clear()
        idx = (self.made + np.arange(n)) % self.n
        tgt = self.targets[self.state]
        ramp = np.clip(np.arange(1, n + 1, dtype=np.float32) * self.step, 0, None)       # (n,)
        d = tgt - self.gain
        g = self.gain[:, None] + np.clip(ramp[None, :], 0, np.abs(d)[:, None]) * np.sign(d)[:, None]   # (layers, n)
        self.gain = g[:, -1].copy()
        y = np.einsum("ln,lnc->nc", g, self.x[:, idx])
        keep = []
        for s, at in self.playing_st:
            if at >= self.made + n:                       # not yet: its grid line is in a later block
                keep.append([s, at])
                continue
            lo = max(at, self.made) - self.made
            off = self.made + lo - at
            seg = s[off:off + n - lo]
            y[lo:lo + len(seg)] += seg
            if off + len(seg) < len(s):
                keep.append([s, at])
        self.playing_st = keep
        self.made += n
        return GM.soft(y).astype(np.float32)


class GamePanel(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.jobs = win, win.jobs
        self.track = None
        self.man = None
        self.secs: list[dict] = []
        self.src: GameSource | None = None
        top = QVBoxLayout(self)
        top.addWidget(help_label(
            "Turn the open song into music for a game: one seamless loop in four intensity states (calm, explore, "
            "tense, combat), the separate layers, short stingers (victory, game over, pickup ...) and ready-made "
            "players for Godot and Unity. Pick a part of the song, press Make, then try it like a game on the right."))
        lay = QHBoxLayout()
        top.addLayout(lay, 1)

        left = QWidget()
        form = QFormLayout(left)
        self.what = QLabel("No song open yet.")
        self.what.setWordWrap(True)
        form.addRow("Song", self.what)
        pick = QPushButton("Open a track …")
        pick.setToolTip("or double-click one in the Library on the left")
        pick.clicked.connect(lambda: self.win.open_dialog())
        form.addRow("", pick)
        self.section = QComboBox()
        self.section.setToolTip("which part of the song becomes the loop (the busiest part is picked for you)")
        form.addRow("Loop", self.section)
        self.bars = QLineEdit()
        self.bars.setPlaceholderText(f"or bars, e.g. 9-16 (at most {GM.MAX_BARS})")
        self.bars.setToolTip("leave empty to use the part picked above")
        form.addRow("", self.bars)
        self.c_sting = QCheckBox("Stingers (short one-shots in the song's key)")
        self.c_sting.setChecked(True)
        form.addRow("", self.c_sting)
        self.c_ogg = QCheckBox("Also OGG files (smaller, with loop tags)")
        self.c_ogg.setEnabled(bool(shutil.which("ffmpeg")))
        self.c_ogg.setToolTip("needs ffmpeg" if not self.c_ogg.isEnabled() else "Godot and Unity both play OGG")
        form.addRow("", self.c_ogg)
        row = QHBoxLayout()
        self.b_make = QPushButton("Make game music")
        self.b_make.setObjectName("primary")
        self.b_make.setToolTip("render the loop, its layers and the stingers into the track's game/ folder (a minute or two)")
        self.b_make.clicked.connect(lambda: self.make())
        self.b_folder = QPushButton("Show folder")
        self.b_folder.clicked.connect(self.show_folder)
        row.addWidget(self.b_make)
        row.addWidget(self.b_folder)
        form.addRow(row)
        left.setMaximumWidth(460)
        lay.addWidget(left)

        right = QVBoxLayout()
        lay.addLayout(right, 1)
        g = QGroupBox("Try it like a game")
        gl = QVBoxLayout(g)
        gl.addWidget(help_label("Press a state to start the loop, then switch while it plays: the layers fade in "
                                "and out the way they will in the game. Stingers wait for the next beat or bar."))
        sr = QHBoxLayout()
        self.states = QButtonGroup(self)
        self.state_btn = {}
        for st in GM.STATES:
            b = QPushButton(st.title())
            b.setCheckable(True)
            b.setMinimumHeight(40)
            b.setToolTip(f"{GM.STATE_WHAT[st]}: {', '.join(GM.STATES[st])}")
            b.clicked.connect(lambda _=False, st=st: self.play_state(st))
            self.states.addButton(b)
            self.state_btn[st] = b
            sr.addWidget(b)
        stop = QPushButton("■ Stop")
        stop.setMinimumHeight(40)
        stop.clicked.connect(self.stop)
        sr.addWidget(stop)
        gl.addLayout(sr)
        grid = QGridLayout()
        self.sting_btn = {}
        for i, (k, (what, q, _)) in enumerate(GM.STINGERS.items()):
            b = QPushButton(k.replace("_", " ").title())
            b.setToolTip(f"{what} (waits for the next {q})")
            b.clicked.connect(lambda _=False, k=k: self.fire(k))
            self.sting_btn[k] = b
            grid.addWidget(b, i // 5, i % 5)
        gl.addLayout(grid)
        right.addWidget(g)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setPlaceholderText("What was made, and how to use it in your game, appears here.")
        right.addWidget(self.out, 1)
        self._enable()

    # ---- state
    def _enable(self):
        have = self.man is not None
        for b in list(self.state_btn.values()):
            b.setEnabled(have)
        for k, b in self.sting_btn.items():
            b.setEnabled(have and k in self.man["stingers"])
        self.b_folder.setEnabled(self.track is not None)
        self.b_make.setEnabled(self.track is not None)

    def set_track(self, tr):
        self.stop()
        self.track, self.man, self.secs = tr, None, []
        self.section.clear()
        self.out.clear()
        if tr is None:
            self._enable()
            return
        self.what.setText(f"{tr.title}  ·  {tr.bpm:g} bpm  ·  {tr.bars} bars")
        self._load(tr.folder / "game")
        folder = tr.folder

        def done(secs):
            if self.track is None or self.track.folder != folder:
                return
            self.secs = secs
            top = GM.busiest(secs)
            for s in secs:
                a, b = GM.loop_bars(s)
                tag = "   ← busiest" if top and s["index"] == top["index"] else ""
                self.section.addItem(f"{s['index'] + 1}. {s['name']}  (bars {a}-{b}){tag}", s["index"])
            if top:
                self.section.setCurrentIndex(top["index"])
        self.jobs.run("", lambda: GM.sections(folder), done)
        self._enable()

    def _load(self, out: Path):
        m = out / "manifest.json"
        if not m.exists():
            self.man = None
            self.out.setPlainText("No game music for this song yet: press Make game music.")
            return
        try:
            self.man = json.loads(m.read_text())
            self.out.setPlainText((out / "README.txt").read_text() if (out / "README.txt").exists() else m.read_text())
        except Exception as e:
            self.man = None
            self.out.setPlainText(f"couldn't read {m}: {e}")
        self._enable()

    # ---- actions
    def make(self, then=None, stingers=None):
        if self.track is None:
            self.win.log("open a track first")
            return
        try:
            bars = bars_arg(self.bars.text())
        except ValueError:
            self.win.log("bars go like 9-16")
            return
        self.stop()
        folder = self.track.folder
        sec = self.section.currentData()
        sting = self.c_sting.isChecked() if stingers is None else stingers
        og = self.c_ogg.isChecked() and self.c_ogg.isEnabled()
        self.out.setPlainText("Making the game music (the loop first, then the stingers) ...")
        self.b_make.setEnabled(False)

        def done(man):
            self.b_make.setEnabled(True)
            if self.track is not None and self.track.folder == folder:
                self._load(Path(man["folder"]))
            if then:
                then(man)

        def fail(e):
            self.b_make.setEnabled(True)
            self.out.setPlainText(f"That didn't work: {e}")
            if then:
                then(e)
        self.jobs.run("making game music", lambda: GM.make(folder, section=sec, bars=bars, stingers=sting, ogg_too=og,
                                                           log=self.jobs.log), done, fail)

    def play_state(self, st: str):
        if self.man is None:
            return
        if self.src is None or self.win.player.src is not self.src:
            try:
                self.src = GameSource(self.track.folder / "game", self.man)
            except Exception as e:
                self.win.log(f"couldn't load the game music: {e}")
                return
            self.src.set_state(st)
            self.src.gain = self.src.targets[self.src.state].copy()     # start at the chosen state, no fade in
            if self.win.livep.b_play.isChecked():
                self.win.livep.b_play.setChecked(False)
            self.win.player.set_source(self.src)
            self.win.now_playing = "game"
            self.win.player.play()
        self.src.set_state(st)
        self.state_btn[st].setChecked(True)
        self.win.statusBar().showMessage(f"▶ game music: {st} ({GM.STATE_WHAT[st]})", 4000)

    def fire(self, name: str):
        if self.src is None or self.win.player.src is not self.src or not self.win.player.playing:
            self.play_state(self.src.state if self.src else "explore")
        if self.src is not None:
            self.src.stinger(name)

    def stop(self):
        if self.src is not None and self.win.player.src is self.src:
            self.win.player.stop()
            self.win.player.set_source(None)
            self.win.now_playing = None
        self.src = None
        self.states.setExclusive(False)
        for b in self.state_btn.values():
            b.setChecked(False)
        self.states.setExclusive(True)

    def show_folder(self):
        if self.track is not None:
            out = self.track.folder / "game"
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out if out.exists() else self.track.folder)))
