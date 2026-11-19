"""Song Spec: a record as a TOML file instead of a script (docs/song-spec.md).

    load(path)      -> the spec as a dict (templates merged, bars resolved)
    compose(S)      -> {track: [(start_beat, end_beat, pitch, vel)]}, the chord chart
    to_lt(S)        -> the SPEC dict that lmms_tracks.make() takes
    build(S)        -> renders the record (about 6 minutes)
    validate(S)     -> runs the checks on the render, writes validation.md

Run: $PY -I bountiful/songspec.py records/moss-radio.toml [--as "Title"] [--dry] [--validate]
  --dry       compose and lint only, no render
  --validate  check an existing render
  --as        build under another title (and so another tracks/ folder), e.g. to compare a port with the original
"""
from __future__ import annotations

import contextlib
import copy
import itertools
import json
import sys
import tomllib
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lmms_tracks as LT  # noqa: E402
import paths  # noqa: E402
import producer as PR  # noqa: E402

import mido  # noqa: E402
import numpy as np  # noqa: E402

ROOT = HERE.parent


def _records(data: Path, examples: Path) -> Path:
    """The records you edit live in the music folder; the first time, it gets a copy of the examples that come
    with the app (the app's own folder may be read-only, and edits there would block updates)."""
    mine = data / "records"
    if not mine.is_dir() and data.resolve() != examples.parent.resolve():
        try:
            mine.mkdir(parents=True)
            for f in examples.glob("*.toml"):
                (mine / f.name).write_bytes(f.read_bytes())
        except OSError:
            return examples
    return mine if mine.is_dir() else examples


RECORDS = _records(LT.B.DATA, ROOT / "records")
SAMPLES = paths.SAMPLES
SF2 = SAMPLES / "sf2" / "GeneralUser-GS.sf2"
# the cleared library (docs/sample-audit.md). A sound id is "<library>:<name>"
LIBRARIES = {
    "gs": "GeneralUser GS soundfont, bank:patch",
    "dm": "samples/drummachines (LMMS DrumSynth renders)",
    "iowa": "samples/iowa cut notes",
    "pixel": "samples/pixel",
    "own": "our own generated sounds (OWN below)",
}
OWN = {"vinyl-crackle-70": SAMPLES / "lofi" / "vinyl_crackle_4bar_70.wav",
       "vinyl-crackle-80": SAMPLES / "lofi" / "vinyl_crackle_4bar_80.wav",
       "cowbell-808-tuned": SAMPLES / "phonk" / "cowbell808_tuned.wav"}
# engine voices written in Python: a record names one of these, never a file, so a .toml can't run code of its choosing
PYVOICES = {"tr808": HERE / "tr808_voice.py"}
PC = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8,
      "A": 9, "A#": 10, "Bb": 10, "B": 11}


from songspec_beats import SpecError  # noqa: E402,F401  (one error class for both engines)


# ------------------------------------------------------------------ loading
def merge(base: dict, over: dict) -> dict:
    """tables merge key by key; everything else (lists included) is replaced"""
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def load(path) -> dict:
    path = Path(path)
    if not path.exists() and (RECORDS / f"{path}.toml").exists():
        path = RECORDS / f"{path}.toml"
    S = tomllib.loads(path.read_text())
    base = S.get("meta", {}).get("extends")
    if base:
        parent = load(base)
        S["meta"].pop("extends")
        S = merge(parent, S)
    S["_path"] = str(path)
    return S


def pitch_class(x) -> int:
    if isinstance(x, int):
        return x % 12
    if x not in PC:
        raise SpecError(f"unknown note name {x!r}")
    return PC[x]


def chords(S) -> dict:
    """name -> (root pc, intervals)"""
    return {n: (pitch_class(c["root"]), list(c["intervals"])) for n, c in S["chords"].items()}


def sections(S) -> list[dict]:
    return S["sections"]


def start_bar(S, name: str) -> int:
    names = [s["name"] for s in sections(S)]
    if name not in names:
        raise SpecError(f"no section called {name!r} (sections: {', '.join(names)})")
    return 1 + sum(s["bars"] for s in sections(S)[:names.index(name)])


def total_bars(S) -> int:
    return sum(s["bars"] for s in sections(S))


