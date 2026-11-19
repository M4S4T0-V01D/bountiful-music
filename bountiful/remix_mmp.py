#!/usr/bin/env python3
"""Render a hand-edited LMMS project (a track folder's <slug>.mmp) without touching it, then put the intelligent-jungle
mix (EQ, sends, chorus, Leslie, sidechain, filter automation, width) and master on top. The project's own volumes,
mutes, notes and effects are the balance: no level trims from instruments.toml are applied.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/remix_mmp.py tracks/acid-corridor [tracks/...]
    -> exports/<slug>-mmp.wav (24-bit) and .mp3 (tagged), stems-mmp/, exports/render_info-mmp.json
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from credits import ARTIST  # noqa: E402
import soundfile as sf

from paths import ENGINE  # noqa: E402
sys.path.insert(0, str(ENGINE / "studio"))
sys.path.insert(0, str(ENGINE))
import render_midi as RM  # noqa: E402
from engine import fx  # noqa: E402
from engine.export import analyse, mp3, write_audio  # noqa: E402
from engine.render import master  # noqa: E402

SR = 44100


def read_project(mmp: Path) -> str:
    raw = mmp.read_bytes()
    return (gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw).decode("utf8", "replace")


def strip_gain_plugins(txt: str) -> tuple[str, dict]:
    """Carla's 'Audio Gain' LV2 plugin needs an LV2 worker that headless LMMS lacks (it aborts). It only multiplies the
    signal, so it is removed from the render copy and its gain is applied to that track afterwards (same result)."""
    gains = {}
    def track_sub(m):
        body = m.group(0)
        name = re.search(r'\bname="([^"]*)"', body).group(1)
        def eff_sub(e):
            if "carla/plugins/audiogain" not in e.group(0):
                return e.group(0)
            g = re.search(r'\bgain="([^"]+)"', e.group(0))
            on = re.search(r'\bon="([^"]+)"', e.group(0))
            if on is None or on.group(1) == "1":
                gains[name] = gains.get(name, 1.0) * float(g.group(1) if g else 1.0)
            return ""
        body2 = re.sub(r'<effect\b[^>]*>.*?</effect>', eff_sub, body, flags=re.S)
        n_left = len(re.findall(r'<effect\b', body2))
        return re.sub(r'(<fxchain\b[^>]*\bnumofeffects=")\d+(")', lambda f: f.group(1) + str(n_left) + f.group(2), body2)
    txt = re.sub(r'<track\b[^>]*>.*?</track>', track_sub, txt, flags=re.S)
    return txt, gains


def remix(track: Path, log=print, mmp: Path | None = None, tag: str = "mmp") -> Path:
    """mmp: another project file in the folder (default <slug>.mmp); tag names the outputs (<slug>-<tag>.wav, stems-<tag>/)."""
    slug = track.name
    mmp = mmp or track / f"{slug}.mmp"
    before = hashlib.sha256(mmp.read_bytes()).hexdigest()
    x = read_project(mmp)
    bpm = float(re.search(r'<head[^>]*\bbpm="([^"]+)"', x).group(1))
    names = [m.group(1) for m in re.finditer(r'<track\b[^>]*\bname="([^"]*)"', x)]
    kicks = []
    m = re.search(r'<track\b[^>]*\bname="drum - kick"[^>]*>.*?</track>', x, re.S)
    if m:
        for clip in re.finditer(r'<midiclip\b([^>]*)>(.*?)</midiclip>', m.group(0), re.S):
            if re.search(r'\bmuted="1"', clip.group(1)):
                continue
            base = int(re.search(r'\bpos="(\d+)"', clip.group(1)).group(1))
            kicks += [(base + int(p)) / 48 * 60 / bpm for p in re.findall(r'<note\b[^>]*\bpos="(\d+)"', clip.group(2))]
    cfg = tomllib.loads((track / "instruments.toml").read_text())
    over = track / f"mix-{tag}.toml"             # a render's own mix moves (filter sweeps, pans, master) on top of instruments.toml
    if tag != "mmp" and over.exists():
        def merge(a, b):
            for k, v in b.items():
                a[k] = merge(a.get(k, {}), v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
            return a
        cfg = merge(cfg, tomllib.loads(over.read_text()))
        log(f"  mix moves from {over.name}")
    tracks = cfg["tracks"]
    drums = tracks.get("drums", {})
    sound_stem = {s: v.get("stem", s) for s, v in drums.get("sounds", {}).items()}
    log(f"{slug}.mmp: {len(names)} tracks, {bpm:g} bpm, {len(kicks)} kick hits; LMMS renders each track (from a copy) ...")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        # LMMS writes each track to a file named after it: '/' in a name would break that, so the copy's names are cleaned
        txt = re.sub(r'(<track\b[^>]*\bname=")([^"]*)(")', lambda mm: mm.group(1) + mm.group(2).replace("/", "-") + mm.group(3), x)
        txt, gains = strip_gain_plugins(txt)
        for nm, g in gains.items():
            log(f"  {nm}: Carla Audio Gain x{g:.3g} ({20 * np.log10(max(g, 1e-6)):+.1f} dB) applied after rendering (headless LMMS cannot run Carla plugins)")
        (d / "p.mmp").write_text(txt)
        (d / "out").mkdir()
        r = subprocess.run(["nice", "-n", "12", "lmms", "rendertracks", str(d / "p.mmp"), "-o", str(d / "out"), "-f", "wav", "-a", "-s", str(SR)],
                           capture_output=True, text=True, timeout=3600)
        files = sorted((d / "out").glob("*.wav"), key=lambda f: int(f.name.split("_", 1)[0]))
        rendered = {f.name.split("_", 1)[1][:-4]: f for f in files}
        raw = {}
        for nm in names:
            f = rendered.get(nm.replace("/", "-"))
            if f is None:
                continue
            a, _ = sf.read(str(f), dtype="float32", always_2d=True)
            a = a * gains.get(nm.replace("/", "-"), 1.0)
            raw[nm] = a if a.shape[1] == 2 else np.repeat(a, 2, 1)
        if not raw:
            raise SystemExit(f"LMMS rendered nothing\n{r.stdout[-500:]}\n{r.stderr[-500:]}")
        missing = [nm for nm in names if nm not in raw]
        if missing:
            log(f"  not rendered by LMMS (muted or empty?): {missing}")
    n = max(len(a) for a in raw.values())
    beat_s = 60 / bpm
    sends = {}
    for k, s in {**RM.DEFAULT_SENDS, **cfg.get("sends", {})}.items():
        sends[k] = fx.delay_ir(beat_s, s["time_beats"], s["feedback"], s.get("taps", 6), s.get("tone", 3000)) if s["type"] == "delay" \
            else fx.reverb_ir(s["seconds"], s.get("predelay", 0.02), s.get("damp", 0.5), size=s.get("size", 1.0))
    auto = cfg.get("automation", [])
    out: dict[str, np.ndarray] = {}
    for nm, a in raw.items():
        a = np.pad(a, ((0, n - len(a)), (0, 0)))
        if nm.startswith("drum - "):
            stem = sound_stem.get(nm[7:], "perc")
            key, c = stem, dict(drums.get("stems", {}).get(stem, {}))
            if nm[7:] in cfg.get("drum_pan", {}):     # a pan for one drum sound (e.g. toms spread across the kit)
                c["pan"] = cfg["drum_pan"][nm[7:]]
        else:
            key = nm.split(" - ")[0]
            c, stem = dict(tracks.get(key, {})), key
        for k in ("gain_db", "kind", "voice", "fallback", "lmms_fx", "transpose", "preset", "layers"):
            c.pop(k, None)
        if c.get("mix_gain_db"):                # a mix trim for a part we added (the user's own faders stay as they are)
            c["gain_db"] = c.pop("mix_gain_db")
        y = RM.process(key, a, c, auto, bpm, n, 0.0, sends, [] if stem == "kick" else kicks)
        out[stem] = out[stem] + y if stem in out else y
    pre = sum(out.values())
    if cfg.get("mix", {}).get("console_drive"):
        pre = fx.console(pre, cfg["mix"]["console_drive"])
    peak = float(np.abs(pre).max())
    scale = 0.5 / peak if peak > 0.5 else 1.0
    sd = track / f"stems-{tag}"
    sd.mkdir(exist_ok=True)
    for s, y in out.items():
        write_audio(sd / f"{s}.wav", y * scale)
    final, minfo = master(pre, {"master": cfg.get("master", {})})
    fade = int(1.5 * SR)
    final[-fade:] *= np.linspace(1, 0, fade)[:, None] ** 2
    ex = track / "exports"
    wav = ex / f"{slug}-{tag}.wav"
    write_audio(ex / f"{slug}-{tag}_premaster.wav", pre * scale)
    write_audio(wav, final)
    meta = cfg.get("meta", {})
    mp3(wav, ex / f"{slug}-{tag}.mp3", {"title": f"{meta.get('title', slug)} (LMMS edit{'' if tag == 'mmp' else ' ' + tag})", "artist": ARTIST, "album": meta.get("album", ""),
                                       "composer": meta.get("composer", ""), "genre": meta.get("genre", ""), "track": meta.get("track", 1)})
    a_ = analyse(final, None, wav.name)
    (ex / f"render_info-{tag}.json").write_text(json.dumps({"source": str(mmp), "stem_scale": scale, "master": minfo, "analysis": a_}, indent=1, default=float))
    after = hashlib.sha256(mmp.read_bytes()).hexdigest()
    log(f"DONE {wav}: {len(final) / SR:.1f} s, {a_['integrated_lufs']} LUFS, TP {a_['true_peak_dbtp_approx']} dBTP; "
        f"{mmp.name} {'unchanged' if before == after else 'CHANGED DURING RENDER'}")
    return wav


if __name__ == "__main__":
    args = sys.argv[1:]
    opt = lambda k: args[args.index(k) + 1] if k in args else None
    folders = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in ("--mmp", "--tag"))]
    for t in folders:
        t = Path(t).resolve()
        remix(t, mmp=t / opt("--mmp") if opt("--mmp") else None, tag=opt("--tag") or "mmp")
