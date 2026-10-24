"""The Observatory: what the ecosystem has been thinking, in one place, as plain data the DAW tab draws.

    ideas(...)            the discovery machine's last shortlist and every saved song in the family tree
    ratings(...)          every rating and judged total ever given, oldest first (the family tree is append-only)
    rate(dna, stars)      rate a song (a new line in the family tree; nothing is rewritten)
    producer(track)       every change the virtual record producer tried on a track, kept or refused, and why
    clocks(song)          the world model bar by bar: section, phrase position, chord, energy, lead and kick activity
    spectrum(wav, ...)    the level in third-octave bands of a stretch of audio
    bar_spectra(wav, ...) one spectrum per bar, for a heat map under the clocks
    branch(dna, bar, ...) children of a song that differ only inside a 4-bar passage, judged and ranked

All of it is deterministic and bounded: spectra read the audio a bar at a time, a branch makes at most
MAX_BRANCHES children, and a child that changes a note outside its passage (or the beat leading into it)
is refused.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import lineage as G
from paths import DATA

PASSAGE = 4                      # bars in a branched passage
MAX_BRANCHES = 48
LEAD_IN = 1.0                    # beats before a passage that still belong to it
BANDS = tuple(round(1000 * 2 ** (k / 3), 1) for k in range(-15, 13))     # 31.2 Hz .. 16 kHz, third octaves
NOTE = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")


# ---------------------------------------------------------------- ideas and ratings

def ideas(store: Path | None = None, last: Path | None = None) -> list[dict]:
    """[{id, where ("shortlist" | "saved"), describe, total, scores, rating, rank, time}], newest saved first,
    the last discovery run's shortlist on top. An id in both shows once, as a shortlist entry with its rating."""
    import discover as D
    recs = G.load(store)
    out, seen = [], set()
    f = Path(last or D.LAST)
    try:
        run = json.loads(f.read_text()) if f.exists() else {}
    except ValueError:
        run = {}
    for c in run.get("presented", []):
        r = recs.get(c["id"], {})
        out.append({"id": c["id"], "where": "shortlist", "describe": c.get("describe", ""), "total": c.get("total"),
                    "scores": c.get("scores", {}), "rating": r.get("rating"), "rank": c.get("rank"),
                    "time": r.get("time"), "dna": c["dna"]})
        seen.add(c["id"])
    for i, r in sorted(recs.items(), key=lambda kv: (-(kv[1].get("time") or 0), kv[0])):
        if i in seen:
            continue
        out.append({"id": i, "where": "saved", "describe": G.describe(r["dna"]), "total": r.get("total"),
                    "scores": r.get("scores", {}), "rating": r.get("rating"), "rank": None, "time": r.get("time"),
                    "dna": r["dna"]})
    return out


def ratings(store: Path | None = None) -> list[dict]:
    """Every line of the family tree that carries a rating or a judged total: [{id, time, rating, total}]."""
    store = Path(store or G.STORE)
    out = []
    if not store.exists():
        return out
    for line in store.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and "id" in r and (r.get("rating") is not None or r.get("total") is not None):
            out.append({"id": r["id"], "time": r.get("time", 0), "rating": r.get("rating"), "total": r.get("total")})
    out.sort(key=lambda r: (r["time"], r["id"]))
    return out


def rate(dna: dict, stars: float, note: str = "", store: Path | None = None) -> str:
    stars = float(np.clip(stars, 0, 5))
    return G.save(dna, rating=stars, note=note or f"rated {stars:g}", store=store)


# ---------------------------------------------------------------- the producer's notebook

def producer(track: Path) -> list[dict]:
    """[{session, time, round, change, kept, verdict, before, after}] for every change of every studio session."""
    import studio as ST
    out = []
    for k, s in enumerate(ST.history(track)):
        before = (s.get("before") or {}).get("score")
        for r, rd in enumerate(s.get("rounds", []), 1):
            after = (rd.get("after") or {}).get("score")
            for c in rd.get("changes", []):
                out.append({"session": k + 1, "time": s.get("time"), "round": r, "change": ST.change_text(c),
                            "kept": bool(rd.get("kept")), "verdict": rd.get("verdict", ""), "before": before, "after": after})
            if rd.get("kept"):
                before = after
    return out


# ---------------------------------------------------------------- the world model's clocks

