#!/usr/bin/env python3
"""Bountiful Music: compose, choose, produce and render songs in a genre.

    PY=~/Documents/Projects/intelligent-jungle/.venv/bin/python
    $PY bountiful/build.py genres                                   # list the genre presets
    $PY bountiful/build.py compose --genre soviet-synthpop-86 --count 12          -> songs/<genre>/, ranked
    $PY bountiful/build.py produce --genre soviet-synthpop-86 --song songs/.../song-123.am.json --title "Name"
    $PY bountiful/build.py render tracks/<name> [--bars 33-40]
    $PY bountiful/build.py reroll --song songs/.../song-123.am.json --what melody      # same song, new melody
    $PY bountiful/build.py produce ... --bounty 1969 [--electronium-drums] [--patch electronium.toml]   # the Electronium (electronium.py)

A produced track folder holds <name>.mid (lead, lead_hi, sidekick, arp, comp, pad, bass, drums, with performed
timing), notes.txt (loops, chords, arrangement, tells), instruments.toml (opens in MIDI Studio), exports/.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import mido
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
import producer as PR  # noqa: E402
import skeleton as SK  # noqa: E402

import paths  # noqa: E402
from paths import DATA, ENGINE  # noqa: E402  (paths.py: the music lives in DATA, the renderer in ENGINE)
PY = str(paths.PY)
RENDER = ENGINE / "studio" / "render_midi.py"
from credits import ARTIST, COMPOSER as COMPOSER_CREDIT, PRODUCED_COMPOSER as COMPOSER, stamp  # noqa: E402,F401  (credits.py)
PART_ORDER = ["lead", "lead_hi", "sidekick", "arp", "comp", "stab", "vox", "pad", "bass", "bass2"]
EXTRA_CH = (12, 13, 14, 15, 7)
CHANNEL = {"lead": (0, 81), "lead_hi": (1, 81), "sidekick": (6, 80), "arp": (2, 87), "comp": (3, 4), "pad": (4, 89), "bass": (5, 38), "vox": (8, 54), "stab": (10, 16), "bass2": (11, 38), "drums": (9, 0)}
# a kit of more than 108 sounds (notes 20-127) goes on past 127: drum note n > 127 is written as note n - 128 on this
# channel of the drums track, and a kit map keys those sounds "15:<note>" (render_midi looks that key up first)
DRUM_HI_CH = 15
SENDS = {"room": {"type": "reverb", "seconds": 0.8, "predelay": 0.01, "size": 0.5, "damp": 0.6},
         "plate": {"type": "reverb", "seconds": 2.4, "predelay": 0.025, "damp": 0.5},
         "echo": {"type": "delay", "time_beats": 0.75, "feedback": 0.36, "tone": 2800},
         "gated": {"type": "reverb", "seconds": 0.45, "predelay": 0.004, "size": 1.0, "damp": 0.3},
         "spring": {"type": "spring", "seconds": 2.0, "period": 0.031, "chirp": 1.0}}
MASTER = {"tape": {"drive": 1.3, "bias": 0.04, "bump_db": 0.5, "hf_db": -0.5, "lp_hz": 19000, "hiss_db": -80, "wow_ms": 0.03},
          "glue": {"threshold": -14.0, "ratio": 2.0, "attack": 0.02, "release": 0.25}, "target_lufs": -11.0, "ceiling": -1.0}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "track"


# ------------------------------------------------------------------ genres

def genres() -> dict[str, dict]:
    kits = tomllib.loads((ROOT / "genres" / "kits.toml").read_text())
    import electronium_drums
    kits["electronium"] = electronium_drums.kit()          # the Electronium's own synthesised percussion
    from synthesis.engines import breakforge
    kits["breakforge"] = breakforge.kit()                  # Breakforge's procedural drums, one stem per drum
    out = {}
    for f in sorted((ROOT / "genres").glob("*.toml")):
        if f.stem == "kits":
            continue
        g = tomllib.loads(f.read_text())
        g["id"] = f.stem
        g["_kit"] = breakforge.kit(g.get("breakforge")) if g["kit"] == "breakforge" else kits[g["kit"]]
        out[f.stem] = g
    return out


# ------------------------------------------------------------------ compose and rank

def compose(genre: dict, count: int = 0, seeds: list[int] | None = None, out: Path | None = None,
            pin: Path | None = None, reroll: list[str] | None = None, log=print) -> list[Path]:
    out = out or DATA / "songs" / genre["id"]
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(genre.get("composer", {}), f)
        settings = f.name
    cmd = ["node", str(HERE / "gen.js"), "--settings", settings, "--out", str(out), "--prefix", genre["id"]]
    cmd += sum([["--seed", str(s)] for s in seeds or []], [])
    if count:
        cmd += ["--count", str(count)]
    if pin:
        cmd += ["--pin", str(pin), "--reroll", ",".join(reroll or ["melody"]), "--prefix", Path(pin).name.replace(".am.json", "") + "-" + "+".join(reroll or ["melody"])]
    files = []
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    for line in p.stdout:
        d = json.loads(line)
        files.append(Path(d["file"]))
        log(f"composed {Path(d['file']).name}: {d['sections']} sections, {d['beats']:.0f} beats")
    p.wait()
    Path(settings).unlink(missing_ok=True)
    return files


def stretched(sk: SK.Skeleton, k: int) -> SK.Skeleton:
    """Play the composition k times slower against the drums (jungle: half-time harmony over breaks)."""
    if k == 1:
        return sk
    s = copy.copy(sk)
    s.melody = [SK.Note(n.t * k, n.d * k, n.p, n.v) for n in sk.melody]
    s.bass = [SK.Note(n.t * k, n.d * k, n.p, n.v) for n in sk.bass]
    halves = []
    for h1, h2 in sk.halves:
        halves += [(h1, h1), (h2, h2)] if k == 2 else [(h1, h2)] * k
    s.halves = halves
    s.chords = [h[0] for h in halves]
    s.bars = sk.bars * k
    s.loops = {n: dict(L, start_bar=L["start_bar"] * k, bars=min(16, L["bars"] * k)) for n, L in sk.loops.items()}
    return s


def produce_loops(sk: SK.Skeleton, g: dict, rng) -> dict:
    bpm = g["bpm"]
    def cfg(name, **extra):
        c = dict(g.get(name, {}))
        c.setdefault("swing", g.get("swing", 0.5))
        c["_bpm"] = bpm
        c.update(extra)
        return c
    loops = {}
    for name, L in sk.loops.items():
        ch = PR.harmony(sk, L["start_bar"], L["bars"], g.get("harmony", {}))
        mcfg = cfg("melody")
        lead_vars = None
        if mcfg.get("writer") == "motif":       # the melody writer (melodist.py): motif, phrase plan, variants for repeats
            import melodist as MW
            lead_vars = MW.loop_melodies(sk, L["start_bar"], L["bars"], ch, mcfg, rng)
            lead = lead_vars["base"]
        else:
            lead = PR.melody(sk, L["start_bar"], L["bars"], ch, mcfg, rng)
        parts = {"lead": lead, "bass": PR.bass(sk, L["start_bar"], L["bars"], ch, cfg("bass"), rng)}
        parts["lead_hi"] = [(t, d, p + 12, v * 0.55, o) for (t, d, p, v, o) in parts["lead"]]
        if "bass2" in g:                       # a second bass line (e.g. long notes for transitions)
            parts["bass2"] = PR.bass(sk, L["start_bar"], L["bars"], ch, cfg("bass2"), rng)
        if "pad" in g:
            pc = g["pad"]
            parts["pad"] = PR.pad(ch, PR.voicings(ch, pc["low"], pc["high"], pc["top"], pc["notes"]), cfg("pad"), rng)
        voic = {}
        for cp in ("comp", "vox", "stab"):  # rhythmic chord parts (vox: vocal or brass stabs; stab: organ stabs)
            if cp in g:
                cc = g[cp]
                voic[cp] = PR.voicings(ch, cc["low"], cc["high"], cc["top"], cc["notes"])
                parts[cp] = PR.comp(ch, voic[cp], cfg(cp), rng)
        if "arp" in g:
            parts["arp"] = PR.arp(ch, None, cfg("arp"), rng)
        loops[name] = {"bars": L["bars"], "chords": ch, "parts": parts, "src": L, "voic": voic, "lead_vars": lead_vars}
    return loops


def chord_names(chords) -> str:
    names = SK._spell["names"]
    return " ".join(f"{names[c.root]}{c.quality}" + (f"({c.beats / 4:g})" if c.beats != 4 else "") for c in chords)


def rank(files: list[Path], g: dict, log=print) -> list[dict]:
    """Score skeletons for the genre: a chorus with 3-4 chords and a singable melody, distinct verse and
    bridge, the genre's preferred mode, a chorus that comes back."""
    rows = []
    comp_ = g.get("composer", {})
    want_minor = comp_.get("minorScaleLikelihood", 1) > comp_.get("majorScaleLikelihood", 1)
    for f in files:
        try:
            sk = SK.load(f)
        except Exception as ex:
            log(f"  skip {f.name}: {ex}")
            continue
        s2 = stretched(sk, g.get("stretch", 1))
        rng = np.random.default_rng(1)
        loops = produce_loops(s2, g, rng)
        A = loops["A"]
        roots = len({c.root for c in A["chords"]})
        lead = A["parts"]["lead"]
        npb = len(lead) / A["bars"]
        iv = np.abs(np.diff([x[2] for x in lead])) if len(lead) > 1 else np.array([0])
        score = 0.0
        score += 1.2 - 0.35 * abs(roots - 3.5)
        score += 1.0 - min(1.0, abs(npb - 3.5) / 3)
        score += 0.6 * (1 - float(np.mean(iv > 7)))
        score += 0.5 if (sk.mode == "minor") == want_minor else 0
        score += 0.4 if loops["V"]["src"]["start_bar"] != loops["A"]["src"]["start_bar"] else 0
        score += 0.3 if loops["B"]["src"]["start_bar"] not in (loops["A"]["src"]["start_bar"], loops["V"]["src"]["start_bar"]) else 0
        reps = sum(1 for s in sk.sections if s.signature == next((x.signature for x in sk.sections if x.start_bar == sk.loops["A"]["start_bar"]), None))
        score += min(0.6, 0.2 * reps)
        rows.append({"file": str(f), "seed": sk.seed, "key": sk.key, "bars": sk.bars, "score": round(score, 2),
                     "chorus": chord_names(A["chords"]), "verse": chord_names(loops["V"]["chords"]), "bridge": chord_names(loops["B"]["chords"]),
                     "melody_notes_per_bar": round(npb, 1)})
    rows.sort(key=lambda r: -r["score"])
    return rows


