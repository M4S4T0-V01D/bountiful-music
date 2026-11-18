"""Ramparts: atmospheric 1990s UK drum & bass on Castle Wars (Ian Taylor, Old School RuneScape, 2004) and breaks 1-3.

    python -I bountiful/ramparts.py              # sample the breaks and the tune, compose, render, master, validate
    python -I bountiful/ramparts.py --validate   # the checks only, on the last render

Standalone (no LMMS): the breaks are sampled with jungle174.sample_break, then chopped and sequenced here; the bass, pads,
Rhodes, rain and effects are synthesized in numpy; the mix goes through the engine's master().

Castle Wars runs at exactly 180 bpm (downbeat at 0.0 s). Played one semitone slower on a sampler it sits at 169.9 bpm
in E-flat minor, so the tune is never time-stretched. It is split into a harmonic layer (horns, choir, strings) and a
percussive one (taiko, kit) by median-filter HPSS; the harmonic layer carries the track, the taiko only shows up far
away in the intro and breakdown. The bass root and chord of every source bar are measured, so the sub, pads and Rhodes
follow the tune bar for bar.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy.ndimage import median_filter  # noqa: E402
from scipy.signal import istft, lfilter, stft  # noqa: E402

import jungle174 as J  # noqa: E402
from engine.render import master as master_chain  # noqa: E402

fx, ROOT, SR = J.fx, J.ROOT, J.SR
fx.set_rate(SR)
SHIFT = -1                                              # semitones: the sampler pitch of the tune
BPM = 180 * 2 ** (SHIFT / 12)                           # 169.897
J.BPM, J.CRUSH = BPM, 0.7                               # read at call time by J.sample_break
SLUG, TITLE, ARTIST = "ramparts", "Ramparts", "M4S4T0"
TRACK = ROOT / "tracks" / SLUG
CW_OGG = ROOT / "samples" / "osrs" / "castle_wars_src" / "castle_wars.ogg"   # oldschool.runescape.wiki/w/File:Castle_Wars.ogg
CACHE = ROOT / "samples" / "osrs" / "ramparts"
STEP = 60 / BPM / 4 * SR                                # one 16th in samples (float)
BAR = 16 * STEP
O = 2048                                                # the song's origin in the render (room for slice leads)
X = int(J.XF * SR)
BARS = 168
N = int(O + BARS * BAR + 7 * SR)
rng = np.random.default_rng(1990)
NAMES = "C C# D Eb E F F# G Ab A Bb B".split()

# out bar ranges (1-based, inclusive)
SECTIONS = [(1, 16, "Intro"), (17, 32, "Build"), (33, 72, "Drop 1"), (73, 88, "Breakdown"), (89, 104, "Build 2"),
            (105, 136, "Drop 2"), (137, 152, "Roll-out"), (153, 168, "Outro")]
# (out bar, Castle Wars bar, bars): which bars of the tune play where
RUNS = [(1, 3, 16), (17, 19, 16), (33, 35, 8), (41, 43, 16), (57, 59, 16), (73, 75, 32), (105, 139, 16), (121, 123, 16),
        (137, 107, 16), (153, 155, 16)]
SRC_OF = {o + k: s + k for o, s, n in RUNS for k in range(n)}


def at(g):
    """the render sample of global 16th step g"""
    return O + int(round(g * STEP))


def bar_s(b):
    return at(16 * (b - 1))


def section(b):
    return next(n for a, z, n in SECTIONS if a <= b <= z)


# ------------------------------------------------------------------ the tune
def castle_wars():
    """the tune slowed one semitone, split into harmonic and percussive layers; plus the measured chords per bar"""
    CACHE.mkdir(parents=True, exist_ok=True)
    fh, fp, fc = CACHE / "cw_harm_170.wav", CACHE / "cw_perc_170.wav", CACHE / "cw_chords.json"
    if fh.exists() and fp.exists() and fc.exists():
        return sf.read(str(fh), dtype="float32")[0], sf.read(str(fp), dtype="float32")[0], json.loads(fc.read_text())
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(CW_OGG), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).reshape(-1, 2)
    H, P = [], []
    kw = dict(fs=SR, nperseg=4096, noverlap=3072)
    for c in range(2):
        _, _, Z = stft(x[:, c], **kw)
        M = np.abs(Z)
        h, p = median_filter(M, size=(1, 17)), median_filter(M, size=(17, 1))
        mh = h ** 2 / (h ** 2 + p ** 2 + 1e-12)
        H.append(istft(Z * mh, **kw)[1][:len(x)])
        P.append(istft(Z * (1 - mh), **kw)[1][:len(x)])
    harm, perc = np.stack(H, 1).astype(np.float32), np.stack(P, 1).astype(np.float32)
    # the chords, measured at the original pitch on the harmonic layer: bass root below 170 Hz, the top three above
    m, bar0, win = harm.mean(1), 4 / 3 * SR, 16384
    f = np.fft.rfftfreq(win, 1 / SR)
    idx = lambda v: np.round(69 + 12 * np.log2(f[v] / 440)).astype(int) % 12
    chords = {}
    for b in range(1, 171):
        seg = m[int((b - 1) * bar0):int(b * bar0)]
        if len(seg) < win:
            break
        S = (np.abs(np.fft.rfft(np.lib.stride_tricks.sliding_window_view(seg, win)[::2048] * np.hanning(win), axis=1)) ** 2).mean(0)
        lo, hi = (f > 35) & (f < 170), (f > 170) & (f < 1500)
        cl = np.bincount(idx(lo), S[lo], 12)
        ch = np.bincount(idx(hi), S[hi], 12)
        root = int(np.argmax(cl))
        top = [int(i) for i in np.argsort(ch)[::-1][:3]]
        chords[b] = {"root": (root + SHIFT) % 12, "tones": sorted({(t + SHIFT) % 12 for t in [root] + top})}
    slow = lambda a: fx.resample(a, 2 ** (SHIFT / 12))
    harm, perc = slow(harm), slow(perc)
    sf.write(str(fh), harm, SR, subtype="FLOAT")
    sf.write(str(fp), perc, SR, subtype="FLOAT")
    fc.write_text(json.dumps(chords))
    return harm, perc, {str(k): v for k, v in chords.items()}


def lay_tune(src):
    """the tune's bars laid out by RUNS, 10 ms crossfades at the joins"""
    out = np.zeros((N, 2), np.float32)
    fade = int(0.01 * SR)
    for o, s, n in RUNS:
        a, ln = int(round((s - 1) * BAR)), int(round(n * BAR))
        seg = src[a:a + ln + fade].copy()
        seg = np.pad(seg, ((0, ln + fade - len(seg)), (0, 0)))
        seg[:fade] *= np.linspace(0, 1, fade)[:, None]
        seg[-fade:] *= np.linspace(1, 0, fade)[:, None]
        p = bar_s(o)
        out[p:p + len(seg)] += seg
    return out


