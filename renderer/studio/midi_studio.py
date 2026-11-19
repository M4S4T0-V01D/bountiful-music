#!/usr/bin/env python3
"""MIDI Studio: open a MIDI file, choose a sound for every track (engine instruments, or any of the
~1180 sounds in the LMMS atlas), mix it, audition bars and render the song with stems.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python ~/Documents/Projects/intelligent-jungle/studio/midi_studio.py [song.mid] [map.toml]

The instrument map is a TOML file (the same format render_midi.py reads), so a map made here can be
reopened, edited by hand, or rendered from the command line.
"""
from __future__ import annotations

import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import tomllib
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ENGINE / "scripts"))
import render_midi as RM  # noqa: E402

PY = str(ENGINE / ".venv" / "bin" / "python")
ATLAS = ENGINE / "docs" / "lmms-atlas"
from engine.share import SAMPLES  # noqa: E402
NOTE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

C = {"bg": "#16121c", "panel": "#211a29", "panel2": "#2a2134", "fg": "#eee4f0", "mut": "#a99bb3", "acc": "#f0a070",
     "acc2": "#7fd0c0", "sel": "#4a3a5c", "line": "#3a2f45", "warn": "#e07a7a"}


def nn(m: int) -> str:
    return f"{NOTE[m % 12]}{m // 12 - 1}"


# ------------------------------------------------------------------ TOML out (enough for instrument maps)

