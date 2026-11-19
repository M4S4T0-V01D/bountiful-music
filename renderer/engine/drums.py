"""Breakbeats, the way they were made in the 90s, but from original material:

1. A drummer 'plays' a two-bar break at its own tempo (synthesised kit, swing, ghost notes, human
   timing) in a small room; the take goes through a 12-bit / 26 kHz sampler. -> audio/samples/breaks
2. The take is sliced at every 16th onset (we know exactly where the hits are, like ReCycle).
3. Slices are pitched up to the song tempo and re-sequenced: original order for the groove, swaps,
   ghost-note flurries, reversals, stutters and triplet fills for variation.

Clean layers (sub kick, crisp snare, swung hats, shaker, bongos, jazz ride, crash) sit on top.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import fx, synth

# ---------------------------------------------------------------- source breaks (32 sixteenths = 2 bars)

BREAKS = {
    "hustle": {
        "bpm": 100, "swing": 0.18, "seed": 11,
        "K": [(0, 1.0), (7, .75), (10, .9), (16, 1.0), (18, .7), (26, .85), (29, .6)],
        "S": [(4, 1.0), (12, 1.0), (20, 1.0), (28, .95)],
        "G": [(6, .28), (9, .22), (15, .32), (22, .25), (25, .3), (31, .35)],
        "H": [(s, .62 if s % 4 == 0 else .5) for s in range(0, 32, 2) if s not in (14, 30)] + [(3, .22), (11, .25), (19, .22), (27, .25)],
        "O": [(14, .5), (30, .5)],
        "R": [],
    },
    "roller": {
        "bpm": 100, "swing": 0.14, "seed": 23,
        "K": [(0, 1.0), (2, .62), (10, .9), (16, 1.0), (23, .7), (26, .85)],
        "S": [(4, 1.0), (12, 1.0), (20, 1.0), (28, 1.0), (30, .6)],
        "G": [(7, .3), (9, .25), (11, .35), (13, .2), (19, .3), (21, .25), (25, .3), (27, .35), (31, .4)],
        "H": [],
        "O": [],
        "R": [(s, .55 if s % 4 == 0 else .4) for s in range(0, 32, 2)] + [(3, .25), (15, .3), (19, .25), (31, .3)],
    },
    "tumble": {   # busy, Amen-ish energy (original pattern): double kicks, snare pickups, ghost runs
        "bpm": 140, "swing": 0.08, "seed": 37,
        "K": [(0, 1.0), (2, .72), (10, .92), (11, .5), (16, 1.0), (18, .65), (26, .9)],
        "S": [(4, 1.0), (12, 1.0), (20, 1.0), (28, 1.0), (15, .62), (30, .7)],
        "G": [(6, .3), (7, .38), (9, .33), (14, .28), (22, .3), (23, .36), (25, .35), (31, .42)],
        "H": [(s, .58 if s % 4 == 0 else .45) for s in range(0, 32, 2)] + [(3, .2), (13, .22), (19, .2), (27, .24)],
        "O": [], "R": [],
    },
    "lazy": {     # heavy and behind the beat, for slow tempos
        "bpm": 96, "swing": 0.26, "seed": 41,
        "K": [(0, 1.0), (7, .8), (10, .9), (16, 1.0), (19, .6), (26, .85)],
        "S": [(4, 1.0), (12, 1.0), (20, 1.0), (28, 1.0)],
        "G": [(15, .3), (21, .25), (31, .35)],
        "H": [(s, .55 if s % 4 == 0 else .42) for s in range(0, 32, 2) if s not in (6, 22)],
        "O": [(6, .45), (22, .45)], "R": [],
    },
    "rave": {     # straight-ahead hardcore break: 16th hats, punchy kick on the 'and'
        "bpm": 128, "swing": 0.04, "seed": 53,
        "K": [(0, 1.0), (6, .8), (10, .95), (16, 1.0), (22, .8), (25, .7)],
        "S": [(4, 1.0), (12, 1.0), (20, 1.0), (28, 1.0), (31, .55)],
        "G": [(9, .3), (14, .35), (27, .3)],
        "H": [(s, .55 if s % 2 == 0 else .32) for s in range(32) if s not in (14, 30)],
        "O": [(14, .5), (30, .5)], "R": [],
    },
}


from .share import SAMPLES as SAMPLE_DIR, sample  # noqa: E402
_sample_cache: dict = {}


def load_sample(rel: str) -> np.ndarray:
    """A recorded one-shot (LMMS sample library or any path), mono, at the engine rate, trimmed to its
    onset and peak-normalised."""
    if rel in _sample_cache:
        return _sample_cache[rel]
    import soundfile as sf
    from pathlib import Path
    p = sample(rel)
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    m = x.mean(1)
    if sr != fx.SR:
        m = fx.resample(m, sr / fx.SR)
    on = int(np.argmax(np.abs(m) > np.abs(m).max() * 0.02))
    m = m[max(0, on - 32):]
    m = (m / (np.abs(m).max() + 1e-9) * 0.9).astype(np.float32)
    _sample_cache[rel] = m
    return m


def sampled_hit(rng, files: list[str], vel: float, dark: bool = False, detune_cents: float = 15) -> np.ndarray:
    """One hit from a list of recordings: round-robin pick, a touch of pitch variation, softer = darker."""
    x = load_sample(files[int(rng.integers(len(files)))])
    ratio = 2 ** (rng.normal(0, detune_cents) / 1200)
    y = fx.resample(x, ratio) if abs(ratio - 1) > 1e-4 else x.copy()
    if dark or vel < 0.45:
        y = fx.lp(y, 2500 + 6000 * vel, 2)
    return (y * vel ** 1.2).astype(np.float32)


PREROLL = 0.004  # slices start a little before the onset so no transient is clipped


@dataclass
class Break:
    name: str
    audio: np.ndarray          # mono, at fx.SR, already 'sampled'
    onsets: list[int]          # sample index of each of the 32 steps
    classes: list[str]         # 'K', 'S', 'G', 'H' per step
    bpm: float


def record_break(name: str, bpm: float | None = None, kit: dict | None = None, sampler: dict | None = None) -> Break:
    """`bpm` re-records the break at another tempo (so it is pitched less when played faster);
    `kit` tunes the drummer's kit: {"kick": {...synth.kick args}, "snare": {...}}."""
    spec = dict(BREAKS[name])
    if bpm:
        spec["bpm"] = bpm
    kit = kit or {}
    kk = {"start": 118, "end": 56, "decay": 0.2, "click": 0.3, "body": 0.35} | kit.get("kick", {})
    sk = {"tone": 196, "decay": 0.17} | kit.get("snare", {})
    rng = np.random.default_rng(spec["seed"])
    s16 = 60 / spec["bpm"] / 4
    n = int((32 * s16 + 1.5) * fx.SR)
    dry = np.zeros(n, np.float32)
    onsets = []
    for step in range(32):
        t = step * s16 + (spec["swing"] * s16 if step % 2 else 0)
        onsets.append(t)

    smp = kit.get("samples", {})

    def hit(kind_, v):   # recorded one-shots when the kit has them, else the synthesised drum
        files = smp.get(kind_) or (smp.get("snare") if kind_ == "ghost" else None)
        if files:
            return sampled_hit(rng, files, v, dark=(kind_ == "ghost"))
        return None

    def put(x, step, extra=0.0):
        t = onsets[step] + extra + rng.normal(0, 0.003)
        i = max(0, int(t * fx.SR))
        m = min(len(x), n - i)
        dry[i:i + m] += x[:m]

    kk = {k: v for k, v in kk.items() if k != "samples"}
    sk = {k: v for k, v in sk.items() if k != "samples"}
    for step, v in spec["K"]:
        h = hit("kick", v)
        put(h if h is not None else synth.kick(rng, v, **kk), step)
    for step, v in spec["S"]:
        h = hit("snare", v)
        put(h if h is not None else synth.snare(rng, v, **sk), step, 0.006)   # laid-back backbeat
    for step, v in spec["G"]:
        h = hit("ghost", v)
        put(h if h is not None else synth.snare(rng, v, tone=sk["tone"], decay=sk["decay"] * 0.6, dark=True), step)
    for step, v in spec["H"]:
        h = hit("hat", v * 0.8)
        put(h if h is not None else synth.hat(rng, v * 0.8), step)
    for step, v in spec["O"]:
        h = hit("open", v * 0.8)
        put(h if h is not None else synth.hat(rng, v * 0.8, open_=True), step)
    for step, v in spec["R"]:
        h = hit("ride", v * 0.7)
        put(h if h is not None else synth.ride(rng, v * 0.7, bell=0.15 if step % 4 else 0.35), step)

    # the room, the desk, the sampler
    room = fx.convolve(dry, fx.reverb_ir(0.5, 0.002, damp=0.7, seed=spec["seed"], size=0.3))[:, 0]
    take = dry + 0.28 * room
    take = fx.compress(take, -16, 3.5, 0.003, 0.09, makeup_db=4)
    take = fx.saturate(take, 1.8)
    sm = {"bits": 12, "rate": 26040, "filtered": True} | (sampler or {})
    take = fx.crush(take, bits=sm["bits"], rate=sm["rate"], filtered=sm["filtered"])
    take /= np.abs(take).max() * 1.12

    classes = []
    for step in range(32):
        hit = {k for k in ("K", "S", "G", "H", "O", "R") if any(s == step for s, _ in spec[k])}
        classes.append("K" if "K" in hit else "S" if "S" in hit else "G" if "G" in hit else "H")
    return Break(name, take.astype(np.float32), [int(o * fx.SR) for o in onsets], classes, spec["bpm"])


