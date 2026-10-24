#!/usr/bin/env python3
"""'Put on the Pixel': M4S4T0, composed by C-Lizzy. Eight demoscene drum & bass tunes on chip drum kits, Copper Bars first.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/pixel_album.py [slug ...]   build songs (default: all)
    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/pixel_album.py --assemble   -> albums/put-on-the-pixel/
    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/pixel_album.py --cover      only redraw the cover

The songs are in pixel_songs.py, their drum machines in pixel_kits.py; Copper Bars is built by pixel_dnb.py.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pixel_songs as S

ROOT = S.ROOT
OUT = ROOT / "albums" / "put-on-the-pixel"
ORDER = [(1, "Copper Bars", "copper-bars"), (2, "Raster Interrupt", "raster-interrupt"), (3, "Sine Scroller", "sine-scroller"),
         (4, "Bitplane Blues", "bitplane-blues"), (5, "Vector Balls", "vector-balls"), (6, "Greetings", "greetings"),
         (7, "Plasma", "plasma"), (8, "Last Frame", "last-frame")]
NOTES = {"copper-bars": "NES kit, two-step; chip PWM lead, SID arps, square pads, BitInvader e-piano",
         "raster-interrupt": "the C-Lizzy break as an 8-bit ProTracker sample; SID lead and arps",
         "sine-scroller": "SID drums, half-time into two-step; square-to-sine lead, mystic bells",
         "bitplane-blues": "soft NES kit with a jazz ride, swung; walking SID bass, e-piano",
         "vector-balls": "Game Boy kit, steppers with triplet tom runs; triplet-32nd SID arps",
         "greetings": "bright NES kit, liquid roller in F major; pulse organ stabs",
         "plasma": "the break crushed to 6-bit / 11 kHz, chopped; noisy pulse pads",
         "last-frame": "the closer: Copper Bars' song and kit, half-time, a toy-piano melody"}


def build(slugs):
    import lmms_tracks as LT
    import pixel_kits as K
    for slug in slugs:
        spec = S.SPECS[slug]
        K.build(spec["kit"]["machine"], spec["kit"]["dir"], **spec["kit"]["params"])
        print(f"== {spec['title']}", flush=True)
        LT.make(spec)


def make_cover(path: Path):
    """Pixel art at 280x280, scaled x5 with no smoothing: a starfield, copper bars on a sine, a checkerboard floor and the title."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    W, X = 280, 5
    rng = np.random.default_rng(1985)
    img = np.zeros((W, W, 3), float)
    img[:] = (6, 4, 18)
    for _ in range(140):                                                    # stars, a few brighter
        x, y = rng.integers(0, W, 2)
        img[y, x] = rng.choice([90, 150, 230]) * np.array([1, 1, 1.1])
    # the copper bars: 7 raster bars swinging on a sine, each a gradient of the copper palette, back to front
    pal = [(255, 60, 60), (255, 150, 40), (255, 230, 60), (60, 230, 120), (60, 170, 255), (150, 80, 255), (255, 80, 200)]
    for i, c in enumerate(pal):
        cy = 150 + 34 * np.sin(i * 0.9)
        for dy in range(-6, 7):
            shade = (1 - abs(dy) / 7) ** 0.7
            row = int(round(cy + dy))
            img[row, :] = np.minimum(255, np.array(c) * shade + 255 * max(0, shade - 0.85) * 2)
    # a perspective checkerboard below the bars
    hz = 196
    for y in range(hz + 1, W):
        z = 200 / (y - hz + 2)                                              # depth: big near the bottom, small at the horizon
        fade = ((y - hz) / (W - hz)) ** 1.3
        for x in range(W):
            on = (int(np.floor((x - W / 2) * z / 30)) + int(np.floor(z))) % 2
            img[y, x] = np.array((6, 4, 18)) * (1 - fade) + (np.array((220, 60, 200)) if on else np.array((40, 12, 90))) * fade
    img[250:268, :] *= 0.25                                                 # a dark strip under the artist's name
    img[hz, :] = (255, 255, 255)
    im = Image.fromarray(np.clip(img, 0, 255).astype("uint8"))

    def font(sz):
        return ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf", sz)

    def title(text, y, sz, top, bot):
        """Hard-edged text with a vertical gradient fill and a one-pixel drop shadow, centred."""
        m = Image.new("L", (W, W))
        dm = ImageDraw.Draw(m)
        dm.fontmode = "1"
        w = dm.textlength(text, font=font(sz))
        dm.text(((W - w) / 2, y), text, font=font(sz), fill=255)
        a = np.array(m) > 0
        sh = np.zeros_like(a)
        sh[2:, 2:] = a[:-2, :-2]
        arr = np.array(im).astype(float)
        arr[sh & ~a] = (0, 0, 0)
        ys = np.arange(W)[:, None] * np.ones((1, W))
        t = np.clip((ys - y) / (sz * 1.1), 0, 1)[..., None]
        grad = np.array(top) * (1 - t) + np.array(bot) * t
        arr[a] = grad[a]
        return Image.fromarray(arr.astype("uint8"))

    im = title("PUT ON THE", 16, 26, (255, 255, 255), (120, 200, 255))
    im = title("PIXEL", 42, 62, (255, 250, 120), (255, 70, 40))
    im = title("M4S4T0", 256, 14, (255, 255, 255), (200, 200, 255))
    d = ImageDraw.Draw(im)                                                  # a scroller of greetings, letters on a sine
    d.fontmode = "1"
    for i, ch in enumerate("GREETZ TO C-LIZZY"):
        d.text((32 + i * 13, 118 + 5 * np.sin(i * 0.7)), ch, font=font(11), fill=(255, 255, 255))
    im.resize((W * X, W * X), Image.NEAREST).save(path, quality=95)


