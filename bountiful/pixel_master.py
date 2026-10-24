#!/usr/bin/env python3
"""Mix and master 'Put on the Pixel' from each track's stems, as one album.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/pixel_master.py            all eight, then the album
    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/pixel_master.py plasma     one track (matched to the album
                                                                                                  using the others' mixes)

Mix (per track, from stems/):
  drums   EQ, glue compressor, parallel (NY) compression with saturation, a shared short room on snare and perc
  bass    sidechain compression keyed from the kick stem, a harmonic exciter (the sub's overtones, for small speakers), mono lows
  music   ping-pong delay on the lead, mud cut and air, a gentle kick-keyed pump, glue compressor
  fx      transitions placed from the arrangement: chip-noise riser and reversed crash into each drop, a sub impact on it,
          a noise downlifter into each breakdown
  bus     mix-bus glue compressor
Master (needs all the mixes, so the album is matched):
  linear-phase EQ pulling each track half-way to the album's average spectrum (max +-1.5 dB, octave-smoothed),
  3-band compressor, M/S (sides high-passed so the lows are mono, a little side air), console colour,
  4x soft clipper, 4x true-peak limiter (-1 dBTP) at a per-track loudness, backing off if the limiter would work too hard.

-> tracks/<slug>/exports/<slug>-master.wav (24-bit) and .mp3, tracks/<slug>/mix/<slug>-mix.wav, master_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy import signal as sg

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build as B  # noqa: E402
import pixel_dnb as P  # noqa: E402
import pixel_songs as S  # noqa: E402

sys.path.insert(0, str(B.ENGINE))
from engine import fx  # noqa: E402
from engine.export import mp3  # noqa: E402

SR = fx.SR
ROOT = S.ROOT
DRUMS = ("kick", "snare", "perc", "hats", "ride", "toms", "cymbals", "break")
BASS = ("bass", "bass_mid", "bass2")
# loudness per track (LUFS): the quieter, jazzier ones sit lower so the album plays at one perceived level
TARGET = {"copper-bars": -9.5, "raster-interrupt": -9.5, "sine-scroller": -9.5, "bitplane-blues": -10.5,
          "vector-balls": -9.2, "greetings": -9.7, "plasma": -9.5, "last-frame": -10.5}
ORDER = list(TARGET)
MATCH = {"plasma": 0.2}          # how far each track is pulled to the album's spectrum (default 0.4); Plasma is dark on purpose
ANCHOR = {"lead": -10.0, "comp": -4.0}   # the widest these may be (side vs mid, dB): the lead holds the centre
METER = pyln.Meter(SR)


def song(slug):
    if slug == "copper-bars":
        return {"title": "Copper Bars", "bpm": P.BPM, "arr": P.SPEC["overrides"]["arrangement"], "crash": P.KIT / "crash.wav", "track": 1}
    s = S.SPECS[slug]
    return {"title": s["title"], "bpm": s["overrides"]["bpm"], "arr": s["overrides"]["arrangement"],
            "crash": s["kit"]["dir"] / "crash.wav", "track": s["track"]}


def lufs(x):
    return METER.integrated_loudness(np.asarray(x, np.float64))


# ------------------------------------------------------------------ processors

def compressor(x, ratio, attack, release, thr=None, pct=None, knee=6.0, sc=None, makeup=0.0, mix=1.0, block=16):
    """Feed-forward compressor with a soft knee and one-pole attack/release on the gain reduction.
    thr in dBFS, or pct: the threshold sits at that percentile of the detector's level in the active passages.
    sc: an external sidechain (key) signal. Returns (output, gain-reduction stats)."""
    s = x if sc is None else sc
    m = np.abs(s).max(1) if s.ndim == 2 else np.abs(s)
    nb = -(-len(m) // block)
    m = np.pad(m, (0, nb * block - len(m))).reshape(nb, block).max(1)
    lvl = 20 * np.log10(m + 1e-9)
    if thr is None:
        thr = float(np.percentile(lvl[lvl > lvl.max() - 40], pct))
    over = lvl - thr
    slope = 1 - 1 / ratio
    gr = np.where(over <= -knee / 2, 0.0, np.where(over >= knee / 2, over * slope, slope * (over + knee / 2) ** 2 / (2 * knee)))
    rate = SR / block
    ka, kr = 1 - np.exp(-1 / (attack * rate)), 1 - np.exp(-1 / (release * rate))
    out, cur = np.empty(nb), 0.0
    for i, v in enumerate(gr.tolist()):
        cur += (v - cur) * (ka if v > cur else kr)
        out[i] = cur
    g = fx.db(makeup - np.interp(np.arange(len(x)), (np.arange(nb) + 0.5) * block, out)).astype(np.float32)
    y = x * (g[:, None] if x.ndim == 2 else g)
    active = out[lvl > lvl.max() - 40]
    return (x * (1 - mix) + y * mix).astype(np.float32), {"thr": round(thr, 1), "gr_avg": round(float(active.mean()), 2),
                                                          "gr_max": round(float(out.max()), 2)}


def split(x, f):
    """A zero-phase crossover: low + high adds back to exactly the input."""
    lo = sg.sosfiltfilt(sg.butter(4, f, "lowpass", fs=SR, output="sos"), x, axis=0).astype(np.float32)
    return lo, (x - lo).astype(np.float32)


def pingpong(x, beat_s, beats=0.75, feedback=0.42, taps=6, level=0.22):
    """A stereo ping-pong echo: repeats alternate left and right, each one darker."""
    src = fx.bp(x.mean(1), 500, 5000)
    d = int(beats * beat_s * SR)
    out = np.zeros((len(x), 2), np.float32)
    for k in range(1, taps + 1):
        if k * d >= len(x):
            break
        src = fx.lp(src, 5000 - 500 * k)
        out[k * d:, (k + 1) % 2] += src[:-k * d] * level * feedback ** (k - 1)
    return x + out


def exciter(bass, level_db=-15.0):
    """Harmonics of the bass's fundamental (driven hard, kept only above 350 Hz): the sub heard on a phone."""
    band = fx.bp(bass.mean(1), 60, 250)
    h = fx.lp(fx.hp(np.tanh(band / (np.abs(band).max() + 1e-9) * 6.0), 350, 4), 3000)
    return bass + fx.stereo(h * fx.db(level_db) * np.abs(bass).max())


