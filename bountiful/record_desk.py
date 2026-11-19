"""The Record tab's desk: what the app shows and changes in a Song Spec record, without a window (so it can be tested).

    records()               the records in records/, one summary each
    bar_map(S)              bar by bar: the section, its chords and what plays (the drum pattern each layer uses)
    set_meta(path, {...})   change title, key, bpm, swing or seed in the file, keeping its comments and layout
    new_take(path, title)   a new record that extends this one with another seed: the same song, played again
    command(path, mode)     the songspec.py command line that checks, test-builds or builds a record
"""
from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import songspec as SS  # noqa: E402
from songspec_beats import SpecError, entry  # noqa: E402

RECORDS = SS.RECORDS
SONGSPEC = HERE / "songspec.py"

# the [meta] fields the tab edits: (type, low, high); the rest stays in the file for the people who write TOML
FIELDS = {"title": (str, 1, 80), "key": (str, 0, 40), "bpm": (float, 40, 240), "swing": (float, 0.5, 0.75),
          "seed": (int, 0, 2 ** 31 - 1)}


def engine(S) -> str:
    return S.get("perform", {}).get("engine", "lmms")


def records() -> list[dict]:
    """every records/*.toml, title first; a file that doesn't load comes back with its error"""
    out = []
    for p in sorted(RECORDS.glob("*.toml")):
        try:
            S = SS.load(p)
            out.append(dict(summary(S), path=p, error=None))
        except (tomllib.TOMLDecodeError, SpecError, KeyError, OSError) as e:
            out.append({"path": p, "title": p.stem, "error": f"{type(e).__name__}: {e}"})
    return out


def summary(S) -> dict:
    meta = S["meta"]
    bars = bar_map(S)
    beats = sum(b["beats"] for b in bars)
    return {"title": meta["title"], "genre": meta.get("genre", ""), "key": meta.get("key", ""), "bpm": meta["bpm"],
            "swing": meta.get("swing", 0.5), "seed": meta.get("seed", 1), "engine": engine(S),
            "backend": S.get("render", {}).get("backend", "lmms"), "bars": len(bars), "seconds": beats * 60 / meta["bpm"],
            "extends": _extends(S), "sections": [(s["name"], s["bars"], s.get("loop", "")) for s in SS.sections(S)]}


def _extends(S) -> str | None:
    return tomllib.loads(Path(S["_path"]).read_text()).get("meta", {}).get("extends")


def bar_map(S) -> list[dict]:
    """one entry per bar: n (from 1), section, beats, chords, plays ([name or name:pattern])"""
    out, b = [], 0
    loops = S["loops"]
    beats_engine = engine(S) == "beats"
    from_song = S.get("perform", {}).get("loop_from", "section") == "song"
    grid = S.get("drums", {}).get("grid", {})
    per_block = S.get("overrides", {}).get("drum_cycle_per_block", False)
    for sec in SS.sections(S):
        loop = loops.get(sec.get("loop"))
        if loop is None:
            raise SpecError(f"section {sec['name']!r} uses loop {sec.get('loop')!r}, which isn't in [loops]")
        for i in range(sec["bars"]):
            names = loop[(b if from_song else i) % len(loop)]
            names = [names] if isinstance(names, str) else list(names)
            if beats_engine:
                plays = []
                for n, cfg in S.get("players", {}).items():
                    e = entry(cfg, sec["name"], i)
                    if e is not None:
                        plays.append(_how(n, e, i))
            else:
                plays = [n for n, v in sec.get("play", {}).items() if v]
                for layer in sec.get("drums", []):         # build.py: a dict grid cycles by the song's bar (0-based)
                    pats = grid.get(layer)
                    if isinstance(pats, dict):
                        keys = sorted(pats)
                        plays.append(f"{layer}:{keys[(i if per_block else b) % len(keys)]}")
                    else:
                        plays.append(layer)
            out.append({"n": b + 1, "section": sec["name"], "bar_in_section": i, "beats": sec.get("beats", 4),
                        "chords": names, "plays": plays})
            b += 1
    return out


