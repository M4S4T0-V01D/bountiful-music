"""Song Spec, the beats engine: records written in beats instead of 16th steps (docs/song-spec.md).

A bar here has its own number of beats (3/4 and 4/4 in one record), swing bends the whole beat (the off-beat eighth
lands at meta.swing, the positions between move with it), and the players write controller events next to the notes:
the sustain pedal, breath swells (CC11) and pitch bends for scoops, slides and falls. Window Frost is the first record.

The notes go to a render backend named in [render] backend, which must be on RENDERERS, the same way pyvoices are
allow-listed, so a .toml can't run code of its choosing.

    compose(S) -> Song        the notes, controller events, sub notes and the written parts, nothing rendered
    build(S, title)           compose, then hand the song to the backend, which renders, mixes and checks
"""
from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np

# render backends: name -> module. The module's mix(out, title) renders NOTES, CTRL and SUB_NOTES.
RENDERERS = {"window-frost": "window_frost"}
KICK, SNARE, SWIRL, HAT, OPEN, CRASH = 36, 38, 40, 42, 46, 49
HAT_V = (70, 44, 62, 52, 68, 42, 60, 54)   # hat accents over a bar of 8ths


class SpecError(ValueError):
    pass


class Song:
    """the form, the random stream and everything the players write"""

    def __init__(self, S):
        meta = S["meta"]
        self.S = S
        self.swing_at = meta.get("swing", 0.5)
        self.chords = {}
        for n, c in S["chords"].items():
            self.chords[n] = dict(bass=c["bass"], v=tuple(c["voicing"]), move=tuple(c["move"]),
                                  scale=tuple(c["scale"]), minor=c.get("minor", False))
        self.form = []                     # (section, beats, chord name, bar in the section)
        for sec in S["sections"]:
            loop = S["loops"].get(sec["loop"])
            if loop is None:
                raise SpecError(f"section {sec['name']}: unknown loop {sec['loop']!r}")
            for i in range(sec["bars"]):
                ch = loop[i % len(loop)]
                if ch not in self.chords:
                    raise SpecError(f"section {sec['name']}: unknown chord {ch!r}")
                self.form.append((sec["name"], sec.get("beats", 4), ch, i))
        self.lift = {s["name"]: s.get("lift", 1.0) for s in S["sections"]}
        self.bar_start = np.concatenate([[0], np.cumsum([b[1] for b in self.form])]).astype(float)
        self.start = {}
        for b, (s, *_r) in enumerate(self.form):
            self.start.setdefault(s, b)
        self.tracks = list(meta["tracks"])
        self.notes = {t: [] for t in self.tracks}
        self.ctrl = {t: [] for t in self.tracks}
        self.sub = []                      # (beat, beats, midi)
        self.parts = parts(S)
        if S.get("perform", {}).get("humanize", "legacy") != "legacy":
            raise SpecError("the beats engine has only humanize = \"legacy\" so far (one stream, players in file order)")
        self.rng = np.random.default_rng(meta["seed"])

    # ------------------------------------------------------------ events
    def cc(self, t, beat, num, val):
        self.ctrl[t].append((max(beat, 0.0), bytes([0xB0, num, int(np.clip(val, 0, 127))])))

    def bend(self, t, beat, semis):
        """pitch bend in semitones (range +-2)"""
        v = int(np.clip(8192 + semis / 2 * 8192, 0, 16383))
        self.ctrl[t].append((max(beat, 0.0), bytes([0xE0, v & 0x7F, v >> 7])))

    def swing(self, beat):
        whole = np.floor(beat)
        f = beat - whole
        f = f / 0.5 * self.swing_at if f < 0.5 else self.swing_at + (f - 0.5) / 0.5 * (1 - self.swing_at)
        return whole + f

    def note(self, t, bar, pos, dur, pitch, vel, late=0.0, jitter=0.008):
        start = self.swing(self.bar_start[bar] + pos)
        end = self.swing(self.bar_start[bar] + pos + dur)
        start = max(start + late + self.rng.normal(0, jitter), 0.0)
        vel = int(np.clip(vel + self.rng.normal(0, 4), 1, 127))
        length = max(end - start - 0.02, 0.05)
        self.notes[t].append((start, length, pitch, vel))
        return start, length

    def roll(self, t, bar, pos, dur, pitches, vel, spread=0.025):
        for k, p in enumerate(pitches):
            self.note(t, bar, pos + k * spread, dur - k * spread, p, vel - 3 * k, jitter=0.004)

    def pedal(self, t, bar, pos=0.0, length=None):
        """down just after the chord, up just before the next one"""
        a = self.bar_start[bar] + pos
        b = a + (length if length is not None else self.form[bar][1] - pos)
        self.cc(t, a + 0.06, 64, 100)
        self.cc(t, b - 0.04, 64, 0)

    def slide(self, t, start, semis, over):
        self.bend(t, start - 0.01, semis)
        for k in range(1, 7):
            self.bend(t, start + over * k / 6, semis * (1 - k / 6))

    # ------------------------------------------------------------ helpers for the players
    def bars(self):
        """(bar, section, beats, chord, bar in the section, last bar of the song)"""
        for b, (sec, meter, ch, i) in enumerate(self.form):
            yield b, sec, meter, self.chords[ch], i, b == len(self.form) - 1

    def track(self, t):
        if t not in self.notes:
            raise SpecError(f"track {t!r} isn't in meta.tracks")
        return t


