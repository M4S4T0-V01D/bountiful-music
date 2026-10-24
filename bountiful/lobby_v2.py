#!/usr/bin/env python3
"""Pepperoni v2: the user's own LMMS project (tracks/pepperoni/pepperoni.mmp, their volumes, effects,
crashes and master volume) with two changes, written to a NEW file (pepperoni-v2.mmp); the original is never touched.

1. The lead comes in at bar 9 (with the bass) instead of bar 41: the hook's melody, one loop earlier, a little softer
   (85% velocity) so the hook still lifts when it arrives.
2. Halfway, after the first hook, a 16-bar 'bit beat' (new bars 57-72; 8 bars at first, doubled at the user's request):
   copies of the drums, bass, organ stabs and (from bar 65) the vocal chops play the whole hook again through a mixer channel
   'Bit beat' carrying LMMS's own Bitcrush, with automation clips on its sample rate and bit levels in two waves: light,
   a hard crush by bar 59, held, easing to medium over bars 63-64, a second, harder dive (the peak) by bar 66, held, then
   clearing back to clean over bars 69-72. The user's 2-bar 'Rewind' (clean break) follows, then the second
   hook, so the return comes out of a clean beat rather than straight out of the effect. Everything after bar 56 moves 8 bars later.
3. A second lead with its own melody in the second hook (new bars 75-90, loop B, which had no lead): Ice Rhodes2 playing the
   melody Bountiful Music wrote for loop B (never used in v1), legato and more dynamic, for more feel.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/lobby_v2.py
"""
from __future__ import annotations

import copy
import sys as _sys
import hashlib
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_sys.path.insert(0, str(Path(__file__).resolve().parent))
TRACK = ROOT / "tracks" / "pepperoni"
SRC, DST = TRACK / "pepperoni.mmp", TRACK / "pepperoni-v2.mmp"
BAR = 192                                   # LMMS ticks per 4/4 bar
CUT = 56 * BAR                              # the end of the first hook (bar 56): the new section goes here
INS = 16 * BAR                              # 16 new bars (the whole hook again)
HOOK = 40 * BAR                             # bar 41: the first hook (loop A from its first bar)
LEAD_AT = 8 * BAR                           # bar 9: the 'Bass' section, also loop A from its first bar
LEAD_VEL = 0.85
CRUSH = ["drum - kick", "drum - snare", "drum - ghost", "drum - hat", "drum - open", "drum - clap", "drum - cowbell", "bass - ", "stab - ", "vox - "]
VOX_FROM = 8 * BAR                          # the chops join the bit beat for its second half
# the crush, (tick in the section, sample rate Hz, levels), two waves: light -> hard by bar 59 -> held -> medium by 63 ->
# a harder dive (the peak) by bar 66 -> held -> clear by the end of bar 72
RATE = [(0, 22050, 64), (2 * BAR, 4000, 10), (4 * BAR, 4000, 10), (6 * BAR, 11025, 32), (8 * BAR, 11025, 32),
        (9 * BAR + 96, 3000, 8), (12 * BAR, 3000, 8), (15 * BAR, 16000, 64), (16 * BAR - 12, 44100, 256)]
ID_RATE, ID_LEVELS = 917001, 917002


def notes_abs(track):
    for clip in track.findall("midiclip"):
        base = int(clip.get("pos"))
        for n in clip.findall("note"):
            yield clip, n, base + int(n.get("pos"))


SECOND_HOOK = (58 * BAR) + INS              # v1 bars 59-74 (loop B from its first bar) -> v2 bars 75-90
SECOND_LEN = 16 * BAR
LEAD2 = {"zyn": "Rhodes/0013-Ice Rhodes2.xiz", "label": "Ice Rhodes2 (ZynAddSubFX - Rhodes), second lead", "vol": 200}
LEAD2_AMP = 160                             # % on LMMS's Amplifier: with the fader at 200, the Rhodes sits level with the main lead
LEAD2_MELODY = {"articulation": "legato", "humanize_ms": 10, "velocity": [0.5, 0.95], "max_notes_per_bar": 5, "push_ms": 4}


def loops_of_lobby(melody=None, seed=1):
    """Re-perform Pepperoni's composition exactly as its build did (same spec, same seed)."""
    import numpy as np
    import album_mezzanine_v2 as A2
    import build as B
    import lmms_tracks as LT
    import skeleton as SK
    spec = A2.SPECS["pepperoni"]
    g = LT.deep_update(copy.deepcopy(B.genres()[spec["genre"]]), spec["overrides"])
    if melody:
        g["melody"] = {**g.get("melody", {}), **melody}
    s2 = B.stretched(SK.load(spec["song"]), g.get("stretch", 1))
    return B.produce_loops(s2, g, np.random.default_rng(seed)), g


