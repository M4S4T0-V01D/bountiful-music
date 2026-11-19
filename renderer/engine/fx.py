"""Offline effects on numpy arrays. Mono signals are 1-D, stereo are (n, 2) float32.

Feedback effects (reverb, delay) are built as impulse responses and applied by FFT convolution, which
keeps everything vectorised and deterministic.
"""
from __future__ import annotations

import numpy as np
from scipy import signal
from scipy.ndimage import maximum_filter1d, minimum_filter1d, uniform_filter1d

SR = 44100


def set_rate(sr: int) -> None:
    global SR
    SR = sr


def db(x: float) -> float:
    return 10 ** (x / 20)


def stereo(x: np.ndarray) -> np.ndarray:
    return x if x.ndim == 2 else np.stack([x, x], 1)


def pan(x: np.ndarray, p: float) -> np.ndarray:
    """Constant-power pan of a mono signal (or balance of a stereo one), p in [-1, 1]."""
    a = (p + 1) * np.pi / 4
    if x.ndim == 1:
        return np.stack([x * np.cos(a), x * np.sin(a)], 1) * np.sqrt(2)
    g = np.array([np.cos(a), np.sin(a)]) * np.sqrt(2)
    return x * g


# ---------------------------------------------------------------- filters

def _sos(kind: str, f: float | tuple, order: int = 2) -> np.ndarray:
    nyq = SR / 2
    if isinstance(f, tuple):
        f = tuple(min(max(v, 10.0), nyq * 0.98) for v in f)
    else:
        f = min(max(f, 10.0), nyq * 0.98)
    return signal.butter(order, f, btype=kind, fs=SR, output="sos")


def filt(x: np.ndarray, kind: str, f, order: int = 2) -> np.ndarray:
    return signal.sosfilt(_sos(kind, f, order), x, axis=0).astype(np.float32)


def hp(x, f, order=2):
    return filt(x, "highpass", f, order)


def lp(x, f, order=2):
    return filt(x, "lowpass", f, order)


def bp(x, lo, hi, order=2):
    return filt(x, "bandpass", (lo, hi), order)


def _biquad(kind: str, f: float, gain_db: float, q: float = 0.707) -> np.ndarray:
    """RBJ cookbook peaking / shelf as an SOS row."""
    A = 10 ** (gain_db / 40)
    w = 2 * np.pi * min(f, SR * 0.45) / SR
    cw, sw = np.cos(w), np.sin(w)
    alpha = sw / (2 * q)
    if kind == "peak":
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    elif kind == "lowshelf":
        sA = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) - (A - 1) * cw + sA), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sA)]
        a = [(A + 1) + (A - 1) * cw + sA, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sA]
    elif kind == "highshelf":
        sA = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) + (A - 1) * cw + sA), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - sA)]
        a = [(A + 1) - (A - 1) * cw + sA, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sA]
    else:
        raise ValueError(kind)
    b, a = np.array(b) / a[0], np.array(a) / a[0]
    return np.concatenate([b, a])[None, :]


def eq(x: np.ndarray, bands: list) -> np.ndarray:
    """bands: [("peak", 2000, +3, 1.0), ("lowshelf", 120, -2), ("hp", 40), ("lp", 12000)]"""
    for band in bands:
        kind = band[0]
        if kind == "hp":
            x = hp(x, band[1], band[2] if len(band) > 2 else 2)
        elif kind == "lp":
            x = lp(x, band[1], band[2] if len(band) > 2 else 2)
        else:
            q = band[3] if len(band) > 3 else 0.707
            x = signal.sosfilt(_biquad(kind, band[1], band[2], q), x, axis=0).astype(np.float32)
    return x


