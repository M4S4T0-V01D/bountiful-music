"""The audio-to-instrument lab and the timbre library.

Give it a sound (a WAV, or an array) and it finds the closest instrument Bountiful can play:

    fp = timbre.fingerprint(y)                     # what the sound is: pitch, envelope, spectrum, noise, width
    run = timbre.match("hit.wav")                  # the nearest engine presets, then a bounded parameter search
    run["best"]["patch"], run["best"]["differences"]
    timbre.add("glass hit", run["best"]["patch"], source="hit.wav")   # into the library
    timbre.search("bright pluck")                  # by words, over the library and every built-in preset

A fingerprint is measured relative to the note's own pitch (harmonic profile, brightness in octaves over f0,
envelope times), so a preset auditioned at C4 compares fairly with a source at any pitch. Every built-in and
user preset of the synthesis engines is auditioned once into <data>/timbres/index.json (about ten seconds;
rebuilt when an engine's version or preset list changes). Matching auditions the closest presets again at the
source's own pitch, then nudges the best ones' numeric parameters one at a time, keeping a nudge only if the
sound moves closer, within a fixed number of renders. Everything is plain DSP: deterministic, CPU only.

The library is <data>/timbres/library/<name>.json, one file per sound: {name, patch, fingerprint, tags,
source, note, time}. Saving under a name that exists keeps the old file as <name>.<n>.json.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import numpy as np

from paths import DATA

SR = 44100
ROOT = DATA / "timbres"
AUDITION = (60, 1.5, 0.8)                           # pitch, seconds held, velocity
TAIL = 0.6
BUDGET = 28                                         # renders a match may spend
NUDGE = 0.15                                        # of a parameter's range
N_HARM = 10

WEIGHTS = {"attack": 1.0, "decay": 0.8, "sustain": 1.0, "brightness": 1.2, "flatness": 1.0, "harmonicity": 0.8,
           "periodicity": 0.6, "harmonics": 1.0, "width": 0.4, "odd_even": 0.4}


# ---------------------------------------------------------------- listening

def _mono(y):
    y = np.asarray(y, np.float64)
    return y.mean(1) if y.ndim == 2 else y


def _db(x):
    return float(20 * np.log10(max(float(x), 1e-9)))


def _f0(x, sr):
    """(f0 Hz, periodicity 0..1) by normalised autocorrelation of a steady stretch; f0 None if unpitched."""
    n = min(len(x), int(0.25 * sr))
    if n < 2048 or np.max(np.abs(x)) < 1e-6:
        return None, 0.0
    seg = x[:n] * np.hanning(n)
    m = 1 << int(np.ceil(np.log2(2 * n)))
    ac = np.fft.irfft(np.abs(np.fft.rfft(seg, m)) ** 2)[:n]
    if ac[0] <= 0:
        return None, 0.0
    ac /= ac[0]
    lo, hi = int(sr / 2000), min(n - 1, int(sr / 30))
    if hi <= lo + 2:
        return None, 0.0
    i = lo + int(np.argmax(ac[lo:hi]))
    best = ac[i]
    for k in (2, 3, 4):                             # prefer the true period over a multiple of it
        j = int(round(i / k))
        if j >= lo:
            w = slice(max(lo, j - 2), j + 3)
            jj = w.start + int(np.argmax(ac[w]))
            if ac[jj] > 0.85 * best:
                i, best = jj, max(ac[jj], 0)
    if 1 <= i < n - 1:                              # parabolic peak, only on a true local maximum
        a, b, c = ac[i - 1], ac[i], ac[i + 1]
        den = a - 2 * b + c
        if b >= a and b >= c and den < 0:
            i = i + float(np.clip(0.5 * (a - c) / den, -0.5, 0.5))
    per = float(np.clip(best, 0, 1))
    return (float(sr / i), per) if per >= 0.3 else (None, per)


def fingerprint(y, sr: int = SR) -> dict:
    """What a single sound is, as numbers that do not depend on its pitch or level."""
    y = np.asarray(y, np.float64)
    x = _mono(y)
    out = {"silent": True}
    if not len(x) or np.max(np.abs(x)) < 1e-5:
        return out
    h = int(0.005 * sr)
    env = np.sqrt(np.mean(x[: len(x) // h * h].reshape(-1, h) ** 2, 1)) + 1e-12
    pk = int(np.argmax(env))
    start = int(np.argmax(env > env[pk] * 0.05))
    top = start + int(np.argmax(env[start:] >= env[pk] * 0.9))      # where the attack ends
    attack = max(h, (top - start) * h) / sr
    after = env[top:]
    below = np.nonzero(after < env[pk] * 0.1)[0]
    decay = (below[0] if len(below) else len(after)) * h / sr
    held = AUDITION[1]
    ks = min(len(env) - 1, start + int(0.7 * held * sr / h))
    sustain = max(-60.0, _db(env[ks] / env[pk]))
    body = x[start * h + int(0.03 * sr): start * h + int(0.03 * sr) + int(0.5 * sr)]
    if len(body) < 2048:
        body = x[start * h:]
    f0, per = _f0(body, sr)
    n = 1 << int(np.ceil(np.log2(max(len(body), 4096))))
    spec = np.abs(np.fft.rfft(body * np.hanning(len(body)), n)) ** 2
    f = np.fft.rfftfreq(n, 1 / sr)
    mag = np.sqrt(spec)
    cen = float((f * mag).sum() / (mag.sum() + 1e-20))
    flat = float(np.exp(np.mean(np.log(spec[1:] + 1e-20))) / (spec[1:].mean() + 1e-20))
    if f0:                                          # an inharmonic sound's autocorrelation finds a common subharmonic;
        band = (f >= 30) & (f <= 8000)              # its lowest strong partial is the pitch heard
        sb, fb = spec[band], f[band]
        pk_i = np.nonzero((sb[1:-1] >= sb[:-2]) & (sb[1:-1] > sb[2:]) & (sb[1:-1] >= sb.max() * 0.03))[0] + 1
        if len(pk_i):
            low = float(fb[pk_i[0]])
            r = low / f0
            if r > 1.5 and (r > 4.5 or abs(r - round(r)) > 0.08):
                f0 = low
    harm, harmonicity = [], 0.0
    if f0:
        for k in range(1, N_HARM + 1):
            if k * f0 >= sr / 2:
                harm.append(-60.0)
                continue
            w = (f >= k * f0 * 0.97) & (f <= k * f0 * 1.03)
            harm.append(10 * np.log10(spec[w].max() + 1e-20) if w.any() else -120.0)
        top = max(harm)
        harm = [round(max(-60.0, v - top), 2) for v in harm]
        near = np.zeros(len(f), bool)               # over the partials above the fundamental (a sine counts as harmonic)
        for k in range(2, int(min(sr / 2, 8000) / f0) + 1):
            near |= (f >= k * f0 * 0.97) & (f <= k * f0 * 1.03)
        above = (f > f0 * 1.5) & (f <= 8000)
        harmonicity = float(spec[near & above].sum() / spec[above].sum()) if spec[above].sum() > 1e-3 * spec.sum() else 1.0
    ref = f0 or 100.0
    wid = 0.0
    if y.ndim == 2 and y.shape[1] == 2:
        m, s = (y[:, 0] + y[:, 1]) / 2, (y[:, 0] - y[:, 1]) / 2
        wid = float(np.sqrt(np.mean(s ** 2) / max(np.mean(m ** 2), 1e-20)))
    odd_even = float(np.clip(np.mean(harm[2:7:2]) - np.mean(harm[1:6:2]), -24, 24)) if len(harm) >= 7 else 0.0
    return {"silent": False, "f0": round(f0, 2) if f0 else None, "periodicity": round(per, 3),
            "attack": round(attack, 4), "decay": round(decay, 3), "sustain": round(sustain, 2),
            "brightness": round(float(np.log2(max(cen, 20) / ref)), 3), "centroid": round(cen, 1),
            "flatness": round(flat, 4), "harmonicity": round(harmonicity, 3), "harmonics": harm,
            "odd_even": round(odd_even, 2), "width": round(min(wid, 2.0), 3)}


def _vec(fp):
    h = (fp.get("harmonics") or [-60.0] * N_HARM) + [-60.0] * N_HARM
    return {"attack": np.log10(fp["attack"] + 0.002) * 1.5, "decay": np.log10(fp["decay"] + 0.01),
            "sustain": fp["sustain"] / 20, "brightness": fp["brightness"] / 1.5, "flatness": np.sqrt(fp["flatness"]) * 3,
            "harmonicity": fp["harmonicity"] * 2, "periodicity": fp["periodicity"] * 2,
            "harmonics": np.array(h[:N_HARM]) / 25, "width": fp["width"] * 2, "odd_even": fp["odd_even"] / 12}


def distance(a: dict, b: dict) -> float:
    """How far two fingerprints are; 0 is the same sound. Silence is infinitely far from anything."""
    if a.get("silent") or b.get("silent"):
        return float("inf")
    va, vb = _vec(a), _vec(b)
    d = 0.0
    for k, w in WEIGHTS.items():
        diff = np.asarray(va[k]) - np.asarray(vb[k])
        d += w * (float(np.mean(diff ** 2)) if np.ndim(diff) else float(diff ** 2))
    return round(float(np.sqrt(d)), 4)


def tags(fp: dict) -> list[str]:
    """Plain words for a fingerprint, for the library and search."""
    if fp.get("silent"):
        return ["silent"]
    t = []
    if fp["attack"] <= 0.02 and fp["sustain"] < -15:
        t.append("pluck" if fp["periodicity"] >= 0.5 else "hit")
    elif fp["attack"] >= 0.15:
        t.append("pad")
    if fp["sustain"] > -8:
        t.append("sustained")
    if fp["decay"] > 1.2 and fp["sustain"] < -8:
        t.append("ringing")
    if fp["brightness"] > 3.0:
        t.append("bright")
    elif fp["brightness"] < 1.2:
        t.append("dark")
    if fp["flatness"] > 0.25:
        t.append("noisy")
    if fp["periodicity"] < 0.4:
        t.append("unpitched")
    elif fp["harmonicity"] < 0.55:
        t.append("metallic")
    if fp.get("odd_even", 0) > 6:
        t.append("hollow")
    if fp["width"] > 0.3:
        t.append("wide")
    if fp.get("f0") and fp["f0"] < 130:
        t.append("low")
    return t


def describe(fp: dict) -> str:
    if fp.get("silent"):
        return "silence"
    p = f"{fp['f0']:.0f} Hz" if fp.get("f0") else "unpitched"
    return (f"{p}, attack {fp['attack'] * 1000:.0f} ms, decay {fp['decay']:.2f} s, sustain {fp['sustain']:.0f} dB, "
            f"{fp['brightness']:.1f} octaves bright, noise {fp['flatness']:.2f}" + (f" ({', '.join(tags(fp))})" if tags(fp) else ""))


def differences(src: dict, got: dict) -> list[str]:
    """What still separates a candidate from the source, largest first, in words."""
    if src.get("silent") or got.get("silent"):
        return ["one of them is silent"]
    out = []
    r = (got["attack"] + 0.002) / (src["attack"] + 0.002)
    if r > 2 or r < 0.5:
        out.append((abs(np.log2(r)), f"attack {'slower' if r > 1 else 'faster'} ({got['attack'] * 1000:.0f} ms against {src['attack'] * 1000:.0f})"))
    r = (got["decay"] + 0.01) / (src["decay"] + 0.01)
    if r > 1.6 or r < 0.6:
        out.append((abs(np.log2(r)), f"rings {'longer' if r > 1 else 'shorter'} ({got['decay']:.2f} s against {src['decay']:.2f})"))
    d = got["brightness"] - src["brightness"]
    if abs(d) > 0.5:
        out.append((abs(d), f"{'brighter' if d > 0 else 'darker'} by {abs(d):.1f} octaves"))
    d = got["flatness"] - src["flatness"]
    if abs(d) > 0.08:
        out.append((abs(d) * 8, "noisier" if d > 0 else "purer"))
    d = got["sustain"] - src["sustain"]
    if abs(d) > 6:
        out.append((abs(d) / 6, f"holds {'more' if d > 0 else 'less'} ({got['sustain']:.0f} dB against {src['sustain']:.0f})"))
    d = got["harmonicity"] - src["harmonicity"]
    if abs(d) > 0.2:
        out.append((abs(d) * 4, "more harmonic" if d > 0 else "more metallic"))
    return [w for _, w in sorted(out, key=lambda t: -t[0])]


def load_audio(path) -> tuple[np.ndarray, int]:
    import soundfile as sf
    y, sr = sf.read(str(path), dtype="float64", always_2d=False)
    return y, sr


# ---------------------------------------------------------------- auditioning engines

def audition(patch: dict, pitch: int = AUDITION[0], held: float = AUDITION[1], vel: float = AUDITION[2], sr: int = SR):
    """One note of a patch ({engine, preset?, params?, seed?, assets?}) as a stereo array."""
    import synthesis as S
    from synthesis.engine_api import note_events
    eng = S.create(patch["engine"], patch.get("preset"), patch.get("params"), seed=patch.get("seed", 1), sr=sr,
                   assets=patch.get("assets"))
    ev = note_events([{"start": 0.0, "end": held, "pitch": int(pitch), "vel": vel}], 0.0, sr)
    return eng.render(ev, int((held + TAIL) * sr), bpm=120)


def _index_key():
    import synthesis as S
    return [[e, S.engine_class(e).VERSION, sorted(S.presets(e))] for e in S.ENGINES]


def index(rebuild: bool = False, log=None) -> list[dict]:
    """Every engine preset auditioned at C4: [{id, patch, fingerprint, tags}]. Cached in <data>/timbres/index.json."""
    import synthesis as S
    f = ROOT / "index.json"
    key = _index_key()
    if not rebuild and f.exists():
        try:
            d = json.loads(f.read_text())
            if d.get("key") == key:
                return d["entries"]
        except ValueError:
            pass
    out = []
    for e in S.ENGINES:
        for p in sorted(S.presets(e)):
            patch = {"engine": e, "preset": p}
            try:
                fp = fingerprint(audition(patch))
            except Exception as ex:                 # a preset that cannot play alone (Oracle without a WAV)
                fp = {"silent": True, "error": str(ex)[:120]}
            if fp.get("silent"):
                continue
            out.append({"id": f"{e}/{p}", "patch": patch, "fingerprint": fp, "tags": tags(fp)})
            if log:
                log(f"  {e}/{p}: {', '.join(tags(fp)) or '-'}")
    ROOT.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"key": key, "entries": out}, separators=(",", ":")))
    return out


def _numeric(eid):
    import synthesis as S
    return [p for p in S.engine_class(eid).PARAMS if p.kind in ("float", "int") and p.hi > p.lo]


def _full_params(patch):
    import synthesis as S
    p = dict(S.presets(patch["engine"]).get(patch.get("preset"), {})) if patch.get("preset") else {}
    p.update(patch.get("params") or {})
    return p


def refine(src: dict, patch: dict, pitch: int, budget: int, start: float | None = None) -> tuple[dict, float, int, list]:
    """Nudge a patch's numeric params one at a time toward the source. Returns (patch, distance, renders, steps)."""
    import synthesis as S
    schema = _numeric(patch["engine"])
    defaults = {p.name: p.default for p in S.engine_class(patch["engine"]).PARAMS}
    cur = {k: v for k, v in _full_params(patch).items()}
    best = start if start is not None else distance(src, fingerprint(audition(patch, pitch)))
    used, steps = 0, []
    improved = True
    while improved and used < budget:
        improved = False
        for p in schema:
            if used >= budget:
                break
            v0 = cur.get(p.name, defaults[p.name])
            for sign in (1, -1):
                if used >= budget:
                    break
                v = p.clamp(v0 + sign * NUDGE * (p.hi - p.lo))
                if v == v0:
                    continue
                trial = dict(patch, params={**(patch.get("params") or {}), p.name: v})
                used += 1
                try:
                    d = distance(src, fingerprint(audition(trial, pitch)))
                except Exception:
                    continue
                if d < best - 1e-4:
                    best, patch, improved = d, trial, True
                    cur[p.name] = v
                    steps.append({"param": p.name, "from": v0, "to": v, "distance": d})
                    break
    return patch, best, used, steps


