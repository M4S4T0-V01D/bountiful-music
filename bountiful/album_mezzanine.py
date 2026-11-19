#!/usr/bin/env python3
"""Album: 'Mezzanine Sessions' by M4S4T0, composed by C-Lizzy. Songs in the manner of Testimony (NY house) and
Mezzanine Light (deep house), composed by Bountiful Music and played by LMMS.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/album_mezzanine.py [slug ...]   # build tracks
    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/album_mezzanine.py --assemble    # album folder

Track 1 is Testimony as the user edited it in LMMS (tracks/testimony/exports/testimony-mmp.wav, rendered from
their .mmp with our mix and master on top); it is not rebuilt here.
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lmms_tracks as LT  # noqa: E402
from house_song import ARRANGEMENT as NY_ARRANGEMENT, BUILD_START as NY_BUILD  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ALBUM = "Mezzanine Sessions"
ARTIST = LT.B.ARTIST
COMPOSER = "C-Lizzy"
YEAR = 2026


def zyn(path, label):
    return {"zyn": path}, label.replace("/", "-")


def calf_organ(preset):
    return {"lv2": "calf:Organ", "preset": preset}, f"{preset} (Calf Organ)"


def sub():
    return (*zyn("Bass/0003-Bass 3 _analog_.xiz", "Bass 3 analog (ZynAddSubFX - Bass), sub"),
            dict(hp=28, lp=150, mono=True, duck={"depth": 0.35, "release": 0.1}, gain_db=-12.0))


# ------------------------------------------------------------------ NY house, the Testimony way
def ny(title, track, seed, bpm, blurb, bass, piano, vox, lead, pad, bass_pattern):
    return {
        "title": title, "track": track, "song": ROOT / "songs" / "ny-house-93" / f"ny-house-93-{seed}.am.json", "genre": "ny-house-93",
        "blurb": blurb, "rebuild": f"bountiful/album_mezzanine.py {LT.B.slug(title)}",
        "overrides": {
            "bpm": bpm, "bass": {"pattern": bass_pattern},
            "comp": {"steps": [0, 3, 6, 10, 13], "low": 56, "high": 76, "top": 73, "notes": 4, "gate": 0.24, "humanize_ms": 4},
            "vox": {"steps": [7, 15], "low": 64, "high": 80, "top": 76, "notes": 2, "gate": 0.32, "vel": 0.72, "accent": 0.8, "humanize_ms": 5},
            "pad": {"low": 55, "high": 79, "top": 76, "notes": 4, "vel": 0.5},
            "arrangement": copy.deepcopy(NY_ARRANGEMENT)},
        "layers": [("bass", "bass_sub")],
        "voices": {
            "bass": (*bass, dict(hp=38, lp=3200, drive=1.3, eq=[["peak", 900, 2.0, 1.0]], mono=True, duck={"depth": 0.3, "release": 0.1}, gain_db=-6.0)),
            "bass_sub": sub(),
            "comp": (*piano, dict(hp=150, eq=[["peak", 300, -3.0, 1.0], ["peak", 2800, 2.5, 0.8]], chorus={"depth_ms": 1.8, "rate": 0.4, "base_ms": 9, "mix": 0.25},
                                  width=1.4, sends={"room": 0.2, "plate": 0.08}, duck={"depth": 0.15, "release": 0.12}, gain_db=-6.0)),
            "lead": (*lead, dict(hp=180, leslie={"speed": [[1, 0]], "crossover": 800, "mix": 0.6}, sends={"plate": 0.22, "echo": 0.12}, gain_db=-6.0)),
            "pad": (*pad, dict(hp=250, lp=7000, width=1.5, sends={"plate": 0.35}, duck={"depth": 0.25, "release": 0.15}, gain_db=-14.0)),
            "vox": (*vox, dict(hp=300, width=1.3, sends={"plate": 0.3, "echo": 0.2}, duck={"depth": 0.15, "release": 0.12}, gain_db=-8.0)),
        },
        "targets": {"bass": -7.0, "bass_sub": -17.0, "comp": -7.0, "lead": -8.0, "pad": -18.0, "vox": -11.0},
        "automation": [{"type": "lowpass", "tracks": ["comp", "pad", "vox"], "points": [[NY_BUILD, 350], [NY_BUILD + 4, 1200], [NY_BUILD + 8, 18000]]}],
        "composer": COMPOSER, "artist": ARTIST, "album": ALBUM, "year": YEAR,
    }


# ------------------------------------------------------------------ deep house, the Mezzanine Light way
DEEP_PEAK = 1 + 16 * 6          # the genre arrangement's peak starts at bar 97


def deep(title, track, seed, bpm, blurb, bass, rhodes, organ, flute, vox, pad):
    return {
        "title": title, "track": track, "song": ROOT / "songs" / "deep-house-mezzanine" / f"deep-house-mezzanine-{seed}.am.json",
        "genre": "deep-house-mezzanine", "blurb": blurb, "rebuild": f"bountiful/album_mezzanine.py {LT.B.slug(title)}",
        "overrides": {"bpm": bpm},
        "test_bars": (DEEP_PEAK, DEEP_PEAK + 7),
        "layers": [("bass", "bass_sub")],
        "voices": {
            "bass": (*bass, dict(hp=34, lp=2800, drive=1.2, mono=True, duck={"depth": 0.3, "release": 0.11}, gain_db=-6.0)),
            "bass_sub": sub(),
            "comp": (*rhodes, dict(hp=140, chorus={"depth_ms": 2.0, "rate": 0.6, "base_ms": 9, "mix": 0.35}, width=1.5,
                                   sends={"plate": 0.15}, duck={"depth": 0.2, "release": 0.12}, gain_db=-8.0)),
            "stab": (*organ, dict(hp=160, eq=[["peak", 350, -2.5, 1.0]], sends={"room": 0.2, "plate": 0.1}, width=1.2, gain_db=-8.0)),
            "lead": (*flute, dict(hp=250, sends={"plate": 0.3, "echo": 0.18}, gain_db=-6.0)),
            "vox": (*vox, dict(hp=300, width=1.3, sends={"plate": 0.35, "echo": 0.22}, gain_db=-9.0)),
            "pad": (*pad, dict(hp=250, lp=7000, width=1.6, sends={"plate": 0.35}, duck={"depth": 0.25, "release": 0.15}, gain_db=-14.0)),
        },
        "targets": {"bass": -6.0, "bass_sub": -17.0, "comp": -9.0, "stab": -10.0, "lead": -7.0, "vox": -12.0, "pad": -18.0},
        "composer": COMPOSER, "artist": ARTIST, "album": ALBUM, "year": YEAR,
    }


SPECS = {s["title"]: s for s in [
    deep("Velvet Hour", 2, 1653290366, 122,
         "E minor, Em9 - Dadd9 - Cmaj9 - Bm7: Mezzanine Light's descending gospel walk. Hard Rhodes on the off-beats, Calf Organ "
         "'Std Jimmy' stabs, a soft flute, 'aah' chops in the lift, a filtered break over the four-to-the-floor.",
         zyn("Bass/0001-Bass 1.xiz", "Bass 1 (ZynAddSubFX - Bass)"), zyn("Rhodes/0043-Hard Rhodes2.xiz", "Hard Rhodes2 (ZynAddSubFX - Rhodes)"),
         calf_organ("Std Jimmy"), zyn("Collection/0057-Soft Flute.xiz", "Soft Flute (ZynAddSubFX - Collection)"),
         zyn("ChoirAndVoice/0001-AHH Choir 1.xiz", "AHH Choir 1 (ZynAddSubFX - ChoirAndVoice)"), zyn("Strings/0016-Sweep Pad 1.xiz", "Sweep Pad 1 (ZynAddSubFX - Strings)")),
    ny("Fifth Floor Freedom", 3, 833899456, 126,
       "D minor, Dm9 - Bbmaj7 - C9 - Fmaj7: uplifting NY house with an organ bass, a home piano on the 3-3-4-3-3 stabs, 'aah' stabs, a Hammond melody.",
       zyn("Organ/0003-Organ 3.xiz", "Organ 3 (ZynAddSubFX - Organ), organ bass"), zyn("Collection/0110-Home Piano.xiz", "Home Piano (ZynAddSubFX - Collection)"),
       zyn("ChoirAndVoice/0001-AHH Choir 1.xiz", "AHH Choir 1 (ZynAddSubFX - ChoirAndVoice)"), zyn("Collection/0054-Hammond Organ.xiz", "Hammond Organ (ZynAddSubFX - Collection)"),
       zyn("the_mysterious_bank/0003-smooth_strings_pad.xiz", "smooth_strings_pad (ZynAddSubFX - the_mysterious_bank)"),
       [[0, "R", 0.4], [3, "R", 0.2], [6, "O", 0.25], [8, "R", 0.3], [11, "R", 0.2], [12, "O", 0.2], [14, "5", 0.3]]),
    deep("Lobby Lights", 4, 135741918, 122,
         "C minor, Cm9 - Fm9 - Abmaj9 - Gm7: Ice Rhodes, Calf Organ 'Gates of dawn' stabs, a warm flute, space-voice chops, an M1-style organ bass.",
         zyn("Organ/0002-Organ 2.xiz", "Organ 2 (ZynAddSubFX - Organ), organ bass"), zyn("Rhodes/0013-Ice Rhodes2.xiz", "Ice Rhodes2 (ZynAddSubFX - Rhodes)"),
         calf_organ("Gates of dawn"), zyn("Collection/0058-Warm Flute.xiz", "Warm Flute (ZynAddSubFX - Collection)"),
         zyn("Fantasy/0008-Space Voice1.xiz", "Space Voice1 (ZynAddSubFX - Fantasy)"), zyn("the_mysterious_bank_3/0001-soft_strings.xiz", "soft_strings (ZynAddSubFX - the_mysterious_bank_3)")),
    ny("Spirit Rising", 5, 1761279037, 124,
       "A-flat major gospel house, Abmaj7 - Bbsus2 - Eb9 / Bbm9 - Eb9 - Abmaj7: the M1 organ bass, a bright piano, full-choir stabs, a Calf Organ melody.",
       zyn("Organ/0002-Organ 2.xiz", "Organ 2 (ZynAddSubFX - Organ), organ bass"), zyn("Cormi_Sound/0068-Piano.xiz", "Piano (ZynAddSubFX - Cormi_Sound)"),
       zyn("Collection/0119-Full Choir.xiz", "Full Choir (ZynAddSubFX - Collection)"), calf_organ("Intertube"),
       zyn("Strings/0011-Strings Pad2.xiz", "Strings Pad2 (ZynAddSubFX - Strings)"),
       [[0, "R", 0.45], [3, "R", 0.2], [6, "O", 0.25], [8, "R", 0.3], [10, "O", 0.2], [11, "R", 0.2], [14, "5", 0.3]]),
    deep("Rooftop Gospel", 6, 1281790664, 121,
         "A minor, Mezzanine Light's key: Am9 - Dm9 - Dm6 - Fmaj9, the verse turning on E. DX Rhodes, Hammond stabs, Flute 2, 'eh' chops.",
         zyn("Bass/0002-Bass 2.xiz", "Bass 2 (ZynAddSubFX - Bass)"), zyn("Rhodes/0002-DX Rhodes 2.xiz", "DX Rhodes 2 (ZynAddSubFX - Rhodes)"),
         zyn("Collection/0054-Hammond Organ.xiz", "Hammond Organ (ZynAddSubFX - Collection)"), zyn("ReedAndWind/0002-Flute 2.xiz", "Flute 2 (ZynAddSubFX - ReedAndWind)"),
         zyn("ChoirAndVoice/0003-EHH Choir 1.xiz", "EHH Choir 1 (ZynAddSubFX - ChoirAndVoice)"), zyn("Strings/0011-Strings Pad2.xiz", "Strings Pad2 (ZynAddSubFX - Strings)")),
    ny("Brooklyn Bound", 7, 1279981710, 125,
       "B-flat minor, Bbm9 - Db6 - Gbmaj7 - F: synth piano stabs, 'eh' stabs, a percussion-organ melody, saw strings, Organ 1 bass.",
       zyn("Organ/0001-Organ 1.xiz", "Organ 1 (ZynAddSubFX - Organ), organ bass"), zyn("Cormi_Sound/0066-Synth_Piano_02.xiz", "Synth_Piano_02 (ZynAddSubFX - Cormi_Sound)"),
       zyn("ChoirAndVoice/0003-EHH Choir 1.xiz", "EHH Choir 1 (ZynAddSubFX - ChoirAndVoice)"), zyn("Collection/0055-Percussion Organ.xiz", "Percussion Organ (ZynAddSubFX - Collection)"),
       zyn("Strings/0007-Saw Strings 7.xiz", "Saw Strings 7 (ZynAddSubFX - Strings)"),
       [[0, "R", 0.4], [3, "O", 0.2], [6, "R", 0.25], [7, "O", 0.2], [10, "R", 0.3], [12, "R", 0.2], [14, "O", 0.25]]),
    deep("Last Elevator", 8, 243054932, 120,
         "B minor, Bm9 - Em9 - Gmaj9 - F#m7: the slowest, latest track. Ice Rhodes, 'Std Jimmy' stabs, a brassy flute, soft-choir chops.",
         zyn("Bass/0003-Bass 3 _analog_.xiz", "Bass 3 analog (ZynAddSubFX - Bass)"), zyn("Cormi_Sound/0104-Ice Rhodes2.xiz", "Ice Rhodes2 (ZynAddSubFX - Cormi_Sound)"),
         calf_organ("Std Jimmy"), zyn("Laba170bank/0008-BrassyFlute.xiz", "BrassyFlute (ZynAddSubFX - Laba170bank)"),
         zyn("Collection/0118-Soft Choir.xiz", "Soft Choir (ZynAddSubFX - Collection)"), zyn("Strings/0018-Sweep Pad 2.xiz", "Sweep Pad 2 (ZynAddSubFX - Strings)")),
    ny("Overtime", 9, 240668134, 126,
       "D-sharp minor, D#m9 - G#m9 - C#add9 - A#m7, a climbing melody: tunnel piano stabs, 'ooh' stabs, a Calf Organ 'Gates of dawn' lead, the M1 organ bass.",
       zyn("Organ/0002-Organ 2.xiz", "Organ 2 (ZynAddSubFX - Organ), organ bass"), zyn("Collection/0109-Tunnel Piano.xiz", "Tunnel Piano (ZynAddSubFX - Collection)"),
       zyn("ChoirAndVoice/0004-Voice OOH.xiz", "Voice OOH (ZynAddSubFX - ChoirAndVoice)"), calf_organ("Gates of dawn"),
       zyn("the_mysterious_bank_4/0003-strings_pad.xiz", "strings_pad (ZynAddSubFX - the_mysterious_bank_4)"),
       [[0, "R", 0.4], [3, "R", 0.18], [6, "O", 0.22], [8, "R", 0.3], [10, "O", 0.18], [11, "R", 0.18], [14, "5", 0.25]]),
]}
ORDER = [("Testimony", 1)] + [(s["title"], s["track"]) for s in SPECS.values()]
STYLE: dict = {}
INTRO = ("Songs composed by Bountiful Music in the manner of *Testimony* (New York house) and *Mezzanine Light* (deep house), "
         "played by LMMS instruments, mixed and mastered by the intelligent-jungle renderer.")


def assemble():
    """albums/mezzanine-sessions/: numbered, tagged MP3s (320k) re-encoded from each track's master WAV, the WAVs
    hard-linked, a cover, and a track list."""
    out = ROOT / "albums" / "mezzanine-sessions"
    out.mkdir(parents=True, exist_ok=True)
    cover = out / "cover.jpg"
    make_cover(cover)
    lines = [f"# {ALBUM}", "", f"**{ARTIST}** · composed by {COMPOSER} · {YEAR}", "",
             INTRO, "",
             "| # | Title | Style | Key | Tempo | Length |", "|---|---|---|---|---|---|"]
    for title, n in ORDER:
        slug = LT.B.slug(title)
        tdir = ROOT / "tracks" / slug
        edited = tdir / "exports" / f"{slug}-mmp.wav"          # the user's LMMS edit, rendered with our mix and master on top
        wav = edited if edited.exists() else tdir / "exports" / f"{slug}.wav"
        if not wav.exists():
            lines.append(f"| {n} | {title} | (not built yet) | | | |")
            continue
        name = f"{n:02d} - {title}"
        dst = out / f"{name}.wav"
        if dst.exists():
            dst.unlink()
        try:
            dst.hardlink_to(wav)
        except OSError:
            shutil.copy(wav, dst)
        subprocess.run(["lame", "--quiet", "-b", "320", "-q", "0", "--add-id3v2", "--tt", title, "--ta", ARTIST, "--tl", ALBUM, "--ty", str(YEAR),
                        "--tn", f"{n}/{len(ORDER)}", "--tg", "House", "--tv", f"TCOM={COMPOSER}", "--tv", f"TPE2={ARTIST}", "--ti", str(cover),
                        str(wav), str(out / f"{name}.mp3")], check=True)
        first = (tdir / "notes.txt").read_text().splitlines()[0] if (tdir / "notes.txt").exists() else ""
        style = STYLE.get(title) or ("deep house" if "Mezzanine" in first else "NY house")
        key = first.split(", ")[2] if first.count(", ") >= 2 else ""
        bpm = first.split(", ")[1] if first.count(", ") >= 1 else ""
        import soundfile as sf
        secs = sf.info(str(wav)).duration
        lines.append(f"| {n} | {title}{' (your LMMS edit)' if edited.exists() else ''} | {style} | {key} | {bpm} | {int(secs // 60)}:{int(secs % 60):02d} |")
    lines += ["", "Each track's folder in `tracks/` holds its MIDI, LMMS project (.mmp), stems, instrument map and notes."]
    (out / "README.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def make_cover(path: Path):
    """A night-club mezzanine: a dark gradient, a warm balcony light band, a grid of window lights, the titles."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    W = 1400
    y = np.linspace(0, 1, W)[:, None]
    x = np.linspace(0, 1, W)[None, :]
    r = 18 + 40 * y + 30 * np.exp(-((y - 0.62) / 0.05) ** 2)
    g = 10 + 14 * y + 22 * np.exp(-((y - 0.62) / 0.05) ** 2)
    b = 38 + 30 * (1 - y) + 10 * np.exp(-((y - 0.62) / 0.05) ** 2)
    img = np.stack([np.broadcast_to(c, (W, W)) for c in (r, g, b)], -1)
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    glow = Image.new("RGB", (W, W))
    d = ImageDraw.Draw(glow)
    rng = np.random.default_rng(7)
    for row in range(5):
        for col in range(14):
            if rng.random() < 0.55:
                x0 = 80 + col * 90 + rng.integers(-6, 6)
                y0 = 330 + row * 95
                warm = (255, int(170 + 60 * rng.random()), int(90 + 60 * rng.random()))
                d.rectangle([x0, y0, x0 + 46, y0 + 52], fill=warm)
    d.rectangle([0, 860, W, 880], fill=(255, 196, 120))
    from PIL import ImageChops
    halo = glow.filter(ImageFilter.GaussianBlur(28))
    im = ImageChops.screen(im, Image.eval(halo, lambda v: int(v * 0.7)))      # warm halo around the lights
    im = ImageChops.screen(im, Image.eval(glow.filter(ImageFilter.GaussianBlur(2)), lambda v: int(v * 0.85)))   # the lit windows
    d = ImageDraw.Draw(im)
    def font(sz):
        import paths
        return paths.font("DejaVuSans-Bold.ttf", sz)
    d.text((80, 1020), "MEZZANINE", font=font(130), fill=(255, 214, 160))
    d.text((84, 1160), "SESSIONS", font=font(84), fill=(240, 228, 245))
    d.text((84, 110), ARTIST, font=font(64), fill=(240, 228, 245))
    d.text((86, 190), f"composed by {COMPOSER}", font=font(34), fill=(200, 180, 210))
    im.save(path, quality=92)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--assemble" in args:
        assemble()
    else:
        want = [a for a in args if not a.startswith("-")]
        for title, s in SPECS.items():
            if not want or LT.B.slug(title) in want:
                LT.make(s, log=lambda m: print(m, flush=True))
