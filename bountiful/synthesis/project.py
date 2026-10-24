"""A Synthesis Lab project: JSON on disk whose tracks are the very tables a song's instruments.toml uses for
kind = "synthesis" parts (rendering.py), plus what the Lab needs around them. So there is one track format: a Lab
track can be pasted into a song (to_instruments) and a song's synthesis track opened in the Lab (from_instruments).

    {"format": "bountiful-synthesis-project", "format_version": 1, "name": "...",
     "bpm": 174, "seed": 1, "render": {"beats": 16, "sr": 44100, "block": 256, "tail_s": 2.0},
     "assets": {"voice": "voice.wav"},                       # project-level files, relative to the project file
     "tracks": {"pad": {"kind": "synthesis", "engine": "ghost", "version": 1, "preset": ..., "params": {...},
                        "seed": 7, "automation": {...}, "modulation": {...}, "graph": {...}, "assets": {...},
                        "gain_db": -6, "pan": 0.0, "mute": false,
                        "clip": [[beat, length, pitch, velocity 0-1], ...],
                        "start": "<snapshot name>"}},    # optional: the engines begin from this saved state
     "snapshots": {"<name>": {"<track>": <engine snapshot> or {"<node>": <snapshot>} for a graph track}}}

Loading is forgiving: older or newer files load (unknown keys are kept and written back), missing keys take
defaults, a track whose engine this build does not have is kept but skipped when rendering (`problems` says why),
and a track's recorded engine version is kept, a different current version only noted. Rendering is
deterministic: the same project renders the same samples.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np

import synthesis as S
from synthesis.engine_api import beat_events
from synthesis.modulation import Matrix
from synthesis.rendering import automation_of, resolve_assets, track_seed

FORMAT = "bountiful-synthesis-project"
FORMAT_VERSION = 1
RENDER = {"beats": 16.0, "sr": S.SR, "block": S.BLOCK, "tail_s": 2.0}
LAB_KEYS = ("clip", "start", "mute")                 # Lab-only track keys, dropped when a track goes into a song


CLIPS = ("arp", "chords", "bass", "melody", "drone", "hits", "break")


def clip(kind: str, beats: float = 16, root: int = 57, seed: int = 0) -> list:
    """A starting clip [[beat, length, pitch, velocity], ...] in a minor key: deterministic for (kind, beats, root, seed)."""
    rng = np.random.default_rng(seed)
    scale = [0, 2, 3, 5, 7, 8, 10]
    chords = [(0, 3, 7), (8, 12, 15), (3, 7, 10), (10, 14, 17)]          # i - VI - III - VII
    n = int(beats)
    out: list = []
    if kind == "arp":
        out = [[b * 0.5, 0.4, root + 12 + chords[int(b // 8) % 4][b % 3] + 12 * (b % 6 >= 3), 0.75 + 0.2 * (b % 4 == 0)]
               for b in range(n * 2)]
    elif kind == "chords":
        out = [[b, 3.8, root + iv, 0.6] for b in range(0, n, 4) for iv in chords[(b // 4) % 4]]
    elif kind == "bass":
        out = [[b + o, 0.45, root - 12 + chords[(b // 4) % 4][0], 0.9 - 0.2 * (o > 0)]
               for b in range(0, n, 4) for o in (0.0, 1.5, 2.5)]
    elif kind == "melody":
        deg, t = 4, 0.0
        while t < n:
            ln = float(rng.choice([0.5, 0.5, 1.0, 1.5, 2.0]))
            deg = int(np.clip(deg + rng.choice([-2, -1, -1, 1, 1, 2, 3]), 0, 11))
            out.append([t, min(ln, n - t) * 0.9, root + 12 + 12 * (deg // 7) + scale[deg % 7], round(0.6 + 0.3 * rng.random(), 2)])
            t += ln
    elif kind == "drone":
        out = [[0.0, float(n), root - 12, 0.7], [0.0, float(n), root - 5, 0.5]]
    elif kind == "hits":
        out = [[b * 0.5, 0.2, root + 12, 0.9 if b % 4 == 0 else 0.5] for b in range(n * 2) if b % 4 == 0 or rng.random() < 0.3]
    elif kind == "break":                    # General MIDI drums: kick, snare, hat (Breakforge's midi-kit plays these)
        for s in range(n * 4):
            t, ph = s * 0.25, s % 16
            if ph in (0, 10) or (ph == 7 and rng.random() < 0.5):
                out.append([t, 0.2, 36, 1.0])
            if ph in (4, 12) or (ph in (13, 15) and rng.random() < 0.3):
                out.append([t, 0.2, 38, 0.95 if ph in (4, 12) else 0.45])
            if s % 2 == 0:
                out.append([t, 0.1, 42, 0.55 + 0.2 * (s % 4 == 0)])
    else:
        raise ValueError(f"no clip {kind!r}; try one of {', '.join(CLIPS)}")
    return [[round(float(a), 4), round(float(b), 4), int(c), round(float(d), 3)] for a, b, c, d in out]


def new(name: str = "untitled", bpm: float = 120.0, seed: int = 1) -> dict:
    return {"format": FORMAT, "format_version": FORMAT_VERSION, "name": name, "bpm": float(bpm), "seed": int(seed),
            "render": dict(RENDER), "assets": {}, "tracks": {}, "snapshots": {}}


def add_track(proj: dict, name: str, engine: str | None = None, preset: str | None = None, params: dict | None = None,
              clip: list | None = None, **settings) -> dict:
    """A track for an engine (or pass graph = {...}); settings are any other track keys (seed, gain_db, ...)."""
    tr = {"kind": "synthesis", **settings}
    if engine:
        tr["engine"] = engine
        tr["version"] = S.engine_class(engine).VERSION
    if preset:
        tr["preset"] = preset
    if params:
        tr["params"] = dict(params)
    tr["clip"] = [list(c) for c in (clip or [])]
    proj["tracks"][name] = tr
    return tr


def normalise(d: dict) -> dict:
    """Any version of the format -> the current one, keeping keys it does not know."""
    if d.get("format", FORMAT) != FORMAT:
        raise ValueError("not a Bountiful synthesis project")
    if int(d.get("format_version", 1)) > FORMAT_VERSION:
        d = dict(d, _newer=int(d["format_version"]))
    out = new()
    out.update(copy.deepcopy(d))
    out["format"], out["format_version"] = FORMAT, FORMAT_VERSION
    out["render"] = {**RENDER, **out.get("render", {})}
    for tr in out["tracks"].values():
        tr.setdefault("kind", "synthesis")
        tr.setdefault("clip", [])
        if tr.get("engine") in S.ENGINES:
            tr.setdefault("version", S.engine_class(tr["engine"]).VERSION)
    return out


def problems(proj: dict) -> list:
    """Why tracks will not render, or will render differently from when they were saved."""
    out = []
    for name, tr in proj["tracks"].items():
        eids = [nd.get("engine") for nd in tr["graph"].get("nodes", {}).values()] if tr.get("graph") else [tr.get("engine")]
        for eid in eids:
            if eid not in S.ENGINES:
                out.append(f"{name}: no engine {eid!r} in this build; the track is skipped")
        eid = tr.get("engine")
        if eid in S.ENGINES and int(tr.get("version", 1)) != S.engine_class(eid).VERSION:
            out.append(f"{name}: made with {eid} v{tr.get('version')}, this build has "
                       f"v{S.engine_class(eid).VERSION}; the patch loads, the sound may differ")
        if tr.get("start") and tr["start"] not in proj["snapshots"]:
            out.append(f"{name}: starts from snapshot {tr['start']!r}, which is missing; starting fresh")
    return out


def save(proj: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(proj, indent=1, sort_keys=True))
    tmp.replace(path)
    return path


def load(path: Path) -> dict:
    return normalise(json.loads(Path(path).read_text()))


def engines_used(proj: dict) -> dict:
    """engine id -> version, over every track and graph node."""
    out = {}
    for tr in proj["tracks"].values():
        nodes = tr["graph"].get("nodes", {}).values() if tr.get("graph") else [tr]
        for nd in nodes:
            eid = nd.get("engine")
            if eid in S.ENGINES:
                out[eid] = int(nd.get("version", S.engine_class(eid).VERSION))
    return out


def _assets(proj: dict, tr: dict, base: Path | None) -> dict:
    a = {k: proj["assets"].get(v, v) for k, v in (tr.get("assets") or {}).items()}   # a track may name a project asset
    return resolve_assets(a, base)


def build(proj: dict, name: str, base: Path | None = None):
    """The track's engine (or routing graph), seeded, with its starting snapshot restored if it has one."""
    tr = proj["tracks"][name]
    sr = int(proj["render"]["sr"])
    seed = track_seed(tr, proj["seed"], name)
    snap = proj["snapshots"].get(tr.get("start") or "", {}).get(name)
    if tr.get("graph"):
        from synthesis.routing import Graph
        g = Graph(tr["graph"], seed, sr)
        if snap:
            g.restore(snap)
        return g
    e = S.create(tr["engine"], tr.get("preset"), tr.get("params"), seed, sr, assets=_assets(proj, tr, base))
    if snap:
        e.restore(snap)
    return e


