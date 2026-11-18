"""Sonora at Midnight - M4S4T0. Late-night jazz-hop single.

Built from the "Midnight Horizon" playlist (Ryo Fukui, Paul Desmond, Dave
Brubeck, Kenny Burrell, Giancarlo Gazzani). Nothing is sampled from those
records: every part is written here and replayed through GeneralUser GS.

84 bpm, D minor, swung boom-bap on the Brush kit.
  intro 8   rolled Fukui-style piano voicings behind rain, opening filter
  A 16      chopped piano loop, upright bass, brushes
  B 16      Desmond-style alto hook enters, slow strings
  bridge 8  3/4 for eight bars (Kathy's Waltz), jazz guitar takes the melody
  A2 16     hook back, Burrell blue-note guitar fills every 8 bars
  outro 9   drums drop out, ends on a held Dm9

Run: .venv/bin/python bountiful/sonora.py
Out: tracks/sonora-at-midnight/{sonora.mid, stems/, exports/}
"""
from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy import signal

import iowa_lead

ROOT = Path(__file__).resolve().parent.parent
SF2 = ROOT / "samples" / "sf2" / "GeneralUser-GS.sf2"
VINYL = ROOT / "samples" / "lofi" / "vinyl_crackle_4bar_80.wav"
OUT = ROOT / "tracks" / "sonora-at-midnight"
TITLE, ARTIST = "Sonora at Midnight", "M4S4T0"

SR = 44100
BPM = 84
PPQ = 480
SPB = 60.0 / BPM                    # seconds per beat
SWING = 0.60                        # where the off-beat eighth lands (0.5 = straight)
TARGET_LUFS = -14.0
rng = np.random.default_rng(84)

# ---------------------------------------------------------------- harmony
# (bass root, rootless left-hand voicing)
DM9 = (38, (53, 57, 60, 64))        # F A C E
G13 = (43, (53, 59, 64, 69))        # F B E A
CMAJ9 = (36, (52, 55, 59, 62))      # E G B D
A7B9 = (45, (55, 61, 65, 70))       # G C# F Bb
GM9 = (43, (58, 62, 65, 69))        # Bb D F A
C13 = (36, (58, 62, 64, 69))        # Bb D E A
FMAJ9 = (41, (57, 60, 64, 67))      # A C E G
LOOP = [DM9, G13, CMAJ9, A7B9]
WALTZ = [GM9, C13, FMAJ9, A7B9]

# ---------------------------------------------------------------- form
# each bar: (section, beats per bar, chord, index inside its section)
FORM: list[tuple[str, int, tuple, int]] = []
for name, n in (("intro", 8), ("A", 16), ("B", 16)):
    FORM += [(name, 4, LOOP[i % 4], i) for i in range(n)]
FORM += [("bridge", 3, WALTZ[i % 4], i) for i in range(8)]
FORM += [("A2", 4, LOOP[i % 4], i) for i in range(16)]
FORM += [("outro", 4, LOOP[i % 4] if i < 8 else DM9, i) for i in range(9)]

BAR_START = np.concatenate([[0], np.cumsum([b[1] for b in FORM])]).astype(float)
TOTAL_BEATS = float(BAR_START[-1])

# ---------------------------------------------------------------- notes
STEMS = {  # name: (program, bank, channel, reverb send, mix gain dB)
    "drums":  (40, 128, 9, 22, -3.0),
    "bass":   (32, 0, 0, 8, -1.0),
    "piano":  (0, 0, 1, 52, 2.0),
    "sax":    (65, 0, 2, 64, 3.5),
    "guitar": (26, 0, 3, 46, 3.0),
    "pad":    (49, 0, 4, 90, -16.0),
    "choir":  (53, 0, 5, 96, -3.0),
    "keys":   (4, 8, 6, 58, -6.0),
}
# stems played by the University of Iowa samples instead of General MIDI: stem -> (instrument, Harmon mute)
SAMPLED = {"sax": ("alto", False)}
NATURAL_VIB = {'sax'}   # the alto takes carry their own vibrato, so no scripted one
NOTES: dict[str, list[tuple[float, float, int, int]]] = {k: [] for k in STEMS}
CTRL: dict[str, list[tuple[float, bytes]]] = {k: [] for k in STEMS}   # (beat, status-less msg)


def cc(stem: str, beat: float, num: int, val: int) -> None:
    CTRL[stem].append((max(beat, 0.0), bytes([0xB0, num, int(np.clip(val, 0, 127))])))


def bend(stem: str, beat: float, semis: float) -> None:
    """Pitch bend in semitones (default range +-2)."""
    v = int(np.clip(8192 + semis / 2 * 8192, 0, 16383))
    CTRL[stem].append((max(beat, 0.0), bytes([0xE0, v & 0x7F, v >> 7])))


def swing(beat: float) -> float:
    """Piecewise-linear swing inside each beat: the '&' moves from .5 to SWING."""
    whole = np.floor(beat)
    f = beat - whole
    f = f / 0.5 * SWING if f < 0.5 else SWING + (f - 0.5) / 0.5 * (1 - SWING)
    return whole + f


