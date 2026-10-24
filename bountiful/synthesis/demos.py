"""The Synthesis Lab's five demos, built as ordinary Lab projects (project.py) so they open, play and change in the
Lab like anything you make there. Deterministic: the same build makes the same samples.

    python -m synthesis.demos [--out DIR] [--only NAME]     # writes <name>.bflab, <name>.wav and stems/ per demo
"""
from __future__ import annotations

import argparse
from pathlib import Path

from synthesis import project as P


def afterimage() -> dict:
    """174 bpm atmospheric jungle: Breakforge's rollers under a Ghost pad that remembers the chords, a gravity bass,
    weather in the background and Echo cells answering the bells."""
    p = P.new("afterimage", bpm=174, seed=95)
    p["render"].update(beats=64, tail_s=3.0)
    P.add_track(p, "break", "breakforge", "afterimage-rollers", gain_db=-4,
                automation={"intensity": [[0, 0.3], [32, 0.45], [48, 0.8], [63, 0.6]]})
    P.add_track(p, "pad", "ghost", "afterimage-pad", clip=P.clip("chords", 64, 57), gain_db=-10,
                automation={"residue": [[0, 0.3], [64, 0.8]]})
    P.add_track(p, "bass", "gravity", "slack-bass", clip=P.clip("bass", 64, 57), gain_db=-6)
    P.add_track(p, "air", "weather", "drizzle", clip=P.clip("drone", 64, 57), gain_db=-17, pan=0.2)
    P.add_track(p, "bells", graph={"nodes": {"src": {"engine": "material", "preset": "cracked-bell"},
                                             "eco": {"engine": "echo", "preset": "glass-lungs"}},
                                   "edges": [{"from": "src", "to": "eco", "gain": 0.8},
                                             {"from": "eco", "to": "src", "gain": 0.25, "feedback": True}],
                                   "notes": ["src"], "out": {"src": 0.5, "eco": 0.6}},
                clip=[c for c in P.clip("melody", 64, 57, seed=95) if c[0] >= 16], gain_db=-12, pan=-0.25)
    return p


def mechanical_garden() -> dict:
    """Clockwork: a fractal sequencer and gravity's struck bars, a phase garden blooming around them."""
    p = P.new("mechanical-garden", bpm=104, seed=11)
    p["render"].update(beats=48, tail_s=3.0)
    P.add_track(p, "clock", "fractal", "golden-clock", clip=P.clip("drone", 48, 57), gain_db=-8,
                automation={"depth": [[0, 2], [24, 4], [48, 5]]})
    P.add_track(p, "bars", "gravity", "marimba-bar", clip=P.clip("arp", 48, 57), gain_db=-10, pan=0.25)
    P.add_track(p, "garden", "phase_garden", "bloom", clip=P.clip("chords", 48, 57), gain_db=-12,
                automation={"coupling": [[0, 0.1], [40, 0.9]]})
    P.add_track(p, "pots", "material", "clay-pots", clip=P.clip("hits", 48, 69, seed=11), gain_db=-5, pan=-0.3)
    return p


def prismatic_weather() -> dict:
    """A slow storm through a hall of mirrors: weather fronts, prismatic chords, a Ghost choir of what was."""
    p = P.new("prismatic-weather", bpm=80, seed=7)
    p["render"].update(beats=32, tail_s=4.0)
    P.add_track(p, "front", "weather", "monsoon-front", clip=P.clip("drone", 32, 52), gain_db=-10,
                automation={"pressure": [[0, 0.2], [16, 0.9], [32, 0.4]]})
    P.add_track(p, "prism", "prismatic", "spinning-chord", clip=P.clip("chords", 32, 57), gain_db=-10,
                automation={"orbit": [[0, 0.2], [32, 1.0]]})
    P.add_track(p, "choir", "ghost", "frozen-choir", clip=P.clip("melody", 32, 57, seed=7), gain_db=-12, pan=0.2)
    return p