# ---------------------------------------------------------------- chop programming

@dataclass
class Hit:
    beat: float                # beats from section start (grid)
    src: str
    idx: int
    length: float              # beats
    rev: bool = False
    stutter: int = 1
    pitch: float = 0.0         # semitones
    vel: float = 1.0
    grid16: bool = True        # swing applies


def _base_bar(bar: int, src: str) -> list[tuple[str, int]]:
    half = 16 * (bar % 2)
    return [(src, half + k) for k in range(16)]


def program_bar(bar: int, bars: int, prog: dict, breaks: dict[str, Break], rng) -> list[Hit]:
    """One bar of chopped break. `prog` keys: main, alt, chop (0..1), fill (bool), halftime (bool)."""
    main, alt = prog.get("main", "hustle"), prog.get("alt", "roller")
    chop = prog.get("chop", 0.2)
    seq = _base_bar(bar, main)
    if prog.get("alt_bars") and rng.random() < prog["alt_bars"]:
        seq = _base_bar(bar, alt)
    last_of_phrase = (bar % 8 == 7) or bar == bars - 1
    mid_phrase = bar % 4 == 3 and not last_of_phrase
    cls = lambda s, i: breaks[s].classes[i]

    # variation: swap non-backbeat steps for slices of the same class
    for step in range(16):
        if step in (4, 12):
            continue
        if rng.random() < chop * 0.35:
            s, i = seq[step]
            c = cls(s, i)
            pool = [(b, j) for b in (main, alt) for j in range(32) if cls(b, j) == c]
            seq[step] = pool[int(rng.integers(len(pool)))]
    if rng.random() < chop * 0.6:  # ghost flurry into the next bar
        g = [(alt, j) for j in range(32) if cls(alt, j) == "G"]
        for step in (13, 14, 15):
            if rng.random() < 0.7:
                seq[step] = g[int(rng.integers(len(g)))]

    hits = [Hit(k * 0.25, s, i, 0.25) for k, (s, i) in enumerate(seq)]

    if prog.get("stop_last") and bar == bars - 1:
        return [Hit(0, main, next(j for j in range(32) if cls(main, j) == "K"), 1.0)]

    if prog.get("halftime"):
        k = next(j for j in range(32) if cls(main, j) == "K")
        sn = next(j for j in range(32) if cls(main, j) == "S")
        hh = [j for j in range(32) if cls(main, j) == "H"]
        hits = [Hit(0, main, k, 0.5), Hit(2, main, sn, 0.5)]
        hits += [Hit(st * 0.25, main, hh[int(rng.integers(len(hh)))], 0.25, vel=0.6) for st in (2, 6, 10, 14) if rng.random() < 0.7]
        if rng.random() < 0.5:
            hits.append(Hit(2.5 + 0.25 * 3, main, k, 0.25, vel=0.8))
        return hits

    if prog.get("fill", True) and (last_of_phrase or (mid_phrase and rng.random() < chop)):
        kind = rng.choice(["roll", "reverse", "triplet", "stop", "shuffle"] if last_of_phrase else ["shuffle", "reverse"])
        if prog.get("fill_last") and bar == bars - 1:
            kind = "roll"
        snares = [(b, j) for b in (main, alt) for j in range(32) if cls(b, j) == "S"]
        ghosts = [(b, j) for b in (main, alt) for j in range(32) if cls(b, j) == "G"]
        if kind == "roll":
            hits = hits[:8]
            for st in range(8, 16):
                s, i = snares[int(rng.integers(len(snares)))] if st % 2 == 0 or st > 12 else ghosts[int(rng.integers(len(ghosts)))]
                hits.append(Hit(st * 0.25, s, i, 0.25, stutter=2 if st >= 14 else 1, vel=0.55 + 0.45 * (st - 8) / 7,
                                pitch=float(rng.choice([0, 0, 1, 2])) if st >= 12 else 0))
        elif kind == "reverse":
            s, i = snares[int(rng.integers(len(snares)))]
            hits = hits[:13] + [Hit(13 * 0.25, s, i, 0.75, rev=True, vel=0.9)]
        elif kind == "triplet":
            hits = hits[:12]
            pool = snares + ghosts
            for k in range(6):
                s, i = pool[int(rng.integers(len(pool)))] if k % 2 else snares[int(rng.integers(len(snares)))]
                hits.append(Hit(3 + k / 6, s, i, 1 / 6, vel=0.6 + 0.07 * k, grid16=False))
        elif kind == "stop":
            hits = hits[:12] + [Hit(3.0, main, next(j for j in range(32) if cls(main, j) == "K"), 0.25)]
        elif kind == "shuffle":
            for st in range(8, 16):
                if st != 12 and rng.random() < 0.6:
                    s, i = seq[int(rng.integers(16))]
                    hits[st] = Hit(st * 0.25, s, i, 0.25, rev=bool(rng.random() < 0.15))
    return hits