def ms(x, side_hp=200.0, side_air_db=1.5):
    m, s = (x[:, 0] + x[:, 1]) / 2, (x[:, 0] - x[:, 1]) / 2
    s = sg.sosfiltfilt(sg.butter(2, side_hp, "highpass", fs=SR, output="sos"), s)
    s = fx.eq(s.astype(np.float32), [("highshelf", 8000, side_air_db)])
    return np.stack([m + s, m - s], 1).astype(np.float32)


# ------------------------------------------------------------------ transitions

def at(bar, bpm):
    return int((bar - 1) * 240 / bpm * SR)


def riser(n, crash):
    """Two bars of chip noise opening up, with the kit's crash reversed into the drop."""
    t = np.linspace(0, 1, n)
    x = fx.sweep(P.noise(n, 120000, seed=7).astype(np.float32), "lowpass", 300 * 40 ** t ** 2, block=256)
    x = fx.sweep(x, "highpass", 80 * 20 ** t, block=256) * (t ** 2.2)
    out = fx.width(np.stack([x, np.roll(x, 331)], 1), 1.4)
    c, csr = sf.read(str(crash))
    c = (c.mean(1) if c.ndim == 2 else c)[::-1]
    c = c[-min(len(c), n):]
    out[-len(c):] += fx.stereo(c.astype(np.float32) * 0.8)
    return out * 0.25


def impact(n):
    """A sub drop on the downbeat: a sine falling 70 -> 32 Hz, decaying over a bar."""
    t = np.arange(n) / SR
    f = 32 + 38 * np.exp(-t / 0.12)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.35) * np.minimum(1, t / 0.003)
    return fx.stereo(fx.hp(x.astype(np.float32), 25)) * 0.35


def downlifter(n):
    t = np.linspace(0, 1, n)
    x = fx.sweep(P.noise(n, 90000, seed=11).astype(np.float32), "lowpass", 9000 * (1 / 30) ** t, block=256) * (1 - t) ** 1.5
    return fx.width(np.stack([x, np.roll(x, 257)], 1), 1.3) * 0.18


