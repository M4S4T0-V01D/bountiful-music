#!/usr/bin/env python3
"""'Haze Theory': a classic 1992-95 atmospheric jungle track at 150 bpm, built to a written brief with the existing
pipeline (Bountiful Music composition, break_maker, LMMS instruments, render_midi mix/master, lmms_tracks recipe).

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/jungle174.py            # break + song
    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/jungle174.py --validate # checks only

The breaks: break 1 is the real four-bar break in breaks/break.mp3 (about 137 bpm), break 2 the one in breaks/break2.wav
(about 114 bpm). For each, tempo and downbeats are fitted from the onsets, it is sped up to 150 on a sampler (one constant
ratio, so it pitches up: about +1.5 and +4.7 semitones), 12-bit / 26 kHz, then re-laid on the grid as one continuous take:
each source 16th crossfades onto its step 5 ms early, in the tail of the hit before. Slices are cut from that take on the
grid with the same 5 ms lead (the render's preroll), so slices in order give back the take with no seam and an edit
crossfades instead of clicking; each slice rings until the next strong hit and chokes the one before.
A high-passed copy gives a hats take and a continuous ride/top loop under the chops; kick and snare one-shots come from
the takes too. --synthetic-break uses the old performed blueprint instead (kick 1, 7, 12 / snare 5, 13 / ghosts).
Breaks A (main), B (rolling) and C (transition) are built from break 1; T and T2 from break 2, which also runs
quietly under break 1 (TL) in the grooves and the drop. Mastered with tape, EQ, three-band and bus compression, clip and limit.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import break_maker as BM  # noqa: E402
import lmms_tracks as LT  # noqa: E402
import producer as PR  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# the tempo the breaks are sampled to: 150 for Haze Theory; a track that imports this module may set BOUNTIFUL_BREAK_BPM
# first (Night Signal: 138), and gets its own sample folder (samples/breaks/haze<bpm>-real), so tracks never overwrite each other
BPM, PLAY = int(os.environ.get("BOUNTIFUL_BREAK_BPM", 150)), 145
# how much of the 12-bit sampler grit the breaks keep (1 = all of it; Tidewater: 0.6, the crushed take blended with the clean one)
CRUSH = float(os.environ.get("BOUNTIFUL_BREAK_CRUSH", 1.0))
BREAK_SRC = ROOT / "breaks" / "break.mp3"          # a real four-bar break; --synthetic-break uses the performed blueprint instead
BREAK2_SRC = ROOT / "breaks" / "break2.wav"        # the second break: layered under the first, and the main break in places
BREAK3_SRC = ROOT / "breaks" / "break3.wav"        # the third break: a cowbell break near 108 bpm (slices c00..c63)
REAL = BREAK_SRC.exists() and "--synthetic-break" not in sys.argv
OUT = ROOT / "samples" / "breaks" / (f"haze{BPM}-real" if REAL else f"haze{BPM}")
SR = 44100
fx = BM.fx

# ------------------------------------------------------------------ the blueprint (0-based 16th steps)
HATS = (0, 2, 3, 4, 6, 8, 9, 10, 12, 14, 15)
BLUE = {"kick": [[(0, 1.0), (6, 0.9), (11, 0.92)]] * 4,
        "snare": [[(4, 0.95), (12, 0.97)]] * 4,
        "ghost": [[(2, 0.32), (7, 0.27), (9, 0.3), (13, 0.35)]] * 4,
        "hat": [[(s, 0.52 if s % 4 == 0 else 0.42 if s % 2 == 0 else 0.3) for s in HATS]] * 4}


def onsets(m, rel=0.06):
    """Attacks in a mono signal: peaks of the positive energy flux (2 ms frames), merged within 24 ms, each refined to
    the first sample above a quarter of the hit's peak. Returns [(sample, strength 0..1)]."""
    w = int(0.002 * SR)
    k = len(m) // w
    e = np.sqrt((m[:k * w].reshape(k, w) ** 2).mean(1))
    fl = np.maximum(0, np.diff(e, prepend=0))
    th = fl.max() * rel
    pk = []
    for i in range(1, len(fl) - 1):
        if fl[i] > th and fl[i] >= fl[i - 1] and fl[i] > fl[i + 1]:
            if pk and i - pk[-1][0] < 12:
                pk[-1] = (pk[-1][0], max(pk[-1][1], fl[i]))
            else:
                pk.append((i, fl[i]))
    out = []
    for i, s in pk:
        a = max(0, (i - 3) * w)
        seg = np.abs(m[a:(i + 6) * w])
        out.append((a + int(np.argmax(seg > 0.25 * seg.max())), float(s / fl.max())))
    return out


XF = 220 / SR                                                 # slice lead / crossfade (s): the render's "preroll_ms"


