"""A composed song (.am.json from gen.js) reduced to its musical skeleton:

  key            tonic pitch class and mode (from all pitched notes)
  chords         one chord per bar: (root pc, quality) detected from the harmony and bass, downbeat bass weighted
  melody         one line: the top voice of the lead parts (octave doubling and inner voices dropped)
  bass           one line: the lowest voice of the bass parts
  sections       start bar, bars, which roles play, chord signature
  loops          automatic picks: A (chorus), V (verse), B (bridge), each 4 or 8 bars, bar-aligned
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

NOTE = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
SHARP_KEYS = {("major", t) for t in (7, 2, 9, 4, 11, 6, 1)} | {("minor", t) for t in (4, 11, 6, 1, 8, 3)}
_spell = {"names": NOTE}


def spell_for(tonic: int, mode: str) -> None:
    """Name notes the way the key does (C# minor has G#, F minor has Ab)."""
    _spell["names"] = SHARP if (mode, tonic) in SHARP_KEYS else FLAT
ROLE = {0: "lead", 1: "lead", 2: "lead", 3: "keys", 4: "keys", 5: "keys", 6: "pad", 7: "pad", 8: "pad", 9: "drums",
        11: "bass", 12: "bass", 13: "bass"}
# chord templates (intervals above the root) and a small prior (simpler chords preferred)
TEMPLATES = {"": ((0, 4, 7), 0.0), "m": ((0, 3, 7), 0.0), "7": ((0, 4, 7, 10), 0.25), "maj7": ((0, 4, 7, 11), 0.25),
             "m7": ((0, 3, 7, 10), 0.25), "dim": ((0, 3, 6), 0.4), "m7b5": ((0, 3, 6, 10), 0.5), "sus4": ((0, 5, 7), 0.35),
             "sus2": ((0, 2, 7), 0.35), "6": ((0, 4, 7, 9), 0.45), "m6": ((0, 3, 7, 9), 0.45)}
MAJOR = (0, 2, 4, 5, 7, 9, 11)
MINOR = (0, 2, 3, 5, 7, 8, 10)


@dataclass
class Note:
    t: float          # beats from song start
    d: float          # beats
    p: int            # MIDI pitch
    v: float          # 0-1


@dataclass
class Chord:
    root: int
    quality: str

    @property
    def name(self) -> str:
        return _spell["names"][self.root] + self.quality

    @property
    def tones(self) -> list[int]:
        return [(self.root + i) % 12 for i in TEMPLATES[self.quality][0]]

    @property
    def minor(self) -> bool:
        return self.quality in ("m", "m7", "m6", "dim", "m7b5")


@dataclass
class Section:
    start_bar: int
    bars: int
    roles: dict
    chords: list

    @property
    def signature(self):
        """Chord roots bar by bar: repeats of a section match even if a colour tone was detected differently."""
        return tuple(c.root for c in self.chords)


@dataclass
class Skeleton:
    name: str
    seed: int
    bars: int
    tonic: int
    mode: str
    chords: list
    melody: list
    bass: list
    parts: dict
    sections: list
    loops: dict = field(default_factory=dict)
    doc: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{_spell['names'][self.tonic]} {self.mode}"

    def chords_in(self, bar: int, n: int) -> list:
        return self.chords[bar:bar + n]


def read_events(doc: dict) -> dict[str, list[Note]]:
    md = doc["midiData"]
    ppq = md["midiDivisions"]
    t = 0
    held: dict = {}
    parts: dict[str, list[Note]] = {}
    for e in md["midiTracks"][0]["trackEvents"]:
        t += e["eventTime"]
        m = e["eventMessage"]
        if m["messageClass"] != "VoiceMessage":
            continue
        k = (m["channel"], m["data1"])
        if m["status"] == "NOTE_ON" and m["data2"] > 0:
            held[k] = (t, m["data2"])
        elif k in held:
            t0, v = held.pop(k)
            parts.setdefault(ROLE.get(m["channel"], f"ch{m['channel']}"), []).append(Note(t0 / ppq, (t - t0) / ppq, int(m["data1"]), v / 127))
    return {k: sorted(v, key=lambda n: (n.t, n.p)) for k, v in parts.items()}


def one_line(notes: list[Note], top: bool) -> list[Note]:
    by: dict[float, Note] = {}
    for n in notes:
        k = round(n.t, 3)
        if k not in by or (n.p > by[k].p if top else n.p < by[k].p):
            by[k] = n
    line = [by[k] for k in sorted(by)]
    for a, b in zip(line, line[1:]):          # a line is monophonic: cut overlaps
        if a.t + a.d > b.t:
            a.d = max(0.05, b.t - a.t)
    return line


def detect_key(parts) -> tuple[int, str]:
    w = [0.0] * 12
    for r, ns in parts.items():
        if r == "drums":
            continue
        for n in ns:
            w[n.p % 12] += n.d
    best = max(((sum(w[(r + i) % 12] for i in sc) + (0.15 * w[r]), r, nm) for r in range(12) for nm, sc in (("major", MAJOR), ("minor", MINOR))))
    return best[1], best[2]


def detect_chord(notes: list[Note], a: float, b: float, key: tuple[int, str] | None = None) -> Chord | None:
    w = [0.0] * 12
    low = None
    for n in notes:
        ov = min(b, n.t + n.d) - max(a, n.t)
        if ov <= 0:
            continue
        w[n.p % 12] += ov
        if n.t <= a + 0.05 and (low is None or n.p < low.p):
            low = n
    tot = sum(w)
    if tot <= 0:
        return None
    best = None
    for r in range(12):
        for q, (iv, prior) in TEMPLATES.items():
            tones = {(r + i) % 12 for i in iv}
            sc = sum(w[p] for p in tones) / tot - 1.3 * sum(w[p] for p in range(12) if p not in tones) / tot - 0.08 * prior
            if low is not None and low.p % 12 == r:
                sc += 0.12
            if w[r] == 0:                                   # a chord whose root never sounds is a guess
                sc -= 0.5
            sc -= 0.06 * sum(1 for p in tones if w[p] == 0)  # missing tones (e.g. an open fifth gets the key's third)
            if key is not None:                             # ties go to the key: natural or harmonic minor / major
                tonic, mode = key
                scale = {(tonic + i) % 12 for i in (MINOR if mode == "minor" else MAJOR)} | ({(tonic + 11) % 12} if mode == "minor" else set())
                sc += 0.04 * sum(1 for p in tones if p in scale) - 0.12 * sum(1 for p in tones if p not in scale)
            if best is None or sc > best[0]:
                best = (sc, Chord(r, q))
    return best[1]


def load(path: Path) -> Skeleton:
    doc = json.loads(Path(path).read_text())
    parts = read_events(doc)
    beats = doc["lengthBeats"]
    bars = int(beats // 4)
    tonic, mode = detect_key(parts)
    spell_for(tonic, mode)
    harm = parts.get("pad", []) + parts.get("keys", []) + [Note(n.t, n.d, n.p, n.v) for n in parts.get("bass", [])] * 2
    # per half bar, then the bar takes its downbeat chord (merging two chords would invent a sus/7th
    # chord that was never played); the second half is kept for genres with two chords per bar
    chords, halves, last = [], [], None
    for b in range(bars):
        h1 = detect_chord(harm, b * 4, b * 4 + 2, (tonic, mode)) or last or Chord(tonic, "m" if mode == "minor" else "")
        h2 = detect_chord(harm, b * 4 + 2, b * 4 + 4, (tonic, mode)) or h1
        chords.append(h1)
        halves.append((h1, h2))
        last = h2
    melody = one_line(parts.get("lead", []), top=True)
    bass = one_line(parts.get("bass", []), top=False)
    if doc.get("sectionTimes"):
        bounds = [0.0] + [float(x) for x in doc["sectionTimes"]]
    else:                                   # older files: the composer writes one tempo event per section
        md, t, bounds = doc["midiData"], 0, []
        for e in md["midiTracks"][0]["trackEvents"]:
            t += e["eventTime"]
            if e["eventMessage"]["messageClass"] == "SetTempoMessage":
                bounds.append(round(t / md["midiDivisions"], 3))
        bounds = sorted(set(bounds + [0.0, float(beats)]))
    sections = []
    for a, b in zip(bounds, bounds[1:]):
        if a % 4 or b - a < 16:
            continue
        sb, nb = int(a // 4), int((b - a) // 4)
        roles = {r: sum(1 for n in ns if a <= n.t < b) for r, ns in parts.items()}
        sections.append(Section(sb, nb, {r: c for r, c in roles.items() if c}, chords[sb:sb + nb]))
    sk = Skeleton(doc["name"], doc["seed"], bars, tonic, mode, chords, melody, bass, parts, sections, doc=doc)
    sk.halves = halves
    sk.loops = pick_loops(sk)
    return sk


def pick_loops(sk: Skeleton) -> dict:
    """A = the chorus: the most repeated full section (lead + bass + chords), densest melody.
    V = a different full (or lead + bass) section, earliest. B = a third signature, else V.
    A section followed by one with the same chords becomes one 8-bar loop (the composer's call and response)."""
    def full(s):
        return "lead" in s.roles and "bass" in s.roles and ({"pad", "keys"} & set(s.roles))
    def extend(i):
        s = sk.sections[i]
        if s.bars == 4 and i + 1 < len(sk.sections) and sk.sections[i + 1].start_bar == s.start_bar + 4 and sk.sections[i + 1].signature == s.signature:
            return {"start_bar": s.start_bar, "bars": 8}
        return {"start_bar": s.start_bar, "bars": min(8, s.bars)}
    full_idx = [i for i, s in enumerate(sk.sections) if full(s)]
    if not full_idx:
        full_idx = [i for i, s in enumerate(sk.sections) if "lead" in s.roles] or list(range(len(sk.sections)))
    if not full_idx:
        return {k: {"start_bar": 0, "bars": min(8, sk.bars), "chords": [c.name for c in sk.chords_in(0, min(8, sk.bars))]} for k in "AVB"}
    count: dict = {}
    for i in full_idx:
        count[sk.sections[i].signature] = count.get(sk.sections[i].signature, 0) + 1
    a_i = max(full_idx, key=lambda i: (count[sk.sections[i].signature], sk.sections[i].roles.get("lead", 0) / sk.sections[i].bars, -i))
    loops = {"A": extend(a_i)}
    used = {sk.sections[a_i].signature}
    others = [i for i, s in enumerate(sk.sections) if s.signature not in used and ("lead" in s.roles) and "bass" in s.roles]
    v_i = min(others, default=None)
    if v_i is not None:
        loops["V"] = extend(v_i)
        used.add(sk.sections[v_i].signature)
    rest = [i for i, s in enumerate(sk.sections) if s.signature not in used and "lead" in s.roles]
    loops["B"] = extend(rest[0]) if rest else loops.get("V", loops["A"])
    loops.setdefault("V", loops["A"])
    for k, L in loops.items():
        L["chords"] = [c.name for c in sk.chords_in(L["start_bar"], L["bars"])]
    return loops


if __name__ == "__main__":
    import sys
    for a in sys.argv[1:]:
        sk = load(Path(a))
        print(f"{sk.name}: {sk.key}, {sk.bars} bars, melody {len(sk.melody)} notes, bass {len(sk.bass)} notes")
        for s in sk.sections:
            print(f"  bar {s.start_bar:3d} x{s.bars:2d}  {','.join(sorted(s.roles)):24s} {' '.join(c.name for c in s.chords)}")
        for k, L in sk.loops.items():
            print(f"  loop {k}: bars {L['start_bar']}-{L['start_bar'] + L['bars'] - 1}  {' '.join(L['chords'])}")
