"""Album cover for the M4S4T0 jazz-hop singles (Sonora at Midnight, Ninth Street Blue).

A late-60s / early-70s abstract: a soft Rothko colour field in deep violet over
an indigo ground, a hard-edge cyan disc printed slightly off-register like a
screen print, a black "midnight" eclipse, thin orbit lines, a halftone patch
and aged paper grain. Pure numpy + Pillow, no inputs.

Run: python3 bountiful/jazzhop_cover.py   (system python: needs numpy + Pillow)
Out: albums/m4s4t0-jazz-hop/cover.{png,jpg} (3000 px) and cover_text.jpg
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "albums" / "m4s4t0-jazz-hop"
ARTIST = "M4S4T0"
W = 3000
rng = np.random.default_rng(1969)
Y, X = np.mgrid[0:W, 0:W].astype(np.float32) / W

INK = np.array([13, 10, 26], np.float32)        # midnight ground
VIOLET = np.array([82, 34, 120], np.float32)    # the colour field
PLUM = np.array([128, 52, 150], np.float32)     # hard-edge band
CYAN = np.array([22, 196, 206], np.float32)     # the disc
TEAL = np.array([10, 58, 74], np.float32)       # lower field
LAVENDER = np.array([206, 190, 228], np.float32)
PAPER = np.array([236, 226, 206], np.float32)


def noise(rows: int, cols: int) -> np.ndarray:
    """Smooth value noise in [0, 1]; a non-square grid stretches it into brush streaks."""
    im = Image.fromarray((rng.random((rows, cols)) * 255).astype(np.uint8))
    return np.asarray(im.resize((W, W), Image.BICUBIC), np.float32) / 255


def blur(m: np.ndarray, r: float) -> np.ndarray:
    im = Image.fromarray((np.clip(m, 0, 1) * 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255


def smooth(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - edge0) / (edge1 - edge0), 0, 1)
    return t * t * (3 - 2 * t)


def paint(img: np.ndarray, mask: np.ndarray, color, opacity: float = 1.0, mode: str = "normal") -> None:
    m = (np.clip(mask, 0, 1) * opacity)[..., None]
    c = np.broadcast_to(np.asarray(color, np.float32), img.shape) if np.ndim(color) == 1 else color
    if mode == "screen":
        c = 255 - (255 - img) * (255 - c) / 255
    elif mode == "multiply":
        c = img * c / 255
    img[:] = img * (1 - m) + c * m


def rect_mask(x0, y0, x1, y1, soft, wobble) -> np.ndarray:
    """A painted rectangle: soft, uneven edges like a Rothko field."""
    n = (noise(70, 70) - 0.5) * wobble + (noise(300, 300) - 0.5) * wobble * 0.08
    d = np.minimum.reduce([X - x0, x1 - X, Y - y0, y1 - Y]) + n
    return smooth(-soft, soft, d)


def disc(cx, cy, r, rough=0.0) -> np.ndarray:
    d = r - np.hypot(X - cx, Y - cy)
    if rough:
        d = d + (noise(90, 90) - 0.5) * rough
    return smooth(-0.0012, 0.0012, d)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # ground: indigo-black, a little lighter low down, with slow mottling
    img = np.broadcast_to(INK, (W, W, 3)).copy()
    img += (noise(6, 6) - 0.5)[..., None] * 14 + (Y * 10)[..., None]

    # the upper colour field: violet, brushed in horizontal strokes
    streak = noise(500, 18) * 0.6 + noise(60, 6) * 0.4
    field = VIOLET * (0.75 + 0.45 * streak[..., None])
    paint(img, rect_mask(0.07, 0.06, 0.93, 0.50, 0.01, 0.012), field, 0.95)
    # a darker veil inside it, the way Rothko layered thin glazes
    paint(img, rect_mask(0.14, 0.14, 0.86, 0.40, 0.04, 0.02), INK, 0.28)

    # the lower field: deep teal, thinner paint
    streak = noise(400, 14)
    paint(img, rect_mask(0.07, 0.56, 0.93, 0.93, 0.01, 0.01), TEAL * (0.7 + 0.5 * streak[..., None]), 0.9)

    # hard-edge diagonal band in plum, cut cleanly across both fields
    u = (X - 0.05) * 0.8 - (Y - 0.95) * 0.6
    band = smooth(0.0, 0.002, u - 0.30) * smooth(0.0, 0.002, 0.40 - u)
    paint(img, band * (0.85 + 0.15 * noise(120, 120)), PLUM, 0.78)

    # halftone dots, lower left, fading toward the centre
    step = 26
    gx, gy = (X * W) % step - step / 2, (Y * W) % step - step / 2
    cell = np.hypot(gx, gy) / step
    amount = smooth(0.34, 0.04, np.hypot(X - 0.07, Y - 0.93)) * 0.5
    paint(img, smooth(0.0, 0.03, amount - cell), CYAN, 0.45)

    # orbit lines around where the disc will sit
    cx, cy = 0.64, 0.47
    rr = np.hypot(X - cx, Y - cy)
    for r, w, o in ((0.305, 0.0016, 0.55), (0.33, 0.0009, 0.4), (0.39, 0.0007, 0.25)):
        paint(img, smooth(w, 0, np.abs(rr - r)), LAVENDER, o)

    # the cyan disc, screen-printed: a magenta ghost off-register, then the cyan, with ink texture
    paint(img, disc(cx - 0.006, cy + 0.004, 0.245, 0.0025), PLUM, 0.6, "screen")
    ink = 0.88 + 0.12 * noise(120, 120) - 0.07 * (noise(700, 700) > 0.88)
    paint(img, disc(cx, cy, 0.245, 0.0015), CYAN * ink[..., None], 0.96)
    # light falloff across the disc, like uneven ink coverage
    paint(img, disc(cx, cy, 0.245) * smooth(-0.2, 0.25, (X - cx) + (Y - cy)), INK, 0.35)

    # the midnight eclipse
    paint(img, blur(disc(0.47, 0.34, 0.135), 30), np.array([60, 230, 235], np.float32), 0.35, "screen")
    paint(img, disc(0.47, 0.34, 0.135, 0.002), INK * 0.8, 1.0)

    # a small hot moon
    paint(img, disc(0.24, 0.30, 0.035, 0.002), np.array([232, 120, 205], np.float32), 0.9)

    # age it: lifted blacks, a slight warm fade, paper fibres, grain, vignette
    img = img * 0.93 + 9
    lum = img.mean(2, keepdims=True)
    img = img * 0.9 + lum * 0.1                         # a touch of fading
    fibres = noise(1500, 40) * 0.5 + noise(40, 1500) * 0.5
    paint(img, smooth(0.7, 0.95, fibres), PAPER, 0.06)
    img += rng.normal(0, 7, (W, W, 1)).astype(np.float32) + rng.normal(0, 2.5, (W, W, 3)).astype(np.float32)
    vig = 1 - 0.38 * smooth(0.45, 0.95, np.hypot(X - 0.5, Y - 0.5) * 1.35)
    img *= vig[..., None]

    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    im.save(OUT / "cover.png", optimize=True)
    im.save(OUT / "cover.jpg", quality=93)

    # variant with the artist name, set small like an old label credit
    t = im.copy()
    d = ImageDraw.Draw(t)
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import paths
    font = paths.font("DejaVuSansCondensed-Bold.ttf", 110)
    x = 0.07 * W
    for ch in ARTIST:
        d.text((x, 0.955 * W - 110), ch, font=font, fill=(226, 216, 236))
        x += d.textlength(ch, font=font) + 34
    t.save(OUT / "cover_text.jpg", quality=93)
    im.resize((1280, 1280), Image.LANCZOS).save("/tmp/cover_preview.jpg", quality=88)


if __name__ == "__main__":
    main()