def rush_bar(breaks: dict[str, Break], src: str, rng, density: float = 0.8) -> list[Hit]:
    """A 165-bpm-feel top layer: hats/ghosts on the 16th-triplet grid of 110 (= straight 16ths at 165).
    Accents every 2 and 4 triplets make the faster pulse audible without moving the backbeat."""
    pool = [j for j in range(32) if breaks[src].classes[j] in ("H", "G")]
    out = []
    for k in range(24):
        if rng.random() > density * (1.0 if k % 2 == 0 else 0.55):
            continue
        acc = 1.0 if k % 4 == 0 else 0.7 if k % 2 == 0 else 0.45
        out.append(Hit(k / 6, src, pool[int(rng.integers(len(pool)))], 1 / 6, vel=acc, grid16=False))
    return out


# ---------------------------------------------------------------- rendering hits to audio

class Sampler:
    """Plays break slices pitched to the song tempo, caching each (slice, pitch, reverse) variant."""

    def __init__(self, breaks: dict[str, Break], bpm: float):
        self.breaks = breaks
        self.bpm = bpm
        self.cache: dict = {}

    def slice(self, src: str, idx: int, steps: float, rev: bool, pitch: float) -> tuple[np.ndarray, float]:
        """The slice audio and how many seconds of it come before the hit (pre-roll)."""
        key = (src, idx, round(steps, 3), rev, pitch)
        if key in self.cache:
            return self.cache[key]
        b = self.breaks[src]
        ratio = self.bpm / b.bpm * 2 ** (pitch / 12)
        a = max(0, b.onsets[idx] - int(PREROLL * fx.SR))
        span = max(1, int(np.ceil(steps)))
        e = b.onsets[idx + span] if idx + span < 32 else len(b.audio)
        if rev:
            e = b.onsets[min(idx + 3, 31)] if idx + 3 < 32 else len(b.audio)
        x = b.audio[a:e].copy()
        if rev:
            x = x[::-1].copy()
        y = fx.resample(x, ratio)
        pre = 0.0 if rev else (b.onsets[idx] - a) / fx.SR / ratio
        self.cache[key] = (y, pre)
        return self.cache[key]


