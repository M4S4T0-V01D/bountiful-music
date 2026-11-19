"""The Record tab: the Song Spec records in records/ (record_desk.py does the work). Pick one, see it bar by bar, change
its title, key, tempo, swing or seed, make a new take, then check it, test-build it or build it and open it in Arrange."""
from __future__ import annotations

import random
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QScrollArea, QSplitter, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

import record_desk as R
import songspec as SS

CELL, LANE, HEAD, NAMES = 26, 17, 34, 120        # a 4-beat bar, one lane, the section + chord rows, the names column
SECTION_COLORS = ["#ff9b42", "#7fd1c7", "#b48cff", "#f2d06b", "#ff6f91", "#8fc26b", "#6fa8ff", "#d98c5f"]


class BarMap(QWidget):
    """Sections, chords and one lane per player (or drum layer), bar by bar; a click picks a bar."""
    picked = Signal(int)

    def __init__(self):
        super().__init__()
        self.bars, self.lanes, self.sel = [], [], None
        self.setMouseTracking(False)

    def set_bars(self, bars: list[dict]):
        self.bars, self.sel = bars, None
        seen = {}
        for b in bars:
            for p in b["plays"]:
                seen.setdefault(p.partition(":")[0], None)
        self.lanes = list(seen)
        self.x = [NAMES]
        for b in bars:
            self.x.append(self.x[-1] + CELL * b["beats"] / 4)
        self.setFixedSize(self.sizeHint())
        self.update()

    def sizeHint(self):
        return QSize(int(self.x[-1]) + 8 if self.bars else 200, HEAD + LANE * len(self.lanes) + 18)

    def mousePressEvent(self, e):
        x = e.position().x()
        for i in range(len(self.bars)):
            if self.x[i] <= x < self.x[i + 1]:
                self.sel = i
                self.update()
                self.picked.emit(i)

    def paintEvent(self, _):
        if not self.bars:
            return
        p = QPainter(self)
        p.setFont(QFont(p.font().family(), 7))
        secs = list(dict.fromkeys(b["section"] for b in self.bars))
        for row, name in enumerate(["section", "chords"] + self.lanes):
            y = 0 if row == 0 else HEAD - LANE if row == 1 else HEAD + LANE * (row - 2)
            p.setPen(QColor("#8c87a3"))
            p.drawText(QRectF(4, y, NAMES - 8, LANE), Qt.AlignVCenter | Qt.AlignLeft, name)
        for i, b in enumerate(self.bars):
            x0, w = self.x[i], self.x[i + 1] - self.x[i]
            col = QColor(SECTION_COLORS[secs.index(b["section"]) % len(SECTION_COLORS)])
            p.fillRect(QRectF(x0, 0, w - 1, LANE - 2), col.darker(130 if b["bar_in_section"] else 100))
            p.setPen(QColor("#d8d4e8"))
            p.drawText(QRectF(x0, HEAD - LANE, w, LANE), Qt.AlignCenter,
                       p.fontMetrics().elidedText(" ".join(b["chords"]), Qt.ElideRight, int(w) - 2))
            how = {q.partition(":")[0]: q.partition(":")[2] for q in b["plays"]}
            for j, lane in enumerate(self.lanes):
                if lane in how:
                    r = QRectF(x0, HEAD + LANE * j + 1, w - 1, LANE - 2)
                    p.fillRect(r, col.darker(220))
                    if how[lane] and (i == 0 or how[lane] != _how(self.bars[i - 1], lane)):
                        p.setPen(QColor("#d8d4e8"))
                        j = i + 1                       # the name spans the bars that keep it
                        while j < len(self.bars) and _how(self.bars[j], lane) == how[lane]:
                            j += 1
                        span = self.x[j] - x0 - 3
                        p.drawText(QRectF(x0 + 2, r.y(), span, r.height()), Qt.AlignVCenter,
                                   p.fontMetrics().elidedText(how[lane], Qt.ElideRight, int(span)))
            if b["n"] % 4 == 1:
                p.setPen(QColor("#5d5870"))
                p.drawText(QRectF(x0, HEAD + LANE * len(self.lanes), CELL * 2, 16), Qt.AlignVCenter, str(b["n"]))
        p.setPen(QColor("#17151f"))
        for i, b in enumerate(self.bars):                  # names last, so the next bars don't paint over them
            if b["bar_in_section"] == 0:
                p.drawText(QRectF(self.x[i] + 2, 0, CELL * 6, LANE - 2), Qt.AlignVCenter, b["section"])
        if self.sel is not None:
            p.setPen(QPen(QColor("#ff9b42"), 2))
            p.drawRect(QRectF(self.x[self.sel], 0, self.x[self.sel + 1] - self.x[self.sel], self.height() - 18))
        p.end()


