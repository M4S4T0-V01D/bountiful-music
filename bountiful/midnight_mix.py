"""Midnight Horizon: the six M4S4T0 jazz-hop singles as one continuous mix.

Order runs by key and tempo: Sapporo, 3 A.M. (C dorian, 78) -> Sonora at Midnight (D minor, 84) ->
Ninth Street Blue (F minor blues, 88) -> Paper Lanterns (E-flat major, 86; Fm is its ii) -> Lighthouse,
Late (F major, 80; a step up from the ringing Ebmaj9) -> Window Frost (B-flat major, 76; the ringing Fmaj9
is its V, and its Bbmaj9 closes the set). Every single ends on a held chord that rings out over a 6 s fade and starts with
a beatless intro, so each seam lets the last chord ring under the next intro while the weather changes
(winter wind, rain, street rain, crickets, surf, a fire and wind at the window). The outgoing tail loses its lows over the overlap so two bass
lines never stack.

Rebuild the singles first (their scripts write the masters), then: .venv/bin/python bountiful/midnight_mix.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy import signal

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tracks" / "midnight-horizon-mix"
TITLE, ARTIST = "Midnight Horizon (Continuous Mix)", "M4S4T0"
SR = 44100
TARGET_LUFS = -14.0
OVERLAP = 4.5          # seconds of the outgoing tail under the incoming intro
SET = [("Sapporo, 3 A.M.", "sapporo-3am/exports/Sapporo 3AM - M4S4T0.wav"),
       ("Sonora at Midnight", "sonora-at-midnight/exports/Sonora at Midnight - M4S4T0.wav"),
       ("Ninth Street Blue", "ninth-street-blue/exports/Ninth Street Blue - M4S4T0.wav"),
       ("Paper Lanterns", "paper-lanterns/exports/Paper Lanterns - M4S4T0.wav"),
       ("Lighthouse, Late", "lighthouse-late/exports/Lighthouse, Late - M4S4T0.wav"),
       ("Window Frost", "window-frost/exports/Window Frost - M4S4T0.wav")]


def db(x: float) -> float:
    return 10 ** (x / 20)


def true_peak_db(x: np.ndarray) -> float:
    up = signal.resample_poly(x, 4, 1, axis=0)
    return 20 * np.log10(np.max(np.abs(up)) + 1e-12)


def band_gap(x: np.ndarray, t0: float, t1: float) -> float:
    seg = x[int(t0 * SR):int(t1 * SR)].mean(1)
    f, pxx = signal.welch(seg, SR, nperseg=8192)
    return 10 * np.log10(pxx[(f >= 40) & (f < 120)].sum() / pxx[(f >= 300) & (f < 3000)].sum())


def thin_tail(x: np.ndarray, n: int) -> np.ndarray:
    """Over the last n samples, crossfade into a 160 Hz high-passed copy: the next intro owns the lows."""
    out = x.copy()
    hp = signal.sosfiltfilt(signal.butter(2, 160, "highpass", fs=SR, output="sos"), x[-n:], axis=0)
    w = np.sin(0.5 * np.pi * np.linspace(0, 1, n))[:, None]
    out[-n:] = x[-n:] * np.sqrt(1 - w ** 2) + hp * w
    return out


def main() -> int:
    songs = []
    for name, rel in SET:
        x, sr = sf.read(ROOT / "tracks" / rel, dtype="float32", always_2d=True)
        assert sr == SR, rel
        songs.append((name, x))
    n_ov = int(OVERLAP * SR)
    starts, pos = [], 0
    for _name, x in songs:
        starts.append(pos)
        pos += len(x) - n_ov
    mix = np.zeros((pos + n_ov, 2), np.float64)
    for k, ((_name, x), s) in enumerate(zip(songs, starts)):
        y = x.astype(np.float64)
        if k < len(songs) - 1:
            y = thin_tail(y, n_ov)
        if k:                                    # the intro comes up under the ring
            y[:n_ov] *= np.sin(0.5 * np.pi * np.linspace(0, 1, n_ov))[:, None]
        mix[s: s + len(y)] += y

    meter = pyln.Meter(SR)
    mix *= db(TARGET_LUFS - meter.integrated_loudness(mix))
    tp = true_peak_db(mix)
    if tp > -1.0:
        mix *= db(-1.0 - tp)
    mix = mix.astype(np.float32)

    (OUT / "exports").mkdir(parents=True, exist_ok=True)
    wav = OUT / "exports" / f"{TITLE} - {ARTIST}.wav"
    sf.write(wav, mix, SR, subtype="PCM_24")
    total_ms = int(len(mix) / SR * 1000)
    cues = [int(s / SR * 1000) for s in starts]
    meta = [";FFMETADATA1", f"title={TITLE}", f"artist={ARTIST}", "genre=Jazz-hop", "date=2026"]
    for k, (name, _x) in enumerate(songs):
        end = cues[k + 1] if k + 1 < len(cues) else total_ms
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={cues[k]}", f"END={end}", f"title={name}"]
    with tempfile.TemporaryDirectory() as td:
        mf = Path(td) / "chapters.txt"
        mf.write_text("\n".join(meta) + "\n")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-i", str(mf),
                        "-map_metadata", "1", "-map_chapters", "1", "-c:a", "libmp3lame", "-b:a", "320k",
                        str(wav.with_suffix(".mp3"))], check=True)
    lines = [f"{c // 60000}:{c // 1000 % 60:02d}  {name}" for c, (name, _x) in zip(cues, songs)]
    (OUT / "tracklist.txt").write_text(f"{TITLE} - {ARTIST}\n\n" + "\n".join(lines) + "\n")

    # checks
    lufs, tp = meter.integrated_loudness(mix), true_peak_db(mix)
    dur = len(mix) / SR
    seams = [s / SR for s in starts[1:]]
    seam_lufs = [meter.integrated_loudness(mix[int((t - OVERLAP) * SR): int((t + 8) * SR)]) for t in seams]
    hop = SR // 10
    rms = 20 * np.log10(np.sqrt((mix[: len(mix) // hop * hop].mean(1).reshape(-1, hop) ** 2).mean(1)) + 1e-9)
    body = rms[int(1 * 10): int((dur - 7) * 10)]
    checks = {
        "loudness within 0.5 LU of target": abs(lufs - TARGET_LUFS) < 0.5,
        "true peak <= -1.0 dBTP": tp <= -0.95,
        "length 20:30-22:30": 1230 <= dur <= 1350,
        "no dropout over 0.5 s below -50 dBFS": not np.any(np.convolve(body < -50, np.ones(5), "valid") >= 5),
        "seams stay within 12 LU of the mix": all(lufs - 12 <= s <= lufs + 3 for s in seam_lufs),
        "lows 3-10 dB over mids in every song body": all(
            3 <= band_gap(mix, s / SR + 60, s / SR + 120) <= 10 for s in starts),
        "mp3 has one chapter per song": subprocess.run(
            ["ffprobe", "-v", "error", "-show_chapters", "-of", "csv", str(wav.with_suffix(".mp3"))],
            capture_output=True, text=True).stdout.count("chapter") == len(songs),
    }
    for k, ok in checks.items():
        print(f"{'ok  ' if ok else 'FAIL'} {k}")
    print("\n".join(lines))
    print(f"{sum(checks.values())}/{len(checks)} checks, {lufs:.1f} LUFS, TP {tp:.1f} dBTP, "
          f"{int(dur // 60)}:{int(dur % 60):02d}, seams {', '.join(f'{s:.1f}' for s in seam_lufs)} LUFS")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