def render_hits(hits: list[Hit], sampler: Sampler, beat_s: float, swing: float, n: int, rng,
                gain: float = 1.0) -> tuple[np.ndarray, list[tuple[float, str, float]]]:
    """Mono buffer for a section; also returns (time, class, vel) of every hit for layers/sidechain."""
    out = np.zeros(n, np.float32)
    trig = []
    hits = sorted(hits, key=lambda h: h.beat)
    s16 = beat_s / 4
    for k, h in enumerate(hits):
        t = h.beat * beat_s
        if h.grid16:
            step = int(round(h.beat * 4))
            if step % 2:
                t += swing * s16
        t += rng.normal(0, 0.0015)
        nxt = hits[k + 1].beat * beat_s if k + 1 < len(hits) else t + h.length * beat_s
        avail = max(nxt - t, h.length * beat_s * 0.5) + 0.004
        if h.rev:
            avail = h.length * beat_s
        x, pre = sampler.slice(h.src, h.idx, h.length * 4 if not h.rev else 3, h.rev, h.pitch)
        t -= pre
        reps = max(1, h.stutter)
        seg_len = int(min(len(x), avail * fx.SR / reps))
        if seg_len < 8:
            continue
        seg = x[:seg_len].copy()
        fade = min(int(0.004 * fx.SR), seg_len // 2)
        seg[-fade:] *= np.linspace(1, 0, fade)
        fin = max(8, min(int(pre * fx.SR * 0.8), int(0.002 * fx.SR)))  # fade in within the pre-roll
        seg[:fin] *= np.linspace(0, 1, fin)
        if h.rev:  # reversed slices end exactly on the next grid point
            t = t + avail - seg_len / fx.SR
        for r in range(reps):
            i = int((t + r * seg_len / fx.SR) * fx.SR)
            if i < 0 or i >= n:
                continue
            m = min(seg_len, n - i)
            out[i:i + m] += seg[:m] * h.vel * gain * (0.85 if r else 1.0)
        if not h.rev:  # layers follow the real transient, not the slice's pre-roll
            trig.append((t + pre, sampler.breaks[h.src].classes[h.idx], h.vel))
    return out, trig


# ---------------------------------------------------------------- clean layers

def hats_bar(rng, density: float, open_prob: float) -> list[tuple[float, str, float]]:
    out = []
    for st in range(16):
        if st % 2 == 0:
            v = 0.62 if st % 4 == 0 else 0.5
        else:
            if rng.random() > density:
                continue
            v = 0.26 + 0.1 * rng.random()
        kind = "hat"
        if st == 14 and rng.random() < open_prob:
            kind = "open"
        out.append((st * 0.25, kind, v))
    return out


def ride_bar(rng) -> list[tuple[float, str, float]]:
    """Jazz ride: 'ding, ding-a ding' with the skip notes swung hard."""
    out = [(0.0, "ride", .6), (1.0, "ride", .55), (2.0, "ride", .6), (3.0, "ride", .55)]
    out += [(1.0 + 2 / 3, "ride", .4), (3.0 + 2 / 3, "ride", .42)]
    if rng.random() < 0.3:
        out.append((2.0 + 2 / 3, "ride", .3))
    return out


def perc_bar(rng, bar: int) -> list[tuple[float, str, float]]:
    out = [(st * 0.25, "shaker", 0.35 if st % 2 else 0.22) for st in range(16)]
    pat = [(3, "bongo_hi", .5), (6, "bongo_lo", .55), (11, "bongo_hi", .45), (14, "bongo_lo", .5)]
    if bar % 2:
        pat = [(2, "bongo_hi", .45), (7, "bongo_hi", .5), (10, "bongo_lo", .55), (15, "bongo_hi", .4)]
    out += [(st * 0.25, k, v) for st, k, v in pat if rng.random() < 0.85]
    return out


class Kit:
    """Round-robin one-shots for the clean layers (each hit slightly different)."""

    def __init__(self, seed: int, params: dict | None = None):
        rng = np.random.default_rng(seed)
        params = params or {}
        kp = {"start": 150, "end": 48, "decay": 0.17, "click": 0.12, "body": 0.08, "sweep": 0.03} | params.get("layer_kick", {})
        sp = {"tone": 205, "decay": 0.14, "crack": 1.4} | params.get("layer_snare", {})
        self.sounds = {
            "kick": [synth.kick(rng, 1.0, **kp) for _ in range(3)],
            "snare": [synth.snare(rng, 1.0, **sp) for _ in range(4)],
            "clap": [synth.clap(rng, 1.0, params.get("clap_tail", 0.12)) for _ in range(3)],
            "hat": [synth.hat(rng, 1.0) for _ in range(6)],
            "open": [synth.hat(rng, 1.0, open_=True) for _ in range(2)],
            "ride": [synth.ride(rng, 1.0, bell=0.25) for _ in range(4)],
            "shaker": [synth.shaker(rng, 1.0) for _ in range(5)],
            "bongo_hi": [synth.bongo(rng, 1.0, 392) for _ in range(3)],
            "bongo_lo": [synth.bongo(rng, 1.0, 262) for _ in range(3)],
            "rim": [synth.rim(rng, 1.0) for _ in range(2)],
            "crash": [synth.crash(rng, 1.0)],
            "odaiko": [synth.taiko(rng, "odaiko") for _ in range(3)],
            "chu": [synth.taiko(rng, "chu") for _ in range(4)],
            "shime": [synth.taiko(rng, "shime") for _ in range(5)],
            "kara": [synth.taiko(rng, "kara") for _ in range(3)],
            "kane": [synth.taiko(rng, "kane") for _ in range(2)],
        }
        for name, files in params.get("samples", {}).items():   # recorded one-shots replace synthesised layers
            if files:
                self.sounds[name] = [fx.resample(load_sample(f), 2 ** (d / 1200)) for f in files for d in (-12, 0, 9)]
        self.rng = rng

    def get(self, kind: str) -> np.ndarray:
        v = self.sounds[kind]
        return v[int(self.rng.integers(len(v)))]


def place(buf: np.ndarray, x: np.ndarray, t: float, gain: float) -> None:
    i = int(t * fx.SR)
    if i < 0 or i >= len(buf):
        return
    m = min(len(x), len(buf) - i)
    buf[i:i + m] += x[:m] * gain


# ---------------------------------------------------------------- programmed (non-break) grooves

def pattern_bar(style: str, bar: int, bars: int, rng, dr: dict) -> list[tuple[float, str, str, float]]:
    """(beat, stem, sound, velocity) for house / garage bars. Stems: kick, snare, top, perc."""
    out = []
    last = bar % 8 == 7
    if style == "house":
        if dr.get("kick", 1.0) > 0:
            out += [(b, "kick", "kick", 0.95 * dr.get("kick", 1.0)) for b in range(4)]
        if dr.get("clap", 0) > 0:
            out += [(1.0, "snare", "clap", dr["clap"]), (3.0, "snare", "clap", dr["clap"])]
            if last and rng.random() < 0.6:
                out += [(3.75, "snare", "clap", dr["clap"] * 0.6)]
        h = dr.get("hats", 0)
        if h > 0:
            out += [(b + 0.5, "top", "open", 0.55 * h) for b in range(4)]
            out += [(s * 0.25, "top", "hat", (0.32 if s % 2 else 0.22) * h) for s in range(16) if s % 4 != 2 and rng.random() < 0.85]
        if dr.get("perc", 0) > 0:
            out += [(s * 0.25, "perc", "shaker", (0.35 if s % 2 else 0.2) * dr["perc"]) for s in range(16)]
            if rng.random() < 0.7:
                out += [(st * 0.25, "perc", "bongo_hi" if st % 2 else "bongo_lo", 0.45 * dr["perc"]) for st in (3, 7, 10, 14) if rng.random() < 0.8]
        if dr.get("ride", 0) > 0:
            out += [(b + o, "top", "ride", (0.5 if o == 0 else 0.35) * dr["ride"]) for b in range(4) for o in (0, 0.5)]
    elif style == "garage":
        k = dr.get("kick", 1.0)
        if k > 0:
            kicks = [0.0, 2.5] if bar % 2 == 0 else [0.0, 1.75, 2.5]
            if rng.random() < 0.3:
                kicks.append(3.75)
            out += [(b, "kick", "kick", 0.95 * k) for b in kicks]
        if dr.get("clap", 0) > 0:
            out += [(1.0, "snare", "clap", dr["clap"]), (3.0, "snare", "clap", dr["clap"])]
            out += [(b, "snare", "rim", 0.35 * dr["clap"]) for b in (1.75, 3.5) if rng.random() < 0.5]
        h = dr.get("hats", 0)
        if h > 0:
            for s in range(16):
                if s % 4 == 0:
                    continue
                if rng.random() < (0.95 if s % 2 == 0 else 0.6):
                    out.append((s * 0.25, "top", "hat", (0.45 if s % 4 == 2 else 0.28) * h))
            if rng.random() < 0.5:
                out += [(3 + k6 / 6, "top", "hat", 0.25 * h) for k6 in range(3, 6)]   # triplet hat flick
            out += [(1.5, "top", "open", 0.4 * h)] if bar % 2 else []
        if dr.get("perc", 0) > 0:
            out += [(s * 0.25, "perc", "shaker", (0.3 if s % 2 else 0.18) * dr["perc"]) for s in range(16)]
    elif style == "bossa":
        clave = [0, 3, 6] if bar % 2 == 0 else [2, 6]          # bossa clave on the rim
        out += [(st * 0.5, "snare", "rim", 0.5 * dr.get("rim", 1.0)) for st in clave]
        if dr.get("kick", 0) > 0:                              # surdo-like low pulse
            out += [(0.0, "kick", "kick", 0.8 * dr["kick"]), (1.5, "kick", "kick", 0.45 * dr["kick"]),
                    (2.0, "kick", "kick", 0.75 * dr["kick"]), (3.5, "kick", "kick", 0.45 * dr["kick"])]
        if dr.get("perc", 0) > 0:
            out += [(s16 * 0.25, "perc", "shaker", (0.34 if s16 % 2 else 0.2) * dr["perc"]) for s16 in range(16)]
            tumbao = [(1.5, "bongo_hi", .55), (3.5, "bongo_hi", .6), (3.75, "bongo_lo", .5), (0.75, "bongo_lo", .35)]
            out += [(b, "perc", k, v * dr["perc"]) for b, k, v in tumbao if rng.random() < 0.9]
        if dr.get("hats", 0) > 0:
            out += [(b + o, "top", "hat", (0.4 if o == 0.5 else 0.25) * dr["hats"]) for b in range(4) for o in (0.0, 0.5)]
    elif style == "taiko":
        # intensity 0..1 decides how much of the ensemble plays; the last `oroshi` bars of the
        # section are an accelerating roll on the big drums (the classic taiko build)
        L = dr.get("level", 0.5)
        ob = dr.get("oroshi", 0)
        if ob and bar >= bars - ob:
            i = bar - (bars - ob)
            sub = [2, 3, 4, 6, 8][min(4, int(i * 5 / ob))]
            for k in range(4 * sub):
                frac = (i + k / (4 * sub)) / ob
                out.append((k / sub, "perc", "chu", 0.45 + 0.5 * frac))
                if k % sub == 0:
                    out.append((k / sub, "kick", "odaiko", 0.6 + 0.4 * frac))
            return out
        out.append((0.0, "kick", "odaiko", 0.95))
        if L >= 0.15 and bar % 2 == 1:
            out.append((2.0, "kick", "odaiko", 0.6))
        if L >= 0.4:
            out += [(1.5, "kick", "odaiko", 0.7), (2.5, "kick", "odaiko", 0.75)]
        if L >= 0.75:
            out += [(1.0, "kick", "odaiko", 0.8), (3.0, "kick", "odaiko", 0.85), (3.75, "kick", "odaiko", 0.6)]
        # chū-daiko: 'don doko' cells
        if L >= 0.3:
            cell = [0, 3, 4, 8, 11, 12] if bar % 2 == 0 else [0, 4, 6, 7, 8, 12, 14, 15]
            if L >= 0.75:
                cell = [s16 for s16 in range(16) if s16 % 4 != 2 or rng.random() < 0.5]
            out += [(s16 * 0.25, "perc", "chu", (0.75 if s16 % 4 == 0 else 0.5) * min(1, L + 0.2)) for s16 in cell]
        # shime-daiko: the high, tight timekeeper
        if L >= 0.1:
            step = 2 if L < 0.5 else 1
            out += [(s16 * 0.25, "snare", "shime", (0.6 if s16 % 4 == 0 else 0.38 if s16 % 2 == 0 else 0.26) * min(1, 0.3 + L))
                    for s16 in range(0, 16, step) if L >= 0.3 or s16 % 4 == 0]
        # rim clicks and the festival gong on the off-beats
        if L >= 0.2:
            out += [(b + 0.5, "top", "kane", 0.45 * min(1, L + 0.2)) for b in range(4) if L >= 0.45 or b % 2]
            if rng.random() < 0.6:
                out += [(s16 * 0.25, "top", "kara", 0.5) for s16 in (7, 15)]
        if bar % 8 == 7 and L >= 0.4:   # 'doko doko' fill into the next phrase
            out = [o for o in out if o[0] < 3.0] + [(3 + k / 4, "perc", "chu", 0.6 + 0.1 * k) for k in range(4)]
    return out


def roll_bar(i: int, n: int, prog: dict, breaks: dict, rng) -> list[Hit]:
    """Bar i of an n-bar snare-roll build: 8ths, then 16ths, then 32nds, louder and rising in pitch,
    the way jungle DJs' favourite tunes wind up before the drop."""
    main, alt = prog.get("main", "hustle"), prog.get("alt", "roller")
    snares = [(b, j) for b in (main, alt) if b in BREAKS for j in range(32) if breaks[b].classes[j] == "S"]
    kicks = [(main, j) for j in range(32) if breaks[main].classes[j] == "K"]
    frac_bar = (i + 1) / n
    sub = 2 if frac_bar <= 0.34 and n > 2 else 4 if frac_bar < 1.0 or n == 1 else 8
    hits = [Hit(0.0, kicks[0][0], kicks[0][1], 0.25, vel=0.9)] if kicks else []
    for k in range(4 * sub):
        pos = k / sub
        if pos == 0 and kicks:
            continue
        prog_t = (i + pos / 4) / n
        s, j = snares[int(rng.integers(len(snares)))]
        if n == 1 and pos >= 3:   # one-bar fill: 32nds on the last beat
            pass
        hits.append(Hit(pos, s, j, 1 / sub, vel=float(0.35 + 0.6 * prog_t),
                        pitch=round(prog.get("roll_pitch", 4.0) * prog_t * 2) / 2, grid16=(sub == 4)))
    if n == 1:
        hits = [h for h in hits if h.beat < 3] + [Hit(3 + k / 8, *snares[int(rng.integers(len(snares)))], 1 / 8,
                                                         vel=0.75 + 0.03 * k, pitch=1.0, grid16=False) for k in range(8)]
    return hits