def chord_name(pcs, root) -> str:
    if root is None:
        return ""
    pcs = {int(p) % 12 for p in pcs}
    r = int(root) % 12
    q = "m" if (r + 3) % 12 in pcs and (r + 4) % 12 not in pcs else ""
    q += "dim" if q == "m" and (r + 6) % 12 in pcs and (r + 7) % 12 not in pcs else ""
    q += "7" if (r + 10) % 12 in pcs else "maj7" if (r + 11) % 12 in pcs else ""
    return NOTE[r] + q


def clocks(song: dict) -> list[dict]:
    """[{bar, section, kind, in_section, phrase, chord, energy, lead, kicks, notes}], one per bar (1-based)."""
    import network as N
    ctx = N.context(song)
    chords = sorted(song.get("chords") or [])
    lead = song["parts"].get("lead") or song["parts"].get("melody") or []
    out = []
    for b in range(1, ctx["bars"] + 1):
        s = ctx["section"][b] or {}
        t0 = (b - 1) * 4.0
        ch = [c for c in chords if c[0] <= t0 + 0.01 < c[0] + c[1]]
        pos = b - s["start"] + 1 if s else 0
        out.append({"bar": b, "section": s.get("name", ""), "kind": s.get("kind", ""), "in_section": pos,
                    "phrase": (pos - 1) % 4 + 1 if pos else 0, "chord": chord_name(ch[0][2], ch[0][3]) if ch else "",
                    "energy": ctx["energy"][b], "lead": sum(1 for n in lead if t0 <= n[0] < t0 + 4),
                    "kicks": sum(1 for k in ctx["kicks"] if t0 <= k < t0 + 4),
                    "notes": sum(ctx["density"][p][b] for p in ctx["density"])})
    return out


# ---------------------------------------------------------------- spectra

def _bands(x: np.ndarray, sr: int) -> np.ndarray:
    """dB per third-octave band (relative to full scale) of a mono stretch."""
    n = 1 << int(np.ceil(np.log2(max(len(x), 1024))))
    win = np.hanning(len(x)) if len(x) > 1 else np.ones(len(x))
    p = np.abs(np.fft.rfft(x * win, n)) ** 2 / max(1e-12, (win ** 2).sum() * len(x) / 2)
    f = np.fft.rfftfreq(n, 1 / sr)
    out = []
    for c in BANDS:
        m = (f >= c / 2 ** (1 / 6)) & (f < c * 2 ** (1 / 6))
        out.append(10 * np.log10(p[m].sum() + 1e-12) if m.any() else -120.0)
    return np.maximum(np.array(out), -120.0)


def spectrum(wav: Path, start: float = 0.0, secs: float | None = None, max_secs: float = 30.0) -> dict:
    """{"bands": Hz, "db": level per band} of a stretch of a WAV (at most max_secs, mixed to mono)."""
    import soundfile as sf
    info = sf.info(str(wav))
    a = int(max(0.0, start) * info.samplerate)
    b = min(info.frames, a + int(min(secs or max_secs, max_secs) * info.samplerate))
    x, sr = sf.read(str(wav), start=a, stop=max(a + 1, b), dtype="float64", always_2d=True)
    return {"bands": list(BANDS), "db": [round(float(v), 2) for v in _bands(x.mean(axis=1), sr)]}


