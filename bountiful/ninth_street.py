"""Ninth Street Blue - M4S4T0. Late-night jazz-hop single, companion to Sonora.

Built from the "Midnight Horizon" playlist (Kenny Burrell, Paul Desmond, Dave
Brubeck, Ryo Fukui, Giancarlo Gazzani). Nothing is sampled from those records:
every part is written here and replayed through GeneralUser GS.

88 bpm, F minor blues, swung boom-bap over brushes, upright bass and sub.
  intro 8   Fukui-style rolled piano, vibes, wet street after rain
  head1 12  Burrell-style guitar head, piano answers
  head2 12  harmon-mute trumpet takes the head, guitar answers, strings
  five 8    5/4 vamp (a nod to Take Five), flute melody, the beat stays in five
  solo 12   guitar solo chorus, walking upright
  head3 12  guitar and trumpet in octaves, vibes answers, choir
  outro 7   beat drops, trumpet over the changes, ends on a held Fm9

Run: .venv/bin/python bountiful/ninth_street.py
Out: tracks/ninth-street-blue/{ninth_street.mid, stems/, exports/}
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
VINYL = ROOT / "samples" / "lofi" / "vinyl_crackle_4bar_78.wav"
OUT = ROOT / "tracks" / "ninth-street-blue"
TITLE, ARTIST = "Ninth Street Blue", "M4S4T0"

SR = 44100
BPM = 88
PPQ = 480
SPB = 60.0 / BPM                    # seconds per beat
SWING = 0.61                        # where the off-beat eighth lands (0.5 = straight)
TARGET_LUFS = -14.0
rng = np.random.default_rng(88)

# ---------------------------------------------------------------- harmony
# (bass root, rootless left-hand voicing)
FM9 = (41, (56, 60, 63, 67))        # Ab C Eb G
BBM9 = (46, (56, 60, 61, 65))       # Ab C Db F
DB9 = (37, (53, 56, 59, 63))        # F Ab Cb Eb
C7S9 = (36, (52, 58, 63, 68))       # E Bb D# G#  (7#9b13)
CM7 = (36, (51, 55, 58, 62))        # Eb G Bb D
BLUES = [FM9, FM9, FM9, FM9, BBM9, BBM9, FM9, FM9, DB9, C7S9, FM9, C7S9]
INTRO = [FM9, BBM9, DB9, C7S9]
VAMP = [FM9, CM7]
OUTRO = [FM9, BBM9, FM9, BBM9, DB9, C7S9, FM9]

# ---------------------------------------------------------------- form
# each bar: (section, beats per bar, chord, index inside its section)
FORM: list[tuple[str, int, tuple, int]] = [("intro", 4, INTRO[i % 4], i) for i in range(8)]
FORM += [(s, 4, BLUES[i], i) for s in ("head1", "head2") for i in range(12)]
FORM += [("five", 5, VAMP[i % 2], i) for i in range(8)]
FORM += [(s, 4, BLUES[i], i) for s in ("solo", "head3") for i in range(12)]
FORM += [("outro", 4, c, i) for i, c in enumerate(OUTRO)]
HEADS = ("head1", "head2", "solo", "head3")

BAR_START = np.concatenate([[0], np.cumsum([b[1] for b in FORM])]).astype(float)
TOTAL_BEATS = float(BAR_START[-1])
START = {}
for _b, (_s, *_r) in enumerate(FORM):
    START.setdefault(_s, _b)

# ---------------------------------------------------------------- notes
STEMS = {  # name: (program, bank, channel, reverb send, mix gain dB)
    "drums":   (40, 128, 9, 22, -3.0),
    "bass":    (32, 0, 0, 8, -1.0),
    "piano":   (0, 0, 1, 52, 4.0),
    "guitar":  (26, 0, 2, 40, 3.0),
    "trumpet": (59, 0, 3, 60, 12.0),
    "flute":   (73, 0, 4, 64, 0.0),
    "pad":     (49, 0, 5, 90, -16.0),
    "choir":   (53, 0, 6, 96, -3.0),
    "vibes":   (11, 0, 7, 62, -2.0),
}
# stems played by the University of Iowa samples instead of General MIDI: stem -> (instrument, Harmon mute)
SAMPLED = {"trumpet": ("trumpet", True), "vibes": ("vibes", False)}
NATURAL_VIB = set()   # the alto takes carry their own vibrato, so no scripted one
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
MOVE = {FM9: (56, 60, 62, 67),      # Fm6/9: Eb steps down to D
        BBM9: (55, 60, 61, 65),     # Bbm6: Ab down to G
        DB9: (53, 58, 59, 63),      # Db13: Ab up to Bb
        C7S9: (52, 58, 61, 68),     # #9 -> b9, D# falls to Db
        CM7: (51, 55, 58, 60)}      # Cm7 sus: D -> C
# energy per section, scales velocities
LIFT = {"intro": 0.8, "head1": 0.92, "head2": 0.98, "five": 0.95, "solo": 1.04,
        "head3": 1.06, "outro": 0.82}

INTRO_TUNE = [(1, 2, 1, 77), (1, 3, 1, 75), (3, 1, 2, 76), (5, 2, 0.5, 75), (5, 2.5, 0.5, 77),
              (5, 3, 1, 80), (7, 0.5, 1, 79), (7, 1.5, 2, 76)]


def write_piano() -> None:
    for b, (sec, meter, chord, i) in enumerate(FORM):
        root, v = chord
        alt = MOVE.get(chord, v)
        lift = LIFT[sec]
        vel = lambda x: int(x * lift)  # noqa: E731
        if b == len(FORM) - 1:                                # final chord rings out
            pedal("piano", b, 0, 7.5)
            roll("piano", b, 0, 7, (root, root + 12) + v + (v[0] + 24,), 60, spread=0.09)
        elif sec in ("intro", "outro"):
            pedal("piano", b)
            roll("piano", b, 0, 2.5, (root + 12,) + v, vel(60), spread=0.07)
            roll("piano", b, 2.5, 1.5, alt[1:], vel(48), spread=0.05)
        elif sec == "five":                                   # the vamp: one, the & of two
            roll("piano", b, 0, 1.4, v, vel(74))
            roll("piano", b, 1.5, 1.2, alt, vel(62))
            if i % 2:
                roll("piano", b, 4.5, 0.4, alt, vel(48), spread=0.012)
        else:
            pattern = (i // 2 + (sec in ("solo", "head3"))) % 3 if i % 4 != 3 else 3
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
    for off, pos, dur, p in INTRO_TUNE:
        note("piano", off, pos, dur, p, 56, late=0.03, jitter=0.012)


def slide(stem: str, start: float, semis: float, over: float) -> None:
    bend(stem, start - 0.01, semis)
    for k in range(1, 7):
        bend(stem, start + over * k / 6, semis * (1 - k / 6))


THIRD = {FM9: 3, BBM9: 3, DB9: 4, C7S9: 4, CM7: 3}
GB = 42                                                       # tritone sub of C7: Gb walks down into F


def write_bass() -> None:
    for b, (sec, meter, chord, i) in enumerate(FORM):
        root, v = chord
        nxt = FORM[b + 1][2][0] if b + 1 < len(FORM) else root
        approach = nxt + (1 if rng.random() < 0.5 else -1)
        lift = LIFT[sec]
        if b == len(FORM) - 1:
            note("bass", b, 0, 6, root, 78)
        elif sec == "intro":
            if i >= 4:
                s, _ = note("bass", b, 0, 3.8, root, 72)
                if i == 4:
                    slide("bass", s, -2, 0.15)
        elif sec == "five":
            note("bass", b, 0, 1.4, root, int(96 * lift), jitter=0.004)
            note("bass", b, 1.5, 0.4, root + 7, int(70 * lift))
            note("bass", b, 3, 0.9, root + 7, int(86 * lift))
            note("bass", b, 4, 0.9, approach, int(72 * lift))
        elif sec == "solo":                                   # walk it
            t = THIRD[chord]
            line = [(root, root + t, root + 7, approach),
                    (root, root + 2, root + t, approach),
                    (root, root + 12, root + 7, approach)][int(rng.integers(0, 3))]
            if chord is C7S9:
                line = (root, root + 4, root + 7, GB)
            for k, p in enumerate(line):
                s, _ = note("bass", b, k, 0.92, p, int((90 if k == 0 else 76) * lift), jitter=0.005)
                if k == 0 and rng.random() < 0.3:
                    slide("bass", s, -1, 0.1)
        elif sec == "outro":
            note("bass", b, 0, 3.8, root, 76)
        else:
            s, _ = note("bass", b, 0, 1.4, root, int(98 * lift), jitter=0.004)
            if i % 4 == 0 or rng.random() < 0.25:
                slide("bass", s, -1, 0.12)                    # finger slide into the one
            note("bass", b, 1.5, 0.45, root + 7, int(72 * lift))
            if rng.random() < 0.5:
                note("bass", b, 2.25, 0.15, root + 7, 34)     # dead note
            if chord is C7S9:
                note("bass", b, 2.5, 1.4, GB, int(88 * lift))
                continue
            note("bass", b, 2.5, 0.9, root + (10 if (sec != "head1" and i % 2) else 0), int(84 * lift))
            note("bass", b, 3.5, 0.45, approach, int(68 * lift))


KICK, SNARE, TAP, SWIRL, HAT, PEDAL, OPEN, CRASH, RIDE = 36, 38, 37, 40, 42, 44, 46, 49, 51
# hat accents over a bar of 8ths: strong on the beat, a lift on the & of 2 and 4
HAT_V = (70, 44, 62, 52, 68, 42, 60, 54, 64, 48)


def write_drums() -> None:
    d = "drums"
    for b, (sec, meter, _, i) in enumerate(FORM):
        lift = LIFT[sec]
        if sec == "intro":
            if i == 7:                                        # pickup into the head
                for k, pos in enumerate((3.0, 3.25, 3.5, 3.75)):
                    note(d, b, pos, 0.2, SNARE, 40 + 14 * k, jitter=0.004)
            continue
        if sec == "outro" and i >= 4:
            continue
        if i == 0 and sec != "outro":
            note(d, b, 0, 1, CRASH, 58)
        swell = 1 + 0.06 * ((i % 4) - 1.5) / 1.5              # 4-bar breath
        kv = lambda x: int(x * lift * swell)  # noqa: E731
        if sec == "five":                                     # boom-bap in five
            for pos, v in ((0, 104), (1.5, 90), (4, 66)):
                note(d, b, pos, 0.5, KICK, kv(v), late=-0.006, jitter=0.003)
            note(d, b, 3, 0.5, SNARE, kv(100 + rng.integers(0, 10)), late=0.035, jitter=0.005)
            note(d, b, 3, 1.0, SWIRL, kv(34), late=0.05)
            for pos in (2.25, 4.75):
                if rng.random() < 0.5:
                    note(d, b, pos, 0.2, SNARE, int(rng.integers(20, 34)), late=0.01, jitter=0.008)
            for k in range(10):
                if i == 7 and k >= 8:
                    break
                note(d, b, k * 0.5, 0.25, HAT, kv(HAT_V[k]), late=0.012 if k % 2 else 0.0, jitter=0.007)
            if i == 7:
                for k, pos in enumerate((4.0, 4.25, 4.5, 4.75)):
                    note(d, b, pos, 0.2, SNARE, 50 + 12 * k, jitter=0.004)
            continue
        fill = i == 11 and sec != "outro"
        busy = sec in ("head2", "solo", "head3")
        note(d, b, 0, 0.5, KICK, kv(104), late=-0.006, jitter=0.003)
        note(d, b, 2.5, 0.5, KICK, kv(90), late=-0.006, jitter=0.003)
        if i % 2 or busy:
            note(d, b, 2.75, 0.25, KICK, kv(66), jitter=0.003)
        if busy and rng.random() < 0.3:
            note(d, b, 3.75, 0.25, KICK, kv(56), jitter=0.003)
        if sec == "outro":                                    # hats + kick only
            for k in range(8):
                note(d, b, k * 0.5, 0.25, HAT, int(HAT_V[k] * 0.85), jitter=0.006)
            continue
        note(d, b, 1, 0.5, SNARE, kv(96 + rng.integers(0, 10)), late=0.035, jitter=0.005)
        if sec in ("head2", "head3"):
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


# the head, a 12-bar riff blues: (bar, pos, dur, pitch). Bars 3 and 7 are left open for answers.
RIFF = [(0, 0.5, 0.5, 72), (0, 1, 0.5, 75), (0, 1.5, 0.5, 77), (0, 2, 1, 75), (0, 3, 0.5, 72),
        (0, 3.5, 0.5, 71), (1, 0, 0.5, 70), (1, 0.5, 1.5, 68), (1, 2.5, 0.5, 65), (1, 3, 1, 68)]
HEAD = (RIFF + [(2, 0.5, 0.5, 72), (2, 1, 0.5, 75), (2, 1.5, 2, 72)]
        + [(o + 4, p, d, n) for o, p, d, n in RIFF]
        + [(6, 0.5, 0.5, 77), (6, 1, 0.5, 80), (6, 1.5, 1.5, 79), (6, 3, 0.5, 77), (6, 3.5, 0.5, 75),
           (7, 0, 2, 72),
           (8, 0, 1.5, 77), (8, 1.5, 0.5, 75), (8, 2, 1, 71), (8, 3, 1, 68),
           (9, 0, 0.5, 67), (9, 0.5, 0.5, 68), (9, 1, 1, 64), (9, 2, 0.5, 67), (9, 2.5, 1.5, 70),
           (10, 0.5, 2, 68), (10, 3, 0.5, 65), (10, 3.5, 0.5, 68),
           (11, 0, 1.5, 64), (11, 2, 0.5, 63), (11, 2.5, 0.5, 64), (11, 3, 1, 67)])
ANSWERS = [(3, 0.5, 0.5, 68), (3, 1, 0.5, 70), (3, 1.5, 1, 72), (3, 2.5, 0.5, 70), (3, 3, 1, 68),
           (7, 2.5, 0.25, 72), (7, 2.75, 0.25, 75), (7, 3, 1, 79)]
# guitar solo chorus, F minor blues scale with the b5 (B) as the passing tone
SOLO = [(0, 0.5, 0.25, 65), (0, 0.75, 0.25, 68), (0, 1, 0.5, 70), (0, 1.5, 0.5, 71), (0, 2, 1, 72),
        (0, 3.5, 0.5, 75), (1, 0, 1.5, 77), (1, 1.5, 0.5, 75), (1, 2, 0.5, 72), (1, 2.5, 0.5, 70),
        (1, 3, 1, 68), (2, 1, 0.5, 72), (2, 1.5, 0.5, 72), (2, 2, 0.5, 75), (2, 2.5, 1.5, 72),
        (3, 0.5, 0.25, 71), (3, 0.75, 0.25, 70), (3, 1, 0.5, 68), (3, 1.5, 0.5, 65), (3, 2, 0.5, 63),
        (3, 2.5, 1.5, 65), (4, 0.5, 0.5, 73), (4, 1, 0.5, 72), (4, 1.5, 0.5, 68), (4, 2, 0.5, 70),
        (4, 2.5, 0.5, 77), (4, 3, 1, 73), (5, 0, 0.5, 72), (5, 0.5, 0.5, 70), (5, 1, 2, 68),
        (5, 3.5, 0.5, 65), (6, 0, 0.5, 68), (6, 0.5, 0.5, 72), (6, 1, 0.5, 75), (6, 1.5, 0.5, 79),
        (6, 2, 1.5, 80), (6, 3.5, 0.5, 79), (7, 0, 0.5, 77), (7, 0.5, 0.5, 75), (7, 1, 0.5, 72),
        (7, 1.5, 0.5, 71), (7, 2, 2, 72), (8, 0.5, 0.5, 77), (8, 1, 0.5, 75), (8, 1.5, 0.5, 71),
        (8, 2, 0.5, 68), (8, 2.5, 0.5, 65), (8, 3, 1, 63), (9, 0, 0.5, 64), (9, 0.5, 0.5, 67),
        (9, 1, 0.5, 70), (9, 1.5, 0.5, 75), (9, 2, 1, 76), (9, 3, 1, 73), (10, 0, 2, 72),
        (10, 2.5, 0.5, 68), (10, 3, 1, 65), (11, 1, 0.5, 67), (11, 1.5, 0.5, 68), (11, 2, 0.5, 70),
        (11, 2.5, 0.5, 71), (11, 3, 1, 76)]
# flute over the 5/4 vamp (Fm9 | Cm7)
FIVE_A = [(0, 0, 1, 77), (0, 1, 0.5, 75), (0, 1.5, 1, 72), (0, 3, 2, 68),
          (1, 0, 1, 70), (1, 1, 1, 67), (1, 2, 3, 74)]
FIVE_TUNE = (FIVE_A + [(2, 0, 1, 77), (2, 1, 0.5, 79), (2, 1.5, 1.5, 80), (2, 3, 1, 79), (2, 4, 1, 77),
                       (3, 0, 2, 75), (3, 2, 1, 74), (3, 3, 2, 70)]
             + [(o + 4, p, d, n) for o, p, d, n in FIVE_A]
             + [(6, 0, 1, 80), (6, 1, 1, 79), (6, 2, 1, 77), (6, 3, 2, 75), (7, 0, 3, 72), (7, 3, 2, 79)])
OUTRO_TUNE = [(0, 1, 2.5, 72), (1, 0.5, 0.5, 73), (1, 1, 2, 72), (1, 3, 1, 68), (2, 1, 2.5, 67),
              (3, 1, 1, 68), (3, 2, 1.5, 65), (4, 0.5, 3, 65), (5, 1, 1, 64), (5, 2, 1.5, 67)]


def sing(stem: str, start: float, length: float, vel: int, scoop: bool, fall: bool,
         depth: float = 0.22, rate: float = 5.2) -> None:
    """Breath and voice for a monophonic line: swell, scoop, delayed vibrato, fall-off."""
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
            bend(stem, t, depth * ramp * np.sin(2 * np.pi * rate * (t - onset) * SPB))
    if fall:
        end = start + length
        for k in range(6):
            bend(stem, end - 0.16 + k * 0.03, -1.6 * (k / 5) ** 2)


def phrase(stem: str, sec: str, notes, vel0: int, shift: int = 0, falls: bool = True,
           grace: bool = False, depth: float = 0.2, rate: float = 5.2) -> None:
    """Play a written line with breath: scoops after rests, falls before long gaps."""
    base, meter = START[sec], FORM[START[sec]][1]
    last_end = -9.0
    for k, (off, pos, dur, p) in enumerate(notes):
        p += shift
        vel = int((vel0 + (6 if dur >= 1 else 0) - (4 if dur <= 0.5 else 0)) * LIFT[sec])
        if grace and dur >= 1 and rng.random() < 0.5:
            note(stem, base + off, pos - 0.12, 0.1, p - 1, vel - 14, late=0.03, jitter=0.004)
        s, ln = note(stem, base + off, pos, dur, p, vel, late=0.03, jitter=0.011)
        gap = (notes[k + 1][0] * meter + notes[k + 1][1] - off * meter - pos - dur
               if k + 1 < len(notes) else 9)
        sing(stem, s, ln, vel, scoop=s - last_end > 0.4 or (dur >= 1 and rng.random() < 0.4),
             fall=falls and gap >= 1 and dur >= 0.5 and rng.random() < 0.6, depth=depth, rate=rate)
        last_end = s + ln


def write_melody() -> None:
    gtr = dict(falls=False, depth=0.1, rate=4.6)
    phrase("guitar", "head1", HEAD, 82, shift=-12, **gtr)
    phrase("piano", "head1", ANSWERS, 64, falls=False, depth=0)
    phrase("trumpet", "head2", HEAD, 76, grace=True, depth=0.18, rate=5.4)
    phrase("guitar", "head2", ANSWERS, 80, shift=-12, **gtr)
    phrase("flute", "five", FIVE_TUNE, 72, depth=0.16, rate=5.6)
    phrase("guitar", "solo", SOLO, 84, **gtr)
    phrase("guitar", "head3", HEAD, 82, shift=-12, **gtr)
    phrase("trumpet", "head3", HEAD, 66, grace=True, depth=0.18, rate=5.4)
    phrase("vibes", "head3", ANSWERS, 70, falls=False, depth=0)
    phrase("trumpet", "outro", OUTRO_TUNE, 70, depth=0.2, rate=5.0)


def write_pad() -> None:
    for b, (sec, meter, (root, v), i) in enumerate(FORM):
        last = b == len(FORM) - 1
        dur = 8 if last else meter
        if sec in ("head2", "five", "solo", "head3", "outro"):
            for p in v[1:]:
                note("pad", b, 0, dur, p + 12, 42 if sec != "outro" else 38, jitter=0.0)
        if sec in ("head3", "outro") or (sec == "five" and i >= 4):
            # wordless "ooh" choir: three upper voices that swell into each bar
            for p in v[1:]:
                note("choir", b, 0.05, dur, p, 50, jitter=0.01)
            a = BAR_START[b]
            for k in range(9):
                cc("choir", a + dur * k / 8, 11, 55 + 50 * np.sin(np.pi * min(k / 6, 1)) * (0.7 if k > 6 else 1))
        alt = MOVE.get((root, v), v)
        if sec == "intro" or last:                            # one ringing mallet chord per bar
            roll("vibes", b, 0.5, 7 if last else 3.4, tuple(p + 12 for p in v), 44, spread=0.06)
        elif sec in ("head2", "solo") or (sec == "outro" and i < 4):
            # comps on the offbeats, between the piano's hits
            roll("vibes", b, 1.5, 0.7, v, 52, spread=0.02)
            roll("vibes", b, 3.5, 0.45, alt, 46, spread=0.02)


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
    n = int(length / SR * 25)
    pos = rng.integers(0, length - 2000, n)
    burst = rng.standard_normal(600) * np.exp(-np.arange(600) / 90)
    for p in pos:
        g = rng.uniform(0.05, 0.4)
        pan = rng.uniform(0.2, 0.8)
        drops[p:p + 600, 0] += burst * g * (1 - pan)
        drops[p:p + 600, 1] += burst * g * pan
    drops = filt(drops, "bandpass", (1500, 7000))
    return hiss + drops * 0.6


def street(length: int) -> np.ndarray:
    """Distant city hum plus a few cars passing on wet asphalt, left to right and back."""
    hum = np.cumsum(rng.standard_normal((length, 2)), axis=0).astype(np.float32)
    hum = filt(filt(hum, "highpass", 40), "lowpass", 180)
    hum /= np.abs(hum).max() + 1e-9
    cars = np.zeros((length, 2), np.float32)
    t = np.arange(length) / SR
    for c, at in enumerate(rng.uniform(8, length / SR - 8, 6)):
        width = rng.uniform(1.8, 3.2)
        shape = np.exp(-0.5 * ((t - at) / width) ** 2).astype(np.float32)
        pan = np.clip(0.5 + (t - at) / (3 * width) * (1 if c % 2 else -1), 0, 1).astype(np.float32)
        cars[:, 0] += shape * np.sqrt(1 - pan)
        cars[:, 1] += shape * np.sqrt(pan)
    hiss = filt(rng.standard_normal((length, 2)).astype(np.float32), "bandpass", (400, 3500))
    return hum * 0.5 + hiss * cars * 0.18


def vinyl(length: int) -> np.ndarray:
    v, sr = sf.read(VINYL, dtype="float32")
    v = v.mean(1) if v.ndim > 1 else v
    v = np.tile(v, length // len(v) + 1)[:length]
    return np.stack([v, np.roll(v, 517)], axis=1)


KIT = ROOT / "samples" / "drummachines"
HIPHOP = ("head1", "head2", "five", "solo", "head3", "outro")   # sections where the sampled beat plays
BEAT_GAIN, SUB_GAIN = -10.5, -24.0


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
        if b == len(FORM) - 1:
            SUB_NOTES.append((a, 7.0, sub_pitch(root)))
        elif sec in HEADS or (sec == "outro" and i < 4):
            SUB_NOTES.append((swing(a), 2.45, sub_pitch(root)))
            second = GB if chord is C7S9 else root
            SUB_NOTES.append((swing(a + 2.5), 1.4, sub_pitch(second)))
        elif sec == "five":
            SUB_NOTES.append((a, 2.9, sub_pitch(root)))
            SUB_NOTES.append((a + 3, 1.9, sub_pitch(root)))
        elif sec == "outro":
            SUB_NOTES.append((a, 3.9, sub_pitch(root)))
        elif sec == "intro" and i == 7:
            SUB_NOTES.append((a + 3, 0.9, sub_pitch(36)))


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
        out[i:i + n] += (np.sin(ph) * amp).astype(np.float32)
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
    (OUT / "ninth_street.mid").write_bytes(smf([tempo_track()] + [stem_track(n) for n in STEMS]))

    with tempfile.TemporaryDirectory() as td:
        st = {n: render(n, length, Path(td)) for n in STEMS}

    a_start, end_t = sec_time(8), TOTAL_BEATS * SPB
    # piano: dark and distant in the intro, opens up over the last intro bar
    p_dark, p_open = filt(st["piano"], "lowpass", 1400), filt(st["piano"], "lowpass", 6500)
    open_env = env([(0, 0), (sec_time(7), 0), (a_start, 1), (sec_time(len(FORM) - 7), 1),
                    (sec_time(len(FORM) - 1), 0.35), (end_t + tail, 0.35)], length)
    st["piano"] = p_dark * (1 - open_env) + p_open * open_env
    st["drums"] = filt(tape(filt(st["drums"], "highpass", 40), 2.2), "lowpass", 9000)
    # upright: the sub owns everything under 90 Hz, keep the wood and the fingers
    st["bass"] = tape(filt(filt(st["bass"], "highpass", 90), "lowpass", 6000), 1.4)
    st["guitar"] = tape(filt(filt(st["guitar"], "highpass", 120), "lowpass", 6500) * 1.5, 1.3) / 1.5
    st["trumpet"] = filt(filt(st["trumpet"], "highpass", 300), "lowpass", 6500)
    st["flute"] = filt(filt(st["flute"], "highpass", 280), "lowpass", 8000)
    st["pad"] = filt(st["pad"], "lowpass", 3500)
    st["choir"] = filt(filt(st["choir"], "highpass", 220), "lowpass", 4200)
    motor = 2 * np.pi * 5.2 * np.arange(length) / SR   # vibraphone motor: tremolo, a little wide
    trem = np.stack([1 - 0.22 * (1 + np.sin(motor)), 1 - 0.22 * (1 + np.sin(motor + 0.6))], 1)
    st["vibes"] = filt(st["vibes"], "highpass", 180) * trem.astype(np.float32)
    beat, kick_only, kicks = beat_stem(length)
    sub = sub_stem(length) * duck(kicks, length, 5.0, 0.09)
    for n in ("piano", "pad", "choir", "vibes"):
        st[n] = st[n] * duck(kicks, length, 2.0, 0.25)
    st["bass"] = st["bass"] * duck(kicks, length, 2.5, 0.15)
    for n in st:
        sf.write(OUT / "stems" / f"{n}.wav", st[n], SR, subtype="PCM_24")
    sf.write(OUT / "stems" / "beat.wav", beat, SR, subtype="PCM_24")
    sf.write(OUT / "stems" / "sub.wav", sub, SR, subtype="PCM_24")

    mix = sum(st[n] * db(STEMS[n][4]) for n in STEMS) + beat * db(BEAT_GAIN) + sub * db(SUB_GAIN)
    amb_env = env([(0, db(-20)), (a_start, db(-29)), (sec_time(len(FORM) - 7), db(-29)),
                   (end_t, db(-20)), (end_t + tail, db(-22))], length)
    amb = (street(length) + rain(length) * 0.35) * amb_env + vinyl(length) * db(-24)
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
    intro_end = int(sec_time(7) * SR)
    checks = {
        "loudness within 0.5 LU of target": abs(lufs - TARGET_LUFS) < 0.5,
        "true peak <= -1.0 dBTP": tp <= -0.95,
        "length 3:00-4:00": 180 <= dur <= 240,
        "every stem has audio": all(np.abs(s).max() > 1e-3 for s in st.values()),
        "drums silent in intro": np.abs(st["drums"][:intro_end]).max() < 1e-3,
        "trumpet silent before head2": np.abs(st["trumpet"][: int(sec_time(START["head2"]) * SR)]).max() < 1e-3,
        "heads are 12-bar blues": all(sum(1 for s, *_ in FORM if s == h) == 12 for h in HEADS),
        "interlude is 8 bars of 5/4": [m for s, m, *_ in FORM if s == "five"] == [5] * 8,
        "ends on Fm9": FORM[-1][2] is FM9,
        "no beat or sub before bar 8": max(np.abs(beat[:intro_end]).max(), np.abs(sub[:intro_end]).max()) < 1e-4,
        "sub is mono": np.allclose(sub[:, 0], sub[:, 1]),
        "lows (<120 Hz) 3-9 dB over mids in head3":
            3 <= band_gap(mix, sec_time(START["head3"]), sec_time(START["outro"])) <= 9,
    }
    for k, ok in checks.items():
        print(f"{'ok  ' if ok else 'FAIL'} {k}")
    print(f"{sum(checks.values())}/{len(checks)} checks, {lufs:.1f} LUFS, TP {tp:.1f} dBTP, "
          f"{int(dur // 60)}:{int(dur % 60):02d}, {len(FORM)} bars")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
