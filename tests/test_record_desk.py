"""The Record tab's desk: bar maps, [meta] edits in place, new takes and the build commands, on copies of the records.

    $PY -I tests/test_record_desk.py
"""
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bountiful"))

import record_desk as R  # noqa: E402
import songspec as SS  # noqa: E402

fails = 0


def check(name, problems):
    global fails
    problems = list(problems)
    print(f"{'ok  ' if not problems else 'FAIL'} {name}")
    for p in problems[:12]:
        print(f"     {p}")
    fails += bool(problems)


def raises(fn):
    try:
        fn()
    except SS.SpecError:
        return True
    return False


# bar maps: every bar once, lengths, meters, and the drum pattern build.py picks (sorted keys, by the song's bar)
rows = {r["path"].stem: r for r in R.records()}
check("records load", [f"{k}: {r['error']}" for k, r in rows.items() if r["error"]])
check("lengths", [f"{k}: {rows[k]['bars']} bars {rows[k]['seconds']:.1f} s" for k, bars, secs in
                  [("moss-radio", 57, 171.0), ("orange-mound-fog", 64, 64 * 240 / 70)]
                  if rows[k]["bars"] != bars or abs(rows[k]["seconds"] - secs) > 0.05])
O = SS.load("orange-mound-fog")
keys = sorted(O["drums"]["grid"]["kick"])
om = R.bar_map(O)
check("grid pattern per bar", [f"bar {b['n']}: {p}" for b in om for p in b["plays"]
                               if p.startswith("kick:") and p != f"kick:{keys[(b['n'] - 1) % len(keys)]}"])
check("loop_from = song", [] if [b["chords"] for b in om[:8]] ==
      [O["loops"]["A"][i % len(O["loops"]["A"])] for i in range(8)] else ["the loop doesn't run from bar 1"])
W = R.bar_map(SS.load("window-frost"))
check("beats engine", [x for x, ok in [("bars", len(W) == 76), ("3/4 intro", W[0]["beats"] == 3),
                                       ("piano pattern", "piano:waltz_even" in W[0]["plays"]),
                                       ("drum style", "drums:boom" in W[12]["plays"]),
                                       ("switch", any(p == "keys:flakes" for p in W[12]["plays"]))] if not ok])

