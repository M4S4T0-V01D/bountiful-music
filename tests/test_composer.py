"""The composer core in the embedded V8 (bountiful/composer.py): the same seed gives the same song, a re-roll keeps
every seed outside the re-rolled group, unknown settings are refused, and, where Node is installed, the songs are
byte for byte what bountiful/gen.js writes.

    $PY -I tests/test_composer.py
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bountiful"))

import composer  # noqa: E402

fails = 0


def check(name, problems):
    global fails
    problems = list(problems)
    print(f"{'ok  ' if not problems else 'FAIL'} {name}")
    for p in problems[:12]:
        print(f"     {p}")
    fails += bool(problems)


if not composer.available():
    print("FAIL mini-racer isn't installed")
    sys.exit(1)

settings = {"melodyMotifZone1TripletLikelihoods": [0]}
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    a = list(composer.compose_songs(settings, [7, 99], out=d / "a", prefix="t"))
    b = list(composer.compose_songs(settings, [7], out=d / "b", prefix="t"))
    doc = json.loads(a[0][0].read_text())
    check("compose", [p for p in [
        [f.name for f, *_ in a] != ["t-7.am.json", "t-99.am.json"] and f"files {[f.name for f, *_ in a]}",
        a[0][0].read_bytes() != b[0][0].read_bytes() and "seed 7 differs between runs",
        a[0][0].read_bytes() == a[1][0].read_bytes() and "seeds 7 and 99 gave the same song",
        not (a[0][2] > 0 and a[0][3] > 0) and f"beats {a[0][2]} sections {a[0][3]}",
        (doc["seed"], doc["settings"], doc["lengthBeats"]) != (7, settings, a[0][2]) and "document header",
        not doc["midiData"].get("midiTracks") and "no MIDI tracks"] if p])

    r = list(composer.compose_songs(settings, [5], out=d / "r", prefix="t-7-melody", pin=a[0][0], reroll=["melody"]))
    rd = json.loads(r[0][0].read_text())
    kept = {k for k in doc["seeds"] if doc["seeds"][k] == rd["seeds"][k]}
    check("reroll", [p for p in [
        kept & set(composer.GROUPS["melody"]) and f"melody seeds kept: {sorted(kept & set(composer.GROUPS['melody']))}",
        set(doc["seeds"]) - set(composer.GROUPS["melody"]) - kept and "a seed outside the melody group changed",
        (rd["pinnedFrom"], rd["rerolled"]) != (str(a[0][0]), ["melody"]) and f"pin fields {rd['pinnedFrom']} {rd['rerolled']}"] if p])

    try:
        list(composer.compose_songs({"noSuchSetting": 1}, [1], out=d / "x"))
        check("unknown setting", ["accepted"])
    except ValueError:
        check("unknown setting", [])

    node = shutil.which("node")
    if node:
        sp = d / "s.json"
        sp.write_text(json.dumps(settings))
        subprocess.run([node, str(ROOT / "bountiful" / "gen.js"), "--settings", str(sp), "--out", str(d / "n"), "--prefix", "t",
                        "--seed", "7", "--seed", "99"], check=True, capture_output=True)
        check("same as Node", [f"{f.name} differs" for f, *_ in a if (d / "n" / f.name).read_bytes() != f.read_bytes()])
    else:
        print("skip same as Node (no Node)")

print("all pass" if not fails else f"{fails} failing")
sys.exit(bool(fails))