def length(proj: dict) -> int:
    r = proj["render"]
    return int(round((r["beats"] * 60.0 / proj["bpm"] + r["tail_s"]) * r["sr"]))


def render_track(proj: dict, name: str, base: Path | None = None, engine=None) -> np.ndarray:
    """One track's stereo stem (before gain and pan), n = length(proj)."""
    tr = proj["tracks"][name]
    n, bpm, blk = length(proj), proj["bpm"], int(proj["render"]["block"])
    events = beat_events([tuple(c) for c in tr.get("clip", [])], bpm, int(proj["render"]["sr"]))
    eng = engine if engine is not None else build(proj, name, base)
    if tr.get("graph"):
        targets = tr["graph"].get("notes") or list(eng.nodes)
        return eng.render({k: events for k in targets}, n, bpm, 0.0, blk)
    return eng.render(events, n, bpm, automation_of(tr), Matrix.from_json(tr.get("modulation")), 0.0, block=blk)


def renderable(proj: dict) -> list:
    bad = {p.split(":")[0] for p in problems(proj) if "skipped" in p}
    return [k for k, tr in proj["tracks"].items() if k not in bad and not tr.get("mute")]


def render(proj: dict, base: Path | None = None) -> tuple:
    """(mix (n, 2), {track: stem (n, 2) after gain and pan}). Muted and unrenderable tracks are left out."""
    n = length(proj)
    mix = np.zeros((n, 2), np.float32)
    stems = {}
    for name in renderable(proj):
        tr = proj["tracks"][name]
        y = render_track(proj, name, base) * 10 ** (float(tr.get("gain_db", 0.0)) / 20)
        pan = float(np.clip(tr.get("pan", 0.0), -1, 1))
        y = y * np.array([min(1.0, 1 - pan), min(1.0, 1 + pan)], np.float32)
        stems[name] = y.astype(np.float32)
        mix += stems[name]
    return mix, stems


