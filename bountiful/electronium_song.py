#!/usr/bin/env python3
"""A whole song from a Bounty: the Electronium writes everything, no composer needed.

From the Bounty (and an optional key, tempo and length) it decides the key and tempo, writes a chord progression
for each section (functional harmony: tonic, subdominant, dominant; phrases that end open, then closed), lays out
the song (intro, verses, choruses, a bridge, an outro), sets up six channels (lead, sidekick, bass, arp, keys,
counter) with its own percussion, lets the operator (operator_.py: the rules, and your brief read by intent.py) play the knobs,
and performs and writes the track folder: .mid, instruments.toml, electronium.toml, notes.txt, source.json.

  reharm 0-1    how far the harmony strays: sevenths, secondary dominants before chord changes, borrowed and
                relative chords (0 = plain triads)

    $PY bountiful/electronium_song.py --bounty 1969 [--key "D minor"] [--bpm 112] [--length short|normal|long]
                                      [--reharm 0.3] [--brief "..."] [--render]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as B  # noqa: E402
import electronium as EL  # noqa: E402
import operator_ as OP  # noqa: E402
import producer as PR  # noqa: E402
from paths import DATA  # noqa: E402

MAJOR, MINOR = (0, 2, 4, 5, 7, 9, 11), (0, 2, 3, 5, 7, 8, 10)
NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
FUNC = {0: "T", 1: "S", 2: "T", 3: "S", 4: "D", 5: "S", 6: "D"}       # scale degree -> function (vi/VI and iii/III as tonic or subdominant)
NEXT = {"T": {"T": 0.2, "S": 0.55, "D": 0.25}, "S": {"T": 0.15, "S": 0.25, "D": 0.6}, "D": {"T": 0.75, "S": 0.15, "D": 0.1}}
WORDS_A = ["Clockwork", "Copper", "Bounty", "Circuit", "Lab", "Signal", "Relay", "Oscillator", "Vacuum", "Punchcard", "Bakelite",
           "Manhattan", "Tape", "Filter", "Lattice", "Silver", "Neon", "Ferrite", "Quartz", "Telefunken"]
WORDS_B = ["Waltz", "Machine", "Lullaby", "Parade", "Garden", "Cascade", "Workshop", "Errand", "Daydream", "Commute",
           "Promenade", "Carousel", "Shuffle", "Ballet", "Picnic", "Factory", "Weather", "Holiday", "Circus", "Hymn"]
LAYOUTS = {   # (name, kind, loop, bars, parts, drum layers)
    "short": [("Intro", "intro", "V", 4, ["arp", "bass"], ["hat", "rim"]),
              ("Verse", "verse", "V", 8, ["lead", "sidekick", "arp", "bass"], ["kick", "hat", "rim"]),
              ("Chorus", "chorus", "A", 8, ["lead", "lead_hi", "sidekick", "arp", "bass", "keys"], ["kick", "snare", "hat", "open", "clap"]),
              ("Bridge", "bridge", "B", 8, ["lead", "counter", "bass", "keys"], ["kick", "rim", "syntom_hi", "syntom_lo"]),
              ("Last chorus", "chorus", "A", 8, ["lead", "lead_hi", "sidekick", "arp", "bass", "keys", "counter"], ["kick", "snare", "hat", "open", "clap"]),
              ("Outro", "outro", "V", 4, ["lead", "arp", "bass"], ["hat", "rim"])],
    "normal": [("Intro", "intro", "V", 8, ["arp", "bass"], ["hat", "rim"]),
               ("Verse 1", "verse", "V", 16, ["lead", "sidekick", "arp", "bass"], ["kick", "hat", "rim"]),
               ("Chorus 1", "chorus", "A", 16, ["lead", "lead_hi", "sidekick", "arp", "bass", "keys"], ["kick", "snare", "hat", "open", "clap"]),
               ("Verse 2", "verse", "V", 8, ["lead", "sidekick", "arp", "bass", "counter"], ["kick", "snare", "hat", "rim"]),
               ("Bridge", "bridge", "B", 8, ["lead", "counter", "bass", "keys"], ["kick", "rim", "syntom_hi", "syntom_lo"]),
               ("Last chorus", "chorus", "A", 16, ["lead", "lead_hi", "sidekick", "arp", "bass", "keys", "counter"], ["kick", "snare", "hat", "open", "clap"]),
               ("Outro", "outro", "A", 8, ["lead", "arp", "bass", "keys"], ["hat", "rim"])],
}
LAYOUTS["long"] = LAYOUTS["normal"][:4] + [("Chorus 2", "chorus", "A", 8, ["lead", "lead_hi", "sidekick", "arp", "bass", "keys"],
                                            ["kick", "snare", "hat", "open", "clap"])] + LAYOUTS["normal"][4:]


def parse_key(s: str) -> tuple[int, str]:
    parts = s.replace("-", " ").split()
    tonic = EL.note_pc(parts[0])
    mode = "minor" if len(parts) > 1 and parts[1].lower().startswith("m") and not parts[1].lower().startswith("maj") else \
        "minor" if parts[0].endswith("m") and len(parts) == 1 else "major"
    return tonic, mode


def chord(tonic: int, mode: str, deg: int, seventh: bool = False) -> tuple[int, list[int]]:
    sc = MINOR if mode == "minor" else MAJOR
    pc = lambda k: (tonic + sc[(deg + k) % 7]) % 12
    root, tones = pc(0), [pc(0), pc(2), pc(4)] + ([pc(6)] if seventh else [])
    if mode == "minor" and deg == 4:                           # the dominant borrows the leading tone
        tones = [(root + 4) % 12 if t == pc(2) else t for t in tones]
        if seventh:
            tones[-1] = (root + 10) % 12
    return root, tones


def progression(rng, tonic: int, mode: str, kind: str, bars: int, reharm: float) -> list[tuple]:
    """Chords as (beat in loop, beats, pcs, root): two 4-bar phrases, the first ending open (on the dominant),
    the second closed (dominant to tonic); bridges start away from home and end on the dominant."""
    by_func = {f: [d for d, g in FUNC.items() if g == f] for f in "TSD"}
    degs = []
    for ph in range(max(1, bars // 4)):
        last = ph == bars // 4 - 1
        start = (0 if kind != "bridge" else int(rng.choice([3, 5, 1]))) if ph == 0 else int(rng.choice([0, 5, 3] if kind != "bridge" else [3, 5]))
        row = [start]
        for _ in range(3):
            f = FUNC[row[-1]]
            nf = rng.choice(list(NEXT[f]), p=list(NEXT[f].values()))
            cand = [d for d in by_func[nf] if d != row[-1] and not (mode == "minor" and d == 6 and nf == "D")] or by_func[nf]
            row.append(int(rng.choice(cand)))
        if kind == "bridge" or not last:
            row[-1] = 4                                         # open: on the dominant
        else:
            row[-1] = 0                                         # closed: home, the dominant (usually) before it
            if FUNC[row[-2]] != "D" and rng.random() < 0.7:
                row[-2] = 4
        degs += row
    degs = (degs + [0] * bars)[:bars]
    if len(degs) >= 4:                                          # no chord held across more than two bars
        for i in range(2, len(degs)):
            if degs[i] == degs[i - 1] == degs[i - 2]:
                degs[i] = 5 if degs[i] != 5 else 3
    out = []
    for i, d in enumerate(degs):
        sev = rng.random() < reharm * 0.8
        if reharm and rng.random() < reharm * 0.3 and d in (0, 3):     # relative substitution: I -> vi, IV -> ii
            d = {0: 5, 3: 1}[d] if not (i == len(degs) - 1) else d
        root, pcs = chord(tonic, mode, d, sev)
        nxt = degs[i + 1] if i + 1 < len(degs) else degs[0]
        dim = (1 if mode == "minor" else 6)                     # no dominant aims at the diminished chord
        if reharm and nxt not in (d, 0, dim) and rng.random() < reharm * 0.6:    # V7 of the next chord on beats 3-4
            nroot, _ = chord(tonic, mode, nxt)
            sd = (nroot + 7) % 12
            out += [(i * 4, 2.0, pcs, root), (i * 4 + 2, 2.0, [sd, (sd + 4) % 12, (sd + 7) % 12, (sd + 10) % 12], sd)]
        else:
            out.append((i * 4, 4.0, pcs, root))
    return out


def title_for(bounty) -> str:
    r = np.random.default_rng([EL.bounty_int(bounty), 404])
    return f"{WORDS_A[int(r.integers(len(WORDS_A)))]} {WORDS_B[int(r.integers(len(WORDS_B)))]}"


def plan(bounty, key: str | None = None, bpm: float | None = None, length: str = "normal", reharm: float = 0.25) -> dict:
    """Everything decided before a note is played: key, tempo, sections, chords per loop, the patch."""
    bi = EL.bounty_int(bounty)
    r = np.random.default_rng([bi, 2026])
    if key:
        tonic, mode = parse_key(key)
    else:
        tonic, mode = int(r.integers(12)), ("minor" if r.random() < 0.6 else "major")
    bpm = float(bpm or int(r.choice([92, 98, 104, 108, 112, 116, 120, 126])))
    loops = {k: progression(np.random.default_rng([bi, EL._crc("chords:" + k)]), tonic, mode, kind, 8, reharm)
             for k, kind in (("V", "verse"), ("A", "chorus"), ("B", "bridge"))}
    sections, bar = [], 1
    for (name, kind, loop, n, parts, drums) in LAYOUTS[length]:
        sections.append({"name": name, "kind": kind, "loop": loop, "start": bar, "bars": n, "parts": parts, "drums": drums})
        bar += n
    side = str(r.choice(["third_below", "sixth_below", "fifth_below"]))
    channels = [
        {"name": "lead", "role": "melody"},
        {"name": "sidekick", "role": "harmony", "follow": "lead", "interval": side, "register": [50, 72]},
        {"name": "bass", "role": "bass", "gate": str(r.choice(["p5 | (r7 & c2 & ~c4)", "c8 | c8+3 | c8+6", "p2 | c16+14", "c4 | (r5 & c2)"]))},
        {"name": "arp", "role": "ostinato", "length": int(r.integers(3, 8)), "gate": str(r.choice(["c2", "p6", "c2 & ~r5", "p3"]))},
        {"name": "keys", "role": "chords", "voices": int(r.choice([3, 3, 4]))},
        {"name": "counter", "role": "counter"},
    ]
    phrase = [["theme", "theme", "answer", "free", "theme", "develop", "free", "cadence"],
              ["theme", "answer", "theme", "answer", "develop", "augment", "free", "cadence"],
              ["theme", "theme", "mirror", "answer", "theme", "develop", "answer", "cadence"]][int(r.integers(3))]
    p = EL.patch({"bounty": bounty, "density": round(float(r.uniform(0.62, 0.8)), 2), "mutation": round(float(r.uniform(0.1, 0.25)), 2),
                  "register": [62, 84], "channels": channels, "phrase": phrase, "think": 200, "keep": 3})
    p["_bpm"] = bpm
    return {"bounty": bounty, "tonic": tonic, "mode": mode, "key": f"{NAMES[tonic]} {mode}", "bpm": bpm, "length": length,
            "reharm": reharm, "loops": loops, "sections": sections, "patch": p, "title": title_for(bounty)}


def chord_text(ch, tonic: int = 0, mode: str = "minor") -> str:
    import skeleton as SK
    SK.spell_for(tonic, mode)
    NAMES = SK._spell["names"]
    out = []
    for (t, d, pcs, root) in ch:
        third = (pcs[1] - root) % 12 if len(pcs) > 1 else 4
        q = ("m" if third == 3 else "") + ("7" if len(pcs) > 3 and (pcs[3] - root) % 12 == 10 else "maj7" if len(pcs) > 3 else "")
        if third == 3 and len(pcs) > 2 and (pcs[2] - root) % 12 == 6:
            q = "dim"
        out.append(NAMES[root] + q + ("" if d == 4 else f"({d / 4:g})"))
    return " ".join(out)


def timeline_for(pl: dict) -> list[dict]:
    key_pcs = sorted((pl["tonic"] + i) % 12 for i in (MINOR if pl["mode"] == "minor" else MAJOR))
    tl = []
    for s in pl["sections"]:
        L = pl["loops"][s["loop"]]
        for i in range(s["bars"]):
            b = s["start"] - 1 + i
            lb = i % 8
            tl.append({"bar": b, "tr": 0, "act": 1.0, "kime": False, "loop": s["loop"], "parts": list(s["parts"]),
                       "restart": i == 0, "lead": "lead" in s["parts"], "sidekick": "sidekick" in s["parts"],
                       "tonic": pl["tonic"], "key_pcs": key_pcs, "section": s["name"],
                       "chords": [(c[0] - lb * 4, c[1], c[2], c[3]) for c in L if lb * 4 <= c[0] < lb * 4 + 4]})
    return tl


def perform(pl: dict, operator: dict | None = None) -> dict:
    """The performance: {"parts", "drums", "machine", "timeline", "operator"}."""
    p = EL.patch(pl["patch"])
    op = operator or OP.operate(pl["sections"], p, bpm=pl["bpm"])
    p["moves"] = [{k: v for k, v in m.items() if k != "why"} for m in op["moves"]]
    p["freeze"] = op["freezes"]
    bars = sum(s["bars"] for s in pl["sections"])
    m = EL.Machine(p, bars, 0.52, pl["bpm"], 3.0)
    tl = timeline_for(pl)
    res = m.perform(tl)
    parts = {k: [] for k in B.PART_ORDER}
    parts.update(res["parts"])
    hi_bars = {c["bar"] for c in tl if "lead_hi" in c["parts"]}
    parts["lead_hi"] = [(t, d, q + 12, v * 0.55, o) for (t, d, q, v, o) in res["parts"].get("lead", []) if int(t // 4) in hi_bars]
    drums = []
    import intent as IN
    for s in IN.apply_drums(pl["sections"], op.get("drums", [])):         # the brief's drum layers, if any
        for i in range(s["bars"]):
            b = s["start"] - 1 + i
            layers = set(s["drums"])
            if i == s["bars"] - 1 and s["kind"] in ("verse", "prechorus", "bridge"):
                layers |= {"syntom_hi", "syntom_lo"}           # a fill into what comes next
            for (st, snd, v) in m.drum_steps(layers, b):
                drums.append((b * 4 + st / 4, 0.2, PR.GM[snd], v, m._off(b * 16 + st)))
            if i == 0 and s["kind"] == "chorus":
                drums.append((b * 4, 0.5, PR.GM["crash"], 0.75, 0.0))
    last = sum(s["bars"] for s in pl["sections"])
    if pl["sections"][-1]["kind"] == "outro":
        drums.append((last * 4 - 4, 0.5, PR.GM["crash"], 0.6, 0.0))
    return {"parts": parts, "drums": drums, "machine": m, "timeline": tl, "operator": op, "patch": p}


def genre_for(pl: dict, p: dict) -> dict:
    g = B.genres().get("electronium-69", {"name": "Electronium", "master": {}})
    g = dict(g, bpm=pl["bpm"], sounds={}, drums="electronium", electronium=p, melody={"writer": "electronium"})
    import electronium_drums
    g["_kit"] = electronium_drums.kit()
    g["name"] = "Electronium (whole song)"
    return g


def song(bounty, key=None, bpm=None, length="normal", reharm=0.25, brief="", title=None, out: Path | None = None,
         operator: dict | None = None, log=print) -> Path:
    pl = plan(bounty, key, bpm, length, reharm)
    title = title or pl["title"]
    name = B.slug(title)
    out = out or DATA / "tracks" / name
    out.mkdir(parents=True, exist_ok=True)
    op = operator or OP.operate(pl["sections"], EL.patch(pl["patch"]), brief, log=log, bpm=pl["bpm"])
    perf = perform(pl, op)
    p = perf["patch"]
    g = genre_for(pl, p)
    mid = out / f"{name}.mid"
    B.write_midi(mid, title, pl["bpm"], perf["parts"], perf["drums"])
    sys.path.insert(0, str(B.ENGINE / "studio"))
    from midi_studio import to_toml
    (out / "instruments.toml").write_text(to_toml(B.instrument_map(g, title, name, EL.bounty_int(bounty) % 100000)))
    (out / "electronium.toml").write_text(EL.dump({k: v for k, v in p.items() if not k.startswith("_")}))
    bars = sum(s["bars"] for s in pl["sections"])
    secs = bars * 4 * 60 / pl["bpm"]
    lines = [f"{title} — the Electronium, a whole song from Bounty {bounty}: {pl['key']}, {pl['bpm']:g} bpm, {bars} bars "
             f"({int(secs // 60)}:{secs % 60:04.1f}), reharm {reharm}", "", "Chords:"]
    lines += [f"  {k}: {chord_text(v, pl['tonic'], pl['mode'])}" for k, v in pl["loops"].items()]
    lines += ["", "Sections:"] + [f"  {s['start']:3d}-{s['start'] + s['bars'] - 1:3d}  {s['name']:12s} loop {s['loop']}  "
                                  f"parts: {', '.join(s['parts']):48s} drums: {', '.join(s['drums'])}" for s in pl["sections"]]
    lines += ["", OP.text(op), ""] + perf["machine"].summary()
    lines += ["", "tracks: " + ", ".join(f"{k} {len(v)} notes" for k, v in perf["parts"].items() if v) + f", drums {len(perf['drums'])} hits"]
    (out / "notes.txt").write_text("\n".join(lines) + "\n")
    (out / "source.json").write_text(json.dumps({"kind": "electronium-song", "bounty": bounty, "key": pl["key"], "bpm": pl["bpm"],
                                                 "length": length, "reharm": reharm, "title": title, "operator": op["by"],
                                                 "brief": brief or op.get("brief", ""),
                                                 "intents": [it for it in op.get("intents", [])]}, indent=1))
    log("\n".join(lines))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bounty", default="1969")
    ap.add_argument("--key")
    ap.add_argument("--bpm", type=float)
    ap.add_argument("--length", default="normal", choices=list(LAYOUTS))
    ap.add_argument("--reharm", type=float, default=0.25)
    ap.add_argument("--brief", default="", help='plain words for the operator, e.g. "make the bridge more restless"')
    ap.add_argument("--title")
    ap.add_argument("--out", type=Path, help="the track folder (default: tracks/<title>)")
    ap.add_argument("--render", action="store_true")
    a = ap.parse_args()
    out = song(a.bounty, a.key, a.bpm, a.length, a.reharm, a.brief, a.title, a.out)
    if a.render:
        B.render(out)


if __name__ == "__main__":
    main()
