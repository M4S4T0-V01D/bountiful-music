"""The Start page: the few things people come to do, as big buttons, plus the tracks they made last."""
from __future__ import annotations

import random

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

import electronium_song as ES

from . import model as M

RECENT = 10
CARD = ("QPushButton { text-align: left; padding: 14px 16px; font-size: 14px; border-radius: 8px; }"
        "QPushButton:hover { border-color: #ff9b42; }")


def card(title: str, text: str, fn) -> QPushButton:
    b = QPushButton(f"{title}\n{text}")
    b.setStyleSheet(CARD)
    b.setMinimumHeight(78)
    b.clicked.connect(lambda: fn())
    return b


class StartPanel(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        hi = QLabel("What do you want to make?")
        hi.setStyleSheet("font-size: 22px; font-weight: bold; color: #ffb347")
        lay.addWidget(hi)
        sub = QLabel("Every song comes from a Bounty: a number or a word. The same Bounty always gives the same song, "
                     "so you can share it or come back to it. Songs are made on this computer; only the sound packs "
                     "are downloaded, once, in Settings → Setup.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #8c87a3; padding-bottom: 8px")
        lay.addWidget(sub)

        g = QGroupBox("A new song")
        gl = QHBoxLayout(g)
        gl.addWidget(QLabel("Bounty"))
        self.bounty = QLineEdit(str(random.randint(1000, 99999)))
        self.bounty.setMaximumWidth(160)
        self.bounty.setToolTip("any number or word")
        gl.addWidget(self.bounty)
        dice = QPushButton("🎲")
        dice.setToolTip("another Bounty")
        dice.clicked.connect(lambda: self.bounty.setText(str(random.randint(1000, 99999))))
        gl.addWidget(dice)
        gl.addWidget(QLabel("  Length"))
        self.length = QComboBox()
        self.length.addItems(list(ES.LAYOUTS))
        self.length.setCurrentText("short" if "short" in ES.LAYOUTS else "normal")
        self.length.setToolTip("short songs render in about a minute; longer ones take a few")
        gl.addWidget(self.length)
        self.b_new = QPushButton("Make it and play it")
        self.b_new.setObjectName("primary")
        self.b_new.setMinimumHeight(34)
        self.b_new.setToolTip("write the song, render it, and open it in Arrange")
        self.b_new.clicked.connect(self.new_song)
        gl.addWidget(self.b_new)
        more = QPushButton("More choices …")
        more.setToolTip("key, tempo, chord colour and a brief in your own words")
        more.clicked.connect(lambda: self.win.show_panel(self.win.song))
        gl.addWidget(more)
        gl.addStretch(1)
        lay.addWidget(g)

        grid = QGridLayout()
        grid.setSpacing(10)
        cards = [
            ("🎮  Game music", "Loops that get more intense (calm → combat), stingers, files for Godot and Unity",
             lambda: self.win.show_panel(self.win.game)),
            ("📂  Open a track", "A song you made before, or any track folder",
             self.win.open_dialog),
            ("💡  A batch of ideas", "Dozens of Bounties at once: hear the best bits, keep the ones you like",
             lambda: self.win.show_panel(self.win.day)),
            ("🎛  Play live", "The Electronium plays; you turn the knobs and it records every move",
             lambda: self.win.show_panel(self.win.livep)),
            ("🔊  Sound lab", "Build new instruments from eleven sound engines and hear them right away",
             lambda: self.win.show_panel(self.win.lab)),
            ("🌳  Ideas and history", "Your ratings, the family tree of songs, and new takes on 4 bars you like",
             lambda: self.win.show_panel(self.win.obs)),
        ]
        for i, (t, s, fn) in enumerate(cards):
            grid.addWidget(card(t, s, fn), i // 3, i % 3)
        lay.addLayout(grid)

        rg = QGroupBox("Recent tracks (double-click to open)")
        rl = QVBoxLayout(rg)
        self.recent = QListWidget()
        self.recent.itemDoubleClicked.connect(lambda it: self.win.open_track(it.data(Qt.UserRole)))
        rl.addWidget(self.recent)
        lay.addWidget(rg, 1)
        tips = QLabel("Space plays and pauses · Ctrl+R renders the open track · Ctrl+1 … Ctrl+9 switch tabs · "
                      "hover over anything for a hint")
        tips.setStyleSheet("color: #6a6585")
        lay.addWidget(tips)
        self.refresh()

    def refresh(self):
        self.recent.clear()
        for p in M.library().get("Tracks", [])[:RECENT]:
            it = QListWidgetItem(p.name)
            it.setData(Qt.UserRole, p)
            it.setToolTip(str(p))
            self.recent.addItem(it)
        if not self.recent.count():
            self.recent.addItem("Nothing yet: make a new song above.")

    def new_song(self):
        s = self.win.song
        s.bounty.setText(self.bounty.text().strip() or str(random.randint(1000, 99999)))
        s.length.setCurrentText(self.length.currentText())
        s.title.clear()
        self.win.log(f"making a song from Bounty {s.bounty.text()} ({self.length.currentText()}) and rendering it ...")
        s.make(True)