def sweep(x: np.ndarray, kind: str, curve: np.ndarray, block: int = 512, order: int = 2) -> np.ndarray:
    """Time-varying Butterworth filter. `curve` gives the cutoff (Hz) per sample (or is resampled to it).

    The filter is redesigned every `block` samples and its state is carried across, which is smooth
    enough for slow sweeps (filter automation, breakdown builds)."""
    n = len(x)
    if len(curve) != n:
        curve = np.interp(np.linspace(0, len(curve) - 1, n), np.arange(len(curve)), curve)
    out = np.empty_like(x)
    zi = None
    for i in range(0, n, block):
        f = float(np.clip(curve[min(i + block // 2, n - 1)], 20, SR * 0.45))
        sos = signal.butter(order, f, btype=kind, fs=SR, output="sos")
        seg = x[i:i + block]
        if zi is None:
            shape = (sos.shape[0], 2) + seg.shape[1:]
            zi = np.zeros(shape)
        out[i:i + block], zi = signal.sosfilt(sos, seg, axis=0, zi=zi)
    return out.astype(np.float32)


# ---------------------------------------------------------------- dynamics and colour

def saturate(x: np.ndarray, drive: float = 1.5, mix: float = 1.0) -> np.ndarray:
    """Soft tape/valve saturation with level compensation."""
    y = np.tanh(x * drive) / np.tanh(drive)
    return (x * (1 - mix) + y * mix).astype(np.float32)


def envelope(x: np.ndarray, attack: float, release: float) -> np.ndarray:
    """Peak envelope (mono) with separate attack/release, vectorised: max-hold then smoothing."""
    m = np.abs(x).max(1) if x.ndim == 2 else np.abs(x)
    rel = max(1, int(release * SR))
    held = maximum_filter1d(m, size=rel, origin=-(rel // 2) + 0)
    att = max(1, int(attack * SR))
    return uniform_filter1d(held, size=att).astype(np.float32) + 1e-9


def compress(x: np.ndarray, threshold_db: float = -18, ratio: float = 3, attack: float = 0.005,
             release: float = 0.12, makeup_db: float = 0.0, mix: float = 1.0) -> np.ndarray:
    env = envelope(x, attack, release)
    lvl = 20 * np.log10(env)
    over = np.maximum(lvl - threshold_db, 0)
    gain = db(-over * (1 - 1 / ratio) + makeup_db)
    g = gain[:, None] if x.ndim == 2 else gain
    return (x * (1 - mix) + x * g * mix).astype(np.float32)


def crossover(x: np.ndarray, freqs: list) -> list:
    """Linkwitz-Riley 4th-order bands (two cascaded 2nd-order Butterworths per split), low to high. Each lower band
    goes through the higher splits' all-pass (LP + HP) so the bands sum back flat in level and phase."""
    lr = lambda y, kind, f: filt(filt(y, kind, f, 2), kind, f, 2)
    bands, rest = [], x
    for k, f in enumerate(freqs):
        low = lr(rest, "lowpass", f)
        for g in freqs[k + 1:]:
            low = lr(low, "lowpass", g) + lr(low, "highpass", g)
        bands.append(low)
        rest = lr(rest, "highpass", f)
    return bands + [rest]


def glue(x: np.ndarray, threshold_rel: float = -6.0, ratio: float = 2.0, attack: float = 0.03, release: float = 0.2,
         knee: float = 6.0, sc_hp: float = 0.0, ref=None, block: int = 32) -> tuple[np.ndarray, np.ndarray]:
    """A mastering compressor: stereo-linked RMS detector (on a sidechain high-passed at sc_hp, so the sub does not
    pump the mix), soft knee, attack/release smoothing of the gain in dB. The threshold is relative to the loud
    passages (the 95th percentile of the 50 ms level of ref, default the input), so it means the same at any level.
    Returns (output, gain reduction in dB per block)."""
    sc = hp(x, sc_hp, 2) if sc_hp else x
    m = (sc.astype(np.float64) ** 2).mean(1) if sc.ndim == 2 else sc.astype(np.float64) ** 2
    nb = len(m) // block
    pw = m[:nb * block].reshape(nb, block).mean(1)
    pw = uniform_filter1d(pw, max(1, int(0.01 * SR / block)))                      # 10 ms RMS window
    lvl = 10 * np.log10(pw + 1e-12)
    r = ref if ref is not None else lvl
    loud = uniform_filter1d(10 ** (r / 10), max(1, int(0.05 * SR / block)))
    th = 10 * np.log10(np.percentile(loud[loud > loud.max() * 1e-4], 95)) + threshold_rel
    over = lvl - th
    gr = np.where(over <= -knee / 2, 0.0, np.where(over >= knee / 2, over, (over + knee / 2) ** 2 / (2 * knee))) * (1 - 1 / ratio)
    a, rl = np.exp(-block / (attack * SR)), np.exp(-block / (release * SR))
    out = np.empty_like(gr)
    g = 0.0
    for i, t in enumerate(gr.tolist()):                                             # attack when reducing more, release when less
        g = a * g + (1 - a) * t if t > g else rl * g + (1 - rl) * t
        out[i] = g
    gain = np.interp(np.arange(len(x)), np.arange(nb) * block + block / 2, 10 ** (-out / 20))
    y = x * (gain[:, None] if x.ndim == 2 else gain)
    return y.astype(np.float32), out


def multiband(x: np.ndarray, freqs: list, bands: list) -> tuple[np.ndarray, list]:
    """Split at freqs (LR4), glue() each band with its own settings (a dict per band, {} = untouched), sum.
    Returns (output, max gain reduction per band in dB)."""
    out, red = np.zeros_like(x), []
    for b, cfg in zip(crossover(x, freqs), bands):
        if cfg:
            b, gr = glue(b, **cfg)
            red.append(float(np.percentile(gr, 99)))
        else:
            red.append(0.0)
        out += b
    return out.astype(np.float32), red


def limiter(x: np.ndarray, ceiling_db: float = -1.0, lookahead: float = 0.004, release: float = 0.08) -> np.ndarray:
    """Look-ahead brickwall limiter: gain = min over a window of the needed reduction, smoothed."""
    ceil = db(ceiling_db)
    peak = np.abs(x).max(1) if x.ndim == 2 else np.abs(x)
    need = np.minimum(1.0, ceil / np.maximum(peak, 1e-9))
    la = max(1, int(lookahead * SR))
    g = minimum_filter1d(need, size=2 * la + 1)          # start reducing `lookahead` before a peak
    # release: on a decimated curve, gain drops instantly and recovers exponentially
    blk = 32
    gd = g[: len(g) // blk * blk].reshape(-1, blk).min(1)
    gd = np.append(gd, g[len(gd) * blk:].min() if len(g) % blk else 1.0)
    k = 1 - np.exp(-blk / (release * SR))
    out = np.empty_like(gd)
    cur = 1.0
    for i, v in enumerate(gd.tolist()):
        cur = v if v < cur else cur + (v - cur) * k
        out[i] = cur
    g = np.minimum(g, np.repeat(out, blk)[: len(g)])
    g = uniform_filter1d(g, size=la)
    g = np.minimum(g, need)  # guarantee no overs after smoothing
    y = x * (g[:, None] if x.ndim == 2 else g)
    return np.clip(y, -ceil, ceil).astype(np.float32)


def crush(x: np.ndarray, bits: int = 12, rate: float = 26040.0, filtered: bool = True) -> np.ndarray:
    """Vintage sampler: anti-alias input filter, sample-and-hold to `rate`, quantise to `bits`, and
    (if `filtered`) the output reconstruction filter. Unfiltered = SP-1200-style grit."""
    n = len(x)
    x = lp(x, rate * 0.42, 6)             # the sampler's steep input filter: no digital 'hash'
    r = rate / SR
    idx = np.floor(np.floor(np.arange(n) * r) / r).astype(np.int64)
    y = x[np.clip(idx, 0, n - 1)]
    q = 2 ** (bits - 1)
    y = (np.round(y * q) / q).astype(np.float32)
    if filtered:
        y = lp(y, rate * 0.45, 4)
    return y.astype(np.float32)


def console(x: np.ndarray, drive: float = 1.3, bias: float = 0.04) -> np.ndarray:
    """Analog desk / transformer colour: gentle asymmetric saturation (adds even harmonics),
    unity gain for small signals."""
    g0 = drive * (1 - np.tanh(drive * bias) ** 2)
    y = (np.tanh(drive * (x + bias)) - np.tanh(drive * bias)) / g0
    return y.astype(np.float32)


def tape(x: np.ndarray, drive: float = 1.5, bias: float = 0.06, bump_db: float = 1.5, hf_db: float = -2.5,
         lp_hz: float = 16000, hiss_db: float = -68, wow_ms: float = 0.1, seed: int = 11) -> np.ndarray:
    """A pass through a tape machine: head bump in the lows, softened highs, asymmetric saturation,
    a little hiss and flutter. Expects the signal around 'tape level' (RMS about -18 dBFS)."""
    x = eq(stereo(x), [("peak", 90, bump_db, 0.8), ("highshelf", 9500, hf_db), ("lp", lp_hz, 2)])
    x = console(x * 1.0, drive, bias)
    rng = np.random.default_rng(seed)
    hiss = lp(rng.standard_normal(x.shape).astype(np.float32), 11000) * db(hiss_db)
    x = x + hiss
    if wow_ms:
        x = wow(x, depth_ms=wow_ms, rate=0.4, flutter_ms=0.02, seed=seed)
    return x.astype(np.float32)


def resample(x: np.ndarray, ratio: float) -> np.ndarray:
    """Play back faster by `ratio` (pitch and speed up together, like a sampler)."""
    n = int(len(x) / ratio)
    if n < 2:
        return x[:1]
    pos = np.arange(n) * ratio
    if x.ndim == 1:
        return np.interp(pos, np.arange(len(x)), x).astype(np.float32)
    return np.stack([np.interp(pos, np.arange(len(x)), x[:, c]) for c in range(x.shape[1])], 1).astype(np.float32)


# ---------------------------------------------------------------- time-based

def reverb_ir(seconds: float = 2.4, predelay: float = 0.02, damp: float = 0.5, seed: int = 7,
              size: float = 1.0) -> np.ndarray:
    """A stereo hall IR: decorrelated noise with frequency-dependent decay (highs die faster),
    sparse early reflections, and a short predelay."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = np.zeros((n, 2), np.float32)
    for ch in range(2):
        noise = rng.standard_normal(n).astype(np.float32)
        lo = lp(noise, 700)
        mid = bp(noise, 700, 3500)
        hi = hp(noise, 3500)
        t60 = seconds
        ir[:, ch] = (lo * np.exp(-6.9 * t / t60) + mid * np.exp(-6.9 * t / (t60 * (1 - 0.45 * damp)))
                     + 0.6 * hi * np.exp(-6.9 * t / (t60 * (1 - 0.8 * damp))))
        # early reflections
        for k in range(10):
            d = int((0.004 + rng.random() * 0.045 * size) * SR)
            ir[d, ch] += (rng.random() - 0.5) * 1.2 * np.exp(-k / 6)
    fade_in = np.minimum(1, t / 0.012)[:, None]
    ir *= fade_in
    pd = int(predelay * SR)
    ir = np.concatenate([np.zeros((pd, 2), np.float32), ir])
    return ir / np.sqrt((ir ** 2).sum(0).mean())


def delay_ir(beat_s: float, time_beats: float = 0.75, feedback: float = 0.45, taps: int = 8,
             tone: float = 3500, pingpong: bool = True) -> np.ndarray:
    """Tempo-synced (ping-pong) echo as an IR; every repeat is darker than the last, like tape."""
    d = int(time_beats * beat_s * SR)
    n = d * taps + 2048
    ir = np.zeros((n, 2), np.float32)
    imp = np.zeros(2048, np.float32)
    imp[0] = 1
    for k in range(1, taps + 1):
        imp = lp(imp, tone)
        ch = (k % 2) if pingpong else None
        g = feedback ** (k - 1)
        if ch is None:
            ir[k * d:k * d + 2048] += (imp * g)[:, None]
        else:
            ir[k * d:k * d + 2048, ch] += imp * g
            ir[k * d:k * d + 2048, 1 - ch] += imp * g * 0.25
    return ir


def convolve(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    x = stereo(x)
    out = np.stack([signal.oaconvolve(x[:, c], ir[:, c])[:len(x)] for c in range(2)], 1)
    return out.astype(np.float32)


def chorus(x: np.ndarray, depth_ms: float = 3.0, rate: float = 0.6, base_ms: float = 12.0, mix: float = 0.5) -> np.ndarray:
    """Stereo chorus: two modulated delay lines in quadrature (widens pads and Rhodes)."""
    x = stereo(x)
    n = len(x)
    t = np.arange(n) / SR
    out = np.empty_like(x)
    for c, ph in enumerate((0, np.pi / 2)):
        d = (base_ms + depth_ms * np.sin(2 * np.pi * rate * t + ph)) * SR / 1000
        pos = np.arange(n) - d
        wet = np.interp(pos, np.arange(n), x[:, c], left=0)
        out[:, c] = x[:, c] * (1 - mix) + wet * mix
    return out.astype(np.float32)


def wow(x: np.ndarray, depth_ms: float = 0.35, rate: float = 0.55, flutter_ms: float = 0.04, seed: int = 3) -> np.ndarray:
    """Tape wow and flutter (slow + fast pitch wander via a modulated delay)."""
    x = stereo(x)
    n = len(x)
    t = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    d = (depth_ms * (0.6 * np.sin(2 * np.pi * rate * t) + 0.4 * np.sin(2 * np.pi * rate * 0.37 * t + rng.random() * 6))
         + flutter_ms * np.sin(2 * np.pi * 6.7 * t)) * SR / 1000 + depth_ms * SR / 1000 * 1.2
    pos = np.arange(n) - d
    return np.stack([np.interp(pos, np.arange(n), x[:, c], left=0) for c in range(2)], 1).astype(np.float32)


def autopan(x: np.ndarray, rate: float, depth: float, phase: float = 0.0) -> np.ndarray:
    """Suitcase-Rhodes style stereo tremolo."""
    x = stereo(x)
    t = np.arange(len(x)) / SR
    m = np.sin(2 * np.pi * rate * t + phase) * depth
    gl, gr = np.sqrt(np.clip(1 - m, 0, 2) / 1.0), np.sqrt(np.clip(1 + m, 0, 2) / 1.0)
    return (x * np.stack([gl, gr], 1) / np.sqrt(1 + depth * 0)).astype(np.float32)


def tremolo(x: np.ndarray, rate: float, depth: float) -> np.ndarray:
    t = np.arange(len(x)) / SR
    g = 1 - depth * (0.5 + 0.5 * np.sin(2 * np.pi * rate * t))
    return (x * (g[:, None] if x.ndim == 2 else g)).astype(np.float32)


def width(x: np.ndarray, amount: float) -> np.ndarray:
    """Mid/side width: 0 mono, 1 unchanged, >1 wider."""
    x = stereo(x)
    m = (x[:, 0] + x[:, 1]) / 2
    s = (x[:, 0] - x[:, 1]) / 2 * amount
    return np.stack([m + s, m - s], 1).astype(np.float32)


def mono_below(x: np.ndarray, f: float = 120) -> np.ndarray:
    """Make everything below f mono (keeps the low end phase-safe on club systems)."""
    x = stereo(x)
    # zero-phase low band, so x - lo is an exact complement (a phase-shifting lowpass left stereo lows in 'hi')
    lo = signal.sosfiltfilt(signal.butter(4, f, "lowpass", fs=SR, output="sos"), x, axis=0)
    hi = x - lo
    m = lo.mean(1, keepdims=True)
    return (hi + m).astype(np.float32)


def duck(n: int, hits: list[float], depth: float = 0.35, release: float = 0.16, attack: float = 0.004) -> np.ndarray:
    """Sidechain gain curve from kick times (seconds): dips by `depth`, recovers over `release`."""
    g = np.zeros(n, np.float32)
    rl = int(release * 5 * SR)
    shape = np.exp(-np.arange(rl) / (release * SR)).astype(np.float32)
    att = int(attack * SR)
    shape[:att] *= np.linspace(0, 1, att)
    for h in hits:
        i = int(h * SR)
        if i >= n:
            continue
        seg = shape[:n - i]
        g[i:i + len(seg)] = np.maximum(g[i:i + len(seg)], seg)
    return (1 - depth * g).astype(np.float32)


def akai(x: np.ndarray, grain: float = 0.04, jump: float = 0.3, fade: float = 0.0015) -> np.ndarray:
    """Akai S1000/S3000-style time-stretch artefact: the sound is re-read in fixed grains whose start
    points jump back and forth, giving the metallic, fluttering 'stretched vocal' of 90s jungle.
    Overall timing is preserved (no drift)."""
    n = len(x)
    G = max(64, int(grain * SR))
    k = np.arange(n) // G
    within = np.arange(n) % G
    offs = ((k % 3) - 1) * int(jump * G)
    src = np.clip(k * G + within + offs, 0, n - 1)
    y = x[src]
    f = max(1, int(fade * SR))
    w = np.ones(G, np.float32)
    w[:f] = np.linspace(0, 1, f)
    w[-f:] = np.linspace(1, 0, f)
    win = w[within]
    return (y * (win[:, None] if y.ndim == 2 else win)).astype(np.float32)


def leslie(x: np.ndarray, speed: np.ndarray, crossover: float = 800.0, mix: float = 1.0) -> np.ndarray:
    """Rotary speaker. The signal splits at `crossover`: the treble horn and the bass drum each spin
    with their own inertia (the horn spins up fast, the drum lags), giving Doppler pitch wobble,
    amplitude throb and a moving stereo image from two virtual mics. `speed` is 0 (chorale/slow) to
    1 (tremolo/fast) per sample (or resampled to it)."""
    x = stereo(x).mean(1).astype(np.float32)
    n = len(x)
    if len(speed) != n:
        speed = np.interp(np.linspace(0, len(speed) - 1, n), np.arange(len(speed)), speed)
    lo = lp(x, crossover, 4)
    hi = x - lo
    t = np.arange(n) / SR
    out = np.zeros((n, 2), np.float32)
    # rotor speeds with inertia (one-pole smoothing): horn ~0.8 s, drum ~3 s
    for band, slow, fast, tau, depth_ms, am in ((hi, 0.83, 6.7, 0.8, 0.35, 0.35), (lo, 0.67, 5.8, 3.0, 0.15, 0.15)):
        target = slow + (fast - slow) * speed
        blk = 256
        tg = target[::blk]
        k = 1 - np.exp(-blk / (tau * SR))
        cur = np.empty_like(tg)
        c = tg[0]
        for i, v in enumerate(tg.tolist()):
            c += (v - c) * k
            cur[i] = c
        rate = np.repeat(cur, blk)[:n]
        phase = np.cumsum(2 * np.pi * rate / SR)
        for ch, off in enumerate((0.0, np.pi / 2)):        # two mics 90 degrees apart
            d = (depth_ms * (1 + np.sin(phase + off)) + 0.2) * SR / 1000
            y = np.interp(np.arange(n) - d, np.arange(n), band, left=0)
            gain = 1 - am * (0.5 + 0.5 * np.cos(phase + off))
            out[:, ch] += (y * gain).astype(np.float32)
    dry = np.stack([x, x], 1)
    return (dry * (1 - mix) + out * mix).astype(np.float32)
