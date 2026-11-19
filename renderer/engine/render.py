"""Render a Score to instrument stems, a pre-master mix and a master."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from scipy.ndimage import uniform_filter1d

from . import drums as D
from . import lmms as LM
from . import fx, synth
from .score import Score, rng_for

PRESETS = Path(__file__).resolve().parent.parent / "presets"

STEMS = ["break", "kick", "snare", "top", "perc", "rush", "bass", "rhodes", "rhodes_solo", "pad", "vibes", "horn", "piano", "atmos", "fx"]
GROUPS = {
    "drums": ["break", "kick", "snare", "top", "perc", "rush"],
    "bass": ["bass"],
    "harmony": ["rhodes", "pad", "piano"],
    "melody": ["horn", "vibes", "rhodes_solo"],
    "atmosphere": ["atmos", "fx"],
}


PARTS = ["bass", "rhodes", "rhodes_solo", "pad", "vibes", "horn", "piano"]
DEFAULT_VOICES = {
    "bass": {"kind": "bass", "preset": "bass-deep.json", "swing": "bass"},
    "rhodes": {"kind": "rhodes", "preset": "rhodes-haze.json", "swing": "rhodes"},
    "rhodes_solo": {"kind": "rhodes", "preset": "rhodes-haze.json", "swing": "melody"},
    "pad": {"kind": "pad", "preset": "pad-night.json", "swing": 0.0},
    "vibes": {"kind": "vibes", "preset": "vibes-motor.json", "swing": "melody"},
    "horn": {"kind": "horn", "preset": "horn-harmon.json", "swing": "melody"},
    "piano": {"kind": "piano", "preset": "piano-rave.json", "swing": "rhodes"},
}


ALBUM_PRESETS: Path | None = None
FALLBACKS: list[str] = []   # parts that should have been LMMS but were rendered by the engine


def preset_path(name: str) -> Path:
    """Album-local presets (<album>/presets) win over the engine's shared ones."""
    if ALBUM_PRESETS and (ALBUM_PRESETS / name).exists():
        return ALBUM_PRESETS / name
    return PRESETS / name


def voice(cfg: dict, part: str) -> dict:
    """Which instrument plays a part ([voices.<part>] kind / preset / label / swing in song.toml)."""
    v = dict(DEFAULT_VOICES.get(part, {"kind": part, "preset": "", "swing": 0.0}))
    v.update(cfg.get("voices", {}).get(part, {}))
    v.setdefault("label", part)
    return v


def groups_for(cfg: dict, stems: dict) -> dict[str, list[str]]:
    """Stem groups, with any extra parts placed by their voice's `group` (default melody)."""
    g = {k: list(v) for k, v in GROUPS.items()}
    known = {m for v in GROUPS.values() for m in v}
    for k in stems:
        if k not in known:
            g.setdefault(cfg.get("voices", {}).get(k, {}).get("group", "melody"), []).append(k)
    return g


def label(cfg: dict, stem: str) -> str:
    return cfg.get("voices", {}).get(stem, {}).get("label", stem)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Timeline:
    def __init__(self, score: Score):
        self.beat_s = score.beat_s
        self.sw = score.cfg.get("swing", {})

    def sec(self, beat: float, swing: float) -> float:
        t = beat * self.beat_s
        step = beat * 4
        r = round(step)
        if abs(step - r) < 1e-6 and r % 2 == 1:
            t += swing * self.beat_s / 4
        return t


def _place(buf, x, t):
    i = int(round(t * fx.SR))
    if i < 0:
        x = x[-i:]
        i = 0
    if i >= len(buf) or len(x) == 0:
        return
    m = min(len(x), len(buf) - i)
    buf[i:i + m] += x[:m]


def automation(score: Score, key: str, default: float, n: int) -> np.ndarray | None:
    """Per-sample curve for an automated parameter (e.g. 'rhodes_lp'), linear within each section."""
    pts_t, pts_v = [], []
    used = False
    for s in score.sections:
        a = s.start_bar * 4 * score.beat_s
        b = (s.start_bar + s.bars) * 4 * score.beat_s
        v = s.cfg.get("auto", {}).get(key)
        if v:
            used = True
            pts_t += [a, b - 1e-3]
            pts_v += [v[0], v[1]]
        else:
            pts_t += [a, b - 1e-3]
            pts_v += [default, default]
    if not used:
        return None
    t = np.arange(0, n, 256) / fx.SR
    # log-frequency interpolation sounds even
    return np.exp(np.interp(t, pts_t, np.log(pts_v)))


