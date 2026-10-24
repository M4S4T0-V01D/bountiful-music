#!/usr/bin/env python3
"""Game music: the loop seam is exactly a repeat, layers stay aligned and additive, WAV loop points survive a
round trip, stingers stay in key, and a real track exports everything an engine needs.
Run: python tests/test_gamemusic.py   (the last test renders a short song: about a minute)"""
from __future__ import annotations

import json
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bountiful"))
import gamemusic as GM  # noqa: E402

SR = GM.SR


def tone(n: int, f: float, tail: int, seed: int = 0) -> np.ndarray:
    """A stem whose notes start inside [0, n) and ring on for `tail` samples after it, like the renderer's --bars."""
    rng = np.random.default_rng(seed)
    x = np.zeros((n + tail, 2))
    for at in rng.integers(0, n, 6):
        t = np.arange(n + tail - at) / SR
        x[at:, 0] += 0.2 * np.sin(2 * np.pi * f * t) * np.exp(-t * 1.5)
    x[:, 1] = x[:, 0] * 0.9
    return x


def test_the_wrapped_loop_is_exactly_the_music_going_round_again():
    n = SR                                   # a 1 s loop whose notes ring for 1.6 s past it: tails reach two passes on
    x = tone(n, 330, int(1.6 * SR))
    played = np.zeros((6 * n + len(x), 2))
    for k in range(6):                       # what playing the section six times in a row sounds like
        played[k * n:k * n + len(x)] += x
    loop = GM.wrap(x, n)
    assert loop.shape == (n, 2)
    steady = played[3 * n:4 * n]             # after the first passes, every pass is the same
    assert np.abs(loop - steady).max() < 1e-12
    tiled = np.tile(loop, (2, 1))
    assert np.abs(tiled[n - 1:n + 1] - played[4 * n - 1:4 * n + 1]).max() < 1e-12      # across the seam too


