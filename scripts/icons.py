"""Render the logo (bountiful/daw/logo.svg) into the hicolor icon theme: PNGs at the usual sizes plus the SVG.

    python scripts/icons.py [icon theme dir, default ~/.local/share/icons/hicolor]
"""
import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

APP_ID = "dev.m4s4t0.bountiful"
SVG = Path(__file__).resolve().parent.parent / "bountiful" / "daw" / "logo.svg"


def main():
    theme = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".local/share/icons/hicolor"
    _app = QGuiApplication([])
    r = QSvgRenderer(str(SVG))
    for n in (16, 22, 24, 32, 48, 64, 128, 256, 512):
        img = QImage(n, n, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        r.render(p)
        p.end()
        d = theme / f"{n}x{n}" / "apps"
        d.mkdir(parents=True, exist_ok=True)
        img.save(str(d / f"{APP_ID}.png"))
    d = theme / "scalable" / "apps"
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy(SVG, d / f"{APP_ID}.svg")
    print(f"icons in {theme}")
    del _app


if __name__ == "__main__":
    main()