# ------------------------------------------------------------------ the breaks
def breaks():
    takes = {}
    for p, src, lo, hi in (("s", J.BREAK_SRC, 120, 160), ("z", J.BREAK2_SRC, 105, 125), ("c", J.BREAK3_SRC, 95, 125)):
        take, F, hits, info = J.sample_break(src, lo, hi)
        takes[p] = (take, info)
        if p in "sz":   # the ride / top loop of the break, kick and snare attacks pulled down (as J.write_top)
            top = fx.hp(fx.hp(take, 3200), 3200) * 1.3
            env = np.ones(len(top), np.float32)
            shape = np.interp(np.arange(int(0.095 * SR)), [0, X, X + 0.04 * SR, X + 0.09 * SR], [1.0, 0.2, 0.3, 1.0])
            for h, v in hits:
                if v > 0.3 and h >= X:
                    seg = env[h - X:h - X + len(shape)]
                    np.minimum(seg, shape[:len(seg)], out=seg)
            takes["r" + p] = ((top * env[:, None]).astype(np.float32), info)
    return takes


def F(j):
    return X + int(round(j * STEP))


AMEN_KICKS = {0, 2, 10, 11, 16, 18, 26, 27, 32, 34, 42, 50, 51, 58}
AMEN_SNARES = {4, 12, 20, 28, 36, 44, 46, 52, 60}


def play(events, takes, maxlen=6):
    """events: (global step, take, slice, gain, semitones, reverse). Monophonic per call: each slice rings until the
    next event (at most maxlen steps), with the take's own crossfades at the joins, so in-order slices give the take back."""
    out = np.zeros((N, 2), np.float32)
    ev = sorted(events, key=lambda e: e[0])
    up = np.linspace(0, 1, X)[:, None]
    for k, (g, p, j, gain, semis, rev) in enumerate(ev):
        take = takes[p][0]
        nxt = ev[k + 1][0] if k + 1 < len(ev) else g + maxlen
        steps = min(nxt - g, maxlen)
        n = at(g + steps) - at(g) + X
        if rev:
            seg = take[F(j):F(j) + n][::-1].copy()
        elif semis:
            r = 2 ** (semis / 12)
            seg = fx.resample(take[F(j) - X:F(j) - X + int(n * r) + 4], r)[:n].copy()
        else:
            seg = take[F(j) - X:F(j) - X + n].copy()
        seg = np.pad(seg, ((0, n - len(seg)), (0, 0)))
        seg[:X] *= up
        seg[-X:] *= up[::-1]
        a = at(g) - X
        out[a:a + n] += seg * gain
    return out