def second_lead(lead_track):
    """loop B's melody as LMMS notes (tick, len, key, vol) over the second hook; checks first that loop A's re-performed
    melody is the one already in the user's lead track (so loop B's belongs to the same performance)."""
    loops, g = loops_of_lobby()
    clip = lead_track.find("midiclip")
    have = sorted((int(clip.get("pos")) + int(n.get("pos")), int(n.get("key"))) for n in clip.findall("note"))
    have = [k for t, k in have if HOOK <= t < HOOK + 4 * BAR]
    mine = [p for (t, d, p, v, o) in sorted(loops["A"]["parts"]["lead"]) if t < 16]
    shift = (have[0] - mine[0]) if have and mine else 0
    if [k - shift for k in have] != mine:
        raise SystemExit(f"loop A melody does not match the project's lead: {have[:8]} vs {mine[:8]}")
    loopsB, _ = loops_of_lobby(LEAD2_MELODY, seed=2)
    L = loopsB["B"]
    notes = []
    for rep in range(SECOND_LEN // (L["bars"] * BAR)):
        for (t, d, p, v, o) in sorted(L["parts"]["lead"]):
            tick = SECOND_HOOK + rep * L["bars"] * BAR + round((t + o) * 48)
            # true pitch: the project's -12 was the Brazz preset's octave correction, not the melody's
            notes.append((tick, max(4, round(d * 48)), p, int(min(200, max(1, 1.6 * (40 + 120 * v * (1.0 if rep else 0.9)))))))
    print(f"second lead: loop B melody, {len(notes)} notes, keys {min(n[2] for n in notes)}-{max(n[2] for n in notes)} (project octave shift {shift:+d})")
    return notes


def LEAD2_XML(notes):
    import sys
    sys.path.insert(0, "/home/s0ich1r0/Documents/Projects/intelligent-jungle")
    from engine import lmms as LM
    v = {k: x for k, x in LEAD2.items() if k != "label"}
    name = "lead2 - " + LEAD2["label"]
    rel = [(t - SECOND_HOOK, l, k, vol) for t, l, k, vol in notes]
    xml = LM.project_xml(116, [(name, LM.instrument_xml(v), rel, False)], SECOND_LEN)
    tr = ET.fromstring(xml[xml.index("<lmms-project"):]).find("song/trackcontainer/track")
    tr.find("midiclip").set("pos", str(SECOND_HOOK))
    it = tr.find("instrumenttrack")
    fxc = it.find("fxchain")
    if fxc is None:
        fxc = ET.SubElement(it, "fxchain", {"numofeffects": "0", "enabled": "1"})
    eff = ET.SubElement(fxc, "effect", {"name": "amplifier", "on": "1", "wet": "1", "autoquit": "1", "autoquit_numerator": "4",
                                        "autoquit_denominator": "4", "autoquit_syncmode": "0"})
    ET.SubElement(eff, "amplifiercontrols", {"volume": str(LEAD2_AMP), "pan": "0", "left": "100", "right": "100"})
    ET.SubElement(eff, "key")
    fxc.set("numofeffects", str(len(fxc.findall("effect"))))
    fxc.set("enabled", "1")
    return ET.tostring(tr, encoding="unicode")


def main():
    before = hashlib.sha256(SRC.read_bytes()).hexdigest()
    tree = ET.parse(SRC)
    root = tree.getroot()
    tc = root.find("song/trackcontainer")
    tracks = tc.findall("track")
    by = lambda prefix: next(t for t in tracks if t.get("name", "").startswith(prefix))

    # source material for the new section (before anything moves): the hook's first 8 bars, per track
    section = {}
    for t in tracks:
        nm = t.get("name", "")
        if any(nm.startswith(p) for p in CRUSH):
            lo = HOOK + (VOX_FROM if nm.startswith("vox - ") else 0)
            section[nm] = [(a - HOOK, copy.deepcopy(n)) for _, n, a in notes_abs(t) if lo <= a < HOOK + INS]
    lead = by("lead - ")
    early = [(a - HOOK, copy.deepcopy(n)) for _, n, a in notes_abs(lead) if HOOK <= a < CUT]

    # 1) open the gap: everything from bar 57 on moves 8 bars later; notes may not ring across the cut
    for t in tracks:
        for clip in t.findall("midiclip"):
            base = int(clip.get("pos"))
            if base >= CUT:
                clip.set("pos", str(base + INS))
                continue
            moved = False
            for n in clip.findall("note"):
                a = base + int(n.get("pos"))
                if a >= CUT:
                    n.set("pos", str(int(n.get("pos")) + INS))
                    moved = True
                elif a + int(n.get("len")) > CUT:
                    n.set("len", str(CUT - a))
            if moved or base + int(clip.get("len")) > CUT:
                clip.set("len", str(int(clip.get("len")) + INS))

    # 2) the lead from bar 9
    lclip = lead.find("midiclip")
    for rel, n in early:
        n.set("pos", str(LEAD_AT + rel - int(lclip.get("pos"))))
        n.set("vol", str(max(1, round(int(n.get("vol")) * LEAD_VEL))))
        lclip.append(n)

    # 3) the mixer channel with Bitcrush
    mixer = root.find("song/mixer")
    ch = ET.SubElement(mixer, "mixerchannel", {"muted": "0", "num": "1", "soloed": "0", "name": "Bit beat", "volume": "1"})
    fxc = ET.SubElement(ch, "fxchain", {"numofeffects": "1", "enabled": "1"})
    eff = ET.SubElement(fxc, "effect", {"autoquit_numerator": "4", "autoquit_syncmode": "0", "autoquit_denominator": "4", "autoquit": "1",
                                        "wet": "1", "on": "1", "name": "bitcrush"})
    bc = ET.SubElement(eff, "bitcrushcontrols", {"ingain": "0", "innoise": "0", "outgain": "0", "outclip": "0", "stereodiff": "0",
                                                 "rateon": "1", "depthon": "1"})
    ET.SubElement(bc, "rate", {"id": str(ID_RATE), "value": str(RATE[0][1]), "scale_type": "linear"})
    ET.SubElement(bc, "levels", {"id": str(ID_LEVELS), "value": str(RATE[0][2]), "scale_type": "linear"})
    ET.SubElement(eff, "key")
    ET.SubElement(ch, "send", {"channel": "0", "amount": "1"})

    # 4) the bit-beat tracks: copies of the user's tracks (same instrument, volume, effects), routed to the 'Bit beat' channel
    last = tracks[-1]
    insert_at = list(tc).index(last) + 1
    for k, (nm, notes) in enumerate(section.items()):
        src = next(t for t in tracks if t.get("name") == nm)
        dup = copy.deepcopy(src)
        short = nm.split(" - ")[1] if nm.startswith("drum - ") else nm.split(" - ")[0]
        dup.set("name", f"bitbeat - {short}")
        dup.find("instrumenttrack").set("mixch", "1")
        for clip in dup.findall("midiclip"):
            dup.remove(clip)
        clip = ET.SubElement(dup, "midiclip", {"muted": "0", "off": "0", "pos": str(CUT), "len": str(INS), "autoresize": "1", "type": "1",
                                               "steps": "16", "name": f"bitbeat - {short}"})
        for rel, n in notes:
            n.set("pos", str(rel))
            clip.append(n)
        tc.insert(insert_at + k, dup)

    # 5) automation of the crush (sample rate and bit levels), visible and editable in LMMS
    for label, idx, oid in (("Bit beat: sample rate", 1, ID_RATE), ("Bit beat: bit levels", 2, ID_LEVELS)):
        at = ET.Element("track", {"muted": "0", "solo": "0", "type": "5", "mutedBeforeSolo": "0", "name": label})
        ET.SubElement(at, "automationtrack")
        ac = ET.SubElement(at, "automationclip", {"pos": str(CUT), "len": str(INS), "name": label, "prog": "1", "tens": "1", "mute": "0"})
        for pt in RATE:     # this LMMS stores an in- and an out-value per point; without outValue a segment starts from 0
            ET.SubElement(ac, "time", {"pos": str(pt[0]), "value": str(pt[idx]), "outValue": str(pt[idx])})
        ET.SubElement(ac, "object", {"id": str(oid)})
        tc.append(at)

    # 6) the second lead: loop B's own melody in the second hook
    n2 = second_lead(lead)
    lt = ET.fromstring(LEAD2_XML(n2))
    tc.insert(list(tc).index(lead) + 1, lt)

    body = ET.tostring(root, encoding="unicode")
    DST.write_text('<?xml version="1.0"?>\n<!DOCTYPE lmms-project>\n' + body + "\n")
    after = hashlib.sha256(SRC.read_bytes()).hexdigest()
    print(f"wrote {DST.name}: lead from bar 9 ({len(early)} notes), bit beat bars 57-{56 + INS // BAR} on {len(section)} tracks "
          f"({sum(len(v) for v in section.values())} notes), +{INS // BAR} bars; {SRC.name} {'unchanged' if before == after else 'CHANGED!'}")


if __name__ == "__main__":
    main()