def bar_spectra(wav: Path, bpm: float, bars: int | None = None, max_bars: int = 512) -> dict:
    """{"bands", "db": [[level per band] per bar]}, read one bar at a time."""
    import soundfile as sf
    info = sf.info(str(wav))
    spb = 240.0 / float(bpm) * info.samplerate
    have = int(info.frames // spb)
    n = min(max_bars, have if bars is None else min(bars, have))
    rows = []
    with sf.SoundFile(str(wav)) as f:
        for k in range(n):
            f.seek(int(k * spb))
            x = f.read(int(spb), dtype="float64", always_2d=True)
            rows.append([round(float(v), 1) for v in _bands(x.mean(axis=1), info.samplerate)])
    return {"bands": list(BANDS), "db": rows}


# ---------------------------------------------------------------- branching a passage

def dna_of(track: Path) -> dict | None:
    """The DNA a track folder was made from: its dna.json, or an origin rebuilt from a Bounty song's source.json."""
    track = Path(track)
    f = track / "dna.json"
    try:
        if f.exists():
            d = json.loads(f.read_text())
            d.pop("id", None)
            return d
        src = json.loads((track / "source.json").read_text())
    except (OSError, ValueError):
        return None
    if src.get("kind") != "electronium-song":
        return None
    return G.origin(src["bounty"], length=src.get("length") or "normal", reharm=src.get("reharm", 0.25),
                    brief=src.get("brief", ""))


def song_of(track: Path) -> dict | None:
    """The song behind a track folder: grown from its DNA when it has one, else read from its MIDI."""
    import features as F
    track = Path(track)
    if (track / "dna.json").exists():
        try:
            return G.grow(dna_of(track))
        except Exception:
            pass
    mids = sorted(track.glob("*.mid"))
    if not mids:
        return None
    song = F.from_midi(mids[0])
    return song if song.get("bars") else None


def _passage_changes(song: dict, a: int, rng) -> list[dict]:
    """Seeded changes confined to bars a .. a+3."""
    b = min(song["bars"], a + PASSAGE - 1)
    half = [a, min(b, a + 1)] if rng.random() < 0.5 else [max(a, b - 1), b]
    pool = [("vary_phrase", lambda: {"bars": half, "how": str(rng.choice(["diatonic", "invert", "retrograde", "neighbor"])),
                                     "steps": int(rng.choice([-2, -1, 1, 2]))}),
            ("ornament", lambda: {"bars": [a, b], "amount": round(float(rng.uniform(0.3, 0.8)), 2)}),
            ("groove_mutate", lambda: {"bars": [a, b], "amount": round(float(rng.uniform(0.2, 0.7)), 2)}),
            ("bass_push", lambda: {"bars": [a, b], "amount": round(float(rng.uniform(0.2, 0.6)), 2)}),
            ("fill", lambda: {"bar": b, "length": int(rng.choice([1, 1, 2]))})]
    out = []
    for _ in range(int(rng.integers(1, 3))):
        op, args = pool[int(rng.integers(len(pool)))]
        out.append({"op": op, "args": args(), "seed": int(rng.integers(1, 2**31)), "why": f"passage {a}-{b}: {op}"})
    return out


def _outside(song: dict, a: int, b: int) -> tuple:
    """Every note outside the passage, sorted. The passage owns the beat before it (a pickup into bar a)."""
    lo, hi = (a - 1) * 4.0 - LEAD_IN, b * 4.0
    keep = lambda n: not (lo <= n[0] < hi)  # noqa: E731
    return (tuple(sorted((p, tuple(n[:3])) for p, notes in song["parts"].items() for n in notes if keep(n))),
            tuple(sorted(tuple(d[:3]) for d in song["drums"] if keep(d))))


def branch(dna: dict, bar: int, n: int = 12, seed: int = 0, keep: int = 6) -> dict:
    """Up to n children of the song that differ only in bars bar .. bar+3, judged; the survivors ranked.
    Returns {"passage": [a, b], "presented": [{id, dna, scores, total, front, why, describe}], "rejected": {...}}."""
    import discover as D
    import evaluators as V
    import evolve as EV
    n = int(np.clip(n, 1, MAX_BRANCHES))
    song = G.grow(dna)
    a = int(np.clip(bar, 1, song["bars"]))
    b = min(song["bars"], a + PASSAGE - 1)
    fixed = _outside(song, a, b)
    rng = np.random.default_rng([seed & 0xFFFFFFFF, a, 11])
    cands, rejected, seen = [], {}, {G.dna_id(dna)}
    for _ in range(n * 2):
        if len(seen) > n:
            break
        ch = _passage_changes(song, a, rng)
        kid = G.child(dna, ch, label=dna.get("label", ""))
        i = G.dna_id(kid)
        if i in seen:
            continue
        seen.add(i)
        grown = EV.apply_all(song, ch)
        why = None
        if grown["parts"] == song["parts"] and grown["drums"] == song["drums"]:
            why = "no change took"
        elif _outside(grown, a, b) != fixed:
            why = "changed notes outside the passage"
        else:
            res = V.evaluate(grown)
            why = D._reject(res)
        if why:
            rejected[why] = rejected.get(why, 0) + 1
            continue
        cands.append({"id": i, "dna": kid, "scores": res["scores"], "describe": G.describe(kid, grown)})
    ranked = V.rank(cands) if cands else []
    return {"passage": [a, b], "presented": ranked[:keep], "rejected": rejected, "considered": len(seen) - 1}