def render_notes(score: Score, part: str, kind: str, preset: dict, swing: float, n: int) -> np.ndarray:
    tl = Timeline(score)
    buf = np.zeros(n, np.float32)
    rng = rng_for(score.cfg["seed"], "synth", part)
    notes = score.notes[part]
    if kind == "pad":
        groups: dict[float, list] = {}
        for nt in notes:
            groups.setdefault(round(nt.beat, 4), []).append(nt)
        for b, g in groups.items():
            dur = max(x.dur for x in g) * score.beat_s
            y = synth.pad_chord([x.pitch for x in g], dur, preset, rng) * g[0].vel
            _place(buf, y, tl.sec(b, 0))
        return buf
    prev = None
    for nt in notes:
        t = tl.sec(nt.beat, swing) + nt.shift
        dur = nt.dur * score.beat_s
        if kind == "rhodes":
            y = synth.rhodes_note(nt.pitch, nt.vel, dur, preset, rng)
        elif kind == "bass":
            bright = float(nt.tag.split("=")[1]) if nt.tag.startswith("bright=") else 1.0
            y = synth.bass_note(nt.pitch, nt.vel, dur, preset, rng, from_midi=prev.pitch if (nt.slide and prev) else None, bright=bright)
        elif kind == "vibes":
            y = synth.vibes_note(nt.pitch, nt.vel, dur, preset, rng)
        elif kind == "horn":
            legato = prev is not None and 0 <= nt.beat - (prev.beat + prev.dur) < 0.13 and abs(nt.pitch - prev.pitch) <= 5
            y = synth.horn_note(nt.pitch, nt.vel, dur, preset, rng, from_midi=prev.pitch if legato else None)
        elif kind == "piano":
            y = synth.piano_note(nt.pitch, nt.vel, dur, preset, rng)
        elif kind == "sampler":
            y = synth.sampler_note(nt.pitch, nt.vel, dur, preset, rng)
        elif kind == "analogbass":
            y = synth.analog_bass_note(nt.pitch, nt.vel, dur, preset, rng, from_midi=prev.pitch if (nt.slide and prev) else None)
        elif kind == "koto":
            semis = synth.koto_bend_ok(preset, rng)
            y = synth.guitar_note(nt.pitch, nt.vel, dur, preset, rng,
                                  from_midi=nt.pitch - semis if semis else None, keep_pluck=True)
        elif kind == "shamisen":
            near = prev is not None and 0 <= nt.beat - (prev.beat + prev.dur) < 0.13
            slide = near and nt.slide and abs(nt.pitch - prev.pitch) <= 5
            y = synth.shamisen_note(nt.pitch, nt.vel, dur, preset, rng, from_midi=prev.pitch if slide else None)
        elif kind == "guitar":
            near = prev is not None and 0 <= nt.beat - (prev.beat + prev.dur) < 0.13
            slide = near and nt.slide and abs(nt.pitch - prev.pitch) <= 5
            y = synth.guitar_note(nt.pitch, nt.vel, dur, preset, rng,
                                  from_midi=prev.pitch if slide else None, legato=near and nt.tag == "legato")
        elif kind == "reese":
            y = synth.reese_note(nt.pitch, nt.vel, dur, preset, rng, from_midi=prev.pitch if (nt.slide and prev) else None)
        elif kind == "organ":
            y = synth.organ_note(nt.pitch, nt.vel, dur, preset, rng)
        elif kind == "stab":
            y = synth.stab_note(nt.pitch, nt.vel, dur, preset, rng)
        elif kind == "vox":
            legato = prev is not None and 0 <= nt.beat - (prev.beat + prev.dur) < 0.13 and abs(nt.pitch - prev.pitch) <= 5
            y = synth.vox_note(nt.pitch, nt.vel, dur, preset, rng, from_midi=prev.pitch if legato else None)
        elif kind == "signals":
            y = synth.signal_blip(nt.pitch, dur, rng) * nt.vel
        else:
            raise ValueError(kind)
        _place(buf, y, t)
        prev = nt
    return buf


