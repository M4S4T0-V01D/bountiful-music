#!/usr/bin/env python3
"""'Moss Radio': a lo-fi hip-hop single by M4S4T0, 80 bpm in F minor, 57 bars (~2:55). The MIDI is composed here, not
generated: a voice-led jazz loop Dbmaj9 - C7b9 - Fm9 - Ebm9 Ab13 and a bridge Bbm9 - Eb13 - Abmaj9 - Dbmaj9 - Gm7b5 - C7b9 -
Fm9 - C7sus C7b9, a written jazz-guitar theme with an answer phrase, a bridge melody the flute takes on its second pass, and
an upright bass line with chromatic approach notes into every chord. Bountiful lays the swung drum grid and its mix around it.

Sound: GeneralUser GS through LMMS sf2player (Chorused Tine EP, Jazz Guitar, Flute, Acoustic Bass, Warm Pad), a sine sub
under the upright, a dusty boom-bap kit (late snare + filtered clap, brushes, swung 16th hats), sparse vinyl crackle, tape.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python -I bountiful/moss_radio.py              # build + checks
    ~/Documents/Projects/intelligent-jungle/.venv/bin/python -I bountiful/moss_radio.py --validate   # checks only
"""
from __future__ import annotations

import copy
import itertools
import json
import shutil
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import album_mezzanine_v2 as A2  # noqa: E402
import jungle174 as J  # noqa: E402
import lmms_tracks as LT  # noqa: E402

import mido  # noqa: E402
import numpy as np  # noqa: E402

ROOT = A2.ROOT
TITLE, SLUG, BPM, SWING = "Moss Radio", "moss-radio", 80, 0.58
SONG = ROOT / "songs" / "lofi-downtempo" / "lofi-downtempo-1346770832.am.json"   # only for the drum grid's bar count
SF2 = ROOT / "samples" / "sf2" / "GeneralUser-GS.sf2"
SF2_SRC = ROOT.parent / "gielinor-lofi" / "assets" / "sf2"
DM, AC, MP = A2.dm, (lambda p: A2.dm(f"acoustic/{p}")), (lambda p: A2.dm(f"misc_perc/{p}"))
CRACKLE = ROOT / "samples" / "lofi" / "vinyl_crackle_4bar_80.wav"
blk = A2.blk

# ------------------------------------------------------------------ harmony: (root pc, the four voiced tones as intervals)
CH = {"Dbmaj9": (1, [4, 7, 11, 14]), "C7b9": (0, [4, 7, 10, 13]), "Fm9": (5, [3, 7, 10, 14]), "Ebm9": (3, [3, 7, 10, 14]),
      "Ab13": (8, [4, 10, 14, 21]), "Bbm9": (10, [3, 7, 10, 14]), "Eb13": (3, [4, 10, 14, 21]), "Abmaj9": (8, [4, 7, 11, 14]),
      "Gm7b5": (7, [0, 3, 6, 10]), "C7sus": (0, [5, 7, 10, 14])}
LOOP_A = [["Dbmaj9"], ["C7b9"], ["Fm9"], ["Ebm9", "Ab13"]]
LOOP_B = [["Bbm9"], ["Eb13"], ["Abmaj9"], ["Dbmaj9"], ["Gm7b5"], ["C7b9"], ["Fm9"], ["C7sus", "C7b9"]]
SCALE = {5, 7, 8, 10, 0, 1, 3}                         # F natural minor

# ------------------------------------------------------------------ written parts: per bar [step16, pitch, length16, vel]
THEME = [[[2, 72, 2, .62], [4, 75, 2, .68], [6, 77, 5, .78], [12, 75, 2, .60], [14, 72, 2, .58]],
         [[0, 73, 6, .75], [8, 70, 2, .60], [10, 68, 2, .60], [12, 67, 4, .66]],
         [[2, 68, 2, .60], [4, 72, 2, .66], [6, 67, 10, .72]],
         [[4, 66, 2, .58], [6, 70, 3, .66], [10, 68, 2, .58], [12, 72, 4, .70]],
         [[0, 77, 3, .76], [3, 75, 1, .55], [4, 72, 4, .68], [10, 75, 2, .60], [12, 80, 4, .78]],      # the answer
         [[0, 79, 4, .74], [4, 76, 2, .62], [6, 73, 2, .62], [8, 70, 4, .66], [14, 72, 2, .58]],
         [[0, 68, 4, .66], [4, 67, 2, .60], [6, 65, 10, .70]],
         [[6, 66, 2, .56], [8, 70, 2, .60], [10, 73, 2, .64], [12, 72, 4, .66]]]