def sample_break(path, bpm_lo, bpm_hi):
    """A real four-bar break as a jungle producer would sample it: sped up to BPM on a sampler (one ratio, so pitch
    rises with tempo), a 12-bit 26 kHz stage, then re-laid onto the grid as one continuous take: each 16th of the source
    (its own bar lines plus sixteenths of that bar, so the drummer's bar-to-bar drift is gone but the feel inside a bar
    stays) is crossfaded onto its grid step just before the step, in the tail of the hit before. Slices cut from that
    take on the grid and played in order give back the take with no seam. Returns (take, step position, hits, info)."""
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if sr != SR:
        x = fx.resample(x, sr / SR)
    reps = 1
    if len(x) < 3 * 4 * 60 / bpm_hi * SR:                    # a one- or two-bar loop: play it round until there are four bars and a bit
        reps = int(np.ceil(5 * 4 * 60 / bpm_lo * SR / len(x)))
        x = np.tile(x, (reps, 1))
    m = x.mean(1)
    on = onsets(m)
    d0 = on[0][0]
    # the bar length: the tempo whose 16th grid (from the first hit) best explains the attacks
    w = int(0.002 * SR)
    fl = np.zeros(len(m) // w)
    for s, v in on:
        fl[min(len(fl) - 1, s // w)] += v
    t = np.arange(len(fl)) * w
    best = max(np.arange(bpm_lo, bpm_hi, 0.05), key=lambda bpm: (fl * np.exp(-((((t - d0) / (60 / bpm / 4 * SR) + 0.5) % 1 - 0.5)
                                                                             * 60 / bpm / 4 / 0.008) ** 2)).sum())
    bar = 4 * 60 / best * SR
    D = [d0]                                                 # each downbeat: the first strong attack near the fitted bar line
    for b in range(1, 4):
        c = [o for o in on if abs(o[0] - (D[-1] + bar)) < 0.06 * SR]
        D.append(min(o[0] for o in c if o[1] >= 0.4 * max(v for _, v in c)) if c else int(D[-1] + bar))
    # the loop end (no downbeat follows bar 4): the bar length that puts bar 4's attacks on its 16th grid
    L3 = D[3] - D[2]
    b4 = [(s - D[3], v) for s, v in on if D[3] + 0.01 * SR < s < D[3] + 1.02 * L3]
    D.append(D[3] + max(np.linspace(0.94 * L3, 1.04 * L3, 201), key=lambda L: sum(
        v * np.exp(-((((s / (L / 16)) + 0.5) % 1 - 0.5) * L / 16 / SR / 0.008) ** 2) for s, v in b4)))
    pre, X = int(0.008 * SR), int(XF * SR)
    n1 = 60 / BPM / 4 * SR
    ratio = (D[4] - D[0]) / (64 * n1)
    xl = fx.lp(x, SR / 2 / ratio * 0.9, 4)                   # anti-alias before the speed-up
    src = D[0] + (np.arange(int((len(m) - D[0]) / ratio) + pre, dtype=np.float64) - pre) * ratio
    fast = np.stack([np.interp(src, np.arange(len(m)), xl[:, c]) for c in range(x.shape[1])], 1).astype(np.float32)
    fast = fx.hp(fast, 30)
    if CRUSH < 1:   # blended with the same sampler at 24 bits: identical filters and hold, so in phase; only the 12-bit grit is reduced
        fast = CRUSH * fx.crush(fast, bits=12, rate=26040, filtered=True) + (1 - CRUSH) * fx.crush(fast, bits=24, rate=26040, filtered=True)
    else:
        fast = fx.crush(fast, bits=12, rate=26040, filtered=True)
    g = lambda i: pre + (D[min(i // 16, 4)] + (i % 16 if i < 64 else 0) * (D[min(i // 16 + 1, 4)] - D[min(i // 16, 4)]) / 16 - D[0]) / ratio
    F = lambda i: X + int(round(i * n1))                     # step i in the take
    tail = int(0.6 * SR)
    take = np.zeros((F(64) + tail, x.shape[1]), np.float32)
    up, down = np.linspace(0, 1, X)[:, None], np.linspace(1, 0, X)[:, None]
    for i in range(64):
        a = int(round(g(i))) - X
        n = F(i + 1) - F(i) + X + (tail if i == 63 else 0)
        seg = fast[a:a + n].copy()
        seg = np.pad(seg, ((0, n - len(seg)), (0, 0)))
        if i:
            seg[:X] *= up
        if i < 63:
            seg[-X:] *= down
        take[F(i) - X:F(i) - X + n] += seg
    take = (take / (np.abs(take).max() + 1e-9) * 0.89).astype(np.float32)
    hits = onsets(take.mean(1), rel=0.04)
    info = {"source": str(path), "source_bpm": round(float(best), 2), "downbeats_s": [round(float(d) / SR, 3) for d in D],
            "speed_ratio": round(float(ratio), 4), "pitch_semitones": round(float(12 * np.log2(ratio)), 2),
            "bar_ratios": [round((D[b + 1] - D[b]) / (16 * n1), 4) for b in range(4)], "looped": reps}
    return take, F, hits, info


def write_slices(take, F, hits, prefix, info, extras=True):
    """16th slices on the grid, each from its step's lead to the step before the next strong hit (at most 4 steps),
    so a slice rings through soft hits and an edit's gap decays instead of playing the next kick; the fade-out sits
    exactly where the next slice's lead fades in."""
    X = int(XF * SR)
    up = lambda n: np.linspace(0, 1, n)[:, None]

    def write(name, s, fade_out=XF):
        s = s.copy()
        f = min(int(fade_out * SR), len(s) // 3)
        s[:X] *= up(X)
        s[-f:] *= up(f)[::-1]
        sf.write(str(OUT / f"{name}.wav"), s.astype(np.float32), SR, subtype="PCM_24")

    strong = [False] * 65                                     # steps that hold a strong attack (from just before the step on)
    for h, v in hits:
        if v > 0.3:
            j = max(0, int((h - X + 0.003 * SR) // (F(1) - F(0))))
            if j < 64 and F(j) - X - 0.003 * SR <= h:
                strong[j] = True
    ends = []
    for i in range(64):
        j = next((j for j in range(i + 1, min(i + 5, 65)) if strong[j] or j == 64), min(i + 4, 64))
        ends.append(j)
        write(f"{prefix}{i:02d}", take[F(i) - X:F(j)])
    sf.write(str(OUT / f"{prefix}_take.wav"), take[X:F(64)], SR, subtype="PCM_24")
    info = {**info, "strong_steps": [i for i in range(64) if strong[i]], "slice_steps": [e - i for i, e in enumerate(ends)]}
    (OUT / f"{prefix}_info.json").write_text(json.dumps(info, indent=1))
    print(f"break {prefix}: {info}")
    return write, strong


def write_top(take, F, hits, write, prefix):
    """the ride / top loop: the take above 3 kHz, bar for bar under the same bar of slices (it lines up sample for
    sample); kick and snare attacks pulled down, leaving the wash"""
    X = int(XF * SR)
    top = fx.hp(fx.hp(take, 3200), 3200) * 1.3
    env = np.ones(len(top), np.float32)
    shape = np.interp(np.arange(int(0.095 * SR)), [0, X, X + 0.04 * SR, X + 0.09 * SR], [1.0, 0.2, 0.3, 1.0])
    for h, v in hits:
        if v > 0.3 and h >= X:
            seg = env[h - X:h - X + len(shape)]
            np.minimum(seg, shape[:len(seg)], out=seg)
    top *= env[:, None]
    for k in range(4):
        write(f"{prefix}{k}", top[F(16 * k) - X:F(16 * k + 16)])


def build_real_break():
    """Break 1 (breaks/break.mp3, the Amen) and break 2 (breaks/break2.wav, a funk break near 114 bpm), both re-laid
    on the 150 grid; slices, 32nds, the hats take, the ride/top loop and one-shots are all cut from the takes."""
    OUT.mkdir(parents=True, exist_ok=True)
    X = int(XF * SR)
    take, F, hits, info = sample_break(BREAK_SRC, 120, 160)
    write, strong = write_slices(take, F, hits, "s", info)
    for i in (0, 4, 6, 11, 12):                               # 32nd slices: the front of a hit
        write(f"t{i:02d}", take[F(i) - X:F(i) + int(0.5 * (F(1) - F(0)))], 0.006)
    hat = fx.hp(fx.hp(take, 6500), 6500) * 1.6                # the hats take: the break's top end, one bar
    for i in range(16):
        write(f"h{i:02d}", hat[F(i) - X:F(i + 1)])
    write_top(take, F, hits, write, "rd")
    write("kick1", take[F(0) - X:min(F(0) + int(0.3 * SR), F(2))], 0.02)
    write("snr1", take[F(4) - X:F(4) + int(0.3 * SR)], 0.03)
    write("gh1", fx.lp(take[F(4) - X:F(4) + int(0.12 * SR)], 3500) * 0.8, 0.04)
    if BREAK2_SRC.exists():
        take2, F2, hits2, info2 = sample_break(BREAK2_SRC, 105, 125)
        write2, _ = write_slices(take2, F2, hits2, "z", info2)
        for i in (4, 12):
            write2(f"zt{i:02d}", take2[F2(i) - X:F2(i) + int(0.5 * (F2(1) - F2(0)))], 0.006)
        write_top(take2, F2, hits2, write2, "rz")
        write2("zk1", take2[F2(0) - X:F2(0) + int(0.25 * SR)], 0.02)
        write2("zs1", take2[F2(4) - X:F2(4) + int(0.3 * SR)], 0.03)
    if BREAK3_SRC.exists():
        take3, F3, hits3, info3 = sample_break(BREAK3_SRC, 95, 125)
        write_slices(take3, F3, hits3, "c", info3)


def build_break():
    if REAL:
        return build_real_break()
    return build_synth_break()


def build_synth_break():
    """Record the blueprint, speed it up, slice it; returns nothing (files in OUT)."""
    OUT.mkdir(parents=True, exist_ok=True)
    bus, step = BM.perform(PLAY, seed=174, pattern=BLUE, ride_on=False)
    full = BM.record(bus)
    hats_bus, _ = BM.perform(PLAY, seed=174, pattern=BLUE, ride_on=False, mute=("kick", "snare"))
    hats = BM.record(hats_bus) * 0.6
    sf.write(str(OUT / f"break_{PLAY}.wav"), full[: int(64 * step * SR)], SR, subtype="PCM_24")
    fast, fh = BM.speed(full, PLAY, BPM), BM.speed(hats, PLAY, BPM)
    st = 60 / BPM / 4
    n1 = st * SR
    fade = int(0.0015 * SR)
    sf.write(str(OUT / f"break_{BPM}.wav"), fast[: int(round(64 * n1))], SR, subtype="PCM_24")

    def cut(src, a, b, name, fade_in=True):
        s = src[int(round(a)): int(round(b)) + fade].copy()
        s[-fade:] *= np.linspace(1, 0, fade)[:, None]
        if fade_in:
            s[:fade] *= np.linspace(0, 1, fade)[:, None]
        sf.write(str(OUT / f"{name}.wav"), s.astype(np.float32), SR, subtype="PCM_24")

    for i in range(64):
        cut(fast, i * n1, (i + 1) * n1, f"s{i:02d}", fade_in=i > 0)
    for i in (0, 4, 6, 11, 12):                     # 32nd slices: the first half of a hit
        cut(fast, i * n1, (i + 0.5) * n1, f"t{i:02d}")
    for i in range(16):                             # the hats-only take, one bar
        cut(fh, i * n1, (i + 1) * n1, f"h{i:02d}", fade_in=i > 0)
    ride_bus, _ = BM.perform(PLAY, seed=175, pattern={"kick": [[]]}, ride_on=True, mute=("kick", "snare"))
    fr = BM.speed(BM.record(ride_bus) * 0.7, PLAY, BPM)
    for k in range(4):                              # the ride-only take, whole bars
        cut(fr, 16 * k * n1, 16 * (k + 1) * n1, f"rd{k}", fade_in=k > 0)
    for name, pat in (("kick1", {"kick": [[(0, 1.0)]]}), ("snr1", {"snare": [[(0, 1.0)]]}), ("gh1", {"ghost": [[(0, 1.0)]]})):
        b, _ = BM.perform(PLAY, seed=7, pattern=pat, bars=1, ride_on=False)
        x = BM.speed(BM.record(b), PLAY, BPM)
        on = int(np.argmax(np.abs(x).max(1) > 0.02))
        cut(x[max(0, on - 32):], 0, 0.3 * SR, name)
    print(f"break: {OUT} ({len(list(OUT.glob('*.wav')))} files)")


SOUNDS = ([f"s{i:02d}" for i in range(64)] + [f"t{i:02d}" for i in (0, 4, 6, 11, 12)] + [f"h{i:02d}" for i in range(16)]
          + ["kick1", "snr1", "gh1", "kreinf", "snlay", "s04u", "s12d", "s09u", "s07d", "s12u", "rd0", "rd1", "rd2", "rd3"]
          + [f"z{i:02d}" for i in range(64)] + ["zt04", "zt12", "zk1", "zs1", "z04u", "rz0", "rz1", "rz2", "rz3"]
          + [f"c{i:02d}" for i in range(64)])   # 236 sounds: notes 20..255, the most one extra channel holds (key_of)
NOTES = {s: 20 + k for k, s in enumerate(SOUNDS)}
PR.GM.update(NOTES)
# 172 sounds run past MIDI's 127: from z08 on they are written on channel DRUM_HI_CH as note - 128 (build.write_midi)
key_of = lambda n: str(n) if n < 128 else f"{LT.B.DRUM_HI_CH}:{n - 128}"   # the kit map key of a note
_BY_KEY = {key_of(n): s for s, n in NOTES.items()}
sound_of = lambda nt: _BY_KEY.get(f"{nt['ch']}:{nt['pitch']}", _BY_KEY.get(str(nt["pitch"]), nt["pitch"]))   # a read_midi note's sound
PITCHED = {"s04u": ("s04", 1.5), "s12d": ("s12", -1.0), "s09u": ("s09", 2.0), "s07d": ("s07", -2.0), "s12u": ("s12", 1.5), "z04u": ("z04", 1.5)}


def kit():
    """Every sound cut from a take carries its 5 ms lead (preroll): the lead sounds before the step, under the fade-out
    of the slice it replaces, so slices played in order give back the take and an edit crossfades instead of clicking."""
    snd = {}
    for s in SOUNDS:
        two = s[0] == "z" or s.startswith("rz")
        lead = {"preroll_ms": XF * 1000, "detune_cents": 0}
        choke = {"choke": "brk2" if two else "brk"}
        if s in PITCHED:
            src, semis = PITCHED[s]
            snd[s] = {"samples": [str(OUT / f"{src}.wav")], "pitch": semis, "stem": "breakfx", **lead, **choke}
        elif s[0] == "t" or s[:2] == "zt":
            snd[s] = {"samples": [str(OUT / f"{s}.wav")], "stem": "breakfx", **lead, **choke}
        elif s[0] == "c" and s[1:].isdigit():
            snd[s] = {"samples": [str(OUT / f"{s}.wav")], "stem": "break3", **lead, "choke": "brk3"}
        elif s[0] in "shz" and s[1:].isdigit():
            snd[s] = {"samples": [str(OUT / f"{s}.wav")], "stem": "break2" if two else "break", **lead, **(choke if s[0] != "h" else {})}
        elif s[:2] in ("rd", "rz"):
            snd[s] = {"samples": [str(OUT / f"{s}.wav")], "stem": "ride", **lead}
        elif s in ("kick1", "snr1", "gh1", "zk1", "zs1"):
            snd[s] = {"samples": [str(OUT / f"{s}.wav")], "stem": "break2" if two else "break", **lead, "detune_cents": 4}
    snd["kreinf"] = {"samples": ["/usr/share/lmms/samples/drums/bassdrum01.ogg"], "lp": 160, "stem": "kick", "detune_cents": 0}
    snd["snlay"] = {"samples": ["/usr/share/lmms/samples/drums/snare01.ogg"], "hp": 1500, "stem": "snlay", "detune_cents": 6}
    return {"map": {key_of(NOTES[s]): s for s in snd}, "sounds": snd,
            "stems": {"break": {"hp": 30, "eq": [["peak", 110, 1.5, 0.9], ["highshelf", 8000, -2.0]], "sends": {"room": 0.08}, "gain_db": -2.0},
                      # the second break: its own low end thinned so it sits under the Amen's kicks when layered
                      "break2": {"hp": 40, "eq": [["lowshelf", 120, -2.0], ["peak", 2500, 1.0, 1.0], ["highshelf", 8000, -2.5]], "sends": {"room": 0.08}, "gain_db": -3.0},
                      # the cowbell break: its kick thinned a little, the bells left bright
                      "break3": {"hp": 40, "eq": [["lowshelf", 120, -1.5], ["highshelf", 8000, -2.0]], "sends": {"room": 0.08}, "gain_db": -3.0},
                      "breakfx": {"hp": 60, "sends": {"slap": 0.3, "room": 0.1}, "gain_db": -3.0},
                      "kick": {"hp": 30, "mono": True, "gain_db": -14.0},
                      "ride": {"hp": 500, "eq": [["highshelf", 9000, -2.0]], "sends": {"room": 0.12}, "gain_db": -13.0 if REAL else -11.0},
                      "snlay": {"hp": 1500, "sends": {"room": 0.15}, "gain_db": -5.0 if REAL else 0.0}}}


# ------------------------------------------------------------------ breaks A, B, C, built from slices
def base(b, steps=range(16)):
    return [[i, 1.0, f"s{16 * b + i:02d}"] for i in steps]


def swap(bar, step, entry):
    return [e for e in bar if e[0] != step] + ([entry] if entry else [])


A = {"a": base(0),
     "b": swap(base(1), 14, [14, 0.9, "s11"]),                                   # a kick slice moved into the second half
     "c": base(2),
     "d": swap(swap(base(3), 15, [15, 0.55, "t12"]), 15.5, None) + [[15.5, 0.7, "t12"]]}   # 32nd snare pickup into the next bar
B = {"a": base(0) + [[5, 0.24, "gh1", 4], [15, 0.3, "gh1", -3], [9, 0.7, "kick1"]],      # extra ghosts (late/early), a syncopated kick
     "b": [e for e in base(1) if e[0] not in (8, 9, 10, 11)] + [[8, 1.0, "s00"], [9, 1.0, "s01"], [10, 1.0, "s02"], [11, 1.0, "s03"]]
          + [[3, 0.26, "gh1", 3], [7, 0.85, "s07d"]],                            # a re-cut half bar: kick on 9 instead of 7; a lower ghost
     "c": swap(base(2), 7, [7, 0.4, "s09u"]) + [[14, 0.7, "kick1"], [13, 0.22, "gh1", 5]],
     "d": swap(swap(swap(base(3), 13, [13, 0.6, "s09u"]), 14, [14, 0.8, "t12"]), 15, [15, 0.9, "s15"]) + [[14.5, 0.85, "t12"]]}
C = {"a": [e for e in base(0) if e[0] < 8] + [[8, 1.0, "s00"], [9, 1.0, "s01"], [11, 0.95, "s11"],      # a gap on 10, then
                                             [12, 1.0, "s12"], [13, 0.8, "s04"], [14, 0.6, "t12"], [14.5, 0.75, "t12"],
                                             [15, 0.9, "s04u"], [15.5, 1.0, "s04u"]],                # snare doubles, pitched up into the next bar
     "b": [e for e in base(1) if e[0] < 8] + [[8, 0.85, "s04"], [9, 0.0, "s05"], [10, 0.9, "s12d"], [11, 0.0, "s13"],
                                             [12, 1.0, "s12"], [13, 0.75, "t04"], [13.5, 0.85, "t04"], [14, 0.9, "s04"],
                                             [15, 0.8, "t12"], [15.5, 1.0, "s04u"]]}
C = {k: [e for e in v if e[1] > 0] for k, v in C.items()}
# A2: the main break breathing: extra ghost one-shots (early/late), shuffled hats from the hats-only take, one re-cut beat
A2 = {"a": base(0) + [[3, 0.2, "gh1", -4], [11, 0.32, "h11", 5]],
      "b": swap(swap(swap(base(1), 9, [9, 0.9, "s10"]), 10, [10, 0.75, "s11"]), 11, [11, 0.3, "s09"]) + [[15, 0.25, "gh1", 6]],  # beat 3 re-cut: the kicks come a step early
      "c": base(2) + [[5, 0.34, "h13", -3], [9, 0.22, "gh1", 3], [13, 0.36, "h15", 4]],
      "d": swap(base(3), 14, [14, 0.85, "s12d"])}


# the fill library: every fill bar in the song is its own edit, placed by hand (FILLS below)
def head(b, upto):
    return [e for e in base(b) if e[0] < upto]


F = {"F1": C["a"],                                                                # gap on 10, snare doubles, pitched up
     "F2": C["b"],                                                                # snare/low-snare call and answer, 32nd doubles
     "F3": head(2, 12) + [[14, 0.55, "t12"], [14.5, 0.7, "t12"], [15, 0.8, "t04"], [15.5, 0.95, "s04u"]],   # drop-out: two steps of air, then a pickup
     "F4": head(0, 8) + [[8 + i, 0.55 + 0.05 * i, "s04" if i % 2 == 0 else "s12"] for i in range(6)] + [[14, 0.9, "s04u"], [15, 1.0, "s04u"]],  # half-bar stutter
     "F5": head(1, 8) + [[8 + i, 0.18 + 0.05 * i, "gh1", (-3, 4, -2, 5, 0, -4, 3, 0)[i]] for i in range(8)] + [[8, 0.9, "s00"], [12, 1.0, "s12"], [15, 0.9, "s04u"]],  # ghost roll
     "F6": swap(base(2), 15, None) + [[3, 0.65, "kick1"], [10, 0.7, "kick1"], [7, 0.8, "s07d"]],     # kick shuffle, the last step left empty
     "F7": head(0, 8) + [[8 + e[0], e[1], e[2]] for e in head(0, 8) if e[0] < 7] + [[15, 0.6, "t12"], [15.5, 0.8, "t12"]],  # a half-bar repeat
     "F8": head(3, 4) + [[4 + i / 2, 0.35 + 0.026 * i, "t12" if i % 2 else "t04"] for i in range(22)] + [[15, 0.95, "s04u"], [15.5, 1.0, "s12u"]],  # the one snare roll-in (into the main drop)
     "PU": [[8, 0.3, "gh1", 3], [10, 0.35, "gh1", -2], [12, 0.8, "s12"], [13, 0.4, "gh1"], [14, 0.6, "t12"], [14.5, 0.75, "t12"], [15, 0.85, "s04u"], [15.5, 1.0, "s04u"]]}
VARY = {"s04u": "s12u", "s12": "s12d", "s04": "s52", "t12": "t04"}


def vary(f):
    """a fill's second outing: the same edit with its snare slices swapped for pitched / 32nd ones"""
    return [[e[0], e[1], VARY.get(e[2], e[2]), *e[3:]] for e in f]


F |= {k + "v": vary(F[k]) for k in ("F1", "F2", "F3", "F4", "F5", "F7")}
F["F9"] = head(1, 8) + [[12, 0.7, "s12d"], [15.5, 0.5, "t04"]]                 # the long drop-out: half a bar of air before the second passage
F["F6v"] = swap(swap(base(2), 15, None), 14, None) + [[9, 0.7, "kick1"], [13, 0.6, "kick1"], [14, 0.5, "gh1", 4]]

# break 2 (breaks/break2.wav): its own straight bars and edits when the track switches to it, and a quieter layer
# under the Amen (its snare on 12 left out in the Amen's third and fourth bars, where the Amen's snare moves to 14)
def zb(b, steps=range(16), vel=1.0):
    return [[i, vel, f"z{16 * b + i:02d}"] for i in steps]


T = {"a": zb(0),
     "b": swap(zb(1), 10, [10, 0.85, "z16"]),                                    # a kick slice on 10, the Amen's place for it
     "c": swap(zb(2), 14, [14, 0.8, "z36"]),                                     # an extra snare on 14
     "d": swap(zb(3), 15, [15, 0.6, "zt12"]) + [[15.5, 0.75, "zt12"]]}          # 32nd snare pickup
T2 = {"a": zb(0) + [[7, 0.28, "gh1", 3]],
      "b": [e for e in zb(1) if e[0] not in (8, 9, 10, 11)] + [[8, 1.0, "z00"], [9, 1.0, "z01"], [10, 1.0, "z02"], [11, 1.0, "z03"]],  # kick on 3
      "c": zb(2) + [[11, 0.7, "zk1"], [13, 0.25, "zs1", 4]],
      "d": swap(swap(zb(3), 13, [13, 0.6, "z04u"]), 14, [14, 0.8, "zt12"]) + [[14.5, 0.85, "zt12"]]}
TL = {k: zb(b, [i for i in range(16) if not (k in "cd" and i == 12)], 0.55) + ([[12, 0.55, f"z{16 * b + 8:02d}"]] if k in "cd" else [])
      for b, k in enumerate("abcd")}
F["FZ1"] = [e for e in zb(1) if e[0] < 8] + [[8 + i / 2, 0.4 + 0.04 * i, "zt04" if i % 2 else "zt12"] for i in range(12)] \
    + [[14, 0.9, "z04u"], [15, 0.95, "z04u"], [15.5, 1.0, "s04u"]]                # break 2's snare roll, an Amen snare to land
F["FZ2"] = [e for e in zb(2) if e[0] < 12] + [[12, 1.0, "s12"], [13, 0.9, "s13"], [14, 1.0, "s14"], [15, 0.9, "s15"]]  # break 2 hands over to the Amen
PROGRAMS = {"A": A, "A2": A2, "B": B, "T": T, "T2": T2, "TL": TL, **F,
            "hats": [[i, 0.85, f"h{i:02d}", round(float(np.random.default_rng(i).normal(0, 3)), 1) if i % 2 else 0.0] for i in range(16)],
            "hatsq": [[i, 0.55 if i % 4 else 0.65, f"h{i:02d}", round(float(np.random.default_rng(i).normal(0, 3)), 1) if i % 2 else 0.0] for i in range(16)],   # the breakdown's hats, further back
            "frag": {"a": [[4, 0.55, "s04"], [12, 0.6, "s12"]], "b": [[4, 0.5, "s04"], [7, 0.3, "s07"], [12, 0.6, "s12"], [14.5, 0.45, "t12"]]},
            "unrest": {"a": [[6, 0.45, "s07d"], [10, 0.4, "s09u", 6], [12, 0.6, "s12d"]], "b": [[3, 0.3, "gh1", 5], [12, 0.55, "s12"], [14, 0.45, "s12u"]],
                       "c": [[4, 0.5, "s04"], [9, 0.35, "s07d", -4], [12, 0.55, "s12d"], [15, 0.4, "t12"]]},
            # real break: the top loop of the same bar, cut on the same grid, so it sits under the slices (no flams);
            # synthetic: the ride-only take runs two bars apart from the slices so it never doubles the same hits
            "ride": ({k: [[0, 0.8, f"rd{i}"]] for i, k in enumerate("abcd")} if REAL else
                     {"a": [[0, 0.8, "rd2"]], "b": [[0, 0.8, "rd3"]], "c": [[0, 0.8, "rd0"]], "d": [[0, 0.8, "rd1"]]}),
            # kick / snare layers under the break's own hits, bar by bar (the Amen's third and fourth bars move them)
            "kr": ({"a": [[0, 0.9, "kreinf"], [2, 0.7, "kreinf"], [10, 0.8, "kreinf"], [11, 0.6, "kreinf"]],
                    "b": [[0, 0.9, "kreinf"], [2, 0.7, "kreinf"], [10, 0.8, "kreinf"], [11, 0.6, "kreinf"]],
                    "c": [[0, 0.9, "kreinf"], [2, 0.7, "kreinf"], [10, 0.8, "kreinf"]],
                    "d": [[3, 0.85, "kreinf"], [10, 0.8, "kreinf"]]} if REAL
                   else [[0, 0.9, "kreinf"], [6, 0.75, "kreinf"], [11, 0.8, "kreinf"]]),
            "rz": {k: [[0, 0.8, f"rz{i}"]] for i, k in enumerate("abcd")},
            "kr2": [[0, 0.9, "kreinf"]], "sl2": [[4, 0.5, "snlay"], [12, 0.55, "snlay"]],
            "sl": ({k: [[4, 0.5, "snlay"], [12 if k in "ab" else 14, 0.55, "snlay"]] for k in "abcd"} if REAL
                   else [[4, 0.5, "snlay"], [12, 0.55, "snlay"]])}


def blk(name, loop, bars, parts=(), drums=(), **kw):
    return {"name": name, "loop": loop, "bars": bars, "parts": list(parts), "drums": list(drums), **kw}


def groove(name, loop, parts, breaks, fills, extra=("kr", "sl", "ride"), restart=False):
    """8-bar blocks: seven bars of a break (each block's own: breaks[k], e.g. "A" or ["A2", "ride"]) and a fill bar (fills[k])."""
    out = []
    for k, (brk, fill) in enumerate(zip(breaks, fills)):
        brk = [brk] if isinstance(brk, str) else list(brk)
        out += [blk(name + (f" {k + 1}" if len(fills) > 1 else ""), loop, 7, parts, list(dict.fromkeys([*brk, *extra])), loop_restart=restart and k == 0),
                blk(f"{name}: fill {fill}", loop, 1, parts, [fill, *[e for e in extra if e not in ("kr", "sl", "kr2", "sl2")]])]   # no layers under the edits
    return out


FULL = ["pad", "bass", "lead", "comp", "vox"]
Z2 = ("kr2", "sl2", "rz")                          # the layers that line up with break 2
ARR = ([blk("Pad intro A", "A", 8, ["pad"]),
        blk("Pad intro B", "A", 8, ["pad", "vox", "lead_hi"]),
        blk("Percussion introduction", "A", 8, ["pad", "vox"], ["hats", "frag"])]
       + groove("First full break", "A", ["pad", "bass2"], ["A", "A"], ["F1", "F3"], restart=True)
       + groove("Main groove A", "V", ["pad", "bass", "comp"], ["A", ["A2", "TL"]], ["F4", "F2"])           # break 2 layered under the Amen
       + groove("Main groove B", "V", ["pad", "bass", "lead", "comp"], ["B"], ["F5"])
       + groove("Main groove B: break 2", "V", ["pad", "bass", "lead", "comp"], ["T"], ["FZ2"], extra=Z2)      # the switch
       + [blk("Atmospheric breakdown", "B", 8, ["pad", "vox", "lead", "comp"], vel={"pad": 0.85, "lead": 0.8, "comp": 0.8}),   # the glue squeezes the drop, so the valley sits lower
          blk("Atmospheric breakdown: hats return", "B", 8, ["pad", "vox", "lead", "comp"], ["hatsq"], vel={"pad": 0.85, "lead": 0.75, "comp": 0.8})]
       + [blk("Break reintroduction", "A", 7, ["pad", "bass2"], ["A", "kr"]), blk("Break reintroduction: roll-in F8", "A", 1, ["pad", "bass2"], ["F8"])]
       + groove("Main drop / groove return", "A", FULL, ["A", ["A2", "TL"], ["A2", "hats"]], ["F7", "F2v", "F5v"], restart=True)
       + [blk("Breakbeat variation: A", "V", 4, FULL[:4], ["A", "kr", "sl", "ride"]), blk("Breakbeat variation: B", "V", 3, FULL[:4], ["B", "kr", "sl", "ride"]),
          blk("Breakbeat variation: fill F6", "V", 1, FULL[:4], ["F6", "ride"]),
          blk("Breakbeat variation: break 2", "V", 4, FULL[:4], ["T2", *Z2]), blk("Breakbeat variation: B again", "V", 3, FULL[:4], ["B", "kr", "sl", "ride"]),
          blk("Breakbeat variation: drop-out F9", "V", 1, FULL[:4], ["F9"])]
       # the second passage is not the first breakdown again: other chords (loop V), the vibraphone motif instead of the Rhodes
       # phrases, long sub notes, and loose pitched fragments that grow more restless; then a bar of subtraction and a pickup
       + [blk("Second atmospheric passage", "V", 8, ["pad", "vox", "lead_hi", "comp", "bass2"], ["hats", "frag"], vel={"bass2": 0.7}),
          blk("Second atmospheric passage: unrest", "V", 6, ["pad", "vox", "lead_hi", "comp", "bass2"], ["hats", "unrest", "ride"], vel={"bass2": 0.75}),
          blk("Second atmospheric passage: subtraction", "V", 1, ["pad", "vox"]),
          blk("Second atmospheric passage: pickup", "V", 1, ["pad", "bass"], ["PU"])]
       + groove("Final full groove", "A", FULL, [["B", "TL"]], ["F1v"])
       + groove("Final full groove: break 2", "A", FULL, ["T2"], ["FZ1"], extra=Z2)
       + groove("Outro development", "A", ["pad", "bass", "comp"], ["A2"], ["F7v"])
       + groove("Outro development: harmony out", "A", ["bass"], ["A"], ["F6v"])
       + [blk("DJ outro", "A", 4, [], ["A2", "ride", "kr"]), blk("DJ outro: last bars", "A", 4, [], ["A", "hats", "kr"])])
FILL_BARS = [1 + sum(x["bars"] for x in ARR[:i]) for i, x in enumerate(ARR) if any(d in F for d in x["drums"])]
SECTIONS = [(1, 8, "Pad intro A"), (9, 16, "Pad intro B"), (17, 24, "Percussion introduction"), (25, 40, "First full break"),
            (41, 56, "Main groove A"), (57, 72, "Main groove B"), (73, 88, "Atmospheric breakdown"), (89, 96, "Break reintroduction"),
            (97, 120, "Main drop / groove return"), (121, 136, "Breakbeat variation"), (137, 152, "Second atmospheric passage"),
            (153, 168, "Final full groove"), (169, 184, "Outro development"), (185, 192, "DJ outro")]
SONG = ROOT / "songs" / "jungle174" / "jungle174-1589336164.am.json"

def SAMPLER(rate, mix):
    """the sampler stage for keys and pads: 12-bit at `rate`, its reconstruction filter as the gentle low-pass"""
    return {"bits": 12, "rate": rate, "mix": mix}


# two layers: the sine sub (a touch of 2nd harmonic and drive, so it reads on small speakers) and a saw/square voice
# through a low-pass that opens on every note and closes again (harder notes open it further): the growl and
# movement in the 100-800 Hz range that a bare sine never has; touching notes glide on both
SUB = {"kind": "bass", "layers": [
           {"kind": "bass", "gain_db": 0.0,
            "preset": {"release": 0.06, "glide": 0.05, "sub": 1.0, "sub_attack": 0.004, "sub_decay": 3.0, "sub_h2": 0.12,
                       "body": 0.18, "tilt": 1.3, "body_decay": 0.9, "pluck": 0.03, "drive": 1.5}},
           {"kind": "analogbass", "gain_db": -3.0,
            "preset": {"release": 0.06, "glide": 0.05, "saw": 0.7, "square": 0.3, "cutoff": 140, "env_amount": 1600,
                       "filter_decay": 0.12, "resonance": 0.35, "sub": 0.0, "sustain": 0.55, "amp_decay": 0.35, "drive": 1.8}}],
       "glide_gap": 0.03, "hp": 25, "eq": [["peak", 70, 1.0, 0.9], ["peak", 250, -1.5, 1.0]], "lp": 1600, "drive": 1.2, "mono": True}

SPEC = {
    "title": "Haze Theory", "song": SONG, "genre": "atmospheric-jungle-95", "rebuild": "bountiful/jungle174.py",
    "composer": LT.B.COMPOSER_CREDIT, "artist": LT.B.ARTIST, "album": "", "year": 2026,
    "blurb": ("A 1992-95 atmospheric jungle track at 150 bpm built to a brief: sixteen bars of pads alone, then two real breaks sampled, "
              "sped up and pitched to 150 on a 12-bit sampler and re-laid on the grid as continuous takes (each chop crossfades into "
              "the next), the second layered under the first and taking over in places, a ride loop from each running under the chops, cut into Breaks A, B "
              "and C (32nd pickups, snare doubles, gaps, pitched slices, extra ghosts and kicks); a warm rolling sub following A minor "
              "Am9 - Fmaj7 - Em7 - Amaj7 - Dm9 at half speed; evolving sweep pads, dusty Rhodes chords and phrases, a distant vibraphone motif and voice."),
    "overrides": {"bpm": BPM, "swing": 0.5, "drums": "grid", "grid": PROGRAMS, "arrangement": ARR, "drum_cycle_per_block": True, "loop_continuous": True,
                  # mastering: a hot tape print for warmth (head bump, rounded top, even harmonics, hiss and wow), a warm EQ
                  # (low-mid body, the hollow 1-3 kHz filled, the hats' 5 kHz and the fizz above 10k eased),
                  # three-band LR4 compression (each band a couple of dB on its loud passages), a bus compressor whose
                  # sidechain ignores the sub, a soft clipper on the drum peaks and a true-peak limiter
                  "master": {**LT.B.MASTER, "hp": 25, "mono_below": 120, "glue": {},
                             "tape": {"drive": 1.7, "bias": 0.07, "bump_db": 1.5, "hf_db": -1.5, "lp_hz": 16500, "hiss_db": -74, "wow_ms": 0.06},
                             "eq": [["peak", 180, 1.0, 0.7], ["peak", 400, -0.8, 1.0], ["peak", 1500, 1.0, 0.7], ["peak", 5000, -1.2, 1.0], ["highshelf", 10000, -0.5]],
                             "multiband": {"freqs": [150, 5000], "bands": [{"threshold_rel": -3, "ratio": 2.5, "attack": 0.03, "release": 0.15},
                                                                           {"threshold_rel": -3, "ratio": 1.6, "attack": 0.015, "release": 0.12},
                                                                           {"threshold_rel": -3, "ratio": 1.8, "attack": 0.005, "release": 0.08}]},
                             "bus_comp": {"threshold_rel": -3, "ratio": 2.0, "attack": 0.03, "release": 0.2, "sc_hp": 100},
                             "target_lufs": -9.6, "ceiling": -1.0, "clip": 1.5, "true_peak": -1.0},
                  "harmony": {"rhythm": 1, "dominant": "modal", "tonic_major": "7sus4", "colors": {"m": "m9", "": "maj7", "m7": "m9", "7": "7sus4", "maj7": "maj7", "6": "6"}},
                  "melody": {"modal": True, "register": [64, 84], "max_leap": 7, "max_notes_per_bar": 3, "articulation": "legato", "humanize_ms": 7, "velocity": [0.5, 0.82]},
                  # a four-bar cycle (step, degree, beats, velocity): the old bar, a rolling one that glides up the octave
                  # and back, a spacious one, and a busier turnaround; all chord tones, so the harmony check holds
                  "bass": {"style": "pattern", "register": [28, 45],
                           "patterns": [[[0, "R", 0.7, 1.0], [3, "R", 0.25, 0.8], [8, "5", 0.45, 0.85], [10, "O", 0.2, 0.75], [13, "7", 0.2, 0.7], [14, "R", 0.45, 0.85]],
                                        [[0, "R", 1.0, 1.0], [4, "R", 0.2, 0.7], [6, "O", 0.5, 0.85], [8, "5", 0.25, 0.8], [9, "R", 0.7, 0.9], [14, "3", 0.5, 0.75]],
                                        [[0, "R", 1.5, 1.0], [7, "O", 0.25, 0.8], [8, "R", 0.95, 0.9], [12, "5", 0.25, 0.75], [13, "7", 0.25, 0.7], [14, "O", 0.5, 0.85]],
                                        [[0, "R", 0.5, 1.0], [2, "O", 0.25, 0.75], [3, "R", 0.7, 0.9], [8, "5", 0.5, 0.85], [10, "R", 0.5, 0.8],
                                         [12, "R", 0.25, 0.8], [13, "3", 0.25, 0.75], [14, "5", 0.5, 0.85]]]},
                  "bass2": {"style": "pattern", "register": [28, 45],
                            "patterns": [[[0, "R", 2.8, 0.9], [12, "O", 0.9, 0.75]], [[0, "R", 1.7, 0.9], [7, "5", 0.9, 0.75], [12, "O", 0.9, 0.8]]]},
                  "comp": {"steps": [0, 10], "low": 55, "high": 74, "top": 71, "notes": 4, "gate": 1.8, "strum_ms": 16, "humanize_ms": 8, "vel": 0.55, "accent": 0.62},
                  "vox": {"steps": [0], "low": 62, "high": 79, "top": 74, "notes": 2, "gate": 3.8, "vel": 0.5, "accent": 0.5},
                  "pad": {"low": 50, "high": 79, "top": 74, "notes": 5, "vel": 0.5}},
    "kit_def": kit(),
    "layers": [("bass", "bass_mid")],
    "sends": {"slap": {"type": "delay", "time_beats": 0.25, "feedback": 0.25, "taps": 3, "tone": 3500},
              "plate": {"type": "reverb", "seconds": 3.2, "predelay": 0.03, "damp": 0.5}},
    "voices": {
        "pad": ({"zyn": "Strings/0018-Sweep Pad 2.xiz"}, "Sweep Pad 2 (ZynAddSubFX - Strings), evolving pad",
                # the Zyn patch is natively very wide (side/mid ~2): narrowed like a sampled pad, 12-bit 32 kHz, highs lifted
                dict(hp=150, width=0.6, eq=[["peak", 2500, 2.0, 0.8], ["highshelf", 3500, 6.0]], crush=SAMPLER(32000, 0.5),
                     sends={"plate": 0.45}, gain_db=-8.0)),
        "vox": ({"zyn": "Fantasy/0008-Space Voice1.xiz"}, "Space Voice1 (ZynAddSubFX - Fantasy), distant voice",
                dict(hp=300, lp=9000, width=0.7, crush=SAMPLER(26040, 0.5), sends={"plate": 0.6}, gain_db=-14.0)),
        "lead_hi": ({"zyn": "Collection/0002-Vibraphone.xiz"}, "Vibraphone (ZynAddSubFX - Collection), the high motif",
                    dict(hp=400, width=0.8, crush=SAMPLER(26040, 0.4), sends={"echo": 0.45, "plate": 0.5}, gain_db=-12.0)),
        "lead": ({"zyn": "Rhodes/0013-Ice Rhodes2.xiz"}, "Ice Rhodes2 (ZynAddSubFX - Rhodes), phrases",
                 dict(hp=200, crush={"bits": 12, "rate": 26040, "mix": 0.3}, sends={"echo": 0.3, "plate": 0.35}, gain_db=-4.0)),
        "comp": ({"zyn": "Rhodes/0003-DX Rhodes 3.xiz"}, "DX Rhodes 3 (ZynAddSubFX - Rhodes), jazzy chords",
                 dict(hp=150, crush={"bits": 12, "rate": 26040, "mix": 0.35}, width=0.85, sends={"plate": 0.3, "echo": 0.1}, gain_db=-8.0)),
        "bass_mid": ({"zyn": "Bass/0001-Bass 1.xiz"}, "Bass 1 (ZynAddSubFX - Bass), upper-bass texture",
                     dict(hp=180, lp=1400, mono=True, duck={"depth": 0.25, "release": 0.09}, gain_db=-16.0)),
    },
    # the sub: a near-pure sine (engine bass voice) with short glides between touching notes, as on a 90s sampler/Juno sub
    # gains are the settled trim: bass2 never plays in the test bars, so it cannot be trimmed there and takes bass's level
    "extra_tracks": {"bass": dict(SUB, duck={"depth": 0.3, "release": 0.09}, gain_db=-14.0),
                     "bass2": dict(SUB, duck={"depth": 0.25, "release": 0.1}, gain_db=-14.0)},
    "targets": {"bass": -3.0, "bass_mid": -15.0, "pad": -11.0, "comp": -13.0, "lead": -10.0, "vox": -19.0},
    "level_ref": "break",
    "test_bars": (97, 104),
    "automation": [{"type": "lowpass", "tracks": ["pad"], "points": [[1, 800], [9, 1500], [17, 12000]]},
                   {"type": "lowpass", "tracks": ["break", "breakfx"], "points": [[17, 600], [21, 1100], [25, 18000]]},
                   {"type": "lowpass", "tracks": ["pad"], "points": [[73, 2200], [81, 3500], [89, 12000]]},
                   {"type": "lowpass", "tracks": ["break", "breakfx", "kick"], "points": [[89, 450], [93, 1400], [97, 18000]]},
                   {"type": "lowpass", "tracks": ["pad"], "points": [[137, 2500], [145, 4500], [153, 12000]]}],
    "mmp_drums": False, "kick_gain": None, "drum_stems": {},
}


def validate():
    """Checks against the brief, from the MIDI and the rendered audio."""
    import pyloudnorm as pyln
    sys.path.insert(0, str(LT.B.ENGINE / "studio"))
    from render_midi import read_midi
    track = ROOT / "tracks" / "haze-theory"
    notes, bpm, _ = read_midi(track / "haze-theory.mid")
    beat = 60 / bpm
    bar_of = lambda t: int((t + 0.01) / beat // 4) + 1
    res = []
    total_bars = max(bar_of(n["start"]) for n in notes)
    res.append((f"192 bars at {BPM} bpm", total_bars == 192 and abs(bpm - BPM) < 0.01, f"{total_bars} bars, {bpm:.0f} bpm, {192 * 4 * beat:.1f} s"))
    drums = [n for n in notes if n["track"] == "drums"]
    res.append(("bars 1-16: no drums at all", not any(bar_of(n["start"]) <= 16 for n in drums), ""))
    per_bar: dict[int, list] = {}
    for n in drums:
        per_bar.setdefault(bar_of(n["start"]), []).append((round((n["start"] / beat) % 4 * 4, 2), sound_of(n)))
    sigs = {b: tuple(sorted(v)) for b, v in per_bar.items()}
    distinct = len(set(sigs.values()))
    res.append(("drum bars are varied (distinct bar patterns)", distinct >= 15, f"{distinct} distinct patterns over {len(sigs)} drum bars"))
    fills = [sigs.get(b) for b in FILL_BARS]
    res.append(("every fill bar is its own edit", len(set(fills)) == len(fills),
                f"{len(set(fills))} distinct fills over {len(fills)} fill bars (bars {', '.join(map(str, FILL_BARS))})"))
    blocks = [tuple(sigs.get(b) for b in range(s, s + 7)) for s in range(25, 185, 8) if all(b in sigs for b in range(s, s + 7))]
    res.append(("8-bar groove blocks are not copies of each other", len(set(blocks)) >= len(blocks) // 2,
                f"{len(set(blocks))} distinct of {len(blocks)}"))
    res.append(("bar 151 subtracts the drums before the final return", 151 not in per_bar and 152 in per_bar, ""))
    harm_pcs = {n["pitch"] % 12 for n in notes if n["track"] in ("pad", "comp", "bass", "bass2", "vox")}
    res.append(("harmony stays in A minor (no bright C# from Amaj7)", 1 not in harm_pcs, f"pitch classes {sorted(harm_pcs)}"))
    names = [x[1] for v in per_bar.values() for x in v]
    for label, test in (("32nd pickups", lambda s: s.startswith("t")), ("pitched slices", lambda s: s in PITCHED),
                        ("extra ghost one-shots", lambda s: s == "gh1"), ("extra kicks", lambda s: s == "kick1"),
                        ("kick reinforcement", lambda s: s == "kreinf"), ("snare layer", lambda s: s == "snlay"), ("hats-only take", lambda s: s.startswith("h"))):
        c = sum(1 for s in names if test(s))
        res.append((f"break uses {label}", c > 0, f"{c} hits"))
    # only break slices count: the reinforcement kick sits on step 10 under the real break's own kick
    gaps = sum(1 for b, v in per_bar.items() if any(x[1].startswith("s") for x in v)
               and len({s for s, n in v if s == int(s) and str(n)[0] in "st"}) < 16 and {10.0} - {s for s, n in v if str(n)[0] in "st"})
    both = sum(1 for v in per_bar.values() if any(n[0] == "s" for _, n in v) and any(n[0] == "z" for _, n in v))
    only2 = sum(1 for v in per_bar.values() if any(n[0] == "z" for _, n in v) and not any(n[0] == "s" and n[1:].isdigit() for _, n in v))
    res.append(("second break: layered under the first, and switched to", both > 0 and only2 > 0, f"{both} layered bars, {only2} bars of break 2 alone"))
    res.append(("transition breaks leave gaps", gaps > 0, f"{gaps} bars with a removed slice"))
    # bass follows the harmony: each bass note's pitch class is a tone of the chord sounding on the pad/comp at that moment
    harm = [n for n in notes if n["track"] in ("pad", "comp")]
    hit = tot = 0
    for n in (n for n in notes if n["track"] in ("bass", "bass2")):
        pcs = {h["pitch"] % 12 for h in harm if h["start"] <= n["start"] + 0.01 < h["end"]}
        if pcs:
            tot += 1
            hit += (n["pitch"] % 12) in pcs
    res.append(("bass follows the harmony (bass notes are chord tones)", tot and hit / tot >= 0.9, f"{hit}/{tot} bass notes"))
    bass_bars = {}
    for n in notes:
        if n["track"] == "bass":
            bass_bars.setdefault(bar_of(n["start"]), set()).add(n["pitch"])
    octs = sum(1 for v in bass_bars.values() if max(v) - min(v) >= 12)
    res.append(("bass moves by octaves / passing tones", octs > 0, f"{octs} bars with an octave move"))
    # audio: sections
    sc = json.loads((track / "exports" / "render_info.json").read_text())
    stems = {p.stem: sf.read(str(p))[0].mean(1) / sc["stem_scale"] for p in (track / "stems").glob("*.wav")}
    master, _ = sf.read(str(track / "exports" / "haze-theory.wav"))
    meter = pyln.Meter(SR)

    def lvl(x):
        k = len(x) // 2048
        r = np.sqrt((x[:k * 2048].reshape(k, 2048) ** 2).mean(1))
        return 20 * np.log10(np.sqrt((r[r > r.max() * 0.03] ** 2).mean()) + 1e-12) if r.max() > 1e-6 else -120

    rows = []
    for a, b, name in SECTIONS:
        i0, i1 = int(((a - 1) * 4 + 1) * beat * SR), int(b * 4 * beat * SR) - int(0.01 * SR)   # the next bar's 5 ms leads stay out
        rows.append((a, b, name, round(meter.integrated_loudness(master[i0:i1]), 1), {s: round(lvl(x[i0:i1]), 0) for s, x in stems.items()}))
    pads_only = rows[0][4]
    res.append(("bars 1-8: pads alone", pads_only.get("pad", -120) > -40 and all(v < -60 for s, v in pads_only.items() if s not in ("pad",)), ""))
    res.append(("bars 9-16: a second texture and the high motif join", rows[1][4].get("vox", -120) > -60 and rows[1][4].get("lead_hi", -120) > -60, ""))
    res.append(("the break is silent until bar 17", rows[0][4].get("break", -120) < -60 and rows[1][4].get("break", -120) < -60, ""))
    loud = {name: l for a, b, name, l, _ in rows}
    contrast = loud["Main drop / groove return"] - loud["Atmospheric breakdown"]
    res.append(("dynamic contrast between breakdown and groove", contrast >= 2.5, f"{contrast:.1f} LU"))
    a_ = sc["analysis"]
    res.append(("master: no clipping, true peak below -0.5 dBTP", a_["clipped_samples"] == 0 and a_["true_peak_dbtp_approx"] < -0.5,
                f"{a_['integrated_lufs']} LUFS, TP {a_['true_peak_dbtp_approx']}"))
    res.append(("low end centred (correlation below 120 Hz)", a_["correlation_below_120hz"] > 0.95, f"{a_['correlation_below_120hz']}"))
    lines = ["# Validation: Haze Theory", "", f"**{sum(r[1] for r in res)}/{len(res)} checks pass**", "", "| check | result | detail |", "|---|---|---|"]
    lines += [f"| {n} | {'ok' if ok else '**FAIL**'} | {d} |" for n, ok, d in res]
    stems_order = [s for s in ("pad", "vox", "lead_hi", "lead", "comp", "bass", "bass2", "bass_mid", "break", "breakfx", "break2", "break3", "kick", "snlay") if s in stems]
    lines += ["", "| bars | section | LUFS | " + " | ".join(stems_order) + " |", "|---|---|---|" + "---|" * len(stems_order)]
    lines += [f"| {a}-{b} | {name} | {l} | " + " | ".join("–" if v.get(s, -120) < -60 else f"{v[s]:.0f}" for s in stems_order) + " |" for a, b, name, l, v in rows]
    lines += ["", f"Master: {a_['integrated_lufs']} LUFS, true peak {a_['true_peak_dbtp_approx']} dBTP, stereo correlation {a_['correlation_full']}, "
              f"spectrum " + ", ".join(f"{k} {v:.1f}" for k, v in a_["spectrum_share_db"].items())]
    (track / "validation.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    if "--validate" in sys.argv:
        validate()
    else:
        build_break()
        LT.make(SPEC, log=lambda m: print(m, flush=True))
        validate()