def parts(S) -> dict:
    """name -> [(bar, beat, beats, pitch)], transposed; like + last = another part with its last note held"""
    out = {}
    for name, p in S.get("parts", {}).items():
        if "like" in p:
            continue
        out[name] = [(n[0], n[1], n[2], n[3] + p.get("transpose", 0)) for n in p["notes"]]
    for name, p in S.get("parts", {}).items():
        if "like" in p:
            base = out[p["like"]]
            b, pos, dur = p["last"]
            out[name] = base[:-1] + [(b, pos, dur, base[-1][3])]
    return out


def entry(cfg, sec, i):
    """the player's entry for this bar of the section: the last one whose from <= i (and inside its bars), or None"""
    e = cfg.get("sections", {}).get(sec)
    if e is None:
        return None
    hit = None
    for x in (e if isinstance(e, list) else [e]):
        if x.get("from", 0) <= i and ("bars" not in x or isinstance(x["bars"], list) or i < x["bars"]):
            hit = x
    return hit


# ---------------------------------------------------------------- players
def jazz_piano(G: Song, cfg, t):
    pats = cfg["patterns"]
    for b, sec, meter, c, i, last in G.bars():
        root, v, alt = c["bass"], c["v"], c["move"]
        if last:
            L = cfg["last"]
            G.pedal(t, b, 0, L["pedal"])
            G.roll(t, b, 0, L["dur"], (root, root + 7) + v + (v[-1] + 4,), L["vel"], spread=L["spread"])
            continue
        e = entry(cfg, sec, i)
        if e is None:
            continue
        name = e["bars"][i % len(e["bars"])]
        if name not in pats:
            raise SpecError(f"players.{t}: unknown pattern {name!r} in {sec}")
        P = pats[name]
        lift, scale = G.lift[sec], e.get("vel", 1.0)
        for pd in P.get("pedal", []):
            G.pedal(t, b, pd[0], pd[1] if len(pd) > 1 else None)
        for pos, dur, voi, vel, spread in P["hits"]:
            ps = {"v": v, "alt": alt, "rv": (root + 12,) + v}[voi]
            G.roll(t, b, pos, dur, ps, int(vel * lift * scale), spread=spread)


