"""A track folder as the DAW sees it: the MIDI parts (notes in beats), sections, stems and exports."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import mido

import build as B
from paths import DATA

COLORS = {"lead": "#ffb347", "lead_hi": "#ffd27a", "sidekick": "#7ad7ff", "arp": "#b48cff", "comp": "#7affb0", "keys": "#7affb0",
          "stab": "#ff7ab8", "vox": "#ff9ec9", "pad": "#6fa8ff", "choir": "#9fb8ff", "bass": "#ff6b5a", "bass2": "#e0584a",
          "counter": "#e6f07a", "drums": "#c8c8c8"}
PALETTE = ["#ffb347", "#7ad7ff", "#b48cff", "#7affb0", "#ff7ab8", "#6fa8ff", "#ff6b5a", "#e6f07a"]


def color(name: str) -> str:
    return COLORS.get(name) or PALETTE[sum(map(ord, name)) % len(PALETTE)]


@dataclass
class Note:
    t: float          # beats
    d: float
    p: int
    v: float          # 0..1


@dataclass
class Track:
    folder: Path
    title: str = ""
    bpm: float = 120.0
    parts: dict[str, list[Note]] = field(default_factory=dict)
    sections: list[dict] = field(default_factory=list)     # {"name", "start" (bar, 1-based), "bars"}
    source: dict = field(default_factory=dict)
    dirty: bool = False

    @property
    def name(self) -> str:
        return self.folder.name

    @property
    def mid(self) -> Path | None:
        return next(iter(sorted(self.folder.glob("*.mid"))), None)

    @property
    def beats(self) -> float:
        end = max((n.t + n.d for ns in self.parts.values() for n in ns), default=16.0)
        return max(16.0, end)

    @property
    def bars(self) -> int:
        return int(-(-self.beats // 4))

    def stems(self) -> dict[str, Path]:
        d = self.folder / "stems"
        return {p.stem: p for p in sorted(d.glob("*.wav"))} if d.exists() else {}

    def master(self) -> Path | None:
        ex = self.folder / "exports"
        for cand in (ex / f"{self.name}.wav", *sorted(ex.glob("*.wav"))):
            if cand.exists() and "premaster" not in cand.name and "preview" not in cand.name:
                return cand
        return None

    def preview(self) -> Path | None:
        p = self.folder / "exports" / "preview.wav"
        return p if p.exists() else None

    def render_info(self) -> dict:
        try:
            return json.loads((self.folder / "exports" / "render_info.json").read_text())
        except (FileNotFoundError, ValueError):
            return {}

    def makeup(self) -> float:
        """Stems → roughly the master's loudness. The stems sum to the premaster; the master chain makes it louder,
        so the gain is the master/premaster level ratio, measured over a few slices."""
        ex = self.folder / "exports"
        pre, mas = ex / f"{self.name}_premaster.wav", self.master()
        if not (pre.exists() and mas):
            g = (self.render_info().get("master") or {}).get("gain_db", 0.0)
            return float(10 ** (g / 20) * 0.65)
        import numpy as np
        import soundfile as sf
        n = sf.info(str(pre)).frames
        num = den = 0.0
        for k in (0.25, 0.5, 0.75):
            a = int(n * k)
            num += float((sf.read(str(mas), start=a, frames=44100 * 4, dtype="float32")[0] ** 2).mean())
            den += float((sf.read(str(pre), start=a, frames=44100 * 4, dtype="float32")[0] ** 2).mean())
        return float(np.sqrt(num / den)) if den > 0 else 1.0

    def notes_text(self) -> str:
        try:
            return (self.folder / "notes.txt").read_text()
        except FileNotFoundError:
            return ""

    def save_midi(self):
        """Write the parts back to the .mid (the same track names and channels build.py uses)."""
        conv = lambda ns: [(n.t, n.d, n.p, n.v, 0.0) for n in ns]  # noqa: E731
        parts = {k: [] for k in B.PART_ORDER}
        parts.update({k: conv(v) for k, v in self.parts.items() if k != "drums"})
        mid = self.mid or self.folder / f"{self.name}.mid"
        B.write_midi(mid, self.title, self.bpm, parts, conv(self.parts.get("drums", [])))
        self.dirty = False
        return mid


def load(folder: Path) -> Track:
    folder = Path(folder)
    tr = Track(folder, title=folder.name.replace("-", " ").title())
    try:
        tr.source = json.loads((folder / "source.json").read_text())
    except (FileNotFoundError, ValueError):
        tr.source = {}
    tr.title = tr.source.get("title") or tr.title
    mid = tr.mid
    if mid:
        mf = mido.MidiFile(str(mid))
        ppq = mf.ticks_per_beat
        for t in mf.tracks:
            name, now, on, notes = None, 0, {}, []
            for m in t:
                now += m.time
                if m.type == "track_name" and name is None:
                    name = m.name
                elif m.type == "set_tempo":
                    tr.bpm = round(mido.tempo2bpm(m.tempo), 3)
                elif m.type == "note_on" and m.velocity > 0:
                    on.setdefault((m.channel, m.note), []).append((now, m.velocity))
                elif m.type in ("note_off", "note_on"):
                    st = on.get((m.channel, m.note))
                    if st:
                        t0, v = st.pop(0)
                        notes.append(Note(t0 / ppq, max(1, now - t0) / ppq, m.note, v / 127))
            if notes and name:
                if name == tr.title and not tr.parts and name not in B.PART_ORDER:
                    name = "melody"
                tr.parts[name] = sorted(notes, key=lambda n: (n.t, n.p))
    tr.sections = sections_for(tr)
    return tr


def sections_for(tr: Track) -> list[dict]:
    s = tr.source
    if s.get("sections"):
        return s["sections"]
    if s.get("kind") == "electronium-song":
        try:
            import electronium_song as ES
            pl = ES.plan(s["bounty"], s.get("key"), s.get("bpm"), s.get("length", "normal"), s.get("reharm", 0.25))
            return [{"name": x["name"], "start": x["start"], "bars": x["bars"], "kind": x["kind"]} for x in pl["sections"]]
        except Exception:
            return []
    return []


def library() -> dict[str, list[Path]]:
    """Track folders, newest first, grouped: tracks, album folders, sessions."""
    out: dict[str, list[Path]] = {}
    tracks = DATA / "tracks"
    if tracks.exists():
        out["Tracks"] = sorted((p for p in tracks.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")) and any(p.glob("*.mid"))),
                               key=lambda p: -p.stat().st_mtime)
    for kind in ("albums", "sessions"):
        base = DATA / kind
        if base.exists():
            for d in sorted(base.iterdir(), key=lambda p: -p.stat().st_mtime):
                if d.is_dir() and not d.name.startswith(("_", ".")):
                    found = sorted(p.parent for p in d.glob("*/*.mid"))
                    if found:
                        out[f"{kind[:-1].title()}: {d.name}"] = found
    return out