# ------------------------------------------------------------------ produce

def arrange(loops: dict, g: dict, rng, machine=None, timeline: list | None = None, seed: int = 0) -> tuple[dict, list, list]:
    """machine: an electronium.Machine for drums = "electronium"; timeline: filled with one dict per bar (for the Electronium's lead)."""
    parts = {k: [] for k in PART_ORDER}
    drums, bar_map, bar = [], [], 0
    dcfg = {"swing": g.get("swing", 0.5), "_bpm": g["bpm"], "drum_humanize_ms": g.get("drum_humanize_ms", 0), "grid": g.get("grid", {}),
            "electronium": machine, "seed": seed, "breakforge": g.get("breakforge", {})}
    prev_loop, carried = None, 0
    passes, cur_var = {}, {}                   # melody-writer variants: each pass through a loop gets the next one
    for blk in g["arrangement"]:
        L = loops[blk["loop"]]
        n = blk["bars"]
        # loop_continuous: the loop position carries on across consecutive blocks on the same loop (a 7-bar groove and its
        # 1-bar fill play loop bars 1-8), resetting when the loop changes or on a block with loop_restart
        off = carried if g.get("loop_continuous") and blk["loop"] == prev_loop and not blk.get("loop_restart") else 0
        tr = blk.get("transpose", 0)
        for i in range(n):
            b = bar + i
            lb = (off + i) % L["bars"]
            if timeline is not None:
                timeline.append({"bar": b, "tr": tr, "act": blk.get("activity", 1.0), "kime": bool(blk.get("kime")),
                                 "loop": blk["loop"], "parts": list(blk.get("parts", [])), "restart": i == 0 and bool(blk.get("loop_restart")),
                                 "lead": "lead" in blk.get("parts", []) and not blk.get("kime"), "sidekick_part": "sidekick" in blk.get("parts", []),
                                 "chords": [(max(0.0, c.start - lb * 4), min(c.start + c.beats, lb * 4 + 4) - max(c.start, lb * 4), c.pcs(), c.root)
                                            for c in L["chords"] if c.start < lb * 4 + 4 and c.start + c.beats > lb * 4]})
            if blk.get("kime"):                 # the whole band plays the same accents on the bar's chord
                ci = next((k for k, c in enumerate(L["chords"]) if c.start <= lb * 4 < c.start + c.beats), 0)
                c = L["chords"][ci]
                for s_ in blk["kime"]:
                    t = b * 4 + s_ / 4
                    if "bass" in blk.get("parts", []):
                        parts["bass"].append((t, 0.22, PR.degree(c, "R", g.get("bass", {}).get("register", [33, 52])[0]) + tr, 0.95, 0.0))
                    for cp in ("comp", "vox"):
                        if cp in blk.get("parts", []) and cp in L["voic"]:
                            parts[cp] += [(t, 0.22, p + tr, 0.92, 0.0) for p in L["voic"][cp][ci]]
                    if "lead" in blk.get("parts", []) and "comp" in L["voic"]:
                        parts["lead"].append((t, 0.24, L["voic"]["comp"][ci][-1] + tr, 0.95, 0.0))
                    drums += [(t, 0.2, PR.GM["kick"], 1.0, 0.0), (t, 0.2, PR.GM["snare"], 0.85, 0.0)]
                drums.append((b * 4 + blk["kime"][0] / 4, 0.5, PR.GM["crash"], 0.75, 0.0))
                continue
            if L.get("lead_vars") and ("lead" in blk.get("parts", []) or "lead_hi" in blk.get("parts", [])):
                if lb == 0 or blk["loop"] not in cur_var:
                    passes[blk["loop"]] = passes.get(blk["loop"], -1) + 1
                    cyc = ["base", "ornament", "base", "lift", "base", "answer"]     # the hook comes back as written every other pass
                    per = max(1, 8 // max(1, L["bars"]))          # short loops keep a variant for 8 bars, so phrases repeat whole
                    cur_var[blk["loop"]] = blk.get("lead_var") or cyc[(passes[blk["loop"]] // per) % len(cyc)]
                if blk.get("lead_var"):
                    cur_var[blk["loop"]] = blk["lead_var"]
            for p in blk.get("parts", []):
                src_notes = L["parts"].get(p, [])
                if p in ("lead", "lead_hi") and L.get("lead_vars"):
                    src_notes = L["lead_vars"][cur_var.get(blk["loop"], "base")]
                    if p == "lead_hi":
                        src_notes = [(t, d, q + 12, v * 0.55, o) for (t, d, q, v, o) in src_notes]
                for (t, d, pitch, v, o) in src_notes:
                    if lb * 4 <= t < lb * 4 + 4:
                        parts[p].append((b * 4 + t - lb * 4, d, pitch + (tr if p != "drums" else 0), v * blk.get("vel", {}).get(p, 1.0), o))
            fill = blk.get("fill") if i == n - 1 else ("snare_roll" if i == n - 2 and blk.get("fill") == "roll16" else None)
            if blk.get("fill") == "roll16" and i == n - 1:
                fill = "roll16"
            style = g["drums"]
            for (t, snd, v, o) in PR.drum_bar(style, set(blk.get("drums", [])), fill, i if g.get("drum_cycle_per_block") else b, rng, dcfg):
                drums.append((b * 4 + t, 0.2, PR.GM[snd], v, o))
            if i == 0 and blk.get("crash"):
                drums.append((b * 4, 0.5, PR.GM["crash"], 0.7, 0.0))
        bar_map.append((bar + 1, bar + n, blk["name"], blk["loop"], blk.get("parts", []), blk.get("drums", [])))
        bar += n
        prev_loop, carried = blk["loop"], off + n
    return parts, drums, bar_map


def write_midi(path: Path, title: str, bpm: float, parts: dict, drums: list):
    ppq = 480
    mf = mido.MidiFile(type=1, ticks_per_beat=ppq)
    meta = mido.MidiTrack()
    meta += [mido.MetaMessage("track_name", name=title, time=0), mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0),
             mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0)]
    mf.tracks.append(meta)
    extra = [k for k in parts if k not in PART_ORDER]          # the Electronium's own channels (counter, el3 ...)
    for name, evs in [(k, parts[k]) for k in PART_ORDER + extra] + [("drums", drums)]:
        if not evs:
            continue
        ch, prog = CHANNEL[name] if name in CHANNEL else (EXTRA_CH[extra.index(name) % len(EXTRA_CH)], 81)
        tr = mido.MidiTrack()
        tr.append(mido.MetaMessage("track_name", name=name, time=0))
        if ch != 9:
            tr.append(mido.Message("program_change", channel=ch, program=prog, time=0))
        msgs = []
        for (t, d, p, v, o) in evs:
            on = max(0, round((t + o) * ppq))
            off = max(on + 1, round((t + o + d) * ppq))
            c, p = (DRUM_HI_CH, p - 128) if name == "drums" and 127 < p < 256 else (ch, p)
            msgs += [(on, 1, mido.Message("note_on", channel=c, note=int(np.clip(p, 0, 127)), velocity=int(np.clip(round(v * 127), 1, 127)))),
                     (off, 0, mido.Message("note_off", channel=c, note=int(np.clip(p, 0, 127)), velocity=0))]
        msgs.sort(key=lambda m: (m[0], m[1]))
        now = 0
        for tk, _, m in msgs:
            tr.append(m.copy(time=tk - now))
            now = tk
        mf.tracks.append(tr)
    mf.save(str(path))


def instrument_map(g: dict, title: str, name: str, seed: int) -> dict:
    tracks = {k: dict(v) for k, v in g.get("sounds", {}).items()}
    if "lead" in tracks and "lead_hi" not in tracks:
        hi = dict(tracks["lead"])
        hi["gain_db"] = hi.get("gain_db", -10) - 8
        hi["pan"] = 0.2
        tracks["lead_hi"] = hi
    if "lead" in tracks and "sidekick" not in tracks and g.get("melody", {}).get("writer") == "electronium":   # its second channel: the lead's sound, lower, left
        sk_ = dict(tracks["lead"])
        sk_["gain_db"] = sk_.get("gain_db", -10) - 3
        sk_["pan"] = -0.25
        tracks["sidekick"] = sk_
    for k, tr in channel_tracks(g).items():
        if tracks.get(k, {}).get("kind") == "synthesis":   # an experimental engine track keeps the tone as its fallback
            tracks[k] = {**tracks[k], "fallback": tr}
        else:
            tracks[k] = tr
    tracks.update(engine_tracks(g, tracks))
    kit = g["_kit"]
    tracks["drums"] = {"channel": 9, "map": {str(k): v for k, v in kit["map"].items()}, "sounds": kit["sounds"], "stems": kit["stems"]}
    return {"seed": seed, "tail_s": 3.0, "fade_out_s": 1.5,
            "preset_dirs": [str(ENGINE / "presets")],
            "meta": {"title": title, "artist": ARTIST, "composer": COMPOSER, "slug": name, "genre": g["name"]},
            "mix": {"console_drive": 1.15}, "master": {**MASTER, **g.get("master", {})}, "sends": SENDS, "tracks": tracks}


def channel_tracks(g: dict) -> dict:
    """The Electronium's channels that have their own tone generator (electronium_voice.py), as render tracks."""
    if g.get("melody", {}).get("writer") != "electronium":
        return {}
    import electronium as EL
    out = {}
    for ch in EL.channels(EL.patch(g.get("electronium"))):
        t = EL.tone(ch)
        if t is None:
            continue
        mx = ch["mix"]
        tr = {"kind": "pyvoice", "preset": {"module": str(ROOT / "bountiful" / "electronium_voice.py"), "fn": "note", **t},
              "gain_db": mx.get("gain_db", -10.0), "pan": mx.get("pan", 0.0), "glide_gap": 0.08,
              "sends": {"plate": mx.get("reverb", 0.0), "echo": mx.get("echo", 0.0), "spring": mx.get("spring", 0.0)},
              "variants": mx.get("variants", 6)}
        tr.update({k: mx[k] for k in ("hp", "lp", "mono", "eq", "drive", "crush", "duck", "width", "chorus") if k in mx})
        out[ch["name"]] = tr
        if ch["name"] == "lead":                       # its octave-up double, on the same generator
            out["lead_hi"] = {**tr, "gain_db": tr["gain_db"] - 8, "pan": 0.2}
    return out


def engine_tracks(g: dict, tracks: dict) -> dict:
    """The Electronium's channels that play a synthesis engine (channel `engine`, synthesis/), as synthesis tracks:
    the tone generator or genre sound they replace stays as the fallback, and the recorder's synth.<param> moves
    become the track's automation. Nothing when experimental synthesis is switched off: the old sounds play."""
    if g.get("melody", {}).get("writer") != "electronium":
        return {}
    import electronium as EL
    import synthesis as S
    if not S.enabled():
        return {}
    from synthesis.genre import track
    p = EL.patch(g.get("electronium"))
    out = {}
    for ch in EL.channels(p):
        spec = EL.engine_spec(ch)
        if spec is None or spec["engine"] not in S.ENGINES:
            continue
        moves = []                                     # the recorder's bars are 1-based, the automation's 0-based
        for m in p.get("moves", []):
            st = {k: v for k, v in m.get("set", {}).items() if k.startswith("synth.")}
            if st and m.get("channel") in (None, ch["name"]):
                moves.append({**{k: m[k] - 1 for k in ("bar", "to_bar") if k in m}, "set": st})
        names = [ch["name"]] + (["lead_hi"] if ch["name"] == "lead" and "lead_hi" in tracks else [])
        for nm in names:
            tr = track(spec, tracks.get(nm))
            if moves:
                tr["moves"] = list(tr.get("moves", [])) + moves
            if nm == "lead_hi":
                tr["gain_db"], tr["pan"] = tracks["lead"].get("gain_db", -10) - 8, 0.2
            out[nm] = tr
    return out


def produce(song: Path, g: dict, title: str | None = None, out: Path | None = None, seed: int = 1, log=print) -> Path:
    sk = SK.load(song)
    title = title or f"{g['name'].split(chr(39))[0].strip()} {sk.seed}"
    name = slug(title)
    out = out or DATA / "tracks" / name
    out.mkdir(parents=True, exist_ok=True)
    s2 = stretched(sk, g.get("stretch", 1))
    rng = np.random.default_rng(seed)
    loops = produce_loops(s2, g, rng)
    machine = electronium_machine(g)
    timeline: list = []
    parts, drums, bar_map = arrange(loops, g, rng, machine, timeline, seed=seed)
    if machine and g.get("melody", {}).get("writer") == "electronium":
        perform_electronium(machine, s2, timeline, parts)
    mid = out / f"{name}.mid"
    write_midi(mid, title, g["bpm"], parts, drums)
    sys.path.insert(0, str(ENGINE / "studio"))
    from midi_studio import to_toml
    (out / "instruments.toml").write_text(to_toml(instrument_map(g, title, name, seed)))
    # notes
    from tells import tells
    t_raw = tells(_raw_midi(song))
    t_new = tells(mid)
    bars = sum(b[1] - b[0] + 1 for b in bar_map)
    secs = bars * 4 * 60 / g["bpm"]
    lines = [f"{title} — {g['name']}, {g['bpm']} bpm, {sk.key}, {bars} bars ({int(secs // 60)}:{secs % 60:04.1f})",
             f"composition: Bountiful Music skeleton from {song.name} (seed {sk.seed}){' played at 1/' + str(g['stretch']) + ' speed' if g.get('stretch', 1) > 1 else ''}", "",
             "Loops (source bars, chords as produced):"]
    for k, L in loops.items():
        lines.append(f"  {k}: source bars {L['src']['start_bar'] + 1}-{L['src']['start_bar'] + L['bars']}  {chord_names(L['chords'])}")
    lines += ["", "Arrangement:"] + [f"  {a:3d}-{b:3d}  {nm:30s} loop {lp}  parts: {', '.join(ps) or '-':32s} drums: {', '.join(dr) or '-'}"
                                      for a, b, nm, lp, ps, dr in bar_map]
    lines += ["", "Tells (raw composer output -> produced):"]
    for k in t_new:
        if k in t_raw:
            lines.append(f"  {k:28s} {t_raw[k]:6.2f} -> {t_new[k]:6.2f}")
    lines += ["", "tracks: " + ", ".join(f"{k} {len(v)} notes" for k, v in parts.items() if v) + f", drums {len(drums)} hits"]
    src = {"song": str(song), "genre": g["id"], "title": title, "seed": seed}
    if machine:
        import electronium as EL
        lines += [""] + machine.summary()
        (out / "electronium.toml").write_text(EL.dump(machine.p))
        src["bounty"] = machine.p["bounty"]
    (out / "notes.txt").write_text("\n".join(lines) + "\n")
    (out / "source.json").write_text(json.dumps(src, indent=1))
    log("\n".join(lines))
    return out


def electronium_machine(g: dict):
    """The genre's Electronium (electronium.py), if its melody writer or drums use one: the patch is the genre's
    [electronium] table, the terrain covers the whole arrangement."""
    if g.get("melody", {}).get("writer") != "electronium" and g.get("drums") != "electronium":
        return None
    import electronium as EL
    bars = sum(b["bars"] for b in g["arrangement"])
    return EL.Machine(EL.patch(g.get("electronium")), bars, g.get("swing", 0.5), g["bpm"], g.get("melody", {}).get("humanize_ms", 0))


def perform_electronium(machine, sk: SK.Skeleton, timeline: list, parts: dict):
    """Every Electronium channel replaces the part it's named after (the lead and its lead_hi double, the bass ...) or adds
    one. Each plays where a block lists it, else with its `with` part (the lead). The sidekick plays where a block
    lists it, or with the lead when no block does."""
    tonic, key_pcs = sk.tonic, sorted(PR.key_scale(sk))
    listed = any(c["sidekick_part"] for c in timeline)
    for c in timeline:
        c.update(tonic=tonic, key_pcs=key_pcs, sidekick=c["sidekick_part"] if listed else c["lead"])
    res = machine.perform(timeline)
    hi_bars = {int(t // 4) for (t, *_ ) in parts["lead_hi"]}
    parts["sidekick"] = []
    for name, notes in res["parts"].items():          # every channel replaces the part of its name (bass, arp ...)
        parts[name] = notes
    first = next((c["name"] for c in machine.chans if c["role"] == "melody"), None)
    if first:
        parts["lead_hi"] = [(t, d, p + 12, v * 0.55, o) for (t, d, p, v, o) in res["parts"][first] if int(t // 4) in hi_bars]


def _raw_midi(song: Path) -> Path:
    """The composer's raw output as a .mid (for before/after measurements)."""
    import am2mid
    import contextlib
    import io
    mid = song.with_name(song.name.replace(".am.json", ".mid"))
    if not mid.exists():
        with contextlib.redirect_stdout(io.StringIO()):
            am2mid.convert(song)
    return mid


def render_script(track: Path) -> Path:
    """render_midi.py, or the Synthesis Lab's wrapper of it when the song has kind = "synthesis" tracks."""
    try:
        inst = tomllib.loads((track / "instruments.toml").read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return RENDER
    from synthesis.rendering import uses_synthesis
    return HERE / "synthesis" / "render.py" if uses_synthesis(inst) else RENDER


def render(track: Path, bars: str | None = None, only: str | None = None, log=print) -> int:
    mid = next(track.glob("*.mid"))
    cmd = ["nice", "-n", "10", PY, "-u", str(render_script(track)), str(mid), str(track / "instruments.toml"), "--out", str(track / "exports")]
    if bars:
        cmd += ["--bars", bars, "--no-stems", "--no-mp3", "--name", "preview"]
    else:
        cmd += ["--stems", str(track / "stems")]
    if only:
        cmd += ["--only", only]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in p.stdout:
        log(line.rstrip())
    return p.wait()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("genres")
    c = sub.add_parser("compose")
    c.add_argument("--genre", required=True)
    c.add_argument("--count", type=int, default=12)
    c.add_argument("--seed", type=int, action="append")
    p = sub.add_parser("produce")
    p.add_argument("--genre", required=True)
    p.add_argument("--song", type=Path, required=True)
    p.add_argument("--title")
    p.add_argument("--render", action="store_true")
    p.add_argument("--electronium", action="store_true", help="the Electronium writes the lead (and sidekick)")
    p.add_argument("--electronium-drums", action="store_true", help="the Electronium's clock matrix plays the drums")
    p.add_argument("--bounty", help="the Electronium's seed: same Bounty, same terrain")
    p.add_argument("--patch", type=Path, help="an electronium.toml patch (e.g. from an earlier track)")
    p.add_argument("--experimental", action="store_true", help="switch on the genre's [experimental_synthesis] engines")
    r = sub.add_parser("render")
    r.add_argument("track", type=Path)
    r.add_argument("--bars")
    rr = sub.add_parser("reroll")
    rr.add_argument("--song", type=Path, required=True)
    rr.add_argument("--genre", required=True)
    rr.add_argument("--what", default="melody", help="melody, harmony, bass, structure (comma-separated)")
    args = ap.parse_args()
    G = genres()
    if args.cmd == "genres":
        for k, g in G.items():
            print(f"{k:26s} {g['name']:26s} {g['bpm']} bpm  {g['description'][:90]}")
    elif args.cmd == "compose":
        g = G[args.genre]
        files = compose(g, args.count, args.seed)
        rows = rank(files, g)
        for r in rows:
            print(f"{r['score']:5.2f}  {Path(r['file']).name:40s} {r['key']:10s} chorus: {r['chorus']}")
        (DATA / "songs" / g["id"] / "ranking.json").write_text(json.dumps(rows, indent=1))
    elif args.cmd == "produce":
        g = G[args.genre]
        if args.electronium or args.electronium_drums or args.bounty or args.patch:
            import electronium as EL
            el = EL.patch(g.get("electronium"), EL.load(args.patch) if args.patch else None, {"bounty": args.bounty} if args.bounty else None)
            g["electronium"] = el
            if args.electronium or args.bounty or args.patch:
                g.setdefault("melody", {})["writer"] = "electronium"
            if args.electronium_drums:
                g["drums"] = "electronium"
        if args.experimental:
            from synthesis import genre as SG
            g = SG.apply(g, force=True)
        out = produce(args.song, g, args.title)
        if args.render:
            render(out)
    elif args.cmd == "render":
        render(args.track, args.bars)
    elif args.cmd == "reroll":
        g = G[args.genre]
        files = compose(g, 0, [int(np.random.default_rng().integers(1, 2**31 - 1))], pin=args.song, reroll=args.what.split(","))
        for r in rank(files, g):
            print(f"{r['score']:5.2f}  {Path(r['file']).name}  chorus: {r['chorus']}")


if __name__ == "__main__":
    main()