def bar(S, x):
    """a bar position: a number, or "@Section", "@Section+3.5", "@Section-1" """
    if not isinstance(x, str):
        return x
    if not x.startswith("@"):
        raise SpecError(f"a bar is a number or \"@Section\", not {x!r}")
    body, off = x[1:], 0
    for sign in ("+", "-"):
        head, sep, tail = body.rpartition(sign)
        if sep and head and tail.replace(".", "", 1).isdigit():
            body, off = head, float(tail) * (1 if sign == "+" else -1)
            break
    b = start_bar(S, body) + off
    return int(b) if float(b).is_integer() else b


# ------------------------------------------------------------------ parts and voicings
def part_bars(S, v) -> list:
    """what a section plays on a line player: a part name, a transform table or inline bars -> a list of bars"""
    if isinstance(v, str):
        if v not in S.get("parts", {}):
            raise SpecError(f"no part called {v!r}")
        return S["parts"][v]
    if isinstance(v, list):
        return v
    src = part_bars(S, v["part"])
    if "bars" in v:
        a, _, b = str(v["bars"]).partition("-")
        src = src[int(a) - 1:int(b or a)]
    shift, vel = v.get("shift", 0), v.get("vel")
    out = [[[e[0], e[1] + shift, e[2], e[3] * vel if vel is not None else e[3], *e[4:]] for e in b] for b in src]
    return [[] for _ in range(v.get("rest", 0))] + out


def voice_lead(ch, name, prev, V):
    """the chord's tones in [lo, hi], nearest to the previous voicing (Moss Radio's voice())"""
    root, iv = ch[name]
    lo, hi, span = V.get("lo", 50), V.get("hi", 70), V.get("max_span", 14)
    cands = [[p for p in range(lo, hi + 1) if p % 12 == (root + i) % 12] for i in iv]
    best, score = None, 1e9
    for combo in itertools.product(*cands):
        v = sorted(combo)
        if len(set(v)) < len(iv) or v[-1] - v[0] > span:
            continue
        s = sum(abs(a - b) for a, b in zip(v, prev)) + 0.25 * abs(np.mean(v) - V.get("center", 60)) + \
            (6 if v[1] - v[0] <= 2 and v[0] < 55 else 0)
        if s < score:
            best, score = v, s
    if best is None:
        raise SpecError(f"no voicing of {name} fits {lo}-{hi} within {span} semitones")
    return best


def voice_near(ch, name, V):
    """each chord tone in [lo, hi], the first `tones` intervals only if given (Orange Mound's chord_voicing())"""
    root, iv = ch[name]
    iv = iv[:V["tones"]] if "tones" in V else iv
    lo, hi = V.get("lo", 55), V.get("hi", 72)
    out = []
    for i in iv:
        p = lo + ((root + i) % 12 - lo) % 12
        out.append(p if p <= hi else p - 12)
    return sorted(set(out))