def _val(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(round(v, 4)) if isinstance(v, float) else str(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, list):
        return "[" + ", ".join(_val(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{_key(k)} = {_val(x)}" for k, x in v.items()) + " }"
    raise TypeError(type(v))


def _key(k: str) -> str:
    return k if re.fullmatch(r"[A-Za-z0-9_-]+", k) else json.dumps(k)


def to_toml(cfg: dict) -> str:
    """Top-level values, then tables: [meta], [mix], [master], [sends.X], [tracks.X] (with the drum
    kit's [tracks.X.map] / .sounds / .stems as their own tables), then [[automation]]. Everything
    deeper is written inline."""
    out = ["# Instrument map (MIDI Studio / render_midi.py)"]
    is_tables = lambda v: isinstance(v, list) and v and all(isinstance(x, dict) for x in v)
    for k, v in cfg.items():
        if not isinstance(v, dict) and not is_tables(v):
            out.append(f"{_key(k)} = {_val(v)}")

    def table(path, d, subs=()):
        out.extend(["", "[" + ".".join(_key(p) for p in path) + "]"])
        later = []
        for k, v in d.items():
            if k in subs and isinstance(v, dict):
                later.append((k, v))
            else:
                out.append(f"{_key(k)} = {_val(v)}")
        for k, v in later:
            table(path + [k], v)

    for k, v in cfg.items():
        if isinstance(v, dict):
            if k in ("tracks", "sends"):
                for name, t in v.items():
                    table([k, name], t, ("map", "sounds", "stems") if k == "tracks" else ())
            else:
                table([k], v)
    for k, v in cfg.items():
        if is_tables(v):
            for item in v:
                out.extend(["", f"[[{_key(k)}]]"] + [f"{_key(kk)} = {_val(vv)}" for kk, vv in item.items()])
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ sound library

class Library:
    def __init__(self):
        self.dirs = [ENGINE / "presets"] + sorted(p for p in ENGINE.parent.glob("*/presets")
                                                   if p.parent != ENGINE and any((p.parent / f).exists() for f in ("spec.toml", "instruments.toml", "tracks", "album.toml")))
        self.presets: dict[str, dict] = {}       # file name -> data (first dir wins)
        self.preset_dir: dict[str, Path] = {}
        for d in self.dirs:
            for f in sorted(d.glob("*.json")):
                if f.name not in self.presets:
                    try:
                        self.presets[f.name] = json.loads(f.read_text())
                        self.preset_dir[f.name] = d
                    except Exception:
                        pass
        self.req = {k: RM.required_keys(k) for k in RM.KINDS}
        self.atlas = self._atlas()
        self.drum_samples = sorted(str(p.relative_to(SAMPLES)) for p in (SAMPLES / "drums").glob("*.ogg"))
        self.inst_samples = sorted(str(p.relative_to(SAMPLES)) for sub in ("instruments", "basses", "stringsnpads", "misc")
                                   for p in (SAMPLES / sub).glob("*.ogg"))

    def for_kind(self, kind: str) -> list[str]:
        need = self.req.get(kind, set())
        return [n for n, p in self.presets.items() if need <= set(p)]

    def about(self, name: str) -> str:
        return self.presets.get(name, {}).get("_about", "")

    def _atlas(self) -> list[dict]:
        try:
            import lmms_atlas
            items = lmms_atlas.entries()
            meta = json.loads((ATLAS / "meta.json").read_text())
        except Exception as ex:
            print("atlas unavailable:", ex)
            return []
        out = []
        for e in items:
            m = meta.get(e["id"], {})
            if not m or m.get("error"):
                continue
            ch = ""
            if "brightness_hz" in m:
                ch = (f'{"bright" if m["brightness_hz"] > 2500 else "warm" if m["brightness_hz"] > 900 else "dark"} · '
                      f'attack {m["attack_ms"]} ms · {"long tail" if m["tail_db"] > -12 else "short"}')
            out.append(dict(e, character=ch, audio=str(ATLAS / "audio" / f"{e['id']}.ogg"), iid=f"a{len(out)}"))
        return out


def guess_sound(name: str, program, lo: int, hi: int) -> dict:
    """A sensible first instrument for a MIDI track, from its name, GM program or range."""
    n = name.lower()
    table = [(("organ",), {"kind": "organ", "preset": "organ-b3.json"}),
             (("bass",), {"kind": "analogbass", "preset": "bass-round.json", "duck": {"depth": 0.3, "release": 0.11}, "mono": True}),
             (("lead", "melody", "hook", "synth"), {"kind": "polylead", "preset": "lead-mellow.json", "sends": {"echo": 0.15, "plate": 0.2}}),
             (("piano",), {"kind": "piano", "preset": "piano-grand.json"}),
             (("rhodes", "epiano", "e.piano", "keys", "ep"), {"kind": "rhodes", "preset": "rhodes-dusty.json"}),
             (("pad", "string", "choir", "atmos"), {"kind": "pad", "preset": "pad-night.json", "sends": {"plate": 0.3}}),
             (("vibe", "bell", "mallet"), {"kind": "vibes", "preset": "vibes-motor.json"}),
             (("horn", "brass", "sax", "trumpet", "flute"), {"kind": "horn", "preset": "horn-harmon.json"}),
             (("guitar",), {"kind": "guitar", "preset": "guitar-nylon.json"}),
             (("vox", "voice", "vocal"), {"kind": "vox", "preset": "vox-soul.json"})]
    for keys, s in table:
        if any(k in n for k in keys):
            return dict(s)
    if program in (4, 5):
        return {"kind": "rhodes", "preset": "rhodes-dusty.json"}
    if program is not None:
        fam = [(7, "piano", "piano-grand.json"), (15, "vibes", "vibes-motor.json"), (23, "organ", "organ-b3.json"),
               (31, "guitar", "guitar-nylon.json"), (39, "analogbass", "bass-round.json"), (55, "pad", "pad-night.json"),
               (79, "horn", "horn-harmon.json"), (87, "polylead", "lead-mellow.json"), (95, "pad", "pad-night.json")]
        for top, kind, pre in fam:
            if program <= top:
                return {"kind": kind, "preset": pre}
    if hi <= 55:
        return {"kind": "analogbass", "preset": "bass-round.json", "mono": True}
    return {"kind": "rhodes", "preset": "rhodes-dusty.json"}


# ------------------------------------------------------------------ widgets

class Slider(ttk.Frame):
    """Label · scale · value. `fmt` turns the value into text, `to_cfg`/`from_cfg` map scale <-> config."""

    def __init__(self, master, label, lo, hi, on_change, fmt=lambda v: f"{v:.2f}", step=None):
        super().__init__(master, style="Panel.TFrame")
        self.fmt, self.on_change, self.step, self._quiet = fmt, on_change, step, False
        ttk.Label(self, text=label, style="Panel.TLabel", width=16).grid(row=0, column=0, sticky="w")
        self.var = tk.DoubleVar(value=lo)
        self.scale = ttk.Scale(self, from_=lo, to=hi, variable=self.var, command=self._moved, length=240)
        self.scale.grid(row=0, column=1, sticky="ew", padx=6)
        self.val = ttk.Label(self, text="", style="Value.TLabel", width=11, anchor="e")
        self.val.grid(row=0, column=2, sticky="e")
        self.columnconfigure(1, weight=1)

    def _moved(self, _=None):
        v = self.var.get()
        if self.step:
            v = round(v / self.step) * self.step
        self.val.config(text=self.fmt(v))
        if not self._quiet:
            self.on_change(v)

    def set(self, v):
        self._quiet = True
        self.var.set(v)
        self._moved()
        self._quiet = False


class Studio(tk.Tk):
    def __init__(self, midi: Path | None, mapfile: Path | None):
        super().__init__()
        self.title("MIDI Studio")
        self.geometry("1360x860")
        self.minsize(1100, 720)
        self.configure(bg=C["bg"])
        self.lib = Library()
        self.midi: Path | None = None
        self.summary: dict = {}
        self.cfg: dict = {"tracks": {}}
        self.mapfile: Path | None = None
        self.cur: str | None = None
        self.proc: subprocess.Popen | None = None
        self.player: subprocess.Popen | None = None
        self.q: queue.Queue = queue.Queue()
        self.last_wav: Path | None = None
        self._style()
        self._build()
        self.after(80, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._quit)
        if midi:
            self.open_midi(midi, mapfile)

    # ---------------------------------------------------------------- look
    def _style(self):
        base = tkfont.nametofont("TkDefaultFont")
        fam = next((f for f in ("Inter", "Cantarell", "Noto Sans", "DejaVu Sans") if f in tkfont.families()), base.actual("family"))
        for f in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            tkfont.nametofont(f).configure(family=fam, size=10)
        self.f_title = tkfont.Font(family=fam, size=17, weight="bold")
        self.f_sub = tkfont.Font(family=fam, size=10)
        self.f_head = tkfont.Font(family=fam, size=11, weight="bold")
        self.f_mono = tkfont.Font(family="DejaVu Sans Mono", size=9)
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=C["bg"], foreground=C["fg"], fieldbackground=C["panel2"], bordercolor=C["line"],
                    lightcolor=C["panel"], darkcolor=C["panel"], troughcolor=C["panel2"], focuscolor=C["acc"], insertcolor=C["fg"])
        s.configure("TFrame", background=C["bg"])
        s.configure("Panel.TFrame", background=C["panel"])
        s.configure("TLabel", background=C["bg"], foreground=C["fg"])
        s.configure("Panel.TLabel", background=C["panel"], foreground=C["fg"])
        s.configure("Muted.TLabel", background=C["bg"], foreground=C["mut"])
        s.configure("PMuted.TLabel", background=C["panel"], foreground=C["mut"])
        s.configure("Value.TLabel", background=C["panel"], foreground=C["acc2"])
        s.configure("Title.TLabel", background=C["bg"], foreground=C["acc"], font=self.f_title)
        s.configure("Head.TLabel", background=C["panel"], foreground=C["acc"], font=self.f_head)
        s.configure("TButton", background=C["panel2"], foreground=C["fg"], borderwidth=0, padding=(12, 6), relief="flat")
        s.map("TButton", background=[("active", C["sel"]), ("disabled", C["panel"])], foreground=[("disabled", C["mut"])])
        s.configure("Accent.TButton", background=C["acc"], foreground="#1b1320", font=self.f_head)
        s.map("Accent.TButton", background=[("active", "#ffbb88"), ("disabled", C["panel2"])])
        s.configure("Teal.TButton", background=C["acc2"], foreground="#10201d")
        s.map("Teal.TButton", background=[("active", "#a8eadc")])
        s.configure("TCheckbutton", background=C["panel"], foreground=C["fg"], indicatorbackground=C["panel2"], indicatorforeground=C["acc"])
        s.map("TCheckbutton", background=[("active", C["panel"])], indicatorbackground=[("selected", C["acc"])])
        s.configure("TRadiobutton", background=C["panel"], foreground=C["fg"], indicatorbackground=C["panel2"])
        s.map("TRadiobutton", background=[("active", C["panel"])], indicatorbackground=[("selected", C["acc"])])
        s.configure("TCombobox", fieldbackground=C["panel2"], background=C["panel2"], foreground=C["fg"], arrowcolor=C["acc"], padding=4)
        s.map("TCombobox", fieldbackground=[("readonly", C["panel2"])], foreground=[("readonly", C["fg"])], selectbackground=[("readonly", C["panel2"])])
        self.option_add("*TCombobox*Listbox.background", C["panel2"])
        self.option_add("*TCombobox*Listbox.foreground", C["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", C["sel"])
        s.configure("TEntry", fieldbackground=C["panel2"], foreground=C["fg"], padding=5)
        s.configure("TSpinbox", fieldbackground=C["panel2"], foreground=C["fg"], arrowcolor=C["acc"], padding=3)
        s.configure("Horizontal.TScale", background=C["acc"], troughcolor=C["panel2"], sliderthickness=14)
        s.configure("Horizontal.TProgressbar", background=C["acc2"], troughcolor=C["panel2"], thickness=8)
        s.configure("TNotebook", background=C["bg"], borderwidth=0, tabmargins=(0, 4, 0, 0))
        s.configure("TNotebook.Tab", background=C["panel2"], foreground=C["mut"], padding=(16, 7), borderwidth=0)
        s.map("TNotebook.Tab", background=[("selected", C["panel"])], foreground=[("selected", C["acc"])])
        s.configure("Treeview", background=C["panel"], fieldbackground=C["panel"], foreground=C["fg"], rowheight=26, borderwidth=0)
        s.map("Treeview", background=[("selected", C["sel"])], foreground=[("selected", C["fg"])])
        s.configure("Treeview.Heading", background=C["panel2"], foreground=C["mut"], relief="flat", padding=5)
        s.map("Treeview.Heading", background=[("active", C["sel"])])
        s.configure("TPanedwindow", background=C["bg"])
        s.configure("Vertical.TScrollbar", background=C["panel2"], troughcolor=C["panel"], arrowcolor=C["mut"])

    # ---------------------------------------------------------------- layout
    def _build(self):
        top = ttk.Frame(self, padding=(16, 12, 16, 4))
        top.pack(fill="x")
        ttk.Label(top, text="MIDI Studio", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="  your notes · our sounds", style="Muted.TLabel", font=self.f_sub).pack(side="left", pady=(6, 0))
        for txt, cmd in (("Save map as…", self.save_map_as), ("Save map", self.save_map), ("Open map…", self.open_map_dialog),
                         ("Open MIDI…", self.open_midi_dialog)):
            ttk.Button(top, text=txt, command=cmd, style="Accent.TButton" if txt == "Open MIDI…" else "TButton").pack(side="right", padx=3)
        self.info = ttk.Label(self, text="Open a MIDI file to begin.", style="Muted.TLabel", padding=(18, 0, 18, 6))
        self.info.pack(fill="x")

        pane = ttk.Panedwindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=14)
        # tracks
        left = ttk.Frame(pane, style="Panel.TFrame", padding=10)
        ttk.Label(left, text="Tracks", style="Head.TLabel").pack(anchor="w")
        cols = ("ch", "notes", "range", "sound", "vol", "state")
        self.tree = ttk.Treeview(left, columns=cols, show="tree headings", selectmode="browse", height=14)
        self.tree.heading("#0", text="Track")
        self.tree.column("#0", width=150)
        for c, t, w in zip(cols, ("Ch", "Notes", "Range", "Sound", "Vol", ""), (36, 56, 84, 230, 56, 54)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w" if c == "sound" else "center")
        self.tree.tag_configure("muted", foreground=C["mut"])
        self.tree.tag_configure("solo", foreground=C["acc2"])
        self.tree.pack(fill="both", expand=True, pady=(8, 6))
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.select(self.tree.focus()))
        row = ttk.Frame(left, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Button(row, text="Mute", command=lambda: self.toggle("mute")).pack(side="left", padx=2)
        ttk.Button(row, text="Solo", command=lambda: self.toggle("solo")).pack(side="left", padx=2)
        ttk.Button(row, text="Auto-assign", command=self.auto_assign_current).pack(side="left", padx=2)
        ttk.Button(row, text="▶ Audition track", style="Teal.TButton", command=lambda: self.audition(track_only=True)).pack(side="right", padx=2)
        pane.add(left, weight=5)
        # editor
        right = ttk.Frame(pane, style="TFrame")
        self.track_title = ttk.Label(right, text="", style="Title.TLabel", font=self.f_head)
        self.track_title.pack(anchor="w", padx=4)
        self.nb = ttk.Notebook(right)
        self.nb.pack(fill="both", expand=True, pady=(4, 0))
        self.tab_sound = ttk.Frame(self.nb, style="Panel.TFrame", padding=12)
        self.tab_mix = ttk.Frame(self.nb, style="Panel.TFrame", padding=12)
        self.tab_drums = ttk.Frame(self.nb, style="Panel.TFrame", padding=12)
        self.tab_master = ttk.Frame(self.nb, style="Panel.TFrame", padding=12)
        for t, n in ((self.tab_sound, "Sound"), (self.tab_mix, "Mix"), (self.tab_drums, "Drum kit"), (self.tab_master, "Master")):
            self.nb.add(t, text=n)
        self._build_sound()
        self._build_mix()
        self._build_drums()
        self._build_master()
        pane.add(right, weight=6)

        # transport
        bot = ttk.Frame(self, style="Panel.TFrame", padding=(14, 10))
        bot.pack(fill="x", padx=14, pady=10)
        ttk.Label(bot, text="Bars", style="PMuted.TLabel").pack(side="left")
        self.bar_a, self.bar_b = tk.IntVar(value=1), tk.IntVar(value=8)
        ttk.Spinbox(bot, from_=1, to=999, textvariable=self.bar_a, width=5).pack(side="left", padx=4)
        ttk.Label(bot, text="to", style="PMuted.TLabel").pack(side="left")
        ttk.Spinbox(bot, from_=1, to=999, textvariable=self.bar_b, width=5).pack(side="left", padx=4)
        ttk.Button(bot, text="▶ Audition mix", style="Teal.TButton", command=lambda: self.audition(track_only=False)).pack(side="left", padx=8)
        ttk.Button(bot, text="■ Stop", command=self.stop).pack(side="left", padx=2)
        ttk.Button(bot, text="▶ Play last", command=self.play_last).pack(side="left", padx=2)
        ttk.Label(bot, text="   Output", style="PMuted.TLabel").pack(side="left")
        self.out_var = tk.StringVar()
        ttk.Entry(bot, textvariable=self.out_var, width=34).pack(side="left", padx=4)
        ttk.Button(bot, text="…", width=3, command=self.choose_out).pack(side="left")
        ttk.Button(bot, text="Open folder", command=lambda: self.open_path(Path(self.out_var.get() or "."))).pack(side="right", padx=2)
        self.render_btn = ttk.Button(bot, text="●  Render song", style="Accent.TButton", command=self.render_song)
        self.render_btn.pack(side="right", padx=6)
        st = ttk.Frame(self, padding=(16, 0, 16, 10))
        st.pack(fill="x")
        self.pbar = ttk.Progressbar(st, mode="determinate", maximum=100)
        self.pbar.pack(fill="x")
        self.status = ttk.Label(st, text="Ready.", style="Muted.TLabel")
        self.status.pack(anchor="w", pady=(4, 0))
        self.log = tk.Text(st, height=5, bg=C["panel"], fg=C["mut"], insertbackground=C["fg"], relief="flat", font=self.f_mono, wrap="none")
        self.log.pack(fill="x", pady=(4, 0))

    def _build_sound(self):
        f = self.tab_sound
        self.src = tk.StringVar(value="engine")
        r = ttk.Frame(f, style="Panel.TFrame")
        r.pack(fill="x")
        ttk.Label(r, text="Source", style="Head.TLabel").pack(side="left", padx=(0, 12))
        for v, t in (("engine", "Engine instrument"), ("lmms", "LMMS atlas sound"), ("sampler", "Sample, played chromatically")):
            ttk.Radiobutton(r, text=t, value=v, variable=self.src, command=self._src_changed).pack(side="left", padx=6)
        self.layers_note = ttk.Label(f, text="", style="PMuted.TLabel", wraplength=560)
        self.layers_note.pack(anchor="w", pady=(6, 0))
        # engine
        self.f_eng = ttk.Frame(f, style="Panel.TFrame")
        g = self.f_eng
        ttk.Label(g, text="Instrument", style="Panel.TLabel").grid(row=0, column=0, sticky="w", pady=6)
        self.kind = ttk.Combobox(g, values=RM.KINDS, state="readonly", width=16)
        self.kind.grid(row=0, column=1, sticky="w", padx=8)
        self.kind.bind("<<ComboboxSelected>>", lambda e: self._kind_changed())
        ttk.Label(g, text="Preset", style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=6)
        self.preset = ttk.Combobox(g, state="readonly", width=34)
        self.preset.grid(row=1, column=1, sticky="w", padx=8)
        self.preset.bind("<<ComboboxSelected>>", lambda e: self._preset_changed())
        self.preset_about = ttk.Label(g, text="", style="PMuted.TLabel", wraplength=520, justify="left")
        self.preset_about.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 8))
        # atlas
        self.f_lm = ttk.Frame(f, style="Panel.TFrame")
        g = self.f_lm
        sr = ttk.Frame(g, style="Panel.TFrame")
        sr.pack(fill="x", pady=(4, 6))
        self.q_var = tk.StringVar()
        e = ttk.Entry(sr, textvariable=self.q_var, width=28)
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda ev: self._atlas_filter())
        groups = ["All groups"] + sorted({a["group"] for a in self.lib.atlas})
        self.group = ttk.Combobox(sr, values=groups, state="readonly", width=30)
        self.group.set("All groups")
        self.group.pack(side="left", padx=6)
        self.group.bind("<<ComboboxSelected>>", lambda ev: self._atlas_filter())
        self.atlas_count = ttk.Label(sr, text="", style="PMuted.TLabel")
        self.atlas_count.pack(side="left", padx=6)
        tf = ttk.Frame(g, style="Panel.TFrame")
        tf.pack(fill="both", expand=True)
        self.atree = ttk.Treeview(tf, columns=("group", "char"), show="tree headings", height=11, selectmode="browse")
        self.atree.heading("#0", text="Sound")
        self.atree.heading("group", text="Group")
        self.atree.heading("char", text="Character")
        self.atree.column("#0", width=200)
        self.atree.column("group", width=180)
        self.atree.column("char", width=220)
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.atree.yview)
        self.atree.configure(yscrollcommand=sb.set)
        self.atree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.atree.bind("<Double-1>", lambda e: self.preview_atlas())
        br = ttk.Frame(g, style="Panel.TFrame")
        br.pack(fill="x", pady=6)
        ttk.Button(br, text="▶ Preview", style="Teal.TButton", command=self.preview_atlas).pack(side="left")
        ttk.Button(br, text="Use for this track", style="Accent.TButton", command=self.use_atlas).pack(side="left", padx=8)
        ttk.Label(br, text="If LMMS fails:", style="PMuted.TLabel").pack(side="left", padx=(16, 4))
        self.fallback = ttk.Combobox(br, values=RM.KINDS, state="readonly", width=12)
        self.fallback.pack(side="left")
        self.fallback.bind("<<ComboboxSelected>>", lambda e: self._fallback_changed())
        self.lm_current = ttk.Label(g, text="", style="Value.TLabel")
        self.lm_current.pack(anchor="w")
        # sampler
        self.f_smp = ttk.Frame(f, style="Panel.TFrame")
        g = self.f_smp
        ttk.Label(g, text="Sample", style="Panel.TLabel").grid(row=0, column=0, sticky="w", pady=6)
        self.sample = ttk.Combobox(g, values=self.lib.inst_samples, state="readonly", width=44)
        self.sample.grid(row=0, column=1, sticky="w", padx=8)
        self.sample.bind("<<ComboboxSelected>>", lambda e: self._sample_changed())
        ttk.Button(g, text="▶", width=3, command=lambda: self.play(SAMPLES / self.sample.get()) if self.sample.get() else None).grid(row=0, column=2)
        ttk.Label(g, text="Sample's own note", style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=6)
        self.root_var = tk.IntVar(value=60)
        ttk.Spinbox(g, from_=0, to=127, textvariable=self.root_var, width=6, command=self._sample_changed).grid(row=1, column=1, sticky="w", padx=8)
        ttk.Button(g, text="Detect", command=self._detect_root).grid(row=1, column=1, sticky="w", padx=(90, 0))
        # transpose (all sources)
        tr = ttk.Frame(f, style="Panel.TFrame")
        tr.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Label(tr, text="Transpose (semitones)", style="Panel.TLabel").pack(side="left")
        self.transpose = tk.IntVar(value=0)
        ttk.Spinbox(tr, from_=-36, to=36, textvariable=self.transpose, width=5, command=self._transpose_changed).pack(side="left", padx=8)

    def _build_mix(self):
        f = self.tab_mix
        log_hz = lambda v: 0 if v <= 0 else int(round(20 * 10 ** (v * 2)))          # 0..1 -> 20..2000 Hz
        log_lp = lambda v: 0 if v >= 1 else int(round(500 * 40 ** v))                 # 0..1 -> 500..20000 Hz
        self.sl = {}
        specs = [("gain_db", "Volume", -40, 12, lambda v: f"{v:+.1f} dB", 0.5),
                 ("pan", "Pan", -1, 1, lambda v: "centre" if abs(v) < 0.01 else f"{'L' if v < 0 else 'R'} {abs(v) * 100:.0f}", 0.01),
                 ("hp", "High-pass", 0, 1, lambda v: "off" if v <= 0 else f"{log_hz(v)} Hz", 0.01),
                 ("lp", "Low-pass", 0, 1, lambda v: "off" if v >= 1 else f"{log_lp(v)} Hz", 0.01),
                 ("drive", "Drive", 0, 3, lambda v: "off" if v <= 0 else f"{v:.2f}", 0.05),
                 ("chorus", "Chorus", 0, 0.8, lambda v: "off" if v <= 0 else f"{v * 100:.0f}%", 0.01),
                 ("width", "Stereo width", 0, 2, lambda v: f"{v * 100:.0f}%", 0.05),
                 ("room", "Room send", 0, 1, lambda v: "off" if v <= 0 else f"{v * 100:.0f}%", 0.01),
                 ("plate", "Plate send", 0, 1, lambda v: "off" if v <= 0 else f"{v * 100:.0f}%", 0.01),
                 ("echo", "Echo send (3/16)", 0, 1, lambda v: "off" if v <= 0 else f"{v * 100:.0f}%", 0.01),
                 ("duck", "Kick sidechain", 0, 0.6, lambda v: "off" if v <= 0 else f"-{-20 * math.log10(1 - v):.1f} dB", 0.01)]
        self._hz = (log_hz, log_lp)
        for i, (k, lab, lo, hi, fmt, step) in enumerate(specs):
            s = Slider(f, lab, lo, hi, lambda v, k=k: self._mix_changed(k, v), fmt, step)
            s.grid(row=i, column=0, sticky="ew", pady=3)
            self.sl[k] = s
        f.columnconfigure(0, weight=1)
        r = ttk.Frame(f, style="Panel.TFrame")
        r.grid(row=len(specs), column=0, sticky="w", pady=(10, 0))
        ttk.Label(r, text="Leslie", style="Panel.TLabel", width=16).pack(side="left")
        self.leslie = ttk.Combobox(r, values=["off", "slow (chorale)", "fast (tremolo)"], state="readonly", width=16)
        self.leslie.pack(side="left", padx=6)
        self.leslie.bind("<<ComboboxSelected>>", lambda e: self._leslie_changed())
        self.mono = tk.BooleanVar()
        ttk.Checkbutton(r, text="Mono", variable=self.mono, command=lambda: self._flag("mono", self.mono.get())).pack(side="left", padx=14)
        self.mute_v, self.solo_v = tk.BooleanVar(), tk.BooleanVar()
        ttk.Checkbutton(r, text="Mute", variable=self.mute_v, command=lambda: self._flag("mute", self.mute_v.get())).pack(side="left", padx=6)
        ttk.Checkbutton(r, text="Solo", variable=self.solo_v, command=lambda: self._flag("solo", self.solo_v.get())).pack(side="left", padx=6)
        self.mix_note = ttk.Label(f, text="", style="PMuted.TLabel", wraplength=560)
        self.mix_note.grid(row=len(specs) + 1, column=0, sticky="w", pady=(8, 0))

    def _build_drums(self):
        f = self.tab_drums
        self.drum_hint = ttk.Label(f, text="Select a drum track (MIDI channel 10).", style="PMuted.TLabel")
        self.drum_hint.pack(anchor="w")
        self.dtree = ttk.Treeview(f, columns=("gm", "hits", "sound", "file"), show="tree headings", height=9, selectmode="browse")
        for c, t, w in (("#0", "Note", 60), ("gm", "GM name", 140), ("hits", "Hits", 50), ("sound", "Sound", 90), ("file", "Sample / synth", 230)):
            self.dtree.heading(c, text=t)
            self.dtree.column(c, width=w)
        self.dtree.pack(fill="both", expand=True, pady=6)
        self.dtree.bind("<<TreeviewSelect>>", lambda e: self._drum_select())
        g = ttk.Frame(f, style="Panel.TFrame")
        g.pack(fill="x")
        ttk.Label(g, text="Sample", style="Panel.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        self.dsample = ttk.Combobox(g, values=["(none)"] + self.lib.drum_samples, state="readonly", width=34)
        self.dsample.grid(row=0, column=1, sticky="w", padx=6)
        self.dsample.bind("<<ComboboxSelected>>", lambda e: self._drum_edit())
        ttk.Button(g, text="▶", width=3, command=self._drum_preview).grid(row=0, column=2)
        ttk.Label(g, text="Synth layer", style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        self.dsynth = ttk.Combobox(g, values=["(none)", "kick", "snare", "clap", "hat", "rim", "shaker", "bongo", "ride", "crash"], state="readonly", width=14)
        self.dsynth.grid(row=1, column=1, sticky="w", padx=6)
        self.dsynth.bind("<<ComboboxSelected>>", lambda e: self._drum_edit())
        ttk.Label(g, text="Stem", style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        self.dstem = ttk.Combobox(g, values=["kick", "snare", "clap", "hats", "openhat", "cymbals", "toms", "perc"], width=14)
        self.dstem.grid(row=2, column=1, sticky="w", padx=6)
        self.dstem.bind("<<ComboboxSelected>>", lambda e: self._drum_edit())
        self.dstem.bind("<Return>", lambda e: self._drum_edit())
        self.dgain = Slider(g, "Hit level", -24, 12, lambda v: self._drum_edit(), lambda v: f"{v:+.1f} dB", 0.5)
        self.dgain.grid(row=3, column=0, columnspan=3, sticky="ew", pady=4)
        self.sgain = Slider(g, "Stem volume", -40, 12, lambda v: self._stem_gain(v), lambda v: f"{v:+.1f} dB", 0.5)
        self.sgain.grid(row=4, column=0, columnspan=3, sticky="ew", pady=4)
        g.columnconfigure(1, weight=1)

    def _build_master(self):
        f = self.tab_master
        ttk.Label(f, text="Master", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        self.m_lufs = Slider(f, "Loudness target", -20, -8, lambda v: self._master("target_lufs", v), lambda v: f"{v:.1f} LUFS", 0.5)
        self.m_lufs.grid(row=1, column=0, sticky="ew", pady=4)
        self.m_ceil = Slider(f, "Peak ceiling", -3, -0.3, lambda v: self._master("ceiling", v), lambda v: f"{v:.1f} dB", 0.1)
        self.m_ceil.grid(row=2, column=0, sticky="ew", pady=4)
        self.m_tape, self.m_glue = tk.BooleanVar(), tk.BooleanVar()
        r = ttk.Frame(f, style="Panel.TFrame")
        r.grid(row=3, column=0, sticky="w", pady=8)
        ttk.Checkbutton(r, text="Print to tape (warmth, head bump, soft top)", variable=self.m_tape, command=self._master_flags).pack(anchor="w")
        ttk.Checkbutton(r, text="Glue compressor (2:1, slow)", variable=self.m_glue, command=self._master_flags).pack(anchor="w", pady=4)
        ttk.Label(f, text="Song", style="Head.TLabel").grid(row=4, column=0, sticky="w", pady=(16, 4))
        r = ttk.Frame(f, style="Panel.TFrame")
        r.grid(row=5, column=0, sticky="w")
        self.meta_vars = {}
        for i, (k, lab) in enumerate((("title", "Title"), ("artist", "Artist"), ("composer", "Composer"), ("slug", "File name"))):
            ttk.Label(r, text=lab, style="Panel.TLabel", width=12).grid(row=i, column=0, sticky="w", pady=3)
            v = tk.StringVar()
            v.trace_add("write", lambda *a, k=k, v=v: self.cfg.setdefault("meta", {}).__setitem__(k, v.get()))
            ttk.Entry(r, textvariable=v, width=36).grid(row=i, column=1, sticky="w", padx=6)
            self.meta_vars[k] = v
        f.columnconfigure(0, weight=1)

    # ---------------------------------------------------------------- files
    def open_midi_dialog(self):
        p = filedialog.askopenfilename(title="Open MIDI", filetypes=[("MIDI", "*.mid *.midi"), ("All", "*")],
                                       initialdir=str(self.midi.parent if self.midi else Path.home() / "Documents" / "Projects"))
        if p:
            m = Path(p)
            guess = next((x for x in (m.parent / "instruments.toml", m.parent.parent / "instruments.toml", m.with_suffix(".toml")) if x.exists()), None)
            if guess and not messagebox.askyesno("Instrument map", f"Use the instrument map next to it?\n{guess}"):
                guess = None
            self.open_midi(m, guess)

    def open_midi(self, midi: Path, mapfile: Path | None = None):
        try:
            self.summary = RM.midi_summary(midi)
        except Exception as ex:
            messagebox.showerror("MIDI", f"Could not read {midi}:\n{ex}")
            return
        self.midi = midi
        if mapfile:
            self.load_map(mapfile)
        else:
            self.mapfile = None
            self.cfg = {"meta": {"title": midi.stem.replace("-", " ").title(), "artist": "M4S4T0", "slug": midi.stem},
                        "master": {"tape": {"drive": 1.3, "bias": 0.04, "bump_db": 0.5, "hf_db": -0.5, "lp_hz": 19000, "hiss_db": -80, "wow_ms": 0.03},
                                   "glue": {"threshold": -14.0, "ratio": 2.0, "attack": 0.02, "release": 0.25}, "target_lufs": -11.0, "ceiling": -1.0},
                        "tracks": {}}
        for t in self.summary["tracks"]:
            if t["name"] not in self.cfg["tracks"] and not self._matched_by_channel(t):
                self.cfg["tracks"][t["name"]] = self._auto(t)
        if not self.out_var.get():
            self.out_var.set(str((self.mapfile.parent if self.mapfile else midi.parent) / "studio-renders"))
        self.bar_b.set(min(8, self.summary["bars"]))
        self._refresh_tracks()
        self._load_master()
        kids = self.tree.get_children()
        if kids:
            self.tree.selection_set(kids[0])
            self.tree.focus(kids[0])
            self.select(kids[0])
        self._info()

    def _matched_by_channel(self, t) -> bool:
        names = {x["name"] for x in self.summary["tracks"]}
        return any(v.get("channel") == t["ch"] and k not in names for k, v in self.cfg["tracks"].items())

    def _auto(self, t) -> dict:
        if t["ch"] == 9:
            return RM.default_drums()
        s = guess_sound(t["name"], t["program"], t["lo"], t["hi"])
        s.setdefault("gain_db", -12.0)
        s.setdefault("sends", {"plate": 0.15})
        return s

    def auto_assign_current(self):
        t = self._track_info(self.cur)
        if t and messagebox.askyesno("Auto-assign", f"Replace {self.cur}'s sound and mix with a suggestion?"):
            self.cfg["tracks"][self._key(self.cur)] = self._auto(t)
            self._refresh_tracks()
            self.select(self.cur)

    def open_map_dialog(self):
        p = filedialog.askopenfilename(title="Open instrument map", filetypes=[("TOML", "*.toml")],
                                       initialdir=str(self.midi.parent if self.midi else Path.home()))
        if p:
            self.load_map(Path(p))
            if self.midi:
                self.open_midi(self.midi, Path(p))

    def load_map(self, p: Path):
        try:
            self.cfg = tomllib.loads(p.read_text())
        except Exception as ex:
            messagebox.showerror("Map", f"Could not read {p}:\n{ex}")
            return
        self.cfg.setdefault("tracks", {})
        self.mapfile = p
        self._info()

    def save_map(self):
        if not self.mapfile:
            return self.save_map_as()
        if self.mapfile.exists() and not getattr(self, "_saved_once", set()).__contains__(self.mapfile):
            if not messagebox.askyesno("Save map", f"Overwrite {self.mapfile.name}?\n(Comments in a hand-written map are not kept.)"):
                return
        self._write_map(self.mapfile)
        self._saved_once = getattr(self, "_saved_once", set()) | {self.mapfile}

    def save_map_as(self):
        p = filedialog.asksaveasfilename(title="Save instrument map", defaultextension=".toml", filetypes=[("TOML", "*.toml")],
                                         initialdir=str(self.midi.parent if self.midi else Path.home()),
                                         initialfile=(self.midi.stem + "-instruments.toml") if self.midi else "instruments.toml")
        if p:
            self.mapfile = Path(p)
            self._write_map(self.mapfile)
            self._saved_once = getattr(self, "_saved_once", set()) | {self.mapfile}
            self._info()

    def _write_map(self, p: Path):
        cfg = dict(self.cfg)
        cfg.pop("base_dir", None)
        p.write_text(to_toml(cfg))
        tomllib.loads(p.read_text())          # round-trip check
        self.status.config(text=f"Saved {p}")

    def choose_out(self):
        d = filedialog.askdirectory(title="Output folder", initialdir=self.out_var.get() or str(Path.home()))
        if d:
            self.out_var.set(d)

    def _info(self):
        if not self.midi:
            return
        s = self.summary
        self.info.config(text=f"{self.midi.name}   ·   {s['bpm']:.1f} bpm   ·   {s['bars']} bars   ·   {int(s['seconds'] // 60)}:{s['seconds'] % 60:04.1f}"
                              f"   ·   {len(s['tracks'])} tracks   ·   map: {self.mapfile.name if self.mapfile else '(new, unsaved)'}")

    # ---------------------------------------------------------------- tracks
    def _key(self, name: str) -> str:
        """The [tracks.X] table a MIDI track uses (its own name, or a table matched by channel)."""
        if name in self.cfg["tracks"]:
            return name
        t = self._track_info(name)
        names = {x["name"] for x in self.summary.get("tracks", [])}
        for k, v in self.cfg["tracks"].items():
            if t and v.get("channel") == t["ch"] and k not in names:
                return k
        self.cfg["tracks"][name] = self._auto(t) if t else {}
        return name

    def _track_info(self, name):
        return next((t for t in self.summary.get("tracks", []) if t["name"] == name), None)

    def _tc(self) -> dict:
        return self.cfg["tracks"][self._key(self.cur)]

    def describe(self, c: dict) -> str:
        if "map" in c:
            return f"drum kit ({len(c.get('sounds', {}))} sounds)"
        if c.get("layers"):
            return "layers: " + " + ".join(f"{L['kind']}" for L in c["layers"])
        if c.get("kind") == "lmms":
            v = c.get("voice", {})
            if v.get("label"):
                return f"LMMS · {v['label']}"
            raw = str(next(iter(v.values()), "?"))
            return f"LMMS · {re.sub(r'^[0-9]+-', '', Path(raw).stem)}"
        if c.get("kind") == "sampler":
            return f"sampler · {Path(c.get('preset', {}).get('sample', '?')).stem}"
        p = c.get("preset", "")
        return f"{c.get('kind', '?')} · {p if isinstance(p, str) else 'custom'}".replace(".json", "")

    def _refresh_tracks(self):
        sel = self.tree.focus()
        self.tree.delete(*self.tree.get_children())
        for t in self.summary.get("tracks", []):
            c = self.cfg["tracks"][self._key(t["name"])]
            state = "M" if c.get("mute") else "S" if c.get("solo") else ""
            tag = "muted" if c.get("mute") else "solo" if c.get("solo") else ""
            rng = "drums" if t["ch"] == 9 else f"{nn(t['lo'])}–{nn(t['hi'])}"
            self.tree.insert("", "end", iid=t["name"], text=t["name"], tags=(tag,),
                             values=(t["ch"] + 1, t["notes"], rng, self.describe(c), f"{c.get('gain_db', 0):+.0f}", state))
        if sel and self.tree.exists(sel):
            self.tree.selection_set(sel)
            self.tree.focus(sel)

    def _update_row(self):
        if self.cur and self.tree.exists(self.cur):
            c = self._tc()
            vals = list(self.tree.item(self.cur, "values"))
            vals[3], vals[4] = self.describe(c), f"{c.get('gain_db', 0):+.0f}"
            vals[5] = "M" if c.get("mute") else "S" if c.get("solo") else ""
            self.tree.item(self.cur, values=vals, tags=("muted" if c.get("mute") else "solo" if c.get("solo") else "",))

    def toggle(self, flag):
        if self.cur:
            c = self._tc()
            c[flag] = not c.get(flag, False)
            if not c[flag]:
                c.pop(flag)
            self.select(self.cur)
            self._update_row()

    def select(self, name):
        if not name:
            return
        self.cur = name
        t = self._track_info(name)
        c = self._tc()
        key = self._key(name)
        self.track_title.config(text=f"{name}" + (f"   (uses [tracks.{key}])" if key != name else "") +
                                (f"   ·   {t['notes']} notes from bar {t['first_bar']}" if t else ""))
        drums = "map" in c
        self.nb.tab(self.tab_drums, state="normal" if drums else "disabled")
        self.nb.tab(self.tab_sound, state="disabled" if drums else "normal")
        if drums and self.nb.select() == str(self.tab_sound):
            self.nb.select(self.tab_drums)
        if not drums and self.nb.select() == str(self.tab_drums):
            self.nb.select(self.tab_sound)
        if drums:
            self._load_drums(t, c)
        else:
            self._load_sound(c)
        self._load_mix(c, drums)
        if t:
            self.bar_a.set(t["first_bar"])
            self.bar_b.set(min(self.summary["bars"], t["first_bar"] + 7))

    # ---------------------------------------------------------------- sound tab
    def _load_sound(self, c):
        self.layers_note.config(text=("This track layers " + " + ".join(f"{L['kind']} ({L.get('preset', '')})" for L in c["layers"]) +
                                      ". Choosing a sound below replaces the layers.") if c.get("layers") else "")
        kind = c.get("kind") or (c["layers"][0]["kind"] if c.get("layers") else "rhodes")
        self.src.set("lmms" if kind == "lmms" else "sampler" if kind == "sampler" else "engine")
        self.transpose.set(c.get("transpose", 0))
        if kind not in ("lmms", "sampler"):
            self.kind.set(kind)
            self._fill_presets(kind)
            p = c.get("preset") if not c.get("layers") else c["layers"][0].get("preset")
            self.preset.set(p if isinstance(p, str) else "(inline preset)")
            self.preset_about.config(text=self.lib.about(p) if isinstance(p, str) else "")
        if kind == "lmms":
            v = c.get("voice", {})
            self.lm_current.config(text="Current: " + (v.get("label") or json.dumps(v)))
            self.fallback.set((c.get("fallback") or RM.DEFAULT_FALLBACK)["kind"])
        else:
            self.lm_current.config(text="")
        if kind == "sampler":
            p = c.get("preset", {})
            self.sample.set(p.get("sample", ""))
            self.root_var.set(p.get("root", 60))
        self._show_src()
        if not self.atree.get_children():
            self._atlas_filter()

    def _show_src(self):
        for fr in (self.f_eng, self.f_lm, self.f_smp):
            fr.pack_forget()
        {"engine": self.f_eng, "lmms": self.f_lm, "sampler": self.f_smp}[self.src.get()].pack(fill="both", expand=True, pady=(10, 0))

    def _src_changed(self):
        self._show_src()
        c = self._tc()
        s = self.src.get()
        if s == "engine" and c.get("kind") in ("lmms", "sampler", None) and not c.get("layers"):
            self.kind.set(self.kind.get() or "rhodes")
            self._kind_changed()
        elif s == "sampler" and c.get("kind") != "sampler":
            if not self.sample.get():
                self.sample.set("instruments/piano02.ogg" if "instruments/piano02.ogg" in self.lib.inst_samples else self.lib.inst_samples[0])
                self._detect_root()
            self._sample_changed()

    def _fill_presets(self, kind):
        vals = self.lib.for_kind(kind)
        self.preset.config(values=vals)
        return vals

    def _kind_changed(self):
        kind = self.kind.get()
        vals = self._fill_presets(kind)
        c = self._tc()
        cur = c.get("preset")
        pick = cur if isinstance(cur, str) and cur in vals else (vals[0] if vals else "")
        self.preset.set(pick)
        self._set_engine(kind, pick)

    def _preset_changed(self):
        self._set_engine(self.kind.get(), self.preset.get())

    def _set_engine(self, kind, preset):
        c = self._tc()
        for k in ("layers", "voice", "fallback", "lmms_fx"):
            c.pop(k, None)
        c["kind"] = kind
        c["preset"] = preset
        self.layers_note.config(text="")
        self.preset_about.config(text=self.lib.about(preset))
        self._update_row()

    def _atlas_filter(self):
        words = self.q_var.get().lower().split()
        grp = self.group.get()
        self.atree.delete(*self.atree.get_children())
        n = 0
        for a in self.lib.atlas:
            if grp != "All groups" and a["group"] != grp:
                continue
            hay = (a["group"] + " " + a["name"]).lower()
            if all(w in hay for w in words):
                self.atree.insert("", "end", iid=a["iid"], text=a["name"], values=(a["group"], a["character"]))
                n += 1
        self.atlas_count.config(text=f"{n} sounds")

    def _atlas_sel(self):
        i = self.atree.focus()
        return next((a for a in self.lib.atlas if a["iid"] == i), None)

    def preview_atlas(self):
        a = self._atlas_sel()
        if a:
            self.play(Path(a["audio"]))
            self.status.config(text=f"Preview: {a['name']} ({a['group']}) — the atlas phrase: arpeggio, chord, low note")

    def use_atlas(self):
        a = self._atlas_sel()
        if not a:
            return
        c = self._tc()
        for k in ("layers", "preset"):
            c.pop(k, None)
        c["kind"] = "lmms"
        c["voice"] = dict(a["voice"], label=f"{a['name']} ({a['group']})")
        c.setdefault("fallback", dict(RM.DEFAULT_FALLBACK))
        self.fallback.set(c["fallback"]["kind"])
        self.lm_current.config(text=f"Current: {a['name']} ({a['group']})")
        self._update_row()
        self.status.config(text=f"{self.cur} now plays '{a['name']}' through LMMS. ▶ Audition track to hear it with your notes.")

    def _fallback_changed(self):
        k = self.fallback.get()
        vals = self.lib.for_kind(k)
        self._tc()["fallback"] = {"kind": k, "preset": vals[0] if vals else {}}

    def _sample_changed(self):
        c = self._tc()
        for k in ("layers", "voice", "fallback"):
            c.pop(k, None)
        c["kind"] = "sampler"
        c["preset"] = {"sample": self.sample.get(), "root": int(self.root_var.get()), "release": 0.3}
        self._update_row()

    def _detect_root(self):
        if self.sample.get():
            try:
                from engine.lmms import sample_root
                self.root_var.set(sample_root(SAMPLES / self.sample.get()))
            except Exception:
                pass
            self._sample_changed()

    def _transpose_changed(self):
        c = self._tc()
        v = int(self.transpose.get())
        if v:
            c["transpose"] = v
        else:
            c.pop("transpose", None)

    # ---------------------------------------------------------------- mix tab
    def _load_mix(self, c, drums):
        if drums:
            self.mix_note.config(text="Drum stems are mixed in the Drum kit tab; these controls are for melodic tracks.")
        else:
            self.mix_note.config(text="")
        log_inv_hp = lambda hz_: 0 if not hz_ else math.log10(hz_ / 20) / 2
        log_inv_lp = lambda hz_: 1 if not hz_ else math.log(hz_ / 500) / math.log(40)
        self.sl["gain_db"].set(c.get("gain_db", 0.0))
        self.sl["pan"].set(c.get("pan", 0.0))
        self.sl["hp"].set(log_inv_hp(c.get("hp")))
        self.sl["lp"].set(log_inv_lp(c.get("lp")))
        self.sl["drive"].set(c.get("drive", 0.0))
        self.sl["chorus"].set(c.get("chorus", {}).get("mix", 0.0))
        self.sl["width"].set(c.get("width", 1.0))
        for s in ("room", "plate", "echo"):
            self.sl[s].set(c.get("sends", {}).get(s, 0.0))
        self.sl["duck"].set(c.get("duck", {}).get("depth", 0.0))
        L = c.get("leslie")
        if not L:
            self.leslie.set("off")
        else:
            sp = [v for _, v in L.get("speed", [[1, 0]])]
            self.leslie.set("slow (chorale)" if max(sp) == 0 else "fast (tremolo)" if min(sp) == 1 else "custom (from map)")
        self.mono.set(bool(c.get("mono")))
        self.mute_v.set(bool(c.get("mute")))
        self.solo_v.set(bool(c.get("solo")))

    def _mix_changed(self, k, v):
        if not self.cur:
            return
        c = self._tc()
        log_hz, log_lp = self._hz
        if k in ("gain_db", "pan"):
            c[k] = round(v, 2)
        elif k == "hp":
            c.pop("hp", None) if v <= 0 else c.__setitem__("hp", log_hz(v))
        elif k == "lp":
            c.pop("lp", None) if v >= 1 else c.__setitem__("lp", log_lp(v))
        elif k == "drive":
            c.pop("drive", None) if v <= 0 else c.__setitem__("drive", round(v, 2))
        elif k == "chorus":
            c.pop("chorus", None) if v <= 0 else c.__setitem__("chorus", {"depth_ms": 2.5, "rate": 0.5, "base_ms": 10, "mix": round(v, 2)})
        elif k == "width":
            c.pop("width", None) if abs(v - 1) < 0.01 else c.__setitem__("width", round(v, 2))
        elif k in ("room", "plate", "echo"):
            s = c.setdefault("sends", {})
            s.pop(k, None) if v <= 0 else s.__setitem__(k, round(v, 2))
            if not s:
                c.pop("sends")
        elif k == "duck":
            c.pop("duck", None) if v <= 0 else c.__setitem__("duck", {"depth": round(v, 2), "release": 0.12})
        self._update_row()

    def _leslie_changed(self):
        c = self._tc()
        v = self.leslie.get()
        if v == "off":
            c.pop("leslie", None)
        elif v.startswith("slow"):
            c["leslie"] = {"speed": [[1, 0]], "crossover": 800, "mix": 0.8}
        elif v.startswith("fast"):
            c["leslie"] = {"speed": [[1, 1]], "crossover": 800, "mix": 0.8}

    def _flag(self, k, on):
        c = self._tc()
        if on:
            c[k] = True
        else:
            c.pop(k, None)
        self._update_row()

    # ---------------------------------------------------------------- drums tab
    def _load_drums(self, t, c):
        self.drum_hint.config(text="Each MIDI note plays a sound; each sound goes to a stem. Select a row to change it.")
        self.dtree.delete(*self.dtree.get_children())
        used = t["pitches"] if t else {}
        for note in sorted(set(int(k) for k in c.get("map", {})) | set(used)):
            if note not in used:
                continue
            snd = c.get("map", {}).get(str(note), "")
            s = c.get("sounds", {}).get(snd, {})
            src = ", ".join(Path(x).stem for x in s.get("samples", [])) + (f" + {s['synth']} synth" if s.get("synth") else "")
            self.dtree.insert("", "end", iid=str(note), text=str(note), values=(RM.GM_NAMES.get(note, ""), used.get(note, 0), snd or "(unmapped)", src))

    def _drum_sound(self):
        i = self.dtree.focus()
        if not i:
            return None, None
        c = self._tc()
        name = c.setdefault("map", {}).get(i)
        if not name:
            name = RM.GM_DRUMS.get(int(i), f"note{i}")
            c["map"][i] = name
        snd = c.setdefault("sounds", {}).setdefault(name, dict(RM.DEFAULT_SOUNDS.get(name, {"samples": [], "stem": "perc"})))
        return name, snd

    def _drum_select(self):
        name, s = self._drum_sound()
        if s is None:
            return
        self._dq = True
        self.dsample.set(s.get("samples", ["(none)"])[0] if s.get("samples") else "(none)")
        self.dsynth.set(s.get("synth", "(none)"))
        self.dstem.set(s.get("stem", name))
        self.dgain.set(s.get("gain_db", 0.0))
        self.sgain.set(self._tc().get("stems", {}).get(s.get("stem", name), {}).get("gain_db", 0.0))
        self._dq = False

    def _drum_edit(self):
        if getattr(self, "_dq", False):
            return
        name, s = self._drum_sound()
        if s is None:
            return
        smp = self.dsample.get()
        if smp and smp != "(none)":
            s["samples"] = [smp]
        else:
            s.pop("samples", None)
        syn = self.dsynth.get()
        if syn and syn != "(none)":
            if s.get("synth") != syn:
                s["synth"], s["args"] = syn, {}
        else:
            s.pop("synth", None)
            s.pop("args", None)
        s["stem"] = self.dstem.get() or name
        g = round(self.dgain.var.get() * 2) / 2
        s.pop("gain_db", None) if g == 0 else s.__setitem__("gain_db", g)
        keep = self.dtree.focus()
        self._load_drums(self._track_info(self.cur), self._tc())
        if keep and self.dtree.exists(keep):
            self._dq = True
            self.dtree.selection_set(keep)
            self.dtree.focus(keep)
            self.after_idle(lambda: setattr(self, "_dq", False))

    def _stem_gain(self, v):
        if getattr(self, "_dq", False):
            return
        name, s = self._drum_sound()
        if s is not None:
            self._tc().setdefault("stems", {}).setdefault(s.get("stem", name), {})["gain_db"] = round(v, 1)

    def _drum_preview(self):
        smp = self.dsample.get()
        if smp and smp != "(none)":
            self.play(SAMPLES / smp)

    # ---------------------------------------------------------------- master
    def _load_master(self):
        m = self.cfg.setdefault("master", {})
        self.m_lufs.set(m.get("target_lufs", -12.0))
        self.m_ceil.set(m.get("ceiling", -1.0))
        self.m_tape.set(bool(m.get("tape")))
        self.m_glue.set(bool(m.get("glue")))
        for k, v in self.meta_vars.items():
            v.set(self.cfg.get("meta", {}).get(k, ""))

    def _master(self, k, v):
        self.cfg.setdefault("master", {})[k] = round(v, 2)

    def _master_flags(self):
        m = self.cfg.setdefault("master", {})
        if self.m_tape.get():
            m.setdefault("tape", {"drive": 1.3, "bias": 0.04, "bump_db": 0.5, "hf_db": -0.5, "lp_hz": 19000, "hiss_db": -80, "wow_ms": 0.03})
        else:
            m.pop("tape", None)
        if self.m_glue.get():
            m.setdefault("glue", {"threshold": -14.0, "ratio": 2.0, "attack": 0.02, "release": 0.25})
        else:
            m.pop("glue", None)

    # ---------------------------------------------------------------- render / play
    def _temp_map(self, out: Path) -> Path:
        cfg = json.loads(json.dumps(self.cfg))
        base = self.mapfile.parent if self.mapfile else self.midi.parent
        cfg["base_dir"] = str(base)
        cfg["preset_dirs"] = [str(d) for d in self.lib.dirs]
        d = out / ".studio"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "map.toml"
        p.write_text(to_toml(cfg))
        return p

    def audition(self, track_only: bool):
        if not self.midi:
            return
        if track_only and not self.cur:
            return
        a, b = int(self.bar_a.get()), int(self.bar_b.get())
        if b < a:
            a, b = b, a
        out = Path(self.out_var.get())
        args = [str(self.midi), str(self._temp_map(out)), "--out", str(out / ".studio"), "--no-stems", "--no-mp3", "--bars", f"{a}-{b}",
                "--name", "audition"]
        if track_only:
            args += ["--only", self._key(self.cur)]
        self.run(args, f"Auditioning {'track ' + self.cur if track_only else 'the mix'}, bars {a}-{b}", play=True)

    def render_song(self):
        if not self.midi:
            return
        out = Path(self.out_var.get())
        slug = self.cfg.get("meta", {}).get("slug") or self.midi.stem
        self.run([str(self.midi), str(self._temp_map(out)), "--out", str(out), "--stems", str(out / "stems"), "--name", slug],
                 f"Rendering the full song to {out}", play=False)

    def run(self, args, msg, play):
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo("Busy", "A render is already running. Stop it first.")
            return
        self.stop_player()
        self.log.delete("1.0", "end")
        self.status.config(text=msg + " …")
        self.pbar.config(value=0)
        self.render_btn.state(["disabled"])
        self._play_after = play
        cmd = ["nice", "-n", "10", PY, "-u", str(HERE / "render_midi.py")] + args
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(HERE))
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()

    def _reader(self, proc):
        for line in proc.stdout:
            self.q.put(("line", line.rstrip()))
        self.q.put(("exit", proc.wait()))

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "line":
                    m = re.match(r"PROGRESS (\d+)/(\d+) (.*)", val)
                    if m:
                        self.pbar.config(value=100 * int(m.group(1)) / int(m.group(2)))
                        self.status.config(text=m.group(3))
                    elif val.startswith("DONE "):
                        self.last_wav = Path(val[5:].split(" | ")[0])
                        self.status.config(text="Done: " + val.split(" | ")[1])
                    self.log.insert("end", val + "\n")
                    self.log.see("end")
                else:
                    self.render_btn.state(["!disabled"])
                    if val == 0:
                        self.pbar.config(value=100)
                        if self._play_after and self.last_wav:
                            self.play(self.last_wav)
                    elif val not in (-15, -9):
                        self.status.config(text=f"Render failed (exit {val}); see the log.")
                    else:
                        self.status.config(text="Stopped.")
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.stop_player()

    def stop_player(self):
        if self.player and self.player.poll() is None:
            self.player.terminate()

    def play(self, path: Path):
        self.stop_player()
        if not Path(path).exists():
            return
        for cmd in (["pw-play"], ["paplay"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]):
            if shutil.which(cmd[0]):
                self.player = subprocess.Popen(cmd + [str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return

    def play_last(self):
        if self.last_wav:
            self.play(self.last_wav)

    def open_path(self, p: Path):
        p.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _quit(self):
        self.stop()
        self.destroy()


def main():
    a = [Path(x) for x in sys.argv[1:]]
    midi = next((x for x in a if x.suffix.lower() in (".mid", ".midi")), None)
    mp = next((x for x in a if x.suffix == ".toml"), None)
    Studio(midi, mp).mainloop()


if __name__ == "__main__":
    main()
