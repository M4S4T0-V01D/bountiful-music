"""Files out: audio (WAV/FLAC/MP3), MIDI, an LMMS project, arrangement metadata and an analysis report."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from xml.sax.saxutils import quoteattr

import mido
import numpy as np
import soundfile as sf
from scipy import signal

from . import fx
from . import theory as th
from .render import GROUPS, STEMS, Timeline
from .score import Score


def write_audio(path: Path, x: np.ndarray, fmt: str = "WAV") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.clip(x, -1, 1), fx.SR, subtype="PCM_24", format=fmt)


def mp3(wav: Path, out: Path, meta: dict) -> bool:
    cmd = ["lame", "--quiet", "-b", "320", "-q", "0", "--add-id3v2",
           "--tt", meta["title"], "--ta", meta["artist"], "--tl", meta["album"], "--ty", str(meta.get("year", 2026)),
           "--tn", str(meta.get("track", 1)), "--tg", meta.get("genre", "Electronic"),
           "--tv", f"TCOM={meta.get('composer', '')}", "--tv", f"TPE2={meta.get('album_artist', meta['artist'])}"]
    if meta.get("cover") and Path(meta["cover"]).exists():
        cmd += ["--ti", str(meta["cover"])]
    cmd += [str(wav), str(out)]
    return subprocess.run(cmd).returncode == 0


# ---------------------------------------------------------------- MIDI

GM = {"rhodes": 4, "rhodes_solo": 4, "pad": 89, "bass": 32, "vibes": 11, "horn": 59, "piano": 0, "signals": 80}


def write_midi(score: Score, path: Path) -> None:
    """One track per part, with the performed timing (swing + humanisation) at 960 ppq."""
    tl = Timeline(score)
    sw = score.cfg.get("swing", {})
    swing_of = {"rhodes": sw.get("rhodes", .12), "piano": sw.get("rhodes", .12), "bass": sw.get("bass", .1),
                "pad": 0.0, "signals": 0.0}
    ppq = 960
    mf = mido.MidiFile(ticks_per_beat=ppq)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("track_name", name=score.cfg["title"], time=0))
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(score.bpm), time=0))
    meta.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    meta.append(mido.MetaMessage("key_signature", key="Fm", time=0))
    for s in score.sections:
        meta.append(mido.MetaMessage("marker", text=s.name, time=0))
    # markers need absolute placement: rebuild with deltas
    meta = mido.MidiTrack([m for m in meta if m.type != "marker"])
    last = 0
    for s in score.sections:
        tick = s.start_bar * 4 * ppq
        meta.append(mido.MetaMessage("marker", text=s.name, time=tick - last))
        last = tick
    mf.tracks.append(meta)
    for ch, (part, notes) in enumerate([(k, v) for k, v in score.notes.items() if v]):
        tr = mido.MidiTrack()
        tr.append(mido.MetaMessage("track_name", name=score.cfg.get("voices", {}).get(part, {}).get("label", part), time=0))
        c = ch if ch < 9 else ch + 1
        tr.append(mido.Message("program_change", program=GM.get(part, 0), channel=c, time=0))
        ev = []
        for n in notes:
            t = tl.sec(n.beat, swing_of.get(part, sw.get("melody", .08))) + n.shift
            a = max(0, int(round(t / score.beat_s * ppq)))
            b = max(a + 1, int(round((t + n.dur * score.beat_s) / score.beat_s * ppq)))
            v = int(np.clip(n.vel * 127, 1, 127))
            ev.append((a, 1, mido.Message("note_on", note=int(n.pitch), velocity=v, channel=c)))
            ev.append((b, 0, mido.Message("note_off", note=int(n.pitch), velocity=0, channel=c)))
        ev.sort(key=lambda e: (e[0], e[1]))
        now = 0
        for tick, _, msg in ev:
            msg.time = tick - now
            now = tick
            tr.append(msg)
        mf.tracks.append(tr)
    # drums: the chop sequence (note = 36 + slice index, one track per break) and the clean layers
    for name in ("break", "rush"):
        tr = mido.MidiTrack()
        tr.append(mido.MetaMessage("track_name", name=f"{name} chops (note 36+slice)", time=0))
        ev = []
        for sec, hits in score.drum_hits[name]:
            for h in hits:
                beat = sec.start_bar * 4 + h.beat
                a = int(round(beat * ppq))
                note = 36 + h.idx + (32 if h.src == "roller" else 0)
                ev.append((a, 1, mido.Message("note_on", note=note, velocity=int(np.clip(h.vel * 110, 1, 127)), channel=9)))
                ev.append((a + int(h.length * ppq * 0.9), 0, mido.Message("note_off", note=note, velocity=0, channel=9)))
        ev.sort(key=lambda e: (e[0], e[1]))
        now = 0
        for tick, _, msg in ev:
            msg.time = tick - now
            now = tick
            tr.append(msg)
        mf.tracks.append(tr)
    gm_drum = {"hat": 42, "open": 46, "ride": 51, "crash": 49, "shaker": 70, "bongo_hi": 60, "bongo_lo": 61,
               "kick": 36, "snare": 38, "clap": 39, "rim": 37, "odaiko": 35, "chu": 47, "shime": 50, "kara": 37, "kane": 56}
    tr = mido.MidiTrack()
    tr.append(mido.MetaMessage("track_name", name="kit layers (GM drums)", time=0))
    ev = []
    for stem in ("top", "perc", "kick", "snare"):
        for beat, kind, v in score.layer_hits[stem]:
            a = int(round(beat * ppq))
            ev.append((a, 1, mido.Message("note_on", note=gm_drum.get(kind, 60), velocity=int(np.clip(v * 127, 1, 127)), channel=9)))
            ev.append((a + ppq // 8, 0, mido.Message("note_off", note=gm_drum.get(kind, 60), velocity=0, channel=9)))
    ev.sort(key=lambda e: (e[0], e[1]))
    now = 0
    for tick, _, msg in ev:
        msg.time = tick - now
        now = tick
        tr.append(msg)
    mf.tracks.append(tr)
    path.parent.mkdir(parents=True, exist_ok=True)
    mf.save(str(path))


# ---------------------------------------------------------------- LMMS

def write_lmms(score: Score, path: Path, stem_files: dict[str, Path], live: bool = False) -> None:
    """An LMMS project: every instrument stem as an audio track (the mix, ready to rebalance), plus
    muted instrument tracks holding each part's notes per section for editing in the piano roll.

    LMMS: 192 ticks per bar, 48 per beat; note key = MIDI - 12. Sample paths are absolute (LMMS
    resolves relative paths against its own sample folder), so re-run the render script after moving
    the project."""
    TPB = 48
    total = score.total_bars * 4 * TPB + 4 * TPB * 2
    q = quoteattr
    lines = ['<?xml version="1.0"?>', "<!DOCTYPE lmms-project>",
             '<lmms-project version="31" creator="LMMS" type="song">',
             f'<head bpm="{score.bpm:g}" timesig_numerator="4" timesig_denominator="4" mastervol="100" masterpitch="0"/>',
             "<song>", '<trackcontainer type="song">']
    for k, f in ({} if live else stem_files).items():
        if not f:
            continue
        lines.append(f'<track type="2" name={q("audio: " + f.stem)} muted="0" solo="0">')
        lines.append('<sampletrack vol="100" pan="0"/>')
        lines.append(f'<sampleclip pos="0" len="{total}" src={q(str(f.resolve()))} off="0" muted="0"/>')
        lines.append("</track>")
    for part, notes in score.notes.items():
        if not notes or part == "signals":
            continue
        lab = score.cfg.get("voices", {}).get(part, {}).get("label", part)
        v = score.cfg.get("voices", {}).get(part, {})
        if live and v.get("backend") != "lmms":
            continue   # the live session only holds parts that LMMS itself plays
        lines.append(f'<track type="0" name={q(("" if live else "notes: ") + lab)} muted="{0 if live else 1}" solo="0">')
        if live and v.get("backend") == "lmms":
            from .lmms import instrument_xml   # the real LMMS instrument (e.g. the actual Zyn patch)
            lines.append(instrument_xml(v))
        else:
            lines.append('<instrumenttrack vol="70" pan="0" basenote="57" pitch="0" pitchrange="1" fxch="0" usemasterpitch="1">')
            lines.append('<instrument name="tripleoscillator"><tripleoscillator/></instrument>')
            lines.append("</instrumenttrack>")
        for s in score.sections:
            a, b = s.start_bar * 4, (s.start_bar + s.bars) * 4
            sel = [n for n in notes if a <= n.beat < b]
            if not sel:
                continue
            lines.append(f'<midiclip type="1" pos="{a * TPB}" len="{s.bars * 4 * TPB}" name={q(s.name)} muted="0" steps="16">')
            for n in sel:
                pos = int(round((n.beat - a) * TPB))
                ln = max(1, int(round(n.dur * TPB)))
                lines.append(f'<note pos="{pos}" len="{ln}" key="{int(n.pitch) - 12}" vol="{int(np.clip(n.vel * 100, 1, 200))}" pan="0"/>')
            lines.append("</midiclip>")
        lines.append("</track>")
    lines += ["</trackcontainer>", "</song>", "</lmms-project>"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


# ---------------------------------------------------------------- metadata

def write_arrangement(score: Score, path: Path) -> None:
    data = {
        "title": score.cfg["title"], "bpm": score.bpm, "key": score.cfg["key"], "seed": score.cfg["seed"],
        "bars": score.total_bars, "duration_s": score.total_bars * 4 * score.beat_s,
        "sections": [{
            "name": s.name, "start_bar": s.start_bar + 1, "bars": s.bars,
            "start_s": round(s.start_bar * 4 * score.beat_s, 3),
            "chords": [f"{sl.chord.symbol}@{sl.start:g}" for sl in s.slots],
            "parts": sorted(p for p, ns in score.notes.items() if any(s.start_bar * 4 <= n.beat < (s.start_bar + s.bars) * 4 for n in ns)),
        } for s in score.sections],
    }
    path.write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------- analysis

def analyse(x: np.ndarray, score: Score | None = None, name: str = "") -> dict:
    import pyloudnorm as pyln
    sr = fx.SR
    meter = pyln.Meter(sr)
    peak = float(np.abs(x).max())
    up = signal.resample_poly(x, 4, 1, axis=0)
    tp = float(np.abs(up).max())
    mono = x.mean(1)
    rep = {
        "file": name, "duration_s": round(len(x) / sr, 3), "sample_rate": sr, "channels": x.shape[1],
        "integrated_lufs": round(float(meter.integrated_loudness(x.astype(np.float64))), 2),
        "sample_peak_dbfs": round(20 * np.log10(peak + 1e-12), 2),
        "true_peak_dbtp_approx": round(20 * np.log10(tp + 1e-12), 2),
        "clipped_samples": int((np.abs(x) >= 0.9999).sum()),
        "dc_offset": [round(float(v), 6) for v in x.mean(0)],
        "rms_dbfs": round(20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-12), 2),
    }
    rep["crest_db"] = round(rep["sample_peak_dbfs"] - rep["rms_dbfs"], 2)
    # silence: windows of 0.5 s below -60 dBFS
    w = int(0.5 * sr)
    blocks = mono[: len(mono) // w * w].reshape(-1, w)
    lvl = 20 * np.log10(np.sqrt((blocks ** 2).mean(1)) + 1e-12)
    silent = np.where(lvl < -60)[0]
    rep["silent_half_seconds"] = [round(i * 0.5, 1) for i in silent.tolist()]
    # stereo
    lo = fx.lp(x, 120, 4)
    hi = fx.hp(x, 200, 4)

    def corr(a):
        return round(float(np.corrcoef(a[:, 0], a[:, 1])[0, 1]), 3)

    rep["correlation_full"] = corr(x)
    rep["correlation_below_120hz"] = corr(lo)
    rep["correlation_above_200hz"] = corr(hi)
    side = (hi[:, 0] - hi[:, 1]) / 2
    mid = (hi[:, 0] + hi[:, 1]) / 2
    rep["side_to_mid_db_above_200hz"] = round(10 * np.log10((side ** 2).mean() / ((mid ** 2).mean() + 1e-12) + 1e-12), 2)
    # spectral balance
    f, P = signal.welch(mono, sr, nperseg=8192)
    bands = {"sub_20_60": (20, 60), "bass_60_200": (60, 200), "lowmid_200_800": (200, 800), "mid_800_3k": (800, 3000),
             "presence_3k_8k": (3000, 8000), "air_8k_16k": (8000, 16000)}
    tot = P.sum()
    rep["spectrum_share_db"] = {k: round(10 * np.log10(P[(f >= a) & (f < b)].sum() / tot + 1e-12), 1) for k, (a, b) in bands.items()}
    if score is not None:
        secs = []
        for s in score.sections:
            a = int(s.start_bar * 4 * score.beat_s * sr)
            b = int((s.start_bar + s.bars) * 4 * score.beat_s * sr)
            seg = x[a:b].astype(np.float64)
            secs.append({"section": s.name, "start": f"{int(a / sr // 60)}:{a / sr % 60:05.2f}",
                         "lufs": round(float(meter.integrated_loudness(seg)), 1),
                         "peak_db": round(20 * np.log10(np.abs(seg).max() + 1e-12), 1)})
        rep["sections"] = secs
    return rep


def spectrogram(x: np.ndarray, path: Path, score: Score, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    mono = x.mean(1)
    f, t, S = signal.spectrogram(mono[:: 2], fx.SR / 2, nperseg=2048, noverlap=1024)
    fig, axes = plt.subplots(2, 1, figsize=(16, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    axes[0].pcolormesh(t, f, 10 * np.log10(S + 1e-12), shading="auto", cmap="magma", vmin=-110, vmax=-30)
    axes[0].set_yscale("symlog", linthresh=200)
    axes[0].set_ylim(30, 11000)
    axes[0].set_ylabel("Hz")
    axes[0].set_title(title)
    hop = int(0.1 * fx.SR)
    env = [20 * np.log10(np.sqrt((mono[i:i + hop] ** 2).mean()) + 1e-9) for i in range(0, len(mono), hop)]
    axes[1].plot(np.arange(len(env)) * 0.1, env, lw=0.6)
    axes[1].set_ylim(-60, 0)
    axes[1].set_ylabel("RMS dB")
    for s in score.sections:
        tt = s.start_bar * 4 * score.beat_s
        for ax in axes:
            ax.axvline(tt, color="cyan", lw=0.6, alpha=0.6)
        axes[0].text(tt + 0.5, 9000, s.name, color="cyan", fontsize=8)
    axes[1].set_xlabel("seconds")
    fig.tight_layout()
    fig.savefig(path, dpi=90)
    plt.close(fig)
