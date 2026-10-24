"""The Observatory tab: ideas, the producer's notebook, the world model's clocks over a spectrum, ratings, and
branching a 4-bar passage. The data comes from bountiful/observatory.py; this file only draws it."""
from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QDoubleSpinBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSpinBox, QSplitter,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

import lineage as G
import observatory as O

KIND = {"intro": "#3b4a6b", "verse": "#3d5f4f", "pre": "#6b5a2f", "chorus": "#8a4a2a", "bridge": "#5a3d6b",
        "break": "#2f4f5f", "drop": "#9a3040", "outro": "#3b4a6b"}
BG, GRID, TEXT, HOT = QColor("#110f18"), QColor("#2a2736"), QColor("#a9a4c0"), QColor("#ff9b42")


def heat(db: float, lo: float = -70.0, hi: float = -15.0) -> QColor:
    t = max(0.0, min(1.0, (db - lo) / (hi - lo)))
    return QColor(int(17 + t * 238), int(15 + t * 140), int(24 + t * 42 * (1 - t) + 20 * t))


def table(cols: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setSelectionMode(QTableWidget.SingleSelection)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.horizontalHeader().setSectionResizeMode(len(cols) - 1, QHeaderView.Stretch)
    return t


def fill(t: QTableWidget, rows: list[list]):
    t.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            it = QTableWidgetItem("" if v is None else f"{v:.3f}" if isinstance(v, float) else str(v))
            t.setItem(r, c, it)
    t.resizeColumnsToContents()


class ClockView(QWidget):
    """Bars left to right: sections, chords, energy and lead activity, then a third-octave heat map of the mix."""
    barClicked = Signal(int)

    def __init__(self):
        super().__init__()
        self.clocks, self.spectra, self.mark = [], None, None
        self.setMinimumHeight(220)

    def set(self, clocks, spectra=None):
        self.clocks, self.spectra = clocks or [], spectra
        self.update()

    def set_mark(self, a, b):
        self.mark = (a, b)
        self.update()

    def _bw(self):
        return max(1e-6, (self.width() - 8) / max(1, len(self.clocks)))

    def mousePressEvent(self, e):
        if self.clocks:
            self.barClicked.emit(max(1, min(len(self.clocks), int((e.position().x() - 4) / self._bw()) + 1)))

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), BG)
        if not self.clocks:
            p.setPen(TEXT)
            p.drawText(self.rect(), Qt.AlignCenter, "Open a track to see its clocks and spectrum")
            return
        bw, x0, h = self._bw(), 4, self.height()
        top, chord_y, en_y, en_h = 4, 24, 42, 46
        heat_y = en_y + en_h + 6
        for k, c in enumerate(self.clocks):               # sections
            x = x0 + k * bw
            if c["in_section"] == 1 or k == 0:
                n = next((j for j, d in enumerate(self.clocks[k + 1:], 1) if d["in_section"] == 1), len(self.clocks) - k)
                r = QRectF(x, top, n * bw - 1, 17)
                p.fillRect(r, QColor(KIND.get(c["kind"], "#3a3650")))
                p.setPen(QColor("#e8e4f8"))
                p.drawText(r.adjusted(3, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, c["section"])
        p.setPen(TEXT)                                      # chords, when they change and there is room
        last, last_x = None, -99
        for k, c in enumerate(self.clocks):
            x = x0 + k * bw
            if c["chord"] and c["chord"] != last and x - last_x > 34:
                p.drawText(QRectF(x, chord_y, 60, 14), Qt.AlignLeft, c["chord"])
                last, last_x = c["chord"], x
        p.fillRect(QRectF(x0, en_y, len(self.clocks) * bw, en_h), QColor("#16141e"))
        peak = max(1, max(c["lead"] for c in self.clocks))
        for k, c in enumerate(self.clocks):                 # lead activity under the energy line
            hgt = en_h * c["lead"] / peak * 0.6
            p.fillRect(QRectF(x0 + k * bw, en_y + en_h - hgt, max(1, bw - 1), hgt), QColor("#3a3a5a"))
        p.setPen(QPen(HOT, 2))
        pts = [(x0 + (k + 0.5) * bw, en_y + en_h * (1 - c["energy"])) for k, c in enumerate(self.clocks)]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            p.drawLine(int(ax), int(ay), int(bx), int(by))
        if self.spectra and self.spectra["db"]:              # the mix, bar by bar, low bands at the bottom
            rows, nb = self.spectra["db"], len(self.spectra["bands"])
            bh = max(1.0, (h - heat_y - 4) / nb)
            for k, row in enumerate(rows[:len(self.clocks)]):
                for j, v in enumerate(row):
                    p.fillRect(QRectF(x0 + k * bw, h - 4 - (j + 1) * bh, bw + 0.5, bh + 0.5), heat(v))
        else:
            p.setPen(TEXT)
            p.drawText(QRectF(0, heat_y, self.width(), h - heat_y), Qt.AlignCenter, "render the track to see its spectrum")
        p.setPen(QPen(GRID, 1))
        for k, c in enumerate(self.clocks):
            if c["phrase"] == 1:
                x = int(x0 + k * bw)
                p.drawLine(x, en_y, x, en_y + en_h)
        if self.mark:
            a, b = self.mark
            p.fillRect(QRectF(x0 + (a - 1) * bw, 0, (b - a + 1) * bw, h), QColor(255, 155, 66, 50))
            p.setPen(QPen(HOT, 1))
            p.drawRect(QRectF(x0 + (a - 1) * bw, 1, (b - a + 1) * bw, h - 2))


class SpectrumView(QWidget):
    def __init__(self):
        super().__init__()
        self.s = None
        self.setMinimumHeight(140)

    def set(self, s):
        self.s = s
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), BG)
        p.setPen(TEXT)
        if not self.s:
            p.drawText(self.rect(), Qt.AlignCenter, "no rendered mix yet")
            return
        db, bands = self.s["db"], self.s["bands"]
        w, h, lo, hi = self.width(), self.height() - 16, -80.0, -10.0
        bw = w / len(db)
        for k, v in enumerate(db):
            t = max(0.0, min(1.0, (v - lo) / (hi - lo)))
            p.fillRect(QRectF(k * bw + 1, h * (1 - t), bw - 2, h * t), heat(v))
        for k, f in enumerate(bands):
            if k % 6 == 0:
                p.drawText(QRectF(k * bw, h, 60, 16), Qt.AlignLeft, f"{f / 1000:g}k" if f >= 1000 else f"{f:g}")