def note(stem: str, bar: int, pos: float, dur: float, pitch: int, vel: int,
         late: float = 0.0, jitter: float = 0.008) -> tuple[float, float]:
    start = swing(BAR_START[bar] + pos)
    end = swing(BAR_START[bar] + pos + dur)
    start = max(start + late + rng.normal(0, jitter), 0.0)
    vel = int(np.clip(vel + rng.normal(0, 4), 1, 127))
    length = max(end - start - 0.02, 0.05)
    NOTES[stem].append((start, length, pitch, vel))
    return start, length


def roll(stem: str, bar: int, pos: float, dur: float, pitches, vel: int, spread: float = 0.025) -> None:
    for k, p in enumerate(pitches):
        note(stem, bar, pos + k * spread, dur - k * spread, p, vel - 3 * k, jitter=0.004)


def pedal(stem: str, bar: int, pos: float = 0.0, length: float | None = None) -> None:
    """Sustain pedal: down just after the chord, up just before the next one."""
    a = BAR_START[bar] + pos
    b = a + (length if length is not None else FORM[bar][1] - pos)
    cc(stem, a + 0.06, 64, 100)
    cc(stem, b - 0.04, 64, 0)


# second-half voicings: the inner voices move inside each bar
MOVE = {DM9: (53, 57, 60, 62),      # E falls to D
        G13: (53, 59, 63, 69),      # 13 -> b13, Eb pulls up to the E of Cmaj9
        CMAJ9: (52, 57, 59, 62),    # C6/9
        A7B9: (55, 61, 65, 70)}     # same notes as Eb9: the tritone sub lives in the bass
# energy per section, scales velocities
LIFT = {"intro": 0.8, "A": 0.92, "B": 1.0, "bridge": 0.9, "A2": 1.06, "outro": 0.82}

# right-hand answers in A (no sax there): (bar in 4, pos, dur, pitch)
LICKS = [[(1, 2.5, 0.5, 74), (1, 3, 0.25, 77), (1, 3.25, 0.25, 75), (1, 3.5, 1, 74),
          (3, 0.5, 0.5, 76), (3, 1, 0.5, 73), (3, 1.5, 0.5, 70), (3, 2, 1, 69)],
         [(1, 2.5, 0.25, 81), (1, 2.75, 0.25, 79), (1, 3, 0.5, 77), (1, 3.5, 0.75, 74),
          (3, 0, 0.5, 76), (3, 0.5, 0.5, 77), (3, 1, 0.5, 76), (3, 1.5, 1.5, 73)]]
INTRO_TUNE = [(1, 2, 1, 76), (1, 3, 1, 74), (3, 1, 2, 73), (5, 2, 0.5, 74), (5, 2.5, 0.5, 76),
              (5, 3, 1, 77), (7, 0.5, 1, 76), (7, 1.5, 2, 73)]


