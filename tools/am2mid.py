#!/usr/bin/env python3
"""Abundant Music output (.am.json from gen.js) -> a clean multitrack .mid for MIDI Studio / any DAW.

    python tools/am2mid.py songs/deep-house-42.am.json [more ...]      -> songs/deep-house-42.mid (+ .txt summary)

Each channel becomes a track named for its role, so MIDI Studio's auto-assign picks sensible sounds:
  melody 1-3 -> lead, lead2, lead3   inner 1 (fast figures) -> keys, keys2, keys3
  inner 2 (slow chords) -> pad, pad2, pad3   bass 1-3 -> bass, bass2, bass3   channel 10 -> drums
(The composer swaps between the three voices of a role across sections, like an arranger changing patches.)
Tempo changes go on the first track; programs and controllers stay with their channel.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import mido

ROLE = {0: "lead", 1: "lead2", 2: "lead3", 3: "keys", 4: "keys2", 5: "keys3", 6: "pad", 7: "pad2", 8: "pad3",
        9: "drums", 11: "bass", 12: "bass2", 13: "bass3"}
NOTE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def convert(src: Path) -> Path:
    doc = json.loads(src.read_text())
    md = doc["midiData"]
    ppq = md["midiDivisions"]
    events = md["midiTracks"][0]["trackEvents"]
    abs_t = 0
    per_ch: dict[int, list] = {}
    tempo: list = []
    for e in events:
        abs_t += e["eventTime"]                          # delta ticks
        m = e["eventMessage"]
        c = m["messageClass"]
        if c == "SetTempoMessage":
            tempo.append((abs_t, mido.MetaMessage("set_tempo", tempo=int(m["microsPerQuarter"]))))
        elif c == "ProgramChangeMessage":
            per_ch.setdefault(m["channel"], []).append((abs_t, 0, mido.Message("program_change", channel=m["channel"], program=int(m["program"]))))
        elif c == "ChannelMessage" and m.get("status") == "CONTROL_CHANGE":
            per_ch.setdefault(m["channel"], []).append((abs_t, 1, mido.Message("control_change", channel=m["channel"], control=int(m["data1"]),
                                                                              value=max(0, min(127, int(round(m["data2"])))))))
        elif c == "VoiceMessage" and m.get("status") in ("NOTE_ON", "NOTE_OFF"):
            on = m["status"] == "NOTE_ON" and m["data2"] > 0
            msg = mido.Message("note_on" if on else "note_off", channel=m["channel"], note=int(m["data1"]), velocity=int(m["data2"]) if on else 0)
            per_ch.setdefault(m["channel"], []).append((abs_t, 3 if on else 2, msg))
    mf = mido.MidiFile(type=1, ticks_per_beat=ppq)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("track_name", name=doc["name"], time=0))
    meta.append(mido.MetaMessage("time_signature", numerator=int((doc["structure"].get("numerators") or [4])[0]), denominator=4, time=0))
    now = 0
    for t, msg in sorted(tempo, key=lambda x: x[0]):
        meta.append(msg.copy(time=t - now))
        now = t
    mf.tracks.append(meta)
    info = []
    for ch in sorted(per_ch):
        evs = sorted(per_ch[ch], key=lambda x: (x[0], x[1]))
        notes = [m for _, _, m in evs if m.type == "note_on"]
        if not notes:
            continue
        tr = mido.MidiTrack()
        name = ROLE.get(ch, f"ch{ch + 1}")
        tr.append(mido.MetaMessage("track_name", name=name, time=0))
        now = 0
        for t, _, msg in evs:
            tr.append(msg.copy(time=t - now))
            now = t
        mf.tracks.append(tr)
        lo, hi = min(n.note for n in notes), max(n.note for n in notes)
        prog = next((m.program for _, _, m in evs if m.type == "program_change"), None)
        info.append(f"  {name:6s} ch {ch + 1:>2}  {len(notes):5d} notes  {NOTE[lo % 12]}{lo // 12 - 1}-{NOTE[hi % 12]}{hi // 12 - 1}  GM program {prog}")
    out = src.with_name(src.name.replace(".am.json", ".mid"))
    mf.save(str(out))
    st = doc["structure"]
    tempos = [round(60_000_000 / m.tempo, 1) for _, m in tempo]
    secs = mf.length
    key = ""
    if st.get("scaleBaseNotes"):
        types = {0: "major", 1: "natural minor", 2: "harmonic minor", 3: "melodic minor"}
        key = ", ".join(sorted({f"{NOTE[b % 12]} {types.get(t, f'scale {t}')}" for b, t in zip(st["scaleBaseNotes"], st.get("scaleTypes") or [])}))
    txt = [f"{doc['name']}  (seed {doc['seed']}, style {doc.get('style', 'bountiful')})",
           f"length {int(secs // 60)}:{secs % 60:04.1f}, {doc.get('sections', len(doc.get('sectionTimes', [])))} sections, time signature {sorted(set(st.get('numerators') or [4]))}/4",
           f"tempo {min(tempos):.0f}-{max(tempos):.0f} bpm ({len(tempos)} tempo events)" if tempos else "tempo: default",
           f"keys/scales: {key}", "tracks:"] + info
    out.with_suffix(".txt").write_text("\n".join(txt) + "\n")
    print("\n".join(txt))
    return out


if __name__ == "__main__":
    for a in sys.argv[1:]:
        convert(Path(a))