tmp = Path(tempfile.mkdtemp())
try:
    R.RECORDS = SS.RECORDS = tmp
    for f in ("moss-radio.toml", "window-frost.toml"):
        shutil.copy(ROOT / "records" / f, tmp / f)
    moss = tmp / "moss-radio.toml"
    before = moss.read_text()

    # edits keep every other line, comments included, and read back as written
    R.set_meta(moss, {"bpm": "84", "swing": 0.6, "title": 'Moss "Radio" II'})
    after = moss.read_text()
    m = tomllib.loads(after)["meta"]
    changed = [(a, b) for a, b in zip(before.splitlines(), after.splitlines()) if a != b]
    check("set_meta", [x for x, ok in [("values", (m["bpm"], m["swing"], m["title"]) == (84, 0.6, 'Moss "Radio" II')),
                                       ("int bpm", type(m["bpm"]) is int),
                                       ("three lines", len(changed) == 3 and len(before.splitlines()) == len(after.splitlines())),
                                       ("rest", tomllib.loads(after)["sections"] == tomllib.loads(before)["sections"])]
                       if not ok])
    # a missing field goes in at the end of [meta], after the multi-line blurb
    moss.write_text("".join(l for l in before.splitlines(keepends=True) if not l.startswith("key =")))
    R.set_meta(moss, {"key": "F dorian"})
    t = moss.read_text()
    check("insert after a multi-line value", [] if tomllib.loads(t)["meta"]["key"] == "F dorian"
          and t.index('key = "F dorian"') < t.index("[perform]") and t.index("upright bass") < t.index('key = "F dorian"')
          else ["inserted in the wrong place"])
    moss.write_text(before)
    bad = [x for x, ch in [("bpm 500", {"bpm": 500}), ("swing .9", {"swing": 0.9}), ("seed -1", {"seed": -1}),
                           ("seed 1.5", {"seed": 1.5}), ("empty title", {"title": " "}), ("two lines", {"title": "a\nb"}),
                           ("bpm text", {"bpm": "fast"}), ("not editable", {"genre": "x"})]
           if not raises(lambda ch=ch: R.set_meta(moss, ch))]
    check("bad values refused, file untouched", bad + ([] if moss.read_text() == before else ["the file changed"]))

    # a new take: the same song from another seed
    take = R.new_take(moss, "Moss Radio Take 2", 99)
    S0, S1 = SS.load(moss), SS.load(take)
    n0, _ = SS.compose(S0)
    n1, _ = SS.compose(S1)
    check("new take", [x for x, ok in [("extends", tomllib.loads(take.read_text())["meta"]["extends"] == "moss-radio"),
                                       ("seeds", (S1["meta"]["seed"], S1["meta"]["humanize_seed"]) == (99, 99)),
                                       ("same song", S1["sections"] == S0["sections"] and S1["loops"] == S0["loops"]),
                                       ("same notes count", {k: len(v) for k, v in n0.items()} == {k: len(v) for k, v in n1.items()}),
                                       ("another take", n0 != n1),
                                       ("summary", R.summary(S1)["extends"] == "moss-radio"),
                                       ("no overwrite", raises(lambda: R.new_take(moss, "Moss Radio Take 2"))),
                                       ("only records/", raises(lambda: R.new_take(ROOT / "README.md", "x")))] if not ok])
    R.set_meta(take, {"bpm": 90})
    check("edit a take", [] if SS.load(take)["meta"]["bpm"] == 90 and SS.load(moss)["meta"]["bpm"] == 80 else ["wrong file"])

    # sounds: only cleared ones, in the file in place; a take gets just the line it changes
    moss.write_text(before)
    iowa = R.catalog("iowa")
    check("catalog", [x for x, ok in [("gs presets", ("gs:0:73", "Flute") in R.catalog("gs")),
                                      ("no iowa raw", iowa and not any(s.startswith("iowa:raw/") for s, _ in iowa)),
                                      ("dm", ("dm:r_n_b/old_kik", "r_n_b/old_kik.wav") in R.catalog("dm"))] if not ok])
    R.set_sound(moss, "drums.kit", "kick", "dm:tr808/kick")
    R.set_sound(moss, "voices", "flute", "gs:0:72", "Clarinet")
    after = moss.read_text()
    S = SS.load(moss)
    changed = [(a, b) for a, b in zip(before.splitlines(), after.splitlines()) if a != b]
    check("set_sound", [x for x, ok in [("kick", S["drums"]["kit"]["kick"] == {"sound": "dm:tr808/kick", "bus": "kick"}),
                                        ("voice", (S["voices"]["flute"]["sound"], S["voices"]["flute"]["label"]) == ("gs:0:72", "Clarinet")),
                                        ("fx kept", S["voices"]["flute"]["fx"] == tomllib.loads(before)["voices"]["flute"]["fx"]),
                                        ("three lines", len(changed) == 3)] if not ok])
    moss.write_text(before)
    bad = [x for x, args in [("not allowed", ("drums.kit", "kick", "pixel:bitplane-blues/kick")),
                             ("no such file", ("drums.kit", "kick", "dm:nope/kick")),
                             ("uncleared", ("drums.kit", "kick", "breaks:amen")),
                             ("sample as voice", ("voices", "flute", "dm:r_n_b/old_kik")),
                             ("engine voice", ("voices", "sub", "gs:0:38")),
                             ("raw iowa", ("drums.kit", "kick", "iowa:raw/x"))]
           if not raises(lambda a=args: R.set_sound(moss, *a))]
    check("uncleared or unfit sounds refused, file untouched", bad + ([] if moss.read_text() == before else ["changed"]))
    t2 = R.new_take(moss, "Moss Radio Take 3", 5)
    R.set_sound(t2, "drums.kit", "snare", "dm:linn/linn_snr")
    R.set_sound(t2, "voices", "keys", "gs:0:4", "Tine EP")
    T, P = SS.load(t2), SS.load(moss)
    check("set_sound on a take", [x for x, ok in [
        ("snare", T["drums"]["kit"]["snare"] == {"sound": "dm:linn/linn_snr", "bus": "snare"}),
        ("keys", (T["voices"]["keys"]["sound"], T["voices"]["keys"]["fx"]) == ("gs:0:4", P["voices"]["keys"]["fx"])),
        ("parent", P["drums"]["kit"]["snare"]["sound"] == "dm:acoustic/jazzsnr")] if not ok])

    cmd = R.command(moss, "test")
    check("commands", [x for x, ok in [("check", R.command(moss, "check")[-1] == "--dry"),
                                       ("test", cmd[-2:] == ["--as", "Moss Radio spec test"] and cmd[1] == "-I"),
                                       ("build", R.command(moss, "build")[-1] == str(moss)),
                                       ("unknown", raises(lambda: R.command(moss, "rm")))] if not ok])

    # the beats backend renders at the record's tempo, not its own constants
    import songspec_beats as SB
    import window_frost as WF
    wf = tmp / "window-frost.toml"
    keep = (WF.BPM, WF.SPB, WF.SWING)
    SB.inject(SB.compose(SS.load(wf)), WF)
    same = (WF.BPM, WF.SPB, WF.SWING) == keep
    R.set_meta(wf, {"bpm": 90, "swing": 0.62})
    SB.inject(SB.compose(SS.load(wf)), WF)
    check("beats backend tempo", [] if same and (WF.BPM, WF.SPB, WF.SWING) == (90, 60 / 90, 0.62) else
          [f"{(WF.BPM, WF.SPB, WF.SWING)}"])
finally:
    shutil.rmtree(tmp)

print("all pass" if not fails else f"{fails} failed")
sys.exit(1 if fails else 0)
