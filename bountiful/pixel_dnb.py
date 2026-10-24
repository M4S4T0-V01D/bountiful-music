#!/usr/bin/env python3
"""'Copper Bars': a demoscene / tracker-style slow jazzy drum & bass at 130 bpm, C# minor (C#m9 - Amaj9 - F#m9 - E9, the
lift C#m9 - Amaj9 - Esus2 - Emaj9). Everything is pixel: our own chip drum kit (synthesised here like a NES APU: a stepped
triangle kick and toms, LFSR noise snares and hats, 16-level stepped envelopes), tracker arpeggios on a SID-style patch
(chords played as fast 32nd-note cycles, the classic one-channel chord), square and pulse pads, a pulse-width vibrato lead
with a dotted-8th echo, a BitInvader e-piano comping the jazz chords and a rolling sub with a SID bass on top. Two-step
breaks with ghost snares, a shuffled hat, chip snare rolls and triangle tom runs as fills.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/pixel_dnb.py            # samples + build
    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/pixel_dnb.py --samples  # only the chip kit
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import album_mezzanine_v2 as A2  # noqa: E402
import lmms_tracks as LT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "samples" / "pixel"
BPM = 130
SR = 44100
blk, kit, zyn, xpf = A2.blk, A2.kit, A2.zyn, A2.xpf


# ------------------------------------------------------------------ the chip kit (a NES-style APU, offline)

def frames(env: np.ndarray, rate=240) -> np.ndarray:
    """A 16-level envelope that only moves on the APU frame clock (240 Hz): the stepped 'pixel' decay."""
    hold = SR // rate
    idx = (np.arange(len(env)) // hold) * hold
    return np.round(np.clip(env[idx], 0, 1) * 15) / 15


def noise(n: int, clock: float, short=False, seed=1) -> np.ndarray:
    """The 15-bit LFSR noise channel; short mode (tap 6) is the metallic, pitched one."""
    reg, acc, out = seed, 0.0, np.empty(n)
    step, tap = clock / SR, 6 if short else 1
    bit = 1.0
    for i in range(n):
        acc += step
        while acc >= 1.0:
            acc -= 1.0
            fb = (reg ^ (reg >> tap)) & 1
            reg = (reg >> 1) | (fb << 14)
            bit = -1.0 if reg & 1 else 1.0
        out[i] = bit
    return out


def triangle(freq: np.ndarray) -> np.ndarray:
    """The 32-step triangle (4-bit DAC): stepped, buzzy in the overtones, round in the bass."""
    ph = np.cumsum(freq / SR) % 1.0
    k = np.floor(ph * 32)
    return (np.where(k < 16, 15 - k, k - 16) / 7.5) - 1.0


def pulse(freq: np.ndarray, duty=0.25) -> np.ndarray:
    ph = np.cumsum(freq / SR) % 1.0
    return np.where(ph < duty, 1.0, -1.0)


def sweep(n, f0, f1, ms):
    t = np.arange(n) / SR
    return f1 + (f0 - f1) * np.exp(-t / (ms / 1000))


def decay(n, ms, curve=1.0):
    t = np.arange(n) / SR
    return np.exp(-t / (ms / 1000)) ** curve


def save(name, x, gain=0.9):
    x = x / (np.abs(x).max() + 1e-9) * gain
    x = np.round(x * 127) / 127                                     # an 8-bit DAC
    fade = int(0.002 * SR)
    x[-fade:] *= np.linspace(1, 0, fade)
    sf.write(str(KIT / f"{name}.wav"), x.astype(np.float32), SR, subtype="PCM_16")


def build_kit():
    KIT.mkdir(parents=True, exist_ok=True)
    n = lambda s: int(s * SR)
    # kick: a triangle diving 240 -> 46 Hz, a noise tick on top
    k = n(0.36)
    kick = triangle(sweep(k, 240, 46, 22)) * frames(decay(k, 170) * np.where(np.arange(k) < n(0.26), 1, decay(k, 40)))
    kick[:n(0.012)] += 0.5 * noise(n(0.012), 90000, seed=3) * frames(decay(n(0.012), 4))
    save("kick", kick, 0.95)
    # snare: bright long-mode noise and a triangle body 230 -> 150 Hz
    s = n(0.24)
    body = triangle(sweep(s, 260, 150, 25)) * frames(decay(s, 45))
    save("snare", 0.75 * noise(s, 26000, seed=5) * frames(decay(s, 85)) + 0.7 * body, 0.9)
    g = n(0.08)
    save("ghost", noise(g, 30000, seed=9) * frames(decay(g, 22)) + 0.3 * triangle(sweep(g, 240, 180, 20)) * frames(decay(g, 18)), 0.5)
    # hats: short-mode (metallic) noise at the top clock
    h = n(0.05)
    save("hat", noise(h, 110000, short=True, seed=17) * frames(decay(h, 12)), 0.55)
    o = n(0.3)
    save("open", noise(o, 110000, short=True, seed=23) * frames(decay(o, 90)), 0.55)
    # ride: metallic noise and a thin 12.5% pulse ping
    r = n(0.6)
    save("ride", 0.7 * noise(r, 70000, short=True, seed=29) * frames(decay(r, 160)) + 0.35 * pulse(np.full(r, 1567.98), 0.125) * frames(decay(r, 120)), 0.5)
    c = n(1.5)
    save("crash", noise(c, 60000, seed=31) * frames(decay(c, 450)), 0.6)
    m = n(0.04)
    save("rim", pulse(np.full(m, 1760.0), 0.125) * frames(decay(m, 10)) + 0.4 * noise(m, 50000, seed=37) * frames(decay(m, 5)), 0.5)
    for name, f0, f1 in (("tom_hi", 360, 190), ("tom_mid", 270, 130), ("tom_lo", 190, 85)):
        t = n(0.28)
        save(name, triangle(sweep(t, f0, f1, 60)) * frames(decay(t, 110)), 0.8)
    print(f"chip kit: {KIT} ({len(list(KIT.glob('*.wav')))} sounds)")


# ------------------------------------------------------------------ the beat: two-step at 130, shuffled hats, ghost snares

HAT = [[s, 0.55 if s % 4 == 2 else 0.42 if s % 2 == 0 else 0.22] for s in range(16)]
GRID = {
    "kick": {"a": [[0, 1.0], [10, 0.92]], "b": [[0, 1.0], [2, 0.7], [10, 0.9]], "c": [[0, 1.0], [10, 0.92]], "d": [[0, 1.0], [10, 0.9], [11, 0.6]]},
    "snare": [[4, 1.0], [12, 1.0]],
    "ghost": {"a": [[7, 0.3], [9, 0.24]], "b": [[3, 0.22], [15, 0.32]], "c": [[6, 0.24], [9, 0.28]], "d": [[7, 0.26], [14, 0.3], [15, 0.36]]},
    "hat": HAT,
    "open": {"a": [], "b": [[14, 0.42]], "c": [], "d": [[6, 0.4]]},
    "ride": [[s, 0.5 if s % 4 == 0 else 0.34] for s in range(0, 16, 2)],
    "rim": {"a": [[11, 0.32]], "b": [], "c": [[7, 0.3]], "d": [[15, 0.34]]},
}
BEAT = [[0, 1.0, "kick"], [4, 1.0, "snare"]]
FILLS = {
    "FA": BEAT + [[8 + i, 0.4 + 0.07 * i, "snare"] for i in range(8)],                                     # chip snare roll up
    "FB": BEAT + [[8, 0.8, "tom_hi"], [9, 0.75, "tom_hi"], [10, 0.8, "tom_mid"], [11, 0.75, "tom_mid"],
                  [12, 0.85, "tom_lo"], [13, 0.8, "tom_lo"], [14, 0.85, "tom_lo"], [15, 0.7, "snare"]],     # triangle tom run
    "FC": BEAT + [[7, 0.3, "ghost"], [10, 0.9, "kick"], [12, 1.0, "snare"], [14, 0.7, "snare"], [15, 0.8, "snare"]],
    "FD": [[12 + i / 2, 0.3 + 0.07 * i, "snare"] for i in range(8)],                                        # 32nd roll pickup
    "FE": BEAT + [[6, 0.3, "ghost"], [8, 0.9, "tom_hi"], [10, 0.9, "kick"], [11, 0.8, "tom_mid"], [12, 1.0, "snare"],
                  [13, 0.8, "tom_lo"], [14.5, 0.6, "snare"], [15, 0.7, "snare"], [15.5, 0.8, "snare"]],
}
GRID |= FILLS
DR = ["kick", "snare", "ghost", "hat"]


def groove(name, loop, parts, drums, fills, **kw):
    """8-bar phrases: 7 bars of groove and a fill bar, each fill its own edit."""
    out = []
    for k, f in enumerate(fills):
        out += [blk(name + (f" {k + 1}" if len(fills) > 1 else ""), loop, 7, parts, drums, **(kw if k == 0 else {})),
                blk(f"{name}: fill {f}", loop, 1, parts, [f, "hat"])]
    return out


ARR = ([blk("Boot: pixel pads", "A", 8, ["pad", "arp"]),
        blk("Scroller", "A", 7, ["pad", "arp", "lead"], ["hat", "rim"], lead_var="sparse"),
        blk("Scroller: pickup", "A", 1, ["pad", "arp", "lead"], ["hat", "FD"], lead_var="sparse")]
       + groove("Pixel break", "A", ["lead", "pad", "arp", "bass", "bass_mid"], DR, ["FA", "FB"], crash=True)
       + groove("Copper bars", "B", ["lead", "comp", "pad", "bass", "bass_mid"], ["kick", "snare", "ghost", "ride", "open"], ["FC", "FE"], crash=True)
       + [blk("Breakdown: jazz in 8 bits", "A", 8, ["comp", "pad", "arp"]),
          blk("Breakdown: the scroller returns", "A", 7, ["comp", "pad", "arp", "lead"], ["hat", "rim"], lead_var="sparse"),
          blk("Breakdown: pickup", "A", 1, ["comp", "pad", "arp", "lead"], ["hat", "FD"], lead_var="sparse")]
       + groove("Second scene", "A", ["lead", "comp", "pad", "arp", "bass", "bass_mid"], DR + ["open"], ["FB", "FA"], crash=True)
       + groove("Last copper", "B", ["lead", "comp", "pad", "arp", "bass", "bass_mid"], ["kick", "snare", "ghost", "ride", "open"], ["FE", "FC"])
       + [blk("End scroller", "A", 8, ["pad", "arp", "lead"], ["hat", "ride"], lead_var="sparse", crash=True),
          blk("Credits", "A", 4, ["pad"])])
ALL = sum(b["bars"] for b in ARR)
at = lambda name: A2.bars_upto(ARR, name)


def chip_kit():
    p = lambda s: str(KIT / f"{s}.wav")
    return kit({"kick": (p("kick"), "kick", {"detune_cents": 0}), "snare": (p("snare"), "snare", {"detune_cents": 0}),
                "ghost": (p("ghost"), "snare", {"detune_cents": 0}), "hat": (p("hat"), "hats", {"detune_cents": 0}),
                "open": (p("open"), "hats", {"detune_cents": 0}), "ride": (p("ride"), "ride", {"detune_cents": 0}),
                "crash": (p("crash"), "ride", {"detune_cents": 0}), "rim": (p("rim"), "perc", {"detune_cents": 0}),
                "tom_hi": (p("tom_hi"), "perc", {"detune_cents": 0}), "tom_mid": (p("tom_mid"), "perc", {"detune_cents": 0}),
                "tom_lo": (p("tom_lo"), "perc", {"detune_cents": 0})},
               {"kick": {"hp": 28, "mono": True, "drive": 1.4, "gain_db": -3.0},
                "snare": {"hp": 120, "sends": {"room": 0.15}, "gain_db": -4.0},
                "hats": {"hp": 3000, "pan": 0.15, "sends": {"room": 0.1}, "gain_db": -9.0},
                "ride": {"hp": 1500, "pan": -0.2, "sends": {"room": 0.15}, "gain_db": -13.0},
                "perc": {"hp": 60, "pan": -0.1, "sends": {"room": 0.2, "echo": 0.08}, "gain_db": -6.0}})


SPEC = {
    "title": "Copper Bars", "song": ROOT / "songs" / "lofi-downtempo" / "lofi-downtempo-1941868402.am.json", "genre": "lofi-downtempo",
    "rebuild": "bountiful/pixel_dnb.py", "composer": A2.COMPOSER, "artist": A2.ARTIST, "album": "", "year": A2.YEAR,
    "blurb": ("Demoscene / tracker-style slow jazzy drum & bass at 130 bpm in C# minor (C#m9 - Amaj9 - F#m9 - E9, lifting to "
              "Esus2 - Emaj9): our own NES-style chip drum kit (stepped triangle kick and toms, LFSR noise snares and hats) in a "
              "two-step break, tracker arpeggios, square and pulse pads, a pulse-width vibrato lead with a dotted echo, a chip "
              "e-piano on the jazz chords and a rolling sub."),
    "overrides": {"name": "Demoscene Drum & Bass", "bpm": BPM, "swing": 0.55, "drums": "grid", "grid": GRID, "arrangement": ARR, "drum_cycle_per_block": True,
                  "loop_continuous": True, "drum_humanize_ms": 3,
                  "harmony": {"rhythm": 1, "dominant": "keep", "colors": {"m": "m9", "": "maj9", "m7": "m9", "7": "9", "maj7": "maj9"}},
                  "melody": {"writer": "motif", "rhythm": "smooth", "register": [68, 87], "range_min": 12, "density": 0.75,
                             "articulation": "legato", "humanize_ms": 4, "swing": 0.55, "velocity": [0.6, 0.9]},
                  "bass": {"style": "pattern", "register": [30, 45], "humanize_ms": 0,
                           "pattern": [[0, "R", 1.3, 1.0], [6, "R", 0.25, 0.7], [10, "R", 0.8, 0.9], [14, "5", 0.4, 0.75]]},
                  "comp": {"steps": [0, 7, 11], "low": 56, "high": 76, "top": 73, "notes": 4, "gate": 0.7, "strum_ms": 10,
                           "humanize_ms": 4, "vel": 0.55, "accent": 0.68},
                  "arp": {"low": 61, "high": 85, "rate": 0.125, "gate": 0.11, "pattern": [0, 1, 2, 3, 4, 5, 6, 5, 4, 3, 2, 1], "humanize_ms": 0},
                  "pad": {"low": 52, "high": 76, "top": 71, "notes": 4, "vel": 0.5},
                  "master": {"tape": {"drive": 1.15, "bias": 0.02, "bump_db": 0.8, "hf_db": 0.0, "lp_hz": 18500, "hiss_db": -90, "wow_ms": 0.0},
                             "glue": {"threshold": -15.0, "ratio": 2.0, "attack": 0.015, "release": 0.2},
                             "target_lufs": -10.0, "ceiling": -1.0, "clip": 2.0, "true_peak": -1.0}},
    "kit_def": chip_kit(),
    "layers": [("bass", "bass_mid"), ("pad", "choir")],
    "sends": {"echo": {"type": "delay", "time_beats": 0.75, "feedback": 0.4, "tone": 3200},
              "plate": {"type": "reverb", "seconds": 2.8, "predelay": 0.03, "damp": 0.45}},
    "voices": {
        "lead": (*zyn("Laba170bank/0136-chip-PWM-VibratoLead.xiz", "chip PWM VibratoLead (ZynAddSubFX - Laba170bank)"),
                 dict(hp=250, sends={"echo": 0.3, "plate": 0.18}, width=1.0, gain_db=-6.0)),
        "arp": (*zyn("Laba170bank/0130-chip-SIDarpSoft.xiz", "chip SIDarpSoft (ZynAddSubFX - Laba170bank), tracker arpeggios"),
                dict(hp=400, pan=-0.15, sends={"echo": 0.18, "plate": 0.2}, width=1.2, gain_db=-12.0)),
        "pad": (*zyn("Pads/0005-Square Pad 1.xiz", "Square Pad 1 (ZynAddSubFX - Pads), the pixel pad"),
                dict(hp=180, lp=6000, width=1.3, sends={"plate": 0.4}, gain_db=-10.0)),
        "choir": (*zyn("Synth/0004-Pulse Pad 1.xiz", "Pulse Pad 1 (ZynAddSubFX - Synth), pulse layer"),
                  dict(hp=300, lp=7000, width=1.5, sends={"plate": 0.5}, gain_db=-16.0)),
        "comp": (*xpf("BitInvader/epiano.xpf", "BitInvader e-piano, the jazz chords"),
                 dict(hp=200, chorus={"depth_ms": 1.6, "rate": 0.5, "base_ms": 9, "mix": 0.25}, width=1.2, sends={"plate": 0.2, "echo": 0.08}, gain_db=-9.0)),
        "bass": (*xpf("BitInvader/subbass.xpf", "BitInvader sub bass, the rolling sub"),
                 dict(hp=28, lp=220, mono=True, duck={"depth": 0.3, "release": 0.1}, gain_db=-4.0)),
        "bass_mid": (*xpf("SID/Bass.xpf", "SID bass, the 8-bit edge on the sub"),
                     dict(hp=200, lp=2500, mono=True, duck={"depth": 0.25, "release": 0.1}, gain_db=-14.0)),
    },
    "targets": {"lead": -7.0, "arp": -15.0, "pad": -14.0, "choir": -20.0, "comp": -13.0, "bass": -2.0, "bass_mid": -14.0},
    "level_ref": "kick",
    "test_bars": (at("Second scene 1"), at("Second scene 1") + 7),
    "automation": [{"type": "lowpass", "tracks": ["arp", "pad", "choir"], "points": [[1, 700], [7, 2500], [9, 6000], [17, 18000]]},
                   {"type": "highpass", "tracks": ["kick", "bass", "bass_mid"], "points": [[at("Second scene 1") - 1, 20], [at("Second scene 1") - 0.05, 350], [at("Second scene 1"), 20]]},
                   {"type": "gain", "tracks": ["pad", "choir", "arp", "lead"], "points": [[ALL - 3, 0], [ALL + 1, -18]]}],
}

if __name__ == "__main__":
    build_kit()
    if "--samples" not in sys.argv:
        LT.make(SPEC, log=lambda m: print(m, flush=True))