def kit(b, k, prog, g=1.0, base=0, take="s"):
    """events for one bar from a 16-entry program of slice indices (None: let the last slice ring; -1: silence via a
    muted slice; (j, gain, semis, rev) for a treated hit). base offsets plain indices (the bar of the break)."""
    ev = []
    for i, e in enumerate(prog):
        if e is None:
            continue
        if isinstance(e, tuple):
            j, gg, semis, rev = e + (1.0, 0, False)[len(e) - 1:]
            ev.append((16 * (b - 1) + i, take, j, g * gg, semis, rev))
        elif e < 0:
            ev.append((16 * (b - 1) + i, take, 0, 0.0, 0, False))
        else:
            ev.append((16 * (b - 1) + i, take, base + e, g, 0, False))
    return ev


IN_ORDER = list(range(16))
# Amen edits (indices into the 64 slices; the classic moves: snare doubles, a bar's tail from another bar, rolls, gaps)
E1 = [0, 1, 2, 3, 4, 5, 6, 7, 0, 1, 10, 11, 12, 13, 12, (12, 0.7)]
E2 = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 4, 5, 12, 13, (4, 0.8), 12]
E3 = [0, 1, 2, 3, 4, 5, 40, 41, 42, 43, 44, 45, 46, 47, 28, 29]
E4 = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, -1, None, (12, 0.9, 0, True), None]                # gap, reversed snare
E5 = [0, 1, 34, 35, 4, 5, 6, 7, 16, 17, 26, 27, 12, 13, 46, 47]
ROLL = [0, 1, 2, 3, 4, 5, (4, 0.7), (4, 0.8), (12, 0.75), (12, 0.8), (4, 0.85), (12, 0.9),
        (4, 0.9, 1), (12, 0.95, 2), (4, 1.0, 3), (12, 1.0, 4)]
HALF = [0, 1, 2, 3, 2, 3, 0, 1, 4, 5, 6, 7, 26, 27, 14, 15]                                        # kick 0, snare on 8
GAPEND = [0, 1, 2, 3, 4, 5, 6, 7, -1, None, None, None, (12, 0.6), (12, 0.75), (4, 0.9), (12, 1.0)]
ORDER8 = [0, 16, 0, 32, 0, 16, 0, 48]                    # which Amen bar plays in an 8-bar phrase


def drums(takes):
    """the drum stems: amen, break2 (z), break3 (c), ride, kick (layer)"""
    am, z, c, ride, kicks = [], [], [], [], []
    for b in range(1, BARS + 1):
        sec, p8 = section(b), (b - 1) % 8
        base = ORDER8[p8]
        full = sec in ("Drop 1", "Drop 2") or (sec == "Roll-out" and b <= 144)
        prog = IN_ORDER
        if full:
            if b in (72, 136):
                prog = GAPEND
            elif b % 16 == 0:
                prog = ROLL if sec == "Drop 2" else E4
            elif p8 == 7:
                prog = E2 if sec == "Drop 1" else E5
            elif p8 == 3:
                prog = E1 if sec == "Drop 1" else E3
            elif sec == "Drop 2" and p8 == 5:
                prog = E5
            elif b == 152:
                prog = ROLL
        if full or (sec == "Build" and b >= 25):
            g = 1.0 if full else 0.8
            if b == 32:
                prog = GAPEND
            bb = 0 if isinstance(prog, list) and prog is not IN_ORDER else base
            am += kit(b, 0, prog, g, base=bb)
            for i, e in enumerate(prog):
                j = (bb + e) if isinstance(e, int) and e >= 0 else (e[0] if isinstance(e, tuple) and not e[3:4] == (True,) else None)
                if j is not None and j in AMEN_KICKS:
                    kicks.append((16 * (b - 1) + i, 1.0 if j % 16 in (0, 10) else 0.7))
        if sec == "Build 2" and b >= 97:
            prog = HALF if b < 103 else (ROLL if b == 104 else HALF)
            am += kit(b, 0, prog, 0.85)
            kicks += [(16 * (b - 1), 0.9), (16 * (b - 1) + 6, 0.6)] if b < 104 else []
        # break 2: the punch layer under the Amen (its kick and snares sit on the Amen's), main break in the roll-out
        if full and prog is not ROLL:
            zp = [e if (isinstance(e, int) and e >= 0 and e in (0, 1, 4, 5, 10, 11, 12, 13)) else None for e in IN_ORDER]
            if prog is GAPEND or prog is E4:
                zp = zp[:8] + [-1] + [None] * 7
            z += kit(b, 0, zp, 1.0, base=16 * (p8 % 4), take="z")
        if sec == "Roll-out" and b > 144:
            z += kit(b, 0, ROLL if b == 152 else IN_ORDER, 1.0, base=16 * (p8 % 4), take="z")
            kicks += [(16 * (b - 1), 0.9)]
        # break 3: percussion and cowbell, the whole loop
        cw_on = (sec == "Intro" and b >= 9) or sec == "Build" or (sec == "Drop 1" and 41 <= b <= 56) or sec == "Build 2" \
            or (sec == "Drop 2" and b >= 121) or sec == "Roll-out" or (sec == "Outro" and b <= 160)
        if cw_on:
            c += kit(b, 0, IN_ORDER, 1.0, base=16 * (p8 % 4), take="c")
        # the ride
        if (sec == "Build") or full or sec == "Roll-out" or (sec == "Build 2" and b >= 97) or (sec == "Outro" and b <= 160):
            ride += kit(b, 0, IN_ORDER, 1.0, base=16 * (p8 % 4), take="rs" if b % 32 < 16 else "rz")
    stems = {"amen": play(am, takes, 6), "break2": play(z, takes, 4), "break3": play(c, takes, 2), "ride": play(ride, takes, 2)}
    # the Amen's lows are its own; break 2 and 3 are thinned so the three don't pile up in the low mids
    stems["break2"] = fx.lp(fx.hp(stems["break2"], 70, 2), 9000, 2)
    stems["break3"] = fx.hp(stems["break3"], 380, 2)
    stems["ride"] = fx.hp(stems["ride"], 5000, 2)
    # build sweeps on the Amen: bars 25-32 and 97-104 open from a high-pass down to nothing
    hpc = np.full(N, 20.0, np.float32)
    for a, z_ in ((25, 33), (97, 105)):
        i0, i1 = bar_s(a), bar_s(z_)
        hpc[i0:i1] = np.geomspace(2200, 20, i1 - i0)
    stems["amen"] = fx.sweep(stems["amen"], "highpass", hpc)
    return stems, kicks