BRIDGE = [[[0, 73, 3, .72], [3, 72, 1, .55], [4, 68, 4, .66], [10, 65, 2, .58], [12, 68, 4, .66]],
          [[0, 67, 6, .70], [8, 72, 2, .62], [10, 70, 2, .60], [12, 65, 4, .64]],
          [[0, 67, 3, .66], [4, 70, 2, .62], [6, 72, 2, .66], [8, 75, 8, .76]],
          [[0, 77, 2, .74], [2, 75, 2, .64], [4, 72, 4, .68], [10, 72, 2, .58], [12, 77, 4, .70]],
          [[0, 77, 4, .72], [4, 73, 2, .64], [6, 70, 2, .62], [8, 67, 6, .68]],
          [[0, 68, 2, .64], [2, 67, 2, .60], [4, 64, 4, .68], [8, 70, 4, .64], [12, 73, 4, .70]],
          [[0, 72, 12, .72]],
          [[8, 70, 2, .60], [10, 67, 2, .60], [12, 64, 4, .64]]]
BASS_A = [[[[0, 37, 6, .90], [7, 44, 2, .62], [10, 41, 3, .72], [14, 37, 2, .60]],
           [[0, 36, 6, .90], [7, 43, 2, .62], [10, 46, 2, .66], [12, 43, 2, .62], [14, 40, 2, .60]],
           [[0, 41, 6, .90], [7, 48, 2, .62], [10, 41, 2, .66], [12, 44, 2, .64], [14, 43, 2, .60]],
           [[0, 39, 4, .88], [5, 46, 2, .60], [8, 44, 4, .84], [12, 39, 2, .62], [14, 38, 2, .62]]],
          [[[0, 37, 3, .90], [3, 49, 1, .50], [4, 44, 3, .70], [8, 41, 2, .66], [10, 37, 4, .72], [14, 35, 2, .60]],
           [[0, 36, 4, .90], [6, 43, 2, .62], [8, 46, 3, .68], [12, 43, 2, .62], [14, 40, 2, .62]],
           [[0, 41, 4, .90], [4, 41, 2, .50], [7, 48, 2, .62], [10, 44, 3, .68], [14, 40, 2, .60]],
           [[0, 39, 6, .88], [7, 46, 1, .55], [8, 44, 6, .84], [14, 38, 2, .62]]]]
BASS_B = [[[0, 34, 6, .90], [7, 41, 2, .62], [10, 44, 2, .64], [14, 38, 2, .60]],
          [[0, 39, 6, .90], [7, 46, 2, .62], [10, 43, 2, .64], [14, 45, 2, .60]],
          [[0, 44, 6, .90], [7, 39, 2, .62], [10, 43, 2, .64], [12, 44, 2, .60], [14, 36, 2, .60]],
          [[0, 37, 6, .90], [7, 44, 2, .62], [10, 41, 2, .64], [14, 42, 2, .60]],
          [[0, 43, 6, .90], [7, 37, 2, .60], [10, 41, 2, .64], [14, 37, 2, .60]],
          [[0, 36, 6, .90], [7, 43, 2, .62], [10, 40, 2, .64], [12, 46, 2, .62], [14, 40, 2, .60]],
          [[0, 41, 6, .90], [7, 36, 2, .60], [10, 41, 2, .64], [14, 43, 2, .60]],
          [[0, 36, 4, .88], [4, 36, 2, .55], [8, 36, 4, .82], [12, 40, 2, .62], [14, 38, 2, .62]]]

