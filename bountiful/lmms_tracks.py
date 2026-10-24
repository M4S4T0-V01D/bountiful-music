"""Bountiful MIDI played by LMMS instruments (the 'Zona' recipe, reusable).

    spec = {"title": ..., "song": .am.json, "genre": "soviet-darkwave-87", "overrides": {...genre changes...},
            "voices": {"bass": (voice, label, mix), "lead": ..., ...}, "layers": [("bass", "bass_sub"), ("pad", "choir")]}
    make(spec)   -> tracks/<slug>/: MIDI, instruments.toml (LMMS voices + effect chains + engine fallbacks),
                    exports/ (WAV, MP3), stems/, <slug>.mmp (LMMS project), README.md

Two checks run on a test render of the first chorus before the full render:
  * octave  - an LMMS preset that sounds an octave below its written notes (energy at f/2 above f)
              is transposed up 12 (LMMS presets differ in their base octave)
  * levels  - every part is trimmed to a target level relative to the kick (LMMS presets differ by up
              to 30 dB), so a new set of sounds still lands in a mix that is known to work
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import mido
import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build as B  # noqa: E402

sys.path.insert(0, str(B.ENGINE / "studio"))
sys.path.insert(0, str(B.ENGINE))
from midi_studio import to_toml  # noqa: E402
from render_midi import lmms_notes, read_midi  # noqa: E402

# target level of each part relative to the kick (dB of active RMS), from the Zona mix
TARGET = {"lead": -4.5, "bass": -6.0, "bass_sub": -20.0, "arp": -13.0, "pad": -17.0, "choir": -23.0}
DRUM_SAMPLES = {"shaker": "drums/shaker02.ogg", "tom_hi": "drums/tom_hi01.ogg", "tom_mid": "drums/tom_mid01.ogg", "tom_lo": "drums/tom_low01.ogg",
                "kick": "drums/bassdrum01.ogg", "snare": "drums/snare01.ogg", "clap": "drums/clap02.ogg", "hat": "drums/hihat_closed01.ogg",
                "open": "drums/hihat_opened02.ogg", "crash": "drums/crash02.ogg", "rim": "drums/rim01.ogg",
                "syntom_hi": "drums/tom_hi01.ogg", "syntom_mid": "drums/tom_mid01.ogg", "syntom_lo": "drums/tom_low01.ogg"}
KITS = {"fusion": "80s session kit: acoustic LMMS samples, ghost notes, gated snare, toms", "synthetic": "synthetic 80s drum machine (engine)", "house": "909-style house kit: LMMS drum samples + synth layers, congas, timbales",
        "linn": "LinnDrum-style kit (LMMS samples)", "breaks": "breakbeat kit (LMMS samples)", "dusty": "dusty boom-bap kit (LMMS samples)"}
MMP_VOL = {"stab": 45, "lead": 55, "lead_hi": 28, "arp": 36, "pad": 34, "choir": 25, "bass": 60, "bass_sub": 42, "comp": 50, "vox": 40}


def deep_update(d: dict, u: dict) -> dict:
    for k, v in u.items():
        d[k] = deep_update(d.get(k, {}), v) if isinstance(v, dict) and isinstance(d.get(k), dict) else v
    return d


def add_layers(mid: Path, layers):
    mf = mido.MidiFile(mid)
    names = [next((m.name for m in t if m.type == "track_name"), "") for t in mf.tracks]
    for i, (src, new) in enumerate(layers):
        if new in names or src not in names:
            continue
        ch = 6 + i
        nt = mido.MidiTrack()
        for m in mf.tracks[names.index(src)]:
            nt.append(m.copy(name=new) if m.type == "track_name" else m.copy(channel=ch) if hasattr(m, "channel") else m.copy())
        mf.tracks.append(nt)
    mf.save(mid)


def level(x):
    m = x.mean(1) if x.ndim == 2 else x
    k = len(m) // 2048
    r = np.sqrt((m[:k * 2048].reshape(k, 2048) ** 2).mean(1))
    return 20 * np.log10(np.sqrt((r[r > r.max() * 0.03] ** 2).mean()) + 1e-12) if r.max() > 1e-6 else -120.0


def octave_offset(stem: np.ndarray, notes: list, t0: float, sr=44100) -> int:
    """+12 if the part sounds an octave below what is written (its energy sits at f/2, not f)."""
    m = stem.mean(1)
    spec = np.abs(np.fft.rfft(m * np.hanning(len(m))))
    f = np.fft.rfftfreq(len(m), 1 / sr)
    def e(hz):
        sel = (f > hz * 0.985) & (f < hz * 1.015)
        return spec[sel].max() if sel.any() else 0.0
    w: dict = {}
    for n in notes:
        w[n["pitch"]] = w.get(n["pitch"], 0) + (n["end"] - n["start"])
    low = mid = 0.0
    for p, wt in w.items():
        hz = 440 * 2 ** ((p - 69) / 12)
        if hz / 2 < 25:
            continue
        low += wt * e(hz / 2)
        mid += wt * e(hz)
    return 12 if low > mid * 1.6 else 0


def chorus_bars(g: dict) -> tuple[int, int]:
    bar = 1
    for blk in g["arrangement"]:
        if blk["loop"] == "A" and "lead" in blk.get("parts", []):
            return bar, bar + 7
        bar += blk["bars"]
    return 1, 8


def render(mid: Path, inst: Path, out: Path, bars: str | None = None, stems: Path | None = None, log=print) -> int:
    cmd = ["nice", "-n", "10", B.PY, "-u", str(B.RENDER), str(mid), str(inst), "--out", str(out)]
    if bars:
        cmd += ["--bars", bars, "--no-mp3", "--name", "test"]
    cmd += ["--stems", str(stems)] if stems else ["--no-stems"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    for line in p.stdout.splitlines():
        if not line.startswith("PROGRESS"):
            log("   " + line)
    return p.returncode


def write_mmp(track: Path, slug: str, T: dict, mmp_drums: bool = True):
    from engine import lmms as LM
    notes, bpm, _ = read_midi(track / f"{slug}.mid")
    tracks = []
    for name, c in T.items():
        if c.get("kind") != "lmms" and not c.get("mmp_voice"):
            continue
        if c.get("kind") != "lmms":           # an engine voice (the Electronium's tone generators): an LMMS stand-in in the project
            c = {"voice": c["mmp_voice"], "transpose": c.get("mmp_transpose", 0)}
        v = dict(c["voice"], vol=MMP_VOL.get(name, 40))
        v.pop("label", None)
        if c.get("lmms_fx"):
            v["fx"] = c["lmms_fx"]
        tracks.append((f"{name} - {c['voice']['label']}".replace("/", "-"), LM.instrument_xml(v),
                       lmms_notes([n for n in notes if n["track"] == name], bpm, 0.0, c.get("transpose", 0)), False))
    dmap = T["drums"]["map"] if mmp_drums else {}
    sounds = T["drums"].get("sounds", {})
    names = {s for s in dmap.values()}
    pick = {snd: (sounds.get(snd, {}).get("samples") or [DRUM_SAMPLES.get(snd)])[0] for snd in names}
    for snd, sample in pick.items():
        if not sample or "&" in str(sample) or "'" in str(sample):
            continue
        keys = [int(k) for k, s in dmap.items() if s == snd]
        dn = [n for n in notes if n["track"] == "drums" and n["pitch"] in keys]
        if dn:
            root = dn[0]["pitch"]
            tracks.append((f"drum - {snd}", LM.instrument_xml({"sample": sample, "root": root, "vol": 45}),
                           lmms_notes([dict(n, pitch=root) for n in dn], bpm, 0.0), False))
    length = int(max(n["end"] for n in notes) / (60 / bpm) * LM.TPB) + LM.TPB * 8
    (track / f"{slug}.mmp").write_text(LM.project_xml(bpm, tracks, length))
    return len(tracks)


def make(spec: dict, log=print) -> Path:
    G = B.genres()
    g = deep_update(copy.deepcopy(G[spec["genre"]]), spec.get("overrides", {}))
    if spec.get("kit_def"):                       # a song's own drum kit (e.g. from the rendered drum machines)
        g["_kit"] = spec["kit_def"]
    title = spec["title"]
    slug = B.slug(title)
    track = B.DATA / "tracks" / slug
    log(f"== {title}: producing the MIDI")
    B.produce(Path(spec["song"]), g, title=title, out=track, seed=spec.get("seed", 1), log=lambda s: None)
    mid = track / f"{slug}.mid"
    add_layers(mid, spec.get("layers", [("bass", "bass_sub"), ("pad", "choir")]))
    cfg = tomllib.loads((track / "instruments.toml").read_text())
    T = cfg["tracks"]
    for name, (voice, label, mix) in spec["voices"].items():
        fb = {k: T[name][k] for k in ("kind", "preset", "layers") if k in T.get(name, {})} or {"kind": "pad", "preset": "formanta-dark.json"}
        T[name] = {"kind": "lmms", "voice": dict(voice, label=label), "fallback": fb, **mix}
    for k, v in spec.get("extra_tracks", {}).items():   # non-LMMS parts (engine instruments), e.g. a Reese
        T[k] = v
    for k, (voice, label) in spec.get("mmp_voices", {}).items():   # LMMS stand-ins in the .mmp for engine-voiced parts
        if k in T:
            T[k]["mmp_voice"] = dict(voice, label=label)
    if "kick" in T["drums"]["stems"] and spec.get("kick_gain", -5.0) is not None:
        T["drums"]["stems"]["kick"]["gain_db"] = spec.get("kick_gain", -5.0)
    for k, v in spec.get("drum_stems", {}).items():
        T["drums"]["stems"].setdefault(k, {}).update(v)
    if spec.get("automation"):
        cfg["automation"] = spec["automation"]
    if spec.get("sends"):
        deep_update(cfg["sends"], spec["sends"])
    cfg["meta"]["composer"] = spec.get("composer", "C-Lizzy & Bountiful Music")
    cfg["meta"].update({k: spec[k] for k in ("album", "track", "year") if k in spec})
    cfg["meta"] = B.stamp(cfg["meta"])          # the artist is always M4S4T0, whatever a spec says
    inst = track / "instruments.toml"
    inst.write_text(to_toml(cfg))

    # test render of the first chorus: octave and level checks
    a, b = spec.get("test_bars") or chorus_bars(g)
    test = track / ".test"
    log(f"   test render, bars {a}-{b}")
    render(mid, inst, test, f"{a}-{b}", test / "stems", log=log)
    info = json.loads((test / "test_info.json").read_text())
    stems = {p.stem: sf.read(str(p))[0] / info["stem_scale"] for p in (test / "stems").glob("*.wav")}
    notes, bpm, _ = read_midi(mid)
    t0, t1 = (a - 1) * 4 * 60 / bpm, b * 4 * 60 / bpm
    changes = []
    moved = False
    for name, c in T.items():                     # 1. octaves first
        if c.get("kind") != "lmms" or name not in stems or name in ("pad", "choir"):
            continue
        ns = [dict(n, pitch=n["pitch"] + c.get("transpose", 0)) for n in notes if n["track"] == name and t0 <= n["start"] < t1]   # as intended to sound
        off = octave_offset(stems[name], ns, t0) if ns else 0
        if off:
            c["transpose"] = c.get("transpose", 0) + off
            changes.append(f"{name} +{off} (sounded an octave low)")
            moved = True
    if moved:                                     # levels are measured on the corrected parts
        inst.write_text(to_toml(cfg))
        render(mid, inst, test, f"{a}-{b}", test / "stems", log=lambda s: None)
        info = json.loads((test / "test_info.json").read_text())
        stems = {p.stem: sf.read(str(p))[0] / info["stem_scale"] for p in (test / "stems").glob("*.wav")}
    ref = spec.get("level_ref") or ("kick" if "kick" in stems else "break")
    kick = level(stems[ref] if ref in stems else next(iter(stems.values())))
    for name, c in T.items():                     # 2. levels against the kick (LMMS parts, and engine parts that have a target)
        if (c.get("kind") != "lmms" and name not in spec.get("targets", {})) or name == "drums" or name not in stems:
            continue
        targets = {**TARGET, **spec.get("targets", {})}
        if name in targets:
            have = level(stems[name]) - kick
            trim = float(np.clip(targets[name] - have, -18, 18))
            c["gain_db"] = round(c.get("gain_db", 0) + trim, 1)
            changes.append(f"{name} {trim:+.1f} dB")
    if "lead_hi" in T and "lead" in T and T["lead_hi"].get("kind") == "lmms" and spec.get("lead_hi_follows_lead", True):
        T["lead_hi"]["gain_db"] = round(T["lead"]["gain_db"] - 10, 1)
    inst.write_text(to_toml(cfg))
    log("   checks: " + ", ".join(changes))

    log("   full render (LMMS + mix)")
    code = render(mid, inst, track / "exports", stems=track / "stems", log=log)
    n = write_mmp(track, slug, T, spec.get("mmp_drums", True))
    import shutil
    shutil.rmtree(test, ignore_errors=True)
    final = json.loads((track / "exports" / "render_info.json").read_text())
    a_ = final["analysis"]
    notes_txt = (track / "notes.txt").read_text()
    rows = "\n".join(f"| {k} | {v['voice']['label']} | {', '.join((e.get('lv2') or e.get('ladspa') or e.get('builtin')) + (' ' + e['preset'] if e.get('preset') else '') for e in v.get('lmms_fx', [])) or '-'} |"
                     for k, v in T.items() if v.get("kind") == "lmms")
    rows += "".join(f"\n| {k} | Electronium tone generator ({v['preset'].get('wave', 'square')}, electronium_voice.py)"
                    f"{'; in the .mmp: ' + v['mmp_voice']['label'] if v.get('mmp_voice') else ''} | - |"
                    for k, v in T.items() if v.get("kind") == "pyvoice")
    (track / "README.md").write_text(f"""# {title} — {B.ARTIST}

{notes_txt.splitlines()[0]}. Composition and MIDI: **Bountiful Music**. Instruments: **LMMS** (headless), mixed and mastered by the
intelligent-jungle renderer. {spec.get('blurb', '')}

**Listen:** `exports/{slug}.mp3` · **Open in LMMS:** `{slug}.mmp` ({n} tracks: same notes, LMMS instruments + effect chains, drums as LMMS sample tracks; the Python mix is not part of it)

| Part | LMMS instrument | LMMS effects |
|---|---|---|
{rows}
| drums | {KITS.get(g.get('kit'), g.get('kit'))} | - |

Loops, arrangement and the composer-tell measurements are in `notes.txt`. Checks on the test render: {', '.join(changes)}.
Master: {a_['integrated_lufs']} LUFS, true peak {a_['true_peak_dbtp_approx']} dBTP.

Rebuild: `{spec.get('rebuild', 'bountiful/darkwave_ep.py ' + slug)}` (from the project folder, with the intelligent-jungle Python).
""")
    log(f"   done: {track} ({'ok' if code == 0 else 'render exit ' + str(code)}), {a_['integrated_lufs']} LUFS, mmp {n} tracks")
    return track
