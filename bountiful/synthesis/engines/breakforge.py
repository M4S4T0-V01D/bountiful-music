"""Breakforge: procedural drums and a mutating breakbeat generator, built for 170-174 BPM jungle.

Drums   every hit is synthesised (breakforge_voices.py): kick, snare, ghost, closed / open hat (the closed hat chokes
        the open one), ride, crash, rim, three toms and a reversed swell, with `grit` for an old-sampler edge.
Breaks  four original two-bar breaks (32 sixteenths). Each two-bar phrase is mutated from the song seed and its
        phrase number, never from the render, so the same seed always plays the same drums at any block size:
          chop      a beat-long slice replaced by another slice of the break (cut-up)
          stutter   half a slice repeated over the next one or two
          reverse   a slice played back to front
          halftime  snare on beat 3 only, the rest turned to ghosts
          drop      the middle of the second bar emptied for the bass
          ghosts    ghost notes on the empty off-steps
          rolls     the last beat turned into a 32nd snare roll
        Mutation grows through each `fill_bars` phrase (the first two bars play close to the break as written) and the
        phrase ends on a fill: a snare roll, a tom run, a stutter or a drop into a reversed swell.
Uses    1. the engine: MIDI drum notes play the kit (GM map); with `generate` on it plays its own break from the clock.
        2. songs: producer.drum_bar(style = "breakforge") writes the break into the song's MIDI and kit() is the
           render_midi drum kit, so the drums come out as individual stems (kick, snare, hats, perc, cymbals).
        3. export_midi() writes the break as a GM drum MIDI file; render_stems() renders each stem separately.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from synthesis.engine_api import CAPS_BASE, Engine, Param
from synthesis.engines import breakforge_voices as BV

VOICE_FILE = str(Path(BV.__file__).resolve())
STEMS = ("kick", "snare", "hats", "perc", "cymbals")
# sound -> (voice function, fixed args, stem, engine gain dB, pan)
SOUNDS = {
    "kick": ("kick", {}, "kick", -10.0, 0.0),
    "snare": ("snare", {}, "snare", -10.0, 0.0),
    "ghost": ("ghost", {}, "snare", -17.0, 0.12),
    "hat": ("hat", {}, "hats", -16.0, 0.4),
    "open": ("open_hat", {}, "hats", -16.0, 0.4),
    "ride": ("ride", {}, "cymbals", -17.0, -0.45),
    "crash": ("crash", {}, "cymbals", -16.0, -0.5),
    "rim": ("rim", {}, "perc", -12.0, 0.3),
    "tom_hi": ("tom", {"pitch": 185.0}, "perc", -9.0, 0.35),
    "tom_mid": ("tom", {"pitch": 135.0}, "perc", -9.0, 0.0),
    "tom_lo": ("tom", {"pitch": 92.0}, "perc", -9.0, -0.35),
    "swell": ("swell", {}, "cymbals", -15.0, 0.0),
}
MAP = {36: "kick", 35: "kick", 38: "snare", 39: "snare", 40: "ghost", 37: "rim", 42: "hat", 44: "hat", 46: "open",
       51: "ride", 59: "ride", 53: "ride", 49: "crash", 57: "crash", 50: "tom_hi", 48: "tom_hi", 47: "tom_mid",
       45: "tom_lo", 43: "tom_lo", 41: "tom_lo", 55: "swell"}
NOTE = {"kick": 36, "snare": 38, "ghost": 40, "rim": 37, "hat": 42, "open": 46, "ride": 51, "crash": 49,
        "tom_hi": 50, "tom_mid": 47, "tom_lo": 45, "swell": 55}

_k, _s, _g = "kick", "snare", "ghost"
BREAKS = {                                 # (sixteenth 0-31, sound, velocity): original two-bar breaks
    "forge": [(0, _k, 1.0), (4, _s, .95), (7, _g, .35), (10, _k, .9), (11, _k, .6), (12, _s, .95), (14, _g, .4),
              (15, _g, .3), (18, _k, .9), (20, _s, .95), (22, _g, .35), (25, _g, .3), (26, _k, .85), (28, _s, .9),
              (30, _g, .4), (31, _s, .55)],
    "rollers": [(0, _k, 1.0), (4, _s, .95), (6, _k, .7), (10, _k, .9), (12, _s, .95), (15, _g, .35), (16, _k, 1.0),
                (20, _s, .95), (23, _g, .3), (24, _k, .6), (26, _k, .85), (28, _s, .95), (30, _g, .35)],
    "stepper": [(0, _k, 1.0), (3, _g, .3), (4, _s, .95), (8, _k, .85), (9, _g, .3), (12, _s, .95), (13, _g, .35),
                (16, _k, 1.0), (19, _k, .7), (20, _s, .95), (24, _k, .8), (27, _g, .3), (28, _s, .95), (30, _s, .5),
                (31, _g, .35)],
    "tumble": [(0, _k, 1.0), (2, _k, .75), (4, _s, .95), (6, _g, .35), (7, _s, .5), (9, _k, .8), (10, _k, .85),
               (12, _s, .95), (14, _g, .4), (15, _s, .45), (17, _k, .7), (18, _k, .9), (20, _s, .95), (21, _g, .3),
               (23, _g, .35), (25, _k, .8), (28, _s, .95), (29, _g, .3), (31, _s, .6)],
}
VARIANTS = 12                              # round-robin takes per voice setting
FILLS = ("roll", "toms", "stutter", "drop_swell")

PARAMS = (
    Param("generate", False, kind="bool", doc="play its own break from the clock (off: MIDI notes play the kit)"),
    Param("pattern", "forge", kind="choice", choices=tuple(BREAKS), doc="the two-bar break mutations start from"),
    Param("intensity", 0.5, 0.0, 1.0, doc="how far the mutations go"),
    Param("chop", 0.5, 0.0, 1.0, doc="slices replaced by other slices"),
    Param("stutter", 0.3, 0.0, 1.0, doc="half-slices repeated"),
    Param("reverse", 0.2, 0.0, 1.0, doc="slices played back to front"),
    Param("halftime", 0.15, 0.0, 1.0, doc="phrases dropped to half-time"),
    Param("drop", 0.15, 0.0, 1.0, doc="second bars emptied for the bass"),
    Param("ghosts", 0.4, 0.0, 1.0, doc="ghost notes on empty off-steps"),
    Param("rolls", 0.3, 0.0, 1.0, doc="32nd snare rolls"),
    Param("fill_bars", 8, 2, 32, "int", unit="bars", doc="phrase length; its last bar is a fill"),
    Param("hats", 0.6, 0.0, 1.0, doc="hat density"),
    Param("ride", 0.8, 0.0, 1.0, doc="ride level"),
    Param("swing", 0.5, 0.5, 0.7, doc="16th swing (generate mode)"),
    Param("tune", 0.0, -12.0, 12.0, unit="st", doc="pitch of kick, snare and toms"),
    Param("punch", 0.5, 0.0, 1.0, doc="kick click and drive"),
    Param("kick_decay", 0.26, 0.08, 0.8, unit="s"),
    Param("snap", 0.7, 0.0, 1.0, doc="snare transient"),
    Param("snare_decay", 0.15, 0.05, 0.4, unit="s"),
    Param("hat_decay", 0.032, 0.01, 0.1, unit="s"),
    Param("ride_bell", 0.35, 0.0, 1.0),
    Param("grit", 0.0, 0.0, 1.0, doc="decimation, bit reduction and drive"),
    Param("width", 0.7, 0.0, 1.0),
    Param("level", 1.0, 0.0, 2.0),
)
_SCHEMA = {p.name: p for p in PARAMS}


def _params(params: dict | None) -> dict:
    P = {p.name: p.default for p in PARAMS}
    for k, v in (params or {}).items():
        if k in _SCHEMA:
            P[k] = _SCHEMA[k].clamp(v)
    return P


def voice_args(sound: str, params: dict | None = None) -> tuple[str, dict]:
    """The voice function and its arguments for a sound under these params."""
    P = _params(params)
    fn, fixed, _, _, _ = SOUNDS[sound]
    t = 2.0 ** (P["tune"] / 12.0)
    a = dict(fixed)
    if sound == "kick":
        a.update(pitch=50 * t, punch=190 * t, drive=1.0 + 1.5 * P["punch"], click=0.15 + 0.45 * P["punch"],
                 decay=P["kick_decay"])
    elif sound == "snare":
        a.update(tone=190 * t, snap=P["snap"], decay=P["snare_decay"], crack=2200 * t ** 0.5)
    elif sound == "ghost":
        a.update(tone=210 * t, decay=P["snare_decay"] * 0.5)
    elif sound == "hat":
        a.update(decay=P["hat_decay"])
    elif sound == "open":
        a.update(decay=P["hat_decay"] * 8)
    elif sound == "ride":
        a.update(bell=P["ride_bell"])
    elif sound.startswith("tom"):
        a["pitch"] = a["pitch"] * t
    if P["grit"] > 0:
        a["grit"] = P["grit"]
    return fn, {k: round(float(v), 4) for k, v in a.items()}


# ------------------------------------------------------------------ the break generator

def phrase(p: int, seed: int = 0, params: dict | None = None) -> tuple[list, list]:
    """Two-bar phrase p of the break layer: ([(sixteenth 0-32, sound, vel)], [mutation tags])."""
    P = _params(params)
    rng = np.random.default_rng([int(seed) & 0x7FFFFFFF, 1913, int(p)])
    nph = max(1, int(P["fill_bars"]) // 2)
    pos = p % nph
    m = P["intensity"] * ((0.35 + 0.65 * pos / (nph - 1)) if nph > 1 else 1.0)
    if pos == 0:
        m *= 0.3                                       # each phrase opens close to the break as written
    sl = [[(s - 4 * i, snd, v) for s, snd, v in BREAKS[P["pattern"]] if 4 * i <= s < 4 * i + 4] for i in range(8)]
    tags = []
    for i in range(1, 8):                              # chop: never the downbeat slice
        if rng.random() < P["chop"] * m * 0.5:
            j = int(rng.integers(8))
            if j != i:
                sl[i] = list(sl[j])
                tags.append(f"chop {i}<{j}")
    if rng.random() < P["halftime"] * m * 0.6:
        for i in range(8):
            sl[i] = [(s, _g if snd == _s else snd, v * (0.4 if snd == _s else 1.0)) for s, snd, v in sl[i]
                     if not (snd == _k and i in (2, 6) and s == 0)]
        sl[2] = [e for e in sl[2] if e[0] != 0] + [(0, _s, 0.97)]
        sl[6] = [e for e in sl[6] if e[0] != 0] + [(0, _s, 0.97)]
        tags.append("halftime")
    if rng.random() < P["stutter"] * m:
        i, n = int(rng.integers(2, 7)), int(rng.integers(1, 3))
        src = [e for e in sl[i] if e[0] < 2]
        if src:
            for k in range(i, min(8, i + n)):
                sl[k] = src + [(s + 2, snd, v * 0.85) for s, snd, v in src]
            tags.append(f"stutter {i}x{n}")
    if rng.random() < P["reverse"] * m:
        i = int(rng.integers(1, 8))
        if sl[i]:
            sl[i] = [(3 - s, snd, v) for s, snd, v in sl[i]]
            tags.append(f"reverse {i}")
    if rng.random() < P["drop"] * m * 0.6:
        sl[4] = sl[5] = sl[6] = []
        tags.append("drop")
    if rng.random() < P["rolls"] * m:
        sl[7] = [(k * 0.5, _s, 0.35 + 0.07 * k) for k in range(8)]
        tags.append("roll")
    if nph > 1 and pos == nph - 1:                     # the phrase's last bar: a fill
        w = np.array([1.0, 0.6 + P["intensity"], 0.4 + P["intensity"], 0.3 + P["drop"]])
        f = FILLS[int(rng.choice(4, p=w / w.sum()))]
        if f == "roll":
            sl[6] = [(s, _s, 0.45 + 0.05 * s) for s in range(4)]
            sl[7] = [(k * 0.5, _s, 0.6 + 0.05 * k) for k in range(8)]
        elif f == "toms":
            run = ("tom_hi", "tom_hi", "tom_mid", "tom_mid", "tom_lo", "tom_lo", _k, _s)
            sl[6], sl[7] = [(s, run[s], 0.8) for s in range(4)], [(s, run[4 + s], 0.85) for s in range(4)]
        elif f == "stutter":
            sl[7] = [(s, _s, 0.55 + 0.12 * s) for s in range(4)]
        else:
            sl[6], sl[7] = [], [(0, "swell", 0.9)]
        tags.append(f"fill {f}")
    ghosted = set()
    if P["ghosts"] > 0:
        taken = {4 * i + s for i in range(8) for s, _, _ in sl[i]}
        for st in range(1, 32, 2):
            if st not in taken and rng.random() < P["ghosts"] * (0.15 + 0.6 * m):
                ghosted.add(st)
    out: dict = {}
    for i in range(8):
        for s, snd, v in sl[i]:
            key = (round(4 * i + s, 3), snd)
            out[key] = max(out.get(key, 0.0), float(v))
    for st in ghosted:
        out[(float(st), _g)] = 0.18 + 0.2 * float(rng.random())
    return sorted((s, snd, v) for (s, snd), v in out.items()), tags


def bar_steps(bar: int, seed: int = 0, params: dict | None = None, layers=("break", "hat", "ride")) -> list:
    """One bar of the drums as [(sixteenth 0-16, sound, vel)] (32nds fall on .5). Pure function of its arguments."""
    P = _params(params)
    layers = set(layers)
    ev = []
    if "break" in layers:
        half = bar % 2
        ev += [(s - 16 * half, snd, v) for s, snd, v in phrase(bar // 2, seed, P)[0] if 16 * half <= s < 16 * half + 16]
    rng = np.random.default_rng([int(seed) & 0x7FFFFFFF, 2, int(bar)])
    if "hat" in layers and P["hats"] > 0:
        open_ = P["hats"] > 0.3 and bar % 2 == 1
        for s in range(16):
            if open_ and s == 14:
                ev.append((14, "open", 0.45))
            elif s % 2 == 0 or rng.random() < P["hats"]:
                ev.append((s, "hat", (0.5 if s % 4 == 2 else 0.38 if s % 2 == 0 else 0.26) * (0.6 + 0.4 * P["hats"])))
    if "ride" in layers and P["ride"] > 0:
        ev += [(s, "ride", P["ride"] * (0.55 if s % 4 == 0 else 0.4)) for s in range(0, 16, 2)]
    if "crash" in layers and bar % max(2, int(P["fill_bars"])) == 0:
        ev.append((0, "crash", 0.75))
    if "perc" in layers:
        ev += [(s, "rim", 0.35) for s in ((3, 11) if bar % 2 == 0 else (6, 13))]
    hum = np.random.default_rng([int(seed) & 0x7FFFFFFF, 3, int(bar)]).normal(0, 0.035, len(ev))
    return [(float(s), snd, float(np.clip(v + h, 0.05, 1.0))) for (s, snd, v), h in zip(ev, hum)]


def kit(params: dict | None = None) -> dict:
    """The kit in render_midi.py's drum-track format: one stem each for kick, snare, hats, perc and cymbals."""
    sounds = {}
    for name in SOUNDS:
        fn, args = voice_args(name, params)
        sounds[name] = {"py": {"module": VOICE_FILE, "fn": fn, "args": args}, "stem": SOUNDS[name][2]}
    return {"map": {int(k): v for k, v in MAP.items()}, "sounds": sounds,
            "stems": {"kick": {"hp": 28, "mono": True, "drive": 1.2, "gain_db": -3.0},
                      "snare": {"hp": 120, "sends": {"room": 0.18, "plate": 0.08}, "gain_db": -4.0},
                      "hats": {"hp": 400, "pan": 0.18, "gain_db": -10.0},
                      "perc": {"sends": {"room": 0.2}, "width": 1.2, "gain_db": -9.0},
                      "cymbals": {"hp": 300, "pan": -0.2, "sends": {"plate": 0.1}, "gain_db": -13.0}}}