def jazz_bass(G: Song, cfg, t):
    rng = G.rng
    form = G.form
    for b, sec, meter, c, i, last in G.bars():
        root = c["bass"]
        fifth = root + 7
        nxt = G.chords[form[b + 1][2]]["bass"] if b + 1 < len(form) else root
        approach = nxt + (1 if rng.random() < 0.5 else -1)
        lift = G.lift[sec]
        if last:
            G.note(t, b, 0, cfg["last"]["dur"], root, cfg["last"]["vel"])
            continue
        e = entry(cfg, sec, i)
        if e is None:
            continue
        style = e["style"]
        if style == "waltz":                     # one root a bar, the fifth on 3 every other bar
            s, _ = G.note(t, b, 0, 1.9 if i % 2 else 2.8, root, 70)
            if i % 2:
                G.note(t, b, 2, 0.9, fifth if fifth < 52 else fifth - 12, 58)
            if "slide" in e and i == e.get("from", 0):
                G.slide(t, s, *e["slide"])
        elif style == "two_feel":                # root, fifth, pickup
            G.note(t, b, 0, 1.9, root, int(92 * lift), jitter=0.004)
            G.note(t, b, 2, 1.4, fifth, int(76 * lift))
            G.note(t, b, 3.5, 0.45, approach, int(66 * lift))
        elif style == "walk":
            third = 3 if c["minor"] else 4
            line = [(root, root + third, fifth, approach),
                    (root, root + 2, root + third, approach),
                    (root, root + 12, fifth, approach)][int(rng.integers(0, 3))]
            for k, p in enumerate(line):
                s, _ = G.note(t, b, k, 0.92, p, int((90 if k == 0 else 76) * lift), jitter=0.005)
                if k == 0 and rng.random() < 0.3:
                    G.slide(t, s, -1, 0.1)
        elif style == "riff":                    # the A-section riff
            s, _ = G.note(t, b, 0, 1.4, root, int(96 * lift), jitter=0.004)
            if i % 4 == 0 or rng.random() < 0.25:
                G.slide(t, s, -1, 0.12)
            G.note(t, b, 1.5, 0.45, fifth, int(72 * lift))
            if rng.random() < 0.5:
                G.note(t, b, 2.25, 0.15, fifth, 34)          # dead note
            G.note(t, b, 2.5, 0.9, root - 2 if c["minor"] else root - 5, int(84 * lift))
            G.note(t, b, 3.5, 0.45, approach, int(68 * lift))
        else:
            raise SpecError(f"players.{t}: unknown style {style!r}")


def jazz_drums(G: Song, cfg, t):
    rng = G.rng
    for b, sec, meter, c, i, last in G.bars():
        e = entry(cfg, sec, i)
        if e is None:
            continue
        lift, style = G.lift[sec], e["style"]
        if style == "pickup":                    # snare taps into the next section, from beat 3
            for k, pos in enumerate((2.0, 2.25, 2.5, 2.75)):
                G.note(t, b, pos, 0.2, SNARE, 40 + 14 * k, jitter=0.004)
            continue
        if style == "swirl":
            G.note(t, b, 0, 2.8, SWIRL, int(34 + 3 * (i % 2)), jitter=0.004)
            continue
        if i == 0:
            G.note(t, b, 0, 1, CRASH, 56)
        swell = 1 + 0.06 * ((i % 4) - 1.5) / 1.5              # 4-bar breath
        kv = lambda x: int(x * lift * swell)  # noqa: E731
        fill = i % 8 == 7
        if style == "half":                      # half-time
            G.note(t, b, 0, 0.5, KICK, kv(104), late=-0.006, jitter=0.003)
            G.note(t, b, 1.75, 0.25, KICK, kv(70), jitter=0.003)
            G.note(t, b, 2, 0.5, SNARE, kv(102 + rng.integers(0, 8)), late=0.04, jitter=0.005)
            G.note(t, b, 2, 1.5, SWIRL, kv(36), late=0.05)
            if rng.random() < 0.5:
                G.note(t, b, 3.25, 0.2, SNARE, int(rng.integers(20, 34)), late=0.01, jitter=0.008)
            for k in range(8):
                if fill and k >= 6:
                    break
                G.note(t, b, k * 0.5, 0.25, HAT, kv(HAT_V[k]), late=0.012 if k % 2 else 0.0, jitter=0.007)
        elif style == "boom":
            busy = e.get("busy", False)
            G.note(t, b, 0, 0.5, KICK, kv(104), late=-0.006, jitter=0.003)
            G.note(t, b, 2.5, 0.5, KICK, kv(90), late=-0.006, jitter=0.003)
            if i % 2 or busy:
                G.note(t, b, 2.75, 0.25, KICK, kv(66), jitter=0.003)
            if busy and rng.random() < 0.3:
                G.note(t, b, 3.75, 0.25, KICK, kv(56), jitter=0.003)
            G.note(t, b, 1, 0.5, SNARE, kv(96 + rng.integers(0, 10)), late=0.035, jitter=0.005)
            if busy:
                G.note(t, b, 1, 1.0, SWIRL, kv(34), late=0.05)
            if not fill:
                G.note(t, b, 3, 0.5, SNARE, kv(100 + rng.integers(0, 10)), late=0.035, jitter=0.005)
            for pos in (0.75, 1.75, 2.25, 3.25):                # ghost notes
                if rng.random() < 0.45:
                    G.note(t, b, pos, 0.2, SNARE, int(rng.integers(20, 34)), late=0.01, jitter=0.008)
            for k in range(8):
                pos = k * 0.5
                if fill and pos >= 3:
                    break
                if i % 4 == 3 and pos == 3.5:
                    G.note(t, b, pos, 0.5, OPEN, kv(56))
                else:
                    G.note(t, b, pos, 0.25, HAT, kv(HAT_V[k]), late=0.012 if k % 2 else 0.0, jitter=0.007)
        else:
            raise SpecError(f"players.{t}: unknown style {style!r}")
        if fill:
            for k, pos in enumerate((3.0, 3.25, 3.5, 3.75)):
                G.note(t, b, pos, 0.2, SNARE, 50 + 12 * k, jitter=0.004)