def match(source, sr: int = SR, budget: int = BUDGET, shortlist: int = 4, refine_top: int = 2, log=None) -> dict:
    """The closest playable instruments to a sound (a path or an array).
    Returns {"source": fingerprint, "candidates": [...], "best": candidate}. A candidate is
    {"patch", "id", "distance", "fingerprint", "tags", "differences", "steps"}."""
    path = None
    if isinstance(source, (str, Path)):
        path = Path(source)
        y, sr = load_audio(path)
    else:
        y = np.asarray(source, np.float64)
    if sr != SR:
        from scipy.signal import resample_poly
        y = resample_poly(y, SR, sr, axis=0)
    src = fingerprint(y)
    if src.get("silent"):
        raise ValueError("the source is silent")
    pitch = int(np.clip(round(69 + 12 * np.log2(src["f0"] / 440)), 24, 108)) if src.get("f0") else 60
    idx = index(log=log)
    ranked = sorted(idx, key=lambda e: (distance(src, e["fingerprint"]), e["id"]))
    picks, engines = [], set()
    for e in ranked:                                # the nearest few, at most two per engine
        if sum(1 for p in picks if p["patch"]["engine"] == e["patch"]["engine"]) < 2:
            picks.append(e)
            engines.add(e["patch"]["engine"])
        if len(picks) >= shortlist:
            break
    used, cands = 0, []
    for e in picks:                                 # compared at the source's pitch, or at C4 if that is closer
        c = {"patch": dict(e["patch"]), "id": e["id"], "pitch": AUDITION[0], "fingerprint": e["fingerprint"],
             "distance": distance(src, e["fingerprint"]), "steps": []}
        if pitch != AUDITION[0]:
            fp = fingerprint(audition(e["patch"], pitch))
            used += 1
            if distance(src, fp) < c["distance"]:
                c.update(pitch=pitch, fingerprint=fp, distance=distance(src, fp))
        cands.append(c)
    cands.sort(key=lambda c: (c["distance"], c["id"]))
    left = max(0, budget - used)
    for c in cands[:refine_top]:
        share = left // max(1, refine_top)
        patch, d, n, steps = refine(src, c["patch"], c["pitch"], share, start=c["distance"])
        used += n
        if steps:
            c.update(patch=patch, distance=d, fingerprint=fingerprint(audition(patch, c["pitch"])), steps=steps)
            used += 1
    for c in cands:
        c["tags"] = tags(c["fingerprint"])
        c["differences"] = differences(src, c["fingerprint"])
    cands.sort(key=lambda c: (c["distance"], c["id"]))
    out = {"source": src, "pitch": pitch, "candidates": cands, "best": cands[0], "renders": used}
    if path is not None:                            # the sound itself, resynthesised by the Oracle
        out["resynthesis"] = {"engine": "oracle", "preset": "transposed-instrument", "assets": {"source": str(path)}}
    return out