def _how(name: str, e: dict, i: int) -> str:
    """a beats player's bar: its pattern list (cycling like jazz_piano's), else its first word (style = "boom"), else
    its first switch (flakes = true)"""
    if isinstance(e.get("bars"), list):
        return f"{name}:{e['bars'][i % len(e['bars'])]}"
    word = next((v for v in e.values() if isinstance(v, str)), None)
    if word is None:
        word = next((k for k, v in e.items() if v is True), None)
    return f"{name}:{word}" if word else name


# ------------------------------------------------------------------ editing [meta] in place
def _value(key: str, v):
    """the checked value, or SpecError"""
    kind, lo, hi = FIELDS[key]
    if kind is str:
        v = str(v).strip()
        if not lo <= len(v) <= hi or any(c in v for c in "\r\n"):
            raise SpecError(f"{key}: {lo}-{hi} characters on one line")
        return v
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise SpecError(f"{key}: {v!r} isn't a number") from None
    if not lo <= x <= hi:
        raise SpecError(f"{key}: {x:g} is outside {lo:g}-{hi:g}")
    if kind is int or (key == "bpm" and x.is_integer()):
        if not x.is_integer():
            raise SpecError(f"{key}: a whole number")
        return int(x)
    return x


def _toml(v) -> str:
    return json.dumps(v, ensure_ascii=False) if isinstance(v, str) else repr(v)


