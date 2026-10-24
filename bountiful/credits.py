"""Who a Bountiful Music release is by. Every script, tag and export takes the artist from here; nothing overrides it.

    from credits import ARTIST, COMPOSER, stamp
"""
from __future__ import annotations

ARTIST = "M4S4T0"
COMPOSER = "C-Lizzy"                          # the songwriter credit on the albums
PRODUCED_COMPOSER = "C-Lizzy & Bountiful Music"   # the composer tag of a track made by build.py


def stamp(meta: dict) -> dict:
    """meta with the artist (and album artist) set to ARTIST, whatever it said before."""
    out = dict(meta)
    out["artist"] = ARTIST
    if "album_artist" in out or out.get("album"):
        out["album_artist"] = ARTIST
    return out