# ------------------------------------------------------------------ the MIDI
def compose(S):
    """{track: [(start_beat, end_beat, pitch, vel)]} and the chord chart [(bar, step16, chord)]"""
    meta, P = S["meta"], S.get("perform", {})
    bpm = meta["bpm"]
    swing = meta.get("swing", 0.5) if P.get("swing", True) else 0.5
    beat_ms = 60000 / bpm
    ch = chords(S)
    players = S.get("players", {})
    tracks = meta.get("tracks") or list(dict.fromkeys(p.get("track", n) for n, p in players.items()))
    out = {t: [] for t in tracks}
    chart = []
    seed = meta.get("humanize_seed", meta.get("seed", 1))
    legacy = P.get("humanize", "per-track") == "legacy"
    shared = np.random.default_rng(seed)
    rngs = {}

    def rng(track):
        if legacy:
            return shared
        if track not in rngs:
            rngs[track] = np.random.default_rng([seed, zlib.crc32(track.encode())])
        return rngs[track]

    def put(track, b, step, pitch, length, vel, jitter, gap, delay_ms=0.0):
        r = rng(track)
        sw = (swing - 0.5) * 0.5 if int(round(step)) % 2 else 0.0
        at = (b - 1) * 4 + step / 4 + sw + (r.normal(0, jitter) / beat_ms if jitter else 0)
        s = max(0.0, at + delay_ms / beat_ms)
        if track not in out:
            raise SpecError(f"a note for track {track!r}, which isn't in meta.tracks")
        out[track].append((s, max(s + 0.05, (b - 1) * 4 + (step + length) / 4 - gap), pitch,
                           float(np.clip(vel + r.normal(0, 0.03), 0.2, 1.0))))

    V = S.get("voicing", {})
    prev = list(V.get("start", [53, 56, 60, 63]))
    chord_players = [(n, p) for n, p in players.items() if p["type"] in ("chords", "root")]
    line_players = [(n, p) for n, p in players.items() if p["type"] in ("line", "every")]
    followers = {}
    for n, p in players.items():
        if p["type"] == "follow":
            followers.setdefault(p["follows"], []).append((n, p))
    loops = S["loops"]
    b = 1
    for sec in sections(S):
        play = sec.get("play", {})
        for i in range(sec["bars"]):
            pos = i if P.get("loop_from", "section") == "section" else b - 1
            loop = loops[sec["loop"]]
            names = loop[pos % len(loop)]
            half = 16 // len(names)
            for k, cn in enumerate(names):
                v = voice_lead(ch, cn, prev, V) if V.get("mode", "lead") == "lead" else voice_near(ch, cn, V)
                prev = v
                chart.append((b, k * half, cn))
                st, ln = k * half, half
                for n, p in chord_players:
                    how = play.get(n)
                    if not how:
                        continue
                    how = how if isinstance(how, dict) else {"mode": how if isinstance(how, str) else p.get("mode", "hold")}
                    trk = p.get("track", n)
                    if p["type"] == "root":
                        base = p.get("octave", 36)
                        put(trk, b, st, base + (ch[cn][0] - base) % 12, ln, p.get("vel", 0.7), p.get("jitter_ms", 0),
                            p.get("gap", 0.04))
                        continue
                    if p.get("voicing") == "near":
                        tones = voice_near(ch, cn, p.get("near", {}))
                    else:
                        tones = v
                    tones = tones[p.get("drop_bottom", 0):]
                    mode = how.get("mode", "hold")
                    if mode == "hold":
                        hits = [(st, ln + sec.get("ring", 0), how.get("hold_vel", p.get("hold_vel", 0.55)))]
                    elif len(names) > 1:
                        sp = p.get("split", {"len": -1, "vel": 0.66, "step_vel": -0.04})
                        hits = [(st, ln + sp["len"], sp["vel"] + sp["step_vel"] * k)]
                    else:
                        hits = [tuple(h) for h in (p["even"] if i % 2 == 0 else p["odd"])]
                    for hs, hl, hv in hits:
                        for j, q in enumerate(tones):
                            put(trk, b, hs, q + p.get("shift", 0), hl, hv + p.get("bottom_vel", 0.0) * (j == 0),
                                p.get("jitter_ms", 6), p.get("gap", 0.04), delay_ms=p.get("roll_ms", 0) * j)
                if k == len(names) - 1:
                    for trk, nb in sec.get("notes", {}).items():
                        for s, q, n_, vv, *_ in nb[i] if i < len(nb) else []:
                            put(trk, b, s, q, n_, vv, 0, 0.04)
            for n, p in line_players:
                how = play.get(n)
                trk = p.get("track", n)
                if p["type"] == "every":
                    if how and (b - 1) % p["bars"] == p.get("offset", 0):
                        s, q, n_, vv = p["note"]
                        put(trk, b, s, q, n_, vv, p.get("jitter_ms", 0), p.get("gap", 0.04))
                    continue
                if not how:
                    continue
                scale = how if isinstance(how, float) else 1.0
                if how is True or isinstance(how, float):
                    if "loops" in p:
                        src = part_bars(S, p["loops"][sec["loop"]])
                    else:
                        src = part_bars(S, p["part"])
                else:
                    src = part_bars(S, how)
                opts = how if isinstance(how, dict) else {}
                if p.get("repeat", True):
                    line = src[pos % len(src)]
                else:
                    line = src[pos] if pos < len(src) else []
                if opts.get("for") is not None and i >= opts["for"]:
                    line = []
                if opts.get("last") and i == sec["bars"] - 1:
                    line = part_bars(S, opts["last"])[0]
                for e in line:
                    s, q, n_, vv = e[:4]
                    tied = len(e) > 4 and e[4] == "s"
                    vel = vv * scale if scale != 1.0 else vv
                    put(trk, b, s, q + p.get("shift", 0), n_, vel * p["vel"] if "vel" in p else vel,
                        p.get("jitter_ms", 8), p.get("tie_gap", 0.0) if tied else p.get("gap", 0.04))
                    for fn, f in followers.get(n, []):
                        if n_ >= f.get("min_len", 0):
                            put(f.get("track", fn), b, s, q + f.get("shift", 0), n_, vv, f.get("jitter_ms", 0),
                                f.get("gap", 0.04))
            b += 1
    for n, p in players.items():
        if p.get("sort"):
            out[p.get("track", n)].sort()
    return out, chart