def synth_kick(kicks):
    out = np.zeros((N, 2), np.float32)
    n = int(0.32 * SR)
    t = np.arange(n) / SR
    f = 48 + 110 * np.exp(-t / 0.028)
    k = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.18) * np.minimum(1, t / 0.0015)
    k = fx.lp(k.astype(np.float32), 900)
    for g, v in kicks:
        a = at(g)
        out[a:a + n] += (k * v)[:, None]
    return out


# ------------------------------------------------------------------ bass, pads, keys
def chord(b, ch):
    s = SRC_OF.get(b)
    return ch[str(s)] if s and str(s) in ch else None


def sub_note(pc):
    """E-flat 1 to D 2 (MIDI 27-38): the root's lowest place there"""
    return 27 + (pc - 3) % 12


SUBPATS = [[(0, 10, 0), (10, 6, 0)], [(0, 7, 0), (7, 3, 12), (10, 6, 0)], [(0, 14, 0), (14, 2, 7)], [(0, 3, 0), (3, 7, 0), (11, 5, 0)]]


def bass(ch):
    """the sub (sine, a little second harmonic, 25 ms glides) and a reese an octave up for drop 2; per-sample pitch"""
    notes = []                                               # (start sample, end sample, midi, vel)
    for b in range(1, BARS + 1):
        sec, c = section(b), chord(b, ch)
        if c is None:
            continue
        r = sub_note(c["root"])
        if sec in ("Drop 1", "Drop 2", "Roll-out") or (sec == "Build" and b >= 25) or (sec == "Build 2" and b >= 97) or (sec == "Outro" and b <= 156):
            pat = SUBPATS[(b - 1) % 4] if sec != "Build" else SUBPATS[2]
            if b in (32, 72, 104, 136):
                pat = [(0, 8, 0)]
            for s, ln, iv in pat:
                notes.append((at(16 * (b - 1) + s), at(16 * (b - 1) + s + ln) - int(0.01 * SR), r + iv, 1.0 if s == 0 else 0.85))
        elif sec == "Breakdown" and (b - 73) % 4 == 0:       # swells: four-bar notes
            notes.append((bar_s(b), bar_s(b + 4) - int(0.3 * SR), r, 0.45))
    f = np.zeros(N, np.float64)
    amp = np.zeros(N, np.float64)
    last = 40.0
    for s, e, m, v in notes:
        f[s:e] = 440 * 2 ** ((m - 69) / 12)
        n = e - s
        env = np.minimum(1, np.arange(n) / (0.004 * SR)) * np.minimum(1, (n - np.arange(n)) / (0.03 * SR))
        if n > 2 * SR:                                       # the breakdown swells
            env = np.minimum(1, np.arange(n) / (1.2 * SR)) * np.minimum(1, (n - np.arange(n)) / (0.8 * SR))
        amp[s:e] = np.maximum(amp[s:e], env * v)
    for i in range(N):                                       # hold the last pitch through the gaps (so glides start right)
        if f[i]:
            break
        f[i] = last
    nz = f > 0
    idx = np.where(nz, np.arange(N), 0)
    np.maximum.accumulate(idx, out=idx)
    f = f[idx]
    a = np.exp(-1 / (0.025 * SR))
    lf = lfilter([1 - a], [1, -a], np.log(f), zi=[np.log(f[0]) * a])[0]
    f = np.exp(lf)
    ph = 2 * np.pi * np.cumsum(f) / SR
    sub = (np.sin(ph) + 0.12 * np.sin(2 * ph)) * amp
    sub = fx.saturate(sub.astype(np.float32), 1.2, 0.5)
    det = lambda r: 2 * ((np.cumsum(2 * f * r) / SR) % 1) - 1
    reese = (det(1.004) + det(0.996)) * amp
    reese_on = np.zeros(N, np.float32)
    reese_on[bar_s(105):bar_s(137)] = 1
    reese = fx.saturate(fx.lp(fx.hp((reese * reese_on).astype(np.float32), 90, 2), 650, 4), 2.0)
    return fx.stereo(sub), fx.width(fx.stereo(reese), 0.6), notes


