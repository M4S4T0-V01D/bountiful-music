#!/usr/bin/env python3
"""Drives the app's logic (genre loading, the Electronium cockpit, freezes, the terrain) with tkinter stubbed out,
so it runs without a display. Run: $PY tests/smoke_app.py"""
import sys
import types
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bountiful"))


class Var:
    def __init__(self, value=None, **k):
        self.v = value

    def get(self):
        return self.v

    def set(self, v):
        self.v = v


class Tk:
    def __init__(self, *a, **k):
        self.inited = True

    def __getattr__(self, n):
        return mock.MagicMock()


class CB:
    def __init__(self, *a, values=(), **k):
        self.values, self.v, self.i = list(values), "", 0

    def set(self, v):
        self.v = v

    def get(self):
        return self.v

    def current(self, i=None):
        if i is None:
            return self.i
        self.i = i

    def __getattr__(self, n):
        return mock.MagicMock()


tk = types.ModuleType("tkinter")
widget = lambda *a, **k: mock.MagicMock()
tk.Tk, tk.Toplevel, tk.Text = Tk, widget, widget
tk.StringVar = tk.DoubleVar = tk.IntVar = tk.BooleanVar = Var
ttk = mock.MagicMock()
ttk.Combobox = CB
font = mock.MagicMock()
font.families.return_value = ["DejaVu Sans"]
tk.ttk, tk.font, tk.messagebox = ttk, font, mock.MagicMock()
sys.modules.update({"tkinter": tk, "tkinter.ttk": ttk, "tkinter.font": font, "tkinter.messagebox": tk.messagebox})

import app  # noqa: E402

a = app.App()
print("start genre:", a.gid(), "| electronium on:", a.el_on.get())
a.genre.current(list(a.G).index("electronium-69"))
a._genre_changed()
print("electronium-69: on", a.el_on.get(), "drums", a.el_drums.get(), "bounty", a.el_bounty.get(), "freezes", len(a.freezes), "freeze bar", a.fz_bar.get())
a._bounty_step(1)
a._freeze()
g = a.genre_cfg()
e = g["electronium"]
print("cfg: writer", g["melody"]["writer"], "drums", g["drums"], "bounty", e["bounty"], "freezes", len(e["freeze"]), "density", e["density"])
assert g["melody"]["writer"] == "electronium" and e["bounty"] == 1970 and len(e["freeze"]) == 3
a._terrain()
print(a.q.get()[1].splitlines()[0])
a._think()
print(a.q.get()[1].splitlines()[0])
a.el_keep.set("17, 42")
assert a.genre_cfg()["electronium"]["keep"] == [17, 42]
a.el_keep.set("3")
a.el_on.set(False)
a.el_drums.set(False)
g = a.genre_cfg()
assert g["melody"]["writer"] != "electronium" and g["drums"] != "electronium"
a.genre.current(0)
a._genre_changed()
a.el_on.set(True)
g = a.genre_cfg()
print(a.gid(), "with the Electronium:", g["melody"]["writer"], g["electronium"]["scale"], g["drums"])
a.el_gate.set("c2 &")
try:
    a.genre_cfg()
    raise AssertionError("a bad gate got through")
except ValueError as ex:
    print("bad gate caught:", ex)
print("ok")
