"""The DAW's music-making panels: Song from a Bounty (the operator: the rules, bent by your brief), the live Electronium
console with its ideas (audition, rate: your taste), and A day of ideas."""
from __future__ import annotations

import json
import threading
import traceback

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSlider, QSpinBox,
                               QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

import batch as BA
import build as B
import electronium as EL
import electronium_song as ES
import live as LV
import operator_ as OP
import paths
import taste

from . import audio as A

KEYS = ["auto"] + [f"{n} {m}" for m in ("minor", "major") for n in ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")]
MONO = QFont("monospace")
MONO.setStyleHint(QFont.Monospace)


class Jobs(QObject):
    """Run slow things off the GUI thread; their results come back on it."""
    _done = Signal(object, object)
    logged = Signal(str)
    busy = Signal(str)

    def __init__(self):
        super().__init__()
        self._done.connect(lambda cb, r: cb(r) if cb else None)
        self.running = 0

    def log(self, s: str):
        self.logged.emit(str(s))

    def run(self, what: str, fn, done=None, fail=None):
        self.running += 1
        self.busy.emit(what)

        def go():
            try:
                r = fn()
                self.running -= 1
                self._done.emit(done, r)
            except Exception as e:
                self.running -= 1
                self.log(f"{what} failed: {e}\n{traceback.format_exc(limit=4)}")
                self._done.emit(fail, e)
            self.busy.emit("")
        threading.Thread(target=go, daemon=True).start()


def key_arg(combo: QComboBox) -> str | None:
    return None if combo.currentText() == "auto" else combo.currentText()


def bounty_arg(s: str):
    s = s.strip() or "1969"
    return int(s) if s.lstrip("-").isdigit() else s


# ------------------------------------------------------------------ song from a Bounty

class SongPanel(QWidget):
    """A whole song from a Bounty: the plan (key, tempo, chords, sections), the operator's moves, then the track."""

    def __init__(self, win):
        super().__init__()
        self.win, self.jobs = win, win.jobs
        self.op = None
        self.pl = None
        lay = QHBoxLayout(self)
        left = QWidget()
        form = QFormLayout(left)
        self.bounty = QLineEdit("1969")
        self.bounty.setToolTip("any number or word: the same Bounty always gives the same song")
        self.key = QComboBox()
        self.key.addItems(KEYS)
        self.bpm = QSpinBox()
        self.bpm.setRange(0, 200)
        self.bpm.setSpecialValueText("auto")
        self.length = QComboBox()
        self.length.addItems(list(ES.LAYOUTS))
        self.length.setCurrentText("normal")
        self.reharm = QDoubleSpinBox()
        self.reharm.setRange(0, 1)
        self.reharm.setSingleStep(0.05)
        self.reharm.setValue(0.25)
        self.reharm.setToolTip("how often a chord is coloured: sevenths, relative substitutes, secondary dominants")
        self.title = QLineEdit()
        self.title.setPlaceholderText("(from the Bounty)")
        form.addRow("Bounty", self.bounty)
        dice = QPushButton("🎲 Any Bounty")
        dice.clicked.connect(self._dice)
        form.addRow("", dice)
        form.addRow("Key", self.key)
        form.addRow("Tempo", self.bpm)
        form.addRow("Length", self.length)
        form.addRow("Colour", self.reharm)
        form.addRow("Title", self.title)
        og = QGroupBox("The operator (who plays the knobs)")
        ol = QVBoxLayout(og)
        ol.addWidget(QLabel("The rules play the classic arc. Your brief, read by code, bends it:"))
        self.brief = QPlainTextEdit()
        self.brief.setPlaceholderText("e.g. 'make the break more restless, keep the Rhodes intimate, "
                                      "let the last two minutes open into something huge'")
        self.brief.setMaximumHeight(70)
        self.brief.textChanged.connect(self._stale)
        ol.addWidget(self.brief)
        self.intents = QTableWidget(0, 4)
        self.intents.setHorizontalHeaderLabels(["Use", "Words", "Who / where", "Controls"])
        self.intents.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.intents.verticalHeader().hide()
        self.intents.setMaximumHeight(150)
        self.intents.setToolTip("what the brief became: untick a row to reject it, then Plan again to compare")
        self.intents.itemChanged.connect(self._toggled)
        ol.addWidget(self.intents)
        form.addRow(og)
        row = QHBoxLayout()
        self.b_plan = QPushButton("Plan")
        self.b_plan.setToolTip("decide key, chords and sections, and let the operator plan its moves (you can read them first)")
        self.b_make = QPushButton("Make song")
        self.b_render = QPushButton("Make && render")
        self.b_render.setObjectName("primary")
        for b in (self.b_plan, self.b_make, self.b_render):
            row.addWidget(b)
        self.b_plan.clicked.connect(lambda: self.plan())
        self.b_make.clicked.connect(lambda: self.make(False))
        self.b_render.clicked.connect(lambda: self.make(True))
        form.addRow(row)
        left.setMaximumWidth(460)
        lay.addWidget(left)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setFont(MONO)
        self.out.setPlaceholderText("The plan appears here: chords, sections and every move the operator makes, and why.")
        lay.addWidget(self.out, 1)
        for w in (self.bounty, self.title):
            w.textChanged.connect(self._stale)
        for w in (self.key, self.length):
            w.currentTextChanged.connect(self._stale)
        self.bpm.valueChanged.connect(self._stale)
        self.reharm.valueChanged.connect(self._stale)

    def _dice(self):
        import random
        self.bounty.setText(str(random.randint(1000, 99999)))

    def _stale(self, *_):
        self.op = None
        self._kept = None

    def _toggled(self, item):
        if item.column() == 0 and self.op is not None:
            row = item.row()
            its = self.op.get("intents", [])
            if row < len(its):
                its[row]["on"] = item.checkState() == Qt.Checked
                self._kept = its
                self.op = None

    def _show_intents(self, its: list[dict]):
        import intent as IN
        self.intents.blockSignals(True)
        self.intents.setRowCount(len(its))
        for i, it in enumerate(its):
            use = QTableWidgetItem()
            use.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            use.setCheckState(Qt.Checked if it.get("on", True) else Qt.Unchecked)
            self.intents.setItem(i, 0, use)
            who = ", ".join(IN.ROLE_PART.get(t, t) for t in it["targets"]) or "everyone"
            ex = IN.explain(it).split(": ", 1)[-1]
            for c, txt in ((1, f'{it["word"]}  ({it["clause"]})'), (2, f'{who} / {it["scope"]}'), (3, ex)):
                cell = QTableWidgetItem(txt)
                cell.setFlags(Qt.ItemIsEnabled)
                cell.setToolTip(IN.explain(it))
                self.intents.setItem(i, c, cell)
        self.intents.resizeColumnsToContents()
        self.intents.blockSignals(False)

    def args(self):
        return dict(bounty=bounty_arg(self.bounty.text()), key=key_arg(self.key), bpm=self.bpm.value() or None,
                    length=self.length.currentText(), reharm=self.reharm.value())

    def plan(self, then=None):
        a = self.args()
        brief = self.brief.toPlainText().strip()
        kept = getattr(self, "_kept", None)
        self._kept = None
        self.out.setPlainText(f"Planning Bounty {a['bounty']} ...")

        def work():
            pl = ES.plan(**a)
            op = OP.operate(pl["sections"], EL.patch(pl["patch"]), brief, log=self.jobs.log, bpm=pl["bpm"], intents=kept)
            return pl, op

        def done(r):
            self.pl, self.op = r
            pl = self.pl
            secs = sum(s["bars"] for s in pl["sections"]) * 4 * 60 / pl["bpm"]
            lines = [f"{self.title.text() or pl['title']} — Bounty {a['bounty']}: {pl['key']}, {pl['bpm']:g} bpm, "
                     f"{int(secs // 60)}:{secs % 60:04.1f}", "", "Chords:"]
            lines += [f"  {k}: {ES.chord_text(v, pl['tonic'], pl['mode'])}" for k, v in pl["loops"].items()]
            lines += ["", "Sections:"] + [f"  {s['start']:3d}-{s['start'] + s['bars'] - 1:3d}  {s['name']:12s} {', '.join(s['parts'])}"
                                          for s in pl["sections"]]
            lines += ["", OP.text(self.op)]
            if self.op.get("problems"):
                lines += ["", "dropped: " + "; ".join(self.op["problems"])]
            self.out.setPlainText("\n".join(lines))
            self._show_intents(self.op.get("intents", []))
            if then:
                then()
        self.jobs.run("planning", work, done)

    def make(self, render: bool):
        if self.op is None:
            return self.plan(then=lambda: self.make(render))
        a, op = self.args(), self.op
        title = self.title.text().strip() or None

        def work():
            t = ES.song(**a, title=title, operator=op, log=lambda *_: None)
            if render:
                self.jobs.log(f"rendering {t.name} (a few minutes) ...")
                B.render(t, log=self.jobs.log)
            return t
        self.jobs.run("rendering" if render else "writing the song", work, self.win.open_track)


# ------------------------------------------------------------------ the live Electronium

class Knob(QWidget):
    """A labelled slider for one machine knob (operator_.RANGES), sent as a move when you let go."""

    def __init__(self, knob: str, value: float, send):
        super().__init__()
        self.knob, self.send = knob, send
        lo, hi = OP.RANGES[knob]
        self.lo, self.hi = lo, hi
        self.integer = isinstance(lo, int) and isinstance(hi, int)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.lab = QLabel(knob)
        self.lab.setFixedWidth(70)
        self.s = QSlider(Qt.Horizontal)
        self.s.setRange(0, 100 if not self.integer else hi - lo)
        self.val = QLabel()
        self.val.setFixedWidth(36)
        self.set(value)
        self.s.valueChanged.connect(lambda _: self.val.setText(self._fmt()))
        self.s.sliderReleased.connect(self._send)
        self.s.actionTriggered.connect(lambda a: QTimer.singleShot(0, self._send) if not self.s.isSliderDown() else None)
        h.addWidget(self.lab)
        h.addWidget(self.s, 1)
        h.addWidget(self.val)

    def value(self):
        return self.lo + self.s.value() if self.integer else round(self.lo + (self.hi - self.lo) * self.s.value() / 100, 3)

    def set(self, v):
        self.s.blockSignals(True)
        v = float(v if v is not None else self.lo)
        self.s.setValue(int(round(v - self.lo)) if self.integer else int(round((v - self.lo) / (self.hi - self.lo) * 100)))
        self.s.blockSignals(False)
        self.val.setText(self._fmt())

    def _fmt(self):
        v = self.value()
        return f"{v:+d}" if self.integer and self.lo < 0 else f"{v:g}"

    def _send(self):
        self.send(self.knob, self.value())


class LivePanel(QWidget):
    """The Electronium playing live: turn its knobs, mute channels, change gates; every change from the next bar on,
    recorded as a move. Make the take into a song, and judge its ideas (your taste)."""

    def __init__(self, win):
        super().__init__()
        self.win, self.jobs = win, win.jobs
        self.live: LV.Live | None = None
        self.src: A.LiveSource | None = None
        self.ideas: list[dict] = []
        outer = QVBoxLayout(self)
        top = QHBoxLayout()
        self.bounty = QLineEdit("1969")
        self.bounty.setMaximumWidth(120)
        self.key = QComboBox()
        self.key.addItems(KEYS)
        self.bpm = QSpinBox()
        self.bpm.setRange(0, 200)
        self.bpm.setSpecialValueText("auto")
        self.b_load = QPushButton("Load")
        self.b_load.clicked.connect(self.load)
        self.b_play = QPushButton("▶ Play live")
        self.b_play.setObjectName("primary")
        self.b_play.setCheckable(True)
        self.b_play.toggled.connect(self.play)
        for w in (QLabel("Bounty"), self.bounty, QLabel("Key"), self.key, QLabel("Tempo"), self.bpm, self.b_load, self.b_play):
            top.addWidget(w)
        top.addStretch(1)
        self.where = QLabel("")
        self.where.setStyleSheet("font-size: 15px; color: #ff9b42")
        top.addWidget(self.where)
        outer.addLayout(top)
        split = QSplitter(Qt.Horizontal)
        outer.addWidget(split, 1)
        # knobs
        kn = QWidget()
        kl = QVBoxLayout(kn)
        g = QGroupBox("The machine")
        self.gl = QVBoxLayout(g)
        kl.addWidget(g)
        self.chbox = QGroupBox("Channels")
        self.cl = QGridLayout(self.chbox)
        kl.addWidget(self.chbox)
        kl.addStretch(1)
        split.addWidget(kn)
        # moves + take
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.addWidget(QLabel("Your moves (they play from the next bar, and go into the song):"))
        self.moves = QPlainTextEdit()
        self.moves.setReadOnly(True)
        self.moves.setFont(MONO)
        ml.addWidget(self.moves, 1)
        r = QHBoxLayout()
        clear = QPushButton("Forget my moves")
        clear.clicked.connect(self.clear_moves)
        mk = QPushButton("Make this take a song")
        mk.setToolTip("the song with the operator's moves and yours, as a track (then render it)")
        mk.clicked.connect(lambda: self.make(False))
        mkr = QPushButton("… and render")
        mkr.clicked.connect(lambda: self.make(True))
        for w in (clear, mk, mkr):
            r.addWidget(w)
        ml.addLayout(r)
        split.addWidget(mid)
        # ideas
        idw = QWidget()
        il = QVBoxLayout(idw)
        il.addWidget(QLabel("Its ideas, best first. Audition them, and tell it what you like:"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["#", "score", "shape"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setFont(MONO)
        self.table.doubleClicked.connect(lambda _: self.audition())
        il.addWidget(self.table, 1)
        r2 = QHBoxLayout()
        aud = QPushButton("▶ Audition")
        aud.clicked.connect(self.audition)
        up = QPushButton("👍 Like")
        up.clicked.connect(lambda: self.rate(1))
        dn = QPushButton("👎 Not for me")
        dn.clicked.connect(lambda: self.rate(-1))
        for w in (aud, up, dn):
            r2.addWidget(w)
        il.addLayout(r2)
        self.taste = QLabel(taste.report())
        self.taste.setWordWrap(True)
        self.taste.setStyleSheet("color: #8c87a3")
        il.addWidget(self.taste)
        split.addWidget(idw)
        split.setSizes([380, 380, 420])
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(120)

    def load(self):
        was = self.b_play.isChecked()
        if was:
            self.b_play.setChecked(False)
        b, k, t = bounty_arg(self.bounty.text()), key_arg(self.key), self.bpm.value() or None
        self.where.setText("thinking …")

        def done(lv):
            self.live, self.load_args = lv, (b, k, t)
            self._build_knobs()
            self._ideas()
            self.where.setText(f"{lv.pl['title']} · {lv.pl['key']} · {lv.pl['bpm']:g} bpm · {lv.bars} bars")
            if was:
                self.b_play.setChecked(True)
        self.jobs.run("loading the Electronium", lambda: LV.Live(b, k, t, lookahead_bars=1), done)

    def _clear(self, layout):
        while layout.count():
            it = layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _build_knobs(self):
        p = EL.patch(self.live.pl["patch"])
        self._clear(self.gl)
        for k in ("density", "mutation", "gravity", "up", "accent", "legato", "modify", "transpose"):
            self.gl.addWidget(Knob(k, p.get(k, 0), lambda kn, v: self.turn(kn, v)))
        self._clear(self.cl)
        for i, (name, ch) in enumerate(self.live.chans.items()):
            mute = QCheckBox(name)
            mute.setChecked(True)
            mute.setToolTip(f"{ch['role']}: untick to mute from the next bar")
            mute.toggled.connect(lambda on, n=name: self.turn("mute", not on, n))
            gate = QLineEdit(str(ch.get("gate") or ""))
            gate.setPlaceholderText(str(p.get("gate") or "the patch's"))
            gate.setToolTip("its gate: when it plays (p1-p12 rhythms, cN clocks, rN random, | & ~)")
            gate.returnPressed.connect(lambda g=gate, n=name: self.turn("gate", g.text().strip(), n))
            dens = Knob("density", ch.get("density", p.get("density", 0.7)), lambda kn, v, n=name: self.turn(kn, v, n))
            dens.lab.setText("dens")
            dens.lab.setFixedWidth(34)
            self.cl.addWidget(mute, i, 0)
            self.cl.addWidget(gate, i, 1)
            self.cl.addWidget(dens, i, 2)
        self._show_moves()

    def turn(self, knob, value, channel=None):
        if not self.live:
            return
        try:
            self.live.turn(knob, value, channel)
        except ValueError as e:
            self.jobs.log(f"the machine can't: {e}")
            return
        self._show_moves()

    def _show_moves(self):
        if not self.live:
            return
        self.moves.setPlainText("\n".join(f"bar {m['bar']:3d}  {m.get('channel', 'all'):9s} " + ", ".join(f"{k}={v}" for k, v in m["set"].items())
                                          for m in self.live.user_moves) or "(none yet: turn something)")

    def clear_moves(self):
        if self.live:
            with self.live.lock:
                self.live.user_moves = []
                self.live.dirty = True
            self._show_moves()

    def play(self, on):
        if on:
            if not self.live:
                self.load()
                self.b_play.setChecked(False)
                return
            self.src = A.LiveSource(self.live)
            self.win.player.set_source(self.src)
            self.win.player.play()
            self.win.now_playing = "live"
            self.b_play.setText("■ Stop")
        else:
            if self.win.now_playing == "live":
                self.win.player.set_source(None)
                self.win.now_playing = None
            self.src = None
            self.b_play.setText("▶ Play live")

    def _tick(self):
        if self.src is not None and self.live is not None and self.win.player.playing:
            at = self.src.bar_at(self.win.player.pos)
            if at:
                b, bty = at
                s = self.live.section_at(b)
                self.where.setText(f"Bounty {bty} · bar {b + 1}/{self.live.bars} · {s['name']}")

    def make(self, render):
        if not self.live:
            return
        lv = self.live
        op = dict(lv.op, moves=lv.moves())
        pl = lv.pl
        b, k, bpm = self.load_args if str(self.load_args[0]) == str(pl["bounty"]) else (pl["bounty"], None, None)

        def work():
            t = ES.song(b, k, bpm, pl["length"], pl["reharm"], operator=op, log=lambda *_: None)
            if render:
                B.render(t, log=self.jobs.log)
            return t
        self.jobs.run("making the take a song", work, self.win.open_track)

    # ---- ideas and your taste
    def _ideas(self):
        p = EL.patch(self.live.pl["patch"])
        ideas = sorted(EL.think(p), key=lambda d: -d["score"])[:24]
        self.ideas = ideas
        self.table.setRowCount(len(ideas))
        for r, i in enumerate(ideas):
            for c, v in enumerate((str(i["n"]), f"{i['score']:+.2f}", EL.notation(i["cells"]))):
                self.table.setItem(r, c, QTableWidgetItem(v))
        self.table.resizeColumnsToContents()

    def _idea(self):
        r = self.table.currentRow()
        return self.ideas[r] if 0 <= r < len(self.ideas) else None

    def audition(self):
        i = self._idea()
        if not i or not self.live:
            return
        if self.b_play.isChecked():
            self.b_play.setChecked(False)
        pl = self.live.pl
        x = taste.audition(i, pl["tonic"], pl["mode"], pl["bpm"], EL.tone(self.live.chans["lead"]))
        self.win.play_array(x, f"idea {i['n']}")

    def rate(self, r):
        i = self._idea()
        if not i or not self.live:
            return
        n = taste.rate(i, r, self.live.pl["bounty"])
        self.taste.setText(taste.report())
        self.jobs.log(f"rated idea {i['n']} {'+' if r > 0 else '-'}; {n} ratings")
        self.table.selectRow(min(self.table.rowCount() - 1, self.table.currentRow() + 1))


# ------------------------------------------------------------------ a day of ideas

class DayPanel(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.jobs = win, win.jobs
        self.rows: list[dict] = []
        self.dir = None
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.count = QSpinBox()
        self.count.setRange(2, 500)
        self.count.setValue(30)
        self.start = QSpinBox()
        self.start.setRange(0, 10 ** 9)
        self.start.setSpecialValueText("today's")
        self.songs = QSpinBox()
        self.songs.setRange(0, 20)
        self.songs.setValue(3)
        self.render = QCheckBox("render them")
        go = QPushButton("Make a day of ideas")
        go.setObjectName("primary")
        go.clicked.connect(self.make)
        for w in (QLabel("Bounties"), self.count, QLabel("from"), self.start, QLabel("whole songs for the best"), self.songs,
                  self.render, go):
            top.addWidget(w)
        top.addStretch(1)
        self.sessions = QComboBox()
        self.sessions.setMinimumWidth(200)
        self.sessions.currentIndexChanged.connect(self.show_session)
        top.addWidget(QLabel("Session"))
        top.addWidget(self.sessions)
        lay.addLayout(top)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["#", "Bounty", "Title", "Key", "BPM", "Score", "Best idea", "Song"])
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.doubleClicked.connect(lambda _: self.audition())
        lay.addWidget(self.table, 1)
        r = QHBoxLayout()
        for text, fn in (("▶ Audition its best idea", self.audition), ("👍", lambda: self.rate(1)), ("👎", lambda: self.rate(-1)),
                         ("Open / make its song", self.song), ("Take it to Song", self.to_song), ("Play it live", self.to_live)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            r.addWidget(b)
        r.addStretch(1)
        lay.addLayout(r)
        self.refresh()

    def refresh(self, select=None):
        self.sessions.blockSignals(True)
        self.sessions.clear()
        for d in BA.sessions():
            self.sessions.addItem(d.name, str(d))
        self.sessions.blockSignals(False)
        if select:
            self.sessions.setCurrentText(select.name)
        self.show_session()

    def show_session(self, *_):
        d = self.sessions.currentData()
        self.rows = []
        if d:
            from pathlib import Path
            self.dir = Path(d)
            try:
                self.rows = json.loads((self.dir / "index.json").read_text())["rows"]
            except (FileNotFoundError, ValueError, KeyError):
                self.rows = []
        self.table.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            vals = [r["rank"], r["bounty"], r["title"], r["key"], f"{r['bpm']:g}", f"{r['score']:+.2f}",
                    EL.notation(r["ideas"][0]["cells"]) if r["ideas"] else "", r.get("track", "")]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c == 6:
                    it.setFont(MONO)
                self.table.setItem(i, c, it)
        self.table.resizeColumnsToContents()

    def make(self):
        n, st, k, rd = self.count.value(), self.start.value() or None, self.songs.value(), self.render.isChecked()
        self.jobs.run("making a day of ideas", lambda: BA.day(n, st, k, rd, log=self.jobs.log), lambda d: self.refresh(d))

    def _row(self):
        i = self.table.currentRow()
        return self.rows[i] if 0 <= i < len(self.rows) else None

    def audition(self):
        r = self._row()
        if r and r.get("audition") and self.dir:
            import soundfile as sf
            x, sr = sf.read(str(self.dir / r["audition"]), dtype="float32")
            self.win.play_array(x, f"{r['title']}: best idea", sr)

    def rate(self, v):
        r = self._row()
        if r and r["ideas"]:
            idea = {"n": r["ideas"][0]["n"], "cells": [tuple(c) for c in r["ideas"][0]["cells"]]}
            n = taste.rate(idea, v, r["bounty"])
            self.jobs.log(f"rated Bounty {r['bounty']}'s idea {'+' if v > 0 else '-'}; {n} ratings")
            self.table.selectRow(min(self.table.rowCount() - 1, self.table.currentRow() + 1))

    def song(self):
        r = self._row()
        if not r:
            return
        if r.get("track") and (self.dir / r["track"]).exists():
            return self.win.open_track(self.dir / r["track"])
        t = self.dir / f"{r['rank']:02d}-{B.slug(r['title'])}"

        def done(path):
            r["track"] = path.name
            idx = json.loads((self.dir / "index.json").read_text())
            idx["rows"] = self.rows
            (self.dir / "index.json").write_text(json.dumps(idx, indent=1))
            self.show_session()
            self.win.open_track(path)
        self.jobs.run("writing the song", lambda: ES.song(r["bounty"], out=t, log=lambda *_: None), done)

    def to_song(self):
        r = self._row()
        if r:
            self.win.song.bounty.setText(str(r["bounty"]))
            self.win.show_panel(self.win.song)

    def to_live(self):
        r = self._row()
        if r:
            self.win.livep.bounty.setText(str(r["bounty"]))
            self.win.show_panel(self.win.livep)
            self.win.livep.load()