def sing(G: Song, t, start, length, vel, scoop, fall, depth, rate, natural):
    """breath and voice for a monophonic line: swell, scoop, delayed vibrato, fall-off"""
    if scoop:
        G.slide(t, start, -0.5, 0.12)
    else:
        G.bend(t, start - 0.005, 0)
    base = 78 + vel // 6
    G.cc(t, start - 0.005, 11, base)
    steps = max(int(length * 12), 1)
    for k in range(1, steps + 1):
        tt = start + length * k / steps
        x = k / steps
        G.cc(t, tt, 11, base + (30 if length >= 1 else 14) * np.sin(np.pi * min(x * 1.3, 1)) - (10 if x > 0.85 else 0))
    if length >= 1.2 and depth and not natural:           # vibrato only once a long note settles
        spb = 60.0 / G.S["meta"]["bpm"]
        onset = start + 0.6
        for k in range(int((length - 0.6) * 36)):
            tt = onset + k / 36
            G.bend(t, tt, depth * min(k / 18, 1) * np.sin(2 * np.pi * rate * (tt - onset) * spb))
    if fall:
        end = start + length
        for k in range(6):
            G.bend(t, end - 0.16 + k * 0.03, -1.2 * (k / 5) ** 2)


def phrase(G: Song, t, sec, notes, vel0, shift=0, falls=True, grace=False, depth=0.2, rate=5.2, natural=False):
    """a written line with breath: scoops after rests, falls before long gaps"""
    rng = G.rng
    base, meter = G.start[sec], G.form[G.start[sec]][1]
    last_end = -9.0
    for k, (off, pos, dur, p) in enumerate(notes):
        p += shift
        vel = int((vel0 + (6 if dur >= 1 else 0) - (4 if dur <= 0.5 else 0)) * G.lift[sec])
        if grace and dur >= 1 and rng.random() < 0.4:
            G.note(t, base + off, pos - 0.12, 0.1, p - 1, vel - 14, late=0.03, jitter=0.004)
        s, ln = G.note(t, base + off, pos, dur, p, vel, late=0.04, jitter=0.012)
        gap = (notes[k + 1][0] * meter + notes[k + 1][1] - off * meter - pos - dur
               if k + 1 < len(notes) else 9)
        sing(G, t, s, ln, vel, scoop=s - last_end > 0.4 and rng.random() < 0.35,
             fall=falls and gap >= 1 and dur >= 0.5 and rng.random() < 0.3, depth=depth, rate=rate, natural=natural)
        last_end = s + ln


def mallet(G: Song, t, sec, notes, vel0, shift=0):
    """vibes and celesta: accent the beats, let each note ring a little past its written length"""
    base = G.start[sec]
    for off, pos, dur, p in notes:
        vel = int((vel0 + (6 if pos % 1 == 0 else 0) - (6 if dur <= 0.5 else 0)) * G.lift[sec])
        G.note(t, base + off, pos, dur + 0.15, p + shift, vel, late=0.01, jitter=0.006)