def to_track(patch: dict, gain_db: float = -10.0) -> dict:
    """A patch as an instruments.toml / Lab track table."""
    import synthesis as S
    t = {"kind": "synthesis", "engine": patch["engine"], "version": S.engine_class(patch["engine"]).VERSION,
         "params": dict(patch.get("params") or {}), "gain_db": gain_db}
    if patch.get("preset"):
        t["preset"] = patch["preset"]
    if patch.get("assets"):
        t["assets"] = dict(patch["assets"])
    return t


# ---------------------------------------------------------------- the library

def _lib(root=None):
    return Path(root or ROOT) / "library"


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "timbre"


def add(name: str, patch: dict, source: str | None = None, note: str = "", fingerprint_: dict | None = None,
        root=None) -> Path:
    """Save a sound to the library. Its fingerprint is measured from the patch if not given."""
    d = _lib(root)
    d.mkdir(parents=True, exist_ok=True)
    fp = fingerprint_ or fingerprint(audition(patch))
    f = d / f"{_slug(name)}.json"
    if f.exists():                                  # never lose a saved sound
        k = 1
        while (d / f"{_slug(name)}.{k}.json").exists():
            k += 1
        f.rename(d / f"{_slug(name)}.{k}.json")
    rec = {"name": name, "patch": patch, "fingerprint": fp, "tags": tags(fp), "source": Path(source).name if source else None,
           "note": note, "time": round(time.time(), 1)}
    f.write_text(json.dumps(rec, indent=1))
    return f