def render_drums(score: Score, n: int) -> tuple[dict[str, np.ndarray], list[float]]:
    tl = Timeline(score)
    sw = score.cfg.get("swing", {})
    bcfg = score.cfg.get("breaks", {})
    kit_cfg = score.cfg.get("kit", {})
    used = {h.src for _, hits in score.drum_hits["break"] + score.drum_hits["rush"] for h in hits}
    smp = {k: bcfg[k] for k in ("bits", "rate", "filtered") if k in bcfg}
    breaks = {name: D.record_break(name, bcfg.get("record_bpm"), kit_cfg.get("break"), smp) for name in sorted(used)}
    sampler = D.Sampler(breaks, score.bpm)
    kit = D.Kit(score.cfg["seed"], kit_cfg)
    out = {k: np.zeros(n, np.float32) for k in ("break", "kick", "snare", "top", "perc", "rush")}
    kicks: list[float] = []
    for sec, hits in score.drum_hits["break"]:
        dr = sec.cfg["drums"]
        S0 = sec.start_bar * 4 * score.beat_s
        m = int((sec.bars * 4 * score.beat_s + 2.0) * fx.SR)
        rng = rng_for(score.cfg["seed"], sec.name, "drum-render")
        buf, trig = D.render_hits(hits, sampler, score.beat_s, sw.get("drums", 0.16), m, rng)
        auto = sec.cfg.get("auto", {})
        if "break_hp" in auto:
            buf = fx.sweep(buf, "highpass", np.geomspace(*auto["break_hp"], 64), order=2)
        if "break_lp" in auto:
            buf = fx.sweep(buf, "lowpass", np.geomspace(*auto["break_lp"], 64), order=2)
        _place(out["break"], buf, S0)
        de, dx = dr.get("enter", {}), dr.get("exit", {})
        bar_s = 4 * score.beat_s
        for t, cls, v in ([] if dr.get("pattern") else trig):
            bar = int(t // bar_s)
            if cls == "K" and not (de.get("kick", 0) <= bar < dx.get("kick", sec.bars)):
                continue
            if cls == "S" and not (de.get("snare", 0) <= bar < dx.get("snare", sec.bars)):
                continue
            if cls == "K" and v >= 0.55 and dr.get("kick", 0) > 0:
                D.place(out["kick"], kit.get("kick"), S0 + t, v * dr["kick"])
                kicks.append(S0 + t)
            if cls == "S" and v >= 0.7 and dr.get("snare", 0) > 0:
                D.place(out["snare"], kit.get("snare"), S0 + t + 0.002, v * dr["snare"])
    for sec, hits in score.drum_hits["rush"]:
        S0 = sec.start_bar * 4 * score.beat_s
        m = int((sec.bars * 4 * score.beat_s + 1.0) * fx.SR)
        buf, _ = D.render_hits(hits, sampler, score.beat_s, 0.0, m, rng_for(score.cfg["seed"], sec.name, "rush-render"))
        _place(out["rush"], buf, S0)
    rng = rng_for(score.cfg["seed"], "layers")
    for stem in ("top", "perc", "kick", "snare"):
        for beat, kind, v in score.layer_hits[stem]:
            jitter = 0.0 if stem == "kick" else rng.normal(0, 0.003)
            t = tl.sec(beat, sw.get("hats", 0.2) if stem in ("top", "perc") else sw.get("drums", 0.0)) + jitter
            D.place(out[stem], kit.get(kind), t, v)
            if stem == "kick":
                kicks.append(t)
    # keep the breaks' own recordings next to the project for re-use
    return out, kicks, breaks


def section_gain(score: Score, name: str, n: int) -> np.ndarray | None:
    """Per-section level offsets (sections[].levels.<stem> in dB), ramped over one beat."""
    if not any(name in s.cfg.get("levels", {}) for s in score.sections):
        return None
    g = np.ones(n, np.float32)
    for s in score.sections:
        d = s.cfg.get("levels", {}).get(name)
        if d is not None:
            a = int(s.start_bar * 4 * score.beat_s * fx.SR)
            b = int((s.start_bar + s.bars) * 4 * score.beat_s * fx.SR)
            if isinstance(d, list):      # [from_dB, to_dB]: a swell or a fade across the section
                g[a:b] = fx.db(np.linspace(d[0], d[1], b - a))
            else:
                g[a:b] = fx.db(d)
    return uniform_filter1d(g, int(score.beat_s * fx.SR / 4)).astype(np.float32)


def process(name: str, mono: np.ndarray, mix: dict, score: Score, irs: dict, kicks: list[float], n: int) -> np.ndarray:
    m = mix.get(name, {})
    x = mono
    sg = section_gain(score, name, n)
    if sg is not None:
        x = x * (sg if x.ndim == 1 else sg[:, None])
    for key, kind in ((f"{name}_lp", "lowpass"), (f"{name}_hp", "highpass")):
        curve = automation(score, key, 20000.0 if kind == "lowpass" else 20.0, n)
        if curve is not None:
            x = fx.sweep(x, kind, curve, block=256)
    if m.get("eq"):
        x = fx.eq(x, [tuple(b) for b in m["eq"]])
    if m.get("crush"):
        x = fx.crush(x, *m["crush"])
    if m.get("saturate"):
        x = fx.saturate(x, m["saturate"])
    if m.get("akai"):
        x = fx.akai(x, m["akai"])
    if m.get("leslie"):
        # section `leslie = { part = "fast" | "slow" | [from, to] }`
        pts_t, pts_v = [], []
        for sct in score.sections:
            a_ = sct.start_bar * 4 * score.beat_s
            b_ = (sct.start_bar + sct.bars) * 4 * score.beat_s
            v_ = sct.cfg.get("leslie", {}).get(name, m.get("leslie_default", "slow"))
            v_ = [v_, v_] if not isinstance(v_, list) else v_
            v_ = [1.0 if q == "fast" else 0.0 if q == "slow" else float(q) for q in v_]
            pts_t += [a_, b_ - 1e-3]
            pts_v += v_
        sp = np.interp(np.arange(0, len(x), 256) / fx.SR, pts_t, pts_v)
        x = fx.leslie(x, sp, mix=m.get("leslie_mix", 1.0))
    if x.ndim == 1:
        if m.get("autopan"):
            x = fx.autopan(x, *m["autopan"])
        else:
            x = fx.pan(x, m.get("pan", 0.0))
    if m.get("tremolo"):
        x = fx.tremolo(x, *m["tremolo"])
    if m.get("chorus"):
        x = fx.chorus(x, mix=m["chorus"])
    if m.get("width"):
        x = fx.width(x, m["width"])
    if m.get("wow"):
        x = fx.wow(x)
    if m.get("duck"):
        g = fx.duck(n, kicks, m["duck"])
        x = x * g[:, None]
    dry = x
    if m.get("room"):  # the instrument heard through a mic in a small room / in front of its amp
        dry = dry + fx.convolve(dry * m["room"], irs["room"])
    wet = np.zeros_like(dry)
    for send in ("hall", "plate", "echo"):
        if m.get(send):
            wet += fx.convolve(dry * m[send], irs[send])
    if any(m.get(k) for k in ("hall", "plate", "echo")):
        wet = fx.lp(fx.hp(wet, 150), 9500)  # keep the lows out and the tails dark, like 90s units
    y = (dry + wet) * fx.db(m.get("gain", 0.0))
    if name in ("bass", "kick"):
        y = fx.mono_below(y, 140)
    return y.astype(np.float32)


def render(score: Score, out_dir: Path) -> dict:
    global ALBUM_PRESETS
    ALBUM_PRESETS = Path(out_dir).resolve().parent.parent / "presets"
    cfg = score.cfg
    fx.set_rate(cfg.get("sample_rate", 44100))
    total_s = score.total_bars * 4 * score.beat_s + 3.0
    n = int(total_s * fx.SR)
    sw = cfg.get("swing", {})
    mix = cfg.get("mix", {})
    irs = {
        "hall": fx.reverb_ir(2.6, 0.025, damp=0.75, seed=5),
        "plate": fx.reverb_ir(1.1, 0.008, damp=0.45, seed=9, size=0.5),
        "room": fx.reverb_ir(0.32, 0.003, damp=0.7, seed=13, size=0.22) * 0.5,
        "echo": fx.delay_ir(score.beat_s, 0.75, 0.42, 7, 3000),
    }
    for k in ("hall", "plate"):
        irs[k] *= 0.35
    log("drums")
    drum_bufs, kicks, breaks = render_drums(score, n)
    stems: dict[str, np.ndarray] = {}
    for k, v in drum_bufs.items():
        stems[k] = process(k, v, mix, score, irs, kicks, n)
    del drum_bufs
    extras = [k for k in score.notes if k not in PARTS and k != "signals"]
    lmms_parts = {}
    for part in PARTS + extras:
        v = voice(cfg, part)
        if v.get("backend") == "lmms" and score.notes[part]:
            sw_v = sw.get(v["swing"], 0.0) if isinstance(v.get("swing"), str) else v.get("swing", 0.0)
            tl = Timeline(score)
            lmms_parts[part] = (v, LM.to_lmms_notes(score.notes[part], score.beat_s,
                                                      lambda nt, s=sw_v: tl.sec(nt.beat, s) + nt.shift))
    if lmms_parts:
        log("LMMS: " + ", ".join(f"{p} ({lmms_parts[p][0].get('zyn') or lmms_parts[p][0].get('xpf') or lmms_parts[p][0].get('plugin')})" for p in lmms_parts))
        try:
            rendered = LM.render_parts(lmms_parts, score.bpm, n, fx.SR, timeout=1800)
        except Exception as ex:
            # LMMS is optional: if it fails, render each part alone, and fall back to the engine's synth
            log(f"LMMS render failed ({str(ex)[:120]}); retrying part by part")
            rendered = {}
            for part, spec in lmms_parts.items():
                try:
                    rendered.update(LM.render_parts({part: spec}, score.bpm, n, fx.SR, timeout=900))
                except Exception as ex2:
                    log(f"  {part}: LMMS unavailable ({str(ex2)[:80]}) -> engine synth fallback")
                    FALLBACKS.append(part)
        for part, audio in rendered.items():
            v = lmms_parts[part][0]
            if v.get("match", True) and v.get("kind") and str(v.get("preset", "")).endswith(".json") and v.get("kind") != "pad":
                # level-match to the engine synth this LMMS instrument replaces, so the tuned mix holds
                sw_v = sw.get(v["swing"], 0.0) if isinstance(v.get("swing"), str) else v.get("swing", 0.0)
                ref = render_notes(score, part, v["kind"], synth.load_preset(preset_path(v["preset"])), sw_v, n)
                g = active_rms(ref) / max(active_rms(audio), 1e-9)
                g = float(np.clip(g, 1e-3, 1e3))
                log(f"  {part}: level-matched to the engine {v['kind']} ({20 * np.log10(g):+.1f} dB)")
                audio = audio * g
            stems[part] = process(part, audio, mix, score, irs, kicks, n)
    jobs = []
    for part in PARTS + extras:
        if part in lmms_parts and part not in FALLBACKS:
            continue
        v = voice(cfg, part)
        jobs.append((part, v["kind"], v["preset"], sw.get(v["swing"], 0.0) if isinstance(v["swing"], str) else v["swing"]))
    for part, kind, preset, swing in jobs:
        if not score.notes[part]:
            stems[part] = np.zeros((n, 2), np.float32)
            continue
        log(part)
        try:
            p = synth.load_preset(preset_path(preset)) if preset else {}
            mono = render_notes(score, part, kind, p, swing, n)
        except (ValueError, FileNotFoundError, IsADirectoryError) as ex:
            log(f"  {part}: no engine synth for '{kind}' ({ex}); part left silent")
            stems[part] = np.zeros((n, 2), np.float32)
            continue
        stems[part] = process(part, mono, mix, score, irs, kicks, n)
    log("atmosphere")
    stems["atmos"] = render_atmos(score, n, mix, irs, kicks)
    stems["fx"] = process("fx", render_fx(score, n), mix, score, irs, kicks, n) if score.fx_events else np.zeros((n, 2), np.float32)
    log("mix")
    for k in STEMS:
        stems.setdefault(k, np.zeros((n, 2), np.float32))
    premaster = np.zeros((n, 2), np.float32)
    for k in stems:
        premaster += stems[k]
    # one trim for everything so the pre-master (and every stem) has headroom; stems still sum to it
    trim = min(1.0, fx.db(-3.0) / float(np.abs(premaster).max()))
    fade = np.ones(n, np.float32)
    f = int(1.5 * fx.SR)
    fade[-f:] = np.linspace(1, 0, f) ** 2
    drive = cfg.get("master", {}).get("console_drive", 0.0)
    premaster[:] = 0
    for k in stems:
        stems[k] *= trim * fade[:, None]
        if drive:   # every channel through the desk
            stems[k] = fx.console(stems[k], drive)
        premaster += stems[k]
    log(f"mix trim {20 * np.log10(trim):.1f} dB")
    return {"stems": stems, "premaster": premaster, "kicks": kicks, "breaks": breaks, "n": n, "trim_db": 20 * np.log10(trim)}


def render_atmos(score: Score, n: int, mix: dict, irs: dict, kicks) -> np.ndarray:
    rng = rng_for(score.cfg["seed"], "atmos")
    env = {"vinyl": np.zeros(n, np.float32), "haze": np.zeros(n, np.float32)}
    fade = int(2 * score.beat_s * fx.SR)
    for s in score.sections:
        a = int(s.start_bar * 4 * score.beat_s * fx.SR)
        b = int((s.start_bar + s.bars) * 4 * score.beat_s * fx.SR)
        for k in env:
            if k in s.cfg.get("atmos", []):
                env[k][a:b] = 1.0
    for k in env:  # smooth section edges
        env[k] = uniform_filter1d(env[k], fade).astype(np.float32)
    # the record keeps crackling a little after the music stops
    end = int(score.total_bars * 4 * score.beat_s * fx.SR)
    env["vinyl"][end:] = np.linspace(env["vinyl"][end - 1], 0, n - end)
    tex = synth.vinyl(n, rng) * env["vinyl"][:, None] * 0.5 if env["vinyl"].any() else np.zeros((n, 2), np.float32)
    if env["haze"].any():
        tex += synth.haze(n, rng) * env["haze"][:, None]
    if any(k in s.cfg.get("atmos", []) for s in score.sections for k in ("waves", "wind", "rain", "thunder")):
        tex += ocean(score, n, rng)
    sig_preset = None
    sig = render_notes(score, "signals", "signals", sig_preset, 0.0, n)
    sig = fx.pan(sig, 0.0)
    t = np.arange(n) / fx.SR
    sig = sig * np.stack([0.75 + 0.25 * np.sin(2 * np.pi * 0.13 * t), 0.75 - 0.25 * np.sin(2 * np.pi * 0.13 * t)], 1) * 0.25
    x = tex + sig.astype(np.float32)
    m = mix.get("atmos", {})
    if "eq" in m:
        x = fx.eq(x, [tuple(bd) for bd in m["eq"]])
    wet = np.zeros_like(x)
    for send in ("hall", "echo"):
        if m.get(send):
            wet += fx.convolve(sig.astype(np.float32) * m[send] * 2, irs[send])
    return ((x + wet) * fx.db(m.get("gain", 0))).astype(np.float32)


def master(premaster: np.ndarray, cfg: dict) -> tuple[np.ndarray, dict]:
    import pyloudnorm as pyln
    mc = cfg.get("master", {})
    x = premaster
    if mc.get("hp"):                           # subsonic clean-up before anything reacts to it
        x = fx.filt(x, "highpass", mc["hp"], 4)
    x = fx.mono_below(x, mc.get("mono_below", 110))
    meter = pyln.Meter(fx.SR)
    comp_info = {}
    if mc.get("tape"):
        # print to tape at a sensible operating level (-18 LUFS ~ 0 VU), then master from it
        x = x * fx.db(-18 - meter.integrated_loudness(x.astype(np.float64)))
        x = fx.tape(x, **mc["tape"])
    g = mc.get("glue", {})
    if g:
        x = fx.compress(x, g["threshold"], g["ratio"], g["attack"], g["release"])
    if mc.get("saturate"):
        x = fx.saturate(x, mc["saturate"])
    if mc.get("eq"):                           # mastering EQ: [[type, freq, gain, q], ...] as fx.eq
        x = fx.eq(x, [tuple(b) for b in mc["eq"]]).astype(np.float32)
    if mc.get("multiband"):                    # {"freqs": [150, 5000], "bands": [{glue args}, ...]}: band-wise control
        x, comp_info["multiband_gr_db_p99"] = fx.multiband(x, mc["multiband"]["freqs"], mc["multiband"]["bands"])
    if mc.get("bus_comp"):                     # the glue compressor proper (fx.glue: RMS, soft knee, sidechain high-pass)
        x, gr = fx.glue(x, **mc["bus_comp"])
        comp_info["bus_comp_gr_db_p99"], comp_info["bus_comp_gr_db_mean"] = float(np.percentile(gr, 99)), float(gr.mean())
    if mc.get("width"):                        # overall stereo width (the lows stay mono below)
        x = fx.mono_below(fx.width(x, mc["width"]), 150)
    lufs = meter.integrated_loudness(x.astype(np.float64))
    gain_db = mc.get("target_lufs", -12.0) - lufs
    x = x * fx.db(gain_db)
    if mc.get("clip") is not None:              # a 4x-oversampled soft clipper ahead of the limiter: shaves transient spikes
        from scipy import signal as _sig        # (drums) by a dB or two so the limiter barely has to work; clip = dB over the ceiling
        t = fx.db(mc.get("ceiling", -1.0) + mc["clip"])
        xo = _sig.resample_poly(x, 4, 1, axis=0)
        pk = np.maximum(np.abs(xo).max(axis=1, keepdims=True), 1e-9)       # linked: one gain for both channels keeps the image
        x = _sig.resample_poly(xo * (t * np.tanh(pk / t) / pk), 1, 4, axis=0).astype(np.float32)
    pre_peak = float(np.abs(x).max())
    if mc.get("true_peak") is not None:         # a true-peak limiter: limit at 4x oversampling, so the peaks between samples
        from scipy import signal as _sig        # are caught too (same 4 ms look-ahead / 80 ms release in real time)
        xo = _sig.resample_poly(x, 4, 1, axis=0).astype(np.float32)
        y = _sig.resample_poly(fx.limiter(xo, min(mc.get("ceiling", -1.0), mc["true_peak"]), lookahead=0.016, release=0.32), 1, 4, axis=0).astype(np.float32)
    else:
        y = fx.limiter(x, mc.get("ceiling", -1.0))
    # how hard the limiter worked
    blk = 441                                    # measured on 10 ms windows (per-sample ratios are meaningless near zero crossings)
    nb = min(len(x), len(y)) // blk
    pk = lambda a: np.abs(a[:nb * blk]).max(1).reshape(nb, blk).max(1)
    red = 20 * np.log10(np.maximum(pk(y), 1e-9) / np.maximum(pk(x), 1e-9))
    tp_trim = 0.0
    if mc.get("true_peak") is not None:         # a safety trim if the downsampling still left a true peak over
        tp = 20 * np.log10(np.abs(_sig.resample_poly(y, 4, 1, axis=0)).max() + 1e-12)
        if tp > mc["true_peak"]:
            tp_trim = mc["true_peak"] - tp
            y = (y * fx.db(tp_trim)).astype(np.float32)
    info = {"pre_lufs": float(lufs), "gain_db": float(gain_db), "peak_before_limiter_db": 20 * np.log10(pre_peak),
            "limiter_max_reduction_db": float(-red.min()),
            "limiter_time_over_1db_s": float((red < -1).sum() * blk / fx.SR), "true_peak_trim_db": float(tp_trim), **comp_info}
    return y.astype(np.float32), info


def render_fx(score: Score, n: int) -> np.ndarray:
    """Build-up and drop effects: filtered noise risers, reverse cymbals into the downbeat, sub booms."""
    out = np.zeros((n, 2), np.float32)
    rng = rng_for(score.cfg["seed"], "fx")
    for kind, a, b, lvl in score.fx_events:
        t0, t1 = a * score.beat_s, b * score.beat_s
        i0, i1 = int(t0 * fx.SR), min(n, int(t1 * fx.SR))
        m = i1 - i0
        if m <= 0:
            continue
        if kind == "riser":
            ramp = np.linspace(0, 1, m) ** 2
            seg = np.zeros((m, 2), np.float32)
            for c in range(2):
                nz = rng.standard_normal(m).astype(np.float32)
                x = fx.sweep(nz, "highpass", np.geomspace(250, 2500, 64), order=2)
                x = fx.sweep(x, "lowpass", np.geomspace(900, 11000, 64), order=2)
                seg[:, c] = x * ramp * 0.35 * float(lvl)
            out[i0:i1] += seg
        elif kind == "revcrash":
            c = D.Kit(int(rng.integers(1 << 30))).get("crash")[: m][::-1].copy()
            pad = np.zeros(m, np.float32)
            pad[m - len(c):] = c
            out[i0:i1] += np.stack([pad * 0.9, pad * 0.7], 1) * 0.6 * float(lvl)
        elif kind == "boom":
            k = synth.kick(rng, 1.0, start=90, end=38, decay=0.7, click=0.05, body=0.0, sweep=0.06)
            j = min(len(k), n - i0)
            out[i0:i0 + j] += np.stack([k[:j], k[:j]], 1) * 0.5 * float(lvl)
    return out


def storm_curve(score: Score, n: int) -> np.ndarray:
    """Per-sample storm intensity 0..1 from each section's `storm = [from, to]` (or a number)."""
    pts_t, pts_v = [], []
    for s in score.sections:
        a = s.start_bar * 4 * score.beat_s
        b = (s.start_bar + s.bars) * 4 * score.beat_s
        v = s.cfg.get("storm", 0.0)
        v = v if isinstance(v, list) else [v, v]
        pts_t += [a, b - 1e-3]
        pts_v += v
    t = np.arange(n) / fx.SR
    return np.interp(t, pts_t, pts_v).astype(np.float32)


def ocean(score: Score, n: int, rng) -> np.ndarray:
    """The sea and the weather: waves breaking in slow swells, wind that rises and whistles, rain,
    and thunder, each scaled by the storm curve and switched on per section via `atmos`."""
    st = storm_curve(score, n)
    on = {k: np.zeros(n, np.float32) for k in ("waves", "wind", "rain", "thunder")}
    for s in score.sections:
        a = int(s.start_bar * 4 * score.beat_s * fx.SR)
        b = int((s.start_bar + s.bars) * 4 * score.beat_s * fx.SR)
        for k in on:
            if k in s.cfg.get("atmos", []):
                on[k][a:b] = 1
    fade = int(2.0 * fx.SR)
    for k in on:
        on[k] = uniform_filter1d(on[k], fade)
    out = np.zeros((n, 2), np.float32)
    t = np.arange(n) / fx.SR
    if on["waves"].any():
        # each wave: a slow rise, the break (bright foam), a long wash back; bigger as the storm grows
        env = np.zeros(n, np.float32)
        foam = np.zeros(n, np.float32)
        pos = 0.0
        while pos < n / fx.SR:
            per = rng.uniform(5.5, 9.0) * (1 - 0.35 * st[min(int(pos * fx.SR), n - 1)])
            i0 = int(pos * fx.SR)
            L = int(per * fx.SR * 1.4)
            tt = np.arange(L) / fx.SR
            rise, peak = per * 0.45, 1.0 + 0.8 * st[min(i0, n - 1)]
            w = np.where(tt < rise, (tt / rise) ** 2, np.exp(-(tt - rise) / (per * 0.35))) * peak
            f = np.where(tt < rise, 0, np.exp(-(tt - rise) / 0.9)) * peak
            m = min(L, n - i0)
            env[i0:i0 + m] = np.maximum(env[i0:i0 + m], w[:m])
            foam[i0:i0 + m] = np.maximum(foam[i0:i0 + m], f[:m])
            pos += per
        for c in range(2):
            nz = rng.standard_normal(n).astype(np.float32)
            body = fx.lp(nz, 900, 2) * env
            spray = fx.bp(rng.standard_normal(n).astype(np.float32), 2500, 9000) * foam
            out[:, c] += (0.12 * body + 0.035 * spray) * on["waves"]
    if on["wind"].any():
        for c in range(2):
            nz = rng.standard_normal(n).astype(np.float32)
            centre = 350 + 900 * st + 250 * np.sin(2 * np.pi * 0.07 * t + c) + 150 * np.sin(2 * np.pi * 0.23 * t + 2 * c)
            gust = 0.55 + 0.45 * np.sin(2 * np.pi * 0.11 * t + c * 1.3) * np.sin(2 * np.pi * 0.037 * t)
            x = fx.sweep(nz, "lowpass", centre[::512], block=512)
            x = fx.hp(x, 160)
            out[:, c] += x * gust * (0.02 + 0.13 * st ** 1.5) * on["wind"]
    if on["rain"].any():
        for c in range(2):
            drops = (rng.random(n) < (400 + 6000 * st) / fx.SR).astype(np.float32) * rng.random(n).astype(np.float32)
            x = fx.bp(drops, 2000, 12000) * 0.8 + fx.bp(rng.standard_normal(n).astype(np.float32), 3000, 10000) * 0.05
            out[:, c] += x * st ** 2 * on["rain"] * 0.5
    if on["thunder"].any():
        pos = 0.0
        while pos < n / fx.SR - 6:
            i0 = int(pos * fx.SR)
            if st[i0] > 0.55 and on["thunder"][i0] > 0.5 and rng.random() < 0.5 * st[i0]:
                L = int(6 * fx.SR)
                tt = np.arange(L) / fx.SR
                rumble = fx.lp(rng.standard_normal(L).astype(np.float32), 160, 2) * np.exp(-tt / 2.2) * (1 - np.exp(-tt / 0.08))
                rumble *= 1 + 0.5 * np.sin(2 * np.pi * 1.3 * tt)
                crack = fx.bp(rng.standard_normal(L).astype(np.float32), 300, 3000) * np.exp(-tt / 0.25) * 0.4
                th = (rumble * 2.4 + crack) * st[i0]
                m = min(L, n - i0)
                pan = rng.uniform(-0.6, 0.6)
                out[i0:i0 + m, 0] += th[:m] * (1 - pan) * 0.5
                out[i0:i0 + m, 1] += th[:m] * (1 + pan) * 0.5
                pos += rng.uniform(5, 11)
            else:
                pos += 2.0
    return out


def active_rms(x: np.ndarray) -> float:
    """RMS over the frames where the part is actually playing (within 40 dB of its loudest frame)."""
    m = x.mean(1) if x.ndim == 2 else x
    fr = 2048
    k = len(m) // fr
    if k == 0:
        return float(np.sqrt((m ** 2).mean()))
    r = np.sqrt((m[:k * fr].reshape(k, fr) ** 2).mean(1))
    act = r[r > r.max() * 0.01]
    return float(np.sqrt((act ** 2).mean())) if len(act) else 0.0
