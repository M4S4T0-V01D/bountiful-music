"""The virtual record producer: listen to a render, fix the mix in small bounded steps, render again, compare.

producer.py chooses a genre's sound before anything is rendered. This one works afterwards, by ear: it renders
short passages of a track (stems and the pre-master mix), measures them, and changes the mix only where a
measurement is out of its range:

    kick/bass masking        bass energy under 150 Hz while the kick hits, against the kick's      -> bass sidechain deeper
    lead masking             lead energy (250 Hz-5 kHz) buried under the accompaniment             -> EQ dip in the masker
    accompaniment overlap    two accompaniment parts (pad and Rhodes, say) in the same band        -> EQ dip in the quieter
    low frequencies          share of the mix's energy under 120 Hz                                -> bass level, high-pass mud
    low end mono             left/right agreement under 120 Hz                                     -> mono bass, high-pass others
    stereo image             side against mid above 200 Hz                                         -> accompaniment width
    transients               drum hits' peak over the bed just before them                           -> kick and snare up
    dynamics                 beat-to-beat loudness movement (reported; the composition owns it)
    section contrast         loudness between the passages (a verse against the last chorus)       -> accompaniment lift

Every change is one step (1 dB, 0.1 of sidechain, a 2 dB dip, 0.2 of width, 40 Hz of high-pass), every
setting is bounded against the mix the producer started from (LIMITS), at most MAX_CHANGES are tried a round,
and a round is kept only if the re-render measures better: the changed measurements rise and nothing else
falls by more than TOLERANCE. Every version of instruments.toml is kept in <track>/versions/ and the whole
session is written to <track>/studio.json, so any step can be explained and undone.

    run = studio.produce(track_dir)                 # render, measure, fix, re-render, compare (2 rounds)
    studio.revert(track_dir, 0)                     # back to how it was
    m = studio.analyse(passages)                    # measurements alone, from arrays (tests use synthetic sound)
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import time
import tomllib
from pathlib import Path

import numpy as np

SR = 44100
LIMITS = {"gain_db": 3.0, "duck": 0.5, "hp": 250.0, "eq_cut": -6.0, "width": (0.6, 1.6), "lift_db": 3.0}
STEP = {"gain_db": 1.0, "duck": 0.1, "hp": 40.0, "eq_cut": -2.0, "width": 0.2, "lift_db": 1.0}
MAX_CHANGES = 3
TOLERANCE = 0.05
MAX_PASSAGES, MAX_BARS = 3, 8

DRUM_STEMS = ("kick", "snare", "clap", "hats", "cymbals", "crash", "toms", "perc")
BASSY = ("bass", "bass2")
LEADS = ("lead", "lead_hi", "melody", "vox", "sidekick")
# (lo, hi, soft, what): 1 inside [lo, hi], falling to 0 `soft` outside it
TARGETS = {
    "kick/bass masking": (0.0, 0.5, 0.7, "bass LF under the kick, against the kick's"),
    "lead masking": (0.0, 0.3, 0.4, "share of the lead buried under the accompaniment"),
    "accompaniment overlap": (0.0, 0.5, 0.35, "two accompaniment parts in the same band"),
    "low frequencies": (0.2, 0.6, 0.2, "share of energy under 120 Hz"),
    "low end mono": (0.9, 1.0, 0.4, "left/right correlation under 120 Hz"),
    "stereo image": (0.08, 0.5, 0.3, "side/mid above 200 Hz"),
    "transients": (8.0, 24.0, 5.0, "drum hits over the bed just before them, dB"),
    "dynamics": (0.8, 5.0, 1.5, "beat-to-beat loudness movement, dB"),
    "section contrast": (1.0, 6.0, 2.0, "last chorus over the verse (or loudest over quietest), dB"),
}
SOUND = ("kick/bass masking", "lead masking", "accompaniment overlap")
REPORT_ONLY = ("dynamics",)


def band(x, lo, hi, soft) -> float:
    if lo <= x <= hi:
        return 1.0
    d = lo - x if x < lo else x - hi
    return float(max(0.0, 1 - d / soft)) if soft > 0 else 0.0


# ---------------------------------------------------------------- measuring

def _mono(x):
    return x.mean(1) if x.ndim == 2 else x


def _stereo(x):
    return np.stack([x, x], 1) if x.ndim == 1 else x


def _db(p):
    return 10 * np.log10(np.maximum(p, 1e-12))


def _bands():
    edges = 40 * 2 ** (np.arange(0, 28) / 3)            # third octaves, 40 Hz to about 20 kHz
    return edges[:-1], edges[1:], np.sqrt(edges[:-1] * edges[1:])


def _spec(x, n=4096):
    """Band power per frame: (frames, bands)."""
    m = _mono(x).astype(np.float64)
    if len(m) < n:
        m = np.pad(m, (0, n - len(m)))
    hop = n // 2
    k = 1 + (len(m) - n) // hop
    fr = np.lib.stride_tricks.as_strided(m, (k, n), (m.strides[0] * hop, m.strides[0])) * np.hanning(n)
    p = np.abs(np.fft.rfft(fr, axis=1)) ** 2
    f = np.fft.rfftfreq(n, 1 / SR)
    lo, hi, _ = _bands()
    return np.stack([p[:, (f >= a) & (f < b)].sum(1) for a, b in zip(lo, hi)], 1)


def _split(x, cut):
    """Low and high parts of a signal (FFT brick wall; measurement only)."""
    from scipy import fft as sfft
    n = sfft.next_fast_len(len(x), real=True)
    X = sfft.rfft(x, n, axis=0, workers=-1)
    f = np.fft.rfftfreq(n, 1 / SR)
    lo = X * (f < cut)[:, None] if X.ndim == 2 else X * (f < cut)
    return sfft.irfft(lo, n, axis=0, workers=-1)[:len(x)], sfft.irfft(X - lo, n, axis=0, workers=-1)[:len(x)]


def onsets(x, rel=0.3, gap=0.09) -> list[int]:
    """Sample positions of hits in a drum stem."""
    m = np.abs(_mono(x))
    h = int(0.005 * SR)
    env = m[: len(m) // h * h].reshape(-1, h).max(1)
    if not len(env) or env.max() <= 0:
        return []
    thr, out, last = rel * env.max(), [], -1e9
    env = np.concatenate([[0.0], env])              # silence before the passage, so a hit on its first sample counts
    for i in range(1, len(env) - 1):
        if env[i] >= thr and env[i] >= env[i - 1] and env[i] > env[i + 1] and env[i] > 2 * env[max(0, i - 6):i].min():
            if (i - last) * h >= gap * SR:
                out.append((i - 1) * h)
                last = i
    return out


def _corr(a, b):
    if np.std(a) < 1e-9 or np.std(b) < 1e-9:
        return 1.0
    return float(np.corrcoef(a, b)[0, 1])


def _role(name):
    if name in DRUM_STEMS or name == "drums":
        return "drums"
    if name in BASSY:
        return "bass"
    if name in LEADS:
        return "lead"
    return "accomp"


def measure(mix, stems: dict, bpm: float) -> tuple[dict, dict]:
    """One passage: {metric: value} and {metric: detail} (what a remedy needs to know)."""
    v, d = {}, {}
    kick = stems.get("kick")
    bass = [stems[k] for k in BASSY if k in stems]
    if kick is not None and bass:
        hits = onsets(kick)
        w = int(0.08 * SR)
        kl, bl = 0.0, 0.0
        klo, _ = _split(_mono(kick), 150)
        blo, _ = _split(_mono(sum(bass)), 150)
        for h in hits:
            kl += float(np.sum(klo[h:h + w] ** 2))
            bl += float(np.sum(blo[h:h + w] ** 2))
        if kl > 0:
            v["kick/bass masking"] = bl / kl
            d["kick/bass masking"] = {"bass": max((k for k in BASSY if k in stems), key=lambda k: np.sum(stems[k] ** 2)),
                                      "hits": len(hits)}
    lo, hi, mid = _bands()
    S = {k: _spec(x) for k, x in stems.items()}
    acc = [k for k in stems if _role(k) == "accomp"]
    lead = next((k for k in ("lead", "melody", "vox") if k in stems), None)
    if lead and acc:
        L = S[lead]
        A = sum(S[k] for k in acc)
        sel = (mid >= 250) & (mid <= 5000)
        act = L.sum(1) > L.sum(1).max() * 1e-3
        Lm, Am = L[act][:, sel], A[act][:, sel]
        if Lm.sum() > 0:
            masked = Am >= Lm
            v["lead masking"] = float(Lm[masked].sum() / Lm.sum())
            per_band = (Lm * masked).sum(0)
            b = int(np.argmax(per_band))
            who = max(acc, key=lambda k: float((S[k][act][:, sel][:, b] * masked[:, b]).sum()))
            d["lead masking"] = {"masker": who, "freq": float(mid[sel][b])}
    sel = (mid >= 150) & (mid <= 4000)
    best = None
    for i, a in enumerate(acc):
        for b in acc[i + 1:]:
            Sa, Sb = S[a][:, sel], S[b][:, sel]
            ea, eb = Sa.sum(1), Sb.sum(1)
            co = (ea > ea.max() * 1e-3) & (eb > eb.max() * 1e-3) if ea.max() > 0 and eb.max() > 0 else np.zeros(len(ea), bool)
            if co.sum() < 2:
                continue
            ma, mb = Sa[co].mean(0), Sb[co].mean(0)
            ov = float(np.minimum(ma, mb).sum() / np.maximum(ma, mb).sum()) * float(co.mean())
            if best is None or ov > best[0]:
                quiet = a if ma.sum() < mb.sum() else b
                best = (ov, a, b, quiet, float(mid[sel][int(np.argmax(np.minimum(ma, mb)))]))
    if best:
        v["accompaniment overlap"] = best[0]
        d["accompaniment overlap"] = {"pair": [best[1], best[2]], "quieter": best[3], "freq": best[4]}
    mx = _stereo(mix).astype(np.float64)
    low, high = _split(mx, 120)
    tot = float(np.sum(mx ** 2))
    if tot > 0:
        v["low frequencies"] = float(np.sum(low ** 2) / tot)
        v["low end mono"] = _corr(low[:, 0], low[:, 1])
        _, h2 = _split(mx, 200)
        mid_, side = (h2[:, 0] + h2[:, 1]) / 2, (h2[:, 0] - h2[:, 1]) / 2
        v["stereo image"] = float(np.sum(side ** 2) / max(np.sum(mid_ ** 2), 1e-12))
        lf = {}
        for k, x in stems.items():
            if k == "kick":
                continue
            sl, _ = _split(_stereo(x).astype(np.float64), 120)
            e = float(np.sum(x.astype(np.float64) ** 2))
            if e > 0:
                lf[k] = {"share": float(np.sum(sl ** 2) / e), "corr": _corr(sl[:, 0], sl[:, 1]), "energy": float(np.sum(sl ** 2))}
        d["low frequencies"] = lf
        d["low end mono"] = lf
        wid = {}
        for k, x in stems.items():
            if _role(k) == "accomp":
                xs = _stereo(x).astype(np.float64)
                wid[k] = float(np.sum((xs[:, 0] - xs[:, 1]) ** 2) / max(np.sum((xs[:, 0] + xs[:, 1]) ** 2), 1e-12))
        d["stereo image"] = wid
    hits = sorted(set(onsets(stems["kick"]) if "kick" in stems else []) | set(onsets(stems["snare"]) if "snare" in stems else []))
    m = _mono(mix).astype(np.float64)
    pk = []
    for h in hits:
        a, b = m[h:h + int(0.015 * SR)], m[max(0, h - int(0.06 * SR)):max(0, h - int(0.01 * SR))]
        if len(a) and len(b) and np.mean(b ** 2) > 0:
            pk.append(_db(np.max(a ** 2)) - _db(np.mean(b ** 2)))
    if pk:
        v["transients"] = float(np.mean(pk))
    beat = int(60 / bpm * SR)
    if len(m) >= 4 * beat:
        r = [_db(np.mean(m[i:i + beat] ** 2)) for i in range(0, len(m) - beat + 1, beat)]
        r = [x for x in r if x > -80]
        if len(r) >= 4:
            v["dynamics"] = float(np.std(r))
    v["_rms_db"] = float(_db(np.mean(m ** 2))) if len(m) else -120.0
    return v, d


def analyse(passages: list[dict], bpm: float = 120.0) -> dict:
    """passages: [{"bars": [a, b], "mix": array, "stems": {name: array}}] at one scale.
    Returns {"values", "scores", "detail", "passages", "score"}: values averaged over passages, the detail of the worst."""
    def cut(p):                                     # the passage itself, without the render's tail
        n = int((p["bars"][1] - p["bars"][0] + 1) * 4 * 60 / bpm * SR)
        return p["mix"][:n], {k: x[:n] for k, x in p["stems"].items()}

    per = [measure(*cut(p), bpm) for p in passages]
    vals, det = {}, {}
    for k in TARGETS:
        xs = [(v[k], d.get(k)) for v, d in per if k in v]
        if not xs:
            continue
        vals[k] = float(np.mean([x for x, _ in xs]))
        worst = min(xs, key=lambda t: band(t[0], *TARGETS[k][:3]))
        if worst[1] is not None:
            det[k] = worst[1]
    if len(per) >= 2:
        r = [v["_rms_db"] for v, _ in per]
        big = [x for x, p in zip(r, passages) if p.get("kind") in ("chorus", "drop")]
        small = [x for x, p in zip(r, passages) if p.get("kind") and p.get("kind") not in ("chorus", "drop")]
        if big and small:                           # signed: a chorus quieter than its verse counts against
            vals["section contrast"] = float(big[-1] - np.mean(small))
        else:
            vals["section contrast"] = float(max(r) - min(r))
        det["section contrast"] = {"rms_db": [round(x, 2) for x in r], "bars": [p["bars"] for p in passages]}
    scores = {k: round(band(x, *TARGETS[k][:3]), 3) for k, x in vals.items()}
    judged = [s for k, s in scores.items() if k not in REPORT_ONLY]
    return {"values": {k: round(x, 4) for k, x in vals.items()}, "scores": scores, "detail": det,
            "passages": [p["bars"] for p in passages], "score": round(float(np.mean(judged)), 4) if judged else None}


def for_evaluators(a: dict) -> dict:
    """The measurements as evaluators.evaluate(song, audio=...) takes them."""
    s = a["scores"]
    return {"sound": {k: s[k] for k in SOUND if k in s},
            "production": {k: s[k] for k in s if k not in SOUND and k not in REPORT_ONLY}}


# ---------------------------------------------------------------- deciding

def _get(cfg, path, default=None):
    for p in path:
        if not isinstance(cfg, dict) or p not in cfg:
            return default
        cfg = cfg[p]
    return cfg


def _set(cfg, path, value):
    for p in path[:-1]:
        cfg = cfg.setdefault(p, {})
    if value is None:
        cfg.pop(path[-1], None)
    else:
        cfg[path[-1]] = value


def _track_path(cfg, name):
    """Where a stem's settings live: its own track, or the drum kit's stem table."""
    if name in cfg.get("tracks", {}):
        return ["tracks", name]
    for k, t in cfg.get("tracks", {}).items():
        if t.get("channel") == 9 or "stems" in t:
            return ["tracks", k, "stems", name]
    return None


def _change(cfg, path, to, metric, why):
    return {"path": path, "from": copy.deepcopy(_get(cfg, path)), "to": to, "metric": metric, "why": why}


def _gain(cfg, orig, name, step, metric, why):
    tp = _track_path(cfg, name)
    if tp is None:
        return None
    g0 = _get(orig, tp + ["gain_db"], 0.0) or 0.0
    g = _get(cfg, tp + ["gain_db"], 0.0) or 0.0
    to = round(max(g0 - LIMITS["gain_db"], min(g0 + LIMITS["gain_db"], g + step)), 2)
    return _change(cfg, tp + ["gain_db"], to, metric, why) if abs(to - g) > 1e-6 else None


def _dip(cfg, name, freq, metric, why):
    tp = _track_path(cfg, name)
    if tp is None:
        return None
    eq = copy.deepcopy(_get(cfg, tp + ["eq"], []) or [])
    for i, b in enumerate(eq):
        if b[0] == "peak" and abs(np.log2(b[1] / freq)) < 1 / 3 and len(b) > 2 and b[2] <= 0:
            if b[2] <= LIMITS["eq_cut"]:
                return None
            eq[i] = ["peak", b[1], round(max(LIMITS["eq_cut"], b[2] + STEP["eq_cut"]), 2), b[3] if len(b) > 3 else 1.2]
            break
    else:
        eq.append(["peak", round(float(freq), 1), STEP["eq_cut"], 1.2])
    return _change(cfg, tp + ["eq"], eq, metric, why)


def prescribe(a: dict, cfg: dict, orig: dict, tried=(), sections=None) -> list[dict]:
    """Bounded changes (at most MAX_CHANGES) for the worst measurement that can still be helped. `tried`: paths refused."""
    out = []
    bad = sorted((s, k) for k, s in a["scores"].items() if s < 0.95 and k not in REPORT_ONLY)
    vals, det = a["values"], a["detail"]
    tracks = cfg.get("tracks", {})

    def add(c):
        if c and len(out) < MAX_CHANGES and tuple(map(str, c["path"])) not in tried and all(c["path"] != o["path"] for o in out):
            out.append(c)
            return True
        return False

    for s, k in bad:
        if out:                                     # one idea a round, so the comparison says what it did
            break
        lo, hi = TARGETS[k][:2]
        dt = det.get(k) or {}
        if k == "kick/bass masking":
            b = dt.get("bass")
            if b in tracks:
                cur = _get(cfg, ["tracks", b, "duck"]) or {}
                dep = round(min(LIMITS["duck"], cur.get("depth", 0.0) + STEP["duck"]), 2)
                if dep > cur.get("depth", 0.0) + 1e-6 and add(_change(cfg, ["tracks", b, "duck"], {"depth": dep, "release": cur.get("release", 0.12)},
                                                                      k, f"bass sits on the kick ({vals[k]:.2f} of its low end); sidechain deeper")):
                    continue
            add(_gain(cfg, orig, "kick", STEP["gain_db"], k, "kick up a step so it reads over the bass"))
        elif k == "lead masking":
            w = dt.get("masker")
            if w and not add(_dip(cfg, w, dt["freq"], k, f"{w} covers the lead around {dt['freq']:.0f} Hz; dip it there")):
                add(_gain(cfg, orig, w, -STEP["gain_db"], k, f"{w} covers the lead; down a step"))
        elif k == "accompaniment overlap":
            q = dt.get("quieter")
            if q and not add(_dip(cfg, q, dt["freq"], k, f"{' and '.join(dt['pair'])} share {dt['freq']:.0f} Hz; dip the quieter, {q}")):
                add(_gain(cfg, orig, q, -STEP["gain_db"], k, f"{q} crowds its partner; down a step"))
        elif k == "low frequencies":
            lf = dt or {}
            if vals[k] > hi:
                mud = sorted((x["energy"], n) for n, x in lf.items() if _role(n) in ("accomp", "lead") and x["share"] > 0.15)
                if mud:
                    n = mud[-1][1]
                    tp = _track_path(cfg, n)
                    cur = (_get(cfg, tp + ["hp"], 0) or 0) if tp else 0
                    to = min(LIMITS["hp"], max(cur, 60) + STEP["hp"])
                    if tp and to > cur and add(_change(cfg, tp + ["hp"], to, k, f"{n} carries low end the bass owns; high-pass at {to:.0f} Hz")):
                        continue
                b = next((x for x in BASSY if x in tracks), None)
                if b:
                    add(_gain(cfg, orig, b, -STEP["gain_db"], k, f"low end heavy ({vals[k]:.2f} of the mix); bass down a step"))
            else:
                b = next((x for x in BASSY if x in tracks), None)
                if b:
                    add(_gain(cfg, orig, b, STEP["gain_db"], k, f"low end thin ({vals[k]:.2f} of the mix); bass up a step"))
        elif k == "low end mono":
            wide = sorted((x["corr"], n) for n, x in (dt or {}).items() if x["energy"] > 0 and x["corr"] < 0.9)
            for c_, n in wide:
                tp = _track_path(cfg, n)
                if tp is None:
                    continue
                if _role(n) == "bass":
                    if not _get(cfg, tp + ["mono"]) and add(_change(cfg, tp + ["mono"], True, k, f"{n} is wide in the low end (corr {c_:.2f}); mono")):
                        break
                else:
                    cur = _get(cfg, tp + ["hp"], 0) or 0
                    to = min(LIMITS["hp"], max(cur, 80) + STEP["hp"])
                    if to > cur and add(_change(cfg, tp + ["hp"], to, k, f"{n} spreads the low end (corr {c_:.2f}); high-pass at {to:.0f} Hz")):
                        break
        elif k == "stereo image":
            wid = dt or {}
            cand = [n for n in wid if _track_path(cfg, n)]
            if not cand:
                continue
            lo_w, hi_w = LIMITS["width"]
            if vals[k] < lo:
                n = max(cand, key=lambda n: (-(_get(cfg, _track_path(cfg, n) + ["width"], 1.0) or 1.0), n))
                cur = _get(cfg, _track_path(cfg, n) + ["width"], 1.0) or 1.0
                to = round(min(hi_w, cur + STEP["width"]), 2)
                if to > cur:
                    add(_change(cfg, _track_path(cfg, n) + ["width"], to, k, f"the mix is narrow ({vals[k]:.2f}); widen {n}"))
            else:
                n = max(cand, key=lambda n: (wid[n], n))
                cur = _get(cfg, _track_path(cfg, n) + ["width"], 1.0) or 1.0
                to = round(max(lo_w, cur - STEP["width"]), 2)
                if to < cur:
                    add(_change(cfg, _track_path(cfg, n) + ["width"], to, k, f"the mix is wide ({vals[k]:.2f}); narrow {n}, the widest"))
        elif k == "transients":
            if vals[k] < lo:
                if not add(_gain(cfg, orig, "kick", STEP["gain_db"], k, f"drums soft against the ring ({vals[k]:.1f} dB); kick up")):
                    pass
                add(_gain(cfg, orig, "snare", STEP["gain_db"], k, f"drums soft against the ring ({vals[k]:.1f} dB); snare up"))
        elif k == "section contrast" and vals[k] < lo and sections:
            lift = [n for n in tracks if _role(n) == "accomp" and n in tracks and not tracks[n].get("mute") and tracks[n].get("channel") != 9]
            if not lift:
                continue
            autos = cfg.get("automation", [])
            mine = next((i for i, x in enumerate(autos) if x.get("by") == "studio"), None)
            cur = autos[mine]["lift_db"] if mine is not None else 0.0
            to = min(LIMITS["lift_db"], cur + STEP["lift_db"])
            if to <= cur:
                continue
            big = {"chorus", "drop"}
            pts = []
            for s_ in sections:
                pts.append([s_["start"], to if s_["kind"] in big else 0.0])
                pts.append([s_["start"] + s_["bars"] - 0.01, to if s_["kind"] in big else 0.0])
            new = copy.deepcopy(autos)
            entry = {"type": "gain", "tracks": sorted(lift), "points": pts, "by": "studio", "lift_db": to}
            if mine is None:
                new.append(entry)
            else:
                new[mine] = entry
            add(_change(cfg, ["automation"], new, k, f"sections too alike ({vals[k]:.1f} dB); lift the accompaniment {to:.0f} dB in choruses"))
    return out


def apply_changes(cfg: dict, changes: list[dict], undo: bool = False) -> dict:
    out = copy.deepcopy(cfg)
    for c in (reversed(changes) if undo else changes):
        _set(out, c["path"], copy.deepcopy(c["from"] if undo else c["to"]))
    return out


def better(before: dict, after: dict, changes: list[dict]) -> tuple[bool, str]:
    """Keep a round only if what it aimed at improved and nothing else fell by more than TOLERANCE."""
    aimed = {c["metric"] for c in changes}
    gain = np.mean([after["scores"].get(k, 0) - before["scores"].get(k, 0) for k in aimed]) if aimed else 0
    worse = [k for k in before["scores"] if k not in aimed and k not in REPORT_ONLY
             and after["scores"].get(k, 0) < before["scores"][k] - TOLERANCE]
    if gain <= 0.005:
        return False, "did not improve " + ", ".join(sorted(aimed))
    if worse:
        return False, "hurt " + ", ".join(worse)
    if (after["score"] or 0) < (before["score"] or 0):
        return False, "lower overall"
    return True, f"{', '.join(sorted(aimed))} +{gain:.2f}"


# ---------------------------------------------------------------- rendering

def _read(path):
    import soundfile as sf
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return x


def song_of(track: Path) -> dict | None:
    """The song the track was exported from, when it has DNA (sections for passages and lifts)."""
    f = track / "dna.json"
    if not f.exists():
        return None
    import lineage as LI
    try:
        return LI.grow(json.loads(f.read_text()))
    except Exception:
        return None


def passages_for(track: Path, song: dict | None = None) -> list[list[int]]:
    """A verse and the last chorus (the passages that should differ most), MAX_BARS each."""
    song = song or song_of(track)
    if song:
        secs = song["sections"]
        pick = [next((s for s in secs if s["kind"] == "verse"), None), next((s for s in secs[::-1] if s["kind"] == "chorus"), None)]
        out = [[s["start"], s["start"] + min(MAX_BARS, s["bars"]) - 1, s["kind"]] for s in pick if s]
        if out:
            return out[:MAX_PASSAGES]
    import mido
    mid = mido.MidiFile(str(next(track.glob("*.mid"))))
    bpm = next((mido.tempo2bpm(m.tempo) for t in mid.tracks for m in t if m.type == "set_tempo"), 120)
    bars = max(8, int(mid.length * bpm / 60 / 4))
    a, b = max(1, int(bars * 0.3)), max(1, int(bars * 0.75))
    return [[a, a + MAX_BARS - 1], [b, min(bars, b + MAX_BARS - 1)]]


def render(track: Path, cfg: dict, passages, tag: str, log=print) -> list[dict]:
    """Render each passage (in parallel) with stems; return arrays at one absolute scale."""
    import build as B
    work = track / "studio" / tag
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    sys_path = str(B.ENGINE / "studio")
    import sys
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from midi_studio import to_toml
    c = dict(copy.deepcopy(cfg), base_dir=str(track))
    (work / "instruments.toml").write_text(to_toml(c))
    script = B.render_script(track)
    mid = next(track.glob("*.mid"))
    procs = []
    for i, (a, b, *_) in enumerate(passages):
        cmd = ["nice", "-n", "10", B.PY, "-u", str(script), str(mid), str(work / "instruments.toml"), "--out", str(work),
               "--stems", str(work / f"stems{i}"), "--bars", f"{a}-{b}", "--no-mp3", "--name", f"p{i}"]
        procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))
    out = []
    for i, p in enumerate(procs):
        text = p.communicate()[0]
        if p.returncode:
            raise RuntimeError(f"render of bars {passages[i]} failed:\n" + "\n".join(text.splitlines()[-8:]))
        info = json.loads((work / f"p{i}_info.json").read_text())
        sc = info.get("stem_scale", 1.0) or 1.0
        stems = {f.stem: _read(f) / sc for f in sorted((work / f"stems{i}").glob("*.wav"))}
        out.append({"bars": list(passages[i][:2]), "kind": passages[i][2] if len(passages[i]) > 2 else None, "mix": _read(work / f"p{i}_premaster.wav") / sc, "stems": stems,
                    "bpm": info.get("bpm", 120), "wav": str(work / f"p{i}.wav")})
        shutil.rmtree(work / f"stems{i}", ignore_errors=True)
        (work / f"p{i}_premaster.wav").unlink(missing_ok=True)
    log(f"rendered {tag}: " + ", ".join(f"bars {a}-{b}" for a, b, *_ in passages))
    return out


# ---------------------------------------------------------------- a session

def _versions(track):
    return sorted((track / "versions").glob("instruments.*.toml"), key=lambda p: int(p.stem.split(".")[1]))


def _save_version(track) -> int:
    d = track / "versions"
    d.mkdir(exist_ok=True)
    n = len(_versions(track))
    shutil.copy(track / "instruments.toml", d / f"instruments.{n}.toml")
    return n


def _write(track, cfg):
    import sys

    import build as B
    sp = str(B.ENGINE / "studio")
    if sp not in sys.path:
        sys.path.insert(0, sp)
    from midi_studio import to_toml
    (track / "instruments.toml").write_text(to_toml(cfg))


def produce(track: Path, rounds: int = 2, passages=None, log=print, render_fn=None) -> dict:
    """Render, measure, fix, re-render, compare, `rounds` times. Writes instruments.toml only for kept rounds."""
    track = Path(track)
    render_fn = render_fn or (lambda cfg, tag: render(track, cfg, passages, tag, log))
    song = song_of(track)
    passages = passages or passages_for(track, song)
    orig = tomllib.loads((track / "instruments.toml").read_text())
    cfg = copy.deepcopy(orig)
    t0 = time.time()
    first = render_fn(cfg, "r0")
    bpm = first[0].get("bpm", song["bpm"] if song else 120)
    cur = analyse(first, bpm)
    session = {"time": round(t0, 1), "passages": passages, "before": cur, "rounds": [], "start_version": None}
    log(text_metrics(cur, "before"))
    tried = set()
    for r in range(1, rounds + 1):
        ch = prescribe(cur, cfg, orig, tried, song["sections"] if song else None)
        if not ch:
            log("nothing left to change within the limits")
            break
        for c in ch:
            log("  try " + change_text(c))
        cand = apply_changes(cfg, ch)
        res = analyse(render_fn(cand, f"r{r}"), bpm)
        ok, why = better(cur, res, ch)
        session["rounds"].append({"changes": ch, "after": res, "kept": ok, "verdict": why})
        log(f"round {r}: {'kept' if ok else 'refused'} ({why}); score {cur['score']} -> {res['score']}")
        if ok:
            if session["start_version"] is None:
                session["start_version"] = _save_version(track)
            cfg, cur = cand, res
            _write(track, cfg)
            _save_version(track)
        else:
            tried |= {tuple(map(str, c["path"])) for c in ch}
    session["after"] = cur
    session["seconds"] = round(time.time() - t0, 1)
    hist = track / "studio.json"
    old = json.loads(hist.read_text()) if hist.exists() else []
    (track / "studio.json").write_text(json.dumps(old + [_slim(session)], indent=1, default=float))
    return session


def change_text(c: dict) -> str:
    """A change in one line. Studio automation is shown as its lift, not as its points."""
    to = c["to"]
    if c["path"] == ["automation"]:
        mine = [a for a in to if a.get("by") == "studio"]
        to = f"{mine[-1]['lift_db']:+g} dB on {', '.join(mine[-1]['tracks'])}" if mine else "none"
        return f"automation: {to}  ({c['why']})"
    return f"{'.'.join(map(str, c['path']))}: {c['from']} -> {to}  ({c['why']})"


def _slim(s):
    out = copy.deepcopy(s)
    for a in [out["before"], out.get("after")] + [r["after"] for r in out["rounds"]]:
        if a:
            a.pop("detail", None)
    return out


def history(track: Path) -> list[dict]:
    f = Path(track) / "studio.json"
    return json.loads(f.read_text()) if f.exists() else []


def revert(track: Path, version: int) -> Path:
    """Put a kept version of instruments.toml back (the current one is kept as a new version first)."""
    track = Path(track)
    v = track / "versions" / f"instruments.{version}.toml"
    if not v.exists():
        raise FileNotFoundError(v)
    _save_version(track)
    shutil.copy(v, track / "instruments.toml")
    return v


def text_metrics(a: dict, label: str = "") -> str:
    rows = [f"{label} score {a['score']}" if label else f"score {a['score']}"]
    for k, (lo, hi, _, what) in TARGETS.items():
        if k in a["values"]:
            mark = "" if a["scores"][k] >= 0.95 else "  <-"
            rows.append(f"  {k:22} {a['values'][k]:8.3f}  [{lo:g}-{hi:g}]  {a['scores'][k]:.2f}{mark}")
    return "\n".join(rows)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="the virtual record producer")
    ap.add_argument("track", type=Path)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--bars", action="append", help="a passage, e.g. 25-32 (repeatable)")
    ap.add_argument("--revert", type=int)
    a = ap.parse_args()
    if a.revert is not None:
        print("restored", revert(a.track, a.revert))
        return
    ps = [[int(x) for x in b.split("-")] for b in a.bars][:MAX_PASSAGES] if a.bars else None
    s = produce(a.track, a.rounds, ps)
    print(text_metrics(s["after"], "after"))


if __name__ == "__main__":
    main()