def library(root=None) -> list[dict]:
    d = _lib(root)
    out = []
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        if re.search(r"\.\d+\.json$", f.name):
            continue
        try:
            out.append(json.loads(f.read_text()))
        except ValueError:
            continue
    return out


def search(query: str = "", like: dict | None = None, k: int = 10, root=None, presets: bool = True) -> list[dict]:
    """Sounds by words (tags, names, engines) and/or nearness to a fingerprint, the library first on ties.
    Returns [{"name", "patch", "tags", "score", "where"}]."""
    words = [w for w in re.split(r"[\s,]+", query.lower()) if w]
    pool = [dict(r, where="library") for r in library(root)]
    if presets:
        pool += [{"name": e["id"], "patch": e["patch"], "fingerprint": e["fingerprint"], "tags": e["tags"], "where": "preset"}
                 for e in index()]
    out = []
    for r in pool:
        hay = set(r["tags"]) | set(re.split(r"[^a-z0-9]+", r["name"].lower())) | {r["patch"]["engine"]}
        hits = sum(1 for w in words if w in hay or any(h.startswith(w) for h in hay))
        if words and not hits:
            continue
        near = distance(like, r["fingerprint"]) if like else 0.0
        out.append({"name": r["name"], "patch": r["patch"], "tags": r["tags"], "where": r["where"],
                    "score": round(hits - 0.25 * near, 3)})
    out.sort(key=lambda r: (-r["score"], r["where"] != "library", r["name"]))
    return out[:k]