def solo(G: Song, sec, lo, hi, start, run_at, run):
    """a solo over the section, two bars a phrase: short phrases with air between them, mostly eighths, each landing on
    a held chord tone, and one scale run down and back up in phrase run_at"""
    rng = G.rng
    s0 = G.start[sec]
    meter = G.form[s0][1]
    n_bars = sum(1 for f in G.form if f[0] == sec)
    phrases = n_bars // 2
    line = []
    p = start
    for ph in range(phrases):
        bar0 = ph * 2
        busy = ph / (phrases - 1)
        nxt = (bar0 + 2) * meter
        if ph == run_at:
            pent = sorted((n for n in range(lo, hi + 1) if n % 12 in run), reverse=True)
            notes = pent[:8] + pent[:8][::-1][1:8]
            b = bar0 * meter + 0.25
            for n in notes:
                line.append((int(b // meter), b % meter, 0.23, n))
                b += 0.25
            p = notes[-1]
        else:
            b = bar0 * meter + (0.5 if ph % 2 == 0 else 1.0) + (0.5 if rng.random() < 0.3 else 0.0)
            end = bar0 * meter + meter + 1.5 * busy          # phrases grow a little through the solo
            dirn = 1 if rng.random() < 0.5 else -1
            while b < end:
                ch = G.chords[G.form[s0 + int(b // meter)][2]]
                pool = [n for n in range(lo, hi + 1) if n % 12 in ch["scale"]]
                step = 0.25 if rng.random() < 0.05 + 0.25 * busy else (1.0 if rng.random() < 0.25 else 0.5)
                if b % 0.5:
                    step = 0.25                               # stay on the grid
                k = min(range(len(pool)), key=lambda j: abs(pool[j] - p))
                if rng.random() < 0.2:
                    dirn = -dirn
                if pool[k] >= hi - 3:
                    dirn = -1
                if pool[k] <= lo + 3:
                    dirn = 1
                k = int(np.clip(k + dirn * (1 if rng.random() < 0.8 else 2), 0, len(pool) - 1))
                p = pool[k]
                line.append((int(b // meter), b % meter, step * 0.9, p))
                b += step
        ch = G.chords[G.form[s0 + min(int(b // meter), n_bars - 1)][2]]   # land on the nearest chord tone, hold it
        tones = [n for n in range(lo, hi + 1) if n % 12 in {x % 12 for x in ch["v"] + (ch["bass"],)}]
        land = min(tones, key=lambda n: abs(n - p))
        dur = min(2.0, nxt - b - 0.5)
        if dur > 0.2:
            line.append((int(b // meter), b % meter, dur, land))
            p = land
    return line


def lines(G: Song, cfg, _t):
    natural = set(cfg.get("natural_vibrato", []))
    for st in cfg["steps"]:
        kind = st["play"]
        if kind == "solo":
            G.parts[st["part"]] = solo(G, st["section"], st["lo"], st["hi"], st["start"], st["run_at"], st["run"])
            continue
        if st["part"] not in G.parts:
            raise SpecError(f"players.lines: unknown part {st['part']!r}")
        t, notes = G.track(st["track"]), G.parts[st["part"]]
        if kind == "mallet":
            mallet(G, t, st["section"], notes, st["vel"], st.get("shift", 0))
        elif kind == "phrase":
            phrase(G, t, st["section"], notes, st["vel"], st.get("shift", 0), falls=st.get("falls", True),
                   grace=st.get("grace", False), depth=st.get("depth", 0.2), rate=st.get("rate", 5.2),
                   natural=t in natural)
        else:
            raise SpecError(f"players.lines: unknown step {kind!r}")


def jazz_keys(G: Song, cfg, _t):
    rng = G.rng
    up = lambda v: tuple(p + 12 for p in v[1:])  # noqa: E731
    for b, sec, meter, c, i, last in G.bars():
        e = entry(cfg, sec, i)
        if e is None:
            continue
        if e.get("vibes") == "pedal":
            G.pedal("vibes", b)
        elif e.get("vibes") == "comp":
            G.roll("vibes", b, 1.5, 0.8, up(c["v"]), int(46 * G.lift[sec]), spread=0.02)
            G.roll("vibes", b, 3.5, 0.6, up(c["move"]), int(40 * G.lift[sec]), spread=0.02)
        if e.get("flakes") and i % 2 == 1:      # celesta snowflakes, high chord tones
            flakes = sorted({p + 24 for p in c["v"]} | {p + 36 for p in c["v"][:2]})
            for pos in (3.0, 3.5):
                G.note("celesta", b, pos, 0.6, int(rng.choice(flakes)), int(rng.integers(34, 46)), jitter=0.004)


def pad(G: Song, cfg, t):
    for b, sec, meter, c, i, last in G.bars():
        e = entry(cfg, sec, i)
        if e is None:
            continue
        for p in c["v"][1:]:
            G.note(t, b, 0, cfg["last_beats"] if last else meter, p + 12, e["vel"], jitter=0.0)


def sub(G: Song, cfg, _t):
    lo, hi = cfg["fold"]

    def fold(m):
        while m > hi:
            m -= 12
        while m < lo:
            m += 12
        return m

    names = [f[2] for f in G.form]
    for b, sec, meter, c, i, last in G.bars():
        root, a = c["bass"], G.bar_start[b]
        if last:
            G.sub.append((a, cfg["last_beats"], fold(root)))
            continue
        e = entry(cfg, sec, i)
        if e is None:
            continue
        style = e["style"]
        if style == "hold_even":
            style = "hold" if i % 2 == 0 else "two"
        if style == "hold":
            G.sub.append((a, 3.9, fold(root)))
        elif style == "two":
            G.sub.append((G.swing(a), 2.45, fold(root)))
            G.sub.append((G.swing(a + 2.5), 1.4, fold(root + cfg.get("push", {}).get(names[b], 0))))
        elif style == "pickup":
            G.sub.append((a + 2, 0.9, fold(e["pitch"])))
        else:
            raise SpecError(f"players.sub: unknown style {style!r}")


PLAYERS = {"jazz_piano": jazz_piano, "jazz_bass": jazz_bass, "jazz_drums": jazz_drums, "lines": lines,
           "jazz_keys": jazz_keys, "pad": pad, "sub": sub}


def compose(S) -> Song:
    G = Song(S)
    for name, cfg in S.get("players", {}).items():
        if cfg["type"] not in PLAYERS:
            raise SpecError(f"players.{name}: unknown type {cfg['type']!r} (the beats engine has {', '.join(PLAYERS)})")
        own = cfg["type"] in ("jazz_piano", "jazz_bass", "jazz_drums", "pad")   # the others name their tracks
        PLAYERS[cfg["type"]](G, cfg, G.track(cfg.get("track", name)) if own else None)
    return G


# ---------------------------------------------------------------- render
def backend(S):
    name = S.get("render", {}).get("backend")
    if name not in RENDERERS:
        raise SpecError(f"render.backend {name!r} isn't one of {', '.join(RENDERERS)}")
    return importlib.import_module(RENDERERS[name])


def inject(G: Song, M):
    """hand the composed song to the backend module: the form, the notes and the parts its checks read"""
    tup = {n: (c["bass"], c["v"]) for n, c in G.chords.items()}
    M.FORM = [(s, m, tup[ch], i) for s, m, ch, i in G.form]
    M.BAR_START, M.TOTAL_BEATS, M.START = G.bar_start, float(G.bar_start[-1]), dict(G.start)
    M.NOTES, M.CTRL, M.SUB_NOTES = G.notes, G.ctrl, G.sub
    M.rng = G.rng                          # the mixer goes on drawing from the same stream (wind, fire, room)
    meta = G.S["meta"]                     # the mixer times its renders and its MIDI tempo from these, not the notes
    M.BPM, M.SWING = meta["bpm"], meta.get("swing", 0.5)
    M.SPB = 60.0 / M.BPM
    if M.__name__ == "window_frost":       # the parts its checks compare with the printed scores
        P, raw = G.parts, G.S["parts"]
        M.SOLO_LINE, M.TANNEN, M.OUTRO_TUNE = P["solo"], P["tannen"], P["tannen_outro"]
        M.TANNEN_G = [tuple(n) for n in raw["tannen"]["notes"]]
        M.MW1, M.MW2, M.BRIDGE = P["midwinter1"], P["midwinter2"], P["bridge"]
        loops = {k: [tup[c] for c in v] for k, v in G.S["loops"].items()}
        M.INTRO, M.OUTRO, M.A_CH, M.A2_CH, M.B_CH = loops["intro"], loops["outro"], loops["A"], loops["A2"], loops["B"]


def build(S, out: Path, title: str, log=print) -> int:
    M = backend(S)
    G = compose(S)
    inject(G, M)
    log(f"{title}: {len(G.form)} bars, " + ", ".join(f"{k} {len(v)}" for k, v in G.notes.items()) + f", sub {len(G.sub)}")
    return M.mix(out, title)
