"""Paper Lanterns - M4S4T0. Fourth jazz-hop single, after Sonora, Ninth Street Blue and Sapporo.

The first one in a major key. Same "Midnight Horizon" playlist, this time the
Brubeck and Desmond side when they play pretty: a vibraphone head in E-flat, a
warm, breathy tenor that takes the solo, and a clarinet-and-harp bridge with the
feel of a summer evening on a library record. Nothing is sampled from those
records: every part is written here and replayed through GeneralUser GS.

86 bpm, E-flat major, swung boom-bap over brushes, upright bass and sub.
  intro 8   harp arpeggios, Rhodes, vibes fragments, crickets
  A1 8      vibes head over Ebmaj9 Gm11 | Abmaj9 Abm6 | Gm11 C7b9 | Fm9 Bb13
  A2 8      the tenor takes the head an octave down, vibes comp
  B1 8      half-time bridge: clarinet, strings, harp
            (Cm9 F13 | Bbm9 Eb13 | Abmaj9 Db13#11 | Fm9 Bb13)
  solo 16   tenor solo; two-feel bass, then the upright walks
  B2 8      vibes, the clarinet an octave down
  A3 8      vibes and tenor in octaves, full band
  outro 8   beat drops, vibes tag, ends on a ringing Ebmaj9

Run: .venv/bin/python bountiful/paper_lanterns.py
Out: tracks/paper-lanterns/{paper_lanterns.mid, stems/, exports/}
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
OUT = ROOT / "tracks" / "paper-lanterns"
TITLE, ARTIST = "Paper Lanterns", "M4S4T0"

SR = 44100
BPM = 86
PPQ = 480
SPB = 60.0 / BPM                    # seconds per beat
SWING = 0.57                        # where the off-beat eighth lands (0.5 = straight)
TARGET_LUFS = -14.0
rng = np.random.default_rng(86)

# ---------------------------------------------------------------- harmony
# (bass root, rootless left-hand voicing)
EBM9 = (39, (55, 58, 62, 65))       # G Bb D F    (Ebmaj9)
GM11 = (43, (53, 58, 60, 62))       # F Bb C D
ABM9 = (44, (55, 58, 60, 63))       # G Bb C Eb   (Abmaj9)
ABM6 = (44, (53, 58, 59, 63))       # F Bb Cb Eb  (Abm6/9, the borrowed iv)
C7B9 = (36, (52, 55, 58, 61))       # E G Bb Db
FM9 = (41, (56, 60, 63, 67))        # Ab C Eb G
BB13 = (46, (56, 60, 62, 67))       # Ab C D G
CM9 = (36, (51, 55, 58, 62))        # Eb G Bb D
F13 = (41, (51, 55, 57, 62))        # Eb G A D
BBM9 = (46, (53, 56, 60, 61))       # F Ab C Db
EB13 = (39, (55, 60, 61, 65))       # G C Db F
DB13 = (37, (53, 55, 59, 63))       # F G Cb Eb   (Db13#11, backdoor home)
MINOR = {GM11, ABM6, FM9, CM9, BBM9}
A_CH = [EBM9, GM11, ABM9, ABM6, GM11, C7B9, FM9, BB13]
B_CH = [CM9, F13, BBM9, EB13, ABM9, DB13, FM9, BB13]
OUTRO = [EBM9, GM11, ABM9, ABM6, EBM9, ABM6, BB13, EBM9]

# ---------------------------------------------------------------- form
# each bar: (section, beats per bar, chord, index inside its section)
FORM: list[tuple[str, int, tuple, int]] = [("intro", 4, A_CH[i], i) for i in range(8)]
FORM += [(s, 4, A_CH[i], i) for s in ("A1", "A2") for i in range(8)]
FORM += [("B1", 4, B_CH[i], i) for i in range(8)]
FORM += [("solo", 4, A_CH[i % 8], i) for i in range(16)]
FORM += [("B2", 4, B_CH[i], i) for i in range(8)]
FORM += [("A3", 4, A_CH[i], i) for i in range(8)]
FORM += [("outro", 4, c, i) for i, c in enumerate(OUTRO)]

BAR_START = np.concatenate([[0], np.cumsum([b[1] for b in FORM])]).astype(float)
TOTAL_BEATS = float(BAR_START[-1])
START = {}
for _b, (_s, *_r) in enumerate(FORM):
    START.setdefault(_s, _b)

# ---------------------------------------------------------------- notes
STEMS = {  # name: (program, bank, channel, reverb send, mix gain dB)
    "drums":    (40, 128, 9, 22, -3.0),
    "bass":     (32, 0, 0, 8, -1.0),
    "piano":    (0, 0, 1, 46, 0.0),
    "vibes":    (11, 0, 2, 58, 3.5),
    "tenor":    (66, 0, 3, 52, 5.5),
    "clarinet": (71, 0, 4, 64, 2.5),
    "keys":     (4, 8, 5, 58, -7.0),
    "pad":      (49, 0, 6, 90, -16.0),
    "harp":     (46, 0, 7, 70, -4.0),
}
# stems played by the University of Iowa samples instead of General MIDI: stem -> (instrument, Harmon mute)
SAMPLED = {"vibes": ("vibes", False), "tenor": ("alto", False)}
NATURAL_VIB = {'tenor'}   # the alto takes carry their own vibrato, so no scripted one
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

# the second voicing in each bar: a neighbour chord that moves the inner voices
MOVE = {EBM9: (55, 58, 60, 65),     # 6/9
        GM11: (55, 58, 62, 65),
        ABM9: (55, 58, 62, 63),     # #11 under the root
        ABM6: (54, 58, 59, 63),     # Abm9
        C7B9: (52, 56, 58, 61),     # b13
        FM9: (56, 60, 62, 67),      # Fm6/9
        BB13: (56, 59, 62, 67),     # b9
        CM9: (51, 57, 58, 62),      # Cm13
        F13: (51, 56, 57, 61),      # 7#9b13
        BBM9: (53, 56, 58, 61),
        EB13: (55, 60, 61, 66),     # #9
        DB13: (53, 58, 59, 63)}
# energy per section, scales velocities
LIFT = {"intro": 0.8, "A1": 0.9, "A2": 0.96, "B1": 0.92, "solo": 1.04, "B2": 1.0,
        "A3": 1.06, "outro": 0.82}

# scale for each chord (pitch classes), used by the solo and the melody check
SCALE = {EBM9: (3, 5, 7, 8, 10, 0, 2), GM11: (7, 8, 10, 0, 2, 3, 5), ABM9: (8, 10, 0, 2, 3, 5, 7),
         ABM6: (8, 10, 11, 1, 3, 5, 7), C7B9: (0, 1, 4, 5, 7, 8, 10), FM9: (5, 7, 8, 10, 0, 2, 3),
         BB13: (10, 0, 2, 3, 5, 7, 8), CM9: (0, 2, 3, 5, 7, 9, 10), F13: (5, 7, 9, 10, 0, 2, 3),
         BBM9: (10, 0, 1, 3, 5, 7, 8), EB13: (3, 5, 7, 8, 10, 0, 1), DB13: (1, 3, 5, 7, 8, 10, 11)}
PENT = (3, 5, 7, 10, 0)             # E-flat major pentatonic
TENOR_LO, TENOR_HI = 55, 80         # G3-Ab5 as written
SOLO_LINE: list[tuple[int, float, float, int]] = []    # (bar in solo, pos, dur, pitch)


def solo_line() -> None:
    """A tenor solo over 16 bars of the A changes: two-bar phrases that get longer
    and busier, each landing on a held chord tone, with a pentatonic run down and
    back up at the peak (bars 12-13)."""
    p = 63
    lo, hi = TENOR_LO, TENOR_HI
    for ph in range(8):
        bar0 = ph * 2
        busy = ph / 7
        nxt = (bar0 + 2) * 4
        if ph == 6:
            pent = sorted((n for n in range(lo, hi + 1) if n % 12 in PENT), reverse=True)
            run = pent[:9] + pent[:9][::-1][1:8]
            b = bar0 * 4 + 0.5
            for n in run:
                SOLO_LINE.append((int(b // 4), b % 4, 0.23, n))
                b += 0.25
            p = run[-1]
        else:
            b = bar0 * 4 + (0.5 if ph % 2 == 0 else 0.0) + (0.5 if rng.random() < 0.3 else 0.0)
            end = bar0 * 4 + 4.5 + 1.75 * busy            # phrases grow through the solo
            dirn = 1 if rng.random() < 0.5 else -1
            while b < end:
                chord = FORM[START["solo"] + int(b // 4)][2]
                pool = [n for n in range(lo, hi + 1) if n % 12 in SCALE[chord]]
                step = 0.25 if rng.random() < 0.1 + 0.45 * busy else (1.0 if rng.random() < 0.15 else 0.5)
                if b % 0.5:
                    step = 0.25                           # stay on the grid
                k = min(range(len(pool)), key=lambda j: abs(pool[j] - p))
                if rng.random() < 0.18:
                    dirn = -dirn
                if pool[k] >= hi - 4:
                    dirn = -1
                if pool[k] <= lo + 3:
                    dirn = 1
                k = int(np.clip(k + dirn * (1 if rng.random() < 0.75 else 2), 0, len(pool) - 1))
                p = pool[k]
                SOLO_LINE.append((int(b // 4), b % 4, step * 0.9, p))
                b += step
        # land on the nearest chord tone and hold it
        root, v = FORM[START["solo"] + min(int(b // 4), 15)][2]
        tones = [n for n in range(lo, hi + 1) if n % 12 in {x % 12 for x in v + (root,)}]
        land = min(tones, key=lambda n: abs(n - p))
        dur = min(1.5, nxt - b - 0.25)
        if dur > 0.2:
            SOLO_LINE.append((int(b // 4), b % 4, dur, land))
            p = land


def comp(stem: str, b: int, pattern: int, v, alt, vel) -> None:
    if pattern == 0:                                      # the chop
        roll(stem, b, 0, 1.25, v, vel(70))
        roll(stem, b, 1.5, 0.4, v, vel(50), spread=0.012)
        roll(stem, b, 2.5, 1.0, alt, vel(64))
        roll(stem, b, 3.75, 0.25, alt, vel(42), spread=0.01)
    elif pattern == 1:                                    # lay back, let it breathe
        roll(stem, b, 0, 2.0, v, vel(66), spread=0.035)
        roll(stem, b, 2.75, 1.2, alt, vel(56))
    elif pattern == 2:                                    # push the &4 into the next bar
        roll(stem, b, 0, 0.9, v, vel(68))
        roll(stem, b, 1.5, 1.0, alt, vel(54))
        roll(stem, b, 3.5, 0.5, alt, vel(48), spread=0.012)
    else:                                                 # turnaround rings
        roll(stem, b, 0, 0.75, v, vel(68))
        roll(stem, b, 1, 0.5, v, vel(50))
        pedal(stem, b, 2, 2)
        roll(stem, b, 2, 2, alt, vel(62), spread=0.045)


def write_piano() -> None:
    for b, (sec, meter, chord, i) in enumerate(FORM):
        root, v = chord
        alt = MOVE[chord]
        lift = LIFT[sec]
        vel = lambda x: int(x * lift)  # noqa: E731
        if b == len(FORM) - 1:                                # the last chord rings out
            pedal("piano", b, 0, 7.5)
            roll("piano", b, 0, 7, (root, root + 7) + v + (v[-1] + 5,), 58, spread=0.09)
        elif sec == "intro":
            if i >= 4:
                pedal("piano", b)
                roll("piano", b, 0, 3.5, v, vel(50), spread=0.06)
        elif sec == "outro":
            pedal("piano", b)
            roll("piano", b, 0, 2.0, (root + 12,) + v, vel(58), spread=0.07)
            roll("piano", b, 2.5, 1.5, alt, vel(46), spread=0.05)
        elif sec in ("B1", "B2"):                             # half-time: long rolled chords
            pedal("piano", b)
            roll("piano", b, 0, 2.0, v, vel(60), spread=0.04)
            roll("piano", b, 2, 2.0, alt, vel(54), spread=0.04)
        elif sec == "solo":                                   # lighter under the tenor
            comp("piano", b, i % 3 if i % 4 != 3 else 3, v, alt, lambda x: int(x * lift * 0.85))
        else:
            comp("piano", b, (i // 2 + (sec != "A1")) % 3 if i % 4 != 3 else 3, v, alt, vel)


def slide(stem: str, start: float, semis: float, over: float) -> None:
    bend(stem, start - 0.01, semis)
    for k in range(1, 7):
        bend(stem, start + over * k / 6, semis * (1 - k / 6))

def write_bass() -> None:
    for b, (sec, meter, chord, i) in enumerate(FORM):
        root, v = chord
        nxt = FORM[b + 1][2][0] if b + 1 < len(FORM) else root
        approach = nxt + (1 if rng.random() < 0.5 else -1)
        lift = LIFT[sec]
        home = chord is BB13 and i == 7                       # the V into the top of the form
        if b == len(FORM) - 1:
            note("bass", b, 0, 6, root, 78)
        elif sec == "intro":
            if i >= 4:
                s, _ = note("bass", b, 0, 3.8, root, 70)
                if i == 4:
                    slide("bass", s, -2, 0.15)
        elif sec in ("B1", "B2") or (sec == "solo" and i < 8):   # two-feel: root, fifth, pickup
            note("bass", b, 0, 1.9, root, int(92 * lift), jitter=0.004)
            note("bass", b, 2, 1.4, root + 7, int(76 * lift))
            note("bass", b, 3.5, 0.45, approach, int(66 * lift))
        elif sec == "solo":                                   # second half of the solo: walk
            t = 3 if chord in MINOR else 4
            line = [(root, root + t, root + 7, approach),
                    (root, root + 2, root + t, approach),
                    (root, root + 12, root + 7, approach)][int(rng.integers(0, 3))]
            for k, p in enumerate(line):
                s, _ = note("bass", b, k, 0.92, p, int((90 if k == 0 else 76) * lift), jitter=0.005)
                if k == 0 and rng.random() < 0.3:
                    slide("bass", s, -1, 0.1)
        elif sec == "outro" and i >= 4:
            note("bass", b, 0, 3.8, root, 76)
        else:                                                 # the A-section riff
            s, _ = note("bass", b, 0, 1.4, root, int(96 * lift), jitter=0.004)
            if i % 4 == 0 or rng.random() < 0.25:
                slide("bass", s, -1, 0.12)
            note("bass", b, 1.5, 0.45, root + 7, int(72 * lift))
            if rng.random() < 0.5:
                note("bass", b, 2.25, 0.15, root + 7, 34)     # dead note
            low = root - 2 if chord in MINOR else (root - 6 if home else root - 5)
            note("bass", b, 2.5, 0.9, low, int(84 * lift))
            note("bass", b, 3.5, 0.45, approach, int(68 * lift))


KICK, SNARE, TAP, SWIRL, HAT, PEDAL, OPEN, CRASH, RIDE = 36, 38, 37, 40, 42, 44, 46, 49, 51
# hat accents over a bar of 8ths: strong on the beat, a lift on the & of 2 and 4
HAT_V = (70, 44, 62, 52, 68, 42, 60, 54)


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
        fill = i % 8 == 7 and sec != "outro"
        if sec in ("B1", "B2"):                               # half-time bridge
            note(d, b, 0, 0.5, KICK, kv(104), late=-0.006, jitter=0.003)
            note(d, b, 1.75, 0.25, KICK, kv(70), jitter=0.003)
            note(d, b, 2, 0.5, SNARE, kv(102 + rng.integers(0, 8)), late=0.04, jitter=0.005)
            note(d, b, 2, 1.5, SWIRL, kv(36), late=0.05)
            if rng.random() < 0.5:
                note(d, b, 3.25, 0.2, SNARE, int(rng.integers(20, 34)), late=0.01, jitter=0.008)
            for k in range(8):
                if fill and k >= 6:
                    break
                note(d, b, k * 0.5, 0.25, HAT, kv(HAT_V[k]), late=0.012 if k % 2 else 0.0, jitter=0.007)
            if fill:
                for k, pos in enumerate((3.0, 3.25, 3.5, 3.75)):
                    note(d, b, pos, 0.2, SNARE, 50 + 12 * k, jitter=0.004)
            continue
        busy = sec in ("A2", "solo", "A3")
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
        if busy:
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

# the head, 8 bars over the A changes: (bar, pos, dur, pitch)
HEAD = [(0, 0, 1.5, 74), (0, 1.5, 0.5, 72), (0, 2, 0.5, 70), (0, 2.5, 1.5, 67),
        (1, 0.5, 0.5, 65), (1, 1, 0.5, 67), (1, 1.5, 0.5, 70), (1, 2, 2, 74),
        (2, 0, 1.5, 75), (2, 1.5, 0.5, 74), (2, 2, 0.5, 72), (2, 2.5, 1.5, 70),
        (3, 0, 0.5, 71), (3, 0.5, 0.5, 70), (3, 1, 2, 65), (3, 3.5, 0.5, 70),
        (4, 0, 1, 74), (4, 1, 0.5, 72), (4, 1.5, 0.5, 74), (4, 2, 2, 77),
        (5, 0, 0.5, 76), (5, 0.5, 0.5, 73), (5, 1, 1, 70), (5, 2, 0.5, 68), (5, 2.5, 1.5, 67),
        (6, 0, 0.5, 68), (6, 0.5, 0.5, 72), (6, 1, 1.5, 75), (6, 2.5, 0.5, 74), (6, 3, 1, 72),
        (7, 0, 0.5, 67), (7, 0.5, 0.5, 68), (7, 1, 2.5, 65)]
# the bridge: Cm9 | F13 | Bbm9 | Eb13 | Abmaj9 | Db13#11 | Fm9 | Bb13
BRIDGE = [(0, 0, 1, 75), (0, 1, 0.5, 74), (0, 1.5, 2.5, 70),
          (1, 0, 0.5, 69), (1, 0.5, 0.5, 72), (1, 1, 3, 74),
          (2, 0, 1, 73), (2, 1, 0.5, 72), (2, 1.5, 2.5, 68),
          (3, 0, 0.5, 67), (3, 0.5, 0.5, 68), (3, 1, 1, 72), (3, 2, 2, 73),
          (4, 0, 1, 72), (4, 1, 0.5, 75), (4, 1.5, 2.5, 79),
          (5, 0, 0.5, 77), (5, 0.5, 0.5, 79), (5, 1, 1.5, 75), (5, 2.5, 1.5, 71),
          (6, 0, 1, 72), (6, 1, 0.5, 68), (6, 1.5, 2.5, 67),
          (7, 0, 0.5, 65), (7, 0.5, 0.5, 67), (7, 1, 1, 70), (7, 2, 0.5, 72), (7, 2.5, 1.5, 74)]
# vibes in the intro: pieces of the head in the gaps
INTRO_TUNE = [(1, 2, 0.5, 70), (1, 2.5, 1.5, 74), (3, 2, 0.5, 71), (3, 2.5, 1.5, 70),
              (5, 1, 0.5, 73), (5, 1.5, 0.5, 70), (5, 2, 2, 67),
              (7, 1, 0.5, 65), (7, 1.5, 0.5, 67), (7, 2, 1, 68), (7, 3, 1, 70)]
OUTRO_TUNE = [(0, 1, 2.5, 70), (1, 0.5, 0.5, 70), (1, 1, 2, 74), (2, 1, 2.5, 72), (3, 1, 1, 71),
              (3, 2, 1.5, 68), (4, 0.5, 3, 67), (5, 1, 1, 71), (5, 2, 1.5, 70), (6, 1, 2, 68),
              (7, 0.5, 5, 74)]
TENOR = dict(depth=0.26, rate=5.0)                            # warm, wider vibrato than the alto
REED = dict(depth=0.08, rate=5.4)                             # clarinet: almost straight


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

def mallet(stem: str, sec: str, notes, vel0: int, shift: int = 0) -> None:
    """Vibes: accent the beats, let each bar ring a little past its written length."""
    base = START[sec]
    for off, pos, dur, p in notes:
        vel = int((vel0 + (6 if pos % 1 == 0 else 0) - (6 if dur <= 0.5 else 0)) * LIFT[sec])
        note(stem, base + off, pos, dur + 0.15, p + shift, vel, late=0.01, jitter=0.006)


def write_melody() -> None:
    mallet("vibes", "intro", INTRO_TUNE, 58)
    mallet("vibes", "A1", HEAD, 82)
    phrase("tenor", "A2", HEAD, 78, shift=-12, grace=True, **TENOR)
    phrase("clarinet", "B1", BRIDGE, 74, **REED)
    solo_line()
    phrase("tenor", "solo", SOLO_LINE, 80, **TENOR)
    mallet("vibes", "B2", BRIDGE, 78)
    phrase("clarinet", "B2", BRIDGE, 64, shift=-12, falls=False, **REED)
    mallet("vibes", "A3", HEAD, 84)
    phrase("tenor", "A3", HEAD, 80, shift=-12, grace=True, **TENOR)
    mallet("vibes", "outro", OUTRO_TUNE, 66)


def write_pad() -> None:
    for b, (sec, meter, (root, v), i) in enumerate(FORM):
        last = b == len(FORM) - 1
        dur = 8 if last else meter
        if sec in ("B1", "B2", "A3", "outro") or (sec == "solo" and i >= 8):
            for p in v[1:]:
                note("pad", b, 0, dur, p + 12, 42 if sec != "outro" else 38, jitter=0.0)
        alt = MOVE[(root, v)]
        up = lambda c: tuple(p + 12 for p in c)  # noqa: E731
        if sec == "intro" or last:                            # one soft Rhodes chord per bar
            roll("keys", b, 0.5, 7 if last else 3.4, v, 40, spread=0.05)
        elif sec in ("A1", "A3") or (sec == "solo" and i < 8) or (sec == "outro" and i < 4):
            # comps on the offbeats, between the piano's hits
            roll("keys", b, 1.5, 0.7, v, 52, spread=0.02)
            roll("keys", b, 3.5, 0.45, alt, 46, spread=0.02)
        elif sec == "A2" or (sec == "solo" and i >= 8):       # vibes comp while the tenor plays
            roll("vibes", b, 1.5, 0.8, up(v), 46, spread=0.02)
            roll("vibes", b, 3.5, 0.6, up(alt), 40, spread=0.02)


def write_harp() -> None:
    for b, (sec, meter, chord, i) in enumerate(FORM):
        root, v = chord
        last = b == len(FORM) - 1
        if sec == "intro" or (sec == "outro" and i >= 4) or last:
            # rising eighths through the chord, each one left to ring
            arp = (root + 12,) + v + tuple(p + 12 for p in v[:3])
            for k, p in enumerate(arp):
                note("harp", b, k * 0.5, 3.0 if not last else 6.0, p, 54 - 2 * k + (6 if k == 0 else 0),
                     jitter=0.004)
        elif sec in ("B1", "B2") and i in (0, 4):
            # a glissando up the chord's scale into the bar
            run = [n for n in range(60, 89) if n % 12 in SCALE[chord]]
            for k, n in enumerate(run):
                note("harp", b, k * (1.0 / len(run)), 2.0, n, 40 + k, jitter=0.002)

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

def crickets(length: int) -> np.ndarray:
    """Summer-night crickets: three insects, each a carrier near 4-5 kHz gated into
    short trills, with its own rate and place in the stereo field."""
    out = np.zeros((length, 2), np.float32)
    for f0, period, pulses, pan, g in ((4600, 0.62, 3, 0.25, 1.0), (4150, 0.9, 4, 0.78, 0.7),
                                       (5100, 0.47, 2, 0.55, 0.45)):
        on, off = 0.018, 0.012
        tt = np.arange(int(pulses * (on + off) * SR)) / SR
        ph = (tt % (on + off)) / on
        chirp = (np.sin(2 * np.pi * f0 * tt) * np.sin(np.pi * np.clip(ph, 0, 1)) * (ph < 1)).astype(np.float32)
        pos = rng.uniform(0, period)
        while (pos * SR) + len(chirp) < length:
            i = int(pos * SR)
            a = g * rng.uniform(0.6, 1.0)
            out[i:i + len(chirp), 0] += chirp * a * np.sqrt(1 - pan)
            out[i:i + len(chirp), 1] += chirp * a * np.sqrt(pan)
            pos += period * rng.uniform(0.93, 1.07)
    return filt(out, "lowpass", 7000) * 0.3


def air(length: int) -> np.ndarray:
    """Warm night air: low, slow-moving noise, far quieter than Sapporo's wind."""
    n = filt(rng.standard_normal((length, 2)).astype(np.float32), "bandpass", (120, 900))
    t = np.arange(length) / SR
    swell = 0.6 + 0.4 * np.sin(2 * np.pi * 0.05 * t + rng.uniform(0, 6))
    return (n * swell[:, None] * 0.5).astype(np.float32)


