"""Setup: the music folder, the sound packs and the programs Bountiful plays through, what's missing and how
to get it. Opens by itself on start while something basic is missing, until it's dismissed."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QMessageBox, QProgressBar, QPushButton, QVBoxLayout)

import packs
import paths
import setup_check as SC

OK, NO = "✔", "✘"


def should_show() -> bool:
    return not paths.config().get("setup", {}).get("dismissed", False) and not SC.report()["ready"]


class SetupDialog(QDialog):
    progressed = Signal(str, int, int)   # pack, bytes so far, total: from the download thread

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Set up Bountiful")
        self.setMinimumWidth(640)
        self.busy = False
        lay = QVBoxLayout(self)
        intro = QLabel("Bountiful makes songs on this computer. It needs somewhere to keep your music, a pack of "
                       "sounds, and a few free programs it plays through.")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        g = QGroupBox("Music folder")
        h = QHBoxLayout(g)
        self.data = QLabel()
        self.data.setTextInteractionFlags(Qt.TextSelectableByMouse)
        h.addWidget(self.data, 1)
        b = QPushButton("Change …")
        b.clicked.connect(self.change_data)
        h.addWidget(b)
        lay.addWidget(g)

        g = QGroupBox("Sound packs")
        grid = QGridLayout(g)
        self.pack_rows = {}
        m = packs.manifest()
        for i, (name, p) in enumerate(packs.PACKS.items()):
            size = f", {m[name]['size'] / 1e6:.0f} MB" if name in m else ""
            label = QLabel(f"<b>{p['title']}</b>{' (needed)' if name == 'starter' else ''}{size}<br>{p['about']}")
            label.setWordWrap(True)
            state, bar, btn = QLabel(), QProgressBar(), QPushButton("Install")
            bar.hide()
            btn.clicked.connect(lambda _=False, n=name: self.install(n))
            grid.addWidget(state, i, 0)
            grid.addWidget(label, i, 1)
            grid.addWidget(bar, i, 2)
            grid.addWidget(btn, i, 3)
            self.pack_rows[name] = (state, bar, btn)
        grid.setColumnStretch(1, 1)
        lay.addWidget(g)

        g = QGroupBox("Programs")
        grid = QGridLayout(g)
        self.tool_rows = {}
        for i, (t, (why, basic)) in enumerate(SC.TOOLS.items()):
            state, label = QLabel(), QLabel()
            label.setWordWrap(True)
            grid.addWidget(state, i, 0)
            grid.addWidget(label, i, 1)
            self.tool_rows[t] = (state, label)
        grid.setColumnStretch(1, 1)
        hint = QHBoxLayout()
        self.hint = QLabel()
        self.hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.hint.setWordWrap(True)
        self.copy = QPushButton("Copy command")
        self.copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.hint.property("cmd") or ""))
        hint.addWidget(self.hint, 1)
        hint.addWidget(self.copy)
        grid.addLayout(hint, len(SC.TOOLS), 0, 1, 2)
        lay.addWidget(g)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        row = QHBoxLayout()
        self.dismiss = QCheckBox("Don't open this by itself again")
        self.dismiss.setChecked(paths.config().get("setup", {}).get("dismissed", False))
        row.addWidget(self.dismiss)
        row.addStretch(1)
        again = QPushButton("Check again")
        again.clicked.connect(self.refresh)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        row.addWidget(again)
        row.addWidget(close)
        lay.addLayout(row)
        self.progressed.connect(self._progress)
        self.refresh()

    def refresh(self):
        r = SC.report()
        self.report = r
        self.data.setText(("" if r["data"]["ok"] else NO + " can't write here: ") + r["data"]["where"])
        for name, (state, bar, btn) in self.pack_rows.items():
            st = r["packs"][name]
            state.setText(OK if st != "missing" else NO)
            btn.setText("Reinstall" if st != "missing" else "Install")
            btn.setEnabled(not self.busy and name in packs.manifest())
        for t, (state, label) in self.tool_rows.items():
            v = r["tools"][t]
            state.setText(OK if v["ok"] else NO)
            need = "" if v["basic"] else " (optional)"
            label.setText(f"<b>{t}</b>{need}: {v['why']}" + (f"<br><small>{v['version']}</small>" if v["version"] else ""))
        if t := r["missing"]:
            self.hint.setText(f"To install the missing programs: <code>{r['hint']}</code>")
            self.hint.setProperty("cmd", r["hint"])
            if "lmms" in t:
                self.hint.setText(self.hint.text() + "<br>LMMS is also at lmms.io.")
        else:
            self.hint.setText("All the programs are here.")
            self.hint.setProperty("cmd", "")
        self.copy.setVisible(bool(r["missing"]))
        if not r["lmms_share"] and r["tools"]["lmms"]["ok"]:
            self.hint.setText(self.hint.text() + "<br>LMMS is here but its sounds aren't: set LMMS_SHARE to its share/lmms folder.")
        self.summary.setText("<b>Ready.</b> Everything Bountiful needs is here." if r["ready"]
                             else "<b>Not ready yet:</b> install what's marked " + NO + " above (the optional ones can wait).")
        return r

    def change_data(self):
        d = QFileDialog.getExistingDirectory(self, "Where your music lives (tracks, albums, sessions)", str(paths.DATA))
        if d:
            paths.save_config(data=d)
            QMessageBox.information(self, "Bountiful", f"Music folder set to {d}. Restart Bountiful to use it; "
                                                       "the sound packs install into its samples folder.")

    def _progress(self, name, done, total):
        bar = self.pack_rows[name][1]
        bar.setMaximum(max(total, 1))
        bar.setValue(done)
        bar.setFormat(f"{done / 1e6:.0f} / {total / 1e6:.0f} MB" if total else f"{done / 1e6:.0f} MB")

    def install(self, name, then=None):
        if self.busy:
            return
        st = self.report["packs"][name]
        self.busy = True
        bar = self.pack_rows[name][1]
        bar.show()
        bar.setValue(0)
        for _, _, b in self.pack_rows.values():
            b.setEnabled(False)

        def done(n):
            self.busy = False
            bar.hide()
            self.refresh()
            self.win.log(f"{packs.PACKS[name]['title']}: {n} files installed into {packs.dest()}")
            if packs.dest() != paths.SAMPLES:
                self.summary.setText(self.summary.text() + " Restart Bountiful to use the new sounds.")
            if then:
                then(n)

        def fail(e):
            self.busy = False
            bar.hide()
            self.refresh()
            QMessageBox.warning(self, "Bountiful", f"{packs.PACKS[name]['title']} didn't install: {e}")
            if then:
                then(e)
        self.win.jobs.run(f"installing {packs.PACKS[name]['title'].lower()}",
                          lambda: packs.install(name, overwrite=st != "missing",
                                                progress=lambda d, t: self.progressed.emit(name, d, t),
                                                log=self.win.jobs.log), done, fail)

    def hideEvent(self, e):   # Close, Esc and the window's X all end here
        if self.dismiss.isChecked() != paths.config().get("setup", {}).get("dismissed", False):
            paths.save_config(setup={"dismissed": self.dismiss.isChecked()})
        super().hideEvent(e)
