"""Bountiful — the DAW. Songs from a Bounty, the Electronium live, a day of ideas; arrange, edit, mix, render.

    python bountiful/daw/main.py [track folder]
    python bountiful/daw/main.py --smoke      (build the window, exercise it, quit: for tests)
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))

from PySide6.QtCore import QSize, Qt, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QKeySequence, QPalette  # noqa: E402
from PySide6.QtWidgets import (QApplication, QCheckBox, QDockWidget, QFileDialog, QLabel,  # noqa: E402
                               QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy, QSlider,
                               QSplitter, QStyle, QTabWidget, QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

import build as B  # noqa: E402
import paths  # noqa: E402
import updater  # noqa: E402

from bountiful.daw import audio as A  # noqa: E402
from bountiful.daw import gamemusic as GP  # noqa: E402
from bountiful.daw import start as SP  # noqa: E402
from bountiful.daw import lab as L  # noqa: E402
from bountiful.daw import model as M  # noqa: E402
from bountiful.daw import observatory as OB  # noqa: E402
from bountiful.daw import panels as P  # noqa: E402
from bountiful.daw import record as RP  # noqa: E402
from bountiful.daw import setup as SU  # noqa: E402
from bountiful.daw import views as V  # noqa: E402

APP_ID = "dev.m4s4t0.bountiful"
LOGO = HERE / "logo.svg"

STYLE = """
QMainWindow, QWidget { background: #17151f; color: #d8d4e8; }
QToolBar { background: #1f1c2a; border: none; spacing: 6px; padding: 4px; }
QTabWidget::pane { border: 1px solid #2a2736; }
QTabBar::tab { background: #1f1c2a; padding: 7px 16px; border: 1px solid #2a2736; border-bottom: none; color: #a9a4c0; }
QTabBar::tab:selected { background: #2a2638; color: #ffb347; }
QPushButton { background: #2a2638; border: 1px solid #3a3650; border-radius: 5px; padding: 5px 12px; }
QPushButton:hover { background: #343048; }
QPushButton:checked { background: #5a3a1a; border-color: #ff9b42; }
QPushButton#primary { background: #ff9b42; color: #17151f; font-weight: bold; border: none; }
QPushButton#primary:hover { background: #ffb36a; }
QPushButton#primary:checked { background: #ff5d6c; color: white; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTableWidget, QTreeWidget {
  background: #110f18; border: 1px solid #2a2736; border-radius: 4px; padding: 3px; selection-background-color: #5a3a1a; }
QHeaderView::section { background: #1f1c2a; color: #a9a4c0; border: none; padding: 4px; }
QGroupBox { border: 1px solid #2a2736; border-radius: 6px; margin-top: 14px; padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #ffb347; }
QSlider::groove:horizontal { height: 4px; background: #2a2736; border-radius: 2px; }
QSlider::handle:horizontal { background: #ff9b42; width: 12px; margin: -5px 0; border-radius: 6px; }
QSlider::groove:vertical { width: 4px; background: #2a2736; border-radius: 2px; }
QSlider::handle:vertical { background: #d8d4e8; height: 18px; margin: 0 -8px; border-radius: 3px; }
QDockWidget::title { background: #1f1c2a; padding: 4px; }
QStatusBar { background: #1f1c2a; }
QSplitter::handle { background: #2a2736; }
QCheckBox::indicator, QRadioButton::indicator { width: 13px; height: 13px; border: 1px solid #6a6585; background: #110f18; }
QRadioButton::indicator { border-radius: 7px; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked { background: #ff9b42; border-color: #ffb36a; }
"""


def fmt_time(s: float) -> str:
    return f"{int(s // 60)}:{s % 60:04.1f}"


def helped(w: QWidget, text: str) -> QWidget:
    """A page: a one-line explanation above the panel."""
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setContentsMargins(6, 4, 6, 0)
    lay.addWidget(GP.help_label(text))
    lay.addWidget(w, 1)
    return page


def TABS(win) -> list[tuple[QWidget, str, str]]:
    """(page, plain name, hover hint), in tab order."""
    return [
        (win.start, "Start", "the main things to do, and your recent tracks"),
        (win.arr, "Arrange", "the open song: its parts bar by bar, and a piano roll to edit the notes"),
        (win.mixer, "Mixer", "levels, panning, mute and solo for the open song's rendered parts"),
        (helped(win.song, "Write a whole song from a Bounty. Make it from the rules alone, or type a brief in your "
                          "own words (\"a restless break, a huge ending\") and see what it changes before you make it."),
         "New song", "a whole song from a Bounty, with key, tempo and a brief in your own words"),
        (helped(win.record, "Song Spec records: whole songs written as TOML files in records/. Change the tempo, swing "
                            "or seed, make a new take, then check it and build it; every bar shows what plays in it."),
         "Record", "songs written as Song Spec files: edit, take again, build"),
        (win.game, "Game music", "loops in four intensity states, stingers, and files for Godot and Unity"),
        (helped(win.livep, "The Electronium plays without stopping. Turn its knobs, mute channels and change the "
                           "rhythm: each change starts on the next bar and is recorded, so the take can become a song."),
         "Play live", "the Electronium playing live while you turn its knobs"),
        (helped(win.day, "Try many Bounties at once. Hear each one's best idea, give a thumbs up or down (it learns "
                         "what you like), and turn the good ones into songs."),
         "Batch of ideas", "many Bounties at once, ranked; your thumbs teach it your taste"),
        (helped(win.lab, "Build an instrument rack from the eleven sound engines, route them into each other, render "
                         "a few beats and look inside the sound."),
         "Sound lab", "the experimental synthesis engines (was: Synthesis Lab)"),
        (helped(win.obs, "Where songs come from: the shortlist of ideas, your ratings, what the producer changed, the "
                         "song's sections over its spectrum, and new takes on any 4 bars."),
         "Ideas and history", "ideas, ratings, family tree and branching (was: Observatory)"),
        (win.notes, "Notes", "the open track's notes file"),
    ]


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bountiful")
        self.setWindowIcon(QIcon(str(LOGO)))
        self.resize(1480, 900)
        self.jobs = P.Jobs()
        self.player = A.Player(log=lambda s: self.jobs.log(s))
        self.track: M.Track | None = None
        self.src = None
        self.now_playing = None

        # ---- views
        self.arrange = V.ArrangeView()
        self.roll = V.PianoRoll()
        self.mixer = V.Mixer()
        self.song = P.SongPanel(self)
        self.livep = P.LivePanel(self)
        self.day = P.DayPanel(self)
        self.lab = L.LabPanel(self)
        self.obs = OB.ObservatoryPanel(self)
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setFont(P.MONO)
        arr = QSplitter(Qt.Vertical)
        arr.addWidget(self.arrange)
        rollbox = QWidget()
        rl = QVBoxLayout(rollbox)
        rl.setContentsMargins(0, 0, 0, 0)
        self.roll_title = QLabel("Piano roll")
        self.roll_title.setStyleSheet("color: #8c87a3; padding: 2px 6px")
        rl.addWidget(self.roll_title)
        rl.addWidget(self.roll, 1)
        arr.addWidget(rollbox)
        arr.setSizes([480, 320])
        self.arr = arr
        self.game = GP.GamePanel(self)
        self.start = SP.StartPanel(self)
        self.record = RP.RecordPanel(self)
        self.tabs = QTabWidget()
        for w, name, tip in TABS(self):
            self.tabs.setTabToolTip(self.tabs.addTab(w, name), tip)
        self.setCentralWidget(self.tabs)
        self.arrange.seek.connect(self.seek_beat)
        self.arrange.laneOpened.connect(self.edit_lane)
        self.arrange.laneSelected.connect(self.edit_lane_quiet)
        self.roll.changed.connect(self._edited)
        self.roll.seek.connect(self.seek_beat)

        # ---- library
        lib = QWidget()
        ll = QVBoxLayout(lib)
        ll.setContentsMargins(4, 4, 4, 4)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter …")
        self.filter.textChanged.connect(self.fill_library)
        ll.addWidget(self.filter)
        self.lib = QTreeWidget()
        self.lib.setHeaderHidden(True)
        self.lib.itemDoubleClicked.connect(lambda it, _: it.data(0, Qt.UserRole) and self.open_track(Path(it.data(0, Qt.UserRole))))
        ll.addWidget(self.lib, 1)
        dock = QDockWidget("Library", self)
        dock.setObjectName("library")
        dock.setWidget(lib)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.libdock = dock

        # ---- log
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setFont(P.MONO)
        self.logbox.setMaximumBlockCount(5000)
        ld = QDockWidget("Log", self)
        ld.setObjectName("log")
        ld.setWidget(self.logbox)
        self.addDockWidget(Qt.BottomDockWidgetArea, ld)
        self.resizeDocks([ld], [130], Qt.Vertical)
        self.resizeDocks([dock], [250], Qt.Horizontal)
        self.logdock = ld
        self.jobs.logged.connect(self.log)
        self.jobs.busy.connect(self._busy)

        self._transport()
        self._menus()
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setMaximumWidth(160)
        self.busy.hide()
        self.busy_label = QLabel("")
        self.upd_btn = QPushButton("")
        self.upd_btn.setObjectName("primary")
        self.upd_btn.hide()
        self.upd_btn.clicked.connect(self.do_update)
        self.statusBar().addPermanentWidget(self.busy_label)
        self.statusBar().addPermanentWidget(self.busy)
        self.statusBar().addPermanentWidget(self.upd_btn)
        self.statusBar().showMessage(f"Music in {paths.DATA}   ·   Bountiful {updater.version()}")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)
        self.fill_library()
        self.log(f"Bountiful {updater.version()} · music: {paths.DATA} · engine: {paths.ENGINE}")
        if self.player.error:
            self.log(f"No audio output: {self.player.error}")

    # ---- chrome
    def _transport(self):
        tb = QToolBar("Transport")
        tb.setObjectName("transport")
        tb.setIconSize(QSize(20, 20))
        tb.setMovable(False)
        self.addToolBar(tb)
        logo = QLabel()
        logo.setPixmap(QIcon(str(LOGO)).pixmap(28, 28))
        tb.addWidget(logo)
        name = QLabel(" Bountiful  ")
        name.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffb347")
        tb.addWidget(name)
        st = self.style()
        self.a_home = tb.addAction(st.standardIcon(QStyle.SP_MediaSkipBackward), "To the start (Home)", lambda: self.seek_beat(0))
        self.a_play = tb.addAction(st.standardIcon(QStyle.SP_MediaPlay), "Play / pause (Space)", self.toggle_play)
        self.a_stop = tb.addAction(st.standardIcon(QStyle.SP_MediaStop), "Stop", self.stop)
        self.pos_label = QLabel("  1.1   0:00.0 / 0:00.0  ")
        self.pos_label.setStyleSheet("font-family: monospace; font-size: 15px; color: #ffe08a; background: #110f18; "
                                     "border-radius: 4px; padding: 3px 8px")
        tb.addWidget(self.pos_label)
        self.follow = QCheckBox("follow")
        self.follow.setChecked(True)
        tb.addWidget(self.follow)
        tb.addSeparator()
        self.title_label = QLabel("")
        self.title_label.setStyleSheet("font-size: 14px")
        tb.addWidget(self.title_label)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.b_preview = QPushButton("Preview 8 bars")
        self.b_preview.setToolTip("render 8 bars from the playhead (quick, no stems)")
        self.b_preview.clicked.connect(self.preview)
        self.b_render = QPushButton("Render")
        self.b_render.setObjectName("primary")
        self.b_render.setToolTip("render the whole track: master, MP3 and stems")
        self.b_render.clicked.connect(self.render)
        tb.addWidget(self.b_preview)
        tb.addWidget(self.b_render)
        vol = QSlider(Qt.Horizontal)
        vol.setRange(0, 100)
        vol.setValue(90)
        vol.setFixedWidth(90)
        vol.setToolTip("monitor volume")
        vol.valueChanged.connect(lambda v: setattr(self.player, "volume", (v / 100) ** 2 / 0.81))
        tb.addWidget(QLabel("  🔊"))
        tb.addWidget(vol)

    def _menus(self):
        mb = self.menuBar()
        f = mb.addMenu("&File")
        self._act(f, "Open track folder …", self.open_dialog, QKeySequence.Open)
        self._act(f, "Save MIDI edits", self.save_midi, QKeySequence.Save)
        self._act(f, "Reload track", lambda: self.track and self.open_track(self.track.folder), QKeySequence.Refresh)
        self._act(f, "Show track folder", lambda: self.track and QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.track.folder))))
        self._act(f, "Show music folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.DATA))))
        f.addSeparator()
        self._act(f, "Quit", self.close, QKeySequence.Quit)
        t = mb.addMenu("&Track")
        self._act(t, "Play / pause", self.toggle_play, "Space")
        self._act(t, "To the start", lambda: self.seek_beat(0), "Home")
        self._act(t, "Render", self.render, "Ctrl+R")
        self._act(t, "Preview 8 bars from the playhead", self.preview, "Ctrl+P")
        self._act(t, "Bounce the mix …", self.bounce, "Ctrl+B")
        self._act(t, "Open in MIDI Studio", self.midi_studio)
        v = mb.addMenu("&View")
        for i in range(self.tabs.count()):
            self._act(v, self.tabs.tabText(i), lambda i=i: self.tabs.setCurrentIndex(i), f"Ctrl+{i + 1}" if i < 9 else None)
        v.addSeparator()
        v.addAction(self.libdock.toggleViewAction())
        v.addAction(self.logdock.toggleViewAction())
        s = mb.addMenu("&Settings")
        self._act(s, "Setup: sounds and programs …", self.open_setup)
        self._act(s, "Music folder …", self.set_data)
        h = mb.addMenu("&Help")
        self._act(h, "Check for updates …", lambda: self.check_updates(quiet=False))
        self._act(h, "About Bountiful", self.about)
        QTimer.singleShot(2500, lambda: self.check_updates(quiet=True))

    def _act(self, menu, text, fn, key=None):
        a = QAction(text, self)
        if key:
            a.setShortcut(QKeySequence(key))
            a.setShortcutContext(Qt.WindowShortcut)
        a.triggered.connect(lambda *_: fn())
        menu.addAction(a)
        self.addAction(a)
        return a

    def log(self, s):
        self.logbox.appendPlainText(str(s))

    def _busy(self, what):
        on = bool(what) or self.jobs.running > 0
        self.busy.setVisible(on)
        if what:
            self.busy_label.setText(what + " …")
        elif not on:
            self.busy_label.setText("")

    def show_panel(self, w):
        while w is not None and self.tabs.indexOf(w) < 0:       # panels sit inside a page with their help line
            w = w.parentWidget()
        if w is not None:
            self.tabs.setCurrentWidget(w)

    # ---- library and tracks
    def fill_library(self):
        q = self.filter.text().lower().strip()
        self.lib.clear()
        for group, folders in M.library().items():
            g = QTreeWidgetItem([group])
            g.setForeground(0, QColor("#ffb347"))
            for d in folders:
                if q and q not in d.name.lower():
                    continue
                it = QTreeWidgetItem([d.name])
                it.setData(0, Qt.UserRole, str(d))
                it.setToolTip(0, str(d))
                if not (d / "exports").exists():
                    it.setForeground(0, QColor("#8c87a3"))
                g.addChild(it)
            if g.childCount():
                self.lib.addTopLevelItem(g)
                g.setExpanded(group == "Tracks" or bool(q))

    def open_dialog(self):
        d = QFileDialog.getExistingDirectory(self, "Open a track folder", str(paths.DATA / "tracks"))
        if d:
            self.open_track(Path(d))

    def open_track(self, folder):
        if folder is None or isinstance(folder, Exception):
            return
        folder = Path(folder)
        if self.track and self.track.dirty and self.track.folder != folder:
            if QMessageBox.question(self, "Bountiful", f"Save your note edits to {self.track.name} first?") == QMessageBox.Yes:
                self.save_midi()
        keep = self.player.pos if self.track and self.track.folder == folder else 0
        try:
            tr = M.load(folder)
        except Exception as e:
            self.log(f"couldn't open {folder}: {e}")
            return
        if self.livep.b_play.isChecked():
            self.livep.b_play.setChecked(False)
        self.track = tr
        self.arrange.set_track(tr)
        self.roll.set_part(tr, None)
        self.notes.setPlainText(tr.notes_text())
        self.title_label.setText(f"  {tr.title}  ·  {tr.bpm:g} bpm  ·  {tr.bars} bars")
        self.setWindowTitle(f"{tr.title} — Bountiful")
        self.game.set_track(tr)
        self._track_source(keep)
        self.obs.set_track(tr)
        self.fill_library()
        self.start.refresh()
        if self.tabs.currentWidget() is not self.game:
            self.tabs.setCurrentWidget(self.arr)
        self.log(f"opened {folder}")

    def _track_source(self, pos=0):
        tr = self.track
        src = None
        if tr:
            try:
                st = tr.stems()
                if st or tr.master():
                    src = A.StemsSource(st, tr.master(), tr.makeup())
            except Exception as e:
                self.log(f"couldn't load the audio: {e}")
        self.src = src
        self.player.set_source(src, pos if src and pos < (src.length or 0) else 0)
        self.now_playing = "track" if src else None
        self.mixer.set_source(tr, src, self.player)

    def play_array(self, x, label="", sr=44100):
        if self.livep.b_play.isChecked():
            self.livep.b_play.setChecked(False)
        self.player.set_source(A.ArraySource(x, sr))
        self.player.play()
        self.now_playing = "audition"
        self.statusBar().showMessage(f"▶ {label}", 4000)

    # ---- transport
    def toggle_play(self):
        if self.player.playing:
            self.player.pause()
            return
        if self.now_playing != "track" and self.track:
            self._track_source(int(self.arrange.play_beat * 60 / self.track.bpm * (self.src.sr if self.src else 44100)))
        if self.now_playing == "track" and self.src is None:
            self.log("This track hasn't been rendered yet: Render (Ctrl+R) or Preview 8 bars.")
            return
        self.player.play()

    def stop(self):
        if self.livep.b_play.isChecked():
            self.livep.b_play.setChecked(False)
        self.player.stop()

    def seek_beat(self, beat):
        if self.track and self.now_playing == "track" and self.src:
            self.player.seek(int(beat * 60 / self.track.bpm * self.src.sr))
        self.arrange.set_playhead(beat, follow=False)
        self.roll.set_playhead(beat)

    def _tick(self):
        self.a_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPause if self.player.playing else QStyle.SP_MediaPlay))
        if self.now_playing == "track" and self.track and self.src:
            sec = self.player.pos / self.src.sr
            beat = sec * self.track.bpm / 60
            self.pos_label.setText(f"  {int(beat // 4) + 1:3d}.{int(beat % 4) + 1}   {fmt_time(sec)} / {fmt_time(self.src.length / self.src.sr)}  ")
            if self.player.playing:
                self.arrange.set_playhead(beat, follow=self.follow.isChecked())
                self.roll.set_playhead(beat)

    # ---- editing and rendering
    def edit_lane(self, name):
        self.edit_lane_quiet(name)
        self.roll.setFocus()

    def edit_lane_quiet(self, name):
        if self.track:
            self.roll.set_part(self.track, name)
            self.roll_title.setText(f"Piano roll — {name}  ({len(self.track.parts.get(name, []))} notes)   "
                                    "double-click add · drag move · edge resize · right-click delete · Alt+wheel velocity · "
                                    "Ctrl+click seek · Ctrl+S save")

    def _edited(self):
        self.arrange.update()
        if self.track:
            self.setWindowTitle(f"*{self.track.title} — Bountiful")

    def save_midi(self):
        if not self.track:
            return
        mid = self.track.save_midi()
        self.setWindowTitle(f"{self.track.title} — Bountiful")
        self.log(f"saved {mid}; render to hear the edits")

    def _need_track(self):
        if not self.track:
            self.log("open a track first")
            return False
        if self.track.dirty:
            self.save_midi()
        return True

    def render(self):
        if not self._need_track():
            return
        tr = self.track
        if self.now_playing == "track":
            self.player.set_source(None)
            self.now_playing = None
        self.log(f"rendering {tr.name} …")
        self.jobs.run(f"rendering {tr.name}", lambda: B.render(tr.folder, log=self.jobs.log),
                      lambda rc: (self.log(f"render finished ({'ok' if rc == 0 else f'exit {rc}'})"), self.open_track(tr.folder)))

    def preview(self):
        if not self._need_track():
            return
        tr = self.track
        b0 = int(self.arrange.play_beat // 4) + 1
        bars = f"{b0}-{min(tr.bars, b0 + 7)}"

        def done(rc):
            p = tr.preview()
            if rc == 0 and p:
                import soundfile as sf
                x, sr = sf.read(str(p), dtype="float32")
                self.play_array(x, f"preview of bars {bars}", sr)
        self.jobs.run(f"previewing bars {bars}", lambda: B.render(tr.folder, bars=bars, log=self.jobs.log), done)

    def bounce(self):
        if not self.src or not hasattr(self.src, "bounce"):
            self.log("render the track first: the mix is made from its stems")
            return
        out = self.track.folder / "exports" / f"{self.track.name}_mix.wav"
        src = A.StemsSource(self.track.stems(), self.track.master(), self.track.makeup())
        src.gain, src.pan, src.mute, src.solo, src.master = dict(self.src.gain), dict(self.src.pan), set(self.src.mute), set(self.src.solo), False
        self.jobs.run("bouncing the mix", lambda: src.bounce(out, log=self.jobs.log))

    def midi_studio(self):
        if not self._need_track():
            return
        studio = paths.ENGINE / "studio" / "midi_studio.py"
        py = paths.PY
        if studio.exists():
            subprocess.Popen([str(py), str(studio), str(self.track.mid), str(self.track.folder / "instruments.toml")], start_new_session=True)
        else:
            self.log(f"MIDI Studio not found at {studio}")

    # ---- settings, updates, about
    def open_setup(self):
        if getattr(self, "setup", None) is None:
            self.setup = SU.SetupDialog(self)
        else:
            self.setup.refresh()
        self.setup.show()
        self.setup.raise_()
        return self.setup

    def set_data(self):
        d = QFileDialog.getExistingDirectory(self, "Where your music lives (tracks, albums, sessions)", str(paths.DATA))
        if d:
            paths.save_config(data=d)
            QMessageBox.information(self, "Bountiful", f"Music folder set to {d}. Restart Bountiful to use it.")

    def check_updates(self, quiet=True):
        def done(st):
            if st["ok"] and st["behind"]:
                rel = st.get("release")
                self.upd_btn.setText(f"⬆ Update to {rel['tag']}" if rel else f"⬆ Update ({st['behind']} new)")
                self.upd_btn.setToolTip("\n".join(st["changes"][:20]))
                self.upd_btn.show()
                if not quiet:
                    self.do_update(st)
            elif not quiet:
                QMessageBox.information(self, "Bountiful updates", st["message"])
        self.jobs.run("" if quiet else "checking for updates", updater.check, done)

    def do_update(self, st=None):
        if st is None or isinstance(st, bool):
            st = updater.check(fetch=False)
        changes = "\n".join(st.get("changes", [])[:25])
        if QMessageBox.question(self, "Update Bountiful",
                                f"{st['message']}\n\n{changes}\n\nUpdate now and restart? (Your music isn't touched.)") != QMessageBox.Yes:
            return

        def done(ok):
            if ok is True and updater.BUNDLE:
                QMessageBox.information(self, "Bountiful", "The new version is downloaded and open. Bountiful closes "
                                        "now so it can be replaced; start it again when that's done.")
                self.close()
            elif ok is True:
                if QMessageBox.question(self, "Bountiful", "Updated. Restart now?") == QMessageBox.Yes:
                    updater.restart()
                    self.close()
            else:
                QMessageBox.warning(self, "Bountiful", "The update didn't finish: see the log.")
        self.logdock.show()
        self.jobs.run("updating", lambda: updater.update(log=self.jobs.log), done)

    def about(self):
        QMessageBox.about(self, "About Bountiful",
                          f"<h2>Bountiful</h2><p>Songs from a Bounty, and the Electronium.</p>"
                          f"<p>Version {updater.version()}<br>Artist: M4S4T0</p>"
                          f"<p>Music: {paths.DATA}<br>Engine: {paths.ENGINE}<br>App: {paths.CODE}</p>")

    def closeEvent(self, e):
        if self.track and self.track.dirty:
            r = QMessageBox.question(self, "Bountiful", f"Save your note edits to {self.track.name}?",
                                     QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                e.ignore()
                return
            if r == QMessageBox.Yes:
                self.save_midi()
        self.mixer.save()
        self.player.close()
        e.accept()


def theme(app: QApplication):
    app.setStyle("Fusion")
    pal = QPalette()
    for role, c in ((QPalette.Window, "#17151f"), (QPalette.WindowText, "#d8d4e8"), (QPalette.Base, "#110f18"),
                    (QPalette.AlternateBase, "#1c1a26"), (QPalette.Text, "#d8d4e8"), (QPalette.Button, "#2a2638"),
                    (QPalette.ButtonText, "#d8d4e8"), (QPalette.Highlight, "#ff9b42"), (QPalette.HighlightedText, "#17151f"),
                    (QPalette.ToolTipBase, "#2a2638"), (QPalette.ToolTipText, "#d8d4e8")):
        pal.setColor(role, QColor(c))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)


def smoke(win: Window, app: QApplication) -> int:
    """Exercise the window without a person: open a track, switch views, edit a note (not saved), plan a song by rules."""
    import tempfile
    import numpy as np
    problems = []
    lib = M.library().get("Tracks", [])
    if lib:
        win.open_track(lib[0])
        if not win.track or not win.track.parts:
            problems.append("track did not load")
        else:
            lane = next(iter(win.track.parts))
            win.edit_lane(lane)
            n0 = len(win.track.parts[lane])
            win.track.parts[lane].append(M.Note(0, 1, 60, 0.8))
            win.roll._changed()
            if len(win.track.parts[lane]) != n0 + 1:
                problems.append("piano roll edit")
            win.track.parts[lane].pop()
            win.track.dirty = False
    for i in range(win.tabs.count()):
        win.tabs.setCurrentIndex(i)
        app.processEvents()
    win.song.bounty.setText("4242")
    win.song.brief.setPlainText("make the break more restless")
    done = []
    win.song.plan(then=lambda: done.append(1))
    A.wait_until(lambda: (app.processEvents(), bool(done))[1], 20)
    if "operator (rules + brief)" not in win.song.out.toPlainText() or win.song.intents.rowCount() < 1:
        problems.append("song plan: " + win.song.out.toPlainText()[:200])
    # the Synthesis Lab: two engines, one routed into an echo with feedback, rendered and looked inside
    lab = win.lab
    lab.new()
    lab.beats.setValue(4)
    a = lab.add("lead", "terrain", "lissajous-lead", "arp")
    lab.add("bells", "material", "cracked-bell", "hits")
    lab.table.selectRow(1)
    lab.r_fb.setValue(0.3)
    lab.route()
    got = []
    lab._rendered = lambda r: got.append(r)
    lab.render()
    A.wait_until(lambda: (app.processEvents(), bool(got))[1], 60)
    if not got or not np.isfinite(got[0][0]).all() or set(got[0][1]) != {"lead", "bells"}:
        problems.append("lab render")
    lab.table.selectRow(0)
    looked = []
    lab._looked = lambda r: looked.append(r)
    lab.look()
    A.wait_until(lambda: (app.processEvents(), bool(looked))[1], 60)
    if a != "lead" or not looked or looked[0][1] is None:
        problems.append("lab look inside (terrain height map)")
    # the Observatory: a track grown from DNA shows its clocks, and a 4-bar passage branches
    import lineage as G
    folder = G.export(G.origin(4242, length="short"), out=Path(tempfile.mkdtemp()) / "obs")
    win.open_track(folder)
    A.wait_until(lambda: (app.processEvents(), bool(win.obs.clock.clocks))[1], 60)
    if not win.obs.clock.clocks or not win.obs.dna:
        problems.append("observatory clocks / dna")
    else:
        win.obs.bar.setValue(5)
        win.obs.count.setValue(4)
        br = []
        win.obs.branch(then=lambda r: br.append(r))
        A.wait_until(lambda: (app.processEvents(), bool(br))[1], 60)
        if not br or isinstance(br[0], Exception) or list(br[0]["passage"]) != [5, 8] or br[0]["considered"] < 1:
            problems.append(f"observatory branch: {br[:1]}")
    # game music: the same track becomes a loop with states and stingers, and the preview switches state and fires one
    gp = win.game
    A.wait_until(lambda: (app.processEvents(), gp.section.count() > 0)[1], 30)
    if not gp.section.count():
        problems.append("game music: no sections")
    gp.bars.setText("5-8")
    made = []
    gp.make(then=lambda r: made.append(r))
    A.wait_until(lambda: (app.processEvents(), bool(made))[1], 300)
    if not made or isinstance(made[0], Exception) or gp.man is None:
        problems.append(f"game music make: {made[:1]}")
    else:
        src = GP.GameSource(win.track.folder / "game", gp.man)
        n = gp.man["loop"]["samples"]
        calm = src.render(0, 4096)
        src.set_state("combat")
        src.stinger("pickup")
        blocks = [src.render(0, 4096) for _ in range(int(3 * n / 4096) // 2)]
        y = np.vstack(blocks)
        if not (np.isfinite(y).all() and np.abs(y).max() <= GP.GM.CEILING + 1e-6 and GP.GM.rms(y[-44100:]) > GP.GM.rms(calm)):
            problems.append("game music preview: combat not louder than calm, or out of range")
        if not all(b.isEnabled() for b in gp.state_btn.values()):
            problems.append("game music: state buttons stay disabled")
    # the Record tab: every record listed, a bar map, and a check that composes one without rendering
    rp = win.record
    if rp.list.topLevelItemCount() != len(RP.R.records()) or not rp.map.lanes or not rp.fields["title"].text():
        problems.append("record tab: list, bar map or fields")
    else:
        rp.map.picked.emit(0)
        ran = []
        rp.run("check", then=lambda rc: ran.append(rc))
        A.wait_until(lambda: (app.processEvents(), bool(ran))[1], 120)
        if ran != [0] or "bar 1:" not in rp.bar_info.text() or rp.changes():
            problems.append(f"record tab check: {ran} {rp.status.text()}")
        # its Sounds page: the record's parts, only allowed libraries, and an instrument to hear
        moss = RP.SS.RECORDS / "moss-radio.toml"
        if moss.exists():
            rp.reload(moss)
            sp = rp.sounds
            voice = next((sp.slots.topLevelItem(i) for i in range(sp.slots.topLevelItemCount())
                          if sp.slots.topLevelItem(i).text(0).startswith("voice ")), None)
            if voice is None:
                problems.append("record sounds: no voices for moss radio")
            else:
                sp.slots.setCurrentItem(voice)
                libs = [sp.lib.itemText(i) for i in range(sp.lib.count())]
                heard = []
                sp.hear(then=lambda r: heard.append(r))
                A.wait_until(lambda: (app.processEvents(), bool(heard))[1], 60)
                if libs != ["gs"] or sp.cands.count() < 100 or not sp.chosen() or not heard \
                        or isinstance(heard[0], Exception) or len(heard[0][0]) < 44100:
                    problems.append(f"record sounds: {libs} {sp.cands.count()} {heard[:1]!r:.80}")
    # the Start page and plain tab names
    if win.tabs.tabText(0) != "Start" or "Game music" not in [win.tabs.tabText(i) for i in range(win.tabs.count())]:
        problems.append("tab names")
    win.show_panel(win.song)
    if win.tabs.tabText(win.tabs.currentIndex()) != "New song":
        problems.append("show_panel through a help page")
    if win.start.recent.count() < 1:
        problems.append("start page recent list")
    # setup: one row per pack and program, matching the report
    su = win.open_setup()
    r = su.report
    if set(su.pack_rows) != set(SU.packs.PACKS) or set(su.tool_rows) != set(SU.SC.TOOLS) \
            or any((su.tool_rows[t][0].text() == SU.OK) != v["ok"] for t, v in r["tools"].items()) \
            or ("Ready" in su.summary.text()) != r["ready"]:
        problems.append(f"setup dialog: {su.summary.text()}")
    su.hide()
    tmp = Path(tempfile.mkdtemp())
    t = M.Track(tmp, "Smoke", 120.0, {"lead": [M.Note(0, 1, 60, 0.8)], "drums": [M.Note(0, 0.25, 36, 0.9)]})
    t.save_midi()
    if [n.p for n in M.load(tmp).parts.get("lead", [])] != [60]:
        problems.append("midi round trip")
    win.close()
    for p in problems:
        print("SMOKE PROBLEM:", p)
    print("smoke ok" if not problems else "smoke failed")
    return 1 if problems else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("track", nargs="?", type=Path)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    QApplication.setApplicationName("Bountiful")
    QApplication.setOrganizationName("M4S4T0")
    QApplication.setDesktopFileName(APP_ID)
    app = QApplication(sys.argv[:1])
    app.setWindowIcon(QIcon(str(LOGO)))
    theme(app)
    win = Window()
    win.show()
    if a.smoke:
        sys.exit(smoke(win, app))
    if a.track:
        win.open_track(a.track)
    if SU.should_show():
        QTimer.singleShot(300, win.open_setup)
    sys.exit(app.exec())


if __name__ == "__main__":
    os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia*=false")
    main()