def write_piano() -> None:
    for b, (sec, meter, chord, i) in enumerate(FORM):
        root, v = chord
        alt = MOVE.get(chord, v)
        lift = LIFT[sec]
        vel = lambda x: int(x * lift)  # noqa: E731
        if sec == "intro" or (sec == "outro" and i < 8):
            pedal("piano", b)
            roll("piano", b, 0, 2.5, (root + 12,) + v, vel(60), spread=0.07)
            roll("piano", b, 2.5, 1.5, alt[1:], vel(48), spread=0.05)
        elif sec == "outro":                                  # final chord rings out
            pedal("piano", b, 0, 7.5)
            roll("piano", b, 0, 7, (root, root + 12) + v + (v[0] + 24,), 60, spread=0.09)
        elif sec == "bridge":
            pedal("piano", b, 0, 2.9)
            note("piano", b, 0, 1, root + 12, vel(62))
            note("piano", b, 0.02, 1, root + 19, vel(50))
            for pos, vv in ((1, v), (2, alt)):
                for p in vv:
                    note("piano", b, pos, 0.8, p, vel(54 if pos == 1 else 46), jitter=0.005)
        else:
            pattern = (i // 2 + (sec == "A2")) % 3 if i % 4 != 3 else 3
            if pattern == 0:                                  # the chop
                roll("piano", b, 0, 1.25, v, vel(74))
                roll("piano", b, 1.5, 0.4, v, vel(54), spread=0.012)
                roll("piano", b, 2.5, 1.0, alt, vel(68))
                roll("piano", b, 3.75, 0.25, alt, vel(46), spread=0.01)
            elif pattern == 1:                                # lay back, let it breathe
                roll("piano", b, 0, 2.0, v, vel(70), spread=0.035)
                roll("piano", b, 2.75, 1.2, alt, vel(60))
            elif pattern == 2:                                # push the &4 into the next bar
                roll("piano", b, 0, 0.9, v, vel(72))
                roll("piano", b, 1.5, 1.0, alt, vel(58))
                roll("piano", b, 3.5, 0.5, alt, vel(52), spread=0.012)
            else:                                             # turnaround rings
                roll("piano", b, 0, 0.75, v, vel(72))
                roll("piano", b, 1, 0.5, v, vel(54))
                pedal("piano", b, 2, 2)
                roll("piano", b, 2, 2, alt, vel(66), spread=0.045)
            if sec == "A":
                for off, pos, dur, p in LICKS[(i // 4) % 2]:
                    if off == i % 4:
                        note("piano", b, pos, dur, p, vel(70 if dur < 1 else 76), late=0.015, jitter=0.01)
    for off, pos, dur, p in INTRO_TUNE:
        note("piano", off, pos, dur, p, 56, late=0.03, jitter=0.012)


def slide(stem: str, start: float, semis: float, over: float) -> None:
    bend(stem, start - 0.01, semis)
    for k in range(1, 7):
        bend(stem, start + over * k / 6, semis * (1 - k / 6))


def write_bass() -> None:
    for b, (sec, meter, chord, i) in enumerate(FORM):
        root, v = chord
        nxt = FORM[b + 1][2][0] if b + 1 < len(FORM) else root
        lift = LIFT[sec]
        if sec == "intro":
            if i >= 4:
                s, _ = note("bass", b, 0, 3.8, root, 72)
                if i == 4:
                    slide("bass", s, -2, 0.15)
        elif sec == "bridge":                                 # walk it in three
            tone = root + (3 if chord in (GM9,) else 4 if chord in (C13, FMAJ9, A7B9) else 7)
            note("bass", b, 0, 0.95, root, int(92 * lift))
            note("bass", b, 1, 0.9, tone + 12 if tone < 40 else tone, int(76 * lift))
            note("bass", b, 2, 0.9, nxt + 1 if nxt < root else nxt - 1, int(72 * lift))
        elif sec == "outro":
            if i < 4 or i == 8:
                note("bass", b, 0, 6 if i == 8 else 3.8, root, 78)
        else:
            third = 12 if chord is CMAJ9 else 10
            s, _ = note("bass", b, 0, 1.4, root, int(98 * lift), jitter=0.004)
            if i % 4 == 0 or rng.random() < 0.25:
                slide("bass", s, -1, 0.12)                    # finger slide into the one
            note("bass", b, 1.5, 0.45, root + 7, int(72 * lift))
            if rng.random() < 0.5:
                note("bass", b, 2.25, 0.15, root + 7, 34)     # dead note
            if chord is A7B9:                                 # tritone sub: Eb walks down into D
                note("bass", b, 2.5, 1.4, 39, int(88 * lift))
                continue
            note("bass", b, 2.5, 0.9, root + (third if (sec != "A" and i % 2) else 0), int(84 * lift))
            note("bass", b, 3.5, 0.45, nxt - 1, int(68 * lift))


KICK, SNARE, TAP, SWIRL, HAT, PEDAL, OPEN, CRASH, RIDE = 36, 38, 37, 40, 42, 44, 46, 49, 51
# hat accents over a bar of 8ths: strong on the beat, a lift on the & of 2 and 4
HAT_V = (70, 44, 62, 52, 68, 42, 60, 54)


def write_drums() -> None:
    d = "drums"
    for b, (sec, meter, _, i) in enumerate(FORM):
        lift = LIFT[sec]
        if sec == "intro":
            if i == 7:                                        # pickup into A
                for k, pos in enumerate((3.0, 3.25, 3.5, 3.75)):
                    note(d, b, pos, 0.2, SNARE, 40 + 14 * k, jitter=0.004)
            continue
        if sec == "bridge":                                   # jazz waltz
            note(d, b, 0, 0.5, KICK, 84, jitter=0.004)
            for pos, vel in ((0, 70), (1, 60), (1.5, 46), (2, 62)):
                note(d, b, pos, 0.5, RIDE, vel, jitter=0.005)
            for pos in (1, 2):
                note(d, b, pos, 0.5, PEDAL, 48)
                note(d, b, pos, 0.6, SWIRL, 44, late=0.02)
            continue
        if sec == "outro" and i >= 4:
            continue
        if i == 0 and sec in ("A", "B", "A2"):
            note(d, b, 0, 1, CRASH, 58)
        fill = i % 8 == 7 and sec != "outro"
        swell = 1 + 0.06 * ((i % 4) - 1.5) / 1.5              # 4-bar breath
        kv = lambda x: int(x * lift * swell)  # noqa: E731
        note(d, b, 0, 0.5, KICK, kv(104), late=-0.006, jitter=0.003)
        note(d, b, 2.5, 0.5, KICK, kv(90), late=-0.006, jitter=0.003)
        if i % 2 or sec == "B":
            note(d, b, 2.75, 0.25, KICK, kv(66), jitter=0.003)
        if sec in ("B", "A2") and rng.random() < 0.3:
            note(d, b, 3.75, 0.25, KICK, kv(56), jitter=0.003)
        if sec == "outro":                                    # hats + kick only
            for k in range(8):
                note(d, b, k * 0.5, 0.25, HAT, int(HAT_V[k] * 0.85), jitter=0.006)
            continue
        note(d, b, 1, 0.5, SNARE, kv(96 + rng.integers(0, 10)), late=0.035, jitter=0.005)
        if sec in ("B", "A2"):
            note(d, b, 1, 1.0, SWIRL, kv(34), late=0.05)
        if not fill:
            note(d, b, 3, 0.5, SNARE, kv(100 + rng.integers(0, 10)), late=0.035, jitter=0.005)
        for pos in (0.75, 1.75, 2.25, 3.25):
            if rng.random() < 0.45:
                note(d, b, pos, 0.2, SNARE, int(rng.integers(20, 34)), late=0.01, jitter=0.008)
        for k in range(8):
            pos = k * 0.5
            if fill and pos >= 3:
                break
            if i % 4 == 3 and pos == 3.5:
                note(d, b, pos, 0.5, OPEN, kv(56))
            else:
                note(d, b, pos, 0.25, HAT, kv(HAT_V[k]), late=0.012 if k % 2 else 0.0, jitter=0.007)
        if fill:
            for k, pos in enumerate((3.0, 3.25, 3.5, 3.75)):
                note(d, b, pos, 0.2, SNARE, 50 + 12 * k, jitter=0.004)


# alto hook, four 4-bar phrases: (bar offset, pos, dur, pitch)
HOOK_HEAD = [(0, 2.5, 0.5, 69), (0, 3, 0.5, 72), (0, 3.5, 1.5, 76),
             (1, 1, 0.5, 74), (1, 1.5, 0.5, 72), (1, 2, 1.5, 71), (1, 3.5, 0.5, 67)]
TAIL_1 = [(2, 2.5, 0.5, 76), (2, 3, 0.5, 79), (2, 3.5, 1, 83),
          (3, 0.5, 0.5, 81), (3, 1, 0.5, 79), (3, 1.5, 0.5, 77), (3, 2, 0.5, 76), (3, 2.5, 1.5, 73)]
TAIL_2 = [(2, 0.5, 0.5, 79), (2, 1, 1, 76), (2, 2.5, 0.5, 74), (2, 3, 1, 76),
          (3, 0.5, 0.5, 73), (3, 1, 0.5, 76), (3, 1.5, 0.5, 79), (3, 2, 1, 82), (3, 3, 1, 81)]
TAIL_3 = [(2, 0.5, 0.5, 76), (2, 1, 0.5, 74), (2, 1.5, 0.5, 72), (2, 2, 2, 71),
          (3, 0.5, 1, 69), (3, 1.5, 0.5, 73), (3, 2, 0.5, 76), (3, 2.5, 0.5, 79), (3, 3, 1.5, 77)]
PHRASES = [HOOK_HEAD + TAIL_1, HOOK_HEAD + TAIL_2, HOOK_HEAD + TAIL_1, HOOK_HEAD + TAIL_3]
# A2 sings it again but freer: grace notes before the long tones
GRACE = {76: 75, 83: 82, 71: 70, 81: 80}

# guitar melody over the waltz (bar, pos, dur, pitch)
WALTZ_TUNE = [(0, 0, 2, 62), (0, 2, 1, 65), (1, 0, 3, 64), (2, 0, 1.5, 69), (2, 1.5, 0.5, 67),
              (2, 2, 1, 64), (3, 0, 3, 61), (4, 0, 2, 69), (4, 2, 1, 67), (5, 0, 1, 64),
              (5, 1, 1, 62), (5, 2, 1, 58), (6, 0, 1, 60), (6, 1, 1, 64), (6, 2, 1, 67),
              (7, 0, 1, 69), (7, 1, 1, 67), (7, 2, 1, 64)]
# Burrell-style blue-note run over A7b9 / Eb9, beats 2.5-4, lands on Eb -> D
FILL = [(2.5, 0.25, 72), (2.75, 0.25, 69), (3.0, 0.25, 68), (3.25, 0.25, 67), (3.5, 0.25, 65), (3.75, 0.6, 63)]


def sing(stem: str, start: float, length: float, vel: int, scoop: bool, fall: bool,
         depth: float = 0.22, rate: float = 5.2) -> None:
    """Breath and voice for a monophonic line: swell, scoop, delayed vibrato, fall-off."""
    sec = SPB
    if scoop:
        slide(stem, start, -0.7, 0.14)
    else:
        bend(stem, start - 0.005, 0)
    base = 78 + vel // 6
    cc(stem, start - 0.005, 11, base)
    steps = max(int(length * 12), 1)
    for k in range(1, steps + 1):
        t = start + length * k / steps
        x = k / steps
        cc(stem, t, 11, base + (34 if length >= 1 else 16) * np.sin(np.pi * min(x * 1.3, 1)) - (10 if x > 0.85 else 0))
    if length >= 0.9 and stem not in NATURAL_VIB:  # vibrato after the note settles
        onset = start + 0.35
        n = int((length - 0.35) * 36)
        for k in range(n):
            t = onset + k / 36
            ramp = min(k / 12, 1)
            bend(stem, t, depth * ramp * np.sin(2 * np.pi * rate * (t - onset) * sec))
    if fall:
        end = start + length
        for k in range(6):
            bend(stem, end - 0.16 + k * 0.03, -1.6 * (k / 5) ** 2)


def write_melody() -> None:
    starts = {}
    for b, (sec, *_rest) in enumerate(FORM):
        starts.setdefault(sec, b)
    for sec in ("B", "A2"):
        for ph, phrase in enumerate(PHRASES):
            base = starts[sec] + ph * 4
            last_end = -9.0
            for k, (off, pos, dur, p) in enumerate(phrase):
                vel = int((74 + (6 if p >= 79 else 0) - (4 if dur <= 0.5 else 0)) * LIFT[sec])
                if sec == "A2" and dur >= 1 and p in GRACE and rng.random() < 0.6:
                    note("sax", base + off, pos - 0.12, 0.1, GRACE[p], vel - 14, late=0.03, jitter=0.004)
                s, ln = note("sax", base + off, pos, dur, p, vel, late=0.035, jitter=0.012)
                after_rest = s - last_end > 0.4
                is_last = k == len(phrase) - 1 or phrase[k + 1][0] - off > 1
                sing("sax", s, ln, vel, scoop=after_rest or (dur >= 1 and rng.random() < 0.4),
                     fall=is_last and ph % 2 == 1)
                last_end = s + ln
    for off, pos, dur, p in WALTZ_TUNE:
        s, ln = note("guitar", starts["bridge"] + off, pos, dur, p, 80, late=0.02, jitter=0.01)
        sing("guitar", s, ln, 80, scoop=dur >= 2, fall=False, depth=0.12, rate=4.6)
    for sec in ("A", "B", "A2"):
        for k in (7, 15):
            for j, (pos, dur, p) in enumerate(FILL):
                s, ln = note("guitar", starts[sec] + k, pos, dur, p, 82 - 2 * j, jitter=0.006)
                bend("guitar", s - 0.005, 0)
                if j == 0:
                    slide("guitar", s, -1, 0.08)


def write_pad() -> None:
    for b, (sec, meter, (root, v), i) in enumerate(FORM):
        last = b == len(FORM) - 1
        if sec in ("intro", "B", "bridge", "A2", "outro"):
            for p in v[1:]:
                note("pad", b, 0, 8 if last else meter, p + 12, 42 if sec != "outro" else 38, jitter=0.0)
        if sec in ("B", "A2", "outro") or (sec == "bridge" and i >= 4):
            # wordless "ooh" choir: three upper voices that swell into each bar
            dur = 8 if last else meter
            for p in v[1:]:
                note("choir", b, 0.05, dur, p, 50, jitter=0.01)
            a = BAR_START[b]
            for k in range(9):
                cc("choir", a + dur * k / 8, 11, 55 + 50 * np.sin(np.pi * min(k / 6, 1)) * (0.7 if k > 6 else 1))
        if sec == "A2" or (sec == "outro" and i < 8):
            # Rhodes comps on the offbeats, between the piano's hits
            alt = MOVE.get((root, v), v)
            roll("keys", b, 1.5, 0.7, v, 52, spread=0.02)
            roll("keys", b, 3.5, 0.45, alt, 46, spread=0.02)


# ---------------------------------------------------------------- midi + render
def vlq(n: int) -> bytes:
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def chunk(events: list[tuple[int, int, bytes]]) -> bytes:
    data, last = b"", 0
    for tick, _prio, ev in sorted(events, key=lambda e: (e[0], e[1])):
        data += vlq(tick - last) + ev
        last = tick
    data += vlq(0) + b"\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(data)) + data


def tempo_track() -> bytes:
    ev = [(0, 0, b"\xff\x51\x03" + int(60e6 / BPM).to_bytes(3, "big"))]
    meter = None
    for b, (_s, m, _c, _i) in enumerate(FORM):
        if m != meter:
            ev.append((int(BAR_START[b] * PPQ), 0, bytes([0xFF, 0x58, 4, m, 2, 24, 8])))
            meter = m
    return chunk(ev)


def stem_track(name: str) -> bytes:
    prog, bank, ch, rev, _g = STEMS[name]
    ev = [(0, 0, bytes([0xFF, 0x03, len(name)]) + name.encode()),
          (0, 0, bytes([0xB0 | ch, 0, bank])),
          (0, 0, bytes([0xC0 | ch, prog])),
          (0, 0, bytes([0xB0 | ch, 7, 100])),
          (0, 0, bytes([0xB0 | ch, 91, rev])),
          (0, 0, bytes([0xB0 | ch, 93, 0]))]
    for beat, msg in CTRL[name]:
        ev.append((int(beat * PPQ), 0, bytes([msg[0] | ch]) + msg[1:]))
    for start, dur, p, vel in NOTES[name]:
        on, off = int(start * PPQ), int((start + dur) * PPQ)
        ev.append((on, 2, bytes([0x90 | ch, p, vel])))
        ev.append((off, 1, bytes([0x80 | ch, p, 0])))
    return chunk(ev)


def smf(tracks: list[bytes]) -> bytes:
    return b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), PPQ) + b"".join(tracks)


def render(name: str, length: int, tmp: Path) -> np.ndarray:
    mid, wav = tmp / f"{name}.mid", tmp / f"{name}.wav"
    mid.write_bytes(smf([tempo_track(), stem_track(name)]))
    subprocess.run(["fluidsynth", "-ni", "-q", "-a", "null", "-r", str(SR), "-g", "0.7",
                    "-o", "synth.reverb.active=1", "-o", "synth.reverb.room-size=0.72",
                    "-o", "synth.reverb.damp=0.45", "-o", "synth.reverb.width=0.9",
                    "-o", "synth.reverb.level=0.8", "-o", "synth.chorus.active=0",
                    "-F", str(wav), str(SF2), str(mid)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    x, sr = sf.read(wav, dtype="float32", always_2d=True)
    assert sr == SR
    out = np.zeros((length, 2), np.float32)
    n = min(length, len(x))
    out[:n] = x[:n, :2]
    if name in SAMPLED:
        inst, mute = SAMPLED[name]
        out = iowa_lead.sampled_stem(inst, NOTES[name], CTRL[name], SPB, out, STEMS[name][3], mute)
    return out


# ---------------------------------------------------------------- dsp
def sos(kind: str, f, order: int = 2):
    return signal.butter(order, f, kind, fs=SR, output="sos")


def filt(x, kind, f, order=2):
    return signal.sosfiltfilt(sos(kind, f, order), x, axis=0).astype(np.float32)


def sec_time(bar: int) -> float:
    return BAR_START[bar] * SPB


def env(points: list[tuple[float, float]], length: int) -> np.ndarray:
    t = np.arange(length) / SR
    xs, ys = zip(*points)
    return np.interp(t, xs, ys).astype(np.float32)[:, None]


def tape(x: np.ndarray, drive: float) -> np.ndarray:
    return (np.tanh(x * drive) / np.tanh(drive)).astype(np.float32)


def rain(length: int) -> np.ndarray:
    hiss = rng.standard_normal((length, 2)).astype(np.float32)
    hiss = filt(filt(hiss, "highpass", 500), "lowpass", 5000) * 0.25
    drops = np.zeros((length, 2), np.float32)
    n = int(length / SR * 40)
    pos = rng.integers(0, length - 2000, n)
    burst = rng.standard_normal(600) * np.exp(-np.arange(600) / 90)
    for p in pos:
        g = rng.uniform(0.05, 0.4)
        pan = rng.uniform(0.2, 0.8)
        drops[p:p + 600, 0] += burst * g * (1 - pan)
        drops[p:p + 600, 1] += burst * g * pan
    drops = filt(drops, "bandpass", (1500, 7000))
    swell = 1 + 0.25 * np.sin(2 * np.pi * np.arange(length) / SR / 11)[:, None]
    return (hiss + drops * 0.6) * swell


def vinyl(length: int) -> np.ndarray:
    v, sr = sf.read(VINYL, dtype="float32")
    v = np.tile(v, length // len(v) + 1)[:length]
    return np.stack([v, np.roll(v, 517)], axis=1)


KIT = ROOT / "samples" / "drummachines"
HIPHOP = ("A", "B", "A2", "outro")         # sections where the sampled beat plays
BEAT_GAIN, SUB_GAIN = -9.0, -20.0


def section_at(beat: float) -> str:
    return FORM[min(int(np.searchsorted(BAR_START, beat, "right")) - 1, len(FORM) - 1)][0]


def load(name: str) -> np.ndarray:
    x, sr = sf.read(KIT / name, dtype="float32")
    x = x.mean(1) if x.ndim > 1 else x
    if sr != SR:
        x = signal.resample_poly(x, SR, sr).astype(np.float32)
    return x / (np.abs(x).max() + 1e-9)


def place(out: np.ndarray, x: np.ndarray, beat: float, gain: float, pan: float = 0.5) -> None:
    i = int(beat * SPB * SR)
    n = min(len(x), len(out) - i)
    if n > 0:
        out[i:i + n, 0] += x[:n] * gain * np.sqrt(1 - pan)
        out[i:i + n, 1] += x[:n] * gain * np.sqrt(pan)


def room(x: np.ndarray, seconds: float = 0.7) -> np.ndarray:
    n = int(seconds * SR)
    ir = rng.standard_normal((n, 2)).astype(np.float32) * np.exp(-np.arange(n) / (0.16 * SR))[:, None]
    ir = filt(ir, "bandpass", (300, 6000))
    wet = np.stack([signal.fftconvolve(x[:, c], ir[:, c])[: len(x)] for c in range(2)], 1)
    return (wet / (np.abs(wet).max() + 1e-9) * np.abs(x).max()).astype(np.float32)


def beat_stem(length: int) -> tuple[np.ndarray, np.ndarray, list[float]]:
    """Sampled boom-bap kit, triggered from the brush part so the two never flam."""
    kick = np.zeros(int(0.25 * SR), np.float32)
    for name, g in (("r_n_b/k_hard.wav", 0.8), ("tr808/kick.wav", 0.5)):   # punch + body
        x = load(name)[: len(kick)]
        kick[: len(x)] += g * x
    kick *= np.exp(-np.arange(len(kick)) / (0.09 * SR))
    snare = load("r_n_b/popsnare.wav")
    linn = load("linn/linn_snr.wav")
    snare[: len(linn)] += 0.6 * linn
    hat, ohat = load("r_n_b/hat.wav"), load("r_n_b/hat_o.wav")
    k_out, s_out, h_out = (np.zeros((length, 2), np.float32) for _ in range(3))
    kicks = []
    for start, _dur, p, vel in NOTES["drums"]:
        if section_at(start) not in HIPHOP:
            continue
        v = (vel / 110) ** 1.4
        if p == KICK:
            place(k_out, kick, start, v)
            kicks.append(start)
        elif p == SNARE and vel > 60:
            place(s_out, snare, start + 0.01, v * 0.9)
        elif p == HAT:
            place(h_out, hat, start, v * 0.5, pan=0.62)
        elif p == OPEN:
            place(h_out, ohat, start, v * 0.45, pan=0.62)
    s_out = s_out + 0.35 * room(s_out)
    k_out = tape(filt(k_out, "highpass", 35) * 1.6, 1.8)
    h_out = filt(h_out, "highpass", 3000)
    beat = k_out + s_out * 0.75 + h_out * 0.9
    return tape(beat, 1.3), k_out, kicks


SUB_NOTES: list[tuple[float, float, int]] = []    # (beat, beats, midi)


def sub_pitch(m: int) -> int:
    """Fold a root into the sub octave, G1-F#2 (49-92 Hz)."""
    while m > 42:
        m -= 12
    while m < 31:
        m += 12
    return m


def write_sub() -> None:
    for b, (sec, meter, chord, i) in enumerate(FORM):
        root = chord[0]
        a = BAR_START[b]
        if sec in ("A", "B", "A2"):
            SUB_NOTES.append((swing(a), 2.45, sub_pitch(root)))
            second = 39 if chord is A7B9 else root
            SUB_NOTES.append((swing(a + 2.5), 1.4, sub_pitch(second)))
        elif sec == "bridge":
            SUB_NOTES.append((a, meter - 0.1, sub_pitch(root)))
        elif sec == "outro" and (i < 4 or i == 8):
            SUB_NOTES.append((a, 7.0 if i == 8 else 3.9, sub_pitch(root)))
        elif sec == "intro" and i == 7:
            SUB_NOTES.append((a + 3, 0.9, sub_pitch(45)))


def sub_stem(length: int) -> np.ndarray:
    out = np.zeros(length, np.float32)
    for beat, beats, m in SUB_NOTES:
        i, n = int(beat * SPB * SR), int(beats * SPB * SR)
        n = min(n, length - i)
        t = np.arange(n) / SR
        f = 440 * 2 ** ((m - 69) / 12) * (1 + 0.18 * np.exp(-t / 0.025))   # 808-ish pitch drop
        ph = 2 * np.pi * np.cumsum(f) / SR
        amp = np.minimum(t / 0.004, 1) * (0.75 + 0.25 * np.exp(-t / 0.3))
        amp *= np.minimum((n - np.arange(n)) / (0.05 * SR), 1)              # release
        sec = section_at(beat)
        out[i:i + n] += (np.sin(ph) * amp * (0.6 if sec == "bridge" else 1.0)).astype(np.float32)
    out = np.tanh(out * 1.8) / np.tanh(1.8)                                # harmonics for small speakers
    out = filt(out[:, None], "lowpass", 240)[:, 0]
    return np.stack([out, out], 1)


def duck(kicks: list[float], length: int, depth_db: float, release: float = 0.12) -> np.ndarray:
    g = np.ones(length, np.float32)
    n = int(release * SR)
    curve = 1 - (1 - db(-depth_db)) * np.exp(-np.arange(n) / (0.35 * n))
    for k in kicks:
        i = int(k * SPB * SR)
        m = min(n, length - i)
        g[i:i + m] = np.minimum(g[i:i + m], curve[:m])
    return g[:, None]


def wow(x: np.ndarray) -> np.ndarray:
    t = np.arange(len(x)) / SR
    d = 0.0011 * np.sin(2 * np.pi * 0.42 * t) + 0.00015 * np.sin(2 * np.pi * 5.7 * t)
    idx = np.clip(np.arange(len(x)) - d * SR - 0.0015 * SR, 0, len(x) - 1)
    return np.stack([np.interp(idx, np.arange(len(x)), x[:, c]) for c in range(2)], 1).astype(np.float32)


def db(x: float) -> float:
    return 10 ** (x / 20)


def band_gap(x: np.ndarray, t0: float, t1: float) -> float:
    seg = x[int(t0 * SR):int(t1 * SR)].mean(1)
    f, pxx = signal.welch(seg, SR, nperseg=8192)
    low = pxx[(f >= 40) & (f < 120)].sum()
    mid = pxx[(f >= 300) & (f < 3000)].sum()
    return 10 * np.log10(low / mid)


def true_peak_db(x: np.ndarray) -> float:
    up = signal.resample_poly(x, 4, 1, axis=0)
    return 20 * np.log10(np.max(np.abs(up)) + 1e-12)


def main() -> int:
    write_piano(); write_bass(); write_drums(); write_melody(); write_pad(); write_sub()
    tail = 6.0
    length = int((TOTAL_BEATS * SPB + tail) * SR)
    (OUT / "stems").mkdir(parents=True, exist_ok=True)
    (OUT / "exports").mkdir(exist_ok=True)
    (OUT / "sonora.mid").write_bytes(smf([tempo_track()] + [stem_track(n) for n in STEMS]))

    with tempfile.TemporaryDirectory() as td:
        st = {n: render(n, length, Path(td)) for n in STEMS}

    a_start, end_t = sec_time(8), TOTAL_BEATS * SPB
    # piano: dark and distant in the intro, opens up over the last intro bar
    p_dark, p_open = filt(st["piano"], "lowpass", 1400), filt(st["piano"], "lowpass", 6500)
    open_env = env([(0, 0), (sec_time(7), 0), (a_start, 1), (sec_time(len(FORM) - 9), 1),
                    (sec_time(len(FORM) - 1), 0.35), (end_t + tail, 0.35)], length)
    st["piano"] = p_dark * (1 - open_env) + p_open * open_env
    st["drums"] = filt(tape(filt(st["drums"], "highpass", 40), 2.2), "lowpass", 9000)
    # upright: the sub owns everything under 90 Hz, keep the wood and the fingers
    st["bass"] = tape(filt(filt(st["bass"], "highpass", 90), "lowpass", 6000), 1.4)
    st["sax"] = filt(filt(st["sax"], "highpass", 250), "lowpass", 7000)
    st["guitar"] = filt(st["guitar"], "highpass", 150)
    st["pad"] = filt(st["pad"], "lowpass", 3500)
    st["choir"] = filt(filt(st["choir"], "highpass", 220), "lowpass", 4200)
    trem = 2 * np.pi * 2.8 * np.arange(length) / SR   # 2.8 Hz suitcase tremolo
    pan = np.stack([0.5 + 0.35 * np.sin(trem), 0.5 - 0.35 * np.sin(trem)], 1).astype(np.float32)
    st["keys"] = tape(filt(st["keys"], "lowpass", 5000) * pan * 2, 1.4)
    beat, kick_only, kicks = beat_stem(length)
    sub = sub_stem(length) * duck(kicks, length, 5.0, 0.09)
    for n in ("piano", "pad", "choir", "keys"):
        st[n] = st[n] * duck(kicks, length, 2.0, 0.25)
    st["bass"] = st["bass"] * duck(kicks, length, 2.5, 0.15)
    for n in st:
        sf.write(OUT / "stems" / f"{n}.wav", st[n], SR, subtype="PCM_24")
    sf.write(OUT / "stems" / "beat.wav", beat, SR, subtype="PCM_24")
    sf.write(OUT / "stems" / "sub.wav", sub, SR, subtype="PCM_24")

    mix = sum(st[n] * db(STEMS[n][4]) for n in STEMS) + beat * db(BEAT_GAIN) + sub * db(SUB_GAIN)
    rain_env = env([(0, db(-20)), (a_start, db(-28)), (sec_time(len(FORM) - 9), db(-28)),
                    (end_t, db(-20)), (end_t + tail, db(-22))], length)
    amb = rain(length) * rain_env + vinyl(length) * db(-24)
    sf.write(OUT / "stems" / "ambience.wav", amb, SR, subtype="PCM_24")
    mix = mix + amb
    mix = filt(filt(mix, "highpass", 30), "lowpass", 13000)
    mix = wow(mix)

    meter = pyln.Meter(SR)
    mix *= db(TARGET_LUFS - meter.integrated_loudness(mix))
    mix = tape(mix * db(1.5), 1.3) * db(-1.5)
    fade = env([(0, 0), (0.4, 1), (end_t, 1), (end_t + tail, 0)], length)
    mix *= fade
    mix *= db(TARGET_LUFS - meter.integrated_loudness(mix))
    tp = true_peak_db(mix)
    if tp > -1.0:
        mix *= db(-1.0 - tp)
    mix = mix.astype(np.float32)

    wav = OUT / "exports" / f"{TITLE} - {ARTIST}.wav"
    sf.write(wav, mix, SR, subtype="PCM_24")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libmp3lame",
                    "-b:a", "320k", "-metadata", f"title={TITLE}", "-metadata", f"artist={ARTIST}",
                    "-metadata", "genre=Jazz-hop", "-metadata", "date=2026",
                    str(wav.with_suffix(".mp3"))], check=True)

    # checks
    lufs, tp = meter.integrated_loudness(mix), true_peak_db(mix)
    dur = len(mix) / SR
    checks = {
        "loudness within 0.5 LU of target": abs(lufs - TARGET_LUFS) < 0.5,
        "true peak <= -1.0 dBTP": tp <= -0.95,
        "length 3:00-4:00": 180 <= dur <= 240,
        "every stem has audio": all(np.abs(s).max() > 1e-3 for s in st.values()),
        "drums silent in intro": np.abs(st["drums"][: int(sec_time(7) * SR)]).max() < 1e-3,
        "sax silent before B": np.abs(st["sax"][: int(sec_time(24) * SR)]).max() < 1e-3,
        "bridge is 3/4": all(m == 3 for s, m, *_ in FORM if s == "bridge"),
        "ends on Dm9": FORM[-1][2] is DM9,
        "no beat or sub before bar 8": max(np.abs(beat[: int(sec_time(7) * SR)]).max(),
                                           np.abs(sub[: int(sec_time(7) * SR)]).max()) < 1e-4,
        "sub is mono": np.allclose(sub[:, 0], sub[:, 1]),
        "lows (<120 Hz) 3-9 dB over mids in A2": 3 <= band_gap(mix, sec_time(48), sec_time(64)) <= 9,
    }
    for k, ok in checks.items():
        print(f"{'ok  ' if ok else 'FAIL'} {k}")
    print(f"{sum(checks.values())}/{len(checks)} checks, {lufs:.1f} LUFS, TP {tp:.1f} dBTP, "
          f"{int(dur // 60)}:{int(dur % 60):02d}, {len(FORM)} bars")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
