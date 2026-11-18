"""Song Spec: the Moss Radio port composes the same notes and builds the same LT spec as bountiful/moss_radio.py.

    $PY -I tests/test_songspec.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bountiful"))

import lmms_tracks as LT  # noqa: E402

orig_produce = LT.B.produce
import moss_radio as M  # noqa: E402  (patches LT.B.produce on import)
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


S = SS.load(ROOT / "records" / "moss-radio.toml")
want, want_chart = M.compose()
got, got_chart = SS.compose(S)
check("track order", [] if list(want) == list(got) else [f"script {list(want)} != port {list(got)}"])
check("notes", (f"{t}: {len(want[t])} notes in the script, {len(got.get(t, []))} in the port; first difference at "
                f"{next((i for i, (a, b) in enumerate(zip(want[t], got.get(t, []))) if a != b), min(len(want[t]), len(got.get(t, []))))}"
                for t in want if want[t] != got.get(t)))
check("chord chart", [] if want_chart == got_chart else ["charts differ"])

a = plain(M.SPEC)
b = plain(SS.to_lt(S, log=lambda m: None))
a.pop("rebuild"), b.pop("rebuild")
check("LT spec", diff(a, b))

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

print("all pass" if not fails else f"{fails} failed")
sys.exit(1 if fails else 0)