def voicing(c, lo, hi):
    """the chord's tones placed in [lo, hi], root first"""
    out = []
    for pc in [c["root"]] + [t for t in c["tones"] if t != c["root"]]:
        m = lo + (pc - lo) % 12
        out.append(m if m <= hi else m - 12)
    return sorted(set(out))


def pad(ch):
    """warm detuned saws (three per note), slow attack, tied across bars where a note stays"""
    held = {}                                                # midi -> [start bar, end bar)
    spans = []
    for b in range(1, BARS + 2):
        c = chord(b, ch) if b <= BARS else None
        now = set(voicing(c, 50, 70)) if c else set()
        for m in list(held):
            if m not in now:
                spans.append((m, held.pop(m), b))
        for m in now:
            held.setdefault(m, b)
    out = np.zeros((N, 2), np.float32)
    rel = int(1.5 * SR)
    for m, b0, b1 in spans:
        s, e = bar_s(b0), bar_s(b1)
        n = e - s + rel
        t = np.arange(n)
        env = np.minimum(1, t / (0.9 * SR)) * np.where(t < e - s, 1.0, np.exp(-(t - (e - s)) / (0.45 * SR)))
        f0 = 440 * 2 ** ((m - 69) / 12)
        v = np.zeros((n, 2))
        for k, cents in enumerate((-9, 0, 9)):
            ph = rng.random() + np.arange(n) * f0 * 2 ** (cents / 1200) / SR
            sw = 2 * (ph % 1) - 1
            v[:, k % 2] += sw
            v[:, 1 - k % 2] += 0.5 * sw
        out[s:s + n] += (v * env[:, None] * 0.12).astype(np.float32)
    cut = np.full(N, 1400.0, np.float32)
    cut[bar_s(73):bar_s(105)] = 2300                         # brighter in the breakdown
    out = fx.sweep(out, "lowpass", cut)
    out = fx.chorus(out, 4.0, 0.25, 14.0, 0.5)
    return out


def rhodes(ch):
    """a small FM electric piano on the chords: bars of the intro, B section, breakdown and outro"""
    out = np.zeros((N, 2), np.float32)
    hits = [(0, 0.8), (6, 0.55), (10, 0.65)]
    hits2 = [(0, 0.75), (11, 0.6)]
    for b in range(1, BARS + 1):
        sec, c = section(b), chord(b, ch)
        on = (sec == "Intro" and b >= 9) or (sec == "Drop 1" and 41 <= b <= 56) or sec in ("Breakdown", "Build 2") or (sec == "Outro")
        if not c or not on:
            continue
        vs = [m for m in voicing(c, 58, 76) if m % 12 != c["root"] or m > 64][:4]
        for s, v in (hits if b % 2 else hits2):
            for k, m in enumerate(vs):
                a = at(16 * (b - 1) + s) + int(k * 0.006 * SR) + int(rng.integers(0, 120))
                n = int(1.4 * SR)
                t = np.arange(n) / SR
                f0 = 440 * 2 ** ((m - 69) / 12)
                idx = 1.6 * np.exp(-t / 0.35) * v + 0.15
                tone = np.sin(2 * np.pi * f0 * t + idx * np.sin(2 * np.pi * f0 * t)) * np.exp(-t / 1.1)
                tine = 0.12 * np.sin(2 * np.pi * 14 * f0 * t) * np.exp(-t / 0.03)
                note = (tone + tine) * v * np.minimum(1, t / 0.002) * 0.15
                out[a:a + n] += note[:N - a, None].astype(np.float32)
    out = fx.lp(out, 4500)
    out = fx.autopan(out, 4.6 * BPM / 170, 0.35)
    return fx.chorus(out, 2.5, 0.5, 10.0, 0.35)