def export_midi(path, bars: int = 16, bpm: float = 172.0, seed: int = 0, params: dict | None = None,
                layers=("break", "hat", "ride", "crash")) -> Path:
    """The generated break as a GM drum MIDI file (channel 10), swung as the engine plays it."""
    import mido
    P = _params(params)
    ppq = 480
    mf = mido.MidiFile(type=1, ticks_per_beat=ppq)
    meta = mido.MidiTrack()
    meta += [mido.MetaMessage("track_name", name="Breakforge", time=0),
             mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0),
             mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0)]
    mf.tracks.append(meta)
    msgs = []
    for b in range(bars):
        for s, snd, v in bar_steps(b, seed, P, layers):
            on = round((b * 4 + _swung(s, P["swing"])) * ppq)
            vel = int(np.clip(round(v * 127), 1, 127))
            msgs += [(on, 1, mido.Message("note_on", channel=9, note=NOTE[snd], velocity=vel)),
                     (on + ppq // 8, 0, mido.Message("note_off", channel=9, note=NOTE[snd], velocity=0))]
    tr = mido.MidiTrack()
    tr.append(mido.MetaMessage("track_name", name="drums", time=0))
    now = 0
    for t, _, msg in sorted(msgs, key=lambda x: (x[0], x[1])):
        tr.append(msg.copy(time=t - now))
        now = t
    mf.tracks.append(tr)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mf.save(path)
    return path


def _swung(s: float, swing: float) -> float:
    """Sixteenth -> beat, odd sixteenths pushed late by swing (as producer.drum_bar does)."""
    return s / 4 + ((swing - 0.5) * 0.5 if float(s).is_integer() and int(s) % 2 else 0.0)


# ------------------------------------------------------------------ the engine

_CHOKE: dict = {}


def _choke(sr: int) -> np.ndarray:
    """1 before the choke, then a 4 ms exponential fade over 50 ms (a table, so every block size gets the same bits)."""
    if sr not in _CHOKE:
        _CHOKE[sr] = np.concatenate([[1.0], np.exp(-np.arange(int(0.05 * sr) + 1) / (0.004 * sr)), [0.0]])
    return _CHOKE[sr]


def _order(h: dict) -> tuple:
    return (-h["pos"], h.get("id", 0))


class Breakforge(Engine):
    ID = "breakforge"
    NAME = "Breakforge"
    VERSION = 1
    DESCRIPTION = "Procedural drums and a seeded, mutating jungle break generator; stems and MIDI export."
    CAPS = CAPS_BASE | {"drums", "generator", "stems", "midi_export"}
    POLY = 1
    PARAMS = PARAMS
    PRESETS = {
        "afterimage-rollers": {"generate": True, "pattern": "rollers", "intensity": 0.45, "ghosts": 0.5, "ride": 0.9,
                               "hats": 0.4, "tune": -1, "snare_decay": 0.18},
        "tearout": {"generate": True, "pattern": "tumble", "intensity": 0.95, "chop": 0.9, "stutter": 0.7,
                    "rolls": 0.7, "grit": 0.45, "punch": 0.9, "snap": 0.9, "ride": 0.3},
        "steppers": {"generate": True, "pattern": "stepper", "intensity": 0.6, "halftime": 0.6, "drop": 0.4,
                     "hats": 0.8, "ride": 0.0, "kick_decay": 0.4, "tune": -3},
        "liquid-ride": {"generate": True, "pattern": "forge", "intensity": 0.3, "chop": 0.2, "ghosts": 0.7,
                        "ride": 1.0, "ride_bell": 0.6, "hats": 0.25, "snare_decay": 0.2, "swing": 0.54},
        "chopped-tumble": {"generate": True, "pattern": "tumble", "intensity": 0.75, "chop": 1.0, "reverse": 0.6,
                           "stutter": 0.5, "fill_bars": 4},
        "mpc-grit": {"generate": True, "pattern": "forge", "intensity": 0.55, "grit": 0.7, "hat_decay": 0.02,
                     "swing": 0.58, "tune": 2},
        "midi-kit": {"generate": False},
    }

    def init_state(self) -> None:
        self.hits: list = []                            # sounding hits: {s, v, seed, pos, choke, args}
        self._cache: dict = {}                          # rendered hit buffers (rebuilt from each hit's seed)
        self._bars: dict = {}                           # generated bars (pure functions of seed and params)
        self._stems = None
        self.last_tags: list = []

    def state(self) -> dict:
        return {"hits": self.hits}

    def load_state(self, d: dict) -> None:
        self.hits = [dict(h) for h in d.get("hits", [])]

    def diagnostics(self) -> dict:
        d = super().diagnostics()
        d["voices"] = len(self.hits)
        return d

    # ------------------------------------------------------------------ hits
    def trigger(self, sound: str, vel: float, offset: int = 0) -> None:
        """Start a hit `offset` samples into the coming chunk. A closed hat chokes a ringing open hat."""
        if sound not in SOUNDS:
            return
        if sound == "hat":
            for h in self.hits:
                if h["s"] == "open" and h["choke"] < 0:
                    h["choke"] = h["pos"] + offset
        fn, args = voice_args(sound, self.v)
        self.hits.append({"s": sound, "v": round(float(vel), 4), "seed": int(self.rng.integers(VARIANTS)),
                          "pos": -int(offset), "choke": -1, "fn": fn, "args": args, "id": self._next_id()})
        self.hits = self.hits[-48:]

    def _buf(self, h: dict) -> np.ndarray:
        """The hit's sound: one of VARIANTS round-robin takes per voice setting, rendered at full velocity once and
        scaled per hit (the voices scale linearly by 0.3 + 0.7 vel), so a long render synthesises each take only once."""
        key = (h["fn"], h["seed"], tuple(sorted(h["args"].items())))
        b = self._cache.get(key)
        if b is None:
            if len(self._cache) > 512:
                self._cache.clear()
            b = BV.RAW[h["fn"]](np.random.default_rng([self.seed & 0x7FFFFFFF, h["seed"]]), 1.0, **h["args"])
            self._cache[key] = b
        return b

    def note_on(self, pitch: int, vel: float) -> None:
        self.trigger(MAP.get(int(pitch), "rim"), vel)

    def note_off(self, pitch: int) -> None:
        pass

    def _bar(self, bar: int) -> list:
        key = (bar, tuple(sorted((k, self.v[k]) for k in ("pattern", "intensity", "chop", "stutter", "reverse",
                                                          "halftime", "drop", "ghosts", "rolls", "fill_bars", "hats",
                                                          "ride", "swing"))))
        ev = self._bars.get(key)
        if ev is None:
            if len(self._bars) > 64:
                self._bars.clear()
            ev = sorted((bar * 4 + _swung(s, self.v["swing"]), snd, v) for s, snd, v in bar_steps(bar, self.seed, self.v))
            self._bars[key] = ev
        return ev

    def _generate(self, n: int) -> None:
        spb = 60.0 / self.bpm * self.sr                  # samples per beat
        b0, b1 = self.beat(), self.beat(self.t + n)
        for bar in range(int(np.floor(b0 / 4)), int(np.floor(b1 / 4)) + 1):
            if bar < 0:
                continue
            if bar % 2 == 0:
                self.last_tags = phrase(bar // 2, self.seed, self.v)[1]
            for hb, snd, v in self._bar(bar):
                at = self._start + int(round((hb - self.t0_beats) * spb))
                if self.t <= at < self.t + n:
                    self.trigger(snd, v, at - self.t)

    # ------------------------------------------------------------------ sound
    def synth(self, n: int, inp) -> np.ndarray:
        if self.v["generate"]:
            self._generate(n)
        out = np.zeros((n, 2))
        stems = {} if self._stems is not None else None
        keep = []
        for h in sorted(self.hits, key=_order):                         # trigger order, whatever the block size
            b = self._buf(h)
            st = max(0, -h["pos"])
            i0 = max(0, h["pos"])
            seg = b[i0:i0 + n - st] * (0.3 + 0.7 * h["v"])
            if len(seg):
                if h["choke"] >= 0:
                    idx = np.arange(i0, i0 + len(seg))
                    seg = seg * _choke(self.sr)[np.clip(idx - h["choke"] + 1, 0, None).clip(max=len(_choke(self.sr)) - 1)]
                _, _, stem, gdb, pan = SOUNDS[h["s"]]
                a = (np.clip(pan * self.v["width"], -1, 1) + 1) * np.pi / 4
                g = 10 ** (gdb / 20) * np.sqrt(2)
                y = np.zeros((n, 2))
                y[st:st + len(seg), 0] = seg * np.cos(a) * g
                y[st:st + len(seg), 1] = seg * np.sin(a) * g
                out += y
                if stems is not None:
                    stems[stem] = stems.get(stem, 0) + y
            h["pos"] += n
            done = h["pos"] >= len(b) or (h["choke"] >= 0 and h["pos"] > h["choke"] + 0.05 * self.sr)
            if not done:
                keep.append(h)
        self.hits = sorted(keep, key=_order)
        out *= self.v["level"]
        if stems is not None:
            for k, y in stems.items():
                self._stems[k][self.t - self._stem_t0:self.t - self._stem_t0 + n] += y * self.v["level"]
        return out.astype(np.float32)

    def render_stems(self, events: list | None, n: int, bpm: float = 172.0, automation: dict | None = None,
                     modulation=None, t0_beats: float = 0.0, block: int = 256) -> dict:
        """Each stem rendered on its own: {kick, snare, hats, perc, cymbals: (n, 2)}; they sum to render()."""
        self._stems = {k: np.zeros((n, 2)) for k in STEMS}
        self._stem_t0 = self.t
        try:
            self.render(events, n, bpm, automation, modulation, t0_beats, block=block)
            return {k: v.astype(np.float32) for k, v in self._stems.items()}
        finally:
            self._stems = None


ENGINE = Breakforge