def write_parts(S, mid: Path):
    """swap every pitched track of Bountiful's MIDI for the composed ones (the tempo track and the drum grid stay)"""
    parts, _ = compose(S)
    m = mido.MidiFile(str(mid))
    tpb = m.ticks_per_beat
    m.tracks = [t for t in m.tracks if not any(x.type == "note_on" for x in t)
                or any(x.type == "track_name" and x.name == "drums" for x in t)]
    for chan, (name, notes) in enumerate(parts.items()):
        ev = []
        for s, e, p, v in sorted(notes):
            ev += [(int(round(s * tpb)), 1, p, int(round(v * 127))), (int(round(e * tpb)), 0, p, 0)]
        ev.sort(key=lambda x: (x[0], x[1]))
        tr = mido.MidiTrack([mido.MetaMessage("track_name", name=name, time=0)])
        held, last = {}, 0
        for t, on, p, v in ev:
            if on and held.get(p):                                     # a re-hit of a ringing note: end it first
                tr.append(mido.Message("note_off", channel=chan, note=p, velocity=0, time=t - last)); last = t
                held[p] -= 1
            elif not on and not held.get(p):
                continue
            tr.append(mido.Message("note_on" if on else "note_off", channel=chan, note=p, velocity=v if on else 0,
                                   time=t - last))
            last = t
            held[p] = held.get(p, 0) + (1 if on else -1)
        tr.append(mido.MetaMessage("end_of_track", time=0))
        m.tracks.append(tr)
    m.save(str(mid))


# ------------------------------------------------------------------ sounds
def sound_path(sid: str, allow) -> str:
    lib, _, name = sid.partition(":")
    if lib not in LIBRARIES:
        raise SpecError(f"sound {sid!r}: unknown library {lib!r} (known: {', '.join(LIBRARIES)})")
    if lib not in allow:
        raise SpecError(f"sound {sid!r}: library {lib!r} isn't in [sounds] allow")
    if lib == "dm":
        return str(SAMPLES / "drummachines" / f"{name}.wav")
    if lib == "own":
        if name not in OWN:
            raise SpecError(f"sound {sid!r}: no such sound of our own (known: {', '.join(OWN)})")
        return str(OWN[name])
    if lib in ("iowa", "pixel"):
        return str(SAMPLES / lib / f"{name}.wav")
    raise SpecError(f"sound {sid!r} can't be a sample")


def lmms_voice(v: dict, allow) -> tuple:
    lib, _, name = v["sound"].partition(":")
    if lib == "own" and "root" in v:                   # a pitched sample, played by LMMS's AudioFileProcessor
        return ({"sample": sound_path(v["sound"], allow), "root": v["root"], "vol": v.get("vol", 100)},
                f"{v['label']} (LMMS AudioFileProcessor)", copy.deepcopy(v.get("fx", {})))
    if lib != "gs" or lib not in allow:
        raise SpecError(f"voice sound {v['sound']!r}: an instrument is gs:<bank>:<patch> or an own:<sample> with a root")
    bank, patch = (int(x) for x in name.split(":"))
    voice = {"plugin": "sf2player", "attrs": {"src": str(SF2), "bank": bank, "patch": patch, "gain": v.get("gain", 3.0),
                                              "reverbOn": 0, "chorusOn": 0}}
    return voice, f"{v['label']} (GeneralUser GS {bank}:{patch}, LMMS sf2player)", copy.deepcopy(v.get("fx", {}))


def fix_glide(x, path, log):
    """glide = 0 renders NaN in the engine's bass voices: the smallest glide that works is 0.01"""
    if isinstance(x, dict):
        for k, v in x.items():
            if k == "glide" and isinstance(v, (int, float)) and v < 0.01:
                log(f"note: {path}.glide = {v} renders NaN; using 0.01")
                x[k] = 0.01
            else:
                fix_glide(v, f"{path}.{k}", log)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            fix_glide(v, f"{path}[{i}]", log)