def transitions(slug, drums, bed, n):
    """Find the drops (drum energy up 4 dB or more into a block) and the breakdowns (down 6 dB or more) from the arrangement."""
    sg_ = song(slug)
    bpm, bar_n = sg_["bpm"], int(240 / sg_["bpm"] * SR)
    out, events = np.zeros((n, 2), np.float32), []
    pw = lambda a: np.sqrt((a ** 2).mean()) + 1e-9
    fit = lambda sig, ref, rel_db, part=slice(None): sig * (pw(ref) * fx.db(rel_db) / pw(sig[part]))   # set a level against the music
    rms = lambda a, b: 20 * np.log10(np.sqrt((drums[max(0, a):max(0, b)] ** 2).mean()) + 1e-5) if b > a else -100
    starts = np.cumsum([0] + [b["bars"] for b in sg_["arr"]])[:-1] + 1
    loudest = max(rms(at(b, bpm), at(b, bpm) + bar_n) for b in range(1, int(starts[-1])))
    bar = 1
    for i, blk in enumerate(sg_["arr"]):
        if i and blk["bars"] >= 4:
            s0 = at(bar, bpm)
            after = rms(s0, s0 + bar_n)
            jump = after - rms(s0 - 2 * bar_n, s0 - bar_n)             # two bars back: the bar before is often a pickup fill
            big = after >= loudest - 4 and (jump >= 4 or blk.get("crash") and jump >= 1.5)
            recent = events and bar - events[-1][0] < 12
            if big:
                r = fit(riser(2 * bar_n, sg_["crash"]), bed[s0 - bar_n:s0], -9, slice(-bar_n, None))   # its last bar, 9 dB under
                out[max(0, s0 - len(r)):s0] += r[-min(len(r), s0):]
                im = impact(min(bar_n, n - s0))
                im = fit(im, bed[s0:s0 + bar_n // 2], -10, slice(0, bar_n // 2))
                out[s0:s0 + len(im)] += im
                events.append((bar, "drop", blk["name"], round(jump, 1)))
            elif after - rms(s0 - bar_n, s0) <= -6 and not recent:
                d = downlifter(min(2 * bar_n, n - s0))
                d = fit(d, bed[s0 - bar_n:s0], -12, slice(0, bar_n)) * min(1.0, pw(bed[s0:s0 + bar_n]) / pw(bed[s0 - bar_n:s0]) * 2.5)
                out[s0:s0 + len(d)] += d
                events.append((bar, "breakdown", blk["name"], round(after - rms(s0 - bar_n, s0), 1)))
        bar += blk["bars"]
    plate = fx.reverb_ir(2.4, 0.02, 0.5, seed=21)
    out = out + fx.convolve(fx.hp(out, 300), plate) * 0.25
    return out, events


# ------------------------------------------------------------------ the mix

def mix(slug):
    d = ROOT / "tracks" / slug / "stems"
    st = {p.stem: fx.stereo(sf.read(str(p), dtype="float32")[0]) for p in sorted(d.glob("*.wav"))}
    n = max(len(x) for x in st.values())
    st = {k: np.pad(x, ((0, n - len(x)), (0, 0))) for k, x in st.items()}
    sgn = song(slug)
    beat_s = 60 / sgn["bpm"]
    rep = {}
    key = st["kick"] if "kick" in st else fx.lp(st["break"], 150, 4)            # what the kick is, for the sidechains
    sum_ = lambda names: sum((st[k] for k in names if k in st), np.zeros((n, 2), np.float32))

    # drums
    dr = fx.eq(sum_(DRUMS), [("peak", 58, 1.0, 0.9), ("peak", 380, -1.5, 1.0), ("peak", 4200, -0.8, 1.2), ("highshelf", 10000, 0.8)])
    dr, rep["drum_glue"] = compressor(dr, 3.0, 0.010, 0.12, pct=93)
    ny, rep["drum_parallel"] = compressor(dr, 8.0, 0.0008, 0.06, pct=55)
    dr = dr + fx.hp(fx.saturate(ny, 2.0), 45) * 0.28
    room = fx.reverb_ir(0.7, 0.006, 0.65, seed=5, size=0.4)
    snare = sum_(("snare", "perc")) + (fx.bp(st["break"], 200, 6000) * 0.5 if "break" in st else 0)
    dr = dr + fx.convolve(fx.hp(snare, 300), room) * fx.db(-15)

    # bass
    bs = sum_(BASS)
    bs, rep["bass_sidechain"] = compressor(bs, 3.0, 0.001, 0.12, sc=key, pct=75)
    bs, rep["bass_level"] = compressor(bs, 3.0, 0.015, 0.2, pct=90)
    bs = fx.mono_below(exciter(bs), 160)

    # music
    mu_names = [k for k in st if k not in DRUMS + BASS]
    rep["narrowed"] = {}
    for k, cap in ANCHOR.items():
        if k in st:
            m_, s_ = (st[k][:, 0] + st[k][:, 1]) / 2, (st[k][:, 0] - st[k][:, 1]) / 2
            sm = 10 * np.log10((s_ ** 2).mean() / ((m_ ** 2).mean() + 1e-12) + 1e-12)
            if sm > cap:
                st[k] = fx.width(st[k], 10 ** ((cap - sm) / 20))
                rep["narrowed"][k] = f"{sm:.1f} -> {cap} dB S/M"
    if "lead" in st:
        st["lead"] = pingpong(st["lead"], beat_s)
    mu = fx.eq(sum_(mu_names), [("hp", 90), ("peak", 280, -1.5, 0.9), ("peak", 2800, 0.6, 1.0), ("highshelf", 11000, 1.0)])
    mu, rep["music_pump"] = compressor(mu, 1.8, 0.004, 0.16, sc=key, pct=80)
    mu, rep["music_glue"] = compressor(mu, 2.0, 0.02, 0.25, pct=95)
    mu = fx.mono_below(fx.width(mu, 1.1), 150)

    fxb, rep["transitions"] = transitions(slug, dr, dr + bs + mu, n)
    x = dr + bs + mu + fxb
    out = ROOT / "tracks" / slug / "mix"
    out.mkdir(exist_ok=True)
    for name, b in (("drums", dr), ("bass", bs), ("music", mu), ("fx", fxb)):        # the bus stems, for checks and remixes
        sf.write(str(out / f"bus_{name}.wav"), b, SR, subtype="FLOAT")
    x, rep["mix_glue"] = compressor(x, 2.0, 0.03, 0.2, pct=95, knee=8.0)
    sf.write(str(out / f"{slug}-mix.wav"), x, SR, subtype="FLOAT")
    return rep


# ------------------------------------------------------------------ the master

def spectrum(x):
    f, p = sg.welch(x.mean(1), SR, nperseg=8192)
    db_ = 10 * np.log10(p + 1e-20)
    sm = np.array([db_[(f >= fc / 2 ** 0.5) & (f <= fc * 2 ** 0.5)].mean() if fc > 15 else db_[i] for i, fc in enumerate(f)])
    return f, sm - sm[(f > 500) & (f < 2000)].mean()                                  # octave-smoothed, normalised at 1 kHz


def match_eq(x, corr_f, corr_db):
    taps = 8191
    g = fx.db(np.interp(np.linspace(0, SR / 2, 2049), corr_f, corr_db))
    h = sg.firwin2(taps, np.linspace(0, 1, 2049), g)
    y = np.stack([sg.oaconvolve(x[:, c], h)[taps // 2: taps // 2 + len(x)] for c in range(2)], 1)
    return y.astype(np.float32)


def limit(x, target, ceiling=-1.0, clip=1.5):
    g = target - lufs(x)
    for _ in range(3):                                   # the clipper and limiter take some loudness: aim again from the result
        y, info = _limit(x * fx.db(g), ceiling, clip)
        miss = target - lufs(y)
        if abs(miss) < 0.1:
            break
        g += miss
    return y, info


def _limit(x, ceiling, clip):
    t = fx.db(ceiling + clip)
    xo = sg.resample_poly(x, 4, 1, axis=0)
    pk = np.maximum(np.abs(xo).max(1, keepdims=True), 1e-9)
    x = sg.resample_poly(xo * (t * np.tanh(pk / t) / pk), 1, 4, axis=0).astype(np.float32)
    xo = sg.resample_poly(x, 4, 1, axis=0).astype(np.float32)
    y = sg.resample_poly(fx.limiter(xo, ceiling, lookahead=0.016, release=0.4), 1, 4, axis=0).astype(np.float32)
    tp = 20 * np.log10(np.abs(sg.resample_poly(y, 4, 1, axis=0)).max())
    if tp > ceiling:
        y = y * fx.db(ceiling - tp)
    blk = 441
    nb = len(y) // blk
    pk_ = lambda a: np.abs(a[:nb * blk]).reshape(nb, blk, 2).max((1, 2))
    red = 20 * np.log10(np.maximum(pk_(y), 1e-9) / np.maximum(pk_(x), 1e-9))
    return y, {"limiter_max_db": round(float(-red.min()), 2), "limiter_over_1db_s": round(float((red < -1).sum() * blk / SR), 1)}


def master(slug, album_f, album_db, rep):
    x = sf.read(str(ROOT / "tracks" / slug / "mix" / f"{slug}-mix.wav"), dtype="float32")[0]
    f, own = spectrum(x)
    corr = np.clip(MATCH.get(slug, 0.4) * (album_db - own), -1.2, 1.2) * ((f > 35) & (f < 16000))
    corr = np.convolve(corr, np.ones(5) / 5, mode="same")
    x = match_eq(x, f, corr)
    rep["match_eq_db"] = {str(int(fc)): round(float(np.interp(fc, f, corr)), 2) for fc in (60, 125, 250, 500, 1000, 2000, 4000, 8000, 12000)}

    lo, rest = split(x, 120)
    mid, hi = split(rest, 4500)
    lo, rep["mb_low"] = compressor(lo, 2.5, 0.03, 0.25, pct=90)
    mid, rep["mb_mid"] = compressor(mid, 1.8, 0.02, 0.2, pct=95)
    hi, rep["mb_high"] = compressor(hi, 2.0, 0.005, 0.1, pct=95)
    x = ms(lo + mid + hi)
    k = fx.db(-18 - lufs(x))                                                       # into the console at its operating level
    x = fx.console(x * k, 1.2, 0.02) / k

    target = TARGET[slug]
    while True:
        y, lim = limit(x, target)
        if lim["limiter_max_db"] <= 3.5 and lim["limiter_over_1db_s"] <= 0.15 * len(y) / SR or target <= TARGET[slug] - 2:
            break
        print(f"   at {target} LUFS: {lim}, backing off", flush=True)
        target -= 0.5                                                              # too much limiting: master quieter
    rep["limiter"], rep["target_lufs"] = lim, target
    fi = int(0.01 * SR)
    y[:fi] *= np.linspace(0, 1, fi)[:, None]
    y = y + (np.random.default_rng(1).random(y.shape) - np.random.default_rng(2).random(y.shape)) * 2 ** -23   # TPDF dither for 24-bit
    exp = ROOT / "tracks" / slug / "exports"
    wav = exp / f"{slug}-master.wav"
    sf.write(str(wav), y.astype(np.float32), SR, subtype="PCM_24")
    s = song(slug)
    mp3(wav, exp / f"{slug}-master.mp3", {"title": s["title"], "artist": S.ARTIST, "album": S.ALBUM, "composer": S.COMPOSER,
                                         "genre": "Drum & Bass", "year": S.YEAR, "track": f"{s['track']}/8", "album_artist": S.ARTIST,
                                         "cover": str(ROOT / "albums" / "put-on-the-pixel" / "cover.jpg")})
    st = [lufs(y[i:i + 3 * SR]) for i in range(0, len(y) - 3 * SR, SR)]
    tp = 20 * np.log10(np.abs(sg.resample_poly(y, 4, 1, axis=0)).max())
    m, sd = y.mean(1), (y[:, 0] - y[:, 1]) / 2
    rep["result"] = {"lufs": round(lufs(y), 2), "short_term_max": round(max(st), 2), "true_peak_dbtp": round(float(tp), 2),
                     "plr_db": round(float(tp - lufs(y)), 1), "side_to_mid_db": round(float(10 * np.log10((sd ** 2).mean() / (m ** 2).mean())), 1),
                     "correlation": round(float(np.corrcoef(y[:, 0], y[:, 1])[0, 1]), 2)}
    (ROOT / "tracks" / slug / "exports" / "master_report.json").write_text(json.dumps(rep, indent=1, default=str))
    return rep


def main():
    slugs = sys.argv[1:] or ORDER
    reports = {}
    for slug in slugs:
        print(f"== mix {slug}", flush=True)
        reports[slug] = mix(slug)
        for e in reports[slug]["transitions"]:
            print(f"   bar {e[0]:>3}  {e[1]:<9} {e[2]} ({e[3]:+.1f} dB drums)")
        if reports[slug]["narrowed"]:
            print(f"   narrowed {reports[slug]['narrowed']}")
    specs = {}
    for slug in ORDER:                                                            # the album's average, from every mix there is
        p = ROOT / "tracks" / slug / "mix" / f"{slug}-mix.wav"
        if p.exists():
            specs[slug] = spectrum(sf.read(str(p), dtype="float32")[0])
    f = next(iter(specs.values()))[0]
    album = np.mean([v[1] for v in specs.values()], 0)
    for slug in slugs:
        print(f"== master {slug}", flush=True)
        r = master(slug, f, album, reports[slug])
        print(f"   {r['result']} | limiter {r['limiter']} | target {r['target_lufs']}")
        print(f"   match EQ {r['match_eq_db']}")
        print(f"   " + " ".join(f"{k} {v['gr_avg']}/{v['gr_max']}" for k, v in r.items() if isinstance(v, dict) and "gr_avg" in v))


if __name__ == "__main__":
    main()