# ------------------------------------------------------------------ atmosphere
def rain():
    n = N
    w = rng.standard_normal((n, 2)).astype(np.float32)
    hiss = fx.lp(fx.hp(w, 700, 2), 7000, 2) * 0.25
    drops = np.zeros((n, 2), np.float32)
    k = int(n / SR * 55)
    pos = rng.integers(0, n - 2000, k)
    for p, ch, g in zip(pos, rng.integers(0, 2, k), rng.random(k) ** 2):
        drops[p, ch] += g
    drops = fx.bp(drops, 1800, 6500, 2) * 6
    return (fx.lp(hiss + drops, 9000)).astype(np.float32)


def risers_and_booms():
    out = np.zeros((N, 2), np.float32)
    for into in (33, 105):
        i0, i1 = bar_s(into - 8), bar_s(into)
        m = i1 - i0
        noise = rng.standard_normal((m, 2)).astype(np.float32)
        r = fx.sweep(noise, "highpass", np.geomspace(250, 7000, m)) * (np.linspace(0, 1, m) ** 2.5)[:, None] * 0.5
        out[i0:i1] += r
        t = np.arange(int(1.6 * SR)) / SR
        boom = np.sin(2 * np.pi * np.cumsum(55 * np.exp(-t / 0.9) + 30) / SR) * np.exp(-t / 0.6) * 0.9
        out[i1:i1 + len(t)] += boom[:, None].astype(np.float32)
    return out


def envelope(points):
    """a gain curve (linear) from (bar, dB) points, linear in dB between them"""
    xs = [bar_s(b) for b, _ in points]
    return 10 ** (np.interp(np.arange(N), xs, [d for _, d in points]) / 20).astype(np.float32)


def active_db(x):
    m = x.mean(1) if x.ndim == 2 else x
    k = len(m) // 2205
    r = np.sqrt((m[:k * 2205].reshape(k, 2205) ** 2).mean(1))
    rd = 20 * np.log10(r + 1e-12)
    on = rd > rd.max() - 30
    return 10 * np.log10((r[on] ** 2).mean() + 1e-20) if on.any() else -120.0


LEVELS = {"amen": -17.0, "break2": -24.0, "break3": -29.0, "ride": -31.0, "kick": -27.0, "sub": -18.5, "reese": -29.0,
          "castle": -21.5, "taiko": -33.0, "pad": -28.0, "rhodes": -29.0, "rain": -42.0, "fx": -31.0}
MC = {"hp": 25, "mono_below": 120, "glue": {},
      "tape": {"drive": 1.6, "bias": 0.07, "bump_db": 1.5, "hf_db": -1.8, "lp_hz": 16000, "hiss_db": -72, "wow_ms": 0.07},
      "eq": [["peak", 60, 0.8, 0.8], ["peak", 400, -1.0, 1.0], ["peak", 1500, 0.6, 0.7], ["peak", 5000, -1.0, 1.0], ["highshelf", 10000, -0.8]],
      "multiband": {"freqs": [150, 5000], "bands": [{"threshold_rel": -3, "ratio": 2.2, "attack": 0.03, "release": 0.15},
                                                    {"threshold_rel": -3, "ratio": 1.6, "attack": 0.015, "release": 0.12},
                                                    {"threshold_rel": -3, "ratio": 1.8, "attack": 0.005, "release": 0.08}]},
      "bus_comp": {"threshold_rel": -3, "ratio": 2.0, "attack": 0.03, "release": 0.2, "sc_hp": 100},
      "target_lufs": -9.4, "ceiling": -1.0, "clip": 1.5, "true_peak": -1.0}


