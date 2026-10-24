"""The songs of 'Put on the Pixel' (M4S4T0, composed by C-Lizzy), all in the family of Copper Bars (pixel_dnb.py): slow jazzy
drum & bass on chip sounds, each with its own key, tempo, drum machine (pixel_kits.py), beat, opening, arrangement and voices.

  1 Copper Bars       130  C# minor  NES kit, two-step                     (pixel_dnb.py)
  2 Raster Interrupt  134  C minor   Amiga 8-bit sampled break, chopped    SID lead, SID arps, SID pad
  3 Sine Scroller     126  E minor   C64 kit, half-time into two-step      square-to-sine lead, mystic bells
  4 Bitplane Blues    124  Ab major  soft NES kit, jazz ride, walking bass chip e-piano, vibrato lead
  5 Vector Balls      136  D# minor  Game Boy kit, steppers                Nescaline lead, triplet-32nd SID arps
  6 Greetings         128  F major   bright NES kit, liquid roller         Watsyn pulse lead, pulse-organ stabs
  7 Plasma            132  A minor   Amiga break, 6-bit 11 kHz, dark       chip vibrato lead, noisy pulses
  8 Last Frame        122  C# minor  the Copper Bars kit, half-time        Copper Bars' song, a new melody; toy piano
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import album_mezzanine_v2 as A2  # noqa: E402
import pixel_dnb as P  # noqa: E402
import pixel_kits as K  # noqa: E402
import producer as PR  # noqa: E402

ROOT = P.ROOT
KITS = ROOT / "samples" / "pixel"
ALBUM, ARTIST, COMPOSER, YEAR = "Put on the Pixel", A2.ARTIST, A2.COMPOSER, A2.YEAR
blk, zyn, xpf = A2.blk, A2.zyn, A2.xpf
SONG = lambda seed: ROOT / "songs" / "lofi-downtempo" / f"lofi-downtempo-{seed}.am.json"
JAZZ = {"rhythm": 1, "dominant": "keep", "colors": {"m": "m9", "": "maj9", "m7": "m9", "7": "9", "maj7": "maj9"}}
MASTER = {"tape": {"drive": 1.15, "bias": 0.02, "bump_db": 0.8, "hf_db": 0.0, "lp_hz": 18500, "hiss_db": -90, "wow_ms": 0.0},
          "glue": {"threshold": -15.0, "ratio": 2.0, "attack": 0.015, "release": 0.2}, "target_lufs": -10.0, "ceiling": -1.0, "clip": 2.0, "true_peak": -1.0}
CHIP = ["kick", "snare", "ghost", "hat", "open", "ride", "crash", "rim", "tom_hi", "tom_mid", "tom_lo"]
PR.GM.update({s: 52 + i for i, s in enumerate(K.AMIGA_SLICES)})      # break slices on notes 52-119, clear of the chip kit
PR.GM.update({"halfkick": PR.GM["kick"], "halfsnare": PR.GM["snare"], "halfghost": PR.GM["ghost"], "hat16": PR.GM["hat"]})   # lanes named for their pattern play the kit sound


def groove(name, loop, parts, drums, fills, extra=(), **kw):
    """8-bar phrases: 7 bars of groove and a fill bar (each fill its own edit)."""
    out = []
    for k, f in enumerate(fills):
        out += [blk(name + (f" {k + 1}" if len(fills) > 1 else ""), loop, 7, parts, drums, **(kw if k == 0 else {})),
                blk(f"{name}: fill {f}", loop, 1, parts, [f, *extra])]
    return out


def drum_kit(machine, slug, sounds, stems, **params):
    d = KITS / slug
    sounds_ = {s: (str(d / f"{s}.wav"), stem, {"detune_cents": 0}) for s, stem in sounds.items()}
    return {"machine": machine, "dir": d, "params": params, "def": A2.kit(sounds_, stems)}


def chip_stems(kick=-3.0, snare=-4.0, hats=-9.0, ride=-13.0, perc=-6.0):
    return {"kick": {"hp": 28, "mono": True, "drive": 1.4, "gain_db": kick}, "snare": {"hp": 120, "sends": {"room": 0.15}, "gain_db": snare},
            "hats": {"hp": 3000, "pan": 0.15, "sends": {"room": 0.1}, "gain_db": hats}, "ride": {"hp": 1500, "pan": -0.2, "sends": {"room": 0.15}, "gain_db": ride},
            "perc": {"hp": 60, "pan": -0.1, "sends": {"room": 0.2, "echo": 0.08}, "gain_db": perc}}


CHIP_STEM = {"kick": "kick", "snare": "snare", "ghost": "snare", "hat": "hats", "open": "hats", "ride": "ride", "crash": "ride",
             "rim": "perc", "tom_hi": "perc", "tom_mid": "perc", "tom_lo": "perc"}


def amiga_kit(slug, bpm, **params):
    sounds = {s: "break" for s in K.AMIGA_SLICES} | {"hat": "hats", "open": "hats", "ride": "ride", "crash": "ride"}
    stems = {"break": {"hp": 35, "eq": [["peak", 90, 2.0, 0.9], ["highshelf", 8000, -1.5]], "drive": 1.2, "sends": {"room": 0.1}, "gain_db": -2.0},
             "hats": {"hp": 3000, "pan": 0.15, "gain_db": -12.0}, "ride": {"hp": 1500, "pan": -0.2, "sends": {"room": 0.15}, "gain_db": -14.0}}
    return drum_kit("amiga", slug, sounds, stems, bpm=bpm, **params)


def brk(beats, vel=1.0):
    """A bar of the Amiga break: four beats (0-15 of the 4-bar break), 'R' a roll, 'S' a stutter, 'rN' a reversed beat, None a rest."""
    out = []
    for q, b in enumerate(beats):
        if b is None:
            continue
        if b == "R":
            out += [[q * 4 + r, 0.6 + 0.1 * r, "a04"] for r in range(4)]
        elif b == "S":
            out += [[q * 4 + r, 0.85, f"a{4 + r % 2:02d}"] for r in range(4)]
        elif isinstance(b, str):
            out.append([q * 4, 0.8, f"r{int(b[1:]):02d}"])
        else:
            out += [[q * 4 + r, vel, f"a{4 * b + r:02d}"] for r in range(4)]
    return out


def hats16(top=0.55, mid=0.42, off=0.22):
    return [[s, top if s % 4 == 2 else mid if s % 2 == 0 else off] for s in range(16)]


def spec(slug, title, seed, bpm, blurb, kitd, grid, arr, voices, targets, test, overrides=None, automation=(), layers=(), level_ref="kick", sends=None, track=1):
    o = {"name": "Demoscene Drum & Bass", "bpm": bpm, "drums": "grid", "grid": grid, "arrangement": arr, "drum_cycle_per_block": True,
         "loop_continuous": True, "drum_humanize_ms": 3, "harmony": JAZZ, "master": MASTER}
    o |= overrides or {}
    return {"slug": slug, "title": title, "song": SONG(seed), "genre": "lofi-downtempo", "rebuild": f"bountiful/pixel_album.py {slug}",
            "composer": COMPOSER, "artist": ARTIST, "album": ALBUM, "track": track, "year": YEAR, "blurb": blurb, "overrides": o,
            "kit": kitd, "kit_def": kitd["def"], "layers": list(layers), "voices": voices, "targets": targets, "level_ref": level_ref,
            "test_bars": test, "automation": list(automation),
            "sends": sends or {"echo": {"type": "delay", "time_beats": 0.75, "feedback": 0.4, "tone": 3200},
                               "plate": {"type": "reverb", "seconds": 2.8, "predelay": 0.03, "damp": 0.45}}}


def at(arr, name):
    return A2.bars_upto(arr, name)


SPECS: dict[str, dict] = {}

# ------------------------------------------------------------------ 2 Raster Interrupt: the Amiga break, chopped

G = {"straight": {"a": brk([0, 1, 2, 3]), "b": brk([4, 5, 6, 7]), "c": brk([8, 9, 10, 11]), "d": brk([12, 13, 14, 15])},
     "roller": {"a": brk([0, 1, 2, 3]), "b": brk([4, 5, 0, 7]), "c": brk([0, 9, 10, 11]), "d": brk([12, 1, 2, 15])},
     "half": {"a": brk([0, None, 1, None]), "b": brk([0, None, 1, None]), "c": brk([0, None, 3, None]), "d": brk([0, None, 1, "r3"])},
     "hat": hats16(0.5, 0.38, 0.2), "ride": [[s, 0.5 if s % 4 == 0 else 0.34] for s in range(0, 16, 2)],
     "F1": brk([0, 1, 2, "R"]), "F2": brk([0, 1, "S", 3]), "F3": brk([0, "r1", 2, 3]), "F4": brk([4, 5, "r2", "R"]),
     "F5": brk([0, 9, "S", "R"]), "F6": brk([12, 13, "S", "r3"]), "PU": [[12 + i / 2, 0.35 + 0.08 * i, "a04"] for i in range(8)]}
LEAD = ["lead", "pad", "arp", "bass", "bass_mid"]
ARR = ([blk("Interrupt: the break alone, filtered", "A", 4, [], ["half"]),
        blk("Raster lines", "A", 4, ["arp", "bass"], ["half", "hat"]),
        blk("Raster lines: pads", "A", 7, ["arp", "bass", "pad", "choir"], ["half", "hat"]),
        blk("Raster lines: pickup", "A", 1, ["arp", "bass", "pad", "choir"], ["PU", "hat"])]
       + groove("Main part", "A", LEAD + ["choir"], ["straight", "hat"], ["F1", "F2"], ["hat"], crash=True)
       + groove("Verse: piano bells", "V", ["lead", "comp", "pad", "bass", "bass_mid"], ["roller", "ride"], ["F3", "F4"], ["ride"])
       + [blk("Vertical blank", "B", 8, ["pad", "choir", "comp"]),
          blk("Vertical blank: the arps return", "B", 7, ["pad", "choir", "comp", "arp"], ["half"]),
          blk("Vertical blank: pickup", "B", 1, ["pad", "choir", "comp", "arp"], ["PU"])]
       + groove("Main part again", "A", LEAD + ["choir", "comp"], ["roller", "hat"], ["F5", "F6"], ["hat"], crash=True)
       + groove("Bridge in the border", "B", LEAD, ["straight", "ride"], ["F2"], ["ride"])
       + [blk("Exit: break and arps", "A", 8, ["arp", "bass"], ["straight", "hat"]), blk("Exit: last half-time", "A", 4, ["arp"], ["half"])])
SPECS["raster-interrupt"] = spec(
    "raster-interrupt", "Raster Interrupt", 204541885, 134,
    ("Amiga-demo drum & bass at 134 in C minor (Ebmaj9 - Dbmaj9 - Cm9 - Fm9): our C-Lizzy break as an 8-bit ProTracker sample, "
     "chopped and reversed, under SID arpeggios, a SID lead, SID pad and piano bells."),
    amiga_kit("raster-interrupt", 134), G, ARR,
    {"lead": (*xpf("SID/Lead.xpf", "SID lead"), dict(hp=250, sends={"echo": 0.28, "plate": 0.15}, gain_db=-6.0)),
     "arp": (*zyn("Laba170bank/0131-chip-SIDarpSharp.xiz", "chip SIDarpSharp (ZynAddSubFX - Laba170bank), tracker arpeggios"),
             dict(hp=450, pan=0.15, sends={"echo": 0.15, "plate": 0.15}, width=1.2, gain_db=-12.0)),
     "pad": (*xpf("SID/Pad.xpf", "SID pad"), dict(hp=180, lp=6500, width=1.3, sends={"plate": 0.4}, gain_db=-10.0)),
     "choir": (*zyn("Laba170bank/0129-chip-SlowSawStrings.xiz", "chip SlowSawStrings (ZynAddSubFX - Laba170bank)"),
               dict(hp=300, lp=6000, width=1.5, sends={"plate": 0.5}, gain_db=-16.0)),
     "comp": (*zyn("Laba170bank/0028-PianoBell.xiz", "PianoBell (ZynAddSubFX - Laba170bank), the jazz chords"),
              dict(hp=220, width=1.2, sends={"plate": 0.25, "echo": 0.1}, gain_db=-9.0)),
     "bass": (*zyn("Bass/0003-Bass 3 _analog_.xiz", "Bass 3 analog (ZynAddSubFX - Bass), sub"), dict(hp=25, lp=200, mono=True, duck={"depth": 0.25, "release": 0.1}, gain_db=-4.0)),
     "bass_mid": (*xpf("Watsyn/Phase_bass.xpf", "Watsyn phase bass, the upper bass"), dict(hp=180, lp=2200, mono=True, gain_db=-14.0))},
    {"lead": -8.0, "arp": -15.0, "pad": -13.0, "choir": -19.0, "comp": -13.0, "bass": -2.0, "bass_mid": -15.0},
    None, level_ref="break", track=2, layers=[("bass", "bass_mid"), ("pad", "choir")],
    overrides={"swing": 0.53, "melody": {"writer": "motif", "rhythm": "fresh", "register": [67, 86], "range_min": 12, "density": 0.8,
                                        "articulation": "detached", "humanize_ms": 3, "velocity": [0.6, 0.92]},
               "bass": {"style": "pattern", "register": [29, 44], "pattern": [[0, "R", 1.4, 1.0], [7, "R", 0.25, 0.7], [10, "R", 0.6, 0.85], [12, "O", 0.3, 0.7], [14, "5", 0.4, 0.75]]},
               "comp": {"steps": [0, 6, 10], "low": 58, "high": 79, "top": 76, "notes": 3, "gate": 0.5, "strum_ms": 6, "humanize_ms": 4, "vel": 0.55, "accent": 0.7},
               "arp": {"low": 60, "high": 84, "rate": 0.125, "gate": 0.1, "pattern": [0, 2, 1, 3, 2, 4, 3, 5], "humanize_ms": 0},
               "pad": {"low": 51, "high": 75, "top": 70, "notes": 4, "vel": 0.5}},
    automation=[{"type": "lowpass", "tracks": ["break"], "points": [[1, 900], [4, 1500], [5, 3000], [17, 18000]]},
                {"type": "lowpass", "tracks": ["arp"], "points": [[5, 1200], [17, 9000]]}])
SPECS["raster-interrupt"]["test_bars"] = (at(ARR, "Main part again 1"), at(ARR, "Main part again 1") + 7)

# ------------------------------------------------------------------ 3 Sine Scroller: C64 kit, half-time into two-step

G = {"halfkick": {"a": [[0, 1.0], [11, 0.65]], "b": [[0, 1.0], [14, 0.6]], "c": [[0, 1.0], [3, 0.6], [11, 0.65]], "d": [[0, 1.0], [10, 0.7]]},
     "halfsnare": [[8, 1.0]], "halfghost": {"a": [[5, 0.24], [13, 0.3]], "b": [[6, 0.22], [15, 0.3]], "c": [[13, 0.28]], "d": [[5, 0.22], [14, 0.26], [15, 0.32]]},
     "kick": {"a": [[0, 1.0], [10, 0.92]], "b": [[0, 1.0], [10, 0.9], [13, 0.6]], "c": [[0, 1.0], [10, 0.92]], "d": [[0, 1.0], [2, 0.7], [10, 0.9]]},
     "snare": [[4, 1.0], [12, 1.0]], "ghost": {"a": [[7, 0.28]], "b": [[9, 0.24], [15, 0.3]], "c": [[7, 0.26], [9, 0.22]], "d": [[3, 0.22], [14, 0.3]]},
     "hat": [[s, 0.5 if s % 4 == 2 else 0.36] for s in range(0, 16, 2)], "hat16": hats16(0.52, 0.4, 0.2),
     "open": {"a": [], "b": [], "c": [], "d": [[14, 0.4]]}, "ride": [[s, 0.48 if s % 4 == 0 else 0.32] for s in range(0, 16, 2)],
     "H1": [[0, 1.0, "kick"], [8, 1.0, "snare"], [12, 0.6, "tom_hi"], [13, 0.65, "tom_mid"], [14, 0.7, "tom_lo"], [15, 0.75, "tom_lo"]],
     "F1": [[0, 1.0, "kick"], [4, 1.0, "snare"]] + [[8 + i, 0.38 + 0.07 * i, "snare"] for i in range(8)],
     "F2": [[0, 1.0, "kick"], [4, 1.0, "snare"], [8, 0.8, "tom_hi"], [10, 0.8, "tom_mid"], [11, 0.75, "tom_mid"], [12, 0.85, "tom_lo"], [14, 0.8, "tom_lo"], [15, 0.6, "snare"]],
     "F3": [[0, 1.0, "kick"], [4, 1.0, "snare"], [7, 0.3, "ghost"], [10, 0.9, "kick"], [12, 1.0, "snare"], [13, 0.6, "snare"], [14.5, 0.7, "snare"], [15, 0.8, "snare"]]}
HALF = ["halfkick", "halfsnare", "halfghost", "hat"]
TWO = ["kick", "snare", "ghost", "hat16"]
ARR = ([blk("The scroller", "A", 8, ["lead", "pad"], lead_var="sparse"),
        blk("Half-time", "A", 7, ["lead", "pad", "choir", "bass"], HALF),
        blk("Half-time: tom pickup", "A", 1, ["lead", "pad", "choir", "bass"], ["H1", "hat"])]
       + groove("Bells over half-time", "V", ["arp", "pad", "comp", "bass", "bass_mid"], HALF, ["H1"], ["hat"])
       + groove("Two-step", "A", ["lead", "pad", "arp", "bass", "bass_mid"], TWO, ["F1", "F2"], ["hat16"], crash=True)
       + groove("Sine wave", "B", ["comp", "pad", "choir", "arp", "bass", "bass_mid"], TWO + ["ride"], ["F3"], ["ride"])
       + [blk("Breakdown: the scroller alone", "A", 8, ["lead", "choir"], ["ride"], lead_var="sparse")]
       + groove("Two-step again", "A", ["lead", "pad", "arp", "comp", "bass", "bass_mid"], TWO + ["open"], ["F2", "F1"], ["hat16"], crash=True)
       + groove("Sine wave again", "V", ["arp", "pad", "comp", "bass", "bass_mid"], TWO + ["ride"], ["F3"], ["ride"])
       + [blk("Back to half-time", "A", 8, ["lead", "pad", "bass"], HALF, lead_var="sparse"), blk("Scroller off screen", "A", 4, ["pad", "choir"])])
SPECS["sine-scroller"] = spec(
    "sine-scroller", "Sine Scroller", 2128092427, 126,
    ("C64-demo drum & bass at 126 in E minor (Em9 - G6 - Am9 - B): a SID-style kit with per-frame pitch tables, half-time that "
     "opens into a two-step, a square-to-sine lead, mystic chip bells and a BitInvader soft pad."),
    drum_kit("c64", "sine-scroller", CHIP_STEM, chip_stems()), G, ARR,
    {"lead": (*zyn("Laba170bank/0001-SquareToSine.xiz", "SquareToSine (ZynAddSubFX - Laba170bank)"), dict(hp=250, sends={"echo": 0.32, "plate": 0.2}, gain_db=-6.0)),
     "arp": (*zyn("Laba170bank/0115-MysticlBells.xiz", "MysticlBells (ZynAddSubFX - Laba170bank), arpeggiated bells"),
             dict(hp=500, pan=-0.2, sends={"echo": 0.2, "plate": 0.25}, width=1.3, gain_db=-12.0)),
     "pad": (*xpf("BitInvader/soft_pad.xpf", "BitInvader soft pad"), dict(hp=180, lp=6000, width=1.3, sends={"plate": 0.4}, gain_db=-10.0)),
     "choir": (*zyn("Synth/0005-Pulse Pad 2.xiz", "Pulse Pad 2 (ZynAddSubFX - Synth)"), dict(hp=300, lp=7000, width=1.5, sends={"plate": 0.5}, gain_db=-16.0)),
     "comp": (*xpf("BitInvader/epiano.xpf", "BitInvader e-piano"), dict(hp=200, chorus={"depth_ms": 1.6, "rate": 0.5, "base_ms": 9, "mix": 0.25}, width=1.2, sends={"plate": 0.2}, gain_db=-9.0)),
     "bass": (*xpf("BitInvader/subbass.xpf", "BitInvader sub bass"), dict(hp=28, lp=220, mono=True, duck={"depth": 0.3, "release": 0.1}, gain_db=-4.0)),
     "bass_mid": (*zyn("Laba170bank/0103-PluckedAnalogBass.xiz", "PluckedAnalogBass (ZynAddSubFX - Laba170bank)"), dict(hp=200, lp=2500, mono=True, gain_db=-14.0))},
    {"lead": -7.0, "arp": -15.0, "pad": -14.0, "choir": -20.0, "comp": -13.0, "bass": -2.0, "bass_mid": -14.0},
    None, track=3, layers=[("bass", "bass_mid"), ("pad", "choir")],
    overrides={"swing": 0.56, "melody": {"writer": "motif", "rhythm": "smooth", "register": [66, 86], "range_min": 12, "density": 0.7,
                                        "articulation": "legato", "humanize_ms": 5, "velocity": [0.55, 0.88]},
               "bass": {"style": "pattern", "register": [28, 43], "pattern": [[0, "R", 2.2, 1.0], [11, "5", 0.5, 0.75], [14, "R", 0.4, 0.8]]},
               "comp": {"steps": [0, 10], "low": 55, "high": 76, "top": 72, "notes": 4, "gate": 1.4, "strum_ms": 18, "humanize_ms": 6, "vel": 0.5, "accent": 0.62},
               "arp": {"low": 64, "high": 88, "rate": 0.25, "gate": 0.3, "pattern": [0, 2, 4, 6, 5, 3, 1, 3], "humanize_ms": 2},
               "pad": {"low": 52, "high": 76, "top": 71, "notes": 4, "vel": 0.5}},
    automation=[{"type": "lowpass", "tracks": ["pad", "lead"], "points": [[1, 1500], [8, 7000], [9, 18000]]}])
SPECS["sine-scroller"]["test_bars"] = (at(ARR, "Two-step again 1"), at(ARR, "Two-step again 1") + 7)

# ------------------------------------------------------------------ 4 Bitplane Blues: soft NES kit, jazz ride, walking bass

RIDE = [[0, 0.6], [4, 0.5], [7, 0.34], [8, 0.58], [12, 0.5], [15, 0.36]]          # ding, ding-a-ding (the 'a' late, on the 16th)
G = {"kick": {"a": [[0, 0.92], [10, 0.8]], "b": [[0, 0.92], [10, 0.78], [15, 0.5]], "c": [[0, 0.92], [6, 0.55], [10, 0.8]], "d": [[0, 0.92], [10, 0.8]]},
     "snare": [[4, 0.88], [12, 0.9]],
     "ghost": {"a": [[2, 0.2], [7, 0.26], [9, 0.22], [14, 0.24]], "b": [[3, 0.2], [6, 0.24], [11, 0.22], [15, 0.3]],
               "c": [[2, 0.22], [7, 0.24], [13, 0.22]], "d": [[6, 0.2], [9, 0.26], [11, 0.22], [14, 0.28], [15, 0.32]]},
     "ride": RIDE, "pedal": [[4, 0.3, "hat"], [12, 0.3, "hat"]], "rim": {"a": [[12, 0.4]], "b": [[12, 0.4]], "c": [[12, 0.4]], "d": [[12, 0.4], [15, 0.3]]},
     "brush": [[s, 0.18 if s % 2 else 0.26, "hat"] for s in range(16)],
     "F1": [[0, 0.9, "kick"], [4, 0.88, "snare"], [8, 0.7, "tom_hi"], [10, 0.7, "tom_mid"], [11, 0.3, "ghost"], [12, 0.8, "tom_lo"], [14, 0.6, "snare"], [15, 0.7, "snare"]],
     "F2": [[0, 0.9, "kick"], [4, 0.88, "snare"], [7, 0.3, "ghost"]] + [[10 + i, 0.3 + 0.08 * i, "snare"] for i in range(6)],
     "F3": [[0, 0.9, "kick"], [4, 0.88, "snare"], [6, 0.6, "tom_hi"], [7, 0.6, "tom_hi"], [10, 0.85, "kick"], [12, 0.9, "snare"], [14, 0.7, "tom_lo"]]}
JAZZKIT = ["kick", "snare", "ghost", "ride", "pedal"]
ARR = ([blk("Bitplane 1: e-piano alone", "A", 4, ["comp"]),
        blk("Bitplane 2: the ride", "A", 4, ["comp", "pad"], ["ride", "rim"]),
        blk("Bitplane 3: the theme", "A", 8, ["comp", "pad", "lead"], ["ride", "rim", "pedal"])]
       + groove("Blues in eight bits", "A", ["lead", "comp", "pad", "bass", "bass_mid"], JAZZKIT, ["F1", "F2"], ["ride"], crash=True)
       + groove("Ping arps", "V", ["arp", "comp", "pad", "bass", "bass_mid"], JAZZKIT, ["F3"], ["ride"])
       + [blk("Jazz club: walking chip bass", "B", 8, ["comp", "bass2", "lead"], ["brush", "rim"], lead_var="sparse"),
          blk("Jazz club: the pad joins", "B", 8, ["comp", "bass2", "pad", "arp"], ["brush", "rim", "pedal"])]
       + groove("Blues again", "A", ["lead", "comp", "pad", "arp", "bass", "bass_mid"], JAZZKIT, ["F2", "F1"], ["ride"], crash=True)
       + groove("Last chorus", "V", ["lead", "comp", "pad", "bass", "bass_mid"], JAZZKIT, ["F3"], ["ride"])
       + [blk("Outro: walking home", "A", 8, ["comp", "bass2", "pad"], ["brush", "rim"]), blk("Outro: e-piano alone", "A", 4, ["comp"])])
SPECS["bitplane-blues"] = spec(
    "bitplane-blues", "Bitplane Blues", 1997447099, 124,
    ("The jazz one, 124 in Ab major (Abmaj9 - Fm9 - Ebadd9; Abmaj9 - Ab6 - Cm7 - Eb9): a soft NES kit led by a swung chip ride "
     "and ghost notes, a BitInvader e-piano, a chip vibrato lead, square-ping arpeggios and a walking SID bass in the jazz-club break."),
    drum_kit("nes", "bitplane-blues", CHIP_STEM, chip_stems(kick=-4.0, snare=-6.0, hats=-11.0, ride=-8.0),
             kick=(200, 42, 28), kick_len=0.4, snare_clock=16000, snare_ms=110, hat_clock=80000, ride_hz=1318.5), G, ARR,
    {"lead": (*zyn("Laba170bank/0135-chip-VibratoLead2.xiz", "chip VibratoLead2 (ZynAddSubFX - Laba170bank)"), dict(hp=250, sends={"echo": 0.25, "plate": 0.2}, gain_db=-6.0)),
     "comp": (*xpf("BitInvader/epiano.xpf", "BitInvader e-piano, the lead instrument of the chords"),
              dict(hp=160, chorus={"depth_ms": 1.8, "rate": 0.45, "base_ms": 9, "mix": 0.3}, width=1.3, sends={"plate": 0.25, "echo": 0.06}, gain_db=-8.0)),
     "arp": (*xpf("TripleOscillator/SquarePing.xpf", "TripleOscillator square ping, arpeggios"), dict(hp=500, pan=0.2, sends={"echo": 0.25, "plate": 0.2}, gain_db=-12.0)),
     "pad": (*zyn("Pads/0006-Square Pad 2.xiz", "Square Pad 2 (ZynAddSubFX - Pads)"), dict(hp=180, lp=5500, width=1.3, sends={"plate": 0.4}, gain_db=-11.0)),
     "bass": (*zyn("Bass/0003-Bass 3 _analog_.xiz", "Bass 3 analog (ZynAddSubFX - Bass), sub"), dict(hp=25, lp=200, mono=True, duck={"depth": 0.25, "release": 0.1}, gain_db=-4.0)),
     "bass_mid": (*xpf("SID/Bass.xpf", "SID bass, the upper bass"), dict(hp=200, lp=2500, mono=True, gain_db=-14.0)),
     "bass2": (*xpf("SID/Bass.xpf", "SID bass, walking"), dict(hp=35, lp=3000, mono=True, gain_db=-6.0))},
    {"lead": -8.0, "comp": -9.0, "arp": -16.0, "pad": -15.0, "bass": -2.0, "bass_mid": -15.0, "bass2": -4.0},
    None, track=4, layers=[("bass", "bass_mid")],
    overrides={"swing": 0.6, "melody": {"writer": "motif", "rhythm": "latin", "register": [65, 84], "range_min": 10, "density": 0.75,
                                       "articulation": "detached", "humanize_ms": 8, "push_ms": 4, "velocity": [0.55, 0.85]},
               "bass": {"style": "pattern", "register": [32, 47], "pattern": [[0, "R", 1.2, 1.0], [6, "5", 0.3, 0.7], [10, "R", 0.9, 0.88], [14, "3", 0.4, 0.72]]},
               "bass2": {"style": "walking", "register": [33, 52], "humanize_ms": 10, "swing": 0.6},
               "comp": {"steps": [0, 3, 10], "low": 55, "high": 75, "top": 72, "notes": 4, "gate": 0.8, "strum_ms": 20, "humanize_ms": 10, "vel": 0.55, "accent": 0.68},
               "arp": {"low": 67, "high": 91, "rate": 0.25, "gate": 0.2, "pattern": [0, 3, 1, 4, 2, 5], "humanize_ms": 3},
               "pad": {"low": 53, "high": 75, "top": 70, "notes": 4, "vel": 0.45}})
SPECS["bitplane-blues"]["test_bars"] = (at(ARR, "Blues again 1"), at(ARR, "Blues again 1") + 7)

# ------------------------------------------------------------------ 5 Vector Balls: Game Boy kit, steppers

G = {"kick": {"a": [[0, 1.0], [7, 0.7], [10, 0.92]], "b": [[0, 1.0], [10, 0.9], [13, 0.65]], "c": [[0, 1.0], [6, 0.7], [10, 0.92]], "d": [[0, 1.0], [3, 0.65], [10, 0.9], [11, 0.6]]},
     "snare": [[4, 1.0], [12, 1.0]], "ghost": {"a": [[9, 0.26]], "b": [[7, 0.24], [15, 0.32]], "c": [[2, 0.2], [9, 0.26]], "d": [[7, 0.26], [14, 0.3]]},
     "hat": hats16(0.6, 0.48, 0.3), "open": [[2, 0.36], [10, 0.36]],
     "roll": {"a": [], "b": [], "c": [], "d": [[12 + i / 2, 0.25 + 0.05 * i, "hat"] for i in range(8)]},
     "ride": [[s, 0.5 if s % 4 == 0 else 0.34] for s in range(0, 16, 2)],
     "T1": [[0, 1.0, "kick"], [4, 1.0, "snare"]] + [[8 + i * 8 / 12, 0.65 + 0.02 * i, ("tom_hi", "tom_mid", "tom_lo")[i // 4]] for i in range(12)],   # triplet tom run
     "T2": [[0, 1.0, "kick"], [4, 1.0, "snare"], [6, 0.6, "snare"], [7, 0.7, "snare"], [10, 0.9, "kick"]] + [[12 + i / 2, 0.4 + 0.07 * i, "snare"] for i in range(8)],
     "T3": [[0, 1.0, "kick"], [2, 0.8, "tom_hi"], [4, 1.0, "snare"], [6, 0.8, "tom_mid"], [8, 0.9, "kick"], [10, 0.8, "tom_lo"], [12, 1.0, "snare"], [14, 0.8, "tom_lo"], [15, 0.8, "snare"]],
     "T4": [[0, 1.0, "kick"], [4, 1.0, "snare"], [8, 1.0, "kick"], [12, 1.0, "snare"], [13, 0.8, "snare"], [14, 0.9, "snare"], [15, 1.0, "snare"]]}
STEP = ["kick", "snare", "ghost", "hat", "roll"]
ARR = ([blk("Power on: arps", "A", 4, ["arp"]), blk("Power on: drums", "A", 3, ["arp"], ["kick", "hat"]),
        blk("Power on: pickup", "A", 1, ["arp"], ["T4"])]
       + groove("Balls in orbit", "A", ["arp", "bass", "bass_mid", "pad"], STEP, ["T1"], ["hat"])
       + groove("Vector theme", "A", ["lead", "arp", "bass", "bass_mid", "pad"], STEP + ["open"], ["T2", "T3"], ["hat"], crash=True)
       + groove("Rotation", "V", ["lead", "pad", "choir", "bass", "bass_mid"], STEP + ["ride"], ["T1"], ["ride"])
       + [blk("Zoom out", "B", 8, ["pad", "choir", "arp"], ["ride"]),
          blk("Zoom in", "B", 7, ["pad", "choir", "arp", "bass"], ["kick", "hat"]), blk("Zoom in: pickup", "B", 1, ["pad", "choir", "arp", "bass"], ["T4"])]
       + groove("Vector theme again", "A", ["lead", "arp", "bass", "bass_mid", "pad", "choir"], STEP + ["open"], ["T3", "T2"], ["hat"], crash=True)
       + groove("Rotation again", "V", ["lead", "pad", "choir", "arp", "bass", "bass_mid"], STEP + ["ride"], ["T1"], ["ride"])
       + [blk("Power off", "A", 8, ["arp", "bass"], ["kick", "hat"]), blk("Power off: arps", "A", 4, ["arp"])])
SPECS["vector-balls"] = spec(
    "vector-balls", "Vector Balls", 1055521371, 136,
    ("The fast one, 136 in D# minor (G#m9 - Bmaj9 - A# - D#m9): a Game Boy kit (4-bit, 64 Hz envelopes) in a stepping beat with "
     "hat rolls and triplet tom runs, triplet-32nd SID arpeggios, a Nescaline detuned lead and hard pulse pads."),
    drum_kit("gb", "vector-balls", CHIP_STEM, chip_stems(hats=-10.0)), G, ARR,
    {"lead": (*xpf("Nescaline/Detune_lead.xpf", "Nescaline detuned lead"), dict(hp=250, lp=9000, sends={"echo": 0.26, "plate": 0.15}, gain_db=-6.0)),
     "arp": (*zyn("Laba170bank/0132-chip-SIDarpSharp2.xiz", "chip SIDarpSharp2 (ZynAddSubFX - Laba170bank), triplet-32nd arpeggios"),
             dict(hp=450, pan=-0.15, sends={"echo": 0.12, "plate": 0.15}, width=1.2, gain_db=-12.0)),
     "pad": (*zyn("Synth/0006-Pulse Pad 3.xiz", "Pulse Pad 3 (ZynAddSubFX - Synth)"), dict(hp=180, lp=6500, width=1.3, sends={"plate": 0.4}, gain_db=-10.0)),
     "choir": (*zyn("the_mysterious_bank/0029-hard_pulse.xiz", "hard pulse (ZynAddSubFX - the mysterious bank)"), dict(hp=400, lp=5000, width=1.5, sends={"plate": 0.5}, gain_db=-18.0)),
     "bass": (*xpf("BitInvader/subbass.xpf", "BitInvader sub bass"), dict(hp=28, lp=220, mono=True, duck={"depth": 0.3, "release": 0.1}, gain_db=-4.0)),
     "bass_mid": (*zyn("Laba170bank/0099-SharpBass1.xiz", "SharpBass1 (ZynAddSubFX - Laba170bank)"), dict(hp=200, lp=2500, mono=True, gain_db=-14.0))},
    {"lead": -7.0, "arp": -14.0, "pad": -14.0, "choir": -21.0, "bass": -2.0, "bass_mid": -13.0},
    None, track=5, layers=[("bass", "bass_mid"), ("pad", "choir")],
    overrides={"swing": 0.52, "melody": {"writer": "motif", "rhythm": "bouncy", "register": [68, 88], "range_min": 12, "density": 0.85,
                                        "articulation": "detached", "humanize_ms": 2, "velocity": [0.65, 0.95]},
               "bass": {"style": "pattern", "register": [27, 42], "pattern": [[0, "R", 0.9, 1.0], [3, "R", 0.25, 0.7], [6, "O", 0.25, 0.75], [10, "R", 0.9, 0.9], [14, "5", 0.4, 0.8]]},
               "arp": {"low": 63, "high": 87, "rate": 1 / 6, "gate": 0.12, "pattern": [0, 1, 2], "humanize_ms": 0},
               "pad": {"low": 51, "high": 75, "top": 70, "notes": 3, "vel": 0.5}},
    automation=[{"type": "lowpass", "tracks": ["arp"], "points": [[1, 800], [8, 6000], [9, 18000]]}])
SPECS["vector-balls"]["test_bars"] = (at(ARR, "Vector theme again 1"), at(ARR, "Vector theme again 1") + 7)

# ------------------------------------------------------------------ 6 Greetings: bright NES kit, liquid roller, major key

G = {"kick": {"a": [[0, 1.0], [10, 0.92]], "b": [[0, 1.0], [10, 0.9], [13, 0.6]], "c": [[0, 1.0], [10, 0.92]], "d": [[0, 1.0], [2, 0.65], [10, 0.9]]},
     "snare": [[4, 1.0], [12, 1.0]], "ghost": {"a": [[7, 0.26], [9, 0.22]], "b": [[14, 0.28], [15, 0.32]], "c": [[6, 0.22], [9, 0.26]], "d": [[3, 0.2], [7, 0.26], [15, 0.34]]},
     "hat": [[s, 0.5, "hat"] for s in (2, 6, 10, 14)], "shaker": [[s, 0.34 if s % 2 else 0.22, "hat"] for s in range(16)],
     "ride": [[s, 0.48 if s % 4 == 0 else 0.32] for s in range(0, 16, 2)], "open": {"a": [], "b": [[14, 0.38]], "c": [], "d": [[14, 0.38]]},
     "W1": [[0, 1.0, "kick"], [4, 1.0, "snare"], [10, 0.9, "kick"], [12, 1.0, "snare"], [14, 0.6, "tom_hi"], [15, 0.7, "tom_lo"]],
     "W2": [[0, 1.0, "kick"], [4, 1.0, "snare"]] + [[8 + i, 0.4 + 0.07 * i, "snare"] for i in range(8)],
     "W3": [[0, 1.0, "kick"], [4, 1.0, "snare"], [7, 0.3, "ghost"], [8, 0.8, "tom_hi"], [10, 0.85, "tom_mid"], [12, 0.9, "tom_lo"], [13, 0.9, "tom_lo"], [15, 0.7, "snare"]]}
ROLL = ["kick", "snare", "ghost", "hat", "shaker"]
ARR = ([blk("Drums for the DJ", "A", 4, [], ["kick", "snare", "shaker"]), blk("Drums and sub", "A", 4, ["bass"], ROLL)]
       + groove("Greetings to", "A", ["arp", "pad", "choir", "bass", "bass_mid"], ROLL, ["W1"], ["shaker"])
       + groove("The theme", "A", ["lead", "arp", "pad", "bass", "bass_mid"], ROLL, ["W2", "W3"], ["shaker"], crash=True)
       + groove("Organ stabs", "V", ["comp", "pad", "choir", "bass", "bass_mid", "lead"], ROLL + ["ride"], ["W1"], ["ride"])
       + [blk("Greetz: the lead alone", "B", 4, ["lead"], lead_var="sparse"), blk("Greetz: pads", "B", 4, ["lead", "pad", "choir"], lead_var="sparse"),
          blk("Greetz: shaker", "B", 7, ["lead", "pad", "choir", "arp"], ["shaker"]), blk("Greetz: pickup", "B", 1, ["lead", "pad", "choir", "arp"], ["W2"])]
       + groove("The theme again", "A", ["lead", "arp", "pad", "choir", "comp", "bass", "bass_mid"], ROLL + ["open"], ["W3", "W2"], ["shaker"], crash=True)
       + groove("Organ stabs again", "V", ["comp", "pad", "choir", "arp", "bass", "bass_mid", "lead"], ROLL + ["ride"], ["W1"], ["ride"])
       + [blk("Drums for the next DJ", "A", 8, ["bass"], ROLL), blk("Last greet", "A", 4, ["pad"], ["shaker"])])
SPECS["greetings"] = spec(
    "greetings", "Greetings", 554077850, 128,
    ("The warm one, 128 in F major (Fmaj9 - Bbmaj9 - Fmaj9 - Cadd9; Dm9 in the verse): a bright NES kit in a liquid roller with a "
     "chip shaker, a Watsyn pulse lead, plucked chip arps, superpulse pads, pulse-organ stabs and a DJ-friendly start and end."),
    drum_kit("nes", "greetings", CHIP_STEM, chip_stems(hats=-11.0), kick=(270, 50, 18), kick_len=0.3, snare_clock=34000, snare_ms=75, hat_clock=120000, ride_hz=1760.0), G, ARR,
    {"lead": (*xpf("Watsyn/Pulse.xpf", "Watsyn pulse lead"), dict(hp=250, lp=9000, sends={"echo": 0.3, "plate": 0.2}, gain_db=-6.0)),
     "arp": (*zyn("Laba170bank/0146-PluckedWithVibTail.xiz", "PluckedWithVibTail (ZynAddSubFX - Laba170bank), arpeggios"),
             dict(hp=450, pan=0.2, sends={"echo": 0.2, "plate": 0.2}, width=1.2, gain_db=-12.0)),
     "pad": (*zyn("the_mysterious_bank/0015-superpulse.xiz", "superpulse (ZynAddSubFX - the mysterious bank)"), dict(hp=180, lp=6500, width=1.3, sends={"plate": 0.4}, gain_db=-10.0)),
     "choir": (*zyn("Laba170bank/0129-chip-SlowSawStrings.xiz", "chip SlowSawStrings (ZynAddSubFX - Laba170bank)"), dict(hp=300, lp=6000, width=1.5, sends={"plate": 0.5}, gain_db=-16.0)),
     "comp": (*zyn("the_mysterious_bank/0020-pulse_organ.xiz", "pulse organ (ZynAddSubFX - the mysterious bank), stabs"),
              dict(hp=200, width=1.1, sends={"plate": 0.2, "echo": 0.15}, gain_db=-9.0)),
     "bass": (*zyn("Bass/0003-Bass 3 _analog_.xiz", "Bass 3 analog (ZynAddSubFX - Bass), sub"), dict(hp=25, lp=200, mono=True, duck={"depth": 0.3, "release": 0.1}, gain_db=-4.0)),
     "bass_mid": (*xpf("SID/Bass.xpf", "SID bass, the upper bass"), dict(hp=200, lp=2500, mono=True, gain_db=-14.0))},
    {"lead": -7.0, "arp": -15.0, "pad": -14.0, "choir": -20.0, "comp": -12.0, "bass": -2.0, "bass_mid": -14.0},
    None, track=6, layers=[("bass", "bass_mid"), ("pad", "choir")],
    overrides={"swing": 0.55, "melody": {"writer": "motif", "rhythm": "house", "register": [67, 86], "range_min": 12, "density": 0.8,
                                        "articulation": "legato", "humanize_ms": 4, "velocity": [0.6, 0.9]},
               "bass": {"style": "pattern", "register": [29, 44], "pattern": [[0, "R", 1.6, 1.0], [10, "R", 0.6, 0.88], [12, "5", 0.4, 0.75], [14, "O", 0.4, 0.75]]},
               "comp": {"steps": [2, 6, 11, 14], "low": 57, "high": 77, "top": 74, "notes": 3, "gate": 0.3, "humanize_ms": 3, "vel": 0.55, "accent": 0.62},
               "arp": {"low": 65, "high": 89, "rate": 0.125, "gate": 0.12, "pattern": [0, 4, 1, 5, 2, 6, 3, 7], "humanize_ms": 0},
               "pad": {"low": 53, "high": 77, "top": 72, "notes": 4, "vel": 0.5}})
SPECS["greetings"]["test_bars"] = (at(ARR, "The theme again 1"), at(ARR, "The theme again 1") + 7)

# ------------------------------------------------------------------ 7 Plasma: the Amiga break, dirtier and darker

G = {"roll": {"a": brk([0, 1, 2, 3]), "b": brk([4, 5, 6, 7]), "c": brk([0, 1, 10, 11]), "d": brk([12, 13, 2, 15])},
     "chop": {"a": brk([0, 5, 2, 7]), "b": brk([8, 1, 10, 3]), "c": brk([0, 9, "r2", 11]), "d": brk([4, 13, 14, "S"])},
     "sparse": {"a": brk([0, None, None, 3]), "b": brk([None, 1, None, None]), "c": brk([0, None, 2, None]), "d": brk([None, None, None, "r3"])},
     "hat": hats16(0.45, 0.34, 0.18), "ride": [[s, 0.5 if s % 4 == 0 else 0.32] for s in range(0, 16, 2)], "open": [[6, 0.35], [14, 0.35]],
     "P1": brk([0, 1, "S", "R"]), "P2": brk([0, "r1", 10, "R"]), "P3": brk([12, 13, "r2", "S"]), "P4": brk([0, 9, "R", "R"]),
     "PU": [[8 + i / 2, 0.3 + 0.05 * i, "a04"] for i in range(16)]}
ARR = ([blk("Plasma: noisy pulses", "A", 8, ["pad", "choir"]), blk("Plasma: the lead", "A", 7, ["pad", "choir", "lead"], ["sparse"], lead_var="sparse"),
        blk("Plasma: pickup", "A", 1, ["pad", "choir", "lead"], ["PU"], lead_var="sparse")]
       + groove("Burn", "A", ["lead", "pad", "bass", "bass_mid", "arp"], ["roll", "hat"], ["P1", "P2"], ["hat"], crash=True)
       + groove("Palette cycle", "V", ["pad", "choir", "arp", "bass", "bass_mid"], ["chop", "ride"], ["P3"], ["ride"])
       + [blk("Cool down", "B", 8, ["pad", "choir", "arp"], ["sparse"]), blk("Cool down: the lead", "B", 7, ["pad", "choir", "arp", "lead"], ["sparse", "hat"]),
          blk("Cool down: pickup", "B", 1, ["pad", "choir", "arp", "lead"], ["PU"])]
       + groove("Burn again", "A", ["lead", "pad", "choir", "bass", "bass_mid", "arp"], ["chop", "hat", "open"], ["P4", "P1"], ["hat"], crash=True)
       + groove("Palette cycle again", "B", ["lead", "pad", "choir", "arp", "bass", "bass_mid"], ["roll", "ride"], ["P3"], ["ride"])
       + [blk("Fade to black", "A", 8, ["pad", "choir", "bass"], ["sparse"]), blk("Black", "A", 4, ["choir"])])
SPECS["plasma"] = spec(
    "plasma", "Plasma", 1615054428, 132,
    ("The dark one, 132 in A minor (Am9 - Dm9 - E; Am9 - G6 - Fmaj9 - Dm9): the break crushed harder (6-bit, 11 kHz), chopped out of "
     "order with reversed beats, under sweepy noisy pulses, a chip vibrato lead and distorted chip arpeggios."),
    amiga_kit("plasma", 132, bits=6, rate=11025), G, ARR,
    {"lead": (*zyn("Laba170bank/0134-chip-VibratoLead.xiz", "chip VibratoLead (ZynAddSubFX - Laba170bank)"), dict(hp=250, sends={"echo": 0.32, "plate": 0.25}, gain_db=-6.0)),
     "arp": (*zyn("Laba170bank/0137-chip-PolyDistorted.xiz", "chip PolyDistorted (ZynAddSubFX - Laba170bank), arpeggios"),
             dict(hp=500, lp=5000, pan=0.15, sends={"echo": 0.15, "plate": 0.2}, width=1.2, gain_db=-14.0)),
     "pad": (*zyn("olivers-100/0098-Sweepy Noisy Pulses.xiz", "Sweepy Noisy Pulses (ZynAddSubFX - olivers-100)"), dict(hp=180, lp=6000, width=1.4, sends={"plate": 0.45}, gain_db=-10.0)),
     "choir": (*xpf("SID/Pad.xpf", "SID pad"), dict(hp=250, lp=5000, width=1.3, sends={"plate": 0.5}, gain_db=-16.0)),
     "bass": (*zyn("Bass/0003-Bass 3 _analog_.xiz", "Bass 3 analog (ZynAddSubFX - Bass), sub"), dict(hp=25, lp=190, mono=True, duck={"depth": 0.25, "release": 0.1}, gain_db=-4.0)),
     "bass_mid": (*zyn("Laba170bank/0113-BassyChirp.xiz", "BassyChirp (ZynAddSubFX - Laba170bank)"), dict(hp=200, lp=2000, mono=True, drive=1.4, gain_db=-14.0))},
    {"lead": -8.0, "arp": -16.0, "pad": -12.0, "choir": -18.0, "bass": -2.0, "bass_mid": -14.0},
    None, level_ref="break", track=7, layers=[("bass", "bass_mid")],
    overrides={"swing": 0.54, "melody": {"writer": "motif", "rhythm": "dub", "register": [64, 84], "range_min": 12, "density": 0.65,
                                        "articulation": "legato", "humanize_ms": 5, "velocity": [0.55, 0.88]},
               "bass": {"style": "pattern", "register": [28, 43], "pattern": [[0, "R", 2.4, 1.0], [10, "R", 0.5, 0.85], [11, "O", 0.25, 0.7], [14, "R", 0.4, 0.8]]},
               "arp": {"low": 57, "high": 81, "rate": 0.125, "gate": 0.1, "pattern": [0, 1, 2, 3, 2, 1], "humanize_ms": 0},
               "pad": {"low": 50, "high": 74, "top": 69, "notes": 4, "vel": 0.5}},
    automation=[{"type": "lowpass", "tracks": ["break"], "points": [[9, 1200], [16, 4000], [17, 18000]]}])
SPECS["plasma"]["test_bars"] = (at(ARR, "Burn again 1"), at(ARR, "Burn again 1") + 7)

# ------------------------------------------------------------------ 8 Last Frame: Copper Bars' song again, slower, a new melody

G = {"halfkick": {"a": [[0, 1.0], [11, 0.6]], "b": [[0, 1.0]], "c": [[0, 1.0], [10, 0.65]], "d": [[0, 1.0], [14, 0.55]]},
     "halfsnare": [[8, 1.0]], "halfghost": {"a": [[13, 0.26]], "b": [[5, 0.22], [15, 0.3]], "c": [[6, 0.22]], "d": [[13, 0.24], [15, 0.3]]},
     "hat": [[s, 0.45 if s % 4 == 2 else 0.32] for s in range(0, 16, 2)],
     "kick": P.GRID["kick"], "snare": P.GRID["snare"], "ghost": P.GRID["ghost"], "hat16": P.HAT, "ride": P.GRID["ride"], "rim": P.GRID["rim"],
     "FA": P.FILLS["FA"], "FB": P.FILLS["FB"], "FD": P.FILLS["FD"],
     "H1": [[0, 1.0, "kick"], [8, 1.0, "snare"], [13, 0.5, "tom_hi"], [14, 0.6, "tom_mid"], [15, 0.7, "tom_lo"]]}
HALF = ["halfkick", "halfsnare", "halfghost", "hat"]
ARR = ([blk("Last frame: toy piano", "B", 8, ["lead", "pad"], lead_var="sparse"),
        blk("Half-time", "B", 7, ["lead", "pad", "choir", "bass"], HALF), blk("Half-time: pickup", "B", 1, ["lead", "pad", "choir", "bass"], ["H1", "hat"])]
       + groove("Copper Bars, remembered", "A", ["arp", "pad", "comp", "bass"], HALF + ["rim"], ["H1"], ["hat"])
       + groove("Once more at full speed", "A", ["lead", "comp", "pad", "arp", "bass"], ["kick", "snare", "ghost", "hat16"], ["FA", "FB"], ["hat16"], crash=True)
       + groove("The lift", "B", ["lead", "comp", "pad", "choir", "bass"], ["kick", "snare", "ghost", "ride"], ["FD"], ["ride"])
       + [blk("Slowing down", "A", 8, ["comp", "pad", "arp", "bass"], HALF), blk("Boot screen, in reverse", "A", 8, ["pad", "arp"]),
          blk("Off", "A", 4, ["arp"])])
SPECS["last-frame"] = spec(
    "last-frame", "Last Frame", 1941868402, 122,
    ("The closer, 122 in C# minor: Copper Bars' own song and kit again, with a new melody on a BitInvader toy piano, half-time for "
     "most of the way, one pass at full speed, and the opening's pads and arpeggios closing the album as they opened it."),
    drum_kit("nes", "last-frame", CHIP_STEM, chip_stems(snare=-5.0)), G, ARR,
    {"lead": (*xpf("BitInvader/toy_piano.xpf", "BitInvader toy piano"), dict(hp=250, sends={"echo": 0.3, "plate": 0.3}, gain_db=-6.0)),
     "arp": (*zyn("Laba170bank/0130-chip-SIDarpSoft.xiz", "chip SIDarpSoft (ZynAddSubFX - Laba170bank), the Copper Bars arpeggios"),
             dict(hp=400, pan=-0.15, sends={"echo": 0.2, "plate": 0.25}, width=1.2, gain_db=-12.0)),
     "pad": (*zyn("Pads/0005-Square Pad 1.xiz", "Square Pad 1 (ZynAddSubFX - Pads), the Copper Bars pad"), dict(hp=180, lp=6000, width=1.3, sends={"plate": 0.45}, gain_db=-10.0)),
     "choir": (*zyn("Synth/0004-Pulse Pad 1.xiz", "Pulse Pad 1 (ZynAddSubFX - Synth)"), dict(hp=300, lp=7000, width=1.5, sends={"plate": 0.5}, gain_db=-16.0)),
     "comp": (*xpf("BitInvader/epiano.xpf", "BitInvader e-piano"), dict(hp=200, chorus={"depth_ms": 1.6, "rate": 0.5, "base_ms": 9, "mix": 0.25}, width=1.2, sends={"plate": 0.25}, gain_db=-9.0)),
     "bass": (*xpf("BitInvader/subbass.xpf", "BitInvader sub bass"), dict(hp=28, lp=220, mono=True, duck={"depth": 0.3, "release": 0.1}, gain_db=-4.0))},
    {"lead": -7.0, "arp": -15.0, "pad": -13.0, "choir": -19.0, "comp": -13.0, "bass": -2.0},
    None, track=8, layers=[("pad", "choir")],
    overrides={"swing": 0.57, "melody": {"writer": "motif", "rhythm": "smooth", "register": [69, 88], "range_min": 12, "density": 0.65,
                                                    "articulation": "detached", "humanize_ms": 6, "velocity": [0.55, 0.85]},
               "bass": {"style": "pattern", "register": [30, 45], "pattern": [[0, "R", 2.0, 1.0], [10, "R", 0.8, 0.85], [14, "5", 0.4, 0.75]]},
               "comp": {"steps": [0, 7], "low": 56, "high": 76, "top": 73, "notes": 4, "gate": 1.0, "strum_ms": 16, "humanize_ms": 6, "vel": 0.52, "accent": 0.64},
               "arp": P.SPEC["overrides"]["arp"], "pad": P.SPEC["overrides"]["pad"]},
    automation=[{"type": "gain", "tracks": ["arp", "pad"], "points": [[sum(b["bars"] for b in ARR) - 3, 0], [sum(b["bars"] for b in ARR) + 1, -18]]}])
SPECS["last-frame"]["seed"] = 8                    # the producer's seed: a new melody from the same song
SPECS["last-frame"]["test_bars"] = (at(ARR, "Once more at full speed 1"), at(ARR, "Once more at full speed 1") + 7)