def _how(bar: dict, lane: str) -> str | None:
    return next((q.partition(":")[2] for q in bar["plays"] if q.partition(":")[0] == lane), None)


class SoundsPage(QWidget):
    """The record's drum samples and instrument voices; swap one for another cleared sound, after hearing it."""

    def __init__(self, panel):
        super().__init__()
        self.panel, self.S, self.cat = panel, None, []
        self.tmp = Path(tempfile.mkdtemp(prefix="bountiful-hear-"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #8c87a3")
        lay.addWidget(self.note)
        split = QSplitter()
        self.slots = QTreeWidget()
        self.slots.setHeaderLabels(["Part", "Sound", "Label"])
        self.slots.setRootIsDecorated(False)
        self.slots.currentItemChanged.connect(lambda it, _: self.pick_slot())
        split.addWidget(self.slots)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.lib = QComboBox()
        self.lib.setToolTip("only the libraries this record's [sounds] allow, and that fit this part")
        self.lib.currentIndexChanged.connect(self.fill)
        row.addWidget(self.lib)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("filter …")
        self.filter.textChanged.connect(self.fill)
        row.addWidget(self.filter, 1)
        rl.addLayout(row)
        self.cands = QListWidget()
        self.cands.itemDoubleClicked.connect(lambda _: self.hear())
        rl.addWidget(self.cands, 1)
        row = QHBoxLayout()
        self.b_hear = QPushButton("▶ Hear")
        self.b_hear.setToolTip("the sample, or the instrument playing a few notes (double-click does it too)")
        self.b_hear.clicked.connect(self.hear)
        self.b_use = QPushButton("Use this sound")
        self.b_use.setToolTip("write it into the record's TOML; a take gets just this line")
        self.b_use.clicked.connect(self.use)
        row.addWidget(self.b_hear)
        row.addWidget(self.b_use)
        rl.addLayout(row)
        split.addWidget(right)
        split.setSizes([300, 400])
        lay.addWidget(split, 1)

    def load(self, S, keep: tuple | None = None):
        self.S = S
        self.slots.clear()
        found = R.slots(S) if S else []
        for s in found:
            it = QTreeWidgetItem([f"{'drum' if s['kind'] == 'sample' else 'voice'} {s['name']}", s["sound"], s["label"]])
            it.setData(0, Qt.UserRole, s)
            self.slots.addTopLevelItem(it)
            if keep == (s["table"], s["name"]):
                self.slots.setCurrentItem(it)
        for i in range(3):
            self.slots.resizeColumnToContents(i)
        if not S:
            self.note.setText("")
        elif not found:
            self.note.setText(f"{S['meta']['title']} uses the {S['meta'].get('engine', 'spec')} engine: its sounds are "
                              "set in its code, not in the TOML, so there is nothing to swap here.")
        else:
            self.note.setText("Every sound here is cleared for release (the libraries in the record's [sounds] allow). "
                              "Pick a part, then hear and use another sound for it.")
        if found and not self.slots.currentItem():
            self.slots.setCurrentItem(self.slots.topLevelItem(0))
        self.pick_slot()

    def slot(self) -> dict | None:
        it = self.slots.currentItem()
        return it.data(0, Qt.UserRole) if it else None

    def pick_slot(self):
        s = self.slot()
        self.lib.blockSignals(True)
        self.lib.clear()
        if s:
            self.lib.addItems(R.allowed(self.S, s["kind"]))
            lib = s["sound"].partition(":")[0]
            if self.lib.findText(lib) >= 0:
                self.lib.setCurrentText(lib)
        self.lib.blockSignals(False)
        self.fill()

    def fill(self):
        self.cands.clear()
        s, lib = self.slot(), self.lib.currentText()
        self.cat = R.catalog(lib) if s and lib else []
        f = self.filter.text().strip().lower()
        for sid, label in self.cat:
            if f and f not in sid.lower() and f not in label.lower():
                continue
            it = QListWidgetItem(f"{label}    ({sid})" if lib == "gs" else sid.partition(":")[2])
            it.setData(Qt.UserRole, (sid, label))
            self.cands.addItem(it)
            if s and sid == s["sound"]:
                self.cands.setCurrentItem(it)
        if self.cands.currentItem():
            self.cands.scrollToItem(self.cands.currentItem())
        for b in (self.b_hear, self.b_use):
            b.setEnabled(bool(s))

    def chosen(self) -> tuple | None:
        it = self.cands.currentItem()
        return it.data(Qt.UserRole) if it else None

    def hear(self, then=None):
        c = self.chosen() or ((self.slot() or {}).get("sound"), None)
        if not c[0]:
            return
        win = self.panel.win

        def go():
            import soundfile as sf
            return sf.read(str(R.audition(c[0], self.tmp)), dtype="float32")

        def done(r):
            if isinstance(r, Exception):
                self.panel.status.setText(f"can't play {c[0]}: {r}")
            else:
                win.play_array(r[0], c[0], r[1])
            if then:
                then(r)
        win.jobs.run(f"hearing {c[0]}", go, done, done)

    def use(self):
        s, c = self.slot(), self.chosen()
        if not s or not c:
            return None
        try:
            done = R.set_sound(self.panel.path, s["table"], s["name"], c[0], c[1] if c[0].startswith("gs:") else None)
        except (SS.SpecError, OSError) as e:
            self.panel.status.setText(f"not changed: {e}")
            return None
        self.panel.status.setText(f"{s['name']} is now {done}")
        self.panel.reload(self.panel.path)
        self.load(self.panel.S, (s["table"], s["name"]))
        return done


class RecordPanel(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.path, self.S, self.bars, self.last = win, None, None, [], None
        split = QSplitter()
        QVBoxLayout(self).addWidget(split)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.list = QTreeWidget()
        self.list.setHeaderLabels(["Record", "Length", "Engine"])
        self.list.setRootIsDecorated(False)
        self.list.currentItemChanged.connect(lambda it, _: it and self.pick(Path(it.data(0, Qt.UserRole))))
        ll.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, fn in (("Reload", self.reload), ("New take …", self.new_take), ("Open TOML", self.open_toml)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        ll.addLayout(row)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        form = QFormLayout()
        self.fields = {}
        for k, label in (("title", "Title"), ("key", "Key"), ("bpm", "Tempo (bpm)"), ("swing", "Swing (0.5 = straight)"),
                         ("seed", "Seed")):
            e = QLineEdit()
            e.returnPressed.connect(self.save)
            self.fields[k] = e
            if k == "seed":
                box = QHBoxLayout()
                box.addWidget(e, 1)
                dice = QPushButton("🎲")
                dice.setToolTip("another seed: the same song, played another way")
                dice.clicked.connect(lambda _=False, e=e: e.setText(str(random.randrange(1, 2 ** 31 - 1))))
                box.addWidget(dice)
                form.addRow(label, box)
            else:
                form.addRow(label, e)
        rl.addLayout(form)
        self.b_save = QPushButton("Save changes")
        self.b_save.clicked.connect(self.save)
        rl.addWidget(self.b_save)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color: #8c87a3")
        rl.addWidget(self.info)
        self.map = BarMap()
        self.map.picked.connect(self.show_bar)
        scroll = QScrollArea()
        scroll.setWidget(self.map)
        scroll.setMinimumHeight(160)
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(scroll, 1)
        self.bar_info = QLabel("click a bar to see what plays in it")
        self.bar_info.setWordWrap(True)
        pl.addWidget(self.bar_info)
        self.tabs = QTabWidget()
        self.tabs.addTab(page, "Bar map")
        self.sounds = SoundsPage(self)
        self.tabs.addTab(self.sounds, "Sounds")
        rl.addWidget(self.tabs, 1)
        row = QHBoxLayout()
        self.b_run = {}
        for mode, text, tip in (("check", "✓ Check", "compose it and check it, without rendering"),
                                ("test", "Test build", "build it as \"<title> spec test\", in its own folder"),
                                ("build", "● Build record", "build the record: MIDI, render, mix and master")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, m=mode: self.run(m))
            self.b_run[mode] = b
            row.addWidget(b)
        row.addStretch(1)
        self.b_open = QPushButton("Open in Arrange")
        self.b_open.clicked.connect(self.open_built)
        row.addWidget(self.b_open)
        b = QPushButton("Open folder")
        b.clicked.connect(lambda: self.last and QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last))))
        row.addWidget(b)
        rl.addLayout(row)
        self.status = QLabel()
        rl.addWidget(self.status)
        split.addWidget(right)
        split.setSizes([260, 700])
        self.reload()

    # ---- the list
    def reload(self, keep: Path | None = None):
        keep = keep or self.path
        self.list.clear()
        pick = None
        for r in R.records():
            if r["error"]:
                it = QTreeWidgetItem([f"⚠ {r['title']}", "", ""])
                it.setToolTip(0, r["error"])
            else:
                m, s = divmod(round(r["seconds"]), 60)
                it = QTreeWidgetItem([("↳ " if r["extends"] else "") + r["title"], f"{m}:{s:02d}", r["engine"]])
                it.setToolTip(0, f"{r['path'].name}" + (f", a take on {r['extends']}" if r["extends"] else ""))
            it.setData(0, Qt.UserRole, str(r["path"]))
            self.list.addTopLevelItem(it)
            if keep and r["path"] == keep:
                pick = it
        for i in range(3):
            self.list.resizeColumnToContents(i)
        if pick or self.list.topLevelItemCount():
            self.list.setCurrentItem(pick or self.list.topLevelItem(0))

    def pick(self, path: Path):
        self.path = path
        try:
            self.S = SS.load(path)
            self.bars = R.bar_map(self.S)
            s = R.summary(self.S)
        except Exception as e:
            self.S, self.bars = None, []
            self.map.set_bars([])
            self.sounds.load(None)
            self.info.setText(f"{path.name} doesn't load: {e}")
            return
        for k, e in self.fields.items():
            e.setText(f"{s[k]:g}" if isinstance(s[k], float) else str(s[k]))
        m, sec = divmod(round(s["seconds"]), 60)
        self.info.setText(f"{s['genre']}  ·  {s['bars']} bars, {m}:{sec:02d}  ·  {s['engine']} engine, "
                          f"{s['backend']} render" + (f"  ·  a take on {s['extends']}" if s["extends"] else "") + "\n" +
                          "  →  ".join(f"{n} {b}" for n, b, _ in s["sections"]))
        self.map.set_bars(self.bars)
        self.sounds.load(self.S)
        self.last = R.track_dir(self.S, "build")
        self.b_open.setEnabled(R.final_wav(self.last) is not None)

    def show_bar(self, i: int):
        b = self.bars[i]
        self.bar_info.setText(f"bar {b['n']}: {b['section']} bar {b['bar_in_section'] + 1}, {b['beats']} beats  ·  "
                              f"{' '.join(b['chords'])}  ·  " + ", ".join(b["plays"]))

    # ---- changing it
    def changes(self) -> dict:
        s = R.summary(self.S)
        return {k: e.text() for k, e in self.fields.items()
                if e.text().strip() != (f"{s[k]:g}" if isinstance(s[k], float) else str(s[k]))}

    def save(self) -> bool:
        if not self.S:
            return False
        ch = self.changes()
        if not ch:
            return True
        try:
            done = R.set_meta(self.path, ch)
        except (SS.SpecError, OSError) as e:
            self.status.setText(f"not saved: {e}")
            return False
        self.status.setText("saved " + ", ".join(f"{k} = {v}" for k, v in done.items()))
        self.reload(self.path)
        return True

    def new_take(self, title: str | None = None):
        if not self.S:
            return None
        if title is None:
            title, ok = QInputDialog.getText(self, "New take", f"A new take on {self.S['meta']['title']}, called:",
                                             text=f"{self.S['meta']['title']} take 2")
            if not ok:
                return None
        try:
            out = R.new_take(self.path, title)
        except (SS.SpecError, OSError) as e:
            self.status.setText(f"no new take: {e}")
            return None
        self.status.setText(f"new take: records/{out.name}")
        self.reload(out)
        return out

    def open_toml(self):
        if self.path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path)))

    # ---- building it
    def run(self, mode: str, then=None):
        if not self.S or not self.save():
            return
        cmd, folder, log = R.command(self.path, mode), R.track_dir(self.S, mode), self.win.jobs.log
        for b in self.b_run.values():
            b.setEnabled(False)
        self.status.setText(f"{self.b_run[mode].text().strip('✓● ')} {self.S['meta']['title']} … (the log has the details)")

        def go():
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(SS.ROOT))
            for line in p.stdout:
                log(line.rstrip())
            return p.wait()

        def done(rc):
            for b in self.b_run.values():
                b.setEnabled(True)
            if isinstance(rc, Exception) or rc != 0:
                self.status.setText(f"{mode} failed ({rc if isinstance(rc, Exception) else f'exit {rc}'}); see the log")
            elif mode == "check":
                self.status.setText(f"{self.S['meta']['title']} checks out")
            else:
                self.last = folder
                wav = R.final_wav(folder)
                self.b_open.setEnabled(wav is not None)
                self.status.setText(f"built {folder.name}" + (f": {wav.name}" if wav else ", but it has no WAV"))
            if then:
                then(rc)
        self.win.jobs.run(f"{mode} {self.S['meta']['title']}", go, done, done)

    def open_built(self):
        if self.last and R.final_wav(self.last):
            self.win.open_track(self.last)
