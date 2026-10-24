"""A day of ideas: many Bounties at once, the best first, ready to audition and rate.

For each Bounty: the song plan (key, tempo, chords), the ideas the machine keeps, scored by the critic and your
taste. They are ranked and written to <data>/sessions/<date>[-n]/ with an index (index.md, index.json), an audition
WAV of each one's best idea, and for the top few (--songs K) the whole song as a track folder (render it from the DAW
or with build.py --render).

    $PY bountiful/batch.py --count 40 [--start 2000] [--songs 3] [--render]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import zlib
from pathlib import Path

import numpy as np

import build as B
import electronium as EL
import electronium_song as ES
import taste
from paths import DATA


def session_dir(base: Path | None = None) -> Path:
    base = base or DATA / "sessions"
    day = dt.date.today().isoformat()
    d, n = base / day, 1
    while d.exists():
        n += 1
        d = base / f"{day}-{n}"
    d.mkdir(parents=True)
    return d


def look(bounty) -> dict:
    """One Bounty, summed up: its plan and kept ideas, with a score (critic + your taste)."""
    pl = ES.plan(bounty)
    p = EL.patch(pl["patch"])
    keep = EL.kept(p)
    score = float(np.mean([i["score"] for i in keep])) if keep else -9.0
    loops = {k: ES.chord_text(v, pl["tonic"], pl["mode"]) for k, v in pl["loops"].items()}
    return {"bounty": bounty, "title": pl["title"], "key": pl["key"], "bpm": pl["bpm"], "score": round(score, 3),
            "ideas": [{"n": i["n"], "cells": [list(c) for c in i["cells"]], "score": i["score"], "notation": EL.notation(i["cells"])}
                      for i in keep], "chords": loops, "_pl": pl}


def day(count: int = 30, start: int | None = None, songs: int = 0, render: bool = False, out: Path | None = None,
        log=print) -> Path:
    if start is None:
        start = zlib.crc32(dt.date.today().isoformat().encode()) % 90000 + 1000
    d = out or session_dir()
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    for k in range(count):
        rows.append(look(start + k))
        log(f"  {k + 1}/{count}  Bounty {start + k}: {rows[-1]['title']} ({rows[-1]['key']}, {rows[-1]['bpm']:g} bpm) score {rows[-1]['score']:+.2f}")
    rows.sort(key=lambda r: -r["score"])
    for rank, r in enumerate(rows, 1):
        pl = r.pop("_pl")
        r["rank"] = rank
        if r["ideas"]:
            ch = {c["name"]: c for c in EL.channels(pl["patch"])}
            wav = d / f"{rank:02d}-{r['bounty']}-idea.wav"
            taste.write_wav(wav, taste.audition(r["ideas"][0], pl["tonic"], pl["mode"], pl["bpm"], EL.tone(ch["lead"])))
            r["audition"] = wav.name
        if rank <= songs:
            t = ES.song(r["bounty"], out=d / f"{rank:02d}-{B.slug(r['title'])}", log=lambda *_: None)
            r["track"] = t.name
            if render:
                log(f"rendering {r['title']} ...")
                B.render(t, log=log)
    (d / "index.json").write_text(json.dumps({"start": start, "count": count, "made": dt.datetime.now().isoformat(timespec="seconds"),
                                              "taste": taste.model() is not None, "rows": rows}, indent=1))
    md = [f"# A day of ideas — {d.name}", "", f"Bounties {start}–{start + count - 1}, best first"
          f"{' (with your taste)' if taste.model() else ''}.", "",
          "| # | Bounty | Title | Key | BPM | Score | Best idea | Song |", "|---|---|---|---|---|---|---|---|"]
    md += [f"| {r['rank']} | {r['bounty']} | {r['title']} | {r['key']} | {r['bpm']:g} | {r['score']:+.2f} | "
           f"{'`' + r['ideas'][0]['notation'].replace('|', '¦') + '`' if r['ideas'] else ''} | {r.get('track', '')} |" for r in rows]
    (d / "index.md").write_text("\n".join(md) + "\n")
    log(f"wrote {d}")
    return d


def sessions() -> list[Path]:
    base = DATA / "sessions"
    return sorted((p for p in base.glob("*") if (p / "index.json").exists()), reverse=True) if base.exists() else []


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--count", type=int, default=30)
    ap.add_argument("--start", type=int, help="the first Bounty (default: from today's date)")
    ap.add_argument("--songs", type=int, default=0, help="write the top K as whole songs")
    ap.add_argument("--render", action="store_true", help="and render them")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    day(a.count, a.start, a.songs, a.render, a.out)


if __name__ == "__main__":
    main()