def render():
    TRACK.mkdir(parents=True, exist_ok=True)
    (TRACK / "stems").mkdir(exist_ok=True)
    (TRACK / "exports").mkdir(exist_ok=True)
    print("castle wars ...", flush=True)
    harm, perc, ch = castle_wars()
    print("breaks ...", flush=True)
    takes = breaks()
    stems, kicks = drums(takes)
    stems["kick"] = synth_kick(kicks)
    kick_t = [at(g) / SR for g, v in kicks if v >= 0.9]
    print("bass, pads, keys ...", flush=True)
    sub, reese, _ = bass(ch)
    stems["sub"], stems["reese"] = sub, reese
    stems["pad"], stems["rhodes"] = pad(ch), rhodes(ch)
    # the tune: harmonic layer above 140 Hz (the sub is ours), opening up over the intro, darker under the drops
    cw = fx.hp(lay_tune(harm), 140, 2)
    cut = np.interp(np.arange(N), [bar_s(b) for b in (1, 16, 17, 33, 73, 89, 105, 153, 169)],
                    [500, 3500, 4200, 9000, 6000, 9000, 11000, 6000, 1500]).astype(np.float32)
    stems["castle"] = fx.wow(fx.sweep(cw, "lowpass", cut), 0.25, 0.4)
    taiko = fx.lp(fx.hp(lay_tune(perc), 60, 2), 900, 2)
    tk = np.zeros(N, np.float32)
    tk[bar_s(1):bar_s(33)] = 1
    tk[bar_s(73):bar_s(97)] = 1
    stems["taiko"] = taiko * tk[:, None]
    stems["rain"], stems["fx"] = rain(), risers_and_booms()
    # rides: per-stem gain curves (dB) by bar
    rides = {"castle": [(1, -2), (17, 0), (33, -1.5), (72, -1.5), (73, -6), (96, -4), (104, 0), (105, -1), (152, -1), (153, 1), (166, 0), (169, -30)],
             "pad": [(1, 2), (32, 0), (33, -4), (72, -4), (73, -5), (96, -3), (104, 0), (105, -5), (152, -5), (153, 1), (169, -20)],
             "rhodes": [(1, 0), (73, -2), (105, 0), (153, 0), (169, -12)],
             "rain": [(1, 3), (32, 0), (33, -6), (72, -6), (73, 2), (104, 0), (105, -8), (152, -6), (153, 3), (169, -6)],
             "taiko": [(1, -4), (16, 0), (32, 2), (73, -4), (96, 0)],
             "break3": [(1, -8), (16, -3), (17, -2), (40, 0)],
             "ride": [(17, -6), (32, 0)]}
    gains = {}
    for k, x in stems.items():
        if k in rides:
            x = x * envelope(rides[k])[:, None]
        g = LEVELS[k] - active_db(x)
        gains[k] = round(float(g), 2)
        stems[k] = (x * fx.db(g)).astype(np.float32)
    # sends: a long hall for the tune, pads, keys and taiko; a dotted echo on the keys; a short room on the breaks
    hall = fx.reverb_ir(4.2, 0.03, 0.55)
    far = fx.reverb_ir(5.5, 0.06, 0.7, seed=11)
    room = fx.reverb_ir(0.7, 0.008, 0.6, seed=3)
    echo = fx.delay_ir(60 / BPM, 0.75, 0.4, 6, 2800)
    stems["castle"] = stems["castle"] + 0.35 * fx.convolve(stems["castle"], hall)
    stems["pad"] = stems["pad"] + 0.5 * fx.convolve(stems["pad"], hall)
    stems["rhodes"] = stems["rhodes"] + 0.35 * fx.convolve(stems["rhodes"], hall) + 0.25 * fx.convolve(stems["rhodes"], echo)
    stems["taiko"] = 0.25 * stems["taiko"] + 1.2 * fx.convolve(fx.lp(stems["taiko"], 700), far)
    stems["amen"] = stems["amen"] + 0.12 * fx.convolve(fx.hp(stems["amen"], 300), room)
    # the sidechain: the tune, pads and reese breathe with the kicks
    d = fx.duck(N, kick_t, 0.3, 0.14)[:, None]
    for k in ("castle", "pad", "reese"):
        stems[k] = stems[k] * d
    stems["sub"] = stems["sub"] * fx.duck(N, kick_t, 0.45, 0.06)[:, None]
    end = bar_s(BARS + 1) + int(6 * SR)
    for k in stems:
        stems[k] = stems[k][:end]
        sf.write(str(TRACK / "stems" / f"{k}.wav"), stems[k], SR, subtype="PCM_24")
    pre = sum(stems.values())
    pre *= 0.5 / (np.abs(pre).max() + 1e-9)
    sf.write(str(TRACK / "exports" / f"{SLUG}_premaster.wav"), pre, SR, subtype="FLOAT")
    print("master ...", flush=True)
    y, info = master_chain(pre.astype(np.float32), {"master": MC})
    fo = int(4 * SR)
    y[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 2
    wav = TRACK / "exports" / f"{SLUG}.wav"
    sf.write(str(wav), y, SR, subtype="PCM_24")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "320k",
                    "-metadata", f"title={TITLE}", "-metadata", f"artist={ARTIST}", "-metadata", "genre=Drum & Bass",
                    "-metadata", "date=2026", "-metadata", "comment=Samples Castle Wars by Ian Taylor (Jagex, Old School RuneScape)",
                    str(TRACK / "exports" / f"{SLUG}.mp3")], check=True)
    meta = {"bpm": BPM, "bars": BARS, "seconds": len(y) / SR, "key": "Eb minor (Castle Wars E minor, -1 st)",
            "sections": SECTIONS, "runs": RUNS, "stem_gain_db": gains, "master": info,
            "breaks": {p: takes[p][1] for p in "szc"}}
    (TRACK / "exports" / "render_info.json").write_text(json.dumps(meta, indent=1, default=float))
    print("Master:", {k: round(v, 2) for k, v in info.items() if isinstance(v, float)})