def set_meta(path, changes: dict) -> dict:
    """write the changed [meta] fields into the file, line by line (comments and order stay); returns what changed"""
    path = Path(path)
    vals = {k: _value(k, v) for k, v in changes.items() if k in FIELDS}
    if unknown := set(changes) - set(FIELDS):
        raise SpecError(f"the tab doesn't edit {', '.join(sorted(unknown))}")
    lines = path.read_text().splitlines(keepends=True)
    head = next((i for i, l in enumerate(lines) if l.strip() == "[meta]"), None)
    if head is None:
        raise SpecError(f"{path.name} has no [meta] table")
    last, quoted, done = head, False, set()      # last: the line that ends the table's last value
    for i in range(head + 1, len(lines)):
        l = lines[i]
        if not quoted:
            if l.lstrip().startswith("["):
                break
            m = re.match(r'(\s*)([A-Za-z_]+)(\s*=\s*)("[^"\\]*(?:\\.[^"\\]*)*"|[-+0-9.eE_]+)(.*)$', l.rstrip("\n"))
            if m and m.group(2) in vals and m.group(2) not in done:
                lines[i] = f"{m.group(1)}{m.group(2)}{m.group(3)}{_toml(vals[m.group(2)])}{m.group(5)}\n"
                done.add(m.group(2))
            if re.match(r"\s*[A-Za-z_]+\s*=", l):
                last = i
        if l.count('"""') % 2:
            quoted = not quoted
            if not quoted:
                last = i
    lines[last + 1:last + 1] = [f"{k} = {_toml(v)}\n" for k, v in vals.items() if k not in done]
    text = "".join(lines)
    meta = tomllib.loads(text)["meta"]
    if any(meta.get(k) != v for k, v in vals.items()):
        raise SpecError("the edit didn't read back as written; the file is unchanged")
    tmp = path.with_suffix(".toml.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
    return vals


def new_take(path, title: str, seed: int | None = None) -> Path:
    """records/<slug>.toml: extends the record, with its own title and seed (both random streams move with it)"""
    path = Path(path)
    title = _value("title", title)
    if path.suffix != ".toml" or path.resolve().parent != RECORDS.resolve():
        raise SpecError("a new take extends a record in records/")
    src = SS.load(path)
    seed = _value("seed", seed if seed is not None else src["meta"].get("seed", 1) + 1)
    out = RECORDS / f"{SS.LT.B.slug(title)}.toml"
    if out.exists():
        raise SpecError(f"{out.name} already exists: pick another title")
    seeds = f"seed = {seed}\n" + (f"humanize_seed = {seed}\n" if "humanize_seed" in src["meta"] else "")
    out.write_text(f"# {title}: a new take on {src['meta']['title']} (records/{path.name}). Everything comes from there\n"
                   f"# except what is below; add any table of that file here to change it for this take.\n\n"
                   f"[meta]\nextends = {_toml(path.stem)}\ntitle = {_toml(title)}\n{seeds}")
    SS.load(out)
    return out


# ------------------------------------------------------------------ running songspec.py
MODES = {"check": ["--dry"], "test": ["--as", None], "build": []}


def command(path, mode: str, title: str | None = None) -> list[str]:
    """check = compose and lint, no render; test = build as "<title> spec test" (its own folder); build = the record"""
    if mode not in MODES:
        raise SpecError(f"unknown mode {mode!r}")
    args = [sys.executable, "-I", str(SONGSPEC), str(path)]
    if mode == "test":
        return args + ["--as", f"{title or SS.load(path)['meta']['title']} spec test"]
    return args + MODES[mode]


def track_dir(S, mode: str) -> Path:
    title = S["meta"]["title"] + (" spec test" if mode == "test" else "")
    return SS.LT.B.DATA / "tracks" / SS.LT.B.slug(title)


def final_wav(folder: Path) -> Path | None:
    """the mastered WAV in a track's exports (LMMS names it <slug>.wav, the beats backend "<Title> - <artist>.wav")"""
    wavs = sorted(p for p in (Path(folder) / "exports").glob("*.wav") if "premaster" not in p.stem)
    return next((p for p in wavs if p.stem == Path(folder).name), wavs[0] if wavs else None)


# ------------------------------------------------------------------ sounds: only the cleared libraries (docs/sample-audit.md)
# what each kind of slot can hold: a drum kit entry is a sample, a voice an instrument (or one of our samples with a root)
SLOT_LIBS = {"sample": ("dm", "pixel", "iowa", "own"), "voice": ("gs",)}


def sf2_presets(path=SS.SF2) -> list[tuple[int, int, str]]:
    """(bank, patch, name) of every preset in a SoundFont, read from its phdr chunk"""
    import struct
    b = Path(path).read_bytes()
    i = b.find(b"phdr")
    if b[:4] != b"RIFF" or i < 0:
        raise SpecError(f"{Path(path).name} isn't a SoundFont")
    n = struct.unpack_from("<I", b, i + 4)[0] // 38
    out = []
    for k in range(n - 1):                                        # the last record is the end marker (EOP)
        name, patch, bank = struct.unpack_from("<20sHH", b, i + 8 + 38 * k)
        out.append((bank, patch, name.split(b"\0")[0].decode("latin-1").strip()))
    return sorted(out)


def catalog(lib: str) -> list[tuple[str, str]]:
    """(sound id, label) for every cleared sound in a library"""
    if lib == "gs":
        return [(f"gs:{b}:{p}", n) for b, p, n in sf2_presets()]
    if lib == "own":
        return [(f"own:{k}", v.name) for k, v in SS.OWN.items()]
    root = {"dm": SS.SAMPLES / "drummachines", "iowa": SS.SAMPLES / "iowa", "pixel": SS.SAMPLES / "pixel"}.get(lib)
    if root is None:
        raise SpecError(f"unknown library {lib!r}")
    wavs = (p for p in root.rglob("*.wav") if not (lib == "iowa" and p.relative_to(root).parts[0] == "raw"))
    return [(f"{lib}:{p.relative_to(root).with_suffix('').as_posix()}", p.relative_to(root).as_posix())
            for p in sorted(wavs)]


def slots(S) -> list[dict]:
    """the record's sounds that come from a library: the drum kit's samples and the instrument voices"""
    out = []
    for name, v in S.get("drums", {}).get("kit", {}).items():
        if isinstance(v, dict) and ":" in v.get("sound", ""):
            out.append({"table": "drums.kit", "name": name, "sound": v["sound"], "kind": "sample", "label": v.get("bus", "")})
    for name, v in S.get("voices", {}).items():
        lib = v.get("sound", "").partition(":")[0]
        if lib == "gs":
            out.append({"table": "voices", "name": name, "sound": v["sound"], "kind": "voice", "label": v.get("label", "")})
    return out


def allowed(S, kind: str) -> list[str]:
    allow = S.get("sounds", {}).get("allow", ["gs", "dm", "own"])
    return [lib for lib in SLOT_LIBS[kind] if lib in allow and lib in SS.LIBRARIES]


def set_sound(path, table: str, name: str, sid: str, label: str | None = None) -> str:
    """put a cleared sound into a kit entry or a voice, in the file (a take gets its own copy of just that line)"""
    path = Path(path)
    S = SS.load(path)
    slot = next((s for s in slots(S) if (s["table"], s["name"]) == (table, name)), None)
    if slot is None:
        raise SpecError(f"{table}.{name} isn't a sound the tab can change")
    lib = sid.partition(":")[0]
    if lib not in allowed(S, slot["kind"]) or sid not in dict(catalog(lib)):
        raise SpecError(f"{sid!r} isn't a cleared {slot['kind']} this record allows")
    lines = path.read_text().splitlines(keepends=True)
    head = f"[{table}]" if table == "drums.kit" else f"[voices.{name}]"
    h = next((i for i, l in enumerate(lines) if l.split("#")[0].strip() == head), None)
    end = next((i for i in range(h + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines)) if h is not None else None
    sound_re = re.compile(r'(sound\s*=\s*)"[^"]*"')
    if table == "drums.kit":
        row = next((i for i in range(h + 1, end) if re.match(rf"\s*{re.escape(name)}\s*=", lines[i])), None) if h is not None else None
        if row is not None and sound_re.search(lines[row]):
            lines[row] = sound_re.sub(lambda m: m.group(1) + _toml(sid), lines[row], count=1)
        elif h is not None:
            lines[h + 1:h + 1] = [f"{name} = {{ sound = {_toml(sid)} }}\n"]   # tables merge, so the rest comes from the parent
        else:
            lines += [f"\n[drums.kit]\n{name} = {{ sound = {_toml(sid)} }}\n"]
    else:
        new = {"sound": sid} | ({"label": label} if label else {})
        if h is None:
            lines += [f"\n{head}\n"] + [f"{k} = {_toml(v)}\n" for k, v in new.items()]
        else:
            for k, v in new.items():
                row = next((i for i in range(h + 1, end) if re.match(rf"\s*{k}\s*=", lines[i])), None)
                if row is None:
                    lines[h + 1:h + 1] = [f"{k} = {_toml(v)}\n"]
                    end += 1
                else:
                    lines[row] = re.sub(rf'({k}\s*=\s*)"[^"]*"', lambda m: m.group(1) + _toml(v), lines[row], count=1)
    text = "".join(lines)
    tmp = path.with_suffix(".toml.tmp")
    tmp.write_text(text)
    try:
        got = next(s for s in slots(SS.load(tmp)) if (s["table"], s["name"]) == (table, name))
        if got["sound"] != sid:
            raise SpecError("the edit didn't read back as written; the file is unchanged")
    except (tomllib.TOMLDecodeError, StopIteration) as e:
        tmp.unlink()
        raise SpecError(f"the edit didn't read back ({e}); the file is unchanged") from None
    except SpecError:
        tmp.unlink()
        raise
    os.replace(tmp, path)
    return sid


def audition(sid: str, folder) -> Path:
    """a WAV to hear a sound by: the sample itself, or an instrument playing a few notes (fluidsynth)"""
    lib, _, name = sid.partition(":")
    if lib != "gs":
        return Path(SS.sound_path(sid, [lib]))
    import mido
    import subprocess
    bank, patch = (int(x) for x in name.split(":"))
    ch = 9 if bank == 128 else 0
    mid = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    mid.tracks.append(t)
    if ch == 0:
        t.append(mido.Message("control_change", channel=ch, control=0, value=bank))
    t.append(mido.Message("program_change", channel=ch, program=patch))
    notes = [36, 38, 42, 46, 49] if ch == 9 else [60, 64, 67, 72]
    for p in notes:
        t.append(mido.Message("note_on", channel=ch, note=p, velocity=96))
        t.append(mido.Message("note_off", channel=ch, note=p, time=360))
    for p in notes[:3]:
        t.append(mido.Message("note_on", channel=ch, note=p, velocity=80))
    t.append(mido.Message("note_off", channel=ch, note=notes[0], time=960))
    for p in notes[1:3]:
        t.append(mido.Message("note_off", channel=ch, note=p))
    folder = Path(folder)
    out = folder / f"{sid.replace(':', '_')}.wav"
    mid.save(folder / "audition.mid")
    subprocess.run(["fluidsynth", "-ni", "-q", "-a", "null", "-r", "44100", "-g", "0.6", "-F", str(out), str(SS.SF2),
                    str(folder / "audition.mid")], check=True, capture_output=True, timeout=60)
    return out