# ------------------------------------------------------------------ the LT spec
def to_lt(S, title: str | None = None, log=print) -> dict:
    meta, D, MX = S["meta"], S["drums"], S.get("mix", {})
    allow = S.get("sounds", {}).get("allow", ["gs", "dm", "own"])
    lint(S, log)
    P = S.get("producer", {})
    arr = []
    for sec in sections(S):
        a = {"name": sec["name"], "loop": P.get("loop", "A"), "bars": sec["bars"], "parts": list(P.get("parts", ["comp"])),
             "drums": list(sec.get("drums", []))}
        for k in ("crash", "fill"):
            if k in sec:
                a[k] = sec[k]
        arr.append(a)
    kit = {"map": {str(PR.GM[n]): n for n in D["kit"]},
           "sounds": {n: {"samples": [sound_path(s["sound"], allow)], "stem": s["bus"], "detune_cents": 6,
                          **{k: v for k, v in s.items() if k not in ("sound", "bus")}} for n, s in D["kit"].items()},
           "stems": copy.deepcopy(D["buses"])}
    voices, extra = {}, {}
    for n, v in S.get("voices", {}).items():
        if v["sound"].startswith("engine:"):
            e = copy.deepcopy(v["engine"])
            if e.get("kind") == "pyvoice":
                mod = e.get("preset", {}).get("module")
                if mod not in PYVOICES:
                    raise SpecError(f"voices.{n}: pyvoice module {mod!r} isn't one of {', '.join(PYVOICES)}")
                e["preset"]["module"] = str(PYVOICES[mod])
            fix_glide(e, f"voices.{n}", log)
            extra[n] = e
        else:
            voices[n] = lmms_voice(v, allow)
    over = merge(S.get("overrides", {}), {
        "bpm": meta["bpm"], "swing": meta.get("swing", 0.5), "drums": "grid", "drum_humanize_ms": D.get("humanize_ms", 8),
        "arrangement": arr, "grid": copy.deepcopy(D["grid"]), "master": copy.deepcopy(S.get("master", {}))})
    spec = {
        "title": title or meta["title"], "genre": meta["genre"], "song": ROOT / meta["skeleton"],
        "album": meta.get("album", ""), "track": meta.get("track", 0), "year": meta.get("year", 2026),
        "seed": meta.get("seed", 1), "composer": meta.get("composer", LT.B.COMPOSER_CREDIT),
        "rebuild": f"bountiful/songspec.py {Path(S['_path']).relative_to(ROOT) if S['_path'].startswith(str(ROOT)) else S['_path']}",
        "blurb": meta.get("blurb", ""), "overrides": over, "kit_def": kit, "layers": [],
        "sends": copy.deepcopy(MX.get("sends", {})), "voices": voices, "extra_tracks": extra,
        "level_ref": MX.get("level_ref", "kick"), "targets": dict(MX.get("targets", {})),
        "test_bars": [bar(S, x) for x in MX["test_bars"]],
        "automation": [dict(a, points=[[bar(S, p[0]), *p[1:]] for p in a["points"]]) for a in MX.get("automation", [])],
        "mmp_drums": MX.get("mmp_drums", True), "lead_hi_follows_lead": MX.get("lead_hi_follows_lead", False),
    }
    return spec