def fractal_machine() -> dict:
    """Self-similar rhythm: fractal machine and dust snare, a terrain bass, a Lissajous lead drawing over it."""
    p = P.new("fractal-machine", bpm=128, seed=3)
    p["render"].update(beats=48, tail_s=2.0)
    P.add_track(p, "machine", "fractal", "fractal-machine", clip=P.clip("drone", 48, 45), gain_db=-3)
    P.add_track(p, "dust", "fractal", "dust-snare", clip=P.clip("drone", 48, 57), gain_db=-6, pan=0.2)
    P.add_track(p, "bass", "terrain", "mountain-growl", clip=P.clip("bass", 48, 57), gain_db=-8,
                automation={"radius": [[0, 0.6], [24, 1.3], [48, 0.8]]})
    P.add_track(p, "lead", "terrain", "lissajous-lead", clip=[c for c in P.clip("melody", 48, 57, seed=3) if c[0] >= 16],
                gain_db=-11, pan=-0.2)
    return p


def mixed_production() -> dict:
    """Eight engines in one piece: every family of the Lab, two of them routed with bounded feedback."""
    p = P.new("eight-engines", bpm=122, seed=42)
    p["render"].update(beats=64, tail_s=3.0)
    P.add_track(p, "drums", "breakforge", "steppers", gain_db=-6)
    P.add_track(p, "bass", "gravity", "slack-bass", clip=P.clip("bass", 64, 57), gain_db=-7)
    P.add_track(p, "keys", "material", "practice-room-piano", clip=P.clip("chords", 64, 57), gain_db=-9, pan=-0.2)
    P.add_track(p, "garden", "phase_garden", "fireflies", clip=P.clip("arp", 64, 57), gain_db=-15, pan=0.3,
                automation={"bloom": [[0, 0.2], [64, 0.9]]})
    P.add_track(p, "lead", "terrain", "lissajous-lead", clip=[c for c in P.clip("melody", 64, 57, seed=42) if c[0] >= 32],
                gain_db=-11)
    P.add_track(p, "sky", "weather", "aurora", clip=P.clip("drone", 64, 57), gain_db=-18)
    P.add_track(p, "mirror", graph={"nodes": {"src": {"engine": "prismatic", "preset": "glass-prism"},
                                              "mem": {"engine": "ghost", "preset": "residue-wash"}},
                                    "edges": [{"from": "src", "to": "mem", "gain": 0.7},
                                              {"from": "mem", "to": "src", "gain": 0.2, "feedback": True}],
                                    "notes": ["src"], "out": {"src": 0.5, "mem": 0.6}},
                clip=P.clip("hits", 64, 69, seed=42), gain_db=-8, pan=0.15)
    P.add_track(p, "clock", "fractal", "binary-tree", clip=P.clip("drone", 64, 69), gain_db=-12, pan=-0.3)
    return p


DEMOS = {"afterimage": afterimage, "mechanical-garden": mechanical_garden, "prismatic-weather": prismatic_weather,
         "fractal-machine": fractal_machine, "eight-engines": mixed_production}


def write(name: str, out: Path, stems: bool = True, log=print) -> Path:
    proj = DEMOS[name]()
    d = out / name
    P.save(proj, d / f"{name}.bflab")
    mix, st = P.render(proj)
    pk = float(abs(mix).max()) or 1.0
    P.write_wav(d / f"{name}.wav", mix * (0.89 / pk))          # the demo mix at -1 dBFS; the stems as rendered
    if stems:
        for k, y in st.items():
            P.write_wav(d / "stems" / f"{k}.wav", y)
    log(f"{name}: {len(st)} tracks, {len(P.engines_used(proj))} engines, {len(mix) / proj['render']['sr']:.1f} s -> {d}")
    return d


def main():
    import paths
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=paths.DATA / "synthesis" / "demos")
    ap.add_argument("--only", choices=sorted(DEMOS))
    ap.add_argument("--no-stems", action="store_true")
    a = ap.parse_args()
    for name in ([a.only] if a.only else DEMOS):
        write(name, a.out, not a.no_stems)


if __name__ == "__main__":
    main()