# ------------------------------------------------------------------ arrangement: (name, bars, loop, parts)
#   keys: "hold" (whole chords) or "comp" (on 1, a push on the and-of-3); melody parts name what they play
SECTIONS = [("Intro", 4, "A", {"keys": "hold"}),
            ("Beat", 8, "A", {"keys": "comp", "bass": 1}),
            ("Theme", 8, "A", {"keys": "comp", "bass": 1, "guitar": THEME}),
            ("Bridge", 8, "B", {"keys": "comp", "bass": 1, "guitar": BRIDGE, "pad": 1}),
            ("Break", 4, "A", {"keys": "hold", "sub_hold": 1, "flute": [[], [], [[s, p + 12, n, v] for s, p, n, v in THEME[2]],
                                                                        [[s, p + 12, n, v] for s, p, n, v in THEME[3]]]}),
            ("Theme again", 8, "A", {"keys": "comp", "bass": 1, "guitar": THEME, "pad": 1,
                                     "flute": [[]] * 4 + [[[s, p + 12, n, v * .85] for s, p, n, v in b] for b in THEME[4:]]}),
            ("Bridge, flute", 8, "B", {"keys": "comp", "bass": 1, "flute": BRIDGE, "pad": 1}),
            ("Outro", 8, "A", {"keys": "comp", "bass": 1, "guitar": [[[s, p, n, v * .85] for s, p, n, v in b] for b in THEME[:4]]}),
            ("Last chord", 1, "END", {"keys": "hold", "end": 1})]
ALL = sum(s[1] for s in SECTIONS)


def start_bar(name):
    return 1 + sum(s[1] for s in SECTIONS[:[s[0] for s in SECTIONS].index(name)])


def chords_of(loop, i):
    return ["Fm9"] if loop == "END" else (LOOP_A if loop == "A" else LOOP_B)[i % (4 if loop == "A" else 8)]


def voice(name, prev, lo=50, hi=70):
    """four tones of the chord in [lo, hi], nearest to the previous voicing (smooth inner-voice motion)"""
    root, iv = CH[name]
    cands = [[p for p in range(lo, hi + 1) if p % 12 == (root + i) % 12] for i in iv]
    best, score = None, 1e9
    for combo in itertools.product(*cands):
        v = sorted(combo)
        if len(set(v)) < 4 or v[-1] - v[0] > 14:
            continue
        s = sum(abs(a - b) for a, b in zip(v, prev)) + 0.25 * abs(np.mean(v) - 60) + (6 if v[1] - v[0] <= 2 and v[0] < 55 else 0)
        if s < score:
            best, score = v, s
    return best


