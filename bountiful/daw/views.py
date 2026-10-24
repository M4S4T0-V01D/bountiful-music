"""The DAW's editing views: arrangement (lanes and sections), piano roll (edit notes), mixer (the stems)."""
from __future__ import annotations

import json

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QDial, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QSlider,
                               QVBoxLayout, QWidget)

from . import model as M

BG = QColor("#15131c")
BG2 = QColor("#1c1a26")
GRID = QColor("#2a2736")
GRID2 = QColor("#3a3650")
TEXT = QColor("#d8d4e8")
DIM = QColor("#8c87a3")
ACCENT = QColor("#ff9b42")
SECTION = {"intro": "#3b5b8c", "verse": "#3f7a5a", "prechorus": "#7a6a3f", "chorus": "#8c3b5b", "bridge": "#5b3b8c", "outro": "#3b6a8c"}


class ArrangeView(QWidget):
    """Every part as a lane, the song's sections on top, the playhead. Click to seek, double-click a lane to edit it."""
    seek = Signal(float)
    laneSelected = Signal(str)
    laneOpened = Signal(str)

    HEAD, RULER, SECT = 120, 22, 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self.track: M.Track | None = None
        self.ppb = 7.0
        self.x0 = 0.0
        self.play_beat = 0.0
        self.sel: str | None = None
        self.setMinimumHeight(200)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_track(self, tr):
        self.track, self.x0 = tr, 0.0
        if tr:
            self.ppb = max(2.0, min(14.0, (self.width() - self.HEAD - 20) / max(16.0, tr.beats)))
        self.update()

    def set_playhead(self, beat: float, follow: bool = True):
        self.play_beat = beat
        if follow:
            vis = (self.width() - self.HEAD) / self.ppb
            if not self.x0 <= beat < self.x0 + vis * 0.92:
                self.x0 = max(0.0, beat - vis * 0.1)
        self.update()

    def lanes(self) -> list[str]:
        return list(self.track.parts) if self.track else []

    def lane_h(self) -> float:
        n = max(1, len(self.lanes()))
        return max(18.0, min(48.0, (self.height() - self.RULER - self.SECT) / n))

    def bx(self, beat: float) -> float:
        return self.HEAD + (beat - self.x0) * self.ppb

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        W, H = self.width(), self.height()
        p.fillRect(self.rect(), BG)
        if not self.track:
            p.setPen(DIM)
            p.drawText(self.rect(), Qt.AlignCenter, "Open a track from the library, or make one: Song from a Bounty, Live, A day of ideas")
            return
        tr = self.track
        top = self.RULER + self.SECT
        lh = self.lane_h()
        # bars
        step = max(1, int(round(40 / (4 * self.ppb))))
        step = next(s for s in (1, 2, 4, 8, 16, 32, 64) if s >= step)
        f = QFont(self.font())
        f.setPointSizeF(8)
        p.setFont(f)
        for bar in range(0, tr.bars + 1):
            x = self.bx(bar * 4)
            if x < self.HEAD or x > W:
                continue
            p.setPen(GRID2 if bar % 4 == 0 else GRID)
            p.drawLine(int(x), self.RULER, int(x), H)
            if bar % step == 0:
                p.setPen(DIM)
                p.drawText(int(x) + 3, 15, str(bar + 1))
        # sections
        for s in tr.sections:
            x1, x2 = self.bx((s["start"] - 1) * 4), self.bx((s["start"] - 1 + s["bars"]) * 4)
            if x2 < self.HEAD or x1 > W:
                continue
            x1 = max(x1, self.HEAD)
            c = QColor(SECTION.get(s.get("kind", ""), "#4a4660"))
            p.fillRect(QRectF(x1, self.RULER, x2 - x1 - 1, self.SECT - 2), c)
            p.setPen(TEXT)
            p.drawText(QRectF(x1 + 4, self.RULER, x2 - x1 - 6, self.SECT - 2), Qt.AlignVCenter | Qt.AlignLeft, s["name"])
        # lanes
        for i, name in enumerate(self.lanes()):
            y = top + i * lh
            notes = tr.parts[name]
            col = QColor(M.color(name))
            if name == self.sel:
                p.fillRect(QRectF(self.HEAD, y, W - self.HEAD, lh), QColor(255, 255, 255, 14))
            p.setPen(GRID)
            p.drawLine(self.HEAD, int(y + lh), W, int(y + lh))
            if notes:
                lo = min(n.p for n in notes)
                hi = max(n.p for n in notes)
                span = max(12, hi - lo + 1)
                b0, b1 = self.x0, self.x0 + (W - self.HEAD) / self.ppb
                p.setPen(Qt.NoPen)
                for n in notes:
                    if n.t + n.d < b0 or n.t > b1:
                        continue
                    ny = y + 3 + (1 - (n.p - lo + 1) / span) * (lh - 8)
                    c = QColor(col)
                    c.setAlphaF(0.45 + 0.55 * n.v)
                    p.setBrush(c)
                    p.drawRect(QRectF(self.bx(n.t), ny, max(1.5, n.d * self.ppb - 0.5), max(2.0, (lh - 8) / span * 1.6)))
            # header
            p.fillRect(QRectF(0, y, self.HEAD, lh), BG2 if name != self.sel else QColor("#2a2638"))
            p.fillRect(QRectF(0, y, 4, lh), col)
            p.setPen(TEXT)
            p.drawText(QRectF(10, y, self.HEAD - 14, lh), Qt.AlignVCenter, f"{name}")
            p.setPen(DIM)
            p.drawText(QRectF(10, y, self.HEAD - 14, lh), Qt.AlignVCenter | Qt.AlignRight, str(len(notes)))
        p.fillRect(QRectF(0, 0, self.HEAD, top), BG2)
        p.setPen(DIM)
        p.drawText(QRectF(8, 0, self.HEAD, self.RULER), Qt.AlignVCenter, f"{tr.bpm:g} bpm")
        p.drawText(QRectF(8, self.RULER, self.HEAD, self.SECT), Qt.AlignVCenter, f"{tr.bars} bars")
        # playhead
        x = self.bx(self.play_beat)
        if x >= self.HEAD:
            p.setPen(QPen(ACCENT, 2))
            p.drawLine(int(x), 0, int(x), H)

    def _lane_at(self, y):
        top = self.RULER + self.SECT
        i = int((y - top) // self.lane_h())
        lanes = self.lanes()
        return lanes[i] if 0 <= i < len(lanes) and y >= top else None

    def mousePressEvent(self, e):
        if not self.track:
            return
        pos = e.position()
        if pos.x() < self.HEAD:
            ln = self._lane_at(pos.y())
            if ln:
                self.sel = ln
                self.laneSelected.emit(ln)
                self.update()
            return
        beat = max(0.0, self.x0 + (pos.x() - self.HEAD) / self.ppb)
        ln = self._lane_at(pos.y())
        if ln:
            self.sel = ln
            self.laneSelected.emit(ln)
        self.seek.emit(round(beat * 4) / 4)

    def mouseDoubleClickEvent(self, e):
        ln = self._lane_at(e.position().y())
        if ln:
            self.laneOpened.emit(ln)

    def wheelEvent(self, e):
        d = e.angleDelta().y() or e.angleDelta().x()
        if e.modifiers() & Qt.ControlModifier:
            at = self.x0 + (e.position().x() - self.HEAD) / self.ppb
            self.ppb = max(1.0, min(80.0, self.ppb * (1.15 if d > 0 else 1 / 1.15)))
            self.x0 = max(0.0, at - (e.position().x() - self.HEAD) / self.ppb)
        else:
            self.x0 = max(0.0, self.x0 - d / 120 * 16 * (8 / self.ppb))
        self.update()


class PianoRoll(QWidget):
    """One part's notes. Double-click: add; drag: move; drag the right edge: length; right-click or Delete: remove;
    Alt+wheel over a note: velocity. Wheel scrolls (Shift: sideways), Ctrl+wheel zooms."""
    changed = Signal()
    seek = Signal(float)

    KEYS = 46

    def __init__(self, parent=None):
        super().__init__(parent)
        self.track: M.Track | None = None
        self.part: str | None = None
        self.ppb = 28.0
        self.kh = 9.0
        self.x0 = 0.0
        self.top_p = 84
        self.snap = 0.25
        self.sel: list[M.Note] = []
        self.drag = None
        self.last_len = 1.0
        self.play_beat = 0.0
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumHeight(220)

    def set_part(self, tr, part):
        self.track, self.part, self.sel = tr, part, []
        ns = self.notes()
        if ns:
            mid = sorted(n.p for n in ns)[len(ns) // 2]
            self.top_p = int(mid + (self.height() / self.kh) / 2)
            self.x0 = max(0.0, ns[0].t - 1)
        self.update()

    def notes(self) -> list[M.Note]:
        return self.track.parts.get(self.part, []) if self.track and self.part else []

    def set_playhead(self, beat):
        self.play_beat = beat
        vis = (self.width() - self.KEYS) / self.ppb
        if self.isVisible() and not self.x0 <= beat < self.x0 + vis * 0.92:
            self.x0 = max(0.0, beat - vis * 0.1)
        self.update()

    def bx(self, b):
        return self.KEYS + (b - self.x0) * self.ppb

    def py(self, p):
        return (self.top_p - p) * self.kh

    def at(self, pos) -> tuple[float, int]:
        return self.x0 + (pos.x() - self.KEYS) / self.ppb, int(self.top_p - pos.y() // self.kh)

    def hit(self, pos):
        b, p = self.at(pos)
        for n in reversed(self.notes()):
            if n.p == p and n.t <= b <= n.t + n.d:
                edge = self.bx(n.t + n.d) - pos.x() < 6
                return n, edge
        return None, False

    def paintEvent(self, _):
        p = QPainter(self)
        W, H = self.width(), self.height()
        p.fillRect(self.rect(), BG)
        if not self.part:
            p.setPen(DIM)
            p.drawText(self.rect(), Qt.AlignCenter, "Double-click a lane in the arrangement to edit its notes here")
            return
        lo = int(self.top_p - H / self.kh) - 1
        for q in range(lo, self.top_p + 1):
            y = self.py(q)
            black = q % 12 in (1, 3, 6, 8, 10)
            p.fillRect(QRectF(self.KEYS, y, W, self.kh), QColor("#18161f") if black else BG)
            if q % 12 == 0:
                p.setPen(GRID2)
                p.drawLine(self.KEYS, int(y + self.kh), W, int(y + self.kh))
        b1 = self.x0 + (W - self.KEYS) / self.ppb
        b = int(self.x0 / self.snap) * self.snap
        while b <= b1:
            x = self.bx(b)
            p.setPen(GRID2 if b % 4 == 0 else (GRID if b % 1 == 0 else QColor("#1f1c29")))
            p.drawLine(int(x), 0, int(x), H)
            if b % 4 == 0:
                p.setPen(DIM)
                p.drawText(int(x) + 3, 11, str(int(b // 4) + 1))
            b += self.snap
        col = QColor(M.color(self.part))
        for n in self.notes():
            if n.t + n.d < self.x0 or n.t > b1 or not lo <= n.p <= self.top_p:
                continue
            c = QColor(col)
            c.setAlphaF(0.35 + 0.65 * n.v)
            r = QRectF(self.bx(n.t), self.py(n.p) + 0.5, max(3.0, n.d * self.ppb - 1), self.kh - 1)
            p.setBrush(c)
            p.setPen(QPen(QColor("#ffffff"), 1.5) if n in self.sel else QPen(c.darker(160), 1))
            p.drawRoundedRect(r, 2, 2)
        # keyboard
        for q in range(lo, self.top_p + 1):
            y = self.py(q)
            black = q % 12 in (1, 3, 6, 8, 10)
            p.fillRect(QRectF(0, y, self.KEYS, self.kh), QColor("#2b2838") if black else QColor("#d9d6e6"))
            p.setPen(QColor("#555"))
            p.drawLine(0, int(y + self.kh), self.KEYS, int(y + self.kh))
            if q % 12 == 0 and self.kh >= 8:
                p.setPen(QColor("#333"))
                f = QFont(self.font())
                f.setPointSizeF(7)
                p.setFont(f)
                p.drawText(QRectF(2, y, self.KEYS - 4, self.kh), Qt.AlignVCenter | Qt.AlignRight, f"C{q // 12 - 1}")
        x = self.bx(self.play_beat)
        if x >= self.KEYS:
            p.setPen(QPen(ACCENT, 2))
            p.drawLine(int(x), 0, int(x), H)

    def _snap(self, b):
        return max(0.0, round(b / self.snap) * self.snap)

    def mousePressEvent(self, e):
        if not self.part:
            return
        pos = e.position()
        if pos.x() < self.KEYS:
            return
        n, edge = self.hit(pos)
        if e.button() == Qt.RightButton:
            if n:
                self.notes().remove(n)
                self.sel = [s for s in self.sel if s is not n]
                self._changed()
            return
        if n:
            if not e.modifiers() & Qt.ShiftModifier and n not in self.sel:
                self.sel = [n]
            elif e.modifiers() & Qt.ShiftModifier:
                self.sel = [s for s in self.sel if s is not n] if n in self.sel else self.sel + [n]
            b, q = self.at(pos)
            self.drag = ("len" if edge else "move", b, q, [(s, s.t, s.p, s.d) for s in self.sel])
        else:
            self.sel = []
            if e.modifiers() & Qt.ControlModifier:
                self.seek.emit(self._snap(self.at(pos)[0]))
        self.update()

    def mouseMoveEvent(self, e):
        pos = e.position()
        if not self.drag:
            n, edge = self.hit(pos)
            self.setCursor(Qt.SizeHorCursor if edge else (Qt.PointingHandCursor if n else Qt.ArrowCursor))
            return
        kind, b0, q0, orig = self.drag
        b, q = self.at(pos)
        db = round((b - b0) / self.snap) * self.snap
        for (n, t, p, d) in orig:
            if kind == "move":
                n.t, n.p = max(0.0, t + db), max(0, min(127, p + (q - q0)))
            else:
                n.d = max(self.snap, d + db)
                self.last_len = n.d
        self.track.dirty = True
        self.update()

    def mouseReleaseEvent(self, e):
        if self.drag:
            self.drag = None
            self.notes().sort(key=lambda n: (n.t, n.p))
            self._changed()

    def mouseDoubleClickEvent(self, e):
        if not self.part or e.position().x() < self.KEYS:
            return
        n, _ = self.hit(e.position())
        if n:
            return
        b, q = self.at(e.position())
        t = self.snap * int(max(0.0, b) / self.snap)
        new = M.Note(t, self.last_len, q, 0.8)
        self.track.parts[self.part].append(new)
        self.notes().sort(key=lambda n: (n.t, n.p))
        self.sel = [new]
        self._changed()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.sel:
            for n in self.sel:
                if n in self.notes():
                    self.notes().remove(n)
            self.sel = []
            self._changed()
        elif e.key() in (Qt.Key_Up, Qt.Key_Down) and self.sel:
            k = (12 if e.modifiers() & Qt.ShiftModifier else 1) * (1 if e.key() == Qt.Key_Up else -1)
            for n in self.sel:
                n.p = max(0, min(127, n.p + k))
            self._changed()
        elif e.key() == Qt.Key_A and e.modifiers() & Qt.ControlModifier:
            self.sel = list(self.notes())
            self.update()
        else:
            super().keyPressEvent(e)

    def wheelEvent(self, e):
        d = e.angleDelta().y() or e.angleDelta().x()
        if e.modifiers() & Qt.AltModifier:
            n, _ = self.hit(e.position())
            for x in ([n] if n and n not in self.sel else self.sel):
                x.v = max(0.05, min(1.0, x.v + (0.05 if d > 0 else -0.05)))
            self._changed()
        elif e.modifiers() & Qt.ControlModifier:
            self.ppb = max(4.0, min(200.0, self.ppb * (1.15 if d > 0 else 1 / 1.15)))
        elif e.modifiers() & Qt.ShiftModifier:
            self.x0 = max(0.0, self.x0 - d / 120 * 4 * (28 / self.ppb))
        else:
            self.top_p = max(20, min(127, self.top_p + (3 if d > 0 else -3)))
        self.update()

    def _changed(self):
        self.track.dirty = True
        self.changed.emit()
        self.update()


class Meter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = 0.0
        self.hold = 0.0
        self.setFixedWidth(8)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

    def set(self, v):
        self.level = max(v, self.level * 0.82)
        self.hold = max(v, self.hold - 0.01)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        H = self.height()
        p.fillRect(self.rect(), QColor("#0f0e14"))
        import math
        db = 20 * math.log10(max(1e-5, self.level))
        h = H * max(0.0, min(1.0, (db + 48) / 48))
        c = QColor("#5fd38d") if db < -9 else (QColor("#e8c547") if db < -1 else QColor("#ff5a4f"))
        p.fillRect(QRectF(0, H - h, self.width(), h), c)


class Strip(QFrame):
    def __init__(self, name, mixer, master=False):
        super().__init__()
        self.name, self.mixer = name, mixer
        self.setFrameShape(QFrame.StyledPanel)
        self.setFixedWidth(78)
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(3)
        lab = QLabel(name)
        lab.setAlignment(Qt.AlignCenter)
        lab.setStyleSheet(f"color: {M.color(name) if not master else '#ff9b42'}; font-weight: bold")
        v.addWidget(lab)
        self.pan = QDial()
        self.pan.setRange(-100, 100)
        self.pan.setFixedSize(40, 40)
        self.pan.setNotchesVisible(True)
        self.pan.setToolTip("pan (double-click: centre)")
        self.pan.valueChanged.connect(self._send)
        if not master:
            v.addWidget(self.pan, 0, Qt.AlignHCenter)
        mid = QHBoxLayout()
        self.fader = QSlider(Qt.Vertical)
        self.fader.setRange(-600, 120)
        self.fader.setValue(0)
        self.fader.setToolTip("gain (dB)")
        self.fader.valueChanged.connect(self._send)
        self.meter = Meter()
        mid.addWidget(self.fader)
        mid.addWidget(self.meter)
        v.addLayout(mid, 1)
        self.db = QLabel("0.0 dB")
        self.db.setAlignment(Qt.AlignCenter)
        v.addWidget(self.db)
        row = QHBoxLayout()
        self.m = QPushButton("M")
        self.s = QPushButton("S")
        for b, tip in ((self.m, "mute"), (self.s, "solo")):
            b.setCheckable(True)
            b.setFixedWidth(30)
            b.setStyleSheet("padding: 3px 0")
            b.setToolTip(tip)
            b.toggled.connect(self._send)
            row.addWidget(b)
        if not master:
            v.addLayout(row)

    def _send(self, *_):
        self.db.setText(f"{self.fader.value() / 10:+.1f} dB")
        self.mixer.strip_changed(self)

    def state(self):
        return {"db": self.fader.value() / 10, "pan": self.pan.value() / 100, "mute": self.m.isChecked(), "solo": self.s.isChecked()}

    def restore(self, st):
        for w in (self.fader, self.pan, self.m, self.s):
            w.blockSignals(True)
        self.fader.setValue(int(st.get("db", 0) * 10))
        self.pan.setValue(int(st.get("pan", 0) * 100))
        self.m.setChecked(bool(st.get("mute")))
        self.s.setChecked(bool(st.get("solo")))
        for w in (self.fader, self.pan, self.m, self.s):
            w.blockSignals(False)
        self._send()


class Mixer(QWidget):
    """A strip per stem: gain, pan, mute, solo, meter, and the master. 'Master export' plays the mastered file instead.
    The settings are kept in the track's mixer.json."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.src = None
        self.track = None
        self.strips: dict[str, Strip] = {}
        outer = QVBoxLayout(self)
        top = QHBoxLayout()
        self.use_master = QCheckBox("Play the mastered export (not the stems)")
        self.use_master.toggled.connect(self._master_toggled)
        top.addWidget(self.use_master)
        top.addStretch(1)
        self.info = QLabel("")
        self.info.setStyleSheet("color: #8c87a3")
        top.addWidget(self.info)
        outer.addLayout(top)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.inner = QWidget()
        self.row = QHBoxLayout(self.inner)
        self.row.setAlignment(Qt.AlignLeft)
        self.area.setWidget(self.inner)
        outer.addWidget(self.area, 1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._meters)
        self.timer.start(50)
        self.player = None

    def set_source(self, track, src, player):
        self.track, self.src, self.player = track, src, player
        while self.row.count():
            w = self.row.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.strips = {}
        if src is None or not hasattr(src, "files"):
            self.info.setText("Render the track to mix its stems." if track else "")
            return
        for k in src.files:
            st = Strip(k, self)
            self.strips[k] = st
            self.row.addWidget(st)
        self.master = Strip("master", self, master=True)
        self.row.addWidget(self.master)
        saved = {}
        try:
            saved = json.loads((track.folder / "mixer.json").read_text())
        except (FileNotFoundError, ValueError):
            ...
        for k, st in self.strips.items():
            st.restore(saved.get(k, {}))
        self.master.restore(saved.get("master", {}))
        self.use_master.blockSignals(True)
        self.use_master.setChecked(bool(saved.get("_use_master")) or not src.files)
        self.use_master.blockSignals(False)
        src.master = self.use_master.isChecked()
        self.info.setText(f"{len(src.files)} stems at {src.sr} Hz")

    def strip_changed(self, st):
        if not self.src or not hasattr(self.src, "files"):
            return
        with self.src.lock:
            if st.name == "master":
                self.player.volume = 10 ** (st.fader.value() / 200)
            else:
                k = st.name
                self.src.gain[k] = 10 ** (st.fader.value() / 200)
                self.src.pan[k] = st.pan.value() / 100
                (self.src.mute.add if st.m.isChecked() else self.src.mute.discard)(k)
                (self.src.solo.add if st.s.isChecked() else self.src.solo.discard)(k)
        self.save()

    def _master_toggled(self, on):
        if self.src and hasattr(self.src, "files"):
            self.src.master = on
            self.player.invalidate()
            self.save()

    def save(self):
        if self.track and self.strips:
            d = {k: st.state() for k, st in self.strips.items()}
            d["master"] = self.master.state()
            d["_use_master"] = self.use_master.isChecked()
            try:
                (self.track.folder / "mixer.json").write_text(json.dumps(d, indent=1))
            except OSError:
                ...

    def _meters(self):
        if not self.player or not self.strips or not self.isVisible():
            return
        m = self.player.meters() if self.player.playing else {}
        for k, st in self.strips.items():
            st.meter.set(m.get(k, 0.0))
        self.master.meter.set(m.get("master", 0.0))