def vinyl(length: int) -> np.ndarray:
    v, sr = sf.read(VINYL, dtype="float32")
    v = v.mean(1) if v.ndim > 1 else v
    v = np.tile(v, length // len(v) + 1)[:length]
    return np.stack([v, np.roll(v, 517)], axis=1)


KIT = ROOT / "samples" / "drummachines"

HIPHOP = ("A1", "A2", "B1", "solo", "B2", "A3", "outro")    # sections where the sampled beat plays
BEAT_GAIN, SUB_GAIN = -10.0, -19.5


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
        elif sec in ("B1", "B2") or (sec == "outro" and i >= 4):
            SUB_NOTES.append((a, 3.9, sub_pitch(root)))
        elif sec in HIPHOP:
            SUB_NOTES.append((swing(a), 2.45, sub_pitch(root)))
            second = root - 6 if chord is BB13 and i == 7 else root     # E under the Bb13, into Eb
            SUB_NOTES.append((swing(a + 2.5), 1.4, sub_pitch(second)))
        elif sec == "intro" and i == 7:
            SUB_NOTES.append((a + 3, 0.9, sub_pitch(46)))


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

SUB_RIDE = {"B1": -3.0, "B2": -1.0, "A3": 3.0, "outro": -4.0}   # dB; held bridge and outro notes run heavy


def sub_ride(length: int) -> np.ndarray:
    pts, last = [(0.0, 1.0)], 1.0
    for sec, bar in START.items():
        g = db(SUB_RIDE.get(sec, 0.0))
        t = sec_time(bar)
        pts += [(max(t - 0.05, pts[-1][0] + 1e-3), last), (t + 0.05, g)]
        last = g
    pts.append((length / SR, last))
    return env(pts, length)


def fits(notes, chords) -> bool:
    """Every note of a written line belongs to the scale of the chord under it."""
    return all(p % 12 in SCALE[chords[off]] for off, _pos, _dur, p in notes)


def main() -> int:
    write_piano(); write_bass(); write_drums(); write_melody(); write_pad(); write_harp(); write_sub()
    tail = 6.0
    length = int((TOTAL_BEATS * SPB + tail) * SR)
    (OUT / "stems").mkdir(parents=True, exist_ok=True)
    (OUT / "exports").mkdir(exist_ok=True)
    (OUT / "paper_lanterns.mid").write_bytes(smf([tempo_track()] + [stem_track(n) for n in STEMS]))

    with tempfile.TemporaryDirectory() as td:
        st = {n: render(n, length, Path(td)) for n in STEMS}

    a_start, end_t = sec_time(8), TOTAL_BEATS * SPB
    # piano: soft and distant in the intro, opens up over the last intro bar
    p_dark, p_open = filt(st["piano"], "lowpass", 1600), filt(st["piano"], "lowpass", 7000)
    open_env = env([(0, 0), (sec_time(7), 0), (a_start, 1), (sec_time(len(FORM) - 8), 1),
                    (sec_time(len(FORM) - 1), 0.4), (end_t + tail, 0.4)], length)
    st["piano"] = p_dark * (1 - open_env) + p_open * open_env
    st["drums"] = filt(tape(filt(st["drums"], "highpass", 40), 2.2), "lowpass", 9000)
    # upright: the sub owns everything under 90 Hz, keep the wood and the fingers
    st["bass"] = tape(filt(filt(st["bass"], "highpass", 90), "lowpass", 6000), 1.4)
    st["tenor"] = tape(filt(filt(st["tenor"], "highpass", 150), "lowpass", 7000), 1.2)
    st["clarinet"] = filt(filt(st["clarinet"], "highpass", 180), "lowpass", 7500)
    st["pad"] = filt(st["pad"], "lowpass", 3500)
    st["harp"] = filt(st["harp"], "highpass", 120)
    motor = 2 * np.pi * 3.6 * np.arange(length) / SR  # slow vibraphone motor, Milt Jackson style
    trem = np.stack([1 - 0.18 * (1 + np.sin(motor)), 1 - 0.18 * (1 + np.sin(motor + 0.7))], 1)
    st["vibes"] = filt(st["vibes"], "highpass", 180) * trem.astype(np.float32)
    trem = 2 * np.pi * 2.8 * np.arange(length) / SR   # 2.8 Hz suitcase tremolo
    pan = np.stack([0.5 + 0.35 * np.sin(trem), 0.5 - 0.35 * np.sin(trem)], 1).astype(np.float32)
    st["keys"] = tape(filt(st["keys"], "lowpass", 5000) * pan * 2, 1.4)
    beat, kick_only, kicks = beat_stem(length)
    sub = sub_stem(length) * duck(kicks, length, 5.0, 0.09) * sub_ride(length)
    for n in ("piano", "pad", "keys", "vibes", "harp"):
        st[n] = st[n] * duck(kicks, length, 2.0, 0.25)
    st["bass"] = st["bass"] * duck(kicks, length, 2.5, 0.15)
    for n in st:
        sf.write(OUT / "stems" / f"{n}.wav", st[n], SR, subtype="PCM_24")
    sf.write(OUT / "stems" / "beat.wav", beat, SR, subtype="PCM_24")
    sf.write(OUT / "stems" / "sub.wav", sub, SR, subtype="PCM_24")

    mix = sum(st[n] * db(STEMS[n][4]) for n in STEMS) + beat * db(BEAT_GAIN) + sub * db(SUB_GAIN)
    amb_env = env([(0, db(-20)), (a_start, db(-31)), (sec_time(len(FORM) - 8), db(-31)),
                   (end_t, db(-20)), (end_t + tail, db(-22))], length)
    amb = (crickets(length) + air(length)) * amb_env + vinyl(length) * db(-24)
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
        "tenor silent before A2": np.abs(st["tenor"][: int(sec_time(START["A2"]) * SR)]).max() < 1e-3,
        "solo is 16 bars over the A changes": [c for s, _m, c, _i in FORM if s == "solo"] == A_CH * 2,
        "tenor solo within G3-Ab5": all(TENOR_LO <= p <= TENOR_HI for _b, _p, _d, p in SOLO_LINE),
        "head and bridge fit their changes": fits(HEAD, A_CH) and fits(BRIDGE, B_CH)
            and fits(OUTRO_TUNE, OUTRO) and fits(INTRO_TUNE, A_CH),
        "ends on Ebmaj9": FORM[-1][2] is EBM9,
        "no beat or sub before bar 8": max(np.abs(beat[:intro_end]).max(), np.abs(sub[:intro_end]).max()) < 1e-4,
        "sub is mono": np.allclose(sub[:, 0], sub[:, 1]),
        "lows (<120 Hz) 3-9 dB over mids in A3":
            3 <= band_gap(mix, sec_time(START["A3"]), sec_time(START["outro"])) <= 9,
    }
    for k, ok in checks.items():
        print(f"{'ok  ' if ok else 'FAIL'} {k}")
    print(f"{sum(checks.values())}/{len(checks)} checks, {lufs:.1f} LUFS, TP {tp:.1f} dBTP, "
          f"{int(dur // 60)}:{int(dur % 60):02d}, {len(FORM)} bars, {len(SOLO_LINE)} solo notes")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
