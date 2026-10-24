"""Your taste, learned: the Electronium's critic, tuned by what you like.

The machine thinks of 200 ideas and its critic picks the best; this lets the critic learn from you. Audition an
idea, rate it (+1 like / -1 not for me, or 1-5), and it's stored in <data>/taste.json. A small ridge regression over
the idea's features (its shape: notes, range, steps and leaps, syncopation, contour, ending, call and answer ...)
learns what you rate up; the machine adds that to the critic's score (patch knob `taste`, 0 = off, 1 = normal),
weighted by how many ratings it has (nothing until 5, full strength from 30).

    $PY bountiful/taste.py            what it has learned
"""
from __future__ import annotations

import json
import time
import wave
from pathlib import Path

import numpy as np

from paths import DATA

FILE = DATA / "taste.json"
FEATURES = ("notes", "range", "steps", "gap fill", "ending", "call and answer", "one high point", "syncopation", "starts",
            "n", "span", "step share", "mean move", "offbeat share", "rise", "longest", "rest share", "echo", "peak at",
            "repeats", "low end")
_cache: dict = {}


def features(cells: list) -> np.ndarray:
    import electronium as EL
    _, parts = EL.critic(cells)
    n = len(cells)
    degs = [c[2] for c in cells] or [0]
    moves = [b - a for a, b in zip(degs, degs[1:])] or [0]
    a = {c[0] for c in cells if c[0] < 16}
    b = {c[0] - 16 for c in cells if c[0] >= 16}
    sound = sum(min(c[1], 8) for c in cells) / 8.0
    x = [parts.get(k, 0.0) for k in FEATURES[:9]] + [
        n / 12, (max(degs) - min(degs)) / 8, sum(abs(m) <= 1 for m in moves) / len(moves), float(np.mean(np.abs(moves))) / 3,
        sum(1 for c in cells if c[0] % 2) / max(1, n), (degs[-1] - degs[0]) / 5, max((c[1] for c in cells), default=0) / 2,
        1 - min(1.0, sound), len(a & b) / max(1, len(a | b)), (degs.index(max(degs)) / max(1, n - 1)),
        sum(m == 0 for m in moves) / len(moves), (min(degs) < -3) * 1.0]
    return np.array(x, float)


def load() -> list[dict]:
    try:
        return json.loads(FILE.read_text()).get("ratings", [])
    except (FileNotFoundError, ValueError):
        return []


def rate(idea: dict, rating: float, bounty=None, note: str = "") -> int:
    """Store a rating (+1 / -1, or 1-5 which maps to -1 ... +1). Returns how many there are now."""
    r = float(rating)
    if r > 1:
        r = (r - 3) / 2
    rows = [x for x in load() if not (x.get("bounty") == bounty and x.get("n") == idea.get("n") and x["cells"] == [list(c) for c in idea["cells"]])]
    rows.append({"cells": [list(c) for c in idea["cells"]], "rating": max(-1.0, min(1.0, r)), "bounty": bounty,
                 "n": idea.get("n"), "time": int(time.time()), **({"note": note} if note else {})})
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps({"ratings": rows}, indent=0))
    _cache.clear()
    return len(rows)


def model() -> dict | None:
    """{"w", "mu", "sd", "n", "strength"} fitted on the ratings, or None with fewer than 5."""
    try:
        mt = FILE.stat().st_mtime
    except FileNotFoundError:
        return None
    if _cache.get("mt") == mt:
        return _cache["m"]
    rows = load()
    m = None
    if len(rows) >= 5:
        X = np.array([features([tuple(c) for c in r["cells"]]) for r in rows])
        y = np.array([r["rating"] for r in rows])
        mu, sd = X.mean(0), X.std(0) + 1e-6
        Z = (X - mu) / sd
        lam = 3.0                                       # ridge: few ratings, stay modest
        w = np.linalg.solve(Z.T @ Z + lam * np.eye(Z.shape[1]), Z.T @ (y - y.mean()))
        m = {"w": w, "mu": mu, "sd": sd, "b": float(y.mean()), "n": len(rows), "strength": min(1.0, (len(rows) - 4) / 26)}
    _cache.update(mt=mt, m=m)
    return m


def bonus(cells: list, weight: float = 1.0) -> float:
    """What your taste adds to the critic's score (about -2 ... +2 at full strength)."""
    m = model()
    if m is None or not weight:
        return 0.0
    z = (features(cells) - m["mu"]) / m["sd"]
    return float(np.clip(z @ m["w"], -1.5, 1.5)) * 1.5 * m["strength"] * float(weight)


