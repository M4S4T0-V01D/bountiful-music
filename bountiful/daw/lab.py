"""The Synthesis Lab: patch Bountiful's experimental engines (synthesis/) into a project, play it, look inside the
engines, route one into another, capture snapshots, and take the tracks into a song. Projects are
synthesis/project.py files (.bflab); their tracks are the same tables a song's instruments.toml uses."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
                               QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

import paths
import synthesis as S
from synthesis import project as P

from .panels import MONO

ROUTE_INTO = ("echo", "ghost", "prismatic", "weather", "oracle")      # engines that listen to their input well


def projects_dir() -> Path:
    return paths.DATA / "synthesis" / "projects"


def inspect(eng) -> str:
    """What an engine shows of itself after playing: its display hooks and diagnostics, as text."""
    out = []
    for hook in ("pattern_info", "memory_map", "describe_source"):
        if hasattr(eng, hook):
            try:
                out.append(f"{hook}: {json.dumps(getattr(eng, hook)(), default=str)[:900]}")
            except Exception as e:                                    # a display never breaks the Lab
                out.append(f"{hook}: unavailable ({e})")
    if isinstance(getattr(eng, "energy", None), (list, np.ndarray)) and len(eng.energy):
        out.append("energy: " + " ".join(f"{float(v):.3g}" for v in list(eng.energy)[:16]))
    if hasattr(eng, "diagnostics"):
        out.append(f"diagnostics: {json.dumps(eng.diagnostics(), default=str)[:600]}")
    return "\n".join(out) or "(this engine has nothing to show)"


def height_image(rows: list, px: int = 160) -> QPixmap:
    a = np.asarray(rows, float)
    a = (a - a.min()) / (np.ptp(a) or 1.0)
    g = np.ascontiguousarray((a * 255).astype(np.uint8))
    img = QImage(g.data, g.shape[1], g.shape[0], g.shape[1], QImage.Format_Grayscale8).copy()
    return QPixmap.fromImage(img).scaled(px, px, Qt.KeepAspectRatio, Qt.FastTransformation)


class LabPanel(QWidget):
    COLS = ("track", "engine", "preset", "gain", "pan", "mute")

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.proj = P.new("lab", 120, 1)
        self.path: Path | None = None
        self.mix = None
        self._filling = False
        v = QVBoxLayout(self)

        top = QHBoxLayout()
        self.name = QLineEdit(self.proj["name"])
        self.bpm = QDoubleSpinBox(); self.bpm.setRange(40, 220); self.bpm.setValue(120)
        self.seed = QSpinBox(); self.seed.setRange(0, 2 ** 31 - 1); self.seed.setValue(1)
        self.beats = QSpinBox(); self.beats.setRange(1, 256); self.beats.setValue(16)
        for lab, w in (("project", self.name), ("bpm", self.bpm), ("seed", self.seed), ("beats", self.beats)):
            top.addWidget(QLabel(lab)); top.addWidget(w)
        for text, fn in (("New", self.new), ("Open…", self.open), ("Save", self.save), ("▶ Render", self.render),
                         ("Export WAV…", self.export_wav), ("To song…", self.to_song)):
            b = QPushButton(text); b.clicked.connect(fn); top.addWidget(b)
        v.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        left = QWidget(); lv = QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self.show_track)
        self.table.itemChanged.connect(self._edited)
        lv.addWidget(self.table, 1)

        add = QGroupBox("Add a track"); af = QFormLayout(add)
        self.t_name = QLineEdit("lead")
        self.t_engine = QComboBox(); self.t_engine.addItems(S.engines())
        self.t_preset = QComboBox()
        self.t_clip = QComboBox(); self.t_clip.addItems(P.CLIPS)
        self.t_engine.currentTextChanged.connect(lambda e: self._presets(self.t_preset, e))
        self._presets(self.t_preset, self.t_engine.currentText())
        b_add = QPushButton("Add"); b_add.clicked.connect(lambda: self.add(self.t_name.text(), self.t_engine.currentText(),
                                                                           self.t_preset.currentText(), self.t_clip.currentText()))
        b_del = QPushButton("Remove selected"); b_del.clicked.connect(self.remove)
        for lab, w in (("name", self.t_name), ("engine", self.t_engine), ("preset", self.t_preset), ("clip", self.t_clip)):
            af.addRow(lab, w)
        hb = QHBoxLayout(); hb.addWidget(b_add); hb.addWidget(b_del); af.addRow(hb)
        lv.addWidget(add)

        route = QGroupBox("Route the selected track into…"); rf = QHBoxLayout(route)
        self.r_engine = QComboBox(); self.r_engine.addItems([e for e in ROUTE_INTO if e in S.ENGINES])
        self.r_fb = QDoubleSpinBox(); self.r_fb.setRange(0, 0.9); self.r_fb.setSingleStep(0.05); self.r_fb.setValue(0.0)
        b_route = QPushButton("Route"); b_route.clicked.connect(self.route)
        rf.addWidget(self.r_engine); rf.addWidget(QLabel("feedback")); rf.addWidget(self.r_fb); rf.addWidget(b_route)
        lv.addWidget(route)

        snap = QGroupBox("Snapshots"); sf = QHBoxLayout(snap)
        self.s_name = QLineEdit("after-the-clip")
        b_cap = QPushButton("Capture"); b_cap.clicked.connect(self.capture)
        self.s_start = QComboBox(); self.s_start.currentTextChanged.connect(self._set_start)
        sf.addWidget(self.s_name); sf.addWidget(b_cap); sf.addWidget(QLabel("selected starts from")); sf.addWidget(self.s_start)
        lv.addWidget(snap)
        split.addWidget(left)

        right = QWidget(); rv = QVBoxLayout(right); rv.setContentsMargins(0, 0, 0, 0)
        self.about = QLabel(); self.about.setWordWrap(True); self.about.setStyleSheet("color: #8c87a3")
        rv.addWidget(self.about)
        self.params_box = QWidget(); self.form = QFormLayout(self.params_box)
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setWidget(self.params_box)
        rv.addWidget(sc, 2)
        hb = QHBoxLayout()
        for text, fn in (("Reset to preset", self.reset_params), ("Save as my preset", self.save_preset),
                         ("▶ Solo", self.solo), ("Look inside", self.look)):
            b = QPushButton(text); b.clicked.connect(fn); hb.addWidget(b)
        rv.addLayout(hb)
        hv = QHBoxLayout()
        self.view = QPlainTextEdit(); self.view.setReadOnly(True); self.view.setFont(MONO)
        self.height = QLabel(); self.height.setFixedSize(160, 160)
        hv.addWidget(self.view, 1); hv.addWidget(self.height)
        rv.addLayout(hv, 1)
        self.probs = QLabel(); self.probs.setWordWrap(True); self.probs.setStyleSheet("color: #e0a050")
        rv.addWidget(self.probs)
        split.addWidget(right)
        split.setSizes([560, 700])
        v.addWidget(split, 1)
        self.fill()

    # ------------------------------------------------------------------ project
    def _sync(self):
        self.proj["name"] = self.name.text().strip() or "lab"
        self.proj["bpm"] = float(self.bpm.value())
        self.proj["seed"] = int(self.seed.value())
        self.proj["render"]["beats"] = float(self.beats.value())

    def set_project(self, proj: dict, path: Path | None = None):
        self.proj, self.path = proj, path
        self.name.setText(proj["name"]); self.bpm.setValue(proj["bpm"]); self.seed.setValue(proj["seed"])
        self.beats.setValue(int(proj["render"]["beats"]))
        self.fill()

    def new(self):
        self.set_project(P.new("lab", self.bpm.value(), self.seed.value()))

    def open(self):
        f, _ = QFileDialog.getOpenFileName(self, "Open a Lab project", str(projects_dir()), "Lab projects (*.bflab *.json)")
        if f:
            try:
                self.set_project(P.load(Path(f)), Path(f))
            except (OSError, ValueError) as e:
                self.win.log(f"couldn't open {f}: {e}")

    def save(self) -> Path:
        self._sync()
        self.path = self.path or projects_dir() / f"{self.proj['name']}.bflab"
        P.save(self.proj, self.path)
        self.win.log(f"saved {self.path}")
        return self.path

    def base(self) -> Path | None:
        return self.path.parent if self.path else None

    # ------------------------------------------------------------------ tracks
    def _presets(self, combo: QComboBox, eid: str):
        combo.clear()
        if eid in S.ENGINES:
            combo.addItems(sorted(S.presets(eid)))

    def add(self, name: str, engine: str, preset: str | None, clip_kind: str = "arp") -> str:
        self._sync()
        name = name.strip() or engine
        base, i = name, 2
        while name in self.proj["tracks"]:
            name, i = f"{base}{i}", i + 1
        P.add_track(self.proj, name, engine, preset or None, clip=P.clip(clip_kind, self.proj["render"]["beats"],
                                                                         seed=self.proj["seed"]))
        self.fill(select=name)
        return name

    def remove(self):
        k = self.selected()
        if k:
            del self.proj["tracks"][k]
            self.fill()

    def route(self):
        """The selected track becomes a small graph: its engine feeding a listening engine, with optional feedback."""
        k = self.selected()
        tr = self.proj["tracks"].get(k)
        if not tr or tr.get("graph"):
            return
        into = self.r_engine.currentText()
        nodes = {"src": {kk: copy.deepcopy(tr[kk]) for kk in ("engine", "preset", "params") if kk in tr},
                 "fx": {"engine": into}}
        edges = [{"from": "src", "to": "fx", "gain": 0.8}]
        if self.r_fb.value() > 0:
            edges.append({"from": "fx", "to": "src", "gain": float(self.r_fb.value()), "feedback": True})
        for kk in ("engine", "preset", "params", "version", "automation", "modulation"):
            tr.pop(kk, None)
        tr["graph"] = {"nodes": nodes, "edges": edges, "notes": ["src"], "out": {"src": 0.6, "fx": 0.6}}
        self.fill(select=k)

    def selected(self) -> str | None:
        r = self.table.currentRow()
        it = self.table.item(r, 0) if r >= 0 else None
        return it.text() if it else None

    def fill(self, select: str | None = None):
        self._filling = True
        tracks = self.proj["tracks"]
        self.table.setRowCount(len(tracks))
        for r, (k, tr) in enumerate(tracks.items()):
            eng = "graph: " + " → ".join(nd.get("engine", "?") for nd in tr["graph"]["nodes"].values()) if tr.get("graph") \
                else tr.get("engine", "?")
            vals = (k, eng, tr.get("preset", ""), f"{tr.get('gain_db', 0):g}", f"{tr.get('pan', 0):g}", "")
            for c, val in enumerate(vals):
                it = QTableWidgetItem(str(val))
                if c == 5:
                    it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    it.setCheckState(Qt.Checked if tr.get("mute") else Qt.Unchecked)
                elif c in (3, 4):
                    it.setFlags(Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                else:
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.table.setItem(r, c, it)
            if k == select:
                self.table.selectRow(r)
        self._filling = False
        self.s_start.blockSignals(True)
        self.s_start.clear(); self.s_start.addItems(["(fresh)"] + sorted(self.proj["snapshots"]))
        self.s_start.blockSignals(False)
        self.probs.setText("\n".join(P.problems(self.proj)))
        self.show_track()

    def _edited(self, it: QTableWidgetItem):
        if self._filling:
            return
        k = self.table.item(it.row(), 0).text()
        tr = self.proj["tracks"][k]
        if it.column() == 5:
            tr["mute"] = it.checkState() == Qt.Checked
        elif it.column() in (3, 4):
            try:
                v = float(it.text())
                tr["gain_db" if it.column() == 3 else "pan"] = max(-60.0, min(12.0, v)) if it.column() == 3 else max(-1.0, min(1.0, v))
            except ValueError:
                pass

    # ------------------------------------------------------------------ parameters
    def show_track(self):
        while self.form.rowCount():
            self.form.removeRow(0)
        k = self.selected()
        tr = self.proj["tracks"].get(k) if k else None
        self.height.clear()
        if not tr:
            self.about.setText("Add a track, pick its engine and preset, then ▶ Render.")
            return
        if tr.get("graph"):
            g = tr["graph"]
            self.about.setText(f"{k}: a routing graph. " + "; ".join(
                f"{e['from']} → {e['to']} ×{e.get('gain', 1):g}{' (feedback, bounded)' if e.get('feedback') else ''}"
                for e in g.get("edges", [])))
            return
        eid = tr.get("engine")
        if eid not in S.ENGINES:
            self.about.setText(f"{k}: engine {eid!r} is not in this build")
            return
        cls = S.engine_class(eid)
        self.about.setText(f"<b>{cls.NAME}</b> v{cls.VERSION} — {cls.DESCRIPTION}")
        cur = {**S.presets(eid).get(tr.get("preset") or "", {}), **(tr.get("params") or {})}
        pre = QComboBox(); pre.addItems(["(none)"] + sorted(S.presets(eid)))
        pre.setCurrentText(tr.get("preset") or "(none)")
        pre.currentTextChanged.connect(lambda t, tr=tr: (tr.__setitem__("preset", None if t == "(none)" else t), self.fill(select=k)))
        self.form.addRow("preset", pre)
        for p in cls.PARAMS:
            v = cur.get(p.name, p.default)
            if p.kind == "choice":
                w = QComboBox(); w.addItems([str(c) for c in p.choices]); w.setCurrentText(str(v))
                w.currentTextChanged.connect(lambda t, n=p.name: self._param(n, t))
            elif p.kind == "bool":
                w = QCheckBox(); w.setChecked(bool(v))
                w.toggled.connect(lambda on, n=p.name: self._param(n, bool(on)))
            elif p.kind == "int":
                w = QSpinBox(); w.setRange(int(p.lo), int(p.hi)); w.setValue(int(p.clamp(v)))
                w.valueChanged.connect(lambda x, n=p.name: self._param(n, int(x)))
            else:
                w = QDoubleSpinBox(); w.setDecimals(3); w.setRange(p.lo, p.hi)
                w.setSingleStep((p.hi - p.lo) / 50 or 0.01); w.setValue(float(p.clamp(v)))
                w.valueChanged.connect(lambda x, n=p.name: self._param(n, round(float(x), 4)))
            w.setToolTip(p.doc)
            self.form.addRow(f"{p.name}{' (' + p.unit + ')' if p.unit else ''}", w)

    def _param(self, name: str, value):
        k = self.selected()
        if k:
            self.proj["tracks"][k].setdefault("params", {})[name] = value

    def reset_params(self):
        k = self.selected()
        if k:
            self.proj["tracks"][k].pop("params", None)
            self.show_track()

    def save_preset(self):
        k = self.selected()
        tr = self.proj["tracks"].get(k) if k else None
        if tr and tr.get("engine") in S.ENGINES:
            from synthesis import patches
            eng = P.build(self.proj, k, self.base())
            f = patches.save_user_preset(eng.patch(), f"{k}-{self.proj['name']}")
            self.win.log(f"saved preset {f}")

    # ------------------------------------------------------------------ sound
    def render(self):
        self._sync()
        proj = copy.deepcopy(self.proj)
        self.win.jobs.run("rendering the Lab", lambda: P.render(proj, self.base()), self._rendered)

    def _rendered(self, res):
        self.mix = res[0]
        self.win.play_array(self.mix, f"Lab: {self.proj['name']}", int(self.proj["render"]["sr"]))
        self.win.log(f"Lab: {len(res[1])} tracks, peak {float(np.abs(self.mix).max()):.2f}")

    def solo(self):
        k = self.selected()
        if not k:
            return
        self._sync()
        proj = copy.deepcopy(self.proj)
        proj["tracks"] = {k: {**proj["tracks"][k], "mute": False}}
        self.win.jobs.run(f"rendering {k}", lambda: P.render(proj, self.base()), self._rendered)

    def look(self):
        """Play the selected track once, then show what its engine shows of itself (and terrain's height map)."""
        k = self.selected()
        if not k or k in {p.split(":")[0] for p in P.problems(self.proj) if "skipped" in p}:
            return
        self._sync()
        proj = copy.deepcopy(self.proj)

        def go():
            eng = P.build(proj, k, self.base())
            P.render_track(proj, k, self.base(), eng)
            if hasattr(eng, "nodes"):
                return "\n\n".join(f"[{nm}]\n{inspect(e)}" for nm, e in eng.nodes.items()), None
            return inspect(eng), eng.height_map(48) if hasattr(eng, "height_map") else None
        self.win.jobs.run(f"looking inside {k}", go, self._looked)

    def _looked(self, res):
        text, hm = res
        self.view.setPlainText(text)
        if hm is not None:
            self.height.setPixmap(height_image(hm))

    def capture(self):
        self._sync()
        name = self.s_name.text().strip() or "snapshot"
        P.capture(self.proj, name, self.base())
        self.win.log(f"captured snapshot {name!r} of {len(self.proj['snapshots'][name])} tracks")
        self.fill(select=self.selected())

    def _set_start(self, name: str):
        k = self.selected()
        if k:
            if name in self.proj["snapshots"]:
                self.proj["tracks"][k]["start"] = name
            else:
                self.proj["tracks"][k].pop("start", None)

    def export_wav(self):
        if self.mix is None:
            self.win.log("render first (▶ Render)")
            return
        f, _ = QFileDialog.getSaveFileName(self, "Export WAV", str(projects_dir() / f"{self.proj['name']}.wav"), "WAV (*.wav)")
        if f:
            self.win.log(f"wrote {P.write_wav(Path(f), self.mix, int(self.proj['render']['sr']))}")

    def to_song(self):
        """Write the tracks as instruments.toml tables, ready to paste into (or merge with) a song's instruments.toml."""
        self._sync()
        import sys
        sys.path.insert(0, str(paths.ENGINE / "studio"))
        from midi_studio import to_toml
        f, _ = QFileDialog.getSaveFileName(self, "Tracks for a song", str(projects_dir() / f"{self.proj['name']}.instruments.toml"),
                                           "TOML (*.toml)")
        if f:
            Path(f).parent.mkdir(parents=True, exist_ok=True)
            Path(f).write_text(to_toml(P.to_instruments(self.proj)))
            self.win.log(f"wrote {f}")