def assemble():
    OUT.mkdir(parents=True, exist_ok=True)
    cover = OUT / "cover.jpg"
    make_cover(cover)
    lines = [f"# {S.ALBUM}", "", f"**{S.ARTIST}** · composed by {S.COMPOSER} · {S.YEAR}", "",
             "Demoscene drum & bass: chip drum kits synthesised the way the NES, Game Boy, C64 and Amiga made drums, "
             "chip pads and leads from LMMS, slow and jazzy.", "",
             "| # | Title | Sound | Key | Tempo | Length |", "|---|---|---|---|---|---|"]
    for n, title, slug in ORDER:
        tdir = ROOT / "tracks" / slug
        wav = next((p for p in (tdir / "exports" / f"{slug}-master.wav", tdir / "exports" / f"{slug}.wav") if p.exists()), tdir / "exports" / f"{slug}.wav")
        if not wav.exists():
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
        subprocess.run(["lame", "--quiet", "-b", "320", "-q", "0", "--add-id3v2", "--tt", title, "--ta", S.ARTIST, "--tl", S.ALBUM, "--ty", str(S.YEAR),
                        "--tn", f"{n}/{len(ORDER)}", "--tg", "Drum & Bass", "--tv", f"TCOM={S.COMPOSER}", "--tv", f"TPE2={S.ARTIST}", "--ti", str(cover),
                        str(wav), str(OUT / f"{name}.mp3")], check=True)
        first = (tdir / "notes.txt").read_text().splitlines()[0] if (tdir / "notes.txt").exists() else ""
        parts = first.split(", ")
        bpm, key = (parts[1], parts[2]) if len(parts) >= 3 else ("", "")
        secs = sf.info(str(wav)).duration
        lines.append(f"| {n} | {title} | {NOTES[slug]} | {key} | {bpm} | {int(secs // 60)}:{int(secs % 60):02d} |")
    lines += ["", "Masters: mixed and mastered from the stems by `bountiful/pixel_master.py` (bus processing, transitions, album-matched EQ, "
              "multiband, M/S, true-peak limiting; 24-bit WAV, 320k MP3). Each track's folder in `tracks/` holds its MIDI, LMMS project (.mmp), stems, mix moves and notes. "
              "Rebuild a song with `bountiful/pixel_album.py <slug>` (Copper Bars: `bountiful/pixel_dnb.py`)."]
    (OUT / "README.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--cover"]:
        OUT.mkdir(parents=True, exist_ok=True)
        make_cover(OUT / "cover.jpg")
    elif args == ["--assemble"]:
        assemble()
    else:
        build(args or list(S.SPECS))