def report() -> str:
    m = model()
    rows = load()
    if m is None:
        return f"{len(rows)} ratings; the critic starts learning at 5."
    order = np.argsort(-np.abs(m["w"]))
    out = [f"{m['n']} ratings, strength {m['strength']:.0%}. What you like (+) and don't (-):"]
    out += [f"  {'+' if m['w'][i] > 0 else '-'} {FEATURES[i]:16s} {m['w'][i]:+.2f}" for i in order[:8]]
    return "\n".join(out)


# ------------------------------------------------------------------ whole songs

SONGS = DATA / "taste_songs.json"
SONG_KEYS = ("energy_range", "energy_arc", "contrast", "lead_range", "lead_stepwise", "lead_leaps", "lead_offbeat",
             "harmonic_rhythm", "in_key", "drum_density", "note_density", "bpm")


def load_songs() -> list[dict]:
    try:
        return json.loads(SONGS.read_text()).get("ratings", [])
    except (FileNotFoundError, ValueError):
        return []


def rate_song(feats: dict, rating: float, ref: str, note: str = "") -> int:
    """Rate a whole song (+1 / -1, or 1-5) by its features (features.features); `ref` names it (a lineage id or
    a Bounty), and rating it again replaces the old rating. Returns how many song ratings there are."""
    r = float(rating)
    if r > 1:
        r = (r - 3) / 2
    rows = [x for x in load_songs() if x.get("ref") != ref]
    rows.append({"ref": ref, "rating": max(-1.0, min(1.0, r)), "time": int(time.time()),
                 "features": {k: float(feats.get(k, 0.0)) for k in SONG_KEYS}, **({"note": note} if note else {})})
    SONGS.parent.mkdir(parents=True, exist_ok=True)
    SONGS.write_text(json.dumps({"ratings": rows}, indent=0))
    return len(rows)


def song_taste(feats: dict, k: int = 5) -> tuple[float | None, list[tuple[str, float, float]]]:
    """-> (-1 ... +1 or None with fewer than 3 ratings, [(ref, rating, weight)]): the rated songs nearest this
    one in feature space, weighted by closeness."""
    rows = load_songs()
    if len(rows) < 3:
        return None, []
    X = np.array([[r["features"].get(k_, 0.0) for k_ in SONG_KEYS] for r in rows])
    mu, sd = X.mean(0), X.std(0) + 1e-6
    x = (np.array([float(feats.get(k_, 0.0)) for k_ in SONG_KEYS]) - mu) / sd
    d = np.linalg.norm((X - mu) / sd - x, axis=1)
    near = np.argsort(d, kind="stable")[:k]
    w = 1 / (1 + d[near])
    y = np.array([rows[i]["rating"] for i in near])
    return float(w @ y / w.sum()), [(rows[i]["ref"], rows[i]["rating"], round(float(wi), 3)) for i, wi in zip(near, w)]


# ------------------------------------------------------------------ audition

def audition(idea: dict, tonic: int = 0, mode: str = "minor", bpm: float = 112, tone: dict | None = None,
             base: int = 67, sr: int = 44100) -> np.ndarray:
    """The idea played twice on the lead's tone generator, with a soft root drone: mono float32."""
    import electronium as EL
    import electronium_voice as V
    sc = EL.SCALES.get(mode, EL.SCALES["minor"])
    scale = [m for m in range(24, 110) if (m - tonic) % 12 in sc]
    home = min((m for m in scale if (m - tonic) % 12 == 0), key=lambda m: abs(m - base))
    i0 = scale.index(home)
    beat = 60 / bpm
    n = int((16 * beat + 1.0) * sr)
    out = np.zeros(n, np.float32)
    rng = np.random.default_rng(1)
    t = tone or EL.TONES["scott-lead"]
    prev = None
    for rep in range(2):
        for (s, d, deg, v) in idea["cells"]:
            q = scale[int(np.clip(i0 + deg, 0, len(scale) - 1))]
            y = V.note(q, float(v), float(d) * beat, t, rng, from_midi=prev)
            prev = q
            i = int(((rep * 32 + s) / 4) * beat * sr)
            m = min(len(y), n - i)
            if m > 0:
                out[i:i + m] += y[:m] * 0.5
    tt = np.arange(n) / sr
    f0 = 440 * 2 ** ((home - 24 - 69) / 12)
    out += (0.05 * np.sin(2 * np.pi * f0 * tt) * np.minimum(1, tt / 0.5) * np.minimum(1, (n / sr - tt) / 0.5)).astype(np.float32)
    return out / max(1e-6, float(np.abs(out).max())) * 0.8


def write_wav(path: Path, x: np.ndarray, sr: int = 44100) -> Path:
    y = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(y.tobytes())
    return Path(path)


if __name__ == "__main__":
    print(report())