def test_layers_are_aligned_additive_and_states_get_louder():
    n = SR
    names = ["pad", "bass", "kick", "hats", "snare", "arp", "lead", "sidekick"]
    stems = {k: tone(n, 110 * (i + 1), SR // 2, seed=i) for i, k in enumerate(names)}
    assert [GM.layer_of(k) for k in names] == ["bed", "low", "beat", "beat", "drive", "drive", "top", "top"]
    r = GM.split(stems, n)
    assert set(r["layers"]) == set(GM.LAYERS)
    assert all(v.shape == (n, 2) for v in r["layers"].values())
    total = sum(r["layers"].values())
    raw = sum(GM.wrap(v, n) for v in stems.values())
    assert np.abs(total - raw * r["layer_gain"]).max() < 1e-9
    assert np.abs(total).max() <= GM.HEADROOM + 1e-9
    assert max(np.abs(v).max() for v in r["layers"].values()) <= GM.HEADROOM + 1e-9
    levels = [GM.rms(r["states"][s]) for s in ("calm", "explore", "tense", "combat")]
    assert levels == sorted(levels), levels
    assert all(np.abs(v).max() <= GM.CEILING + 1e-12 for v in r["states"].values())
    assert r["states"]["combat"].shape == (n, 2)
    # a loop with nothing for the calm state (no pads, no bass) still gets a calm mix
    r2 = GM.split({"kick": stems["kick"], "lead": stems["lead"]}, n)
    assert GM.rms(r2["states"]["calm"]) > 0 and len(r2["mix"]["calm"]) == 1


def test_the_soft_clip_is_memoryless_and_bounded():
    x = np.linspace(-3, 3, 2001)
    y = GM.soft(x)
    assert np.allclose(y[np.abs(x) <= 0.75], x[np.abs(x) <= 0.75])
    assert np.abs(y).max() < GM.CEILING and np.all(np.diff(y) > 0)
    assert np.allclose(GM.soft(x[::-1])[::-1], y)            # sample by sample: order does not matter


def test_wav_loop_points_round_trip():
    tmp = Path(tempfile.mkdtemp())
    x = np.stack([np.sin(np.arange(4410) / 7), np.cos(np.arange(4410) / 9)], 1) * 0.5
    GM.write_wav(tmp / "a.wav", x, (0, 4409))
    y, loop = GM.read_wav(tmp / "a.wav")
    assert loop == (0, 4409) and y.shape == x.shape and np.abs(y - x).max() < 1 / 32767
    with wave.open(str(tmp / "a.wav")) as w:                 # a plain reader skips the smpl chunk
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (2, 2, SR, 4410)
    GM.write_wav(tmp / "b.wav", x[:, 0])
    assert GM.read_wav(tmp / "b.wav")[1] is None


def test_stingers_stay_in_key_and_are_the_same_every_time():
    for tonic, mode, parts in ((2, "dorian", ["lead", "pad", "bass"]), (9, "minor_pent", ["arp", "bass2"]),
                               (5, "major", ["pad"]), (0, "weird_mode", ["lead_hi", "comp"])):
        st = GM.stinger_song({"tonic": tonic, "mode": mode, "bpm": 150}, parts)
        assert set(st) == set(GM.STINGERS), (mode, list(st))
        scale = {(tonic + d) % 12 for d in GM.scale_of(mode)}
        for name, s in st.items():
            notes = [n for evs in s["parts"].values() for n in evs]
            assert notes and set(s["parts"]) <= set(parts), (name, s["parts"].keys())
            assert all(n[2] % 12 in scale for n in notes), (mode, name, [n[2] for n in notes])
            assert all(0 <= n[0] < s["beats"] and n[1] > 0 for n in notes)
        assert GM.stinger_song({"tonic": tonic, "mode": mode, "bpm": 150}, parts) == st
    assert GM.stinger_song({"tonic": 0, "mode": "major"}, []) == {}


def test_a_pushed_downbeat_moves_to_the_end_of_the_loop():
    import build as B
    import mido
    tmp = Path(tempfile.mkdtemp())
    push = -0.02                                     # beats: 10 ms early at 120 bpm
    parts = {k: [] for k in B.PART_ORDER}
    parts["bass"] = [(16 + push, 1, 40, .8, 0), (17, 1, 41, .8, 0), (32 + push, 1, 42, .8, 0), (8, 1, 43, .8, 0)]
    B.write_midi(tmp / "s.mid", "s", 120, parts, [(16 + push, .25, 36, .9, 0), (20, .25, 36, .9, 0)])
    GM.loop_midi(tmp / "s.mid", 5, 8, tmp / "loop.mid")       # bars 5-8 = beats 16..32

    def notes(path):
        mf = mido.MidiFile(str(path))
        out = []
        for tr in mf.tracks:
            t = 0
            for m in tr:
                t += m.time
                if m.type == "note_on" and m.velocity:
                    out.append((round(t / mf.ticks_per_beat, 2), m.note))
        return sorted(out)
    assert notes(tmp / "loop.mid") == sorted([(31.98, 40), (17.0, 41), (8.0, 43), (31.98, 36), (20.0, 36)])


def test_sections_pick_the_busiest_and_cap_the_loop():
    song = {"bars": 40, "parts": {"pad": [(b * 4.0, 4, 60, .6, 0) for b in range(40)],
                                  "lead": [(b * 4.0 + k, .5, 72, .8, 0) for b in range(16, 40) for k in range(4)]},
            "drums": [(b * 4.0, .25, 36, .9, 0) for b in range(8, 40)],
            "sections": [{"name": "intro", "start": 1, "bars": 8}, {"name": "verse", "start": 9, "bars": 8},
                         {"name": "drop", "start": 17, "bars": 24}]}
    secs = GM.sections(None, song)
    assert [s["parts"] for s in secs] == [["pad"], ["drums", "pad"], ["drums", "lead", "pad"]]
    top = GM.busiest(secs)
    assert top["name"] == "drop" and GM.loop_bars(top) == (17, 17 + GM.MAX_BARS - 1)
    nosec = GM.sections(None, dict(song, sections=None))
    assert [s["start"] for s in nosec] == [1, 9, 17, 25, 33]


def test_a_real_track_exports_loops_layers_stingers_and_engine_players():
    import lineage as G
    tmp = Path(tempfile.mkdtemp())
    track = G.export(G.origin(4242, length="short"), out=tmp / "song")
    m = GM.make(track, bars=(5, 8), log=lambda *_: None)
    out = Path(m["folder"])
    n = m["loop"]["samples"]
    assert n == round(4 * 4 * 60 / m["bpm"] * SR) and m["loop"]["bars"] == [5, 8]
    assert set(m["states"]) == set(GM.STATES) and m["layers"] and set(m["stingers"]) == set(GM.STINGERS)
    for v in list(m["states"].values()) + list(m["layers"].values()):
        x, loop = GM.read_wav(out / v["file"])
        assert len(x) == n and loop == (0, n - 1), v["file"]
    x = GM.read_wav(out / "loop_combat.wav")[0]
    jumps = np.abs(np.diff(x, axis=0)).max(1)
    assert np.abs(x[0] - x[-1]).max() <= jumps.max() + 1e-9          # the seam is no bigger a step than inside
    for v in m["stingers"].values():
        y = GM.read_wav(out / v["file"])[0]
        assert 0.3 < len(y) / SR <= max(s[2] for s in GM.STINGERS.values()) and np.abs(y).max() > 0.05
    assert json.loads((out / "manifest.json").read_text())["loop"]["samples"] == n
    gd, cs = (out / "godot" / "BountifulMusic.gd").read_text(), (out / "unity" / "BountifulMusic.cs").read_text()
    assert "set_state" in gd and "stinger" in gd
    assert all(f'"{k}"' in cs for k in m["layers"]) and "PlayScheduled" in cs and cs.count("{") == cs.count("}")
    # the same track renders to the same loop
    m2 = GM.make(track, bars=(5, 8), stingers=False, out=tmp / "again", log=lambda *_: None)
    assert (Path(m2["folder"]) / "loop_combat.wav").read_bytes() == (out / "loop_combat.wav").read_bytes()


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok    {name}")
            except Exception as ex:
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"FAIL  {name}: {ex}")
    sys.exit(1 if fails else 0)
