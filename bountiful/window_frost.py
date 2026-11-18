"""Window Frost - M4S4T0. Sixth jazz-hop single, after Sonora, Ninth Street Blue, Sapporo, Paper Lanterns
and Lighthouse, Late.

The winter one, in the spirit of Vince Guaraldi's trio records: a jazz waltz at both ends,
a breathy flute and vibes in unison, celesta snowflakes, and a fire going indoors while the
wind works at the window. It borrows two public-domain winter melodies, both from printed
scores and neither from any recording:
  - "O Tannenbaum" (German folk tune, best known in Ernst Anschuetz's 1824 version), the
    first strain, a minor third up from G into B-flat, as the 3/4 intro and outro
  - "In the Bleak Midwinter" (Gustav Holst's tune Cranham, The English Hymnal, 1906), both
    strains a fourth up from F into B-flat, as the flute head over new jazz changes
The bridge, the changes, the solo and every other part are original and played here: through
GeneralUser GS, and the flute and vibes through University of Iowa recordings.

76 bpm, B-flat major, waltz intro and outro, swung boom-bap over brushes, upright bass and sub.
  intro 10  (3/4) O Tannenbaum on vibes and celesta over a waltzing piano, fire and wind
  A1 8      Midwinter, first strain, on flute: Bbmaj9 Gm9 | Cm9 F13sus | Ebmaj9 Ebm6 | Cm9 Bbmaj9
  A2 8      second strain ("Snow had fallen"), vibes comping: Ebmaj9 Gm9 | Dm11 F13sus | Gm9 Ebm6 | F13sus Bbmaj9
  B1 8      half-time bridge on vibes, strings: Gm9 C9 | Fm9 Bb13 | Ebmaj9 Ab13 | Cm9 F13
  solo 16   flute solo over both strains; two-feel bass, then the upright walks, vibes comp
  B2 8      flute takes the bridge
  A3 8      first strain, flute and vibes in unison, full band
  outro 10  (3/4) O Tannenbaum on flute and vibes, the beat gone, ends on a ringing Bbmaj9

Run: .venv/bin/python bountiful/window_frost.py
Out: tracks/window-frost/{window_frost.mid, stems/, exports/}
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
OUT = ROOT / "tracks" / "window-frost"
TITLE, ARTIST = "Window Frost", "M4S4T0"

SR = 44100
BPM = 76
PPQ = 480
SPB = 60.0 / BPM                    # seconds per beat
SWING = 0.58                        # where the off-beat eighth lands (0.5 = straight)
TARGET_LUFS = -14.0
rng = np.random.default_rng(76)

# ---------------------------------------------------------------- harmony
# (bass root, rootless left-hand voicing)
BBM9 = (46, (50, 53, 57, 60))       # D F A C     (Bbmaj9)
GM9 = (43, (53, 57, 58, 62))        # F A Bb D
CM9 = (36, (51, 55, 58, 62))        # Eb G Bb D
F13SUS = (41, (51, 55, 58, 60))     # Eb G Bb C   (F9sus)
EBM9 = (39, (50, 53, 55, 58))       # D F G Bb    (Ebmaj9)
EBM6 = (39, (54, 58, 60, 65))       # Gb Bb C F   (Ebm6/9, the borrowed iv)
DM11 = (38, (53, 55, 57, 60))       # F G A C
C9 = (36, (52, 55, 58, 62))         # E G Bb D
FMIN9 = (41, (51, 55, 56, 60))      # Eb G Ab C
BB13 = (46, (50, 55, 56, 60))       # D G Ab C
AB13 = (44, (48, 53, 54, 62))       # C F Gb D    (Ab13#11, the backdoor dominant)
F13 = (41, (51, 55, 57, 62))        # Eb G A D
MINOR = {GM9, CM9, EBM6, DM11, FMIN9}
A_CH = [BBM9, GM9, CM9, F13SUS, EBM9, EBM6, CM9, BBM9]       # under the first strain
A2_CH = [EBM9, GM9, DM11, F13SUS, GM9, EBM6, F13SUS, BBM9]   # under the second
B_CH = [GM9, C9, FMIN9, BB13, EBM9, AB13, CM9, F13]
# under O Tannenbaum, one chord a 3/4 bar; bar 0 holds the pickup
INTRO = [F13SUS, BBM9, GM9, CM9, BBM9, EBM9, GM9, F13, EBM6, F13SUS]
OUTRO = INTRO[:-1] + [BBM9]

# ---------------------------------------------------------------- form
# each bar: (section, beats per bar, chord, index inside its section)
FORM: list[tuple[str, int, tuple, int]] = [("intro", 3, c, i) for i, c in enumerate(INTRO)]
FORM += [("A1", 4, A_CH[i], i) for i in range(8)]
FORM += [("A2", 4, A2_CH[i], i) for i in range(8)]
FORM += [("B1", 4, B_CH[i], i) for i in range(8)]
FORM += [("solo", 4, (A_CH + A2_CH)[i], i) for i in range(16)]
FORM += [("B2", 4, B_CH[i], i) for i in range(8)]
FORM += [("A3", 4, A_CH[i], i) for i in range(8)]
FORM += [("outro", 3, c, i) for i, c in enumerate(OUTRO)]

BAR_START = np.concatenate([[0], np.cumsum([b[1] for b in FORM])]).astype(float)
TOTAL_BEATS = float(BAR_START[-1])
START = {}
for _b, (_s, *_r) in enumerate(FORM):
    START.setdefault(_s, _b)

# ---------------------------------------------------------------- notes
STEMS = {  # name: (program, bank, channel, reverb send, mix gain dB)
    "drums":   (40, 128, 9, 22, -3.0),
    "bass":    (32, 0, 0, 8, -1.0),
    "piano":   (0, 0, 1, 46, 0.0),
    "flute":   (73, 0, 2, 54, 2.5),
    "vibes":   (11, 0, 3, 58, 1.5),
    "celesta": (8, 0, 4, 64, -3.0),
    "pad":     (49, 0, 5, 90, -14.0),
}
# stems played by the University of Iowa samples instead of General MIDI: stem -> (instrument, Harmon mute)
SAMPLED = {"flute": ("flute", False), "vibes": ("vibes", False)}
NATURAL_VIB = {"flute"}  # the flute takes carry their own vibrato
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
MOVE = {BBM9: (50, 52, 57, 60),     # #11
        GM9: (52, 57, 58, 62),      # Gm13
        CM9: (51, 55, 57, 62),      # Cm13
        F13SUS: (50, 55, 58, 63),
        EBM9: (50, 53, 57, 60),     # lydian
        EBM6: (54, 58, 61, 65),     # Ebm9
        DM11: (53, 55, 60, 62),
        C9: (52, 57, 58, 62),       # C13
        FMIN9: (51, 55, 56, 62),    # Fm13
        BB13: (50, 54, 56, 61),     # altered
        AB13: (48, 53, 54, 63),
        F13: (51, 54, 57, 62)}      # b9, into the B-flat
# energy per section, scales velocities
LIFT = {"intro": 0.76, "A1": 0.88, "A2": 0.93, "B1": 0.9, "solo": 1.0, "B2": 0.98,
        "A3": 1.03, "outro": 0.78}
FIFTH: dict = {}

# scale for each chord (pitch classes), used by the solo and the melody check
SCALE = {BBM9: (10, 0, 2, 3, 5, 7, 9), GM9: (7, 9, 10, 0, 2, 3, 5), CM9: (0, 2, 3, 5, 7, 9, 10),
         F13SUS: (5, 7, 9, 10, 0, 2, 3), EBM9: (3, 5, 7, 9, 10, 0, 2), EBM6: (3, 5, 6, 8, 10, 0, 1),
         DM11: (2, 3, 5, 7, 9, 10, 0), C9: (0, 2, 4, 5, 7, 9, 10), FMIN9: (5, 7, 8, 10, 0, 2, 3),
         BB13: (10, 0, 2, 3, 5, 7, 8), AB13: (8, 10, 0, 2, 3, 5, 6), F13: (5, 7, 9, 10, 0, 2, 3)}
PENT = (10, 0, 2, 5, 7)             # B-flat major pentatonic
FL_LO, FL_HI = 65, 86               # F4-D6: the flute's warm middle, under the shrill top
SOLO_LINE: list[tuple[int, float, float, int]] = []    # (bar in solo, pos, dur, pitch)


def solo_line() -> None:
    """A flute solo over 16 bars of both strains: short phrases with air between them,
    mostly eighths, each landing on a held chord tone, and one pentatonic run down and
    back up at the peak (bar 12, over the Gm9)."""
    p = 74
    lo, hi = FL_LO, FL_HI
    for ph in range(8):
        bar0 = ph * 2
        busy = ph / 7
        nxt = (bar0 + 2) * 4
        if ph == 6:
            pent = sorted((n for n in range(lo, hi + 1) if n % 12 in PENT), reverse=True)
            run = pent[:8] + pent[:8][::-1][1:8]
            b = bar0 * 4 + 0.25
            for n in run:
                SOLO_LINE.append((int(b // 4), b % 4, 0.23, n))
                b += 0.25
            p = run[-1]
        else:
            b = bar0 * 4 + (0.5 if ph % 2 == 0 else 1.0) + (0.5 if rng.random() < 0.3 else 0.0)
            end = bar0 * 4 + 4.0 + 1.5 * busy            # phrases grow a little through the solo
            dirn = 1 if rng.random() < 0.5 else -1
            while b < end:
                chord = FORM[START["solo"] + int(b // 4)][2]
                pool = [n for n in range(lo, hi + 1) if n % 12 in SCALE[chord]]
                step = 0.25 if rng.random() < 0.05 + 0.25 * busy else (1.0 if rng.random() < 0.25 else 0.5)
                if b % 0.5:
                    step = 0.25                           # stay on the grid
                k = min(range(len(pool)), key=lambda j: abs(pool[j] - p))
                if rng.random() < 0.2:
                    dirn = -dirn
                if pool[k] >= hi - 3:
                    dirn = -1
                if pool[k] <= lo + 3:
                    dirn = 1
                k = int(np.clip(k + dirn * (1 if rng.random() < 0.8 else 2), 0, len(pool) - 1))
                p = pool[k]
                SOLO_LINE.append((int(b // 4), b % 4, step * 0.9, p))
                b += step
        # land on the nearest chord tone and hold it
        root, v = FORM[START["solo"] + min(int(b // 4), 15)][2]
        tones = [n for n in range(lo, hi + 1) if n % 12 in {x % 12 for x in v + (root,)}]
        land = min(tones, key=lambda n: abs(n - p))
        dur = min(2.0, nxt - b - 0.5)
        if dur > 0.2:
            SOLO_LINE.append((int(b // 4), b % 4, dur, land))
            p = land


def comp(stem: str, b: int, pattern: int, v, alt, vel) -> None:
    if pattern == 0:                                      # the chop
        roll(stem, b, 0, 1.25, v, vel(68))
        roll(stem, b, 1.5, 0.4, v, vel(48), spread=0.012)
        roll(stem, b, 2.5, 1.0, alt, vel(62))
    elif pattern == 1:                                    # lay back, let it breathe
        roll(stem, b, 0, 2.0, v, vel(64), spread=0.035)
        roll(stem, b, 2.75, 1.2, alt, vel(54))
    elif pattern == 2:                                    # push the &4 into the next bar
        roll(stem, b, 0, 0.9, v, vel(66))
        roll(stem, b, 1.5, 1.0, alt, vel(52))
        roll(stem, b, 3.5, 0.5, alt, vel(46), spread=0.012)
    else:                                                 # turnaround rings
        roll(stem, b, 0, 0.75, v, vel(66))
        roll(stem, b, 1, 0.5, v, vel(48))
        pedal(stem, b, 2, 2)
        roll(stem, b, 2, 2, alt, vel(60), spread=0.045)


def write_piano() -> None:
    for b, (sec, meter, chord, i) in enumerate(FORM):
        root, v = chord
        alt = MOVE[chord]
        lift = LIFT[sec]
        vel = lambda x: int(x * lift)  # noqa: E731
        if b == len(FORM) - 1:                                # the last chord rings out
            pedal("piano", b, 0, 7.5)
            roll("piano", b, 0, 7, (root, root + 7) + v + (v[-1] + 4,), 58, spread=0.09)
        elif sec in ("intro", "outro"):                       # Guaraldi waltz: chord on 1, answers on 2 and 3
            pedal("piano", b)
            roll("piano", b, 0, 1.0, ((root + 12,) if i % 2 else ()) + v, vel(58), spread=0.05)
            roll("piano", b, 1, 0.9, alt, vel(44), spread=0.02)
            if i % 2 == 0:
                roll("piano", b, 2, 0.9, alt, vel(40), spread=0.02)
        elif sec in ("B1", "B2"):                             # half-time: long rolled chords
            pedal("piano", b)
            roll("piano", b, 0, 2.0, v, vel(58), spread=0.04)
            roll("piano", b, 2, 2.0, alt, vel(52), spread=0.04)
        elif sec == "solo":                                   # lighter under the flute
            comp("piano", b, i % 3 if i % 4 != 3 else 3, v, alt, lambda x: int(x * lift * 0.82))
        else:
            comp("piano", b, (i // 2 + (sec != "A1")) % 3 if i % 4 != 3 else 3, v, alt, vel)


def slide(stem: str, start: float, semis: float, over: float) -> None:
    bend(stem, start - 0.01, semis)
    for k in range(1, 7):
        bend(stem, start + over * k / 6, semis * (1 - k / 6))

def write_bass() -> None:
    for b, (sec, meter, chord, i) in enumerate(FORM):
        root, v = chord
        fifth = root + FIFTH.get(chord, 7)
        nxt = FORM[b + 1][2][0] if b + 1 < len(FORM) else root
        approach = nxt + (1 if rng.random() < 0.5 else -1)
        lift = LIFT[sec]
        if b == len(FORM) - 1:
            note("bass", b, 0, 6, root, 78)
        elif sec in ("intro", "outro"):                       # one root a bar, the fifth on 3 now and then
            if i >= 5 or sec == "outro":
                s, _ = note("bass", b, 0, 1.9 if i % 2 else 2.8, root, 70)
                if i % 2:
                    note("bass", b, 2, 0.9, fifth if fifth < 52 else fifth - 12, 58)
                if i == 5 and sec == "intro":
                    slide("bass", s, -2, 0.15)
        elif sec in ("B1", "B2") or (sec == "solo" and i < 8):   # two-feel: root, fifth, pickup
            note("bass", b, 0, 1.9, root, int(92 * lift), jitter=0.004)
            note("bass", b, 2, 1.4, fifth, int(76 * lift))
            note("bass", b, 3.5, 0.45, approach, int(66 * lift))
        elif sec == "solo":                                   # second half of the solo: walk
            t = 3 if chord in MINOR else 4
            line = [(root, root + t, fifth, approach),
                    (root, root + 2, root + t, approach),
                    (root, root + 12, fifth, approach)][int(rng.integers(0, 3))]
            for k, p in enumerate(line):
                s, _ = note("bass", b, k, 0.92, p, int((90 if k == 0 else 76) * lift), jitter=0.005)
                if k == 0 and rng.random() < 0.3:
                    slide("bass", s, -1, 0.1)
        else:                                                 # the A-section riff
            s, _ = note("bass", b, 0, 1.4, root, int(96 * lift), jitter=0.004)
            if i % 4 == 0 or rng.random() < 0.25:
                slide("bass", s, -1, 0.12)
            note("bass", b, 1.5, 0.45, fifth, int(72 * lift))
            if rng.random() < 0.5:
                note("bass", b, 2.25, 0.15, fifth, 34)        # dead note
            low = root - 2 if chord in MINOR else root - 5
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
            if i == len(INTRO) - 1:                           # pickup into the head, on beat 3
                for k, pos in enumerate((2.0, 2.25, 2.5, 2.75)):
                    note(d, b, pos, 0.2, SNARE, 40 + 14 * k, jitter=0.004)
            continue
        if sec == "outro":                                    # brushes stir under the waltz, then stop
            if i < 8:
                note(d, b, 0, 2.8, SWIRL, int(34 + 3 * (i % 2)), jitter=0.004)
            continue
        if i == 0:
            note(d, b, 0, 1, CRASH, 56)
        swell = 1 + 0.06 * ((i % 4) - 1.5) / 1.5              # 4-bar breath
        kv = lambda x: int(x * lift * swell)  # noqa: E731
        fill = i % 8 == 7
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

# "O Tannenbaum" (German folk tune, public domain), first strain with its pickup as written in G, 3/4:
# (bar, pos, dur, pitch); bar 0 holds the pickup, bars 5-8 are the repeat
_STRAIN = [(0, 0.75, 67), (0.75, 0.25, 67), (1, 1, 67), (2, 1, 69),
           (0, 0.75, 71), (0.75, 0.25, 71), (1, 1.5, 71), (2.5, 0.5, 71),
           (0, 0.5, 69), (0.5, 0.5, 71), (1, 1, 72), (2, 1, 66),
           (0, 1, 69), (1, 1, 67)]
# pitches and lengths as read off the ABC transcriptions, for the checks: D | G>G G2 A2 | B>B B3 B | AB c2 F2 | A2 G2 :|
TANNEN_ABC = [62, 67, 67, 67, 69, 71, 71, 71, 71, 69, 71, 72, 66, 69, 67]
TANNEN_DUR = [1, .75, .25, 1, 1, .75, .25, 1.5, .5, .5, .5, 1, 1, 1, 1]
MIDWINTER_ABC = ([69, 70, 72, 69, 67, 65, 67, 69, 67, 62, 67, 69, 70, 72, 69, 67, 65, 67, 69, 67, 65, 65],
                 [70, 69, 70, 72, 74, 69, 72, 69, 67, 65, 67, 69, 70, 72, 69, 67, 65, 67, 69, 67, 65, 65])
TANNEN_G = [(0, 2, 1, 62)]
for _rep in (0, 1):
    for _k, (_pos, _dur, _p) in enumerate(_STRAIN):
        TANNEN_G.append((1 + 4 * _rep + _k // 4 if _k < 12 else 4 + 4 * _rep, _pos, _dur, _p))
    if _rep == 0:
        TANNEN_G.append((4, 2, 1, 62))                                   # the pickup again, for the repeat
TANNEN = [(b, pos, dur, p + 3) for b, pos, dur, p in TANNEN_G]           # a minor third up, into B-flat
OUTRO_TUNE = TANNEN[:-1] + [(8, 1, 4.5, TANNEN[-1][3])]                  # the last B-flat rings on

# "In the Bleak Midwinter" (Gustav Holst, Cranham, 1906, public domain), as written in F, 4/4:
# first strain ("In the bleak midwinter ... water like a stone"), second ("Snow had fallen ...")
MIDWINTER_F1 = [(0, 0, 1.5, 69), (0, 1.5, 0.5, 70), (0, 2, 1, 72), (0, 3, 1, 69),
                (1, 0, 2, 67), (1, 2, 2, 65),
                (2, 0, 1.5, 67), (2, 1.5, 0.5, 69), (2, 2, 1, 67), (2, 3, 1, 62),
                (3, 0, 3, 67),
                (4, 0, 1.5, 69), (4, 1.5, 0.5, 70), (4, 2, 1, 72), (4, 3, 1, 69),
                (5, 0, 2, 67), (5, 2, 2, 65),
                (6, 0, 1, 67), (6, 1, 1, 69), (6, 2, 1.5, 67), (6, 3.5, 0.5, 65),
                (7, 0, 3, 65)]
MIDWINTER_F2 = [(0, 0, 1, 70), (0, 1, 1, 69), (0, 2, 1, 70), (0, 3, 1, 72),
                (1, 0, 2, 74), (1, 2, 2, 69),
                (2, 0, 1, 72), (2, 1, 1, 69), (2, 2, 1, 67), (2, 3, 1, 65),
                (3, 0, 3, 67)] + MIDWINTER_F1[11:]
MW1 = [(b, pos, dur, p + 5) for b, pos, dur, p in MIDWINTER_F1]          # a fourth up, into B-flat
MW2 = [(b, pos, dur, p + 5) for b, pos, dur, p in MIDWINTER_F2]
# the bridge: Gm9 | C9 | Fm9 | Bb13 | Ebmaj9 | Ab13 | Cm9 | F13
BRIDGE = [(0, 0, 1, 74), (0, 1, 0.5, 77), (0, 1.5, 2.5, 81),
          (1, 0, 0.5, 79), (1, 0.5, 0.5, 76), (1, 1, 1, 74), (1, 2, 2, 70),
          (2, 0, 1, 72), (2, 1, 0.5, 75), (2, 1.5, 2.5, 79),
          (3, 0, 0.5, 77), (3, 0.5, 0.5, 74), (3, 1, 1, 72), (3, 2, 2, 68),
          (4, 0, 1.5, 67), (4, 1.5, 0.5, 70), (4, 2, 2, 74),
          (5, 0, 0.5, 75), (5, 0.5, 0.5, 72), (5, 1, 1, 70), (5, 2, 2, 66),
          (6, 0, 1, 67), (6, 1, 0.5, 70), (6, 1.5, 0.5, 74), (6, 2, 2, 75),
          (7, 0, 0.5, 74), (7, 0.5, 0.5, 72), (7, 1, 1, 69), (7, 2, 0.5, 70), (7, 2.5, 1.5, 65)]
FLUTE = dict(depth=0.0, rate=5.0)


def sing(stem: str, start: float, length: float, vel: int, scoop: bool, fall: bool,
         depth: float = 0.22, rate: float = 5.2) -> None:
    """Breath and voice for a monophonic line: swell, scoop, delayed vibrato, fall-off."""
    if scoop:
        slide(stem, start, -0.5, 0.12)
    else:
        bend(stem, start - 0.005, 0)
    base = 78 + vel // 6
    cc(stem, start - 0.005, 11, base)
    steps = max(int(length * 12), 1)
    for k in range(1, steps + 1):
        t = start + length * k / steps
        x = k / steps
        cc(stem, t, 11, base + (30 if length >= 1 else 14) * np.sin(np.pi * min(x * 1.3, 1)) - (10 if x > 0.85 else 0))
    if length >= 1.2 and depth and stem not in NATURAL_VIB:  # vibrato only once a long note settles
        onset = start + 0.6
        n = int((length - 0.6) * 36)
        for k in range(n):
            t = onset + k / 36
            ramp = min(k / 18, 1)
            bend(stem, t, depth * ramp * np.sin(2 * np.pi * rate * (t - onset) * SPB))
    if fall:
        end = start + length
        for k in range(6):
            bend(stem, end - 0.16 + k * 0.03, -1.2 * (k / 5) ** 2)


def phrase(stem: str, sec: str, notes, vel0: int, shift: int = 0, falls: bool = True,
           grace: bool = False, depth: float = 0.2, rate: float = 5.2) -> None:
    """Play a written line with breath: scoops after rests, falls before long gaps."""
    base, meter = START[sec], FORM[START[sec]][1]
    last_end = -9.0
    for k, (off, pos, dur, p) in enumerate(notes):
        p += shift
        vel = int((vel0 + (6 if dur >= 1 else 0) - (4 if dur <= 0.5 else 0)) * LIFT[sec])
        if grace and dur >= 1 and rng.random() < 0.4:
            note(stem, base + off, pos - 0.12, 0.1, p - 1, vel - 14, late=0.03, jitter=0.004)
        s, ln = note(stem, base + off, pos, dur, p, vel, late=0.04, jitter=0.012)
        gap = (notes[k + 1][0] * meter + notes[k + 1][1] - off * meter - pos - dur
               if k + 1 < len(notes) else 9)
        sing(stem, s, ln, vel, scoop=s - last_end > 0.4 and rng.random() < 0.35,
             fall=falls and gap >= 1 and dur >= 0.5 and rng.random() < 0.3, depth=depth, rate=rate)
        last_end = s + ln


def mallet(stem: str, sec: str, notes, vel0: int, shift: int = 0) -> None:
    """Vibes and celesta: accent the beats, let each note ring a little past its written length."""
    base = START[sec]
    for off, pos, dur, p in notes:
        vel = int((vel0 + (6 if pos % 1 == 0 else 0) - (6 if dur <= 0.5 else 0)) * LIFT[sec])
        note(stem, base + off, pos, dur + 0.15, p + shift, vel, late=0.01, jitter=0.006)


def write_melody() -> None:
    mallet("vibes", "intro", TANNEN, 62, shift=12)
    mallet("celesta", "intro", TANNEN, 56, shift=12)
    phrase("flute", "A1", MW1, 74, falls=False, **FLUTE)
    phrase("flute", "A2", MW2, 76, grace=True, falls=False, **FLUTE)
    mallet("vibes", "B1", BRIDGE, 80)
    solo_line()
    phrase("flute", "solo", SOLO_LINE, 78, **FLUTE)
    phrase("flute", "B2", BRIDGE, 78, falls=False, **FLUTE)
    phrase("flute", "A3", MW1, 80, grace=True, falls=False, **FLUTE)
    mallet("vibes", "A3", MW1, 72)
    phrase("flute", "outro", OUTRO_TUNE, 66, falls=False, **FLUTE)
    mallet("vibes", "outro", OUTRO_TUNE, 60, shift=12)


def write_keys() -> None:
    """Vibes comping under the flute (A2, the back half of the solo), the bars held by the
    pedal at both ends, and celesta snowflakes in the gaps of A1 and A3."""
    up = lambda v: tuple(p + 12 for p in v[1:])  # noqa: E731
    for b, (sec, meter, chord, i) in enumerate(FORM):
        root, v = chord
        if sec in ("intro", "outro"):
            pedal("vibes", b)
        elif sec == "A2" or (sec == "solo" and i >= 8):
            roll("vibes", b, 1.5, 0.8, up(v), int(46 * LIFT[sec]), spread=0.02)
            roll("vibes", b, 3.5, 0.6, up(MOVE[chord]), int(40 * LIFT[sec]), spread=0.02)
        if sec in ("A1", "A3") and i % 2 == 1:
            flakes = sorted({p + 24 for p in v} | {p + 36 for p in v[:2]})
            for pos in (3.0, 3.5):
                note("celesta", b, pos, 0.6, int(rng.choice(flakes)), int(rng.integers(34, 46)), jitter=0.004)


def write_pad() -> None:
    """Strings: the bridges, the back half of the solo, A3, and a soft bed under the waltz
    once the bass comes in."""
    for b, (sec, meter, (root, v), i) in enumerate(FORM):
        last = b == len(FORM) - 1
        dur = 8 if last else meter
        if sec in ("B1", "B2", "A3", "outro") or (sec == "solo" and i >= 8) or (sec == "intro" and i >= 5):
            for p in v[1:]:
                note("pad", b, 0, dur, p + 12, 34 if sec in ("intro", "outro") else 42, jitter=0.0)

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


def wind(length: int) -> np.ndarray:
    """Wind at the window: band-passed noise that gusts and drifts across, muffled by the glass."""
    n = filt(rng.standard_normal((length, 2)).astype(np.float32), "bandpass", (180, 1400))
    t = np.arange(length) / SR
    gust = (0.5 + 0.5 * np.sin(2 * np.pi * 0.045 * t + rng.uniform(0, 6))) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.13 * t))
    pan = 0.5 + 0.3 * np.sin(2 * np.pi * 0.03 * t)
    out = n * (0.25 + 0.75 * gust)[:, None]
    out[:, 0] *= np.sqrt(1 - pan)
    out[:, 1] *= np.sqrt(pan)
    return (out * 1.2).astype(np.float32)


def fire(length: int) -> np.ndarray:
    """A log fire across the room: a low breathing roar, soft crackle and the odd sharp pop."""
    t = np.arange(length) / SR
    roar = filt(rng.standard_normal((length, 2)).astype(np.float32), "bandpass", (60, 400))
    roar *= (0.7 + 0.3 * np.sin(2 * np.pi * 0.21 * t + rng.uniform(0, 6)))[:, None] * 0.25
    out = np.zeros((length, 2), np.float32)
    k = 0.0
    while k * SR < length:
        pop = rng.random() < 0.06
        n = int(rng.uniform(0.002, 0.006 if not pop else 0.02) * SR)
        burst = rng.standard_normal(n).astype(np.float32) * np.exp(-np.arange(n) / (n / 4))
        pan = rng.uniform(0.35, 0.65)
        i = int(k * SR)
        m = min(n, length - i)
        g = rng.uniform(0.1, 0.5) * (3.0 if pop else 1.0)
        out[i:i + m, 0] += burst[:m] * g * np.sqrt(1 - pan)
        out[i:i + m, 1] += burst[:m] * g * np.sqrt(pan)
        k += rng.exponential(0.09)
    crackle = filt(out, "bandpass", (900, 6000))
    return (roar + crackle).astype(np.float32)

def vinyl(length: int) -> np.ndarray:
    v, sr = sf.read(VINYL, dtype="float32")
    v = v.mean(1) if v.ndim > 1 else v
    v = np.tile(v, length // len(v) + 1)[:length]
    return np.stack([v, np.roll(v, 517)], axis=1)


KIT = ROOT / "samples" / "drummachines"

HIPHOP = ("A1", "A2", "B1", "solo", "B2", "A3")    # sections where the sampled beat plays
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
        if b == len(FORM) - 1:                                   # one low B-flat under the last chord
            SUB_NOTES.append((a, 7.0, sub_pitch(root)))
        elif sec == "B2" or (sec == "B1" and i % 2 == 0):
            SUB_NOTES.append((a, 3.9, sub_pitch(root)))
        elif sec in HIPHOP:
            SUB_NOTES.append((swing(a), 2.45, sub_pitch(root)))
            second = root - 6 if chord is F13 else root              # B under the F13, into B-flat
            SUB_NOTES.append((swing(a + 2.5), 1.4, sub_pitch(second)))
        elif sec == "intro" and i == len(INTRO) - 1:
            SUB_NOTES.append((a + 2, 0.9, sub_pitch(41)))


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

SUB_RIDE = {"A1": 1.0, "A2": 2.0, "B1": -2.0, "solo": 0.0, "B2": 2.5, "A3": 4.5}   # dB; the strings and the doubled lead crowd the mids late on


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
    write_piano(); write_bass(); write_drums(); write_melody(); write_keys(); write_pad(); write_sub()
    tail = 7.0
    length = int((TOTAL_BEATS * SPB + tail) * SR)
    (OUT / "stems").mkdir(parents=True, exist_ok=True)
    (OUT / "exports").mkdir(exist_ok=True)
    (OUT / "window_frost.mid").write_bytes(smf([tempo_track()] + [stem_track(n) for n in STEMS]))

    with tempfile.TemporaryDirectory() as td:
        st = {n: render(n, length, Path(td)) for n in STEMS}

    a_start, o_start, end_t = sec_time(START["A1"]), sec_time(START["outro"]), TOTAL_BEATS * SPB
    # piano: soft and warm under the waltz, opens up for the head, closes again for the outro
    p_dark, p_open = filt(st["piano"], "lowpass", 2200), filt(st["piano"], "lowpass", 7000)
    open_env = env([(0, 0), (a_start - 2, 0), (a_start, 1), (o_start - 4, 1),
                    (o_start + 4, 0.4), (end_t + tail, 0.4)], length)
    st["piano"] = p_dark * (1 - open_env) + p_open * open_env
    st["drums"] = filt(tape(filt(st["drums"], "highpass", 40), 2.2), "lowpass", 9000)
    st["bass"] = tape(filt(filt(st["bass"], "highpass", 90), "lowpass", 6000), 1.4)
    st["flute"] = tape(filt(filt(st["flute"], "highpass", 220), "lowpass", 8000), 1.1)
    # vibes: the motor on, the two sides of the bar a little out of step
    motor = 2 * np.pi * 3.6 * np.arange(length) / SR
    trem = np.stack([1 - 0.18 * (1 + np.sin(motor)), 1 - 0.18 * (1 + np.sin(motor + 0.7))], 1)
    st["vibes"] = (filt(st["vibes"], "highpass", 180) * trem).astype(np.float32)
    st["celesta"] = filt(st["celesta"], "highpass", 400)
    st["pad"] = filt(filt(st["pad"], "highpass", 200), "lowpass", 4000)
    beat, kick_only, kicks = beat_stem(length)
    sub = sub_stem(length) * duck(kicks, length, 5.0, 0.09) * sub_ride(length)
    for n in ("piano", "pad"):
        st[n] = st[n] * duck(kicks, length, 2.0, 0.25)
    st["bass"] = st["bass"] * duck(kicks, length, 2.5, 0.15)
    for n in st:
        sf.write(OUT / "stems" / f"{n}.wav", st[n], SR, subtype="PCM_24")
    sf.write(OUT / "stems" / "beat.wav", beat, SR, subtype="PCM_24")
    sf.write(OUT / "stems" / "sub.wav", sub, SR, subtype="PCM_24")

    mix = sum(st[n] * db(STEMS[n][4]) for n in STEMS) + beat * db(BEAT_GAIN) + sub * db(SUB_GAIN)
    # the fire stays across the room; the wind comes up at both ends, when the band is quiet
    wind_env = env([(0, db(-22)), (a_start, db(-34)), (o_start, db(-34)),
                    (end_t, db(-21)), (end_t + tail, db(-22))], length)
    fire_env = env([(0, db(-20)), (a_start, db(-30)), (o_start, db(-30)),
                    (end_t, db(-20)), (end_t + tail, db(-20))], length)
    amb = wind(length) * wind_env + fire(length) * fire_env + vinyl(length) * db(-25)
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
    intro_end = int((a_start - 3 * SPB) * SR)          # before the snare pickup
    o0, o1 = int((o_start + 1.5) * SR), int(sec_time(len(FORM) - 1) * SR)
    checks = {
        "loudness within 0.5 LU of target": abs(lufs - TARGET_LUFS) < 0.5,
        "true peak <= -1.0 dBTP": tp <= -0.95,
        "length 3:00-4:00": 180 <= dur <= 240,
        "every stem has audio": all(np.abs(s).max() > 1e-3 for s in st.values()),
        "drums silent in intro": np.abs(st["drums"][:intro_end]).max() < 1e-3,
        "intro and outro are 10 bars of 3/4": [m for s, m, *_r in FORM if s in ("intro", "outro")] == [3] * 20,
        "solo is 16 bars over both strains": [c for s, _m, c, _i in FORM if s == "solo"] == A_CH + A2_CH,
        "flute solo within F4-D6": all(FL_LO <= p <= FL_HI for _b, _p, _d, p in SOLO_LINE),
        "O Tannenbaum is the folk tune a minor third up":
            [m - 3 for *_x, m in TANNEN] == TANNEN_ABC * 2 and [d for _b, _p, d, _m in TANNEN_G][:15] == TANNEN_DUR,
        "Midwinter is Holst's tune a fourth up": [m - 5 for *_x, m in MW1] == MIDWINTER_ABC[0]
            and [m - 5 for *_x, m in MW2] == MIDWINTER_ABC[1],
        "every line fits its changes": fits(TANNEN, INTRO) and fits(OUTRO_TUNE, OUTRO) and fits(MW1, A_CH)
            and fits(MW2, A2_CH) and fits(BRIDGE, B_CH) and fits(SOLO_LINE, A_CH + A2_CH),
        "ends on Bbmaj9": FORM[-1][2] is BBM9,
        "no beat or sub before A1": max(np.abs(beat[:intro_end]).max(), np.abs(sub[:intro_end]).max()) < 1e-4,
        "no beat in the outro": np.abs(beat[o0:o1]).max() < 1e-4,
        "sub is mono": np.allclose(sub[:, 0], sub[:, 1]),
        "lows (<120 Hz) 3-9 dB over mids in A3":
            3 <= band_gap(mix, sec_time(START["A3"]), sec_time(START["outro"])) <= 9,
    }
    for k, ok in checks.items():
        print(f"{'ok  ' if ok else 'FAIL'} {k}")
    gaps = {s: band_gap(mix, sec_time(START[s]), sec_time(START[s]) + 8 * 4 * SPB) for s in START}
    print("gaps " + " ".join(f"{s} {g:.1f}" for s, g in gaps.items()))
    print(f"{sum(checks.values())}/{len(checks)} checks, {lufs:.1f} LUFS, TP {tp:.1f} dBTP, "
          f"{int(dur // 60)}:{int(dur % 60):02d}, {len(FORM)} bars, {len(SOLO_LINE)} solo notes")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
