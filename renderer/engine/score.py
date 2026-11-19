"""Turn a song config (song.toml) into a Score: every note of every part, the chords, the drum hits and
the section map. No audio here — see render.py."""
from __future__ import annotations

import tomllib
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import compose as C
from . import drums as D
from . import theory as th


@dataclass
class Section:
    name: str
    start_bar: int
    bars: int
    cfg: dict
    slots: list = field(default_factory=list)       # chord slots, beats relative to section start
    voicings: list = field(default_factory=list)


@dataclass
class Score:
    cfg: dict
    bpm: float
    beat_s: float
    sections: list[Section]
    notes: dict[str, list[C.Note]]
    drum_hits: dict[str, list[tuple[Section, list[D.Hit]]]]   # 'break' / 'rush' -> per section
    layer_hits: dict[str, list[tuple[float, str, float]]]     # clean kit hits in beats: top/perc
    total_bars: int
    fx_events: list = field(default_factory=list)   # ('riser'|'revcrash'|'boom', start_beat, end_beat, level)

    def chords(self) -> list[tuple[float, float, str]]:
        out = []
        for s in self.sections:
            for sl in s.slots:
                out.append((s.start_bar * 4 + sl.start, sl.beats, sl.chord.symbol))
        return out


def rng_for(seed: int, *keys) -> np.random.Generator:
    """Independent, stable random streams per section and part: editing one section never changes
    what the dice say anywhere else."""
    return np.random.default_rng([seed] + [zlib.crc32(str(k).encode()) for k in keys])


def _as_list(v, n):
    if isinstance(v, list):
        return (v + [v[-1]] * n)[:n]
    return [v] * n


def _pass_slots(cfg, prog_name: str, bars: int, from_bar: int = 0) -> list[th.Slot]:
    bars_txt = cfg["progressions"][prog_name]
    base = th.parse_progression(bars_txt)
    length = len(bars_txt) * 4
    out = []
    pos = 0.0
    while pos < (from_bar + bars) * 4:
        for s in base:
            out.append(th.Slot(s.chord, s.start + pos, s.beats))
        pos += length
    a, b = from_bar * 4, (from_bar + bars) * 4
    win = [th.Slot(s.chord, s.start - a, s.beats) for s in out if s.start < b and s.start + s.beats > a]
    for s in win:
        if s.start < 0:
            s.beats += s.start
            s.start = 0
        s.beats = min(s.beats, bars * 4 - s.start)
    return win


_DEFAULT_COMP = {k: v for k, v in C.COMP.items()}
_DEFAULT_BASS = {k: v for k, v in C.BASS.items()}


def _install_patterns(cfg: dict) -> None:
    """Songs can add their own comping rhythms and bass cells ([comp_patterns], [bass_cells])."""
    C.COMP.clear()
    C.COMP.update(_DEFAULT_COMP)
    for name, pats in cfg.get("comp_patterns", {}).items():
        C.COMP[name] = [[tuple(h) for h in pat] for pat in pats]
    C.BASS.clear()
    C.BASS.update(_DEFAULT_BASS)
    for name, cells in cfg.get("bass_cells", {}).items():
        C.BASS[name] = [[tuple(h) for h in cell] for cell in cells]


