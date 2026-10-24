#!/usr/bin/env python3
"""Bountiful Music: pick a genre, compose candidate songs, hear the chorus, re-roll the melody, chords or
bass of a song you like, and build the full track (MIDI, WAV, MP3, stems), then refine its sounds in
MIDI Studio.

    ~/Documents/Projects/bountiful-music/bountiful-music        (launcher)
"""
from __future__ import annotations

import copy
import json
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter import font as tkfont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build as B  # noqa: E402
import electronium as EL  # noqa: E402
import friends as FR  # noqa: E402

ROOT = B.ROOT
STUDIO = B.ENGINE / "studio" / "midi-studio"
C = {"bg": "#14121b", "panel": "#1f1b29", "panel2": "#2a2436", "fg": "#efe8f2", "mut": "#a79cb4", "acc": "#e8b04c",
     "acc2": "#79d0c2", "sel": "#463a5a", "line": "#3a3148"}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Bountiful Music")
        self.geometry("1720x900")
        self.minsize(1450, 800)
        self.configure(bg=C["bg"])
        self.G = B.genres()
        self.rows: list[dict] = []
        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self.player = None
        self.last_wav: Path | None = None
        self.last_track: Path | None = None
        self._style()
        self._build()
        self.genre.current(list(self.G).index("soviet-synthpop-86") if "soviet-synthpop-86" in self.G else 0)
        self._genre_changed()
        self.after(80, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._quit)

    # ---------------------------------------------------------------- look
    def _style(self):
        fam = next((f for f in ("Inter", "Cantarell", "Noto Sans", "DejaVu Sans") if f in tkfont.families()), "TkDefaultFont")
        for f in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            tkfont.nametofont(f).configure(family=fam, size=10)
        self.f_title = tkfont.Font(family=fam, size=19, weight="bold")
        self.f_head = tkfont.Font(family=fam, size=11, weight="bold")
        self.f_mono = tkfont.Font(family="DejaVu Sans Mono", size=9)
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=C["bg"], foreground=C["fg"], fieldbackground=C["panel2"], bordercolor=C["line"],
                    lightcolor=C["panel"], darkcolor=C["panel"], troughcolor=C["panel2"], focuscolor=C["acc"], insertcolor=C["fg"])
        for n, bg in (("TFrame", C["bg"]), ("Panel.TFrame", C["panel"])):
            s.configure(n, background=bg)
        s.configure("TLabel", background=C["bg"], foreground=C["fg"])
        s.configure("Panel.TLabel", background=C["panel"], foreground=C["fg"])
        s.configure("PMuted.TLabel", background=C["panel"], foreground=C["mut"])
        s.configure("Muted.TLabel", background=C["bg"], foreground=C["mut"])
        s.configure("Value.TLabel", background=C["panel"], foreground=C["acc2"])
        s.configure("Title.TLabel", background=C["bg"], foreground=C["acc"], font=self.f_title)
        s.configure("Head.TLabel", background=C["panel"], foreground=C["acc"], font=self.f_head)
        s.configure("TButton", background=C["panel2"], foreground=C["fg"], borderwidth=0, padding=(12, 6))
        s.map("TButton", background=[("active", C["sel"]), ("disabled", C["panel"])], foreground=[("disabled", C["mut"])])
        s.configure("Accent.TButton", background=C["acc"], foreground="#1d1608", font=self.f_head)
        s.map("Accent.TButton", background=[("active", "#f6c86e"), ("disabled", C["panel2"])])
        s.configure("Teal.TButton", background=C["acc2"], foreground="#0f1f1c")
        s.map("Teal.TButton", background=[("active", "#a5eadf"), ("disabled", C["panel2"])])
        s.configure("TCombobox", fieldbackground=C["panel2"], background=C["panel2"], foreground=C["fg"], arrowcolor=C["acc"], padding=5)
        s.map("TCombobox", fieldbackground=[("readonly", C["panel2"])], foreground=[("readonly", C["fg"])], selectbackground=[("readonly", C["panel2"])])
        self.option_add("*TCombobox*Listbox.background", C["panel2"])
        self.option_add("*TCombobox*Listbox.foreground", C["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", C["sel"])
        s.configure("TEntry", fieldbackground=C["panel2"], foreground=C["fg"], padding=5)
        s.configure("TSpinbox", fieldbackground=C["panel2"], foreground=C["fg"], arrowcolor=C["acc"], padding=3)
        s.configure("Horizontal.TScale", background=C["acc"], troughcolor=C["panel2"])
        s.configure("Horizontal.TProgressbar", background=C["acc2"], troughcolor=C["panel2"], thickness=8)
        s.configure("Treeview", background=C["panel"], fieldbackground=C["panel"], foreground=C["fg"], rowheight=27, borderwidth=0)
        s.map("Treeview", background=[("selected", C["sel"])])
        s.configure("Treeview.Heading", background=C["panel2"], foreground=C["mut"], relief="flat", padding=5)
        s.configure("TCheckbutton", background=C["panel"], foreground=C["fg"], indicatorbackground=C["panel2"])
        s.map("TCheckbutton", background=[("active", C["panel"])], indicatorbackground=[("selected", C["acc"])])

    # ---------------------------------------------------------------- layout
    def _build(self):
        top = ttk.Frame(self, padding=(18, 12, 18, 6))
        top.pack(fill="x")
        ttk.Label(top, text="Bountiful Music", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="   songs composed, then produced like records", style="Muted.TLabel").pack(side="left", pady=(8, 0))
        body = ttk.Frame(self, padding=(14, 0))
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # genre panel
        g = ttk.Frame(body, style="Panel.TFrame", padding=14)
        g.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        ttk.Label(g, text="Genre", style="Head.TLabel").pack(anchor="w")
        self.genre = ttk.Combobox(g, values=[v["name"] for v in self.G.values()], state="readonly", width=30)
        self.genre.pack(anchor="w", pady=(6, 4))
        self.genre.bind("<<ComboboxSelected>>", lambda e: self._genre_changed())
        self.gdesc = ttk.Label(g, text="", style="PMuted.TLabel", wraplength=300, justify="left")
        self.gdesc.pack(anchor="w", pady=(0, 10))
        ttk.Label(g, text="Feel (overrides the preset)", style="Head.TLabel").pack(anchor="w", pady=(6, 4))
        self.ctl = {}
        for key, lab, lo, hi, step, fmt in (("bpm", "Tempo", 60, 180, 1, "{:.0f} bpm"),
                                            ("density", "Melody notes / bar", 2, 10, 1, "{:.0f}"),
                                            ("leap", "Largest melody leap", 3, 12, 1, "{:.0f} semitones"),
                                            ("swing", "Swing", 0.5, 0.66, 0.01, "{:.0%}"),
                                            ("human", "Humanize", 0, 25, 1, "{:.0f} ms")):
            f = ttk.Frame(g, style="Panel.TFrame")
            f.pack(fill="x", pady=2)
            ttk.Label(f, text=lab, style="Panel.TLabel", width=19).pack(side="left")
            v = tk.DoubleVar()
            val = ttk.Label(f, text="", style="Value.TLabel", width=12, anchor="e")
            sc = ttk.Scale(f, from_=lo, to=hi, variable=v, length=130,
                           command=lambda x, v=v, val=val, step=step, fmt=fmt: val.config(text=fmt.format(round(float(x) / step) * step)))
            sc.pack(side="left", padx=4)
            val.pack(side="left")
            self.ctl[key] = (v, val, step, fmt)
        ttk.Button(g, text="Reset to preset", command=self._genre_changed).pack(anchor="w", pady=(6, 12))
        ttk.Label(g, text="Compose", style="Head.TLabel").pack(anchor="w", pady=(8, 4))
        f = ttk.Frame(g, style="Panel.TFrame")
        f.pack(fill="x")
        ttk.Label(f, text="Candidates", style="Panel.TLabel").pack(side="left")
        self.count = tk.IntVar(value=12)
        ttk.Spinbox(f, from_=1, to=60, textvariable=self.count, width=5).pack(side="left", padx=8)
        self.compose_btn = ttk.Button(g, text="✦  Compose", style="Accent.TButton", command=self.compose)
        self.compose_btn.pack(fill="x", pady=(10, 0))

        # candidates + details
        mid = ttk.Frame(body, style="Panel.TFrame", padding=12)
        mid.grid(row=0, column=1, sticky="nsew")
        mid.rowconfigure(1, weight=1)
        mid.columnconfigure(0, weight=1)
        ttk.Label(mid, text="Candidates  (best first)", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        cols = ("score", "key", "chorus", "mel")
        self.tree = ttk.Treeview(mid, columns=cols, show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Song")
        self.tree.column("#0", width=230)
        for c, t, w in zip(cols, ("Score", "Key", "Chorus", "Melody / bar"), (60, 90, 420, 90)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w" if c == "chorus" else "center")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=1, column=0, sticky="nsew", pady=6)
        sb.grid(row=1, column=1, sticky="ns", pady=6)
        self._cockpit(body)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._select())
        self.tree.bind("<Double-1>", lambda e: self.preview())
        self.detail = ttk.Label(mid, text="Compose some songs, then select one.", style="PMuted.TLabel", justify="left", font=self.f_mono)
        self.detail.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 8))
        act = ttk.Frame(mid, style="Panel.TFrame")
        act.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.btns = []
        for txt, cmd, st in (("▶  Preview chorus", self.preview, "Teal.TButton"), ("New melody", lambda: self.reroll("melody"), "TButton"),
                             ("New chords", lambda: self.reroll("harmony"), "TButton"), ("New bass", lambda: self.reroll("bass"), "TButton")):
            b = ttk.Button(act, text=txt, style=st, command=cmd)
            b.pack(side="left", padx=(0, 6))
            self.btns.append(b)
        bld = ttk.Frame(mid, style="Panel.TFrame")
        bld.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Label(bld, text="Title", style="Panel.TLabel").pack(side="left")
        self.title_var = tk.StringVar()
        ttk.Entry(bld, textvariable=self.title_var, width=28).pack(side="left", padx=8)
        b = ttk.Button(bld, text="●  Build track", style="Accent.TButton", command=self.build_track)
        b.pack(side="left", padx=4)
        self.btns.append(b)
        self.studio_btn = ttk.Button(bld, text="Open in MIDI Studio", command=self.open_studio)
        self.studio_btn.pack(side="left", padx=4)
        ttk.Button(bld, text="Open folder", command=self.open_folder).pack(side="left", padx=4)
        ttk.Button(bld, text="Friends", command=self.friends_dialog).pack(side="left", padx=4)
        ttk.Button(bld, text="Share captions", command=self.share_captions).pack(side="left", padx=4)
        ttk.Button(bld, text="■", width=3, command=self.stop_player).pack(side="right")
        ttk.Button(bld, text="▶ Play", command=lambda: self.play(self.last_wav)).pack(side="right", padx=4)

        st = ttk.Frame(self, padding=(16, 8, 16, 12))
        st.pack(fill="x")
        self.pbar = ttk.Progressbar(st, mode="determinate", maximum=100)
        self.pbar.pack(fill="x")
        self.status = ttk.Label(st, text="Ready.", style="Muted.TLabel")
        self.status.pack(anchor="w", pady=(4, 0))
        self.log = tk.Text(st, height=6, bg=C["panel"], fg=C["mut"], relief="flat", font=self.f_mono, wrap="none")
        self.log.pack(fill="x", pady=(4, 0))

    # ---------------------------------------------------------------- the Electronium cockpit
    def _cockpit(self, body):
        """Every Electronium control on one flat panel: no menus to dig through."""
        k = ttk.Frame(body, style="Panel.TFrame", padding=12)
        k.grid(row=0, column=2, sticky="nse", padx=(10, 0))
        ttk.Label(k, text="Electronium", style="Head.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        self.el_on, self.el_drums = tk.BooleanVar(), tk.BooleanVar()
        ttk.Checkbutton(k, text="writes the lead", variable=self.el_on).grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(k, text="plays the drums", variable=self.el_drums).grid(row=1, column=2, columnspan=2, sticky="w")
        r = 2
        f = ttk.Frame(k, style="Panel.TFrame")
        f.grid(row=r, column=0, columnspan=4, sticky="w", pady=(8, 2))
        ttk.Label(f, text="Bounty", style="Panel.TLabel", width=9).pack(side="left")
        self.el_bounty = tk.StringVar(value="1")
        ttk.Button(f, text="◀", width=2, command=lambda: self._bounty_step(-1)).pack(side="left")
        ttk.Entry(f, textvariable=self.el_bounty, width=10, justify="center").pack(side="left", padx=3)
        ttk.Button(f, text="▶", width=2, command=lambda: self._bounty_step(1)).pack(side="left")
        ttk.Button(f, text="⚄", width=2, command=self._bounty_roll).pack(side="left", padx=(3, 0))
        r += 1
        f = ttk.Frame(k, style="Panel.TFrame")
        f.grid(row=r, column=0, columnspan=4, sticky="w", pady=2)
        ttk.Label(f, text="Scale", style="Panel.TLabel", width=9).pack(side="left")
        self.el_scale = ttk.Combobox(f, values=["key"] + list(EL.SCALES), state="readonly", width=13)
        self.el_scale.pack(side="left")
        ttk.Label(f, text=" on", style="Panel.TLabel").pack(side="left")
        self.el_root = ttk.Combobox(f, values=["key", "C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"], state="readonly", width=4)
        self.el_root.pack(side="left", padx=3)
        r += 1
        self.el = {}

        def slider(row, col, key, lab, lo, hi, step, fmt, width=11, length=110):
            ttk.Label(k, text=lab, style="Panel.TLabel", width=width).grid(row=row, column=col, sticky="w")
            v = tk.DoubleVar()
            val = ttk.Label(k, text="", style="Value.TLabel", width=5, anchor="e")
            fr_ = ttk.Frame(k, style="Panel.TFrame")
            ttk.Scale(fr_, from_=lo, to=hi, variable=v, length=length,
                      command=lambda x, val=val, step=step, fmt=fmt: val.config(text=fmt.format(round(float(x) / step) * step))).pack(side="left")
            val.pack(in_=fr_, side="left")
            fr_.grid(row=row, column=col + 1, sticky="w")
            self.el[key] = (v, val, step, fmt)
        for key, lab, lo, hi, st, fmt in (("density", "Density", 0.05, 1, 0.01, "{:.2f}"), ("mutation", "Mutation", 0, 1, 0.01, "{:.2f}"),
                                          ("up", "Up / down", 0, 1, 0.01, "{:.2f}"), ("gravity", "Chord gravity", 0, 1, 0.01, "{:.2f}"),
                                          ("accent", "Accent", 0, 1, 0.01, "{:.2f}"), ("modify", "Modify", 0, 1, 0.01, "{:.2f}")):
            slider(r, 0, key, lab, lo, hi, st, fmt, length=190)
            r += 1
        f = ttk.Frame(k, style="Panel.TFrame")
        f.grid(row=r, column=0, columnspan=4, sticky="w", pady=(6, 2))
        ttk.Label(f, text="Gate", style="Panel.TLabel", width=9).pack(side="left")
        self.el_gate = tk.StringVar()
        ttk.Entry(f, textvariable=self.el_gate, width=30, font=self.f_mono).pack(side="left")
        r += 1
        f = ttk.Frame(k, style="Panel.TFrame")
        f.grid(row=r, column=0, columnspan=4, sticky="w", pady=2)
        ttk.Label(f, text="Sidekick", style="Panel.TLabel", width=9).pack(side="left")
        self.el_side = ttk.Combobox(f, values=list(EL.SIDEKICK), state="readonly", width=17)
        self.el_side.pack(side="left")
        r += 1
        ttk.Label(k, text="Interval jumps", style="PMuted.TLabel").grid(row=r, column=0, columnspan=4, sticky="w", pady=(8, 0))
        r += 1
        for i, iv in enumerate(EL.INTERVALS):
            slider(r + i // 2, (i % 2) * 2, "iv_" + iv, iv, 0, 2, 0.01, "{:.2f}", width=7, length=70)
        r += (len(EL.INTERVALS) + 1) // 2
        ttk.Label(k, text="Behaviours (chance per bar)", style="PMuted.TLabel").grid(row=r, column=0, columnspan=4, sticky="w", pady=(8, 0))
        r += 1
        for i, bh in enumerate(EL.BEHAVIOURS):
            slider(r + i // 2, (i % 2) * 2, "bh_" + bh, bh, 0, 0.4, 0.01, "{:.2f}", width=7, length=70)
        r += (len(EL.BEHAVIOURS) + 1) // 2
        ttk.Label(k, text="Freeze & Populate", style="PMuted.TLabel").grid(row=r, column=0, columnspan=4, sticky="w", pady=(8, 0))
        r += 1
        f = ttk.Frame(k, style="Panel.TFrame")
        f.grid(row=r, column=0, columnspan=4, sticky="w", pady=2)
        self.fz_bar, self.fz_notes, self.fz_bars, self.fz_amt = tk.IntVar(value=33), tk.IntVar(value=8), tk.IntVar(value=4), tk.DoubleVar(value=1)
        for lab, var, lo, hi, w in (("bar", self.fz_bar, 1, 999, 4), ("notes", self.fz_notes, 4, 16, 3), ("for", self.fz_bars, 1, 32, 3)):
            ttk.Label(f, text=lab, style="Panel.TLabel").pack(side="left", padx=(0, 2))
            ttk.Spinbox(f, from_=lo, to=hi, textvariable=var, width=w).pack(side="left", padx=(0, 6))
        r += 1
        f = ttk.Frame(k, style="Panel.TFrame")
        f.grid(row=r, column=0, columnspan=4, sticky="w", pady=2)
        self.fz_tf = ttk.Combobox(f, values=["transpose", "invert", "mutate", "none"], state="readonly", width=9)
        self.fz_tf.set("transpose")
        self.fz_tf.pack(side="left")
        ttk.Label(f, text="amount", style="Panel.TLabel").pack(side="left", padx=(6, 2))
        ttk.Spinbox(f, from_=-7, to=7, increment=0.25, textvariable=self.fz_amt, width=5).pack(side="left")
        ttk.Button(f, text="❄ Freeze", style="Teal.TButton", command=self._freeze).pack(side="left", padx=(8, 0))
        r += 1
        self.freezes: list[dict] = []
        self.fz_list = ttk.Label(k, text="", style="PMuted.TLabel", font=self.f_mono, justify="left")
        self.fz_list.grid(row=r, column=0, columnspan=3, sticky="w")
        ttk.Button(k, text="clear", command=lambda: self._set_freezes([])).grid(row=r, column=3, sticky="e")
        r += 1
        f = ttk.Frame(k, style="Panel.TFrame")                 # "It thinks of 200 things. You keep the ones that are good."
        f.grid(row=r, column=0, columnspan=4, sticky="w", pady=(8, 2))
        ttk.Label(f, text="keep ideas", style="Panel.TLabel").pack(side="left", padx=(0, 4))
        self.el_keep = tk.StringVar(value="3")
        ttk.Entry(f, textvariable=self.el_keep, width=14).pack(side="left")
        ttk.Button(f, text="Think", command=self._think).pack(side="left", padx=(8, 0))
        r += 1
        ttk.Button(k, text="Show the terrain", command=self._terrain).grid(row=r, column=0, columnspan=4, sticky="ew", pady=(10, 0))

    def _bounty_step(self, d):
        self.el_bounty.set(str(EL.bounty_int(self.el_bounty.get()) + d))

    def _bounty_roll(self):
        import random
        self.el_bounty.set(str(random.randint(1, 99999)))

    def _set_freezes(self, fz):
        self.freezes = fz
        self.fz_list.config(text="\n".join(f"bar {f['bar']}: {f['notes']} notes x {f['bars']} bars, {f['transform']} {f['amount']:g}" for f in fz))

    def _freeze(self):
        """Capture the last N notes before a bar into a loop (the default bar is the first chorus)."""
        f = {"bar": int(self.fz_bar.get()), "notes": int(self.fz_notes.get()), "bars": int(self.fz_bars.get()),
             "transform": self.fz_tf.get(), "amount": float(self.fz_amt.get())}
        self._set_freezes([x for x in self.freezes if x["bar"] != f["bar"]] + [f])

    def _el_load(self, g):
        p = EL.patch(g.get("electronium"))
        self.el_on.set(g.get("melody", {}).get("writer") == "electronium")
        self.el_drums.set(g.get("drums") == "electronium")
        self.el_bounty.set(str(p["bounty"]))
        self.el_scale.set(p["scale"])
        self.el_root.set(str(p["root"]))
        self.el_gate.set(p["gate"])
        self.el_side.set(p["sidekick"])
        vals = {k_: p[k_] for k_ in ("density", "mutation", "up", "gravity", "accent", "modify")}
        vals.update({"iv_" + k_: p["intervals"][k_] for k_ in EL.INTERVALS})
        vals.update({"bh_" + k_: p["behaviours"].get(k_, 0) for k_ in EL.BEHAVIOURS})
        for k_, (v, lab, step, fmt) in self.el.items():
            v.set(vals[k_])
            lab.config(text=fmt.format(vals[k_]))
        self._set_freezes(list(p.get("freeze", [])))
        self.el_keep.set(", ".join(map(str, p["keep"])) if isinstance(p["keep"], list) else str(p["keep"]))
        self.fz_bar.set(self._chorus_bars(g)[0])

    def el_patch(self, g) -> dict:
        get = lambda k_: round(self.el[k_][0].get() / self.el[k_][2]) * self.el[k_][2]
        b = self.el_bounty.get().strip() or "1"
        return EL.patch(g.get("electronium"), {
            "bounty": int(b) if b.lstrip("-").isdigit() else b, "scale": self.el_scale.get(), "root": self.el_root.get(),
            "gate": self.el_gate.get().strip() or EL.DEFAULT["gate"], "sidekick": self.el_side.get(),
            **{k_: round(get(k_), 3) for k_ in ("density", "mutation", "up", "gravity", "accent", "modify")},
            "intervals": {k_: round(get("iv_" + k_), 3) for k_ in EL.INTERVALS},
            "behaviours": {k_: round(get("bh_" + k_), 3) for k_ in EL.BEHAVIOURS}, "freeze": list(self.freezes),
            "keep": self._keep()})

    def _keep(self):
        """The keep box: a count (the critic's best N) or idea numbers, '17, 42, 108'."""
        txt = self.el_keep.get().replace(",", " ").split()
        if not txt or not all(t.isdigit() for t in txt):
            raise ValueError("keep: a number of ideas (3) or idea numbers (17, 42, 108)")
        return int(txt[0]) if len(txt) == 1 else [int(t) for t in txt]

    def _think(self):
        """What the machine thought of for this Bounty and these knobs, best first; the kept ones starred."""
        try:
            self.say(EL.ideas_text(self.el_patch(self.G[self.gid()]), 20))
        except ValueError as ex:
            messagebox.showerror("Electronium", str(ex))

    def _terrain(self):
        try:
            p = self.el_patch(self.G[self.gid()])
            EL.Gate(p["gate"]).eval(EL.np.arange(16), lambda n: 0)
            self.say(EL.sketch(p, 4))
        except ValueError as ex:
            messagebox.showerror("Gate", str(ex))

    # ---------------------------------------------------------------- friends
    def friends_dialog(self):
        """The friends Bountiful remembers: one row per friend, a field per platform. Save writes friends.toml."""
        w = tk.Toplevel(self, bg=C["panel"])
        w.title("Friends")
        fr = FR.load()
        plats = list(FR.PLATFORMS)
        rows = []
        hdr = ["name", "role", "always"] + plats
        for j, h in enumerate(hdr):
            ttk.Label(w, text=h, style="PMuted.TLabel").grid(row=0, column=j, padx=3, pady=(10, 2))

        def add_row(f):
            i = len(rows) + 1
            vs = {"name": tk.StringVar(value=f.get("name", "")), "role": tk.StringVar(value=f.get("role", "")),
                  "always": tk.BooleanVar(value=bool(f.get("always")))}
            vs.update({p: tk.StringVar(value=f.get(p, "")) for p in plats})
            for j, h in enumerate(hdr):
                if h == "always":
                    ttk.Checkbutton(w, variable=vs[h]).grid(row=i, column=j)
                else:
                    ttk.Entry(w, textvariable=vs[h], width=14 if h == "name" else 11).grid(row=i, column=j, padx=2, pady=1)
            rows.append(vs)
        for f in sorted(fr.values(), key=lambda f: f["name"].lower()):
            add_row(f)
        add_row({})

        def save():
            out = {}
            try:
                for vs in rows:
                    name = vs["name"].get().strip()
                    if not name:
                        continue
                    f = {"name": name}
                    if vs["role"].get().strip():
                        f["role"] = vs["role"].get().strip()
                    if vs["always"].get():
                        f["always"] = True
                    for p in plats:
                        if vs[p].get().strip():
                            f[p] = FR.clean(p, vs[p].get())
                    out[FR.key(name)] = f
            except ValueError as ex:
                messagebox.showerror("Friends", str(ex), parent=w)
                return
            FR.save(out)
            self.say(f"friends saved: {', '.join(f['name'] for f in out.values())}")
            w.destroy()
        b = ttk.Frame(w, style="Panel.TFrame", padding=8)
        b.grid(row=999, column=0, columnspan=len(hdr), sticky="ew")
        ttk.Button(b, text="+ friend", command=lambda: add_row({})).pack(side="left")
        ttk.Button(b, text="Save", style="Accent.TButton", command=save).pack(side="right")
        ttk.Label(b, text="Handles only: no @, or paste a profile URL. Nothing is posted anywhere.", style="PMuted.TLabel").pack(side="left", padx=12)

    def share_captions(self):
        """Captions for the last built track, one per platform, friends tagged where they have a handle."""
        t = self.last_track
        if not t:
            messagebox.showinfo("Share", "Build a track first.")
            return
        names = [n for n in FR.load().values() if not n.get("always")]
        from tkinter import simpledialog
        who = simpledialog.askstring("Share", "Friends on this track (comma-separated):\n" + ", ".join(f["name"] for f in names), parent=self)
        if who is None:
            return
        FR.share(t, [x for x in who.split(",") if x.strip()], log=self.say)
        self.say(f"captions written to {t / 'share'} (not posted: paste them where you want)")

    # ---------------------------------------------------------------- genre and overrides
    def gid(self) -> str:
        return list(self.G)[self.genre.current()]

    def _genre_changed(self):
        g = self.G[self.gid()]
        self.gdesc.config(text=g["description"])
        vals = {"bpm": g["bpm"], "density": g.get("melody", {}).get("max_notes_per_bar", 6), "leap": g.get("melody", {}).get("max_leap", 7),
                "swing": g.get("swing", 0.5), "human": g.get("melody", {}).get("humanize_ms", 5)}
        for k, (v, lab, step, fmt) in self.ctl.items():
            v.set(vals[k])
            lab.config(text=fmt.format(vals[k]))
        self._el_load(g)

    def genre_cfg(self) -> dict:
        g = copy.deepcopy(self.G[self.gid()])
        get = lambda k: round(self.ctl[k][0].get() / self.ctl[k][2]) * self.ctl[k][2]
        g["bpm"] = int(get("bpm"))
        g["swing"] = round(get("swing"), 2)
        m = g.setdefault("melody", {})
        m["max_notes_per_bar"] = int(get("density"))
        m["max_leap"] = int(get("leap"))
        base_h = self.G[self.gid()].get("melody", {}).get("humanize_ms", 5) or 1
        scale = get("human") / base_h
        for part in ("melody", "bass", "comp"):
            if part in g:
                g[part]["humanize_ms"] = round(g[part].get("humanize_ms", 0) * scale if g[part].get("humanize_ms") else (get("human") if part == "melody" else 0), 1)
                if "swing" in self.G[self.gid()].get(part, {}):
                    g[part]["swing"] = g["swing"]
        if self.el_on.get() or self.el_drums.get():
            g["electronium"] = self.el_patch(self.G[self.gid()])
            EL.Gate(g["electronium"]["gate"]).eval(EL.np.arange(16), lambda n: 0)     # a bad gate stops here, with its message
        if self.el_on.get():
            m["writer"] = "electronium"
        elif m.get("writer") == "electronium":
            m["writer"] = "phrase"
        if self.el_drums.get():
            g["drums"] = "electronium"
        elif g["drums"] == "electronium":
            g["drums"] = "synthpop"
        return g

    # ---------------------------------------------------------------- work in a thread
    def run(self, fn, msg):
        if self.busy:
            messagebox.showinfo("Busy", "Still working on the last job.")
            return
        self.busy = True
        self.status.config(text=msg + " …")
        self.pbar.config(mode="indeterminate")
        self.pbar.start(12)
        for b in self.btns + [self.compose_btn]:
            b.state(["disabled"])

        def work():
            try:
                fn()
                self.q.put(("done", None))
            except Exception as ex:
                import traceback
                self.q.put(("log", traceback.format_exc()))
                self.q.put(("error", str(ex)))
        threading.Thread(target=work, daemon=True).start()

    def say(self, line: str):
        self.q.put(("log", line))

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    if val.startswith("PROGRESS"):
                        parts = val.split(" ", 2)
                        a, b = parts[1].split("/")
                        self.pbar.stop()
                        self.pbar.config(mode="determinate", value=100 * int(a) / int(b))
                        self.status.config(text=parts[2] if len(parts) > 2 else val)
                    self.log.insert("end", val + "\n")
                    self.log.see("end")
                elif kind == "rows":
                    self._fill(val)
                elif kind == "rows_prepend":
                    self._fill(val, prepend=True)
                elif kind == "play":
                    self.last_wav = val
                    self.play(val)
                elif kind in ("done", "error"):
                    self.busy = False
                    self.pbar.stop()
                    self.pbar.config(mode="determinate", value=100 if kind == "done" else 0)
                    for b in self.btns + [self.compose_btn]:
                        b.state(["!disabled"])
                    if kind == "error":
                        self.status.config(text="Error: " + val)
                    elif not self.status.cget("text").startswith("Done"):
                        self.status.config(text="Done.")
                elif kind == "status":
                    self.status.config(text=val)
        except queue.Empty:
            pass
        self.after(80, self._poll)

    # ---------------------------------------------------------------- actions
    def compose(self):
        g = self.genre_cfg()
        n = int(self.count.get())

        def job():
            files = B.compose(g, n, log=self.say)
            self.say("ranking …")
            self.q.put(("rows", B.rank(files, g, log=self.say)))
            self.q.put(("status", f"Done: {n} songs composed in {g['name']}. Select one and preview its chorus."))
        self.run(job, f"Composing {n} songs in {g['name']}")

    def _fill(self, rows, prepend=False):
        self.rows = rows + [r for r in self.rows if r["file"] not in {x["file"] for x in rows}] if prepend else rows
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rows):
            self.tree.insert("", "end", iid=str(i), text=Path(r["file"]).name.replace(".am.json", ""),
                             values=(f"{r['score']:.2f}", r["key"], r["chorus"], r["melody_notes_per_bar"]))
        if self.rows:
            self.tree.selection_set("0")
            self.tree.focus("0")
            self._select()

    def sel(self) -> dict | None:
        i = self.tree.focus()
        return self.rows[int(i)] if i else None

    def _select(self):
        r = self.sel()
        if not r:
            return
        self.detail.config(text=f"{Path(r['file']).name}   seed {r['seed']}   {r['key']}   {r['bars']} composed bars\n"
                                f"chorus  {r['chorus']}\nverse   {r['verse']}\nbridge  {r['bridge']}")
        g = self.G[self.gid()]
        if not self.title_var.get() or self.title_var.get().startswith(tuple(x["name"].split("'")[0] for x in self.G.values())):
            self.title_var.set(f"{g['name'].split(chr(39))[0].strip()} {r['seed'] % 1000}")

    def preview(self):
        r = self.sel()
        if not r:
            return
        g = self.genre_cfg()

        def job():
            out = B.DATA / "tracks" / ".preview" / f"{g['id']}-{r['seed']}"
            B.produce(Path(r["file"]), g, title=f"preview {r['seed']}", out=out, log=lambda s: None)
            a, b = self._chorus_bars(g)
            self.say(f"rendering bars {a}-{b} …")
            code = B.render(out, f"{a}-{b}", log=self.say)
            wav = out / "exports" / "preview.wav"
            if code == 0 and wav.exists():
                self.q.put(("play", wav))
                self.q.put(("status", f"Done: playing the chorus (bars {a}-{b}) of {Path(r['file']).name}."))
        self.run(job, "Producing and rendering the chorus")

    def _chorus_bars(self, g) -> tuple[int, int]:
        bar = 1
        for blk in g["arrangement"]:
            if blk["loop"] == "A" and "lead" in blk.get("parts", []):
                return bar, bar + min(8, blk["bars"]) - 1
            bar += blk["bars"]
        return 1, 8

    def reroll(self, what: str):
        r = self.sel()
        if not r:
            return
        g = self.genre_cfg()

        def job():
            import random
            files = B.compose(g, 0, [random.randint(1, 2**31 - 2)], pin=Path(r["file"]), reroll=[what], log=self.say)
            rows = B.rank(files, g, log=self.say)
            self.q.put(("rows_prepend", rows))
            self.q.put(("status", f"Done: new {what} for {Path(r['file']).name} (added at the top). Preview it to compare."))
        self.run(job, f"Re-rolling the {what}")

    def _fill_prepend(self, rows):
        self._fill(rows, prepend=True)

    def build_track(self):
        r = self.sel()
        if not r:
            return
        g = self.genre_cfg()
        title = self.title_var.get().strip() or f"{g['name']} {r['seed']}"

        def job():
            out = B.produce(Path(r["file"]), g, title=title, log=self.say)
            self.last_track = out
            self.say("rendering the full track …")
            code = B.render(out, log=self.say)
            wav = out / "exports" / f"{B.slug(title)}.wav"
            if code == 0 and wav.exists():
                self.last_wav = wav
                self.q.put(("status", f"Done: {out}  (WAV, MP3, stems, MIDI, notes.txt). ▶ Play, or open it in MIDI Studio."))
        self.run(job, f"Building '{title}'")

    def open_studio(self):
        t = self.last_track
        if not t:
            messagebox.showinfo("MIDI Studio", "Build a track first.")
            return
        subprocess.Popen([str(STUDIO), str(next(t.glob("*.mid"))), str(t / "instruments.toml")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def open_folder(self):
        p = self.last_track or B.DATA / "tracks"
        subprocess.Popen(["xdg-open", str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def play(self, path):
        self.stop_player()
        if not path or not Path(path).exists():
            return
        for cmd in (["pw-play"], ["paplay"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]):
            if shutil.which(cmd[0]):
                self.player = subprocess.Popen(cmd + [str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return

    def stop_player(self):
        if self.player and self.player.poll() is None:
            self.player.terminate()

    def _quit(self):
        self.stop_player()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