# ------------------------------------------------------------------ checks
def validate():
    import pyloudnorm as pyln
    y, _ = sf.read(str(TRACK / "exports" / f"{SLUG}.wav"), dtype="float32")
    st = {p.stem: sf.read(str(p), dtype="float32")[0] for p in (TRACK / "stems").glob("*.wav")}
    ch = json.loads((CACHE / "cw_chords.json").read_text())
    meter = pyln.Meter(SR)
    seg = lambda x, a, b: x[bar_s(a):bar_s(b + 1)]
    lufs = lambda x: meter.integrated_loudness(x.astype(np.float64))
    res = []
    L = lufs(y)
    from scipy.signal import resample_poly
    tp = 20 * np.log10(np.abs(resample_poly(y, 4, 1, axis=0)).max() + 1e-12)
    res.append(("master: integrated loudness -10 +/- 0.5 LUFS", abs(L + 10) <= 0.5, f"{L:.1f} LUFS"))
    res.append(("master: true peak below -0.5 dBTP, no clipping", tp < -0.5 and (np.abs(y) >= 0.999).sum() == 0, f"{tp:.2f} dBTP"))
    res.append(("length 3:30 to 4:30", 210 <= len(y) / SR <= 270, f"{len(y) / SR / 60:.0f}:{len(y) / SR % 60:04.1f}"))
    # every break is heard where it plays
    lv = {k: active_db(seg(st[k], a, b)) for k, a, b in (("amen", 33, 72), ("break2", 145, 151), ("break3", 41, 56))}
    res.append(("all three breaks heard (Amen drop 1, break 2 roll-out, break 3 B section) above -40 dB", all(v > -40 for v in lv.values()),
                {k: round(v, 1) for k, v in lv.items()}))
    # the Amen sits on the 169.9 grid
    on = np.array([s for s, v in J.onsets(seg(st["amen"], 33, 72).mean(1), rel=0.05)])
    grid = [at(16 * (b - 33) + i) - O for b in range(33, 72) if b % 8 for i in (0, 4, 12)]
    err = [np.abs(on - g).min() / SR * 1000 for g in grid]
    ok = np.mean([e < 15 for e in err])
    res.append(("Amen kick/snare hits within 15 ms of the 169.9 bpm grid, drummer feel kept (>= 90% of beats 1, 2, 4)", ok >= 0.9, f"{ok * 100:.0f}% of {len(err)}"))
    # the tune is heard through the whole song
    cwb = [active_db(seg(st["castle"], b, b)) for b in range(1, 165)]
    hear = np.mean([v > -45 for v in cwb])
    res.append(("Castle Wars heard in >= 95% of bars 1-164", hear >= 0.95, f"{hear * 100:.0f}%"))
    # the sub follows the tune's measured roots
    good = tot = 0
    for b in list(range(33, 72)) + list(range(105, 136)):
        x = seg(st["sub"], b, b)[:int(0.4 * BAR)].mean(1)
        if np.abs(x).max() < 1e-3:
            continue
        S = np.abs(np.fft.rfft(x * np.hanning(len(x)), 1 << 17))
        f = np.fft.rfftfreq(1 << 17, 1 / SR)
        v = (f > 25) & (f < 80)
        pc = int(round(69 + 12 * np.log2(f[v][np.argmax(S[v])] / 440))) % 12
        tot += 1
        good += pc == ch[str(SRC_OF[b])]["root"]
    res.append(("sub root = Castle Wars bass root (drops, >= 90% of bars)", tot and good / tot >= 0.9, f"{good}/{tot}"))
    # shape: the breakdown well under the drops
    bd, d1, d2 = lufs(seg(y, 73, 88)), lufs(seg(y, 33, 72)), lufs(seg(y, 105, 136))
    res.append(("breakdown at least 3 LU under both drops", d1 - bd >= 3 and d2 - bd >= 3, f"bd {bd:.1f}, d1 {d1:.1f}, d2 {d2:.1f}"))
    res.append(("drop 2 at least as loud as drop 1 (-0.5 LU)", d2 >= d1 - 0.5, f"{d2 - d1:+.1f} LU"))
    # band balance in the drops: sub weight without swamping the mids
    x = seg(y, 33, 72).mean(1)
    band = lambda lo, hi: 10 * np.log10((fx.bp(x, lo, hi, 4) ** 2).mean() + 1e-20)
    gap = band(30, 120) - band(300, 2000)
    res.append(("drops: lows 0-9 dB over the mids", 0 <= gap <= 9, f"{gap:+.1f} dB"))
    lines = [f"# {TITLE} - validation", ""] + [f"- [{'x' if ok else ' '}] {n}: {d}" for n, ok, d in res]
    passed = sum(bool(ok) for _, ok, _ in res)
    lines += ["", f"{passed}/{len(res)} checks pass"]
    (TRACK / "validation.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return passed == len(res)


if __name__ == "__main__":
    if "--validate" not in sys.argv:
        render()
    validate()