class HistoryView(QWidget):
    """Judged totals (orange) and ratings out of five (white), in the order they were given."""

    def __init__(self):
        super().__init__()
        self.rows = []
        self.setMinimumHeight(140)

    def set(self, rows):
        self.rows = rows or []
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), BG)
        p.setPen(TEXT)
        if not self.rows:
            p.drawText(self.rect(), Qt.AlignCenter, "no ratings yet: rate an idea, or save discoveries")
            return
        w, h, n = self.width() - 8, self.height() - 8, len(self.rows)
        for k, r in enumerate(self.rows):
            x = 4 + (k + 0.5) * w / n
            for v, col in ((r.get("total"), HOT), (None if r.get("rating") is None else r["rating"] / 5, QColor("#e8e4f8"))):
                if v is not None:
                    p.setBrush(col)
                    p.setPen(Qt.NoPen)
                    p.drawEllipse(QRectF(x - 3, 4 + h * (1 - v) - 3, 6, 6))


class ObservatoryPanel(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.track = None
        self.dna = None
        self.data = {}
        self.ideas, self.branches = [], []
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.title = QLabel("No track open: ideas and ratings only")
        self.title.setStyleSheet("color: #8c87a3")
        b = QPushButton("Refresh")
        b.clicked.connect(self.refresh)
        top.addWidget(self.title, 1)
        top.addWidget(b)
        lay.addLayout(top)
        split = QSplitter(Qt.Vertical)
        self.clock = ClockView()
        self.clock.barClicked.connect(self._bar)
        split.addWidget(self.clock)
        tabs = QTabWidget()
        split.addWidget(tabs)
        split.setSizes([300, 360])
        lay.addWidget(split, 1)

        # ideas
        w = QWidget()
        v = QVBoxLayout(w)
        self.t_ideas = table(["id", "where", "total", "rating", "idea"])
        v.addWidget(self.t_ideas, 1)
        row = QHBoxLayout()
        self.stars = QDoubleSpinBox()
        self.stars.setRange(0, 5)
        self.stars.setSingleStep(0.5)
        self.stars.setValue(4)
        rb = QPushButton("Rate")
        rb.clicked.connect(self.rate)
        ob = QPushButton("Open as a track")
        ob.clicked.connect(lambda: self.open_dna(self._picked(self.t_ideas, self.ideas)))
        row.addWidget(QLabel("stars"))
        row.addWidget(self.stars)
        row.addWidget(rb)
        row.addStretch(1)
        row.addWidget(ob)
        v.addLayout(row)
        tabs.addTab(w, "Ideas")

        # the producer
        self.t_prod = table(["session", "round", "kept", "score", "change", "verdict"])
        self.t_prod.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.t_prod.horizontalHeader().setSectionResizeMode(5, QHeaderView.Interactive)
        tabs.addTab(self.t_prod, "Producer")

        # branching
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        self.bar = QSpinBox()
        self.bar.setRange(1, 999)
        self.bar.valueChanged.connect(self._mark)
        self.count = QSpinBox()
        self.count.setRange(1, O.MAX_BRANCHES)
        self.count.setValue(12)
        self.seed = QSpinBox()
        self.seed.setRange(0, 99999)
        self.b_branch = QPushButton("Branch these 4 bars")
        self.b_branch.setObjectName("primary")
        self.b_branch.clicked.connect(self.branch)
        for lab, wd in (("from bar", self.bar), ("children", self.count), ("seed", self.seed)):
            row.addWidget(QLabel(lab))
            row.addWidget(wd)
        row.addWidget(self.b_branch)
        row.addStretch(1)
        v.addLayout(row)
        self.branch_info = QLabel("Click a bar above, or pick one, then branch: every child differs only in those 4 bars.")
        self.branch_info.setStyleSheet("color: #8c87a3")
        v.addWidget(self.branch_info)
        self.t_branch = table(["#", "id", "front", "total", "what changed"])
        v.addWidget(self.t_branch, 1)
        row = QHBoxLayout()
        sb = QPushButton("Keep in the family tree")
        sb.clicked.connect(self.keep_branch)
        ob = QPushButton("Open as a track")
        ob.clicked.connect(lambda: self.open_dna(self._picked(self.t_branch, self.branches)))
        row.addStretch(1)
        row.addWidget(sb)
        row.addWidget(ob)
        v.addLayout(row)
        tabs.addTab(w, "Branch a passage")

        # ratings and spectrum
        w = QWidget()
        hl = QHBoxLayout(w)
        self.history = HistoryView()
        self.spec = SpectrumView()
        for lab, wd in (("Ratings history (white: your stars / 5, orange: judged total)", self.history),
                        ("The mix, third octaves", self.spec)):
            box = QVBoxLayout()
            t = QLabel(lab)
            t.setStyleSheet("color: #8c87a3")
            box.addWidget(t)
            box.addWidget(wd, 1)
            hl.addLayout(box, 1)
        tabs.addTab(w, "Ratings && spectrum")

    # ---- data
    def set_track(self, track):
        self.track = track
        self.refresh()

    def refresh(self):
        tr = self.track

        def go():
            out = {"ideas": O.ideas(), "ratings": O.ratings()}
            if tr is not None:
                out["dna"] = O.dna_of(tr.folder)
                song = O.song_of(tr.folder)
                out["clocks"] = O.clocks(song) if song else []
                out["producer"] = O.producer(tr.folder)
                wav = tr.master() or tr.preview()
                if wav:
                    out["spectra"] = O.bar_spectra(wav, tr.bpm)
                    out["spectrum"] = O.spectrum(wav, secs=30)
            return out
        self.win.jobs.run("reading the observatory", go, self._refreshed, self._refreshed)

    def _refreshed(self, d):
        if isinstance(d, Exception):
            return
        self.data = d
        self.ideas = d["ideas"]
        fill(self.t_ideas, [[i["id"], i["where"] + (f" #{i['rank']}" if i["rank"] else ""), i["total"], i["rating"],
                             i["describe"]] for i in self.ideas])
        self.history.set(d["ratings"])
        self.dna = d.get("dna")
        self.clock.set(d.get("clocks"), d.get("spectra"))
        self.spec.set(d.get("spectrum"))
        fill(self.t_prod, [[r["session"], r["round"], "kept" if r["kept"] else "refused",
                            f"{r['before']} -> {r['after']}", r["change"], r["verdict"]] for r in d.get("producer", [])])
        if self.track is not None:
            self.title.setText(f"{self.track.title}  ·  " + (f"DNA {G.dna_id(self.dna)}" if self.dna else "no DNA: branching off")
                               + f"  ·  {len(d.get('producer', []))} producer changes")
            self.bar.setMaximum(max(1, len(d.get("clocks") or [1])))
        self.b_branch.setEnabled(self.dna is not None)
        self._mark()

    def _bar(self, b):
        self.bar.setValue(b)

    def _mark(self, *_):
        if self.clock.clocks:
            a = self.bar.value()
            self.clock.set_mark(a, min(len(self.clock.clocks), a + O.PASSAGE - 1))

    @staticmethod
    def _picked(t: QTableWidget, rows: list):
        r = t.currentRow()
        return rows[r]["dna"] if 0 <= r < len(rows) else None

    # ---- actions
    def rate(self):
        dna = self._picked(self.t_ideas, self.ideas)
        if dna:
            O.rate(dna, self.stars.value())
            self.refresh()

    def branch(self, then=None):
        if not self.dna:
            return
        dna, bar, n, seed = self.dna, self.bar.value(), self.count.value(), self.seed.value()
        t0 = time.time()

        def done(r):
            if not isinstance(r, Exception):
                self.branches = r["presented"]
                fill(self.t_branch, [[k + 1, c["id"], c["front"], c["total"], c["describe"].split(": ", 1)[-1]]
                                     for k, c in enumerate(self.branches)])
                rej = ", ".join(f"{v} {k}" for k, v in r["rejected"].items()) or "none"
                self.branch_info.setText(f"bars {r['passage'][0]}-{r['passage'][1]}: {r['considered']} children, "
                                         f"{len(self.branches)} shown, rejected {rej}  ({time.time() - t0:.1f} s)")
            if then:
                then(r)
        self.win.jobs.run(f"branching bars {bar}-{bar + O.PASSAGE - 1}", lambda: O.branch(dna, bar, n=n, seed=seed), done, done)

    def keep_branch(self):
        r = self.t_branch.currentRow()
        if 0 <= r < len(self.branches):
            c = self.branches[r]
            G.save(c["dna"], scores=c["scores"], total=c["total"], note=f"branched bars from {self.bar.value()}")
            self.refresh()

    def open_dna(self, dna):
        if dna:
            self.win.jobs.run("writing the track", lambda: G.export(dna), self.win.open_track)
