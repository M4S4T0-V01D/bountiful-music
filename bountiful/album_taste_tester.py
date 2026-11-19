#!/usr/bin/env python3
"""'Taste Tester': M4S4T0, composed by C-Lizzy. Pepperoni (formerly Breakbeat Lobby, from Mezzanine Sessions) opens it,
then Cheese, Bread Roll, Pesto, Anchovies and Marinara, Crushed Red Pepper (formerly Testimony), and Meatball closes it.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/album_taste_tester.py
    -> albums/taste-tester/: numbered, tagged MP3s (320k) re-encoded from each track's master WAV, the WAVs hard-linked,
       a cover, and a track list. Tracks not built yet are listed as such.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
from credits import ARTIST, COMPOSER  # noqa: E402

ALBUM, YEAR = "Taste Tester", 2026
OUT = ROOT / "albums" / "taste-tester"
ART = OUT / "art" / "taste-tester-cover.jpg"     # the album cover, by the user
# (number, title, slug, the master to use: the first that exists)
ORDER = [(1, "Pepperoni", "pepperoni", ["pepperoni-v2.wav", "pepperoni-mmp.wav", "pepperoni.wav"]),
         (2, "Cheese", "cheese", ["cheese-v2.wav", "cheese-mastered.wav", "cheese-mmp.wav", "cheese.wav"]),
         (3, "Bread Roll", "bread-roll", ["bread-roll-v2.wav", "bread-roll-mastered.wav", "bread-roll-mmp.wav", "bread-roll.wav"]),
         (4, "Pesto", "pesto", ["pesto-v2.wav", "pesto-mastered.wav", "pesto-mmp.wav", "pesto.wav"]),
         (5, "Anchovies", "anchovies", ["anchovies-v2.wav", "anchovies-mastered.wav", "anchovies-mmp.wav", "anchovies.wav"]),
         (6, "Marinara", "marinara", ["marinara-v2.wav", "marinara-mastered.wav", "marinara-mmp.wav", "marinara.wav"]),
         (7, "Crushed Red Pepper", "crushed-red-pepper", ["crushed-red-pepper-mastered.wav", "crushed-red-pepper-mmp.wav", "crushed-red-pepper.wav"]),
         (8, "Meatball", "meatball", ["meatball-v2.wav", "meatball-mastered.wav", "meatball-mmp.wav", "meatball.wav"])]
NOTES = {"pepperoni-v2.wav": "v2: your LMMS edit + the bit beat, the Rhodes second lead, the full mix and master",
         "crushed-red-pepper-mastered.wav": "your LMMS edit (formerly Testimony) with the full treatment",
         "cheese.wav": "brushed jazz kit, upright, Royale with Cheese organ, Ice Rhodes; written melody",
         "bread-roll.wav": "our C-Lizzy break, Monosynth bass, Transistor organ, piano stabs, whistle; written melody",
         "pesto.wav": "TR-909, wah bass, Shamrock organ, marimba, flute; written melody",
         "anchovies.wav": "TR-808 at 10 bits, boom bass, Intertube dub organ, melodica; written melody",
         "marinara.wav": "LinnDrum and congas, Italo piano, nylon guitar, accordion; written melody",
         "meatball.wav": "the closer: heavy kit, Fat Bass, Fat Belly organ, Fat Brass, Pepperoni's organ returns"}


def make_cover(path: Path):
    """Pepperoni slices scattered on a warm crust-coloured board, the titles in cream."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    W = 1400
    rng = np.random.default_rng(1)
    y = np.linspace(0, 1, W)[:, None]
    base = np.stack([150 + 60 * (1 - y), 70 + 40 * (1 - y), 30 + 20 * (1 - y)], -1) * np.ones((W, W, 1))
    base += rng.normal(0, 6, (W, W, 1))                                     # a little grain
    img = Image.fromarray(np.clip(base, 0, 255).astype("uint8"))
    d = ImageDraw.Draw(img)
    for _ in range(26):                                                     # the slices
        cx, cy, r = rng.uniform(80, W - 80), rng.uniform(260, 980), rng.uniform(55, 120)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(150, 28, 22), outline=(110, 18, 14), width=6)
        for _ in range(7):                                                  # spots of fat
            a, rr, s = rng.uniform(0, 6.28), rng.uniform(0, r * 0.7), rng.uniform(5, 12)
            px, py = cx + rr * np.cos(a), cy + rr * np.sin(a)
            d.ellipse([px - s, py - s, px + s, py + s], fill=(196, 70, 50))
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 1010, W, W], fill=(28, 16, 12))

    def font(sz):
        import paths
        return paths.font("DejaVuSans-Bold.ttf", sz)

    d.text((80, 1040), "TASTE TESTER", font=font(140), fill=(250, 232, 190))
    d.text((84, 1210), f"{ARTIST}  ·  composed by {COMPOSER}", font=font(46), fill=(230, 190, 150))
    d.text((84, 90), ARTIST, font=font(64), fill=(255, 240, 215))
    img.save(path, quality=92)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cover = OUT / "cover.jpg"
    if ART.exists():                     # the user's cover (2026-10-16); the generated one is only a fallback
        shutil.copy(ART, cover)
    else:
        make_cover(cover)
    lines = [f"# {ALBUM}", "", f"**{ARTIST}** · composed by {COMPOSER} · {YEAR}", "",
             "| # | Title | Version | Key | Tempo | Length |", "|---|---|---|---|---|---|"]
    for n, title, slug, masters in ORDER:
        tdir = ROOT / "tracks" / slug
        wav = next((tdir / "exports" / m for m in masters if (tdir / "exports" / m).exists()), None)
        if wav is None:
            lines.append(f"| {n} | {title} | (not built yet) | | | |")
            continue
        name = f"{n:02d} - {title}"
        dst = OUT / f"{name}.wav"
        if dst.exists():
            dst.unlink()
        try:
            dst.hardlink_to(wav)
        except OSError:
            shutil.copy(wav, dst)
        subprocess.run(["lame", "--quiet", "-b", "320", "-q", "0", "--add-id3v2", "--tt", title, "--ta", ARTIST, "--tl", ALBUM, "--ty", str(YEAR),
                        "--tn", f"{n}/{len(ORDER)}", "--tg", "House", "--tv", f"TCOM={COMPOSER}", "--tv", f"TPE2={ARTIST}", "--ti", str(cover),
                        str(wav), str(OUT / f"{name}.mp3")], check=True)
        first = (tdir / "notes.txt").read_text().splitlines()[0] if (tdir / "notes.txt").exists() else ""
        key = first.split(", ")[2] if first.count(", ") >= 2 else ""
        bpm = first.split(", ")[1] if first.count(", ") >= 1 else ""
        secs = sf.info(str(wav)).duration
        lines.append(f"| {n} | {title} | {NOTES.get(wav.name, wav.name)} | {key} | {bpm} | {int(secs // 60)}:{int(secs % 60):02d} |")
    lines += ["", "Each track's folder in `tracks/` holds its MIDI, LMMS project (.mmp), stems, mix moves and notes."]
    (OUT / "README.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
