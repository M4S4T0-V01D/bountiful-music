"""Song Spec: the ports (Moss Radio, Orange Mound Fog, Window Frost) compose the same notes as their scripts.

    $PY -I tests/test_songspec.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bountiful"))

import lmms_tracks as LT  # noqa: E402

orig_produce = LT.B.produce
import moss_radio as M  # noqa: E402  (patches LT.B.produce on import)
import orange_mound as O  # noqa: E402  (so does this one)
LT.B.produce = orig_produce
import songspec as SS  # noqa: E402


def plain(x):
    """tuples -> lists, Paths -> str, so the script's SPEC and the loader's compare as data"""
    if isinstance(x, dict):
        return {k: plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [plain(v) for v in x]
    if isinstance(x, Path):
        return str(x)
    return x


def diff(a, b, path="spec"):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                yield f"{path}.{k}: only in {'script' if k in a else 'port'}"
            else:
                yield from diff(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            yield from diff(x, y, f"{path}[{i}]")
    elif a != b or type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        yield f"{path}: script {a!r} != port {b!r}"


fails = 0


def check(name, problems):
    global fails
    problems = list(problems)
    print(f"{'ok  ' if not problems else 'FAIL'} {name}")
    for p in problems[:12]:
        print(f"     {p}")
    fails += bool(problems)


def same_record(label, script, toml):
    """the port composes the script's notes and chord chart and builds its LT spec"""
    S = SS.load(ROOT / "records" / toml)
    want, want_chart = script.compose()
    got, got_chart = SS.compose(S)
    check(f"{label}: track order", [] if list(want) == list(got) else [f"script {list(want)} != port {list(got)}"])
    check(f"{label}: notes", (
        f"{t}: {len(want[t])} notes in the script, {len(got.get(t, []))} in the port; first difference at "
        f"{next((i for i, (a, b) in enumerate(zip(want[t], got.get(t, []))) if a != b), min(len(want[t]), len(got.get(t, []))))}"
        for t in want if want[t] != got.get(t)))
    check(f"{label}: chord chart", [] if want_chart == got_chart else ["charts differ"])
    a = plain(script.SPEC)
    b = plain(SS.to_lt(S, log=lambda m: None))
    a.pop("rebuild"), b.pop("rebuild")
    check(f"{label}: LT spec", diff(a, b))
    return S


S = same_record("Moss Radio", M, "moss-radio.toml")
same_record("Orange Mound Fog", O, "orange-mound-fog.toml")

# the loader puts its hook in only while it builds
before = LT.B.produce
with SS.composed(S):
    inside = LT.B.produce
check("produce hook restored", [] if LT.B.produce is before and inside is not before else ["hook leaked"])

# bar references
check("bar refs", [f"{x} -> {SS.bar(S, x)} (want {w})" for x, w in
                   [("@Intro", 1), ("@Break", 29), ("@Break+3.5", 32.5), ("@Outro+4", 53), ("@Last chord-1", 56), (12, 12)]
                   if SS.bar(S, x) != w])

# lint catches the gotchas before a render
bad = []
for label, edit in [("unknown chord", lambda s: s["loops"]["A"].append(["Xm7"])),
                    ("unknown drum layer", lambda s: s["sections"][0]["drums"].append("cowbell")),
                    ("grid sound not in kit", lambda s: s["drums"]["grid"]["kick"]["a"].append([4, 0.5, "tom"])),
                    ("silent target in test bars", lambda s: s["sections"][5]["play"].pop("pad")),
                    ("library not allowed", lambda s: s["sounds"].update(allow=["gs", "own"]))]:
    s2 = SS.load(ROOT / "records" / "moss-radio.toml")
    edit(s2)
    try:
        SS.to_lt(s2, log=lambda m: None)
        bad.append(f"{label}: not caught")
    except SS.SpecError:
        pass
check("lint", bad)

notes = []
s3 = SS.load(ROOT / "records" / "moss-radio.toml")
s3["voices"]["sub"]["engine"]["layers"][0]["preset"]["glide"] = 0.0
SS.to_lt(s3, log=notes.append)
check("glide 0 is raised to 0.01", [] if any("glide" in n for n in notes) else ["no note logged"])

# a grid beat doesn't depend on the order of the section's layers (they come as a set, whose order follows the hash seed)
import numpy as np  # noqa: E402
import producer as PR  # noqa: E402
cfg = {"grid": O.GRID, "drum_humanize_ms": 4, "_bpm": 70}
layers = ["vinyl", "kick", "snare", "clap", "hat", "open", "perc"]
takes = [PR.drum_bar("grid", order, None, 5, np.random.default_rng(7), cfg) for order in (layers, layers[::-1])]
check("grid drums independent of layer order", [] if takes[0] == takes[1] else ["the take changes with the order"])

# Window Frost: the beats engine writes the script's notes, controller events and sub, and leaves the random stream
# where the script's writers left it (the mixer goes on drawing from it)
import window_frost as WF  # noqa: E402
import songspec_beats as SB  # noqa: E402
WF.write_all()
G = SB.compose(SS.load(ROOT / "records" / "window-frost.toml"))
check("Window Frost: notes", (f"{t}: {len(WF.NOTES[t])} in the script, {len(G.notes[t])} in the port"
                              for t in WF.NOTES if WF.NOTES[t] != G.notes[t]))
check("Window Frost: controller events", (f"{t}: {len(WF.CTRL[t])} in the script, {len(G.ctrl[t])} in the port"
                                          for t in WF.CTRL if WF.CTRL[t] != G.ctrl[t]))
check("Window Frost: sub and solo", [x for x, ok in [("sub", WF.SUB_NOTES == G.sub),
                                                     ("solo", WF.SOLO_LINE == G.parts["solo"])] if not ok])
tup = {n: (c["bass"], c["v"]) for n, c in G.chords.items()}
check("Window Frost: form", [] if WF.FORM == [(s, m, tup[c], i) for s, m, c, i in G.form] else ["forms differ"])
check("Window Frost: random stream", [] if WF.rng.random() == G.rng.random() else ["left in another place"])
check("Window Frost: parts", [p for p, a, b in [("tannen", WF.TANNEN, G.parts["tannen"]),
                                                ("tannen_outro", WF.OUTRO_TUNE, G.parts["tannen_outro"]),
                                                ("midwinter1", WF.MW1, G.parts["midwinter1"]),
                                                ("midwinter2", WF.MW2, G.parts["midwinter2"]),
                                                ("bridge", WF.BRIDGE, G.parts["bridge"])] if a != b])
s4 = SS.load(ROOT / "records" / "window-frost.toml")
s4["render"]["backend"] = "os"
try:
    SB.backend(s4)
    check("render backend allow-list", ["an unknown backend was imported"])
except SS.SpecError:
    check("render backend allow-list", [])

print("all pass" if not fails else f"{fails} failed")
sys.exit(1 if fails else 0)
