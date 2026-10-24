#!/usr/bin/env python3
"""'Taste Tester' tracks 2-7, after Pepperoni. Cohesion from a shared musical identity, not one arrangement five times:

  shared  breakbeat house with no four-to-the-floor; minor-9th jazz harmony; drums gated like LMMS's sampler and crushed to 12 bits,
          mixed percussion-forward to the balance of the user's Pepperoni edit; an organ in every track (a different one each time);
          vocal-morph chops; the era filter sweeps, pans and the clipper master Pepperoni v2 got.
  own     key, tempo, drum kit and source, bass, keys, lead, beat, opening, song form and length.

  #  title       key / tempo   drums                           bass                  organ               keys / lead                           form
  2  Cheese      F minor, 112  brushed acoustic jazz kit, ride upright (Zyn)           Royale with Cheese  Ice Rhodes lead, vibraphone double    Rhodes early, 'the melt', long outro
  3  Bread Roll  D minor, 121  the C-Lizzy break, re-sliced    Monosynth Cut Through Transistor          piano-house stabs, whistle            bass alone, two 'roll calls'
  4  Pesto       G major, 124  TR-909 + shaker                 Zyn Wah Bass          Shamrock            marimba arpeggio, flute               flute early, 'the garden', a stop
  5  Anchovies   C minor, 126  TR-808 crushed to 10 bits       Monosynth Boom Bass   Intertube (dub)     Melodica NOS                          salt intro, hypnotic, two dub-outs
  6  Marinara    A minor, 108  LinnDrum + congas, bongos       Zyn Analogue Bass     Rusty Keys (pad)    Italo piano, nylon guitar, accordion  a short verse/chorus song
  7  Meatball    G minor, 128  heavy acoustic kit, ride, toms  Monosynth Fat Bass    Fat Belly           Fat Brass hook; Pepperoni's organ back  the closer: opens 'through a door', a big outro

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/taste_tester.py [cheese] [bread-roll] [pesto] [anchovies] [marinara] [meatball]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import album_mezzanine_v2 as A2  # noqa: E402
import break_maker as BM  # noqa: E402
import lmms_tracks as LT  # noqa: E402
import producer as PR  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
blk, kit, zyn, calf, xpf, sub, dm, LD = A2.blk, A2.kit, A2.zyn, A2.calf, A2.xpf, A2.sub, A2.dm, A2.LMMS_DRUMS
ALBUM = "Taste Tester"


def at(arr, name):
    return A2.bars_upto(arr, name)


def mallets(preset, label):
    return {"plugin": "malletsstk", "attrs": {"preset": preset}}, label


# ------------------------------------------------------------------ the shared identity
CRUSH = {"bits": 12, "rate": 26040, "mix": 0.4}


def gated_kit(bpm, sounds, stems=None, ticks=10):
    """sounds: name -> (sample, stem, extra). Every hit gated to `ticks` LMMS ticks (as LMMS's sampler plays the user's projects),
    the stems crushed to 12 bits, hats right, percussion left, mixed percussion-forward."""
    g = ticks / 48 * 60 / bpm
    snd = {n: (p, st, {"gate": g, **(ex or {})}) for n, (p, st, ex) in sounds.items()}
    base = {"kick": {"hp": 35, "mono": True, "drive": 1.4, "crush": CRUSH, "gain_db": -3.0},
            "break": {"hp": 90, "drive": 1.5, "crush": {**CRUSH, "mix": 0.5}, "sends": {"room": 0.15}, "gain_db": -3.2},
            "hats": {"hp": 300, "pan": 0.3, "crush": CRUSH, "gain_db": 0.8},
            "perc": {"pan": -0.35, "sends": {"room": 0.2}, "gain_db": 1.4}}
    for k, v in (stems or {}).items():
        base[k] = {**base.get(k, {}), **v}
    return kit(snd, base)


# the user's Pepperoni balance vs the kick (measured from their mix)
TARGETS = {"bass": -10.5, "bass_sub": -16.6, "stab": -12.0, "pad": -15.0, "lead": -11.5, "vox": -20.0}
MASTER = {"eq": [["peak", 75, -2.0, 0.8], ["peak", 300, -1.0, 0.9], ["highshelf", 3500, 2.5], ["highshelf", 11000, 1.5]],
          "width": 1.05, "target_lufs": -10.2, "ceiling": -1.2, "clip": 2.0, "true_peak": -1.0}


def CHOPS(f, label):
    return (*zyn(f"ChoirAndVoice/{f}", f"{label} (ZynAddSubFX - ChoirAndVoice), chops"),
            dict(hp=280, drive=1.3, sends={"echo": 0.2, "plate": 0.2}, gain_db=-8.0))


def spec(title, slug, track, song, bpm, swing, arr, blurb, g_over, kitdef, voices, targets, automation, test, layers=(("bass", "bass_sub"),), **kw):
    s = {"title": title, "song": ROOT / "songs" / song, "genre": "ny-house-93", "rebuild": f"bountiful/taste_tester.py {slug}",
         "composer": A2.COMPOSER, "artist": A2.ARTIST, "album": ALBUM, "track": track, "year": A2.YEAR, "blurb": blurb,
         "overrides": {"bpm": bpm, "swing": swing, "drums": "grid", "arrangement": arr, "drum_cycle_per_block": True, "loop_continuous": True,
                       **g_over, "master": dict(MASTER, **kw.pop("master", {}))},
         "kit_def": kitdef, "layers": list(layers), "voices": voices, "targets": targets, "level_ref": kw.pop("level_ref", "kick"),
         "automation": automation, "test_bars": (at(arr, test), at(arr, test) + 7)}
    s.update(kw)
    return s


# ================================================================== 2 Cheese: F minor, 112 bpm, smooth and melty
DR_C = ["kick", "snare", "ghost", "hat"]
ARR_C = [blk("Organ alone, filtering in", "A", 8, ["stab"]),
         blk("The break", "A", 8, ["stab"], DR_C),
         blk("The Rhodes", "V", 16, ["lead", "stab", "bass"], DR_C + ["rim"]),
         blk("Hook", "A", 16, ["lead", "lead_hi", "vox", "pad", "stab", "bass"], DR_C + ["ride", "rim"], crash=True),
         blk("The melt", "B", 8, ["lead", "pad", "stab", "bass2"], ["hkick", "hsnare", "hghost", "hhat"]),
         blk("Re-forming", "B", 4, ["pad", "stab", "bass"], DR_C),
         blk("Verse", "V", 16, ["lead", "vox", "stab", "bass"], DR_C + ["rim"]),
         blk("Last hook", "A", 16, ["lead", "lead_hi", "vox", "pad", "stab", "bass"], DR_C + ["ride", "rim"], crash=True),
         blk("Long outro: Rhodes and organ", "A", 12, ["lead", "stab", "pad"], ["kick", "hat"])]
M, R = at(ARR_C, "The melt"), at(ARR_C, "Re-forming")
OUT_C = at(ARR_C, "Long outro: Rhodes and organ")
CHEESE = spec(
    "Cheese", "cheese", 2, "cheese/cheese-1463168861.am.json", 112, 0.6, ARR_C,
    ("Taste Tester, track 2: smooth and melty. F minor Fm9 - Dbmaj9 - Cm7, 112 bpm with a heavy swing, a brushed acoustic jazz kit "
     "with rimshots and a ride, an upright bass, Calf Organ 'Royale with Cheese', the Ice Rhodes as the lead (a vibraphone doubles it in "
     "the hooks), and 'the melt': the break goes half-time as the band melts under a closing filter, then re-forms."),
    {"harmony": {"rhythm": 1, "dominant": "keep", "colors": {"m": "m9", "m7": "m9", "7": "9", "": "maj7", "maj7": "maj9"}},
     "melody": {"register": [57, 76], "max_leap": 7, "max_notes_per_bar": 5, "articulation": "legato", "humanize_ms": 9, "velocity": [0.55, 0.92]},
     "bass": {"style": "pattern", "register": [36, 53],
              "pattern": [[0, "R", 0.4, 1.0], [3, "R", 0.15, 0.7], [6, "5", 0.2, 0.8], [8, "R", 0.35, 0.9], [11, "O", 0.15, 0.7], [14, "7", 0.25, 0.8]]},
     "bass2": {"style": "pattern", "register": [36, 53], "pattern": [[0, "R", 3.6, 0.85]]},
     "stab": {"steps": [0, 7, 10], "low": 55, "high": 75, "top": 72, "notes": 4, "gate": 0.3, "vel": 0.76, "accent": 0.88},
     "vox": {"steps": [3, 11, 14], "low": 60, "high": 78, "top": 72, "notes": 2, "gate": 0.22, "vel": 0.72, "accent": 0.85},
     "pad": {"low": 53, "high": 75, "top": 72, "notes": 4, "vel": 0.48},
     "grid": {"kick": {"a": [[0, 1.0], [10, 0.85]], "b": [[0, 1.0], [6, 0.7], [10, 0.85], [13, 0.5]],
                       "c": [[0, 1.0], [10, 0.85], [11, 0.6]], "d": [[0, 1.0], [7, 0.75], [10, 0.8]]},
              "snare": {"a": [[4, 0.9], [12, 0.92]], "b": [[4, 0.9], [12, 0.92]], "c": [[4, 0.9], [12, 0.92]], "d": [[4, 0.9], [12, 0.88], [15, 0.5]]},
              "ghost": {"a": [[2, 0.25], [7, 0.3], [9, 0.28], [14, 0.32], [15, 0.22]], "b": [[3, 0.26], [6, 0.22], [9, 0.3], [11, 0.28], [14, 0.3]],
                        "c": [[2, 0.24], [7, 0.3], [9, 0.26], [13, 0.3], [15, 0.24]], "d": [[3, 0.25], [6, 0.24], [9, 0.3], [14, 0.32]]},
              "hat": [[s, 0.45 if s % 4 == 0 else 0.3] for s in range(0, 16, 2)],
              "ride": [[s, 0.5 if s % 4 == 0 else 0.38] for s in range(0, 16, 2)],
              "rim": {"a": [[7, 0.4]], "b": [[3, 0.35], [11, 0.4]], "c": [[7, 0.4]], "d": [[11, 0.4], [14, 0.3]]},
              "hkick": [[0, 1.0, "kick"]], "hsnare": [[8, 0.9, "snare"]],                                           # the melt: half-time
              "hghost": {"a": [[5, 0.22, "ghost"], [11, 0.25, "ghost"], [14, 0.28, "ghost"]], "b": [[3, 0.22, "ghost"], [13, 0.26, "ghost"]]},
              "hhat": [[s, 0.4, "hat"] for s in (0, 4, 8, 12)]}},
    gated_kit(112, {"kick": (dm("acoustic/jazzkick"), "kick", None), "snare": (dm("acoustic/jazzsnr"), "break", None),
                    "ghost": (dm("acoustic/jazzsnr_h"), "break", {"gain_db": -6, "lp": 6000}),
                    "hat": (dm("acoustic/brush1"), "hats", None), "ride": (dm("acoustic/ride2"), "hats", {"gate": 30 / 48 * 60 / 112}),
                    "rim": (dm("tr808/rimshot"), "perc", None), "crash": (str(LD / "crash02.ogg"), "hats", {"gate": 24 / 48 * 60 / 112})},
              {"break": {"gain_db": -6.0}, "hats": {"gain_db": -1.4}}),            # the jazz snare and brushes measured 2-3 dB over the balance
    {"bass": (*zyn("the_mysterious_bank_4/0024-pseudo_doublebass.xiz", "pseudo_doublebass (ZynAddSubFX - the_mysterious_bank_4), upright"),
              dict(hp=35, lp=2500, drive=1.2, mono=True, duck={"depth": 0.2, "release": 0.12}, gain_db=-6.0)),
     "bass_sub": sub(),
     "stab": (*calf("Organ", "Royale with Cheese"), dict(hp=160, sends={"room": 0.2}, width=0.6, gain_db=-6.0)),   # the preset is wide on its own (measured -0.09)
     "lead": (*zyn("Rhodes/0013-Ice Rhodes2.xiz", "Ice Rhodes2 (ZynAddSubFX - Rhodes), the lead"),
              dict(hp=200, wow={"depth_ms": 0.3, "rate": 0.5, "flutter_ms": 0.03}, autopan={"rate_beats": 1.5, "depth": 0.3},
                   chorus={"depth_ms": 1.5, "rate": 0.5, "base_ms": 8, "mix": 0.2}, eq=[["peak", 2800, 2.0, 0.9], ["highshelf", 9000, 1.5]],
                   sends={"plate": 0.25, "echo": 0.18}, gain_db=-4.0)),
     "lead_hi": (*mallets(1, "Vibraphone (LMMS Mallets STK), doubling the Rhodes"), dict(hp=300, sends={"plate": 0.3, "echo": 0.15}, gain_db=-10.0)),
     "vox": CHOPS("0004-Voice OOH.xiz", "Voice OOH"),
     "pad": (*zyn("Pads/0065-Soft Pad.xiz", "Soft Pad (ZynAddSubFX - Pads)"), dict(hp=250, width=0.6, autopan={"rate_beats": 16, "depth": 0.25}, sends={"plate": 0.3}, gain_db=-12.0)),
     "bass2": (*zyn("Bass/0003-Bass 3 _analog_.xiz", "Bass 3 analog (ZynAddSubFX - Bass), the melt's long sub notes"), dict(hp=28, lp=160, mono=True, gain_db=-6.0))},
    {**TARGETS, "lead": -11.0, "lead_hi": -17.0},
    [{"type": "lowpass", "tracks": ["stab"], "points": [[1, 350], [8, 4000], [8.99, 9000], [9, 20000]]},
     {"type": "highpass", "tracks": ["kick", "break", "stab"], "points": [[16, 20], [16.95, 300], [17, 20]]},
     {"type": "highpass", "tracks": ["kick", "bass", "bass_sub", "stab", "lead", "break"], "points": [[31, 20], [32.95, 450], [33, 20]]},
     {"type": "lowpass", "tracks": ["stab", "pad", "lead", "hats", "perc", "break"],
      "points": [[M, 20000], [M + 4, 1500], [R - 0.05, 500], [R, 700], [R + 3.95, 8000], [R + 4, 20000]]},
     {"type": "lowpass", "tracks": ["kick", "hats", "stab", "pad"], "points": [[OUT_C + 4, 20000], [OUT_C + 12, 500]]}],
    "Hook", master={"eq": [["peak", 75, -2.0, 0.8], ["peak", 350, -2.5, 0.9], ["highshelf", 3500, 1.5], ["highshelf", 10000, -1.5]]})   # melty: a softer top
CHEESE["voices"]["vox"][2].update(autopan={"rate_beats": 2, "bars": [[33, 49, 0.5], [R + 4, OUT_C, 0.4]]})


# ================================================================== 3 Bread Roll: D minor, 121 bpm, rolling and bouncy, on our own break
BR_BPM = 121
SL = BM.OUT / f"slices_{BR_BPM}"
SLICES = {f"s{i:02d}": 88 + i for i in range(40)}           # beats 0-9 of the C-Lizzy break, one key per 16th slice
PR.GM.update(SLICES)


def bar(beats, vel=1.0):
    """a bar of break beats (four 16th slices each)"""
    return [[q * 4 + r, vel, f"s{4 * b + r:02d}"] for q, b in enumerate(beats) for r in range(4)]


ARR_B = [blk("Rolling bass alone", "A", 4, ["bass"]),
         blk("Hats", "A", 4, ["bass"], ["open", "tamb"]),
         blk("The break rolls in", "A", 8, ["bass"], ["brk", "open"], fill="roll16"),
         blk("Organ", "A", 8, ["stab", "bass"], ["brk", "open"], fill="toms"),
         blk("Piano and chops", "V", 16, ["comp", "stab", "bass", "vox"], ["brk", "open", "tamb"], fill="snare_roll"),
         blk("Hook", "A", 16, ["lead", "comp", "vox", "stab", "bass"], ["brk", "open", "tamb"], crash=True, fill="toms"),
         blk("Roll call", "B", 8, ["vox", "bass"], ["brk", "toms"]),
         blk("Build", "B", 8, ["comp", "stab", "vox"], ["open", "tamb", "toms"], fill="roll16"),
         blk("Second hook", "V", 16, ["lead", "comp", "vox", "stab", "bass"], ["brk", "open", "tamb"], crash=True),
         blk("Roll call, short", "B", 4, ["bass"], ["toms", "open"], fill="roll16"),
         blk("Last hook", "A", 16, ["lead", "comp", "vox", "stab", "bass"], ["brk", "open", "tamb"], crash=True, fill="snare_roll"),
         blk("Outro", "A", 8, ["bass"], ["brk", "open"])]
BUILD_B, LAST_B = at(ARR_B, "Build"), at(ARR_B, "Outro")


def bread_roll_kit():
    if not (SL / "s39.wav").exists():
        BM.make(BR_BPM)
    snd = {n: (str(SL / f"{n}.wav"), "break", {"detune_cents": 0}) for n in SLICES}
    snd["snare"] = (str(SL / "s04.wav"), "break", {"detune_cents": 0})     # rolls use the break's own snare
    snd |= {"open": (str(LD / "hihat_opened03.ogg"), "hats", None), "tamb": (dm("latin/tamb_shk"), "perc", None),
            "crash": (str(LD / "crash01.ogg"), "hats", {"gate": 24 / 48 * 60 / BR_BPM})}
    st = {}
    for t, f, p in (("tom_hi", "tom_hi01.ogg", -0.5), ("tom_mid", "tom_mid01.ogg", 0.0), ("tom_lo", "tom_low01.ogg", 0.5)):
        snd[t] = (str(LD / f), t, {"gate": 18 / 48 * 60 / BR_BPM})
        st[t] = {"hp": 60, "pan": p, "crush": CRUSH, "sends": {"room": 0.25}, "gain_db": -5.0}
    k = gated_kit(BR_BPM, snd, {**st, "break": {"hp": 45, "eq": [["lowshelf", 100, -5.0]], "drive": 1.3, "gain_db": -2.0}, "perc": {"gain_db": 9.4}})
    # (the sped-up break's kick peaks at 58 Hz and carried 95% of the low end: thinned, so the bass and sub hold the bottom)
    for n in list(SLICES) + ["snare"]:                       # slices are one 16th long already: no extra gate
        k["sounds"][n].pop("gate", None)
    return k


BREAD_ROLL = spec(
    "Bread Roll", "bread-roll", 3, "breadroll/breadroll-299719357.am.json", BR_BPM, 0.54, ARR_B,
    ("Taste Tester, track 3: rolling and bouncy. D minor Dm9 - Gm9 - Am7 - C6, 121 bpm, our own C-Lizzy break sped up and re-sliced, "
     "a rolling octave Calf Monosynth bass that opens the track alone, piano-house stabs on the off-beats, a Calf 'Transistor' organ, a "
     "whistle lead, and 'roll call': tom rolls sweeping across the stereo field."),
    {"harmony": {"rhythm": 1, "dominant": "keep", "colors": {"m": "m9", "m7": "m9", "7": "7"}},
     "melody": {"register": [67, 86], "max_leap": 7, "max_notes_per_bar": 6, "articulation": "detached", "humanize_ms": 6, "velocity": [0.65, 0.92]},
     "bass": {"style": "pattern", "register": [38, 55],
              "pattern": [[0, "R", 0.2, 1.0], [2, "O", 0.12, 0.7], [4, "R", 0.15, 0.85], [6, "O", 0.12, 0.7], [8, "R", 0.2, 0.95],
                          [10, "O", 0.12, 0.7], [11, "5", 0.12, 0.65], [12, "R", 0.15, 0.85], [14, "O", 0.12, 0.75], [15, "5", 0.1, 0.6]]},
     "stab": {"steps": [0, 11], "low": 57, "high": 77, "top": 74, "notes": 3, "gate": 0.2, "vel": 0.8, "accent": 0.9},
     "comp": {"steps": [2, 6, 10, 14], "low": 57, "high": 79, "top": 76, "notes": 4, "gate": 0.18, "vel": 0.72, "accent": 0.85},
     "vox": {"steps": [8, 13], "low": 62, "high": 80, "top": 74, "notes": 2, "gate": 0.2, "vel": 0.75, "accent": 0.85},
     "grid": {"brk": {"a": bar([0, 1, 2, 3]), "b": bar([4, 5, 6, 7]), "c": bar([0, 1, 8, 9]), "d": bar([4, 5, 2, 9])},
              "open": [[2, 0.42], [6, 0.38], [10, 0.42], [14, 0.4]],
              "tamb": [[s, 0.28 if s % 4 == 2 else 0.16] for s in range(2, 16, 2)],
              "toms": {"a": [[10, 0.55, "tom_hi"], [11, 0.5, "tom_hi"], [12, 0.6, "tom_mid"], [13, 0.55, "tom_mid"], [14, 0.65, "tom_lo"], [15, 0.7, "tom_lo"]],
                       "b": [[7, 0.45, "tom_lo"], [14, 0.5, "tom_mid"], [15, 0.55, "tom_hi"]]}}},
    bread_roll_kit(),
    {"bass": (*calf("Monosynth", "Cut Through Bass"), dict(hp=38, lp=4000, drive=1.3, mono=True, duck={"depth": 0.25, "release": 0.1}, gain_db=-6.0)),
     "bass_sub": sub(),
     "stab": (*calf("Organ", "Transistor"), dict(hp=180, sends={"room": 0.2, "echo": 0.1}, width=0.6, gain_db=-6.0)),
     "comp": (*zyn("SynthPiano/0005-Synth Piano1.xiz", "Synth Piano1 (ZynAddSubFX - SynthPiano), piano-house stabs"),
              dict(hp=200, eq=[["peak", 300, -2.0, 1.0]], sends={"room": 0.2, "plate": 0.1}, width=1.0, pan=-0.15, gain_db=-6.0)),
     "lead": (*xpf("TripleOscillator/Whistle.xpf", "Whistle (LMMS TripleOscillator)"), dict(hp=400, width=0.6, sends={"plate": 0.25, "echo": 0.2}, gain_db=-8.0)),
     "vox": CHOPS("0067-Vocal Morph 3.xiz", "Vocal Morph 3")},
    {"bass": -10.5, "bass_sub": -15.0, "stab": -12.5, "comp": -13.5, "lead": -12.5, "vox": -20.5},
    [{"type": "lowpass", "tracks": ["bass"], "points": [[1, 1200], [8.99, 5000], [9, 20000]]},
     {"type": "highpass", "tracks": ["break", "bass", "bass_sub", "stab", "comp", "vox"], "points": [[39, 20], [40.95, 450], [41, 20]]},
     {"type": "highpass", "tracks": ["hats", "perc"], "points": [[BUILD_B, 20], [BUILD_B + 7.95, 1500], [BUILD_B + 8, 20]]},
     {"type": "lowpass", "tracks": ["comp", "stab"], "points": [[BUILD_B, 800], [BUILD_B + 7.95, 20000]]},
     {"type": "lowpass", "tracks": ["bass", "bass_sub", "break", "hats", "perc"], "points": [[LAST_B, 20000], [LAST_B + 4, 3000], [LAST_B + 8, 400]]}],
    "Hook", level_ref="break",
    master={"eq": [["peak", 60, -2.5, 0.8], ["peak", 300, -1.0, 0.9], ["highshelf", 4000, -1.0], ["highshelf", 11000, 0.5]]})   # the break is bright already
BREAD_ROLL["voices"]["vox"][2].update(autopan={"rate_beats": 2, "bars": [[17, 33, 0.6], [33, 49, 0.35], [49, BUILD_B + 8, 0.55], [BUILD_B + 8, LAST_B, 0.35]]})


# ================================================================== 4 Pesto: G major, 124 bpm, fresh and herby
DR_P = ["kick", "snare", "ghost", "hat"]
ARR_P = [blk("The garden: pad and marimba", "A", 8, ["pad", "arp"]),
         blk("The break", "A", 8, ["arp"], DR_P + ["shaker"]),
         blk("Flute", "V", 16, ["lead", "arp", "stab", "bass"], DR_P + ["shaker", "open"]),
         blk("Chops", "V", 8, ["stab", "bass", "vox"], DR_P + ["open", "clap"]),
         blk("Hook", "A", 16, ["lead", "stab", "vox", "pad", "bass"], DR_P + ["open", "clap", "shaker"], crash=True),
         blk("The garden", "B", 16, ["pad", "arp", "vox"], ["hat", "shaker"]),
         blk("Hook again", "A", 16, ["lead", "stab", "vox", "pad", "arp", "bass"], DR_P + ["open", "clap", "shaker"], crash=True),
         blk("Flute and chops", "V", 8, ["lead", "vox", "stab", "bass"], DR_P + ["open", "clap"]),
         blk("Outro: marimba", "A", 8, ["arp", "pad"], ["hat", "shaker"])]
G, X = at(ARR_P, "The garden"), at(ARR_P, "Hook again")
OUT_P = at(ARR_P, "Outro: marimba")
ALL_P = ["kick", "break", "hats", "perc", "stab", "bass", "bass_sub", "vox", "lead", "pad", "arp"]
PESTO = spec(
    "Pesto", "pesto", 4, "pesto/pesto-1141562927.am.json", 124, 0.57, ARR_P,
    ("Taste Tester, track 4: fresh and herby, the album's one major key. G major Gmaj7 - Cmaj9 - Dadd9 (a borrowed C minor in the bridge), "
     "124 bpm, a TR-909 kit with shaker in a garage-style skip, a marimba arpeggio, a flute lead, a wah bass, Calf Organ 'Shamrock', "
     "and 'the garden': the drums thin to hats and shaker under the pad, marimba and chops, then a one-beat stop before the hook."),
    {"harmony": {"rhythm": 1, "dominant": "keep", "colors": {"": "maj7", "maj7": "maj9", "m": "m9", "m7": "m9", "7": "9"}},
     "melody": {"register": [67, 86], "max_leap": 7, "max_notes_per_bar": 5, "articulation": "legato", "humanize_ms": 8, "velocity": [0.6, 0.9]},
     "bass": {"style": "pattern", "register": [38, 55],
              "pattern": [[0, "R", 0.3, 1.0], [3, "O", 0.15, 0.7], [6, "R", 0.2, 0.85], [8, "5", 0.25, 0.85], [10, "R", 0.15, 0.75], [13, "O", 0.2, 0.8]]},
     "stab": {"steps": [2, 10], "low": 57, "high": 77, "top": 74, "notes": 4, "gate": 0.3, "vel": 0.75, "accent": 0.85},
     "vox": {"steps": [0, 7, 12], "low": 62, "high": 80, "top": 76, "notes": 2, "gate": 0.22, "vel": 0.75, "accent": 0.85},
     "pad": {"low": 55, "high": 79, "top": 76, "notes": 4, "vel": 0.5},
     "arp": {"pattern": [0, 2, 1, 3, 2, 1], "low": 62, "high": 84, "gate": 0.22, "rate": 0.5},
     "grid": {"kick": {"a": [[0, 1.0], [7, 0.75], [10, 0.85]], "b": [[0, 1.0], [3, 0.6], [10, 0.85]],
                       "c": [[0, 1.0], [7, 0.7], [9, 0.6]], "d": [[0, 1.0], [6, 0.7], [10, 0.85], [11, 0.6]]},
              "snare": {"a": [[4, 0.95], [12, 0.95]], "b": [[4, 0.95], [12, 0.95]], "c": [[4, 0.95], [12, 0.95]], "d": [[4, 0.95], [12, 0.9], [14, 0.6]]},
              "ghost": {"a": [[9, 0.25], [15, 0.3]], "b": [[7, 0.26], [13, 0.24]], "c": [[9, 0.25], [15, 0.3]], "d": [[3, 0.24], [7, 0.26]]},
              "hat": [[s, 0.55 if s % 4 == 0 else 0.42] for s in (0, 2, 3, 4, 6, 8, 10, 11, 12, 14)],
              "open": {"a": [], "b": [[14, 0.5]], "c": [], "d": [[6, 0.42], [14, 0.5]]},
              "clap": {"a": [], "b": [[12, 0.55]], "c": [], "d": [[12, 0.55]]},
              "shaker": [[s, 0.32 if s % 2 else 0.22] for s in range(16)]}},
    gated_kit(124, {"kick": (dm("tr909/kick_2"), "kick", None), "snare": (dm("tr909/snare2"), "break", None),
                    "ghost": (dm("tr909/snare"), "break", {"gain_db": -8, "lp": 6000}), "hat": (dm("tr909/hat-c"), "hats", None),
                    "open": (dm("tr909/hat-o"), "hats", None), "clap": (dm("tr909/tr909_clap"), "perc", None),
                    "shaker": (dm("latin/shaker_1"), "perc", None), "crash": (str(LD / "crash01.ogg"), "hats", {"gate": 24 / 48 * 60 / 124})},
              {"hats": {"gain_db": 7.3}, "perc": {"gain_db": 9.4}}),          # the 909 hats and shaker measured 7-8 dB under the balance
    {"bass": (*zyn("Bass/0033-Wah Bass.xiz", "Wah Bass (ZynAddSubFX - Bass)"), dict(hp=38, lp=4000, drive=1.2, mono=True, duck={"depth": 0.25, "release": 0.1}, gain_db=-6.0)),
     "bass_sub": sub(),
     "stab": (*calf("Organ", "Shamrock"), dict(hp=180, sends={"room": 0.2}, width=0.6, gain_db=-6.0)),
     "arp": (*mallets(0, "Marimba (LMMS Mallets STK), the arpeggio"), dict(hp=200, sends={"echo": 0.18, "room": 0.15}, autopan={"rate_beats": 4, "depth": 0.35}, gain_db=-8.0)),
     "lead": (*zyn("ReedAndWind/0001-Flute 1.xiz", "Flute 1 (ZynAddSubFX - ReedAndWind)"),     # it carried 54% of the 0.8-3 kHz band: de-honked
              dict(hp=300, eq=[["peak", 1200, -3.0, 1.0], ["peak", 3500, 1.5, 0.9], ["highshelf", 8000, 2.0]], sends={"plate": 0.3, "echo": 0.15}, gain_db=-6.0)),
     "vox": CHOPS("0065-Vocal Morph 1.xiz", "Vocal Morph 1"),
     "pad": (*zyn("Pads/0003-Analog Pad 1.xiz", "Analog Pad 1 (ZynAddSubFX - Pads)"), dict(hp=250, eq=[["peak", 1000, -2.0, 0.9]], width=1.0, autopan={"rate_beats": 16, "depth": 0.25}, sends={"plate": 0.3}, gain_db=-12.0))},
    {**TARGETS, "arp": -15.0, "lead": -12.5},
    [{"type": "lowpass", "tracks": ["pad", "arp"], "points": [[1, 600], [8, 5000], [8.99, 9000], [9, 20000]]},
     {"type": "highpass", "tracks": ["kick", "break", "bass", "bass_sub", "stab", "lead"], "points": [[39, 20], [40.95, 450], [41, 20]]},
     {"type": "lowpass", "tracks": ["pad", "arp", "vox"], "points": [[G, 20000], [G + 2, 2500], [G + 12, 2500], [X - 0.3, 20000]]},
     {"type": "gain", "tracks": ALL_P, "points": [[X - 0.26, 0], [X - 0.25, -60], [X - 0.01, -60], [X, 0]]},
     {"type": "lowpass", "tracks": ["arp", "pad", "hats", "perc"], "points": [[OUT_P + 2, 20000], [OUT_P + 8, 600]]}],
    "Hook", master={"eq": [["peak", 75, -2.0, 0.8], ["peak", 300, -1.0, 0.9], ["peak", 1500, -1.5, 0.8], ["highshelf", 3500, 2.0], ["highshelf", 10000, 3.0]]})   # fresh: more air, less honk
PESTO["voices"]["vox"][2].update(autopan={"rate_beats": 2, "bars": [[33, 41, 0.55], [41, 57, 0.35], [G, X, 0.6], [X, OUT_P, 0.35]]}, sends={"echo": 0.3, "plate": 0.25})


# ================================================================== 5 Anchovies: C minor, 126 bpm, salty, dark and dubby
DR_A = ["kick", "snare", "ghost", "hat"]
ARR_A = [blk("Salt", "A", 8, [], ["hat", "open", "cowbell", "rim"]),
         blk("Kick and bass", "A", 8, ["bass"], ["kick", "hat", "open"]),
         blk("The break", "A", 16, ["bass"], DR_A + ["open", "cowbell"]),
         blk("Dub organ", "V", 16, ["stab", "bass", "vox"], DR_A + ["open", "clap", "cowbell"]),
         blk("Dub-out", "B", 8, ["stab", "bass"], ["kick", "hat"]),
         blk("Melodica", "A", 16, ["lead", "stab", "vox", "pad", "bass"], DR_A + ["open", "clap", "cowbell", "rim"], crash=True),
         blk("Brine", "B", 8, ["pad", "stab", "vox"], DR_A + ["open"]),
         blk("Melodica again", "V", 16, ["lead", "stab", "vox", "pad", "bass"], DR_A + ["open", "clap", "cowbell", "rim"], crash=True),
         blk("Dub-out 2", "B", 8, ["stab", "bass", "lead"], ["kick", "hat"]),
         blk("Outro", "A", 8, ["bass"], ["kick", "hat", "open"])]
D1, D2, BR = at(ARR_A, "Dub-out"), at(ARR_A, "Dub-out 2"), at(ARR_A, "Brine")
MEL, OUT_A = at(ARR_A, "Melodica"), at(ARR_A, "Outro")
ANCHOVIES = spec(
    "Anchovies", "anchovies", 5, "anchovies/anchovies-1396395200.am.json", 126, 0.52, ARR_A,
    ("Taste Tester, track 5: salty, dark and dubby. C minor Cm9 - G - Abmaj7 - G, 126 bpm, a TR-808 crushed to 10 bits, a Calf Monosynth "
     "boom bass, Calf Organ 'Intertube' chords throwing dub echoes, a 'Melodica NOS' lead, opening on thin high-passed percussion, with "
     "two 'dub-outs' (only kick, bass and echoing organ) and a high-passed 'brine' build."),
    {"harmony": {"rhythm": 1, "dominant": "keep", "colors": {"m": "m9", "m7": "m9", "7": "7"}},
     "melody": {"register": [62, 82], "max_leap": 7, "max_notes_per_bar": 4, "articulation": "legato", "humanize_ms": 8, "velocity": [0.6, 0.9]},
     "bass": {"style": "pattern", "register": [36, 53],
              "pattern": [[0, "R", 0.5, 1.0], [6, "R", 0.2, 0.8], [10, "O", 0.15, 0.75], [11, "R", 0.3, 0.85], [14, "5", 0.2, 0.7]]},
     "stab": {"steps": [0, 10], "low": 55, "high": 75, "top": 72, "notes": 3, "gate": 0.18, "vel": 0.8, "accent": 0.9},
     "vox": {"steps": [6, 14], "low": 60, "high": 78, "top": 72, "notes": 2, "gate": 0.2, "vel": 0.75, "accent": 0.85},
     "pad": {"low": 53, "high": 75, "top": 70, "notes": 4, "vel": 0.45},
     "grid": {"kick": {"a": [[0, 1.0], [6, 0.8], [10, 0.9]], "b": [[0, 1.0], [3, 0.7], [6, 0.75], [10, 0.9]],
                       "c": [[0, 1.0], [6, 0.8], [11, 0.8]], "d": [[0, 1.0], [6, 0.75], [9, 0.65], [10, 0.9]]},
              "snare": {"a": [[4, 0.95], [12, 0.95]], "b": [[4, 0.95], [12, 0.95]], "c": [[4, 0.95], [12, 0.95]], "d": [[4, 0.95], [12, 0.95], [15, 0.6]]},
              "ghost": {"a": [[7, 0.28], [14, 0.3]], "b": [[9, 0.26]], "c": [[7, 0.28], [13, 0.26]], "d": [[2, 0.24], [9, 0.28]]},
              "hat": [[s, 0.55 if s % 4 == 0 else 0.4 if s % 2 == 0 else 0.28] for s in range(16)],
              "open": {"a": [[10, 0.45]], "b": [[10, 0.45]], "c": [[10, 0.45]], "d": [[2, 0.35], [10, 0.45]]},
              "clap": {"a": [], "b": [[12, 0.55]], "c": [], "d": [[12, 0.55], [14, 0.35]]},
              "cowbell": {"a": [[3, 0.3], [7, 0.25]], "b": [[11, 0.3]], "c": [[3, 0.3], [7, 0.25]], "d": [[11, 0.3], [15, 0.22]]},
              "rim": {"a": [[6, 0.35]], "b": [[14, 0.35]], "c": [[6, 0.35], [9, 0.25]], "d": [[14, 0.35]]}}},
    gated_kit(126, {"kick": (dm("tr808/kickhard"), "kick", None), "snare": (dm("tr808/snr_snap"), "break", None),
                    "ghost": (dm("tr808/snare"), "break", {"gain_db": -8, "lp": 5000}), "hat": (dm("tr808/hat_c"), "hats", None),
                    "open": (dm("tr808/hat_o"), "hats", None), "clap": (dm("tr808/handclap"), "perc", None),
                    "cowbell": (dm("tr808/cowbell"), "perc", None), "rim": (dm("tr808/rimshot"), "perc", None),
                    "crash": (str(LD / "crash02.ogg"), "hats", {"gate": 24 / 48 * 60 / 126})},
              {"kick": {"crush": {"bits": 10, "rate": 22050, "mix": 0.5}}, "hats": {"crush": {"bits": 10, "rate": 22050, "mix": 0.5}, "gain_db": 9.8},
               "break": {"crush": {"bits": 10, "rate": 22050, "mix": 0.5}, "drive": 1.8, "gain_db": -4.8}, "perc": {"gain_db": 6.4}}),   # 808 hats measured 9 dB under
    {"bass": (*calf("Monosynth", "Boom Bass"), dict(hp=40, lp=2500, drive=1.3, mono=True, duck={"depth": 0.3, "release": 0.1}, gain_db=-6.0)),
     "stab": (*calf("Organ", "Intertube"), dict(hp=180, sends={"echo": 0.45, "room": 0.15}, width=1.0, gain_db=-6.0)),
     "lead": (*calf("Organ", "Melodica NOS"), dict(hp=250, width=0.6, sends={"echo": 0.3, "plate": 0.2}, gain_db=-6.0)),
     "vox": CHOPS("0071-Vocal Morph 7.xiz", "Vocal Morph 7"),
     "pad": (*zyn("Pads/0009-Resonance Pad2.xiz", "Resonance Pad2 (ZynAddSubFX - Pads)"), dict(hp=250, lp=5000, width=1.0, sends={"plate": 0.3}, gain_db=-12.0))},
    {"bass": -9.5, "stab": -12.0, "pad": -16.0, "lead": -11.5, "vox": -20.0},
    [{"type": "highpass", "tracks": ["hats", "perc"], "points": [[1, 2500], [8, 400], [8.99, 150], [9, 20]]},
     {"type": "highpass", "tracks": ["kick", "bass", "stab", "vox", "break"], "points": [[D1 + 6, 20], [D1 + 7.95, 450], [D1 + 8, 20]]},
     {"type": "highpass", "tracks": ["break", "hats", "perc", "pad", "stab"], "points": [[BR, 20], [BR + 7.95, 1200], [BR + 8, 20]]},
     {"type": "lowpass", "tracks": ["bass", "kick", "hats"], "points": [[OUT_A, 20000], [OUT_A + 4, 2500], [OUT_A + 8, 300]]}],
    "Melodica", layers=(), master={"eq": [["peak", 45, -3.0, 0.8], ["peak", 300, -1.0, 0.9], ["highshelf", 3500, 2.5], ["highshelf", 11000, 1.5]]},   # the 808 + boom bass piled up under 60 Hz
    sends={"echo": {"type": "delay", "time_beats": 0.75, "feedback": 0.48, "taps": 8, "tone": 2200}})
ANCHOVIES["voices"]["stab"][2].update(autopan={"rate_beats": 3, "bars": [[D1, D1 + 8, 0.55], [D2, D2 + 8, 0.55]]})
ANCHOVIES["voices"]["vox"][2].update(autopan={"rate_beats": 2, "bars": [[25, 41, 0.55], [MEL, OUT_A, 0.35]]})


# ================================================================== 6 Marinara: A minor, 108 bpm, a slow simmer, a short song
DR_M = ["kick", "snare", "hat"]
ARR_M = [blk("Guitar alone", "A", 4, ["arp"]),
         blk("Piano and guitar", "A", 4, ["arp", "comp"], ["conga"]),
         blk("The break", "A", 8, ["arp", "comp", "bass"], DR_M + ["conga", "cabasa"]),
         blk("Verse: accordion", "V", 16, ["lead", "comp", "bass", "pad"], DR_M + ["conga", "cabasa", "clap"]),
         blk("Chorus", "A", 16, ["lead", "comp", "vox", "pad", "bass", "arp"], DR_M + ["conga", "cabasa", "clap", "open"], crash=True),
         blk("Bridge: congas and bongos", "B", 8, ["comp", "pad", "bass"], ["conga", "bongo", "cabasa", "hat"]),
         blk("Chorus again", "A", 16, ["lead", "comp", "vox", "pad", "bass", "arp"], DR_M + ["conga", "cabasa", "clap", "open"], crash=True),
         blk("Coda: guitar and accordion", "A", 8, ["arp", "lead", "pad"], ["conga", "hat"])]
BRIDGE_M, CH2_M, CODA = at(ARR_M, "Bridge: congas and bongos"), at(ARR_M, "Chorus again"), at(ARR_M, "Coda: guitar and accordion")
MARINARA = spec(
    "Marinara", "marinara", 6, "marinara2/marinara2-1048998005.am.json", 108, 0.58, ARR_M,
    ("Taste Tester, track 6: a slow simmer, and the album's one short song form. C# minor C#m9 - F#m9 - F#sus4 - G# (an Amaj7 lift in the "
     "verse and bridge), 108 bpm, a LinnDrum with congas, cabasa and bongos, a nylon guitar arpeggio that opens it alone, "
     "Italo-house piano, an accordion lead, an analogue bass and Calf Organ 'Rusty Keys' holding the chords."),
    {"harmony": {"rhythm": 1, "dominant": "keep", "colors": {"m": "m9", "m7": "m9", "7": "7", "": "maj7"}},
     "melody": {"register": [64, 84], "max_leap": 7, "max_notes_per_bar": 5, "articulation": "legato", "humanize_ms": 9, "velocity": [0.6, 0.92]},
     "bass": {"style": "pattern", "register": [36, 53],
              "pattern": [[0, "R", 0.4, 1.0], [3, "5", 0.15, 0.7], [6, "R", 0.2, 0.8], [8, "O", 0.3, 0.85], [11, "5", 0.2, 0.75], [14, "R", 0.2, 0.8]]},
     "comp": {"steps": [0, 3, 6, 10], "low": 57, "high": 79, "top": 76, "notes": 4, "gate": 0.22, "vel": 0.74, "accent": 0.88},
     "vox": {"steps": [8, 14], "low": 62, "high": 80, "top": 74, "notes": 2, "gate": 0.22, "vel": 0.72, "accent": 0.85},
     "pad": {"low": 52, "high": 72, "top": 69, "notes": 4, "vel": 0.42},
     "arp": {"pattern": [0, 1, 2, 3, 2, 1], "low": 52, "high": 76, "gate": 0.3, "rate": 0.5},
     "grid": {"kick": {"a": [[0, 1.0], [7, 0.8], [10, 0.85]], "b": [[0, 1.0], [10, 0.85], [13, 0.6]],
                       "c": [[0, 1.0], [7, 0.75], [10, 0.85]], "d": [[0, 1.0], [6, 0.7], [10, 0.85], [11, 0.55]]},
              "snare": [[4, 0.95], [12, 0.95]],
              "hat": [[s, 0.5 if s % 4 == 0 else 0.36] for s in range(0, 16, 2)],
              "open": {"a": [], "b": [[14, 0.45]], "c": [], "d": [[14, 0.45]]},
              "clap": {"a": [], "b": [[12, 0.5]], "c": [], "d": [[12, 0.5]]},
              "cabasa": [[s, 0.3 if s % 2 else 0.2] for s in range(16)],
              "conga": {"a": [[3, 0.55, "conga_hi"], [6, 0.6, "conga_lo"], [7, 0.45, "conga_hi"], [11, 0.55, "conga_hi"], [14, 0.65, "conga_lo"], [15, 0.45, "conga_hi"]],
                        "b": [[3, 0.55, "conga_hi"], [6, 0.6, "conga_lo"], [10, 0.5, "conga_hi"], [11, 0.55, "conga_hi"], [14, 0.65, "conga_lo"]]},
              "bongo": [[s, 0.55 if s % 4 == 0 else 0.4, "bongo_hi" if s % 3 else "bongo_lo"] for s in (0, 2, 3, 5, 6, 8, 10, 11, 13, 14)]}},
    gated_kit(108, {"kick": (dm("linn/linn_kik"), "kick", None), "snare": (dm("linn/linn_snr"), "break", None),
                    "hat": (str(LD / "hihat_closed04.ogg"), "hats", None), "open": (str(LD / "hihat_opened01.ogg"), "hats", None),
                    "clap": (dm("linn/linn_clp"), "perc", None), "cabasa": (dm("linn/linn_cab"), "hats", {"gain_db": -4}),
                    "conga_hi": (dm("linn/linn_cga1"), "congas", None), "conga_lo": (dm("linn/linn_cga3"), "congas", None),
                    "bongo_hi": (dm("latin/bongo_h"), "bongos", None), "bongo_lo": (dm("latin/bongo_l"), "bongos", None),
                    "crash": (str(LD / "crash02.ogg"), "hats", {"gate": 24 / 48 * 60 / 108})},
              {"congas": {"pan": -0.4, "crush": CRUSH, "sends": {"room": 0.2}, "gain_db": -1.5},
               "bongos": {"pan": 0.4, "crush": CRUSH, "sends": {"room": 0.2}, "gain_db": -2.5},
               "break": {"gain_db": -13.7}, "perc": {"gain_db": -2.3}, "hats": {"gain_db": 4.7}}, ticks=12),   # the Linn snare and clap measured hot, hats low
    {"bass": (*zyn("Bass/0006-Analogue Bass.xiz", "Analogue Bass (ZynAddSubFX - Bass)"), dict(hp=38, lp=3500, drive=1.2, mono=True, duck={"depth": 0.25, "release": 0.1}, gain_db=-6.0)),
     "bass_sub": sub(),
     "comp": (*zyn("SynthPiano/0067-Synth Piano 3.xiz", "Synth Piano 3 (ZynAddSubFX - SynthPiano), Italo piano"),
              dict(hp=180, eq=[["peak", 300, -2.0, 1.0], ["peak", 3000, 1.5, 0.9]], sends={"room": 0.2, "plate": 0.12}, width=0.6, pan=-0.15, gain_db=-6.0)),
     "pad": (*calf("Organ", "Rusty keys"), dict(hp=200, lp=6000, sends={"plate": 0.25}, width=0.5, gain_db=-10.0)),     # measured -0.26 at width 1
     "arp": (*zyn("Collection/0108-Nylon Guitar.xiz", "Nylon Guitar (ZynAddSubFX - Collection), the arpeggio"), dict(hp=120, sends={"room": 0.2, "plate": 0.15}, pan=0.2, gain_db=-8.0)),
     "lead": (*zyn("Cormi_Sound/0095-Accordian.xiz", "Accordian (ZynAddSubFX - Cormi_Sound)"), dict(hp=250, width=0.6, eq=[["peak", 350, -1.5, 1.0]], sends={"plate": 0.22, "echo": 0.12}, gain_db=-6.0)),
     "vox": CHOPS("0070-Vocal Morph 6.xiz", "Vocal Morph 6")},
    {**TARGETS, "comp": -12.5, "arp": -15.0, "pad": -16.0},
    [{"type": "lowpass", "tracks": ["arp"], "points": [[1, 2500], [4.99, 8000], [5, 20000]]},
     {"type": "highpass", "tracks": ["kick", "break", "bass", "bass_sub", "comp"], "points": [[31, 20], [32.95, 400], [33, 20]]},
     {"type": "lowpass", "tracks": ["comp", "pad"], "points": [[BRIDGE_M, 1500], [CH2_M - 0.05, 20000]]},
     {"type": "lowpass", "tracks": ["arp", "lead", "pad", "congas", "hats"], "points": [[CODA + 4, 20000], [CODA + 8, 700]]}],
    "Chorus", master={"eq": [["peak", 75, -2.0, 0.8], ["peak", 350, -3.0, 0.9], ["highshelf", 3500, 3.5], ["highshelf", 11000, 2.0]]})
MARINARA["voices"]["vox"][2].update(autopan={"rate_beats": 2, "depth": 0.45})


# ================================================================== 7 Meatball: G minor, 128 bpm, hearty and chunky, the closer
DR_X = ["kick", "snare", "ghost", "hat", "clap"]
ARR_X = [blk("The whole table, through the door", "A", 8, ["stab", "bass", "pad"], DR_X + ["open"]),
         blk("Groove", "V", 16, ["stab", "bass", "vox"], DR_X + ["open"], fill="toms"),
         blk("Brass hook", "A", 16, ["lead", "stab", "bass", "vox", "pad"], DR_X + ["open", "ride"], crash=True, fill="toms"),
         blk("Simmer", "B", 8, ["pad", "vox", "stab"], ["hat", "ride"]),
         blk("Roll", "B", 4, ["pad", "stab"], ["hat"], fill="roll16"),
         blk("Big hook", "A", 16, ["lead", "stab", "bass", "vox", "pad"], DR_X + ["open", "ride"], crash=True, fill="toms"),
         blk("Second theme", "V", 16, ["lead", "stab", "bass", "pad"], DR_X + ["open"], fill="snare_roll"),
         blk("Final hook", "A", 16, ["lead", "stab", "bass", "vox", "pad"], DR_X + ["open", "ride"], crash=True),
         blk("Outro: Pepperoni's organ comes back", "A", 12, ["comp", "bass", "pad"], ["kick", "hat", "ride"])]
OUT_X = at(ARR_X, "Outro: Pepperoni's organ comes back")
MEATBALL = spec(
    "Meatball", "meatball", 7, "meatball/meatball-770599851.am.json", 128, 0.53, ARR_X,
    ("Taste Tester, track 7, the closer: hearty and chunky. G minor Gm9 - Ebmaj7 - D7, 128 bpm, the album's fastest, a heavy acoustic kit "
     "with clap-doubled snares, a ride and big tom fills, a round Calf Monosynth 'Fat Bass', Calf Organ 'Fat Belly', Zyn 'Fat Brass' "
     "carrying the hook; it opens on the whole band heard through a door, and closes with Pepperoni's 'Std Jimmy' organ coming back."),
    {"harmony": {"rhythm": 1, "dominant": "keep", "colors": {"m": "m9", "m7": "m9", "7": "7", "": "maj7"}},
     "melody": {"register": [62, 82], "max_leap": 7, "max_notes_per_bar": 5, "articulation": "detached", "humanize_ms": 6, "velocity": [0.7, 0.95]},
     "bass": {"style": "pattern", "register": [36, 53],
              "pattern": [[0, "R", 0.35, 1.0], [3, "R", 0.15, 0.75], [6, "O", 0.2, 0.85], [8, "R", 0.3, 0.95], [11, "5", 0.15, 0.75], [13, "R", 0.15, 0.7], [14, "O", 0.2, 0.85]]},
     "stab": {"steps": [0, 3, 8, 11], "low": 55, "high": 76, "top": 72, "notes": 4, "gate": 0.2, "vel": 0.8, "accent": 0.92},
     "comp": {"steps": [0, 3, 10], "low": 57, "high": 77, "top": 74, "notes": 4, "gate": 0.22, "vel": 0.78, "accent": 0.88},
     "vox": {"steps": [6, 14], "low": 60, "high": 79, "top": 74, "notes": 2, "gate": 0.2, "vel": 0.75, "accent": 0.85},
     "pad": {"low": 53, "high": 77, "top": 72, "notes": 4, "vel": 0.48},
     "grid": {"kick": {"a": [[0, 1.0], [6, 0.8], [10, 0.9]], "b": [[0, 1.0], [3, 0.7], [10, 0.9], [14, 0.6]],
                       "c": [[0, 1.0], [6, 0.8], [8, 0.7], [10, 0.9]], "d": [[0, 1.0], [6, 0.8], [11, 0.75], [14, 0.6]]},
              "snare": {"a": [[4, 1.0], [12, 1.0]], "b": [[4, 1.0], [12, 1.0]], "c": [[4, 1.0], [12, 1.0]], "d": [[4, 1.0], [12, 0.95], [15, 0.6]]},
              "clap": [[4, 0.6], [12, 0.65]],
              "ghost": {"a": [[7, 0.3], [9, 0.26], [15, 0.32]], "b": [[2, 0.24], [9, 0.3]], "c": [[7, 0.3], [13, 0.28]], "d": [[3, 0.26], [9, 0.3], [11, 0.24]]},
              "hat": [[s, 0.55 if s % 4 == 0 else 0.42 if s % 2 == 0 else 0.3] for s in range(16)],
              "open": {"a": [[6, 0.4]], "b": [[14, 0.45]], "c": [[6, 0.4]], "d": [[6, 0.4], [14, 0.45]]},
              "ride": [[s, 0.5 if s % 4 == 0 else 0.4] for s in range(0, 16, 2)]}},
    gated_kit(128, {"kick": (str(LD / "kick_hard01.ogg"), "kick", None), "snare": (str(LD / "snare_acoustic01.ogg"), "break", None),
                    "ghost": (str(LD / "snare05.ogg"), "break", {"gain_db": -8, "lp": 6000}), "clap": (str(LD / "clap01.ogg"), "perc", None),
                    "hat": (str(LD / "hihat_closed05.ogg"), "hats", None), "open": (str(LD / "hihat_opened02.ogg"), "hats", None),
                    "ride": (str(LD / "ride01.ogg"), "hats", {"gate": 30 / 48 * 60 / 128, "gain_db": -3}),
                    "tom_hi": (str(LD / "tom01.ogg"), "toms", {"gate": 18 / 48 * 60 / 128}), "tom_mid": (str(LD / "tom03.ogg"), "toms", {"gate": 18 / 48 * 60 / 128}),
                    "tom_lo": (str(LD / "tom05.ogg"), "toms", {"gate": 18 / 48 * 60 / 128}),
                    "crash": (str(LD / "crash01.ogg"), "hats", {"gate": 30 / 48 * 60 / 128})},
              {"toms": {"hp": 60, "crush": CRUSH, "sends": {"room": 0.3}, "width": 1.0, "gain_db": -10.0},
               "break": {"gain_db": -12.2}, "perc": {"gain_db": -2.3}}),      # the acoustic snare measured 9 dB over the balance, clap 4, toms 9
    {"bass": (*calf("Monosynth", "Fat Bass"), dict(hp=32, lp=3500, drive=1.3, mono=True, duck={"depth": 0.3, "release": 0.1}, gain_db=-6.0)),
     "bass_sub": sub(),
     "stab": (*calf("Organ", "Fat Belly"), dict(hp=170, sends={"room": 0.2}, width=0.5, gain_db=-6.0)),      # measured -0.41 at width 1
     "lead": (*zyn("Brass/0066-Fat Brass.xiz", "Fat Brass (ZynAddSubFX - Brass), the hook"), dict(hp=200, eq=[["peak", 2200, 1.5, 0.9]], sends={"plate": 0.22, "echo": 0.1}, gain_db=-6.0)),
     "comp": (*calf("Organ", "Std Jimmy"), dict(hp=160, sends={"room": 0.2}, width=1.0, autopan={"rate_beats": 4, "depth": 0.3}, gain_db=-6.0)),
     "vox": CHOPS("0066-Vocal Morph 2.xiz", "Vocal Morph 2"),
     "pad": (*xpf("TripleOscillator/PowerStrings.xpf", "PowerStrings (LMMS TripleOscillator)"), dict(hp=250, lp=8000, width=0.6, autopan={"rate_beats": 16, "depth": 0.2}, sends={"plate": 0.3}, gain_db=-12.0))},
    {**TARGETS, "comp": -12.0},
    [{"type": "lowpass", "tracks": ["kick", "break", "hats", "perc", "stab", "bass", "bass_sub", "pad"], "points": [[1, 300], [6, 1200], [8.95, 6000], [9, 20000]]},
     {"type": "highpass", "tracks": ["kick", "break", "bass", "bass_sub", "stab"], "points": [[24, 20], [24.95, 350], [25, 20]]},
     {"type": "lowpass", "tracks": ["pad", "stab", "vox"], "points": [[at(ARR_X, "Simmer"), 2500], [at(ARR_X, "Roll") + 3.95, 20000]]},
     {"type": "highpass", "tracks": ["hats", "pad", "stab"], "points": [[at(ARR_X, "Roll"), 20], [at(ARR_X, "Roll") + 3.95, 1200], [at(ARR_X, "Roll") + 4, 20]]},
     {"type": "highpass", "tracks": ["kick", "bass", "bass_sub"], "points": [[84, 20], [84.95, 350], [85, 20]]},
     {"type": "lowpass", "tracks": ["kick", "hats", "bass", "bass_sub", "comp", "pad"], "points": [[OUT_X + 4, 20000], [OUT_X + 12, 400]]}],
    "Brass hook")
MEATBALL["voices"]["vox"][2].update(autopan={"rate_beats": 2, "bars": [[9, 25, 0.55], [25, OUT_X, 0.35]]})

# ================================================================== the melody writer (melodist.py), 2026-10-16
# every remade track's lead is written (motif, phrase plan, chord tones on strong beats) rather than filtered from the composer,
# with its own rhythm character, and varies on each pass; breakdowns take the sparse variant, last hooks the lift
WRITER = {"cheese": "smooth", "bread-roll": "bouncy", "pesto": "fresh", "anchovies": "dub", "marinara": "latin"}
VARS = {"cheese": {"The melt": "sparse", "Last hook": "lift", "Long outro: Rhodes and organ": "sparse"},
        "bread-roll": {"Last hook": "lift"},
        "pesto": {"Hook again": "lift", "Flute and chops": "answer"},
        "anchovies": {"Dub-out 2": "sparse", "Melodica again": "lift"},
        "marinara": {"Chorus again": "lift", "Coda: guitar and accordion": "sparse"}}
for _slug, _sp in (("cheese", CHEESE), ("bread-roll", BREAD_ROLL), ("pesto", PESTO), ("anchovies", ANCHOVIES), ("marinara", MARINARA)):
    _sp["overrides"]["melody"].update({"writer": "motif", "rhythm": WRITER[_slug], "range_min": 12})
    for _b in _sp["overrides"]["arrangement"]:
        if _b["name"] in VARS[_slug]:
            _b["lead_var"] = VARS[_slug][_b["name"]]

PESTO["seed"] = 6              # the best of ten melody seeds by melody_metrics.score (6.50; seed 1 gave 5.66)

SPECS = {"cheese": CHEESE, "bread-roll": BREAD_ROLL, "pesto": PESTO, "anchovies": ANCHOVIES, "marinara": MARINARA, "meatball": MEATBALL}

if __name__ == "__main__":
    want = [a for a in sys.argv[1:] if not a.startswith("-")] or list(SPECS)
    for k in want:
        LT.make(SPECS[k], log=lambda m: print(m, flush=True))