# ------------------------------------------------------------------ the MIDI
def compose():
    """{track: [(start_beat, end_beat, pitch, vel)]} and the chord per half bar (for the checks)"""
    rng = np.random.default_rng(80)
    beat_ms = 60000 / BPM
    out = {k: [] for k in ("keys", "guitar", "flute", "bass", "sub", "pad")}
    chart = []

    def at(bar, step, jitter_ms=0.0):
        sw = (SWING - 0.5) * 0.5 if int(round(step)) % 2 else 0.0
        return (bar - 1) * 4 + step / 4 + sw + (rng.normal(0, jitter_ms) / beat_ms if jitter_ms else 0)

    def put(track, bar, step, pitch, length, vel, jitter=8, gap=0.04, delay_ms=0.0):
        s = max(0.0, at(bar, step, jitter) + delay_ms / beat_ms)
        out[track].append((s, max(s + 0.05, (bar - 1) * 4 + (step + length) / 4 - gap), pitch,
                           float(np.clip(vel + rng.normal(0, 0.03), 0.2, 1.0))))

    prev = [53, 56, 60, 63]
    bar = 1
    for name, bars, loop, parts in SECTIONS:
        for i in range(bars):
            names = chords_of(loop, i)
            half = 16 // len(names)
            for k, cn in enumerate(names):
                v = voice(cn, prev)
                prev = v
                chart.append((bar, k * half, cn))
                st, ln = k * half, half
                if parts.get("keys") == "hold":
                    hits = [(st, ln + (2 if parts.get("end") else 0), 0.5 if name == "Intro" else 0.55)]
                elif len(names) == 2:
                    hits = [(st, ln - 1, 0.66 - 0.04 * k)]
                else:
                    hits = [(0, 9, 0.68), (10, 6, 0.52)] if i % 2 == 0 else [(0, 13, 0.68), (14, 2, 0.45)]
                for hs, hl, hv in hits:
                    for j, p in enumerate(v):                          # rolled up from the bottom, like a hand
                        put("keys", bar, hs, p, hl, hv - 0.03 * (j == 0), jitter=6, delay_ms=14 * j)
                if parts.get("pad"):
                    for p in v[1:]:
                        put("pad", bar, st, p + 12, ln, 0.42, jitter=0, gap=0.0)
                if parts.get("sub_hold"):
                    r = 36 + (CH[cn][0] - 36) % 12
                    put("sub", bar, st, r, ln, 0.7, jitter=0)
                if parts.get("end"):
                    put("bass", bar, 0, 29, 14, 0.8, jitter=0)
                    put("sub", bar, 0, 41, 14, 0.75, jitter=0)
                    put("guitar", bar, 2, 72, 10, 0.55, jitter=0)
            if parts.get("bass"):
                line = (BASS_A[(i // 4) % 2] if loop == "A" else BASS_B)[i % (4 if loop == "A" else 8)]
                for s, p, n, vv in line:
                    put("bass", bar, s, p, n, vv, jitter=5, gap=0.02)
                    if n >= 2:
                        put("sub", bar, s, p, n, vv, jitter=0, gap=0.02)
            for part in ("guitar", "flute"):
                mel = parts.get(part)
                if mel and i < len(mel) and isinstance(mel, list):
                    src = mel[i % len(mel)]
                    for s, p, n, vv in src:
                        put(part, bar, s, p, n, vv, jitter=11 if part == "guitar" else 8)
            bar += 1
    return out, chart


def write_parts(mid: Path):
    """swap every pitched track of Bountiful's MIDI for the composed ones (the tempo track and the drum grid stay)"""
    parts, _ = compose()
    m = mido.MidiFile(str(mid))
    tpb = m.ticks_per_beat
    keep = [t for t in m.tracks if not any(x.type == "note_on" for x in t)
            or any(x.type == "track_name" and x.name == "drums" for x in t)]
    m.tracks = keep
    for ch, (name, notes) in enumerate(parts.items()):
        ev = []
        for s, e, p, v in sorted(notes):
            ev += [(int(round(s * tpb)), 1, p, int(round(v * 127))), (int(round(e * tpb)), 0, p, 0)]
        ev.sort(key=lambda x: (x[0], x[1]))
        tr = mido.MidiTrack([mido.MetaMessage("track_name", name=name, time=0)])
        held, last = {}, 0
        for t, on, p, v in ev:
            if on and held.get(p):                                     # a re-hit of a ringing note: end it first
                tr.append(mido.Message("note_off", channel=ch, note=p, velocity=0, time=t - last)); last = t
                held[p] -= 1
            elif not on and not held.get(p):
                continue
            tr.append(mido.Message("note_on" if on else "note_off", channel=ch, note=p, velocity=v if on else 0, time=t - last))
            last = t
            held[p] = held.get(p, 0) + (1 if on else -1)
        tr.append(mido.MetaMessage("end_of_track", time=0))
        m.tracks.append(tr)
    m.save(str(mid))


def produce_then_write(song, g, title, out, seed=1, log=print):
    _produce(song, g, title=title, out=out, seed=seed, log=log)
    write_parts(out / f"{SLUG}.mid")
    inst = out / "instruments.toml"
    cfg = tomllib.loads(inst.read_text())
    cfg["tracks"] = {k: v for k, v in cfg["tracks"].items() if k == "drums"}
    inst.write_text(LT.to_toml(cfg))
    lines = ["  " + f"{n} ({b} bars): " + (" | ".join(" ".join(c) for c in (LOOP_A if l == "A" else LOOP_B if l == "B" else [["Fm9"]])))
             for n, b, l, _ in SECTIONS]
    (out / "notes.txt").write_text(f"{TITLE} — lo-fi hip-hop, {BPM} bpm, F minor, {ALL} bars ({ALL * 4 * 60 / BPM / 60:.0f}:"
                                   f"{ALL * 240 / BPM % 60:04.1f})\ncomposition: written in bountiful/moss_radio.py (chords, "
                                   "voicings, theme, bridge melody, bass); drums: Bountiful grid\n\n" + "\n".join(lines) + "\n")


_produce = LT.B.produce
LT.B.produce = produce_then_write

# ------------------------------------------------------------------ drums: boom-bap, snare laid back, swung 16th hats
LATE = 16
HATS = {"a": [[s, .5 if s % 4 == 0 else .36 if s % 2 == 0 else .22] for s in range(15)],
        "b": [[s, .5 if s % 4 == 0 else .36 if s % 2 == 0 else .2] for s in range(16) if s != 11],
        "c": [[s, .5 if s % 4 == 0 else .36 if s % 2 == 0 else .22] for s in range(16)],
        "d": [[s, .5 if s % 4 == 0 else .36 if s % 2 == 0 else .2] for s in range(14)] + [[14, .42, "open"]]}
GRID = {
    "kick": {"a": [[0, .95], [7, .55], [10, .85]], "b": [[0, .95], [10, .85], [13, .5]],
             "c": [[0, .95], [3, .45], [7, .55], [10, .8]], "d": [[0, .95], [8, .6], [10, .8], [15, .45]]},
    "snare": {"a": [[4, .9, "snare", LATE], [12, .92, "snare", LATE + 4]],
              "b": [[4, .9, "snare", LATE], [12, .92, "snare", LATE + 2], [15, .3, "snare", LATE]]},
    "clap": {"a": [[4, .6, "clap", LATE + 6], [12, .62, "clap", LATE + 10]]},
    "ghost": {"a": [[6, .3], [15, .26]], "b": [[9, .28], [13, .24]], "c": [[2, .24], [7, .3]], "d": [[9, .3], [11, .22], [14, .28]]},
    "hat": HATS,
    "rim": {"a": [[10, .34]], "b": [], "c": [[6, .3], [14, .28]], "d": []},
    "shaker": [[s, .26 if s % 2 else .16] for s in range(16)],
    "vinyl": {"a": [[0, .8, "swell"]], "b": [], "c": [], "d": []},
}
DRUMS = {"Intro": ["vinyl"], "Beat": ["vinyl", "kick", "snare", "clap", "ghost", "hat"],
         "Theme": ["vinyl", "kick", "snare", "clap", "ghost", "hat", "rim"],
         "Bridge": ["vinyl", "kick", "snare", "clap", "ghost", "hat", "rim", "shaker"],
         "Break": ["vinyl", "hat", "rim"], "Theme again": ["vinyl", "kick", "snare", "clap", "ghost", "hat", "rim"],
         "Bridge, flute": ["vinyl", "kick", "snare", "clap", "ghost", "hat", "rim", "shaker"],
         "Outro": ["vinyl", "kick", "snare", "clap", "hat"], "Last chord": ["vinyl"]}
ARR = [blk(n, "A", b, ["comp"], DRUMS[n], **({"crash": True} if n in ("Theme", "Bridge", "Theme again", "Bridge, flute") else {}),
           **({"fill": "drop"} if n in ("Bridge", "Theme again") else {})) for n, b, _, _ in SECTIONS]

KIT = A2.kit({"kick": (DM("r_n_b/old_kik"), "kick", None), "snare": (AC("jazzsnr"), "snare", None),
              "clap": (DM("r_n_b/clapfilt"), "snare", {"gain_db": -6}),
              "ghost": (AC("brush1"), "snare", {"gain_db": -4, "lp": 7000}), "hat": (DM("r_n_b/hat"), "hats", {"lp": 9000}),
              "open": (DM("r_n_b/hat_o"), "hats", {"gain_db": -5, "lp": 8000}),
              "rim": (MP("hollow_wood"), "perc", None), "shaker": (MP("mellow_shake"), "perc", None),
              "crash": (AC("ride3"), "hats", {"gain_db": -8, "lp": 7000}), "swell": (str(CRACKLE), "vinyl", {"detune_cents": 0})},
             {"kick": {"hp": 30, "mono": True, "drive": 1.3, "eq": [["peak", 60, 2.0, 1.0], ["peak", 350, -2.5, 1.2]],
                       "crush": {"bits": 12, "rate": 26040, "mix": 0.35}, "gain_db": -3.0},
              "snare": {"hp": 140, "lp": 8500, "drive": 1.2, "crush": {"bits": 12, "rate": 26040, "mix": 0.45},
                        "sends": {"room": 0.25}, "gain_db": 3.0},
              "hats": {"pan": 0.18, "hp": 250, "lp": 8500, "crush": {"bits": 12, "rate": 22050, "mix": 0.4}, "gain_db": 20.0},
              "perc": {"pan": -0.3, "crush": {"bits": 12, "rate": 26040, "mix": 0.3}, "sends": {"room": 0.25}, "gain_db": 14.0},
              "vinyl": {"hp": 500, "lp": 8000, "gain_db": 0.0}})


def gs(bank, patch, label, gain=3.0):
    return ({"plugin": "sf2player", "attrs": {"src": str(SF2), "bank": bank, "patch": patch, "gain": gain, "reverbOn": 0, "chorusOn": 0}},
            f"{label} (GeneralUser GS {bank}:{patch}, LMMS sf2player)")


SUB = copy.deepcopy(J.SUB)
SUB["layers"] = SUB["layers"][:1]
SUB["layers"][0]["preset"].update({"glide": 0.01, "sub_h2": 0.1, "body": 0.0, "pluck": 0.0, "drive": 1.1, "release": 0.1})
SUB.update({"hp": 28, "lp": 160, "mono": True, "duck": {"depth": 0.3, "release": 0.12}, "gain_db": -12.0})
DUSTY = J.SAMPLER(26040, 0.4)

SPEC = {
    "title": TITLE, "genre": "lofi-downtempo", "song": SONG, "album": "", "track": 0, "year": 2026, "seed": 7,
    "composer": LT.B.COMPOSER_CREDIT, "rebuild": "bountiful/moss_radio.py",
    "blurb": "Lo-fi hip-hop at 80 bpm in F minor, composed note by note: a voice-led Dbmaj9 - C7b9 - Fm9 - Ebm9 Ab13 loop on a "
             "chorused Tine EP, a jazz-guitar theme with an answer phrase, an eight-bar bridge the flute takes on its second pass, an "
             "upright bass walking into every chord over a sine sub, and a dusty boom-bap kit with a laid-back snare.",
    "overrides": {"bpm": BPM, "swing": SWING, "drums": "grid", "drum_humanize_ms": 8, "arrangement": ARR, "grid": GRID,
                  "master": {"tape": {"drive": 1.4, "bias": 0.07, "bump_db": 1.2, "hf_db": -2.0, "lp_hz": 14000, "hiss_db": -68,
                                      "wow_ms": 0.18}, "target_lufs": -14.0, "true_peak": -1.0}},
    "kit_def": KIT,
    "layers": [],
    "sends": {"echo": {"type": "delay", "time_beats": 0.75, "feedback": 0.35, "tone": 2200, "taps": 5}},
    "voices": {
        "keys": (*gs(8, 4, "Chorused Tine EP"),
                 dict(hp=90, lp=6500, eq=[["peak", 250, -1.5, 1.0], ["peak", 1200, 1.0, 0.8]], crush=DUSTY, drive=1.15,
                      wow={"depth_ms": 1.2, "rate": 0.6, "flutter_ms": 0.12}, duck={"depth": 0.18, "release": 0.18},
                      width=0.9, sends={"room": 0.22, "plate": 0.08}, gain_db=0.0)),
        "guitar": (*gs(0, 26, "Jazz Guitar"),
                   dict(hp=160, lp=7000, eq=[["peak", 2200, 1.5, 0.9]], crush=J.SAMPLER(26040, 0.3), pan=-0.15,
                        sends={"room": 0.25, "echo": 0.1}, gain_db=0.0)),
        "flute": (*gs(0, 73, "Flute"),
                  dict(hp=300, lp=7500, pan=0.2, wow={"depth_ms": 0.8, "rate": 0.5, "flutter_ms": 0.08},
                       sends={"plate": 0.3, "echo": 0.18}, gain_db=0.0)),
        "bass": (*gs(0, 32, "Acoustic Bass"),
                 dict(hp=35, lp=2500, mono=True, drive=1.2, eq=[["peak", 90, 1.5, 0.9], ["peak", 700, 1.5, 1.0]],
                      duck={"depth": 0.15, "release": 0.1}, gain_db=0.0)),
        "pad": (*gs(0, 89, "Warm Pad"),
                dict(hp=250, lp=3200, width=0.8, sends={"plate": 0.3}, gain_db=-6.0)),
    },
    "extra_tracks": {"sub": SUB},
    "level_ref": "kick",
    "targets": {"keys": -4.0, "guitar": -5.0, "flute": -8.0, "bass": -3.0, "sub": -9.0, "pad": -15.0},
    "test_bars": (start_bar("Theme again"), start_bar("Theme again") + 7),
    "automation": [
        {"type": "lowpass", "tracks": ["keys"], "points": [[1, 650], [4, 1300], [4.75, 2400], [5, 18000]]},   # the record, then the room
        {"type": "lowpass", "tracks": ["keys", "flute", "hats", "perc"],
         "points": [[start_bar("Break"), 18000], [start_bar("Break") + 0.01, 1700], [start_bar("Break") + 3.5, 2600],
                    [start_bar("Theme again"), 18000]]},
        {"type": "lowpass", "tracks": ["kick", "snare", "hats", "perc", "bass"], "points": [[start_bar("Outro") + 4, 18000], [ALL, 1200]]},
        {"type": "gain", "tracks": ["keys", "guitar", "bass", "sub", "kick", "snare", "hats", "perc", "vinyl"],
         "points": [[start_bar("Outro") + 4, 0], [ALL, -8], [ALL + 2, -40]]}],
    "mmp_drums": True,
    "lead_hi_follows_lead": False,
}


def setup():
    if not SF2.exists():                                   # the user's GeneralUser GS (free to use in music), copied once
        SF2.parent.mkdir(parents=True, exist_ok=True)
        for f in ("GeneralUser-GS.sf2", "LICENSE.txt"):
            shutil.copy2(SF2_SRC / f, SF2.parent / f)
    if CRACKLE.exists():
        return
    import soundfile as sf
    from engine import fx
    rng = np.random.default_rng(80)
    n = int(round(16 * 60 / BPM * fx.SR)) + fx.SR // 2
    clicks = (rng.random(n) < 7.0 / fx.SR) * rng.standard_normal(n) * rng.random(n) ** 3
    pops = (rng.random(n) < 0.4 / fx.SR) * rng.standard_normal(n) * 2.0
    x = fx.bp((clicks + pops).astype(np.float32), 900, 7000) * 3.0
    x += fx.lp(rng.standard_normal(n).astype(np.float32), 4000) * 0.02
    x[:200] *= np.linspace(0, 1, 200)
    x[-fx.SR // 2:] *= np.linspace(1, 0, fx.SR // 2)
    x[0] = max(abs(x).max(), 1e-3)                         # a click on the onset so the loader does not trim the start
    CRACKLE.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(CRACKLE), (x / abs(x).max() * 0.9).astype(np.float32), fx.SR)


# ------------------------------------------------------------------ checks
def validate():
    import soundfile as sf
    from render_midi import read_midi
    track = LT.B.DATA / "tracks" / SLUG
    an = json.loads((track / "exports" / "render_info.json").read_text())["analysis"]
    notes, bpm, _ = read_midi(track / f"{SLUG}.mid")
    bar_s = 4 * 60 / bpm
    res = []

    def check(name, ok, detail):
        res.append((name, bool(ok), detail))

    check("length 2:30-3:30", 150 <= an["duration_s"] <= 210, f"{an['duration_s']:.1f} s")
    check("loudness -14 LUFS (+-0.5)", abs(an["integrated_lufs"] + 14) <= 0.5, f"{an['integrated_lufs']} LUFS")
    check("true peak <= -1 dBTP", an["true_peak_dbtp_approx"] <= -0.95, f"{an['true_peak_dbtp_approx']} dBTP")
    check("no clipping", an["clipped_samples"] == 0, f"{an['clipped_samples']} samples")
    check("low end mono (corr <120 Hz > 0.95)", an["correlation_below_120hz"] > 0.95, f"{an['correlation_below_120hz']}")
    tracks = {n["track"] for n in notes}
    check("composed parts in the MIDI", {"keys", "guitar", "flute", "bass", "sub", "pad", "drums"} <= tracks, ", ".join(sorted(tracks)))
    drums = [n for n in notes if n["track"] == "drums"]
    intro = [n for n in drums if n["start"] < 4 * bar_s - 0.01 and n["pitch"] != A2.PR.GM["swell"]]
    check("intro: keys and crackle only", not intro, f"{len(intro)} drum hits in bars 1-4")
    _, chart = compose()
    beat = 60 / bpm

    def chord_at(t):
        b, s = int(t / bar_s) + 1, (t % bar_s) / beat * 4
        cur = None
        for cb, cs, cn in chart:
            if (cb, cs) <= (b, s + 0.5):
                cur = cn
        root, iv = CH[cur]
        return {root % 12} | {(root + i) % 12 for i in iv}
    mel = [n for n in notes if n["track"] in ("guitar", "flute")]
    bad = [n for n in mel if n["pitch"] % 12 not in chord_at(n["start"]) | SCALE]
    check("melody on chord tones or F minor", len(bad) <= 2, f"{len(bad)}/{len(mel)} outside")
    bass = [n for n in notes if n["track"] == "bass"]
    on_beat = [n for n in bass if ((n["start"] % bar_s) / beat) % 4 < 0.1]
    rootless = [n for n in on_beat if n["pitch"] % 12 != min(chord_at(n["start"] + 0.01), key=lambda p: 0) and
                n["pitch"] % 12 not in chord_at(n["start"] + 0.01)]
    check("bass on the downbeats is in the chord", not rootless, f"{len(rootless)}/{len(on_beat)} off")
    keys = sorted((n for n in notes if n["track"] == "keys"), key=lambda n: n["start"])
    snares = [n for n in drums if n["pitch"] == A2.PR.GM["snare"]]
    late = [((n["start"] % (beat / 4)) * 1000) for n in snares]
    check("snare sits behind the beat (10-40 ms)", late and 10 <= np.median(late) <= 40, f"median {np.median(late):.0f} ms")
    x, sr = sf.read(str(track / "exports" / f"{SLUG}.wav"), dtype="float32", always_2d=True)

    def rms(a, b):
        seg = x[int((a - 1) * bar_s * sr):int((b - 1) * bar_s * sr)].mean(1)
        return 10 * np.log10(np.mean(seg ** 2) + 1e-12)
    br, ta = rms(start_bar("Break"), start_bar("Theme again")), rms(start_bar("Theme again"), start_bar("Bridge, flute"))
    check("theme returns >= 2 dB over the break", ta - br >= 2.0, f"{ta - br:.1f} dB")
    check("keys present", len(keys) > 300, f"{len(keys)} key notes")
    n_ok = sum(ok for _, ok, _ in res)
    lines = [f"- {'PASS' if ok else 'FAIL'} {name}: {d}" for name, ok, d in res]
    print("\n".join(lines))
    print(f"{n_ok}/{len(res)} checks pass")
    (track / "validation.md").write_text(f"# {TITLE}: validation\n\n" + "\n".join(lines) + f"\n\n{n_ok}/{len(res)} checks pass\n")
    return n_ok == len(res)


if __name__ == "__main__":
    if "--validate" not in sys.argv:
        setup()
        LT.make(SPEC, log=lambda m: print(m, flush=True))
    validate()