# ------------------------------------------------------------------ lint: the gotchas, before a 6-minute render
def lint(S, log=print) -> list[str]:
    """raises SpecError on what would break the render; returns (and logs) warnings"""
    warn = []
    D, MX = S["drums"], S.get("mix", {})
    ch = chords(S)
    for name, loop in S["loops"].items():
        for bar_ in loop:
            for c in bar_:
                if c not in ch:
                    raise SpecError(f"loop {name} uses chord {c!r}, which isn't in [chords]")
    for sec in sections(S):
        if sec["loop"] not in S["loops"]:
            raise SpecError(f"section {sec['name']!r} uses loop {sec['loop']!r}, which isn't in [loops]")
        for layer in sec.get("drums", []):
            if layer not in D["grid"]:
                raise SpecError(f"section {sec['name']!r} uses drum layer {layer!r}, which isn't in [drums.grid]")
    for layer, pats in D["grid"].items():   # an entry without a sound name plays the sound named like its layer
        for pat in (pats.values() if isinstance(pats, dict) else [pats]):
            for e in pat:
                snd = e[2] if len(e) > 2 else layer
                if snd not in D["kit"]:
                    raise SpecError(f"drum layer {layer!r} plays sound {snd!r}, which isn't in [drums.kit]"
                                    + ("" if len(e) > 2 else " (an entry without a sound name uses the layer's name)"))
    for n in D["kit"]:
        if n not in PR.GM:
            raise SpecError(f"drum sound {n!r} has no MIDI note in producer.GM")
    # a track that is silent in the test bars gets no level trim: it would be rendered at whatever level its preset has
    if MX.get("test_bars"):
        a, z = (bar(S, x) for x in MX["test_bars"])
        parts, _ = compose(S)
        for t in MX.get("targets", {}):
            ns = parts.get(t)
            if ns is not None and not any((a - 1) * 4 <= n[0] < z * 4 for n in ns):
                raise SpecError(f"track {t!r} has a level target but doesn't play in the test bars {a}-{z}: "
                                "move test_bars or the part")
    # rootless voicings with nothing under them
    bass = [n for n, p in S.get("players", {}).items() if p.get("track", n) in ("bass", "boom", "808") or p["type"] == "root"]
    for sec in sections(S):
        play = sec.get("play", {})
        if any(play.get(n) for n in bass) or set(sec.get("notes", {})) & {"bass", "sub", "boom", "808"} \
                or not any(play.values()) or sec.get("rootless_ok"):
            continue
        rootless = sorted({c for bar_ in S["loops"][sec["loop"]] for c in bar_ if all(i % 12 for i in ch[c][1])})
        if rootless:
            warn.append(f"section {sec['name']!r}: no bass under rootless voicings ({', '.join(rootless)}); "
                        "set rootless_ok = true if that is the sound")
    for w in warn:
        log(f"warning: {w}")
    return warn


# ------------------------------------------------------------------ build
@contextlib.contextmanager
def composed(S, log=print):
    """while LT.make runs: after Bountiful writes its MIDI, swap in the composed parts and drop its pitched tracks"""
    orig = LT.B.produce

    def produce_then_write(song, g, title, out, seed=1, log=print):
        orig(song, g, title=title, out=out, seed=seed, log=log)
        write_parts(S, out / f"{LT.B.slug(title)}.mid")
        inst = out / "instruments.toml"
        cfg = tomllib.loads(inst.read_text())
        cfg["tracks"] = {k: v for k, v in cfg["tracks"].items() if k == "drums"}
        inst.write_text(LT.to_toml(cfg))
        (out / "notes.txt").write_text(notes_txt(S))

    LT.B.produce = produce_then_write
    try:
        yield
    finally:
        LT.B.produce = orig


def notes_txt(S) -> str:
    meta = S["meta"]
    n = total_bars(S)
    secs = n * 240 / meta["bpm"]
    lines = [f"  {s['name']} ({s['bars']} bars, from bar {start_bar(S, s['name'])}): "
             + " | ".join(" ".join(c) for c in S["loops"][s["loop"]]) for s in sections(S)]
    return (f"{meta['title']} — {meta['genre']}, {meta['bpm']} bpm, {meta.get('key', '')}, {n} bars "
            f"({secs // 60:.0f}:{secs % 60:04.1f})\ncomposition: {Path(S['_path']).name} (Song Spec); drums: Bountiful grid\n\n"
            + "\n".join(lines) + "\n")


def build(S, title=None, log=print) -> Path:
    spec = to_lt(S, title, log)
    for p in [s["samples"][0] for s in spec["kit_def"]["sounds"].values()]:
        if not Path(p).exists():
            raise SpecError(f"missing sample {p}")
    with composed(S, log):
        return LT.make(spec, log=log)