def build(song_dir: Path) -> Score:
    cfg = tomllib.loads((song_dir / "song.toml").read_text())
    if cfg.get("profile"):
        # a style profile (profiles/<name>.toml): tempo, swing, kit, rhythms, progressions, voices; the song wins
        def merge(b, o):
            out = dict(b)
            for k, v in o.items():
                out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
            return out
        prof = Path(__file__).resolve().parent.parent / "profiles" / f"{cfg['profile']}.toml"
        cfg = merge(tomllib.loads(prof.read_text()), cfg)
    if cfg.get("mix_base"):
        # album cohesion: start from another track's mix/master and override per instrument
        base = tomllib.loads((song_dir.parent / cfg["mix_base"] / "song.toml").read_text())
        mix = {k: dict(v) for k, v in base.get("mix", {}).items()}
        for k, v in cfg.get("mix", {}).items():
            mix.setdefault(k, {}).update(v)
        cfg["mix"] = mix
        cfg["master"] = base.get("master", {}) | cfg.get("master", {})
        cfg["swing"] = base.get("swing", {}) | cfg.get("swing", {})
        def deep(b, o):
            out = dict(b)
            for k, v in o.items():
                out[k] = deep(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
            return out
        cfg["kit"] = deep(base.get("kit", {}), cfg.get("kit", {}))
    _install_patterns(cfg)
    seed = cfg["seed"]
    bpm = cfg["bpm"]
    beat_s = 60 / bpm
    phrases = cfg["phrases"]
    sections: list[Section] = []
    bar = 0
    for sc in cfg["sections"]:
        sections.append(Section(sc["name"], bar, sc["bars"], sc))
        bar += sc["bars"]
    total_bars = bar

    notes: dict[str, list[C.Note]] = {k: [] for k in ("rhodes", "rhodes_solo", "pad", "bass", "vibes", "horn", "piano", "signals")}
    # extra parts a song defines in [voices] (e.g. a strings layer, temple bells), played by any synth or LMMS
    extras = [k for k, v in cfg.get("voices", {}).items() if k not in notes and ("backend" in v or "kind" in v)]
    for k in extras:
        notes[k] = []
    drum_hits = {"break": [], "rush": []}
    layer_hits = {"top": [], "perc": [], "kick": [], "snare": []}
    fx_events: list[tuple] = []
    prev_piano = None
    prev_voicing = None
    prev_root = None
    theme_A = th.parse_progression(cfg["progressions"]["A"]) if "A" in cfg["progressions"] else None

    for si, sec in enumerate(sections):
        sc = sec.cfg
        progs = sc["progressions"]
        n_pass = len(progs)
        pass_bars = sec.bars // n_pass
        vary = _as_list(sc.get("vary", [0.0]), n_pass)
        S0 = sec.start_bar * 4
        # ---- harmony (re-harmonised around whatever written melody this pass carries)
        for p, name in enumerate(progs):
            slots = _pass_slots(cfg, name, pass_bars, sc.get("from_bar", 0))
            tune = []
            for part in ("horn", "vibes"):
                spec = _as_list(sc.get(part, {}), n_pass)[p]
                if spec and isinstance(spec, dict) and "phrase" in spec and not spec.get("refit") and spec["phrase"] not in cfg.get("phrase_src", {}):
                    src = phrases[spec["phrase"]]
                    wa, wb = spec.get("bars", [0, len(src)])
                    ns = C.parse_phrase(src[wa:wb], part)
                    if "tail" in spec:
                        cut = (wb - wa - len(phrases[spec["tail"]])) * 4
                        ns = [n for n in ns if n.beat < cut] + C.parse_phrase(phrases[spec["tail"]], part, cut)
                    tune += [(n.beat, n.pitch) for n in ns]
            slots = C.vary_progression(slots, rng_for(seed, sec.name, "harmony", p), vary[p], tune)
            for s in slots:
                sec.slots.append(th.Slot(s.chord, s.start + p * pass_bars * 4, s.beats))
        sec.voicings, prev_voicing = C.section_voicings(sec.slots, prev_voicing)

        # ---- comping, pad, piano
        if sc.get("rhodes"):
            ns = C.comp(sec.slots, sec.voicings, S0, sec.bars, sc["rhodes"], rng_for(seed, sec.name, "rhodes"),
                        strum_ms=cfg.get("strum_ms", 9.0))
            for n in ns:
                n.vel *= sc.get("rhodes_vel", 1.0)
            notes["rhodes"] += C.humanize(ns, rng_for(seed, sec.name, "rhodes-h"), 5, 0.05)
        if sc.get("pad"):
            notes["pad"] += C.pad_part(sec.slots, sec.voicings, S0)
        pr = cfg.get("piano_range", [55, 84, 76])
        for p, on in enumerate(_as_list(sc.get("piano", False), n_pass)):
            if not on or isinstance(on, dict):
                continue
            a, b = p * pass_bars * 4, (p + 1) * pass_bars * 4
            idx = [i for i, s in enumerate(sec.slots) if a <= s.start < b]
            sl = [th.Slot(sec.slots[i].chord, sec.slots[i].start - a, sec.slots[i].beats) for i in idx]
            if isinstance(on, str):
                # comped on its own voice-led voicings (e.g. house organ chord riffs)
                contour = cfg.get("piano_contour")   # a top line to lead towards: a list, or {progression: list}
                if isinstance(contour, dict):
                    contour = contour.get(progs[p])
                tw = cfg.get("piano_top_weight", 2.5) if contour else 0.6
                vs = th.voice_lead([x.chord for x in sl], pr[0], pr[1], contour or pr[2], prev_piano, top_weight=tw)
                prev_piano = vs[-1] if vs else prev_piano
                ns = C.comp(sl, vs, S0 + a, pass_bars, on, rng_for(seed, sec.name, "piano", p), part="piano", strum_ms=4,
                            motion=cfg.get("piano_motion", 0.0), cycle=cfg.get("comp_cycle", False))
            else:
                vs = [sec.voicings[i] for i in idx]
                ns = C.stabs(sl, vs, S0 + a, pass_bars, rng_for(seed, sec.name, "piano", p))
            notes["piano"] += C.humanize(ns, rng_for(seed, sec.name, "piano-h", p), 4, 0.04)

        # ---- bass
        if sc.get("bass") and isinstance(sc["bass"], str):
            ns, prev_root = C.bassline(sec.slots, S0, sec.bars, sc["bass"], rng_for(seed, sec.name, "bass"), prev_root=prev_root)
            for n in ns:
                n.tag = f"bright={sc.get('bass_bright', 1.0)}"
            notes["bass"] += C.humanize(ns, rng_for(seed, sec.name, "bass-h"), 4, 0.04)

        # ---- melody parts (horn, vibes) per pass
        lead_by_pass: dict[int, list[C.Note]] = {}
        for part in ("horn", "vibes", "piano", "rhodes_solo", "bass", *extras):
            specs = _as_list(sc.get(part, {}), n_pass)
            for p, spec in enumerate(specs):
                if not spec or not isinstance(spec, dict):
                    continue
                a = p * pass_bars * 4
                sl = [th.Slot(s.chord, s.start - a, s.beats) for s in sec.slots if a <= s.start < a + pass_bars * 4]
                rng = rng_for(seed, sec.name, part, p)
                ns: list[C.Note] = []
                if "phrase" in spec:
                    src = phrases[spec["phrase"]]
                    wa, wb = spec.get("bars", [0, len(src)])
                    ns = C.parse_phrase(src[wa:wb], part)
                    if "tail" in spec:
                        tail = phrases[spec["tail"]]
                        cut = (wb - wa - len(tail)) * 4
                        ns = [n for n in ns if n.beat < cut] + C.parse_phrase(tail, part, cut)
                    src_prog = cfg.get("phrase_src", {}).get(spec["phrase"]) or spec.get("refit")
                    if spec.get("tile"):
                        # repeat the phrase across the pass, re-fitting each copy to the chords under it
                        span = (wb - wa) * 4
                        src_slots = _pass_slots(cfg, src_prog or progs[p], wb - wa, wa)
                        tiled = []
                        for k in range(int(pass_bars * 4 // span)):
                            dst = [th.Slot(x.chord, x.start - k * span, x.beats) for x in sl if x.start + x.beats > k * span and x.start < (k + 1) * span]
                            moved = C.refit(ns, src_slots, dst, 0, 0)
                            tiled += [C.Note(n.beat + k * span, n.dur, n.pitch, n.vel, n.part) for n in moved]
                        ns = tiled
                    elif src_prog:
                        # the phrase was written over another progression: move it onto these chords by degree
                        src_slots = _pass_slots(cfg, src_prog, wb - wa, wa)
                        ns = C.refit(ns, src_slots, sl, 0, 0)
                    for op in spec.get("ops", []):
                        k, v = op.split(":")
                        if k == "rhythm":
                            ns = C.rhythm_vary(ns, rng, float(v))
                        elif k == "ornament":
                            ns = C.ornament(ns, rng, float(v))
                        elif k == "octave":
                            ns = C.transpose(ns, int(v))
                        elif k == "displace":
                            ns = C.displace(ns, int(v))
                        elif k == "diatonic":
                            ns = C.diatonic(ns, sl, 0, int(v))
                    ns = C.fix_avoid(ns, sl, 0)
                    for n in ns:
                        n.vel *= spec.get("vel", 0.72) / 0.72
                elif "motif" in spec:
                    src = phrases[spec["motif"]]
                    wa, wb = spec.get("bars", [0, 1])
                    frag = C.parse_phrase(src[wa:wb], part)
                    src_slots = _pass_slots(cfg, cfg.get("phrase_src", {}).get(spec["motif"]) or spec.get("refit", "A"), wb - wa, wa)
                    for at in spec.get("at", [3]):
                        dst = [th.Slot(s.chord, s.start - at * 4, s.beats) for s in sl if s.start + s.beats > at * 4]
                        moved = C.refit(frag, src_slots, dst, 0, 0) if dst else frag
                        ns += [C.Note(n.beat + at * 4, n.dur, n.pitch + 12 * (part == "vibes"), spec.get("vel", 0.5), part) for n in moved]
                elif spec.get("chords"):
                    # sustained chords on this part (a strings / choir / organ layer), voice-led in its own range
                    rg = spec.get("range", [55, 79, 72])
                    vs = th.voice_lead([x.chord for x in sl], rg[0], rg[1], rg[2])
                    ns = C.pad_part(sl, vs, 0, part, spec.get("vel", 0.5))
                elif spec.get("guide"):
                    ns = C.guide_line(sl, 0, rng, part, vel=spec.get("vel", 0.5))
                elif spec.get("answers"):
                    lead = [C.Note(n.beat - S0 - a, n.dur, n.pitch, n.vel, n.part) for n in lead_by_pass.get(p, [])]
                    ns = C.answers(lead, sl, 0, pass_bars * 4, rng, part, density=spec.get("density", 0.7))
                ns = [n for n in ns if 0 <= n.beat < pass_bars * 4]
                for n in ns:
                    n.beat += S0 + a
                ns = C.humanize(ns, rng_for(seed, sec.name, part, p, "h"), 7, 0.05)
                notes[part] += ns
                if part == "horn":
                    lead_by_pass[p] = ns

        # ---- solo
        if isinstance(sc.get("solo"), dict) and sc["solo"].get("style") == "float":
            rng_l = sc["solo"].get("range", [64, 84])
            ns = C.float_solo(sec.slots, S0, sec.bars, rng_for(seed, sec.name, "float", sc["solo"].get("take", 0)),
                              lo=rng_l[0], hi=rng_l[1])
            notes["rhodes_solo"] += C.humanize(ns, rng_for(seed, sec.name, "float-h"), 5, 0.03)
        elif sc.get("solo"):
            has_theme = "theme" in phrases and theme_A is not None
            ns = C.solo(sec.slots, S0, sec.bars, rng_for(seed, sec.name, "solo"),
                        motif=C.parse_phrase(phrases["theme"], "x") if has_theme else None, motif_slots=theme_A)
            notes["rhodes_solo"] += C.humanize(ns, rng_for(seed, sec.name, "solo-h"), 6, 0.05)

        # ---- final chord
        if sc.get("final_chord"):
            last = S0 + (sec.bars - 1) * 4
            ch = sec.slots[-1].chord
            v = th.voice_lead([ch], 50, 79, 72, prev_voicing)[0]
            notes["rhodes"] += [C.Note(last, 4.0, p, 0.6, "rhodes", shift=k * 0.012) for k, p in enumerate(v)]
            notes["bass"] += [C.Note(last, 4.0, th.fit(ch.root, 31), 0.9, "bass", tag="bright=1.0")]
            notes["vibes"] += [C.Note(last + 0.5, 3.5, th.fit((ch.root + 14) % 12, 79), 0.45, "vibes")]

        # ---- atmosphere 'signals': sparse shortwave blips on the F minor pentatonic
        if "signals" in sc.get("atmos", []):
            rng = rng_for(seed, sec.name, "signals")
            penta = [th.note(x) for x in cfg.get("signals_scale", ["F6", "Ab6", "Bb6", "C7", "Eb7", "F7"])]
            for b in range(0, sec.bars, 2):
                if rng.random() < 0.75:
                    t0 = S0 + b * 4 + int(rng.integers(2, 12)) * 0.25
                    for k in range(int(rng.integers(2, 6))):
                        notes["signals"].append(C.Note(t0 + k * 0.25 * rng.choice([1, 1, 2]), 0.1 + 0.15 * rng.random(),
                                                       int(rng.choice(penta)), 0.3 + 0.3 * rng.random(), "signals"))

        # ---- the keys make room for whatever melody is speaking in this section
        if sc.get("make_room", cfg.get("make_room", True)):
            S1_ = S0 + sec.bars * 4
            leads = [n for part in ("horn", "vibes", "rhodes_solo") for n in notes[part] if S0 <= n.beat < S1_ and n.dur >= 0.25]
            abs_slots = sec.slots
            mr = sc.get("make_room", cfg.get("make_room", True))
            for part in (mr if isinstance(mr, list) else ("rhodes", "piano")):
                inside = [n for n in notes[part] if S0 <= n.beat < S1_]
                if inside and leads:
                    rest = [n for n in notes[part] if not (S0 <= n.beat < S1_)]
                    notes[part] = rest + C.make_room(inside, leads, abs_slots, S0)

        # ---- parts entering / leaving inside the section (bars, relative to the section)
        S1 = S0 + sec.bars * 4
        for part, bar in sc.get("enter", {}).items():
            notes[part] = [n for n in notes[part] if not (S0 <= n.beat < S0 + bar * 4)]
        for part, bar in sc.get("exit", {}).items():
            notes[part] = [n for n in notes[part] if not (S0 + bar * 4 <= n.beat < S1)]
        build = sc.get("build", {})
        gap = build.get("gap", 0) if build else 0
        if build.get("riser"):
            fx_events.append(("riser", S1 - build.get("bars", 4) * 4, S1, build.get("riser")))
        if build.get("reverse", build.get("riser")):
            fx_events.append(("revcrash", S1 - 2, S1, 1.0))
        if sc.get("drop"):
            fx_events.append(("boom", S0, S0 + 4, sc["drop"] if isinstance(sc["drop"], float) else 1.0))
        if gap:
            # a breath before the drop: everything but pads and atmosphere stops
            for part in ("rhodes", "rhodes_solo", "bass", "vibes", "horn", "piano", *extras):
                keep = []
                for n in notes[part]:
                    if S1 - gap <= n.beat < S1:
                        continue
                    if n.beat < S1 - gap < n.beat + n.dur and n.beat >= S0:
                        n.dur = S1 - gap - n.beat
                    keep.append(n)
                notes[part] = keep

        # ---- drums
        dr = sc.get("drums", {})
        rng = rng_for(seed, sec.name, "drums")
        d_enter, d_exit = dr.get("enter", {}), dr.get("exit", {})

        def live(stem: str, bar: int) -> bool:
            return d_enter.get(stem, 0) <= bar < d_exit.get(stem, sec.bars)
        if dr.get("breaks", True) and "main" in dr:
            hits = []
            nb = build.get("bars", 0) if build.get("roll") else 0
            for b in range(sec.bars):
                if nb and b >= sec.bars - nb:
                    bar_hits = D.roll_bar(b - (sec.bars - nb), nb, dr, _BREAK_INFO, rng)
                elif not live("break", b):
                    continue
                else:
                    bar_hits = D.program_bar(b, sec.bars, dr, _BREAK_INFO, rng)
                for h in bar_hits:
                    h.beat += b * 4
                    if gap and h.beat >= sec.bars * 4 - gap:
                        continue
                    hits.append(h)
            drum_hits["break"].append((sec, hits))
        if dr.get("pattern"):
            for b in range(sec.bars):
                if dr.get("stop_last") and b == sec.bars - 1:
                    continue
                for beat, stem, kind, v in D.pattern_bar(dr["pattern"], b, sec.bars, rng, dr):
                    if live(stem, b) and not (gap and b * 4 + beat >= sec.bars * 4 - gap):
                        layer_hits[stem].append((S0 + b * 4 + beat, kind, v))
        if dr.get("rush", 0) > 0:
            hits = []
            for b in range(sec.bars):
                for h in D.rush_bar(_BREAK_INFO, dr.get("alt", "roller"), rng, density=0.85):
                    h.beat += b * 4
                    h.vel *= dr["rush"]
                    hits.append(h)
            drum_hits["rush"].append((sec, hits))
        for b in range(sec.bars):
            B0 = S0 + b * 4
            if (dr.get("stop_last") and b == sec.bars - 1) or dr.get("pattern"):
                continue
            in_gap = (lambda t: gap and b * 4 + t >= sec.bars * 4 - gap)
            if dr.get("hats", 0) > 0 and live("hats", b):
                layer_hits["top"] += [(B0 + t, k, v * dr["hats"]) for t, k, v in D.hats_bar(rng, 0.35 + 0.5 * dr["hats"], 0.5) if not in_gap(t)]
            if dr.get("ride", 0) > 0 and live("ride", b):
                layer_hits["top"] += [(B0 + t, k, v * dr["ride"]) for t, k, v in D.ride_bar(rng) if not in_gap(t)]
            if dr.get("perc", 0) > 0 and live("perc", b):
                layer_hits["perc"] += [(B0 + t, k, v * dr["perc"]) for t, k, v in D.perc_bar(rng, b) if not in_gap(t)]
        if sc.get("crash") or sc.get("drop"):
            layer_hits["top"].append((S0, "crash", 0.55))

    # keep parts inside their instrument's real range (e.g. a vibraphone tops out at F6): fold by octaves
    ranges = {"vibes": (53, 89)}
    for part, v in cfg.get("voices", {}).items():
        if "range" in v:
            ranges[part] = tuple(v["range"])
        elif part == "vibes" and v.get("kind") in ("vox", "horn", "stab"):
            ranges.pop("vibes", None)
    for part, (lo, hi) in ranges.items():
        for n in notes.get(part, []):
            while n.pitch > hi:
                n.pitch -= 12
            while n.pitch < lo:
                n.pitch += 12
    for k in notes:
        notes[k].sort(key=lambda n: n.beat)
    return Score(cfg, bpm, beat_s, sections, notes, drum_hits, layer_hits, total_bars, fx_events)


class _ClassInfo:
    """program_bar only needs each break's slice classes; this gives them without recording audio."""

    def __init__(self):
        self.data = {}
        for name, spec in D.BREAKS.items():
            classes = []
            for step in range(32):
                hit = {k for k in ("K", "S", "G", "H", "O", "R") if any(s == step for s, _ in spec[k])}
                classes.append("K" if "K" in hit else "S" if "S" in hit else "G" if "G" in hit else "H")
            self.data[name] = type("B", (), {"classes": classes})()

    def __getitem__(self, k):
        return self.data[k]


_BREAK_INFO = _ClassInfo()