def capture(proj: dict, snap_name: str, base: Path | None = None, beats: float | None = None) -> dict:
    """Render every track for `beats` (default: the whole clip) and store each engine's state as a snapshot."""
    p = copy.deepcopy(proj)
    if beats is not None:
        p["render"] = {**p["render"], "beats": float(beats), "tail_s": 0.0}
    out = {}
    for name in renderable(p):
        eng = build(p, name, base)
        render_track(p, name, base, eng)
        out[name] = eng.snapshot()
    proj["snapshots"][snap_name] = out
    return out


def to_instruments(proj: dict) -> dict:
    """{"tracks": {...}} for a song's instruments.toml: the same tables, without the Lab-only keys."""
    out = {}
    for name, tr in proj["tracks"].items():
        t = {k: copy.deepcopy(v) for k, v in tr.items() if k not in LAB_KEYS}
        if t.get("assets"):
            t["assets"] = {k: proj["assets"].get(v, v) for k, v in t["assets"].items()}
        out[name] = t
    return {"tracks": out}


def from_instruments(instruments: dict, name: str = "from-song", bpm: float = 120.0, seed: int = 1) -> dict:
    """A project holding a song's synthesis tracks (no clips yet: the song's MIDI plays them there)."""
    proj = new(name, bpm, seed)
    for k, tr in instruments.get("tracks", {}).items():
        if isinstance(tr, dict) and tr.get("kind") == "synthesis":
            proj["tracks"][k] = {**copy.deepcopy(tr), "clip": []}
    return normalise(proj)


def write_wav(path: Path, y: np.ndarray, sr: int = S.SR) -> Path:
    from scipy.io import wavfile
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pk = float(np.abs(y).max()) if len(y) else 0.0
    y = y / pk * 0.89 if pk > 0.89 else y                      # never clip the file: -1 dBFS ceiling
    wavfile.write(str(path), sr, (np.clip(y, -1, 1) * 32767).astype(np.int16))
    return path