def main():
    import argparse
    ap = argparse.ArgumentParser(description="the audio-to-instrument lab and timbre library")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("match", help="find the closest instrument to a WAV")
    m.add_argument("wav", type=Path)
    m.add_argument("--save", metavar="NAME", help="add the best match to the library")
    m.add_argument("--budget", type=int, default=BUDGET)
    sub.add_parser("index", help="audition every preset again")
    s = sub.add_parser("search", help="find sounds by words")
    s.add_argument("words", nargs="*")
    sub.add_parser("list", help="the library")
    a = ap.parse_args()
    if a.cmd == "index":
        print(f"{len(index(rebuild=True, log=print))} presets")
    elif a.cmd == "match":
        r = match(a.wav, budget=a.budget)
        print("source:", describe(r["source"]))
        for c in r["candidates"]:
            print(f"  {c['distance']:.3f}  {c['id']}" + (f" + {len(c['steps'])} nudges" if c["steps"] else "")
                  + (f"  ({'; '.join(c['differences'][:3])})" if c["differences"] else "  (close)"))
        if a.save:
            print("saved", add(a.save, r["best"]["patch"], source=str(a.wav)))
    elif a.cmd == "search":
        for r in search(" ".join(a.words)):
            print(f"  {r['score']:5.2f}  {r['where']:7}  {r['name']}  ({', '.join(r['tags'])})")
    else:
        for r in library():
            print(f"  {r['name']}: {r['patch']['engine']}/{r['patch'].get('preset') or '-'}  ({', '.join(r['tags'])})")


if __name__ == "__main__":
    main()
