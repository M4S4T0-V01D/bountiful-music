#!/usr/bin/env python3
"""'Mezzanine Sessions' (second version): M4S4T0, composed by C-Lizzy. Testimony is kept; the other eight are each
a different corner of house music, with their own tempo, drum machine, beat, opening, arrangement and LMMS sounds.
Pepperoni (formerly Breakbeat Lobby) left this album on 2026-10-16 for its own, 'Taste Tester' (bountiful/album_taste_tester.py);
its spec stays here because its builds (and lobby_v2.py) use it. Testimony left too (2026-10-16), renamed Crushed Red Pepper, for Taste Tester; the running order is the list below without both.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/album_mezzanine_v2.py [slug ...]   # build tracks
    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/album_mezzanine_v2.py --assemble    # album folder

  2 Sunday Service   NJ gospel garage      120 bpm  D major   solo piano + choir opening, shuffled garage beat, +1 key lift
  3 Acid Corridor    Chicago acid house    128 bpm  A minor   the 303 alone, raw TR-909 / TR-606, a filter that opens all song
  4 Low Light        slow deep house       112 bpm  D minor   pads and CR-78 rimshots, Larry Heard-style lushness
  - Pepperoni        breakbeat house       116 bpm  B minor   (own album now: Taste Tester)
  6 Drum Ritual      tribal house          131 bpm  E minor   congas alone, toms/bongos/timbales leading, a chanted vamp
  7 Skyline          Italo piano house     126 bpm  G major   the piano hook alone, LinnDrum, galloping bass, arpeggio
  8 Last Call        NY dub house          134 bpm  C# minor  echoing stabs into silence, crushed TR-909, melodica, sub
  9 Night Bus        downtempo lounge       98 bpm  Bb major  Rhodes alone, lazy boom-bap, vibraphone, walking upright bass
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import album_mezzanine as V1  # noqa: E402
import lmms_tracks as LT  # noqa: E402
import producer as PR  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DM = ROOT / "samples" / "drummachines"
LMMS_DRUMS = Path("/usr/share/lmms/samples/drums")
ALBUM, ARTIST, COMPOSER, YEAR = V1.ALBUM, V1.ARTIST, V1.COMPOSER, V1.YEAR
SONGS = ROOT / "songs" / "album2"


def dm(path):
    return str(DM / f"{path}.wav")


def kit(sounds: dict, stems: dict) -> dict:
    """sounds: name -> (sample path, stem, extra dict)."""
    return {"map": {str(PR.GM[n]): n for n in sounds},
            "sounds": {n: {"samples": [p], "stem": st, "detune_cents": 6, **(ex or {})} for n, (p, st, ex) in sounds.items()},
            "stems": stems}


def zyn(path, label):
    return {"zyn": path}, label.replace("/", "-")


def calf(plugin, preset):
    return {"lv2": f"calf:{plugin}", "preset": preset}, f"{preset} (Calf {plugin})"


def xpf(path, label):
    return {"xpf": path}, label


def sub(gain=-12.0):
    return (*zyn("Bass/0003-Bass 3 _analog_.xiz", "Bass 3 analog (ZynAddSubFX - Bass), sub"),
            dict(hp=28, lp=150, mono=True, duck={"depth": 0.35, "release": 0.1}, gain_db=gain))


def blk(name, loop, bars, parts=(), drums=(), **kw):
    return {"name": name, "loop": loop, "bars": bars, "parts": list(parts), "drums": list(drums), **kw}


def song_file(slug, seed):
    return SONGS / slug / f"album2-{slug}-{seed}.am.json"


def bars_upto(arr, name):
    return 1 + sum(b["bars"] for b in arr[:[b["name"] for b in arr].index(name)])


def common(title, track, slug, seed, base, blurb):
    return {"title": title, "track": track, "song": song_file(slug, seed), "genre": base, "blurb": blurb,
            "rebuild": f"bountiful/album_mezzanine_v2.py {slug}", "composer": COMPOSER, "artist": ARTIST, "album": ALBUM, "year": YEAR}


SPECS = {}

# ------------------------------------------------------------------ 2. Sunday Service: NJ gospel garage, 120, D major
ARR = [blk("Piano and choir", "A", 8, ["comp", "pad"]),
       blk("Drums enter", "A", 8, ["comp", "pad"], ["kick", "clap", "hat", "tamb"]),
       blk("Organ bass", "A", 16, ["bass", "comp"], ["kick", "clap", "hat", "tamb", "rim"], fill="toms"),
       blk("Verse", "V", 16, ["bass", "comp", "lead"], ["kick", "clap", "hat", "tamb", "rim", "open"], fill="snare_roll"),
       blk("Chorus", "A", 16, ["bass", "comp", "vox", "lead", "pad"], ["kick", "clap", "hat", "tamb", "rim", "open"], crash=True, fill="toms"),
       blk("Bridge", "B", 8, ["bass", "comp", "pad"], ["kick", "tamb"]),
       blk("Chorus 2", "A", 16, ["bass", "comp", "vox", "lead", "pad"], ["kick", "clap", "hat", "tamb", "rim", "open"], crash=True),
       blk("Church breakdown", "A", 8, ["comp", "vox", "pad"]),
       blk("Last chorus, up a half step", "A", 16, ["bass", "comp", "vox", "lead", "pad"], ["kick", "clap", "hat", "tamb", "rim", "open"], crash=True, transpose=1),
       blk("Outro", "A", 8, ["comp", "pad"], ["kick", "hat", "tamb"], transpose=1)]
SPECS["sunday-service"] = {
    **common("Sunday Service", 2, "sunday-service", 1131350256, "ny-house-93",
             "NJ gospel garage: D major Dmaj7 - Em9 - Aadd9, a solo piano and choir opening, a shuffled garage beat with a skipping kick, "
             "rimshots and tambourine, an M1 organ bass, a gospel organ melody, full-choir stabs, the last chorus lifted a half step."),
    "overrides": {"bpm": 120, "swing": 0.58, "drums": "grid", "arrangement": ARR,
                  "harmony": {"rhythm": 2, "dominant": "keep", "colors": {"": "maj9", "m": "m9", "7": "9", "m7": "m9", "maj7": "maj9", "sus4": "7sus4"}},
                  "melody": {"register": [65, 86], "max_leap": 7, "max_notes_per_bar": 6, "articulation": "legato", "humanize_ms": 6, "velocity": [0.62, 0.92]},
                  "bass": {"style": "pattern", "register": [33, 52], "pattern": [[0, "R", 0.4], [3, "R", 0.2], [6, "O", 0.25], [8, "R", 0.3], [10, "5", 0.2], [11, "R", 0.2], [14, "O", 0.3]]},
                  "comp": {"steps": [0, 3, 7, 10, 14], "low": 55, "high": 76, "top": 74, "notes": 4, "gate": 0.3, "humanize_ms": 6, "swing": 0.58},
                  "vox": {"steps": [6, 14], "low": 62, "high": 81, "top": 77, "notes": 3, "gate": 0.35, "vel": 0.75, "accent": 0.82},
                  "pad": {"low": 55, "high": 79, "top": 76, "notes": 4, "vel": 0.5},
                  "grid": {"kick": {"A": [[0, 1], [4, 1], [8, 1], [12, 1]], "B": [[0, 1], [4, 1], [8, 1], [11, 0.65], [12, 1]]},
                           "clap": [[4, 0.9], [12, 0.95]],
                           "rim": {"A": [[3, 0.5], [10, 0.45]], "B": [[3, 0.5], [7, 0.4], [13, 0.45]]},
                           "hat": [[s, 0.62 if s % 4 == 2 else 0.3] for s in range(16) if s % 4 != 0],
                           "open": {"A": [], "B": [[14, 0.5]]},
                           "tamb": [[s, 0.42 if s % 4 == 2 else 0.3] for s in range(0, 16, 2)]}},
    "kit_def": kit({"kick": (dm("tr909/kick"), "kick", None), "clap": (dm("tr909/clap"), "clap", None), "snare": (dm("tr909/snare2"), "clap", None),
                    "rim": (dm("tr808/rimshot"), "perc", None), "hat": (dm("tr909/hat-c"), "hats", None), "open": (dm("tr909/hat-o"), "hats", None),
                    "tamb": (dm("latin/tamb_shk"), "perc", None), "crash": (dm("tr606/tr606_cymbal"), "crash", None),
                    "tom_hi": (dm("tr808/tom_hi"), "toms", None), "tom_mid": (dm("tr808/tom_mid"), "toms", None), "tom_lo": (dm("tr808/tom_lo"), "toms", None)},
                   {"kick": {"hp": 30, "mono": True, "gain_db": -3.0}, "clap": {"hp": 200, "sends": {"room": 0.25}, "gain_db": -6.0},
                    "hats": {"pan": 0.2, "gain_db": -8.0}, "perc": {"pan": -0.25, "sends": {"room": 0.2}, "gain_db": -9.0},
                    "crash": {"gain_db": -15.0}, "toms": {"sends": {"room": 0.25}, "gain_db": -8.0}}),
    "layers": [("bass", "bass_sub")],
    "voices": {"bass": (*zyn("Organ/0002-Organ 2.xiz", "Organ 2 (ZynAddSubFX - Organ), organ bass"), dict(hp=38, lp=3200, drive=1.2, mono=True, duck={"depth": 0.3, "release": 0.1}, gain_db=-6.0)),
               "bass_sub": sub(),
               "comp": (*zyn("Collection/0110-Home Piano.xiz", "Home Piano (ZynAddSubFX - Collection)"), dict(hp=120, eq=[["peak", 300, -2.0, 1.0]], width=0.8, sends={"room": 0.25, "plate": 0.12}, gain_db=-6.0)),
               "lead": (*calf("Organ", "Gates of dawn"), dict(hp=150, leslie={"speed": [[1, 1]], "crossover": 800, "mix": 0.6}, sends={"plate": 0.25}, gain_db=-6.0)),
               "vox": (*zyn("Collection/0119-Full Choir.xiz", "Full Choir (ZynAddSubFX - Collection), stabs"), dict(hp=250, width=0.8, sends={"plate": 0.35}, gain_db=-8.0)),
               "pad": (*zyn("ChoirAndVoice/0034-Slow Morph_Choir.xiz", "Slow Morph_Choir (ZynAddSubFX - ChoirAndVoice)"), dict(hp=220, width=0.9, sends={"plate": 0.4}, gain_db=-12.0))},
    "targets": {"bass": -7.0, "bass_sub": -17.0, "comp": -7.0, "lead": -8.0, "vox": -11.0, "pad": -15.0},
    "test_bars": (bars_upto(ARR, "Chorus"), bars_upto(ARR, "Chorus") + 7),
}

# ------------------------------------------------------------------ 3. Acid Corridor: Chicago acid house, 128, A minor
ARR = [blk("303 alone", "A", 8, ["bass"], ["hat"]),
       blk("Kick in", "A", 16, ["bass"], ["kick", "hat"]),
       blk("Clap and open hats", "A", 16, ["bass"], ["kick", "clap", "hat", "open"], fill="snare_roll"),
       blk("Stabs", "A", 24, ["bass", "stab", "bass_sub"], ["kick", "clap", "hat", "open"], crash=True),
       blk("Acid break", "V", 8, ["bass"], ["hat", "open"]),
       blk("Second wave", "V", 24, ["bass", "stab", "bass_sub"], ["kick", "clap", "hat", "open", "cowbell"], crash=True, fill="roll16"),
       blk("Peak", "A", 32, ["bass", "stab", "pad", "bass_sub"], ["kick", "clap", "hat", "open", "cowbell"], crash=True),
       blk("Outro", "A", 16, ["bass"], ["kick", "hat"])]
SPECS["acid-corridor"] = {
    **common("Acid Corridor", 3, "acid-corridor", 583939804, "ny-house-93",
             "Chicago acid house: an LMMS LB302 squelching a 16th line with slides over Am9 - Em7 (two bars each), raw TR-909 kick and clap, "
             "TR-606 hats, a TR-808 cowbell, sparse organ stabs, and a low-pass that opens over the whole track."),
    "overrides": {"bpm": 128, "swing": 0.52, "drums": "grid", "arrangement": ARR,
                  "harmony": {"rhythm": 0.5, "dominant": "modal", "colors": {"m": "m", "m7": "m7", "m9": "m"}},
                  "bass": {"style": "pattern", "register": [33, 52],
                           "pattern": [[0, "R", 0.3, 1.0], [2, "O", 0.2, 0.7], [3, "R", 0.3, 0.8], [5, "5", 0.2, 0.9], [6, "R", 0.55, 0.8], [8, "O", 0.2, 1.0],
                                       [10, "R", 0.2, 0.7], [11, "7", 0.3, 0.8], [13, "R", 0.2, 0.9], [14, "O", 0.5, 1.0]]},
                  "stab": {"steps": [3, 10], "low": 57, "high": 76, "top": 72, "notes": 3, "gate": 0.2, "vel": 0.8, "accent": 0.85},
                  "pad": {"low": 52, "high": 72, "top": 67, "notes": 3, "vel": 0.45},
                  "grid": {"kick": [[0, 1], [4, 1], [8, 1], [12, 1]], "clap": [[4, 0.9], [12, 0.92]],
                           "hat": [[s, 0.58 if s % 2 == 0 else 0.34] for s in range(16)],
                           "open": [[2, 0.5], [6, 0.5], [10, 0.5], [14, 0.55]],
                           "cowbell": {"A": [], "B": [[7, 0.45], [15, 0.4]]}}},
    "kit_def": kit({"kick": (dm("tr909/kick"), "kick", None), "clap": (dm("tr909/clap"), "clap", None), "snare": (dm("tr909/snare"), "clap", None),
                    "hat": (dm("tr606/tr606_hat_c"), "hats", None), "open": (dm("tr909/hat-o"), "hats", None),
                    "cowbell": (dm("tr808/cowbell"), "perc", None), "crash": (dm("tr606/tr606_cymbal"), "crash", None)},
                   {"kick": {"hp": 30, "mono": True, "drive": 1.2, "gain_db": -3.0}, "clap": {"hp": 200, "sends": {"room": 0.2}, "gain_db": -6.0},
                    "hats": {"pan": 0.15, "gain_db": -9.0}, "perc": {"pan": -0.3, "sends": {"echo": 0.15}, "gain_db": -12.0}, "crash": {"gain_db": -15.0}}),
    "layers": [("bass", "bass_sub")],
    "voices": {"bass": (*xpf("LB302/GoodOldTimes.xpf", "GoodOldTimes (LMMS LB302), the 303"), dict(lmms_fx=[{"lv2": "calf:Saturator"}], hp=40, drive=1.4, sends={"echo": 0.12, "room": 0.1}, gain_db=-6.0)),
               "bass_sub": sub(-14.0),
               "stab": (*calf("Organ", "Transistor 2"), dict(hp=200, sends={"echo": 0.25, "room": 0.15}, width=1.2, gain_db=-8.0)),
               "pad": (*zyn("Strings/0034-Dark Strings.xiz", "Dark Strings (ZynAddSubFX - Strings)"), dict(hp=250, width=1.6, sends={"plate": 0.35}, gain_db=-14.0))},
    "targets": {"bass": -3.0, "bass_sub": -18.0, "stab": -10.0, "pad": -20.0},
    "test_bars": (bars_upto(ARR, "Peak"), bars_upto(ARR, "Peak") + 7),
    "automation": [{"type": "lowpass", "tracks": ["bass"], "points": [[1, 450], [41, 1100], [65, 2400], [89, 650], [97, 3500], [129, 18000], [161, 700]]}],
}

# ------------------------------------------------------------------ 4. Low Light: slow deep house, 112, D minor
ARR = [blk("Pads and rimshots", "A", 8, ["pad"], ["rim", "maracas"]),
       blk("Bass", "A", 8, ["pad", "bass"], ["rim", "maracas", "hat"]),
       blk("Groove", "A", 16, ["pad", "bass", "comp"], ["kick", "rim", "hat", "maracas", "tamb"]),
       blk("Melody", "V", 16, ["pad", "bass", "comp", "lead"], ["kick", "rim", "hat", "maracas", "tamb", "conga"]),
       blk("Deep", "B", 16, ["pad", "bass", "comp", "lead", "vox"], ["kick", "rim", "hat", "maracas", "tamb", "conga", "clave"]),
       blk("Breathe", "A", 8, ["pad", "lead", "vox"], ["rim"]),
       blk("Return", "A", 32, ["pad", "bass", "comp", "lead", "vox"], ["kick", "rim", "hat", "maracas", "tamb", "conga"]),
       blk("Fade", "A", 16, ["pad", "comp"], ["rim", "maracas"])]
SPECS["low-light"] = {
    **common("Low Light", 4, "low-light", 79686656, "deep-house-mezzanine",
             "Slow deep house in the Larry Heard school: D minor Dm9 - Gm9 - Bbmaj9 - Am7, opening on pads and CR-78 rimshots alone, "
             "a soft CR-78 kit with maracas, tambourine and conga, held DX Rhodes chords, a gentle triangle lead, a space choir in the deep part."),
    "overrides": {"bpm": 112, "swing": 0.53, "drums": "grid", "arrangement": ARR,
                  "harmony": {"rhythm": 1, "dominant": "modal", "colors": {"m": "m11", "": "maj9", "m7": "m9", "7": "7sus4", "maj7": "maj9"}},
                  "melody": {"modal": True, "register": [62, 81], "max_leap": 5, "max_notes_per_bar": 3, "articulation": "legato", "humanize_ms": 9, "velocity": [0.55, 0.82]},
                  "bass": {"style": "pattern", "register": [33, 50], "pattern": [[0, "R", 1.6], [8, "R", 0.5], [10, "5", 0.4], [14, "O", 0.4]]},
                  "comp": {"steps": [0, 10], "low": 53, "high": 74, "top": 70, "notes": 4, "gate": 1.6, "humanize_ms": 10, "strum_ms": 12},
                  "vox": {"steps": [0], "low": 64, "high": 81, "top": 76, "notes": 2, "gate": 3.5, "vel": 0.55, "accent": 0.6},
                  "pad": {"low": 50, "high": 77, "top": 72, "notes": 5, "vel": 0.55},
                  "grid": {"kick": [[0, 0.85], [4, 0.85], [8, 0.85], [12, 0.85]],
                           "rim": {"A": [[3, 0.5], [6, 0.45], [11, 0.5]], "B": [[3, 0.5], [10, 0.45], [14, 0.4]]},
                           "hat": [[2, 0.55], [6, 0.55], [10, 0.55], [14, 0.55]],
                           "maracas": [[s, 0.32 if s % 2 else 0.22, "shaker"] for s in range(16)],
                           "tamb": [[4, 0.5], [12, 0.5]],
                           "conga": {"A": [[7, 0.5, "conga_lo"], [13, 0.45, "conga_lo"]], "B": [[5, 0.45, "conga_lo"], [11, 0.5, "conga_lo"], [15, 0.4, "conga_lo"]]},
                           "clave": {"A": [], "B": [[10, 0.4]]}}},
    "kit_def": kit({"kick": (dm("cr78/kick"), "kick", None), "rim": (dm("cr78/rim"), "perc", None), "hat": (dm("cr78/hihat"), "hats", None),
                    "shaker": (dm("cr78/maracas"), "hats", None), "tamb": (dm("cr78/tamb"), "perc", None), "conga_lo": (dm("cr78/conga"), "perc", None),
                    "clave": (dm("cr78/clave"), "perc", None), "snare": (dm("cr78/snare"), "perc", None), "crash": (dm("cr78/cymbal"), "perc", None)},
                   {"kick": {"hp": 30, "mono": True, "gain_db": -3.0}, "hats": {"pan": 0.2, "gain_db": -11.0},
                    "perc": {"pan": -0.2, "sends": {"room": 0.25, "plate": 0.1}, "width": 1.3, "gain_db": -9.0}}),
    "layers": [("bass", "bass_sub")],
    "voices": {"bass": (*zyn("Bass/0001-Bass 1.xiz", "Bass 1 (ZynAddSubFX - Bass)"), dict(hp=32, lp=2200, mono=True, duck={"depth": 0.2, "release": 0.15}, gain_db=-6.0)),
               "bass_sub": sub(),
               "comp": (*zyn("Rhodes/0003-DX Rhodes 3.xiz", "DX Rhodes 3 (ZynAddSubFX - Rhodes)"), dict(hp=130, chorus={"depth_ms": 2.5, "rate": 0.5, "base_ms": 9, "mix": 0.35}, width=1.0, sends={"plate": 0.2}, gain_db=-8.0)),
               "lead": (*zyn("olivers-100/0038-Gentle Triangle Lead.xiz", "Gentle Triangle Lead (ZynAddSubFX - olivers-100)"), dict(hp=250, sends={"plate": 0.35, "echo": 0.2}, gain_db=-6.0)),
               "vox": (*zyn("Fantasy/0011-Space Choir1.xiz", "Space Choir1 (ZynAddSubFX - Fantasy)"), dict(hp=250, width=0.9, sends={"plate": 0.45}, gain_db=-12.0)),
               "pad": (*zyn("Strings/0017-Sweep Pad 1 Fat.xiz", "Sweep Pad 1 Fat (ZynAddSubFX - Strings)"), dict(hp=180, width=0.9, sends={"plate": 0.35}, gain_db=-10.0))},
    "targets": {"bass": -6.0, "bass_sub": -17.0, "comp": -8.0, "lead": -8.0, "vox": -15.0, "pad": -12.0},
    "test_bars": (bars_upto(ARR, "Return"), bars_upto(ARR, "Return") + 7),
}

# ------------------------------------------------------------------ 5. Pepperoni: breakbeat house, 116, B minor
ARR = [blk("The break alone", "A", 2, [], ["kick", "snare", "ghost", "hat"]),
       blk("Stabs hit", "A", 6, ["stab"], ["kick", "snare", "ghost", "hat"]),
       blk("Bass", "A", 16, ["stab", "bass"], ["kick", "snare", "ghost", "hat", "open"]),
       blk("Chops", "V", 16, ["stab", "bass", "vox"], ["kick", "snare", "ghost", "hat", "open", "clap"]),
       blk("Hook", "A", 16, ["stab", "bass", "vox", "lead", "pad"], ["kick", "snare", "ghost", "hat", "open", "clap", "cowbell"], crash=True),
       blk("Rewind", "A", 2, [], ["kick", "snare", "ghost"]),
       blk("Second hook", "B", 16, ["stab", "bass", "vox", "pad"], ["kick", "snare", "ghost", "hat", "open", "clap"], crash=True),
       blk("Hook again", "A", 16, ["stab", "bass", "vox", "lead", "pad"], ["kick", "snare", "ghost", "hat", "open", "clap", "cowbell"], crash=True),
       blk("Outro", "A", 8, ["stab"], ["kick", "snare", "ghost", "hat"])]
SPECS["pepperoni"] = {
    **common("Pepperoni", 5, "pepperoni", 1565170330, "ny-house-93",
             "Breakbeat house: no four-to-the-floor, a chopped acoustic break with ghost notes and TR-808 claps and cowbell, B minor Bm9 - Em9 - F#7, "
             "Calf Organ 'Std Jimmy' stabs, vocal-morph chops as the hook, a synth-brass melody, the dingy Funky Reso Bass."),
    "overrides": {"bpm": 116, "swing": 0.55, "drums": "grid", "arrangement": ARR,
                  "harmony": {"rhythm": 1, "dominant": "keep", "colors": {"m": "m9", "m7": "m9", "7": "7"}},
                  "melody": {"register": [64, 84], "max_leap": 7, "max_notes_per_bar": 6, "articulation": "detached", "humanize_ms": 6, "velocity": [0.65, 0.92]},
                  "bass": {"style": "pattern", "register": [33, 52], "pattern": [[0, "R", 0.3], [3, "R", 0.2], [6, "O", 0.2], [10, "R", 0.4], [13, "5", 0.2], [14, "R", 0.25]]},
                  "stab": {"steps": [0, 6], "low": 57, "high": 77, "top": 74, "notes": 4, "gate": 0.25, "vel": 0.8, "accent": 0.88},
                  "vox": {"steps": [2, 7, 14], "low": 62, "high": 80, "top": 74, "notes": 2, "gate": 0.22, "vel": 0.75, "accent": 0.85},
                  "pad": {"low": 55, "high": 77, "top": 74, "notes": 4, "vel": 0.45},
                  "grid": {"kick": {"A": [[0, 1], [6, 0.85], [10, 0.9]], "B": [[2, 0.9], [6, 0.8], [10, 0.9], [11, 0.6]]},
                           "snare": {"A": [[4, 0.95], [12, 0.95]], "B": [[4, 0.95], [12, 0.95], [14, 0.6]]},
                           "ghost": {"A": [[7, 0.32], [9, 0.28], [15, 0.38]], "B": [[3, 0.3], [9, 0.3], [13, 0.35]]},
                           "hat": [[s, 0.5 if s % 4 == 0 else 0.38] for s in range(0, 16, 2)],
                           "open": {"A": [], "B": [[14, 0.5]]},
                           "clap": {"A": [], "B": [[12, 0.6]]},
                           "cowbell": {"A": [[3, 0.4]], "B": []}}},
    "kit_def": kit({"kick": (str(LMMS_DRUMS / "bassdrum02.ogg"), "kick", None), "snare": (str(LMMS_DRUMS / "snare03.ogg"), "break", None),
                    "ghost": (str(LMMS_DRUMS / "snare05.ogg"), "break", {"gain_db": -8, "lp": 6000}), "hat": (str(LMMS_DRUMS / "hihat_closed02.ogg"), "hats", None),
                    "open": (str(LMMS_DRUMS / "hihat_opened03.ogg"), "hats", None), "clap": (dm("tr808/handclap"), "perc", None),
                    "cowbell": (dm("tr808/cowbell"), "perc", None), "crash": (str(LMMS_DRUMS / "crash01.ogg"), "hats", None)},
                   {"kick": {"hp": 35, "mono": True, "drive": 1.4, "crush": {"bits": 12, "rate": 26040, "mix": 0.4}, "gain_db": -3.0},
                    "break": {"hp": 90, "drive": 1.5, "crush": {"bits": 12, "rate": 26040, "mix": 0.5}, "sends": {"room": 0.15}, "gain_db": -4.0},
                    "hats": {"pan": 0.15, "crush": {"bits": 12, "rate": 26040, "mix": 0.4}, "gain_db": -10.0},
                    "perc": {"pan": -0.25, "sends": {"room": 0.2}, "gain_db": -10.0}}),
    "layers": [("bass", "bass_sub")],
    "voices": {"bass": (*zyn("olivers-100/0054-Funky Reso Bass.xiz", "Funky Reso Bass (ZynAddSubFX - olivers-100)"),
                        dict(lmms_fx=[{"lv2": "calf:Saturator"}], hp=38, lp=4500, drive=1.6, crush={"bits": 10, "rate": 18000, "mix": 0.3}, mono=True, gain_db=-6.0)),
               "bass_sub": sub(),
               "stab": (*calf("Organ", "Std Jimmy"), dict(hp=160, sends={"room": 0.2}, width=1.2, gain_db=-6.0)),
               "vox": (*zyn("ChoirAndVoice/0069-Vocal Morph 5.xiz", "Vocal Morph 5 (ZynAddSubFX - ChoirAndVoice), chops"), dict(hp=280, drive=1.3, sends={"echo": 0.2, "plate": 0.2}, gain_db=-8.0)),
               "lead": (*zyn("Brass/0004-Synth Brazz 2.xiz", "Synth Brazz 2 (ZynAddSubFX - Brass)"), dict(hp=200, sends={"plate": 0.2, "echo": 0.12}, gain_db=-7.0)),
               "pad": (*zyn("Strings/0005-Saw Strings 5.xiz", "Saw Strings 5 (ZynAddSubFX - Strings)"), dict(hp=250, width=1.5, sends={"plate": 0.3}, gain_db=-14.0))},
    "targets": {"bass": -6.0, "bass_sub": -17.0, "stab": -8.0, "vox": -10.0, "lead": -8.0, "pad": -18.0},
    "test_bars": (bars_upto(ARR, "Hook"), bars_upto(ARR, "Hook") + 7),
}

# ------------------------------------------------------------------ 6. Drum Ritual: tribal house, 131, E minor
PERC = ["conga", "bongo", "toms", "shaker", "timbale"]
ARR = [blk("Congas", "A", 8, [], ["conga", "bongo"]),
       blk("Toms and shaker", "A", 8, [], ["conga", "bongo", "toms", "shaker"]),
       blk("Kick", "A", 16, ["bass"], ["kick"] + PERC[:4]),
       blk("Chant", "A", 16, ["bass", "vox"], ["kick", "hat"] + PERC, fill="toms"),
       blk("Stabs", "V", 16, ["bass", "stab", "vox"], ["kick", "hat", "clap"] + PERC, crash=True, fill="toms"),
       blk("Drums only", "A", 8, [], PERC),
       blk("Peak", "A", 32, ["bass", "stab", "vox", "pad"], ["kick", "hat", "clap"] + PERC, crash=True, fill="toms"),
       blk("Outro", "A", 16, ["bass"], ["kick", "conga", "shaker"])]
SPECS["drum-ritual"] = {
    **common("Drum Ritual", 6, "drum-ritual", 1908976397, "ny-house-93",
             "Tribal house: E minor Em9 / Am9 vamped two bars at a time, opening on congas alone; TR-808 toms, CR-8000 congas, bongos, "
             "shakers and a funk timbale carry the groove, a chanted space voice, transistor-organ pickups, a hypnotic Calf Monosynth bass."),
    "overrides": {"bpm": 131, "swing": 0.53, "drums": "grid", "arrangement": ARR,
                  "harmony": {"rhythm": 0.5, "dominant": "modal", "colors": {"m": "m9", "m7": "m9"}},
                  "bass": {"style": "pattern", "register": [31, 48], "pattern": [[0, "R", 0.25], [3, "R", 0.15], [6, "R", 0.25], [8, "O", 0.15], [10, "R", 0.25], [13, "R", 0.15], [14, "5", 0.2]]},
                  "stab": {"steps": [14], "low": 57, "high": 76, "top": 72, "notes": 3, "gate": 0.3, "vel": 0.8, "accent": 0.85},
                  "vox": {"steps": [0], "low": 59, "high": 76, "top": 71, "notes": 2, "gate": 3.0, "vel": 0.6, "accent": 0.62},
                  "pad": {"low": 47, "high": 67, "top": 64, "notes": 3, "vel": 0.45},
                  "grid": {"kick": [[0, 1], [4, 1], [8, 1], [12, 1]],
                           "toms": {"A": [[3, 0.6, "tom_lo"], [6, 0.5, "tom_mid"], [10, 0.55, "tom_lo"], [13, 0.45, "tom_hi"]],
                                    "B": [[3, 0.6, "tom_lo"], [7, 0.5, "tom_lo"], [11, 0.5, "tom_mid"], [14, 0.55, "tom_lo"], [15, 0.5, "tom_hi"]]},
                           "conga": [[0, 0.5, "conga_lo"], [2, 0.5, "conga_hi"], [6, 0.5, "conga_lo"], [7, 0.45, "conga_hi"], [10, 0.45, "conga_lo"], [11, 0.5, "conga_hi"], [15, 0.4, "conga_hi"]],
                           "bongo": [[1, 0.4, "bongo_hi"], [3, 0.4, "bongo_lo"], [5, 0.4, "bongo_hi"], [9, 0.4, "bongo_hi"], [12, 0.35, "bongo_lo"], [13, 0.45, "bongo_hi"]],
                           "shaker": [[s, 0.36 if s % 2 else 0.24] for s in range(16)],
                           "timbale": {"A": [], "B": [[9, 0.5], [11, 0.45]]},
                           "clap": {"A": [[12, 0.8]], "B": [[4, 0.75], [12, 0.85]]},
                           "hat": [[2, 0.4], [6, 0.4], [10, 0.4], [14, 0.4]]}},
    "kit_def": kit({"kick": (dm("tr909/kick"), "kick", None), "clap": (dm("tr808/handclap"), "perc", None), "hat": (dm("tr808/hat_c"), "perc", None),
                    "tom_lo": (dm("tr808/tom_lo"), "toms", None), "tom_mid": (dm("tr808/tom_mid"), "toms", None), "tom_hi": (dm("tr808/tom_hi"), "toms", None),
                    "conga_lo": (dm("cr8000/conga_l"), "congas", None), "conga_hi": (dm("cr8000/conga_m"), "congas", None),
                    "bongo_hi": (dm("latin/bongo_h"), "congas", None), "bongo_lo": (dm("latin/bongo_l"), "congas", None),
                    "shaker": (dm("latin/shaker_1"), "perc", None), "timbale": (dm("misc_perc/funkay_timbale"), "perc", None),
                    "snare": (dm("tr808/snare"), "perc", None), "crash": (dm("tr606/tr606_cymbal"), "perc", None)},
                   {"kick": {"hp": 30, "mono": True, "gain_db": -3.0}, "toms": {"sends": {"room": 0.3}, "width": 1.4, "gain_db": -6.0},
                    "congas": {"pan": -0.25, "sends": {"room": 0.25}, "width": 1.5, "gain_db": -7.0}, "perc": {"pan": 0.25, "sends": {"room": 0.2}, "gain_db": -9.0}}),
    "layers": [("bass", "bass_sub")],
    "voices": {"bass": (*calf("Monosynth", "Boom Bass"), dict(lmms_fx=[{"lv2": "calf:Saturator"}], hp=35, lp=3000, mono=True, duck={"depth": 0.3, "release": 0.1}, gain_db=-6.0)),
               "bass_sub": sub(),
               "stab": (*calf("Organ", "Transistor"), dict(hp=200, sends={"echo": 0.3, "plate": 0.15}, gain_db=-8.0)),
               "vox": (*zyn("Fantasy/0009-Space Voice2.xiz", "Space Voice2 (ZynAddSubFX - Fantasy), the chant"), dict(hp=200, width=1.5, sends={"plate": 0.4, "echo": 0.15}, gain_db=-9.0)),
               "pad": (*zyn("Pads/0003-Analog Pad 1.xiz", "Analog Pad 1 (ZynAddSubFX - Pads)"), dict(hp=150, lp=4000, width=1.6, sends={"plate": 0.3}, gain_db=-14.0))},
    "targets": {"bass": -6.0, "bass_sub": -17.0, "stab": -10.0, "vox": -11.0, "pad": -20.0},
    "test_bars": (bars_upto(ARR, "Peak"), bars_upto(ARR, "Peak") + 7),
}

# ------------------------------------------------------------------ 7. Skyline: Italo piano house, 126, G major
ARR = [blk("The piano hook alone", "A", 8, ["lead", "comp"]),
       blk("Drums", "A", 8, ["lead", "comp"], ["kick", "clap", "hat", "tamb"]),
       blk("Bass", "A", 8, ["lead", "comp", "bass"], ["kick", "clap", "snare", "hat", "tamb", "cabasa"], fill="toms"),
       blk("Verse", "V", 16, ["comp", "bass", "pad"], ["kick", "clap", "snare", "hat", "tamb", "cabasa"], fill="toms"),
       blk("Hook", "A", 24, ["lead", "comp", "bass", "pad", "arp"], ["kick", "clap", "snare", "hat", "open", "tamb", "cabasa"], crash=True, fill="toms"),
       blk("Piano and strings", "B", 8, ["lead", "pad"]),
       blk("Build", "B", 8, ["comp", "pad", "arp"], ["hat", "tamb"], fill="roll16"),
       blk("Big hook", "A", 24, ["lead", "lead_hi", "comp", "bass", "pad", "arp"], ["kick", "clap", "snare", "hat", "open", "tamb", "cabasa"], crash=True, fill="toms"),
       blk("Outro", "A", 8, ["comp", "bass"], ["kick", "hat", "tamb"])]
SPECS["skyline"] = {
    **common("Skyline", 7, "skyline", 2037275263, "italo-disco-84",
             "Italo piano house: G major G - Em - Cmaj7 - Am7, opening on the piano hook alone, a LinnDrum kit with tambourine and cabasa, "
             "bouncy off-beat piano chords, a galloping octave bass, a plucked arpeggio, bright strings, the hook doubled by a synth at the end."),
    "overrides": {"bpm": 126, "swing": 0.5, "drums": "grid", "arrangement": ARR,
                  "harmony": {"rhythm": 1, "dominant": "keep", "colors": {"": "add9", "m": "m7", "7": "7", "maj7": "maj7"}},
                  "melody": {"register": [67, 88], "max_leap": 7, "max_notes_per_bar": 7, "articulation": "detached", "humanize_ms": 4, "velocity": [0.68, 0.95]},
                  "bass": {"style": "octave8", "register": [33, 50], "gate": 0.3},
                  "comp": {"steps": [2, 6, 10, 14], "low": 57, "high": 77, "top": 74, "notes": 4, "gate": 0.22, "humanize_ms": 3},
                  "arp": {"pattern": [0, 1, 2, 3, 2, 1], "low": 67, "high": 88, "gate": 0.14, "rate": 0.25},
                  "pad": {"low": 57, "high": 81, "top": 77, "notes": 4, "vel": 0.5},
                  "grid": {"kick": [[0, 1], [4, 1], [8, 1], [12, 1]], "clap": [[4, 0.8], [12, 0.85]], "snare": [[4, 0.7], [12, 0.75]],
                           "hat": [[2, 0.6], [6, 0.6], [10, 0.6], [14, 0.6]], "open": {"A": [], "B": [[14, 0.5]]},
                           "tamb": [[s, 0.42 if s % 4 == 2 else 0.3] for s in range(0, 16, 2)],
                           "cabasa": [[s, 0.25] for s in range(1, 16, 2)]}},
    "kit_def": kit({"kick": (dm("linn/linn_kik"), "kick", None), "snare": (dm("linn/linn_snr"), "snare", None), "clap": (dm("linn/linn_clp"), "snare", None),
                    "hat": (dm("tr606/tr606_hat_c"), "hats", None), "open": (dm("tr606/tr606_hat_o"), "hats", None), "tamb": (dm("linn/linn_tamb"), "perc", None),
                    "cabasa": (dm("linn/linn_cab"), "perc", None), "crash": (dm("tr606/tr606_cymbal"), "hats", None),
                    "tom_hi": (dm("linn/linn_tom1"), "toms", None), "tom_mid": (dm("linn/linn_tom3"), "toms", None), "tom_lo": (dm("linn/linn_tom5"), "toms", None)},
                   {"kick": {"hp": 30, "mono": True, "gain_db": -3.0}, "snare": {"hp": 150, "sends": {"gated": 0.4, "plate": 0.1}, "gain_db": -6.0},
                    "hats": {"pan": 0.2, "gain_db": -9.0}, "perc": {"pan": -0.25, "gain_db": -11.0}, "toms": {"sends": {"plate": 0.2}, "width": 1.3, "gain_db": -8.0}}),
    "layers": [("bass", "bass_sub")],
    "voices": {"lead": (*zyn("Cormi_Sound/0065-Synth_piano_03.xiz", "Synth_piano_03 (ZynAddSubFX - Cormi_Sound), the piano hook"), dict(hp=120, width=0.9, sends={"room": 0.2, "plate": 0.15}, gain_db=-5.0)),
               "lead_hi": (*zyn("Laba170bank/0009-GenericLead2.xiz", "GenericLead2 (ZynAddSubFX - Laba170bank)"), dict(hp=300, sends={"plate": 0.25}, gain_db=-14.0)),
               "comp": (*zyn("Collection/0110-Home Piano.xiz", "Home Piano (ZynAddSubFX - Collection), off-beat chords"), dict(hp=150, width=0.8, sends={"room": 0.2}, gain_db=-8.0)),
               "bass": (*zyn("Bass/0002-Bass 2.xiz", "Bass 2 (ZynAddSubFX - Bass)"), dict(hp=35, lp=3500, mono=True, duck={"depth": 0.25, "release": 0.1}, gain_db=-6.0)),
               "bass_sub": sub(-14.0),
               "arp": (*zyn("Plucked/0036-Plucked Wah.xiz", "Plucked Wah (ZynAddSubFX - Plucked)"), dict(hp=300, width=0.9, sends={"echo": 0.2}, gain_db=-12.0)),
               "pad": (*zyn("the_mysterious_bank/0004-trance_strings_pad.xiz", "trance_strings_pad (ZynAddSubFX - the_mysterious_bank)"), dict(hp=250, width=0.9, sends={"plate": 0.35}, gain_db=-12.0))},
    "lead_hi_follows_lead": False,
    "targets": {"lead": -5.0, "comp": -9.0, "bass": -6.0, "bass_sub": -18.0, "arp": -14.0, "pad": -16.0},
    "test_bars": (bars_upto(ARR, "Hook"), bars_upto(ARR, "Hook") + 7),
}

# ------------------------------------------------------------------ 8. Last Call: NY dub house, 134, C# minor
ARR = [blk("Echoes", "A", 8, ["stab"]),
       blk("Kick", "A", 8, ["stab"], ["kick"]),
       blk("Sub", "A", 16, ["stab", "bass"], ["kick", "hat", "rim"]),
       blk("Groove", "A", 16, ["stab", "bass"], ["kick", "clap", "hat", "open", "rim"]),
       blk("Melodica", "V", 16, ["stab", "bass", "lead"], ["kick", "clap", "hat", "open", "rim"], crash=True),
       blk("Dub out", "A", 8, ["stab", "vox"], ["rim"]),
       blk("Peak", "A", 32, ["stab", "bass", "lead", "vox"], ["kick", "clap", "hat", "open", "rim"], crash=True),
       blk("Outro", "A", 16, ["bass", "stab"], ["kick", "hat"])]
SPECS["last-call"] = {
    **common("Last Call", 8, "last-call", 546054846, "ny-house-93",
             "NY dub house, the fastest track: C# minor C#m9 / G#7, opening on chord stabs echoing into silence; a crushed TR-909, "
             "a deep sub bass, a Calf Organ melodica, rare vocal-morph chops, long dub delays."),
    "overrides": {"bpm": 134, "swing": 0.5, "drums": "grid", "arrangement": ARR,
                  "harmony": {"rhythm": 0.5, "dominant": "keep", "colors": {"m": "m9", "7": "7sus4", "m7": "m9"}},
                  "melody": {"register": [62, 81], "max_leap": 7, "max_notes_per_bar": 3, "articulation": "legato", "humanize_ms": 8, "velocity": [0.6, 0.9]},
                  "bass": {"style": "pattern", "register": [28, 45], "pattern": [[0, "R", 2.5], [12, "R", 0.5], [14, "O", 0.3]]},
                  "stab": {"steps": [6], "low": 57, "high": 77, "top": 72, "notes": 4, "gate": 0.3, "vel": 0.85, "accent": 0.85},
                  "vox": {"steps": [10], "low": 62, "high": 79, "top": 74, "notes": 2, "gate": 0.3, "vel": 0.7, "accent": 0.7},
                  "grid": {"kick": [[0, 1], [4, 1], [8, 1], [12, 1]], "clap": {"A": [[12, 0.85]], "B": [[4, 0.8], [12, 0.9]]},
                           "rim": [[7, 0.5], [10, 0.45]], "hat": [[2, 0.55], [6, 0.55], [10, 0.55], [14, 0.55]], "open": {"A": [], "B": [[14, 0.5]]}}},
    "kit_def": kit({"kick": (dm("tr909/kick"), "kick", None), "clap": (dm("tr909/clap"), "clap", None), "snare": (dm("tr909/snare"), "clap", None),
                    "rim": (dm("tr808/rimshot"), "perc", None), "hat": (dm("tr909/hat-c2"), "hats", None), "open": (dm("tr909/hat-o2"), "hats", None),
                    "crash": (dm("tr606/tr606_cymbal"), "hats", None)},
                   {"kick": {"hp": 30, "mono": True, "drive": 1.4, "crush": {"bits": 12, "rate": 26040, "mix": 0.5}, "gain_db": -3.0},
                    "clap": {"hp": 200, "drive": 1.3, "crush": {"bits": 12, "rate": 26040, "mix": 0.6}, "sends": {"echo": 0.25, "room": 0.2}, "gain_db": -7.0},
                    "hats": {"pan": 0.2, "crush": {"bits": 10, "rate": 22050, "mix": 0.4}, "gain_db": -10.0},
                    "perc": {"pan": -0.3, "sends": {"echo": 0.35}, "gain_db": -10.0}}),
    "layers": [],
    "sends": {"echo": {"time_beats": 0.75, "feedback": 0.58, "tone": 2200, "taps": 10}},
    "voices": {"stab": (*zyn("Rhodes/0042-Hard Rhodes1.xiz", "Hard Rhodes1 (ZynAddSubFX - Rhodes), dub stabs"), dict(hp=180, sends={"echo": 0.6, "plate": 0.2}, width=1.3, gain_db=-6.0)),
               "bass": (*zyn("Bass/0003-Bass 3 _analog_.xiz", "Bass 3 analog (ZynAddSubFX - Bass), sub"), dict(hp=25, lp=400, mono=True, duck={"depth": 0.35, "release": 0.12}, gain_db=-6.0)),
               "lead": (*calf("Organ", "Melodica NOS"), dict(hp=200, sends={"echo": 0.5, "plate": 0.25}, gain_db=-6.0)),
               "vox": (*zyn("ChoirAndVoice/0071-Vocal Morph 7.xiz", "Vocal Morph 7 (ZynAddSubFX - ChoirAndVoice)"), dict(hp=300, sends={"echo": 0.7, "plate": 0.3}, gain_db=-10.0))},
    "targets": {"stab": -8.0, "bass": -5.0, "lead": -8.0, "vox": -14.0},
    "test_bars": (bars_upto(ARR, "Peak"), bars_upto(ARR, "Peak") + 7),
    "overrides_master": True,
}
SPECS["last-call"]["overrides"]["master"] = V1.__dict__.get("DIRTY_TAPE") or {
    "tape": {"drive": 1.6, "bias": 0.06, "bump_db": 1.0, "hf_db": -1.5, "lp_hz": 16000, "hiss_db": -76, "wow_ms": 0.05}, "target_lufs": -11.0}

# ------------------------------------------------------------------ 9. Night Bus: downtempo lounge, 98, Bb major
ARR = [blk("Rhodes alone", "A", 4, ["comp"]),
       blk("Beat", "A", 8, ["comp", "bass"], ["kick", "snare", "hat"]),
       blk("Vibes", "A", 16, ["comp", "bass", "lead"], ["kick", "snare", "hat", "rim", "shaker"]),
       blk("B section", "V", 8, ["comp", "bass", "pad", "lead"], ["kick", "snare", "hat", "open"]),
       blk("Space", "B", 8, ["comp", "bass", "lead"], ["hat", "rim"]),
       blk("Theme", "A", 24, ["comp", "bass", "lead", "pad"], ["kick", "snare", "hat", "rim", "shaker", "open"]),
       blk("Last stop", "A", 8, ["comp"], ["hat"])]
SPECS["night-bus"] = {
    **common("Night Bus", 9, "night-bus", 860581073, "lofi-downtempo",
             "The closer, downtempo lounge: B-flat major Bbmaj9 - Ebmaj9 - Fadd9, opening on the Rhodes alone, a lazy swung boom-bap from an "
             "R&B drum machine, a vibraphone melody, a walking upright bass, a soft sine pad."),
    "overrides": {"bpm": 98, "swing": 0.6, "drums": "grid", "drum_humanize_ms": 8, "arrangement": ARR,
                  "harmony": {"rhythm": 1, "dominant": "keep", "colors": {"m": "m9", "": "maj9", "m7": "m9", "7": "9", "maj7": "maj9"}},
                  "melody": {"register": [64, 84], "max_leap": 7, "max_notes_per_bar": 5, "articulation": "detached", "humanize_ms": 14, "push_ms": 6, "swing": 0.6, "velocity": [0.5, 0.82]},
                  "bass": {"style": "walking", "register": [33, 52], "humanize_ms": 10, "swing": 0.6},
                  "comp": {"steps": [0, 7, 10], "low": 55, "high": 74, "top": 71, "notes": 4, "gate": 0.9, "strum_ms": 22, "humanize_ms": 12, "swing": 0.6},
                  "pad": {"low": 55, "high": 76, "top": 72, "notes": 4, "vel": 0.4},
                  "grid": {"kick": {"A": [[0, 0.95], [7, 0.7], [10, 0.85]], "B": [[0, 0.95], [3, 0.65], [10, 0.85], [11, 0.6]]},
                           "snare": [[4, 0.9], [12, 0.92]],
                           "hat": [[0, 0.55], [2, 0.4], [4, 0.5], [6, 0.4], [8, 0.55], [10, 0.4], [12, 0.5], [14, 0.4], [15, 0.25]],
                           "open": {"A": [], "B": [[14, 0.45]]}, "rim": {"A": [[10, 0.4]], "B": [[6, 0.35]]},
                           "shaker": [[s, 0.2] for s in range(1, 16, 2)]}},
    "kit_def": kit({"kick": (dm("r_n_b/k_muffle"), "kick", None), "snare": (dm("r_n_b/popsnare"), "snare", None), "hat": (dm("r_n_b/hat"), "hats", None),
                    "open": (dm("r_n_b/hat_o"), "hats", None), "rim": (dm("r_n_b/s_hollow"), "snare", None), "shaker": (dm("latin/shaker_2"), "hats", None),
                    "crash": (dm("cr78/cymbal"), "hats", None)},
                   {"kick": {"hp": 30, "mono": True, "drive": 1.2, "gain_db": -3.0}, "snare": {"hp": 120, "drive": 1.2, "sends": {"room": 0.2}, "gain_db": -6.0},
                    "hats": {"pan": 0.15, "gain_db": -8.0}}),
    "layers": [],
    "voices": {"comp": (*zyn("Rhodes/0013-Ice Rhodes2.xiz", "Ice Rhodes2 (ZynAddSubFX - Rhodes)"), dict(hp=110, chorus={"depth_ms": 2.0, "rate": 0.6, "base_ms": 9, "mix": 0.3}, width=1.3, sends={"room": 0.2}, gain_db=-6.0)),
               "lead": (*zyn("Collection/0002-Vibraphone.xiz", "Vibraphone (ZynAddSubFX - Collection)"), dict(hp=250, eq=[["peak", 3200, 3.0, 0.8], ["highshelf", 7000, 2.0]], sends={"plate": 0.25, "echo": 0.12}, gain_db=-6.0)),
               "bass": (*zyn("the_mysterious_bank_4/0024-pseudo_doublebass.xiz", "pseudo_doublebass (ZynAddSubFX - the_mysterious_bank_4), upright"), dict(hp=35, lp=2500, mono=True, gain_db=-6.0)),
               "pad": (*zyn("Pads/0001-Sine Pad.xiz", "Sine Pad (ZynAddSubFX - Pads)"), dict(hp=200, lp=3000, width=1.5, sends={"plate": 0.3}, gain_db=-14.0))},
    "targets": {"comp": -7.0, "lead": -6.0, "bass": -6.0, "pad": -18.0},
    "test_bars": (bars_upto(ARR, "Theme"), bars_upto(ARR, "Theme") + 7),
}
SPECS["night-bus"]["overrides"]["master"] = {"tape": {"drive": 1.5, "bias": 0.06, "bump_db": 1.2, "hf_db": -1.2, "lp_hz": 16500, "hiss_db": -74, "wow_ms": 0.1}, "target_lufs": -12.0}

SPECS["pepperoni"].update({"album": "Taste Tester", "track": 1})     # its own album now (album_taste_tester.py)
ORDER = [(s["title"], i + 1) for i, s in enumerate(v for v in SPECS.values() if v.get("album") == ALBUM)]   # Testimony left for Taste Tester (as Crushed Red Pepper)


def assemble():
    import shutil
    old = ROOT / "albums" / "mezzanine-sessions"
    arch = ROOT / "albums" / "_archive" / "mezzanine-sessions-v1"
    if old.exists() and not arch.exists() and any(old.glob("02 - Velvet Hour.*")):
        arch.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old), str(arch))
    V1.ORDER = ORDER
    V1.INTRO = ("Seven different corners of house music, from 98 to 134 bpm: gospel garage, acid, slow deep house, "
                "tribal, Italo piano house, dub house and a downtempo closer. Each has its own drum machine (TR-909, TR-808, TR-606, CR-78, "
                "LinnDrum, an R&B box), its own beat, opening and arrangement. Composed by Bountiful Music, played by LMMS "
                "instruments, mixed and mastered by the intelligent-jungle renderer.")
    V1.STYLE = {"Testimony": "NY house", "Sunday Service": "gospel garage", "Acid Corridor": "acid house", "Low Light": "slow deep house",
                "Pepperoni": "breakbeat house", "Drum Ritual": "tribal house", "Skyline": "Italo piano house", "Last Call": "dub house",
                "Night Bus": "downtempo lounge"}
    V1.assemble()


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--assemble" in args:
        assemble()
    else:
        want = [a for a in args if not a.startswith("-")]
        for slug, s in SPECS.items():
            if not want or slug in want:
                LT.make(s, log=lambda m: print(m, flush=True))