# ------------------------------------------------------------------ checks
def validate(S, title=None, log=print) -> bool:
    import soundfile as sf
    from render_midi import read_midi
    meta, M = S["meta"], S.get("master", {})
    slug = LT.B.slug(title or meta["title"])
    track = LT.B.DATA / "tracks" / slug
    an = json.loads((track / "exports" / "render_info.json").read_text())["analysis"]
    notes, bpm, _ = read_midi(track / f"{slug}.mid")
    bar_s, beat = 4 * 60 / bpm, 60 / bpm
    ch = chords(S)
    _, chart = compose(S)
    drums = [n for n in notes if n["track"] == "drums"]
    res = []
    x = None

    def check(name, ok, detail):
        res.append((name, bool(ok), detail))

    def chord_at(t):
        b, s = int(t / bar_s) + 1, (t % bar_s) / beat * 4
        cur = None
        for cb, cs, cn in chart:
            if (cb, cs) <= (b, s + 0.5):
                cur = cn
        root, iv = ch[cur]
        return {root % 12} | {(root + i) % 12 for i in iv}

    def in_bars(ns, a, b):
        return [n for n in ns if (a - 1) * bar_s - 0.01 <= n["start"] < (b - 1) * bar_s - 0.01]

    def span(sec):
        a = start_bar(S, sec)
        return a, a + next(s["bars"] for s in sections(S) if s["name"] == sec)

    def audio():
        nonlocal x
        if x is None:
            x = sf.read(str(track / "exports" / f"{slug}.wav"), dtype="float32", always_2d=True)
        return x

    def rms(a, b):
        y, sr = audio()
        seg = y[int((a - 1) * bar_s * sr):int((b - 1) * bar_s * sr)].mean(1)
        return 10 * np.log10(np.mean(seg ** 2) + 1e-12)

    def band(a, b, lo, hi):
        y, sr = audio()
        seg = y[int((a - 1) * bar_s * sr):int((b - 1) * bar_s * sr)].mean(1)
        spec = np.abs(np.fft.rfft(seg)) ** 2
        f = np.fft.rfftfreq(len(seg), 1 / sr)
        return 10 * np.log10(spec[(f >= lo) & (f < hi)].sum() + 1e-12)

    lo, hi = S.get("validate", {}).get("length_s", [120, 300])
    check(f"length {lo // 60}:{lo % 60:02d}-{hi // 60}:{hi % 60:02d}", lo <= an["duration_s"] <= hi, f"{an['duration_s']:.1f} s")
    lufs, tol = M.get("target_lufs", -14.0), S.get("validate", {}).get("lufs_tolerance", 0.5)
    check(f"loudness {lufs:g} LUFS (+-{tol:g})", abs(an["integrated_lufs"] - lufs) <= tol, f"{an['integrated_lufs']} LUFS")
    check("true peak <= -1 dBTP", an["true_peak_dbtp_approx"] <= M.get("true_peak", -1.0) + 0.05, f"{an['true_peak_dbtp_approx']} dBTP")
    check("no clipping", an["clipped_samples"] == 0, f"{an['clipped_samples']} samples")
    check("low end mono (corr <120 Hz > 0.95)", an["correlation_below_120hz"] > 0.95, f"{an['correlation_below_120hz']}")
    have = {n["track"] for n in notes}
    want = set(meta.get("tracks") or compose(S)[0]) | {"drums"}
    check("composed parts in the MIDI", want <= have, ", ".join(sorted(have)))

    for c in S.get("checks", []):
        t = c["type"]
        if t == "no_drums":                    # no drum hits in a section (except the named sounds)
            a, z = span(c["in"])
            skip = {PR.GM[s] for s in c.get("except", [])}
            hits = [n for n in in_bars(drums, a, z) if n["pitch"] not in skip]
            check(c.get("name", f"{c['in']}: no drums"), not hits, f"{len(hits)} drum hits in bars {a}-{z - 1}")
        elif t == "absent":                    # a track stays out of the named sections
            ns = [n for n in notes if n["track"] == c["track"]]
            k = sum(len(in_bars(ns, *span(s))) for s in c["in"])
            check(c.get("name", f"no {c['track']} in {', '.join(c['in'])}"), k == 0, f"{k} {c['track']} notes")
        elif t == "in_harmony":                # pitches on the chord or the scale
            scale = {pitch_class(p) for p in meta.get("scale", [])}
            ns = [n for n in notes if n["track"] in c["tracks"]]
            bad = [n for n in ns if n["pitch"] % 12 not in chord_at(n["start"]) | scale]
            check(c.get("name", f"{' and '.join(c['tracks'])} in key"), len(bad) <= c.get("max_outside", 0),
                  f"{len(bad)}/{len(ns)} outside")
        elif t == "on_chord":                  # notes on the strong beats are chord tones
            every = c.get("every_beats", 4)
            ns = [n for n in notes if n["track"] == c["track"]]
            strong = [n for n in ns if ((n["start"] % bar_s) / beat) % every < c.get("window_beats", 0.1)]
            off = [n for n in strong if n["pitch"] % 12 not in chord_at(n["start"] + 0.01)]
            check(c.get("name", f"{c['track']} on the strong beats is in the chord"), not off, f"{len(off)}/{len(strong)} off")
        elif t == "late":                      # a drum sound sits behind the grid by a median within ms
            hits = [n for n in drums if n["pitch"] == PR.GM[c["sound"]]]
            late = [(n["start"] % (beat / 4)) * 1000 for n in hits]
            a, z = c["ms"]
            med = float(np.median(late)) if late else float("nan")
            check(c.get("name", f"{c['sound']} sits behind the beat ({a}-{z} ms)"), late and a <= med <= z, f"median {med:.0f} ms")
        elif t == "stops":                     # the beat stops after a beat in the last bar of a section
            bad = []
            for sec in c["in"]:
                p = span(sec)[1] - 1
                bad += [n for n in in_bars(drums, p, p + 1) if n["pitch"] not in {PR.GM[s] for s in c.get("except", [])}
                        and c["after_beat"] * beat + 0.02 < n["start"] - (p - 1) * bar_s < bar_s - 0.03]   # not the next downbeat, humanized early
            check(c.get("name", f"the beat stops after beat {c['after_beat']}"), not bad, f"{len(bad)} hits after it")
        elif t == "louder":                    # section a is at least db louder than section b (RMS)
            d = rms(*span(c["a"])) - rms(*span(c["b"]))
            check(c.get("name", f"{c['a']} >= {c['db']} dB over {c['b']}"), d >= c["db"], f"{d:.1f} dB")
        elif t == "bands":                     # in one section, band a is at least db over band b
            a, z = span(c["in"])
            d = band(a, z, *c["a"]) - band(a, z, *c["b"])
            check(c.get("name", f"{c['in']}: {c['a']} Hz >= {c['db']} dB over {c['b']} Hz"), d >= c["db"], f"{d:+.1f} dB")
        elif t == "band_drop":                 # a band is at least db quieter per bar in section b than in a
            (a0, a1), (b0, b1) = span(c["a"]), span(c["b"])
            if "bars" in c:                    # only the first n bars of each, e.g. to leave out a pocket bar
                a1, b1 = a0 + c["bars"][0], b0 + c["bars"][1]
            lo_, hi_ = c["band"]
            d = (band(a0, a1, lo_, hi_) - 10 * np.log10(a1 - a0)) - (band(b0, b1, lo_, hi_) - 10 * np.log10(b1 - b0))
            check(c.get("name", f"{c['b']} {lo_}-{hi_} Hz >= {c['db']} dB under {c['a']}"), d >= c["db"], f"{d:.1f} dB")
        elif t == "count":
            k = sum(n["track"] == c["track"] for n in notes)
            check(c.get("name", f"{c['track']} present"), k >= c["min"], f"{k} {c['track']} notes")
        else:
            raise SpecError(f"unknown check type {t!r}")
    n_ok = sum(ok for _, ok, _ in res)
    lines = [f"- {'PASS' if ok else 'FAIL'} {name}: {d}" for name, ok, d in res]
    log("\n".join(lines))
    log(f"{n_ok}/{len(res)} checks pass")
    (track / "validation.md").write_text(f"# {title or meta['title']}: validation\n\n" + "\n".join(lines)
                                         + f"\n\n{n_ok}/{len(res)} checks pass\n")
    return n_ok == len(res)


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    title = None
    if "--as" in argv:
        title = argv[argv.index("--as") + 1]
        args.remove(title)
    if not args:
        print(__doc__)
        return 2
    S = load(args[0])
    log = lambda m: print(m, flush=True)  # noqa: E731
    try:
        if S.get("perform", {}).get("engine") == "beats":          # written in beats: songspec_beats.py
            import songspec_beats as SB
            title = title or S["meta"]["title"]
            if "--dry" in argv:
                SB.backend(S)
                G = SB.compose(S)
                log(f"{title}: {len(G.form)} bars, " + ", ".join(f"{k} {len(v)}" for k, v in G.notes.items()))
                return 0
            if "--validate" in argv:
                raise SpecError(f"the {S['render']['backend']} backend checks the render as it builds; build it again")
            return SB.build(S, LT.B.DATA / "tracks" / LT.B.slug(title), title, log)
        if "--dry" in argv:
            parts, _ = compose(S)
            to_lt(S, title, log)
            log(f"{S['meta']['title']}: {total_bars(S)} bars, " + ", ".join(f"{k} {len(v)}" for k, v in parts.items()))
            return 0
        if "--validate" not in argv:
            build(S, title, log)
        return 0 if validate(S, title, log) else 1
    except SpecError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
