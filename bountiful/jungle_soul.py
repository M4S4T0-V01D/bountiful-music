#!/usr/bin/env python3
"""'Velvet Static': soulful early-90s UK atmospheric jungle at 162 bpm, written to a brief about the intro: a warm,
tape-worn keyboard phrase (doubled by a wordless 'ooh' voice) opens alone, lush pads and slow jazz chords join, then
filtered break fragments, shuffled hats and ghost snares gather until our own Amen-style break (the C-Lizzy break,
bountiful/break_maker.py) is revealed with a deep rolling sub. No riser, no boom, no crash on the reveal: the filter on
the fragments opens over eight bars and the phrase plays straight through it. The opening phrase is loop A's melody, so it
returns with loop A: alone in the breakdown, over the second groove and in the outro.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/jungle_soul.py            # build + validate
    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/jungle_soul.py --validate # checks only
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import break_maker as BM  # noqa: E402
import lmms_tracks as LT  # noqa: E402
import producer as PR  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BPM = 162
SL = BM.OUT / f"slices_{BPM}"                       # the C-Lizzy break at 162: s00-s63, rb00-rb15 (reversed beats), ride0-3
EXTRA = ROOT / "samples" / "breaks" / "velvet162"    # this track's own takes: shuffled hats (h00-h15) and a ghost one-shot
SR = 44100


def build_samples():
    if not (SL / "s00.wav").exists():
        BM.make(BPM)
    EXTRA.mkdir(parents=True, exist_ok=True)
    fade = int(0.0015 * SR)
    n1 = 60 / BPM / 4 * SR

    def cut(src, a, b, name, fade_in=True):
        s = src[int(round(a)): int(round(b)) + fade].copy()
        s[-fade:] *= np.linspace(1, 0, fade)[:, None]
        if fade_in:
            s[:fade] *= np.linspace(0, 1, fade)[:, None]
        sf.write(str(EXTRA / f"{name}.wav"), s.astype(np.float32), SR, subtype="PCM_24")

    hats = {"hat": [[(s, 0.5 if s % 4 == 0 else 0.4 if s % 2 == 0 else 0.26) for s in range(16)]], "open": [[(14, 0.3)]]}
    b, _ = BM.perform(BM.PLAY_BPM, seed=162, pattern=hats, bars=1, ride_on=False, mute=("kick", "snare"))
    fh = BM.speed(BM.record(b) * 0.6, BM.PLAY_BPM, BPM)
    for i in range(16):
        cut(fh, i * n1, (i + 1) * n1, f"h{i:02d}", fade_in=i > 0)
    b, _ = BM.perform(BM.PLAY_BPM, seed=7, pattern={"ghost": [[(0, 1.0)]]}, bars=1, ride_on=False)
    x = BM.speed(BM.record(b), BM.PLAY_BPM, BPM)
    on = int(np.argmax(np.abs(x).max(1) > 0.02))
    cut(x[max(0, on - 32):], 0, 0.3 * SR, "gh1")
    print(f"samples: {SL.name} + {EXTRA.name} ({len(list(EXTRA.glob('*.wav')))} files)")


SOUNDS = [f"s{i:02d}" for i in range(64)] + [f"rb{k:02d}" for k in range(16)] + [f"ride{k}" for k in range(4)] + [f"h{i:02d}" for i in range(16)] + ["gh1"]
NOTES = {s: 20 + k for k, s in enumerate(SOUNDS)}
PR.GM.update(NOTES)


def kit():
    snd = {}
    for s in SOUNDS:
        src = EXTRA if (s[0] == "h" or s == "gh1") else SL
        stem = {"r": "reverse" if s.startswith("rb") else "ride", "h": "hats", "g": "break"}.get(s[0], "break")
        snd[s] = {"samples": [str(src / f"{s}.wav")], "stem": stem, "detune_cents": 3 if s == "gh1" else 0}
    return {"map": {str(NOTES[s]): s for s in snd}, "sounds": snd,
            "stems": {"break": {"hp": 30, "eq": [["peak", 100, 1.5, 0.9], ["highshelf", 7000, -2.5], ["lp", 12500, 2]], "sends": {"room": 0.08}, "gain_db": -2.0},
                      "reverse": {"hp": 150, "sends": {"hall": 0.3}, "gain_db": -9.0},
                      "ride": {"hp": 450, "eq": [["highshelf", 9000, -2.0]], "sends": {"room": 0.15}, "gain_db": -10.0},
                      "hats": {"hp": 600, "sends": {"room": 0.2}, "gain_db": -9.0}}}


# ------------------------------------------------------------------ the break: a bar is four break beats (0-15); "R" a snare roll,
# "S" a stutter, "revN" a reversed beat, None a rest
def bar(beats, vel=1.0):
    out = []
    for q, b in enumerate(beats):
        if b is None:
            continue
        if b == "R":
            out += [[q * 4 + r, 0.6 + 0.1 * r, "s04"] for r in range(4)]
        elif b == "S":
            out += [[q * 4 + r, 0.85, f"s{4 + r % 2:02d}"] for r in range(4)]
        elif isinstance(b, str) and b.startswith("rev"):
            out.append([q * 4, 0.8, f"rb{int(b[3:]):02d}"])
        else:
            out += [[q * 4 + r, vel, f"s{4 * b + r:02d}"] for r in range(4)]
    return out


def gh(*hits):
    """extra ghost snares: (step, vel, ms offset)"""
    return [[s, v, "gh1", ms] for s, v, ms in hits]


SHUFFLE = 14          # ms late on the off 16ths: the hats' shuffle
PROGRAMS = {
    "straight": {"a": bar([0, 1, 2, 3]), "b": bar([4, 5, 6, 7]), "c": bar([8, 9, 10, 11]), "d": bar([12, 13, 14, 15])},
    "roller": {"a": bar([0, 1, 2, 3]), "b": bar([4, 5, 6, 7]), "c": bar([0, 9, 10, 11]), "d": bar([12, 13, 2, 15])},
    "soul": {"a": bar([0, 1, 2, 3]) + gh((6, 0.22, 5), (14, 0.25, -3)), "b": bar([4, 5, 0, 7]) + gh((10, 0.2, 4)),     # breathing: ghosts and one re-ordered beat
             "c": bar([8, 9, 10, 1]) + gh((3, 0.2, -4), (7, 0.24, 6)), "d": bar([12, 13, 14, 15]) + gh((9, 0.22, 3))},
    "half": {"a": bar([0, None, 1, None]), "b": bar([0, None, 1, None]), "c": bar([0, None, 3, None]), "d": bar([0, None, 1, None]) + gh((12, 0.3, 4), (14, 0.35, 0))},
    "frag": {"a": [[4, 0.45, "s04"]], "b": [[12, 0.5, "s12"]] + gh((7, 0.22, 5)), "c": [[0, 0.45, "s00"], [4, 0.4, "s04"]],
             "d": [[10, 0.38, "s10"], [12, 0.5, "s12"]] + gh((15, 0.26, -3))},
    "ghosts": {"a": gh((7, 0.2, 5)), "b": [], "c": gh((9, 0.18, -4), (15, 0.24, 6)), "d": gh((3, 0.2, 0))},
    "hats": [[i, 0.8, f"h{i:02d}", SHUFFLE if i % 2 else 0.0] for i in range(16)],
    "ride": {"a": [[0, 0.85, "ride0"]], "b": [[0, 0.85, "ride1"]], "c": [[0, 0.85, "ride2"]], "d": [[0, 0.85, "ride3"]]},
}
# every fill bar is its own edit (a 1-bar block always plays the first key of a cycled program, so fills are plain lists)
FILLS = {"F1": bar([0, 1, 2, "R"]), "F2": bar([0, 1, "S", 3]), "F3": bar([0, "rev1", 2, 3]), "F4": bar([0, 1, 10, "R"]) + gh((5, 0.22, 4)),
         "F5": bar([4, 5, 2, "S"]), "F6": bar([8, 9, "rev2", "R"]), "F7": bar([0, None, 2, "R"]), "F8": bar([12, 13, "S", "rev3"]),
         "F9": bar([0, 1, None, "S"]), "F10": bar([4, 1, 2, "R"]) + gh((2, 0.2, -3)), "F11": bar([0, 9, "rev10", 15]),
         "F12": bar([12, 1, "S", None]), "F13": bar([0, 5, "R", "R"]),
         "PU1": gh((8, 0.22, 4), (10, 0.26, -2), (12, 0.3, 0), (13, 0.34, 3)) + [[14, 0.5, "s04"], [15, 0.6, "s04"]],     # quiet pickups, no roll-up
         "PU2": [[0, 0.45, "s00"]] + gh((6, 0.22, 5), (11, 0.26, 0), (13, 0.3, -3)) + [[15, 0.55, "s12"]]}
PROGRAMS |= FILLS


def blk(name, loop, bars, parts=(), drums=(), **kw):
    return {"name": name, "loop": loop, "bars": bars, "parts": list(parts), "drums": list(drums), **kw}


def groove(name, loop, parts, breaks, fills):
    out = []
    for k, (brk, fill) in enumerate(zip(breaks, fills)):
        brk = [brk] if isinstance(brk, str) else list(brk)
        out += [blk(name + (f" {k + 1}" if len(fills) > 1 else ""), loop, 7, parts, brk), blk(f"{name}: fill {fill}", loop, 1, parts, [fill])]
    return out


PHRASE = ["lead"]                    # the opening phrase (its 'ooh' double, phrase_vox, is a layer of the lead and follows it)
ARR = ([blk("Opening phrase", "A", 8, PHRASE),
        blk("Pads arrive", "A", 8, PHRASE + ["pad", "vox"]),
        blk("Fragments", "A", 8, PHRASE + ["pad", "vox"], ["frag", "hats", "ghosts"]),
        blk("Layers gather", "A", 7, PHRASE + ["pad", "vox", "bass2"], ["half", "hats"]),
        blk("Layers gather: pickup", "A", 1, PHRASE + ["pad", "vox", "bass2"], ["half", "PU1", "hats"])]
       + groove("The break emerges", "A", PHRASE + ["pad", "bass"], ["straight", "soul"], ["F1", "F2"])
       + groove("Groove", "V", ["pad", "bass", "comp", "vox"], ["roller", ["straight", "ride"]], ["F3", "F4"])
       + groove("Groove: edits", "V", ["pad", "bass", "comp"], ["soul", "roller"], ["F5", "F6"])
       + [blk("Breakdown: the phrase returns", "A", 8, PHRASE + ["pad"]),
          blk("Breakdown: fragments", "A", 7, PHRASE + ["pad", "vox", "bass2"], ["frag", "hats", "ghosts"]),
          blk("Breakdown: pickup", "A", 1, PHRASE + ["pad", "vox", "bass2"], ["PU2", "hats"])]
       + groove("Second groove: the phrase over the break", "A", PHRASE + ["pad", "bass", "comp", "vox"], ["soul", ["roller", "ride"]], ["F7", "F8"])
       + groove("Bridge groove", "B", ["pad", "bass", "comp", "vox"], ["roller", ["soul", "ride"]], ["F9", "F10"])
       + groove("Last statement", "A", PHRASE + ["pad", "bass", "comp"], ["straight", "soul"], ["F11", "F12"])
       + groove("Outro: the phrase fades", "A", PHRASE + ["pad"], [["straight", "ride"]], ["F13"])
       + [blk("DJ outro", "A", 4, [], ["straight", "ride"]), blk("DJ outro: last bars", "A", 4, [], ["straight", "hats"])])
REVEAL = 33
SONG = ROOT / "songs" / "jungle162" / "jungle162-757371520.am.json"

SPEC = {
    "title": "Velvet Static", "song": SONG, "genre": "atmospheric-jungle-95", "rebuild": "bountiful/jungle_soul.py",
    "composer": LT.B.COMPOSER_CREDIT, "artist": LT.B.ARTIST, "album": "", "year": 2026,
    "blurb": ("Soulful early-90s UK atmospheric jungle at 162 bpm: a tape-worn Rhodes phrase and a wordless 'ooh' open alone, lush pads "
              "and slow jazz chords (F minor: Fm9 - Fsus4 - Bbm9 - Db6/9) join, filtered fragments of our own Amen-style break, shuffled "
              "hats and ghost snares gather, and the break and a deep rolling sub emerge with no riser or drop. The opening phrase "
              "returns in the breakdown, over the second groove and in the outro."),
    "overrides": {"bpm": BPM, "swing": 0.5, "drums": "grid", "grid": PROGRAMS, "arrangement": ARR, "drum_cycle_per_block": True, "loop_continuous": True,
                  "harmony": {"rhythm": 1, "dominant": "modal", "tonic_major": "7sus4",
                              "colors": {"m": "m9", "": "maj7", "m7": "m9", "7": "7sus4", "maj7": "maj9", "6": "6/9"}},
                  "melody": {"modal": True, "register": [62, 80], "max_leap": 7, "max_notes_per_bar": 4, "articulation": "legato", "humanize_ms": 9, "velocity": [0.48, 0.8]},
                  "bass": {"style": "pattern", "register": [29, 46],
                           "pattern": [[0, "R", 1.4, 1.0], [6, "R", 0.3, 0.72], [8, "5", 0.6, 0.85], [11, "O", 0.25, 0.7], [14, "R", 0.4, 0.8]]},
                  "bass2": {"style": "pattern", "register": [29, 46], "pattern": [[0, "R", 3.6, 0.85]]},
                  "comp": {"steps": [0, 7], "low": 53, "high": 72, "top": 70, "notes": 4, "gate": 2.2, "strum_ms": 22, "humanize_ms": 9, "vel": 0.5, "accent": 0.58},
                  "vox": {"steps": [0], "low": 60, "high": 77, "top": 72, "notes": 2, "gate": 3.8, "vel": 0.5, "accent": 0.5},
                  "pad": {"low": 48, "high": 77, "top": 72, "notes": 5, "vel": 0.5}},
    "kit_def": kit(),
    "layers": [("lead", "phrase_vox"), ("bass", "bass_mid")],
    "sends": {"hall": {"type": "reverb", "seconds": 4.0, "predelay": 0.04, "damp": 0.55},
              "echo": {"type": "delay", "time_beats": 0.75, "feedback": 0.38, "taps": 6, "tone": 2400}},
    "voices": {
        "lead": ({"zyn": "Rhodes/0041-Soft Rhodes.xiz"}, "Soft Rhodes (ZynAddSubFX - Rhodes), the opening phrase, tape-worn",
                 dict(hp=140, lp=5500, wow={"depth_ms": 0.6, "rate": 0.5, "flutter_ms": 0.05}, tape={"drive": 1.4, "hf_db": -3.0, "hiss_db": -60},
                      sends={"hall": 0.5, "echo": 0.22}, gain_db=-4.0)),
        "phrase_vox": ({"zyn": "ChoirAndVoice/0004-Voice OOH.xiz"}, "Voice OOH (ZynAddSubFX - ChoirAndVoice), the phrase's wordless double",
                       dict(hp=250, lp=4500, wow={"depth_ms": 0.8, "rate": 0.45, "flutter_ms": 0.05}, width=0.9, sends={"hall": 0.7}, gain_db=-14.0)),
        "pad": ({"zyn": "Pads/0065-Soft Pad.xiz"}, "Soft Pad (ZynAddSubFX - Pads), lush sustained chords",
                dict(hp=140, width=1.0, eq=[["highshelf", 6000, 1.5]], sends={"hall": 0.5}, gain_db=-8.0)),
        "vox": ({"zyn": "ChoirAndVoice/0116-Far Space Voice.xiz"}, "Far Space Voice (ZynAddSubFX - ChoirAndVoice), distant",
                dict(hp=300, lp=6000, width=0.9, sends={"hall": 0.65}, gain_db=-14.0)),
        "comp": ({"zyn": "Rhodes/0008-Synth Rhodes1.xiz"}, "Synth Rhodes1 (ZynAddSubFX - Rhodes), slow jazz chords",
                 dict(hp=160, crush={"bits": 12, "rate": 26040, "mix": 0.3}, width=1.0, sends={"hall": 0.3, "echo": 0.1}, gain_db=-8.0)),
        "bass": ({"zyn": "Bass/0003-Bass 3 _analog_.xiz"}, "Bass 3 analog (ZynAddSubFX - Bass), the rolling sub",
                 dict(hp=25, lp=190, mono=True, duck={"depth": 0.3, "release": 0.09}, gain_db=-4.0)),
        "bass_mid": ({"zyn": "Bass/0001-Bass 1.xiz"}, "Bass 1 (ZynAddSubFX - Bass), a touch of upper bass",
                     dict(hp=180, lp=1300, mono=True, duck={"depth": 0.25, "release": 0.09}, gain_db=-16.0)),
        "bass2": ({"zyn": "Bass/0003-Bass 3 _analog_.xiz"}, "Bass 3 analog (ZynAddSubFX - Bass), long sub notes",
                  dict(hp=25, lp=180, mono=True, gain_db=-4.0)),
    },
    "targets": {"bass": -2.0, "bass_mid": -15.0, "pad": -12.0, "comp": -13.0, "lead": -8.0, "phrase_vox": -17.0, "vox": -19.0},
    "level_ref": "break",
    "test_bars": (97, 104),
    "automation": [{"type": "lowpass", "tracks": ["break", "hats", "reverse", "ride"], "points": [[17, 650], [25, 600], [27, 900], [29, 1500], [31, 3000], [32, 5000], [REVEAL, 18000]]},
                   {"type": "lowpass", "tracks": ["pad"], "points": [[9, 900], [17, 2500], [REVEAL, 7000]]},
                   {"type": "lowpass", "tracks": ["break", "hats"], "points": [[89, 700], [93, 1300], [96, 3500], [97, 18000]]},
                   {"type": "gain", "tracks": ["bass2"], "points": [[25, -12], [29, -6], [REVEAL, 0]]},
                   {"type": "gain", "tracks": ["lead", "phrase_vox"], "points": [[1, -5.0], [9, -3.0], [17, -1.5], [25, 0.0]]},   # the opening, intimate
                   {"type": "gain", "tracks": ["lead", "phrase_vox", "pad"], "points": [[145, 0], [153, -14]]}],
    "mmp_drums": False, "kick_gain": None, "drum_stems": {},
}
SECTIONS = [(1, 8, "Opening phrase"), (9, 16, "Pads arrive"), (17, 24, "Fragments"), (25, 32, "Layers gather"), (33, 48, "The break emerges"),
            (49, 64, "Groove"), (65, 80, "Groove: edits"), (81, 88, "Breakdown: the phrase returns"), (89, 96, "Breakdown: fragments"),
            (97, 112, "Second groove (phrase)"), (113, 128, "Bridge groove"), (129, 144, "Last statement"), (145, 152, "Outro: the phrase fades"),
            (153, 160, "DJ outro")]


def validate():
    import pyloudnorm as pyln
    import json
    sys.path.insert(0, str(LT.B.ENGINE / "studio"))
    from render_midi import read_midi
    track = ROOT / "tracks" / "velvet-static"
    notes, bpm, _ = read_midi(track / "velvet-static.mid")
    beat = 60 / bpm
    bar_of = lambda t: int((t + 0.01) / beat // 4) + 1            # 10 ms tolerance: humanized hits may land just before a barline
    res = []
    total = max(bar_of(n["start"]) for n in notes)
    res.append(("length", total == 160, f"{total} bars at {bpm:.0f} bpm, {total * 4 * beat:.0f} s"))
    drums = [n for n in notes if n["track"] == "drums"]
    first_drum = min(bar_of(n["start"]) for n in drums)
    res.append(("it begins with the phrase alone; drums only from bar 17", first_drum == 17 and not any(n["track"] not in ("lead", "phrase_vox") and bar_of(n["start"]) <= 8 for n in notes), f"first drum bar {first_drum}"))
    inv = {v: k for k, v in NOTES.items()}
    per_bar: dict[int, list] = {}
    for n in drums:
        per_bar.setdefault(bar_of(n["start"]), []).append((round((n["start"] / beat) % 4 * 4, 2), inv.get(n["pitch"], n["pitch"])))
    full = lambda b: sum(1 for _, s in per_bar.get(b, []) if s[0] == "s")
    res.append(("bars 17-32: only fragments, hats and ghosts (no full break)", all(full(b) < 12 for b in range(17, 33)), f"max {max(full(b) for b in range(17, 33))} break slices per bar"))
    res.append(("the full break is revealed at bar 33", full(33) >= 14, f"{full(33)} slices in bar 33"))
    sigs = {b: tuple(sorted(v)) for b, v in per_bar.items()}
    fills = [b for b in range(40, 153, 8) if b in sigs]
    res.append(("every fill bar is its own edit", len({sigs[b] for b in fills}) == len(fills), f"{len({sigs[b] for b in fills})} distinct of {len(fills)}"))
    lead = {}
    for n in notes:
        if n["track"] == "lead":
            lead.setdefault(bar_of(n["start"]), []).append(n["pitch"])
    same = lambda a, b: all(lead.get(a + k) == lead.get(b + k) for k in range(8))
    returns = [b for b in (33, 81, 97, 129, 145) if same(1, b)]
    res.append(("the opening phrase returns later (same notes)", len(returns) >= 4, f"bars {', '.join(map(str, returns))} repeat bars 1-8"))
    harm = [n for n in notes if n["track"] in ("pad", "comp")]
    hit = tot = 0
    for n in (n for n in notes if n["track"] in ("bass", "bass2")):
        pcs = {h["pitch"] % 12 for h in harm if h["start"] <= n["start"] + 0.01 < h["end"]}
        if pcs:
            tot += 1
            hit += (n["pitch"] % 12) in pcs
    res.append(("the sub follows the harmony", tot and hit / tot >= 0.9, f"{hit}/{tot} bass notes are chord tones"))
    info = json.loads((track / "exports" / "render_info.json").read_text())
    stems = {p.stem: sf.read(str(p))[0].mean(1) / info["stem_scale"] for p in (track / "stems").glob("*.wav")}
    master, _ = sf.read(str(track / "exports" / "velvet-static.wav"))
    meter = pyln.Meter(SR)

    def lvl(x):
        k = len(x) // 2048
        r = np.sqrt((x[:k * 2048].reshape(k, 2048) ** 2).mean(1))
        return 20 * np.log10(np.sqrt((r[r > r.max() * 0.03] ** 2).mean()) + 1e-12) if r.max() > 1e-6 else -120

    def seg(a, b):
        return int(((a - 1) * 4) * beat * SR), int(b * 4 * beat * SR)

    rows = []
    for a, b, name in SECTIONS:
        i0, i1 = seg(a, b)
        rows.append((a, b, name, round(meter.integrated_loudness(master[i0:i1]), 1), {s: round(lvl(x[i0:i1]), 0) for s, x in stems.items()}))
    lufs = [r[3] for r in rows[:5]]
    res.append(("the intro builds gradually (loudness rises each 8 bars to the reveal)", all(b > a for a, b in zip(lufs, lufs[1:])),
                " -> ".join(f"{v}" for v in lufs) + " LUFS"))
    per = [meter.integrated_loudness(master[slice(*seg(b, b))]) for b in range(25, 41)]
    jump = max(b - a for a, b in zip(per, per[1:]))
    res.append(("no sudden oversized drop at the reveal (largest bar-to-bar loudness step, bars 25-40)", jump < 4.0, f"+{jump:.1f} LU"))
    pre = meter.integrated_loudness(master[slice(*seg(29, 32))])
    post = meter.integrated_loudness(master[slice(*seg(33, 36))])
    res.append(("the reveal lifts but does not explode (bars 29-32 vs 33-36)", 1.0 < post - pre < 6.5, f"+{post - pre:.1f} LU"))
    a_ = info["analysis"]
    res.append(("master: no clipping, true peak below -0.5 dBTP", a_["clipped_samples"] == 0 and a_["true_peak_dbtp_approx"] < -0.5,
                f"{a_['integrated_lufs']} LUFS, TP {a_['true_peak_dbtp_approx']}"))
    res.append(("low end centred", a_["correlation_below_120hz"] > 0.95, f"{a_['correlation_below_120hz']}"))
    lines = ["# Validation: Velvet Static", "", f"**{sum(bool(r[1]) for r in res)}/{len(res)} checks pass**", "", "| check | result | detail |", "|---|---|---|"]
    lines += [f"| {n} | {'ok' if ok else '**FAIL**'} | {d} |" for n, ok, d in res]
    order = [s for s in ("lead", "phrase_vox", "pad", "vox", "comp", "bass", "bass2", "bass_mid", "break", "hats", "ride", "reverse") if s in stems]
    lines += ["", "| bars | section | LUFS | " + " | ".join(order) + " |", "|---|---|---|" + "---|" * len(order)]
    lines += [f"| {a}-{b} | {name} | {l} | " + " | ".join("–" if v.get(s, -120) < -60 else f"{v[s]:.0f}" for s in order) + " |" for a, b, name, l, v in rows]
    lines += ["", f"Master: {a_['integrated_lufs']} LUFS, true peak {a_['true_peak_dbtp_approx']} dBTP, correlation {a_['correlation_full']}, "
              "spectrum " + ", ".join(f"{k} {v:.1f}" for k, v in a_["spectrum_share_db"].items())]
    (track / "validation.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    if "--validate" in sys.argv:
        validate()
    else:
        build_samples()
        LT.make(SPEC, log=lambda m: print(m, flush=True))
        validate()
