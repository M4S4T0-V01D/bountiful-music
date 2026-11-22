"""The composer core without Node: Abundant Music's composer (vendor/abundant-music/composeworkersource.js, Copyright
(c) 2017 Per Nyblom, MIT License) run in an embedded V8 (mini-racer), doing what composer.js + gen.js do under Node and
writing the same .am.json documents byte for byte (same engine, same JSON.stringify).

    files = compose_songs(settings, seeds=[1, 2], count=0, out=Path("songs/x"), prefix="x", pin=None, reroll=None)
"""
from __future__ import annotations

import json
import random
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = next(p for p in (HERE.parent / "upstream" / "abundant-music" / "js" / "composeworkersource.js",
                       HERE.parent / "vendor" / "abundant-music" / "composeworkersource.js") if p.is_file())

# composer.js's GROUPS and compose(), and gen.js's document, in the composer's own context
GLUE = r"""
var GROUPS = %s;
function __render(seed, genInfo) {
  var rnd = new MersenneTwister(seed);
  var resultObj = {};
  var module = createTestModule(rnd.genrand_int31(), genInfo, resultObj);
  var midiRenderer = module.getSynthRenderer("midiRenderer");
  var renderData = new RenderData();
  var state = new RenderState(module, renderData);
  var structure = module.structures[0];
  if (structure.references.length > 40) structure.references.length = 40;
  var sectionTimes = [];
  structure.renderBatch(state, function () { sectionTimes.push(state.sectionTime); });
  renderData.sort();
  var midiData = midiRenderer.getMidiData(renderData, module, genInfo);
  return { seed: seed, midiData: midiData, songStructureInfo: resultObj.songStructureInfo,
           channelMaps: midiRenderer.channelMaps, sectionTimes: sectionTimes, length: state.sectionTime };
}
function __seedKeys() { return Object.keys(new GenInfo()).filter(function (k) { return /Seed$/.test(k); }); }
function __unknownSettings(json) { var gi = new GenInfo(); return JSON.stringify(Object.keys(JSON.parse(json)).filter(function (k) { return !(k in gi); })); }
function __pinned(docJson, reroll) {
  var doc = JSON.parse(docJson), drop = new Set([].concat.apply([], reroll.map(function (g) { return GROUPS[g] || [g]; })));
  return Object.fromEntries(Object.entries(doc.seeds).filter(function (e) { return !drop.has(e[0]); }));
}
function __song(seed, settingsJson, pinJson, pinPath, reroll, name) {
  var settings = JSON.parse(settingsJson);
  var pinned = pinJson ? __pinned(pinJson, reroll) : {};
  var overrides = Object.assign({}, JSON.parse(JSON.stringify(settings)), pinned);
  var gi = new GenInfo(), rnd = new MersenneTwister(seed), keys = __seedKeys();
  keys.forEach(function (k) { gi[k] = rnd.genrand_int31(); });
  Object.entries(overrides).forEach(function (e) { gi[e[0]] = e[1]; });
  var r = __render(seed, gi);
  r.seeds = Object.fromEntries(keys.map(function (k) { return [k, gi[k]]; }));
  var ssi = r.songStructureInfo || {};
  var doc = { generator: "Bountiful Music (composer core: Abundant Music by Per Nyblom, MIT)", name: name, seed: seed,
              pinnedFrom: pinPath || null, rerolled: pinPath ? reroll : null, settings: settings, seeds: r.seeds, lengthBeats: r.length,
              sectionTimes: r.sectionTimes, structure: { tempos: ssi.tempos, scaleTypes: ssi.scaleTypes, scaleBaseNotes: ssi.scaleBaseNotes,
              numerators: ssi.numerators, songPartTypes: ssi.songPartTypes }, midiData: r.midiData };
  return JSON.stringify([JSON.stringify(doc), r.length, r.sectionTimes.length]);
}
"""
GROUPS = {
    "melody": ["melodyMotifSeed", "melodyMotifRythmSeed", "melodyMotifEmbellishConnectSeed", "melodyShapeSeed", "melodyShapeIndicesSeed",
               "melodyMotifDistributionSeed", "melodyMotifDistributionIndicesSeed", "melodyHarmonyPunctationSeed",
               "melodyChannelDistributionIndicesSeed"],
    "harmony": ["harmonySeed", "harmonyIndicesSeed", "harmonyRythmSeed", "harmonyRythmIndicesSeed", "harmonyExtraIndicesSeed",
                "harmonyMotifSeed", "harmonyMotifRythmSeed", "harmonyMotifEmbellishConnectSeed", "suspendSeed", "suspendIndicesSeed",
                "tonicizationSeed", "modulationSeed"],
    "bass": ["bassMotifSeed", "bassMotifRythmSeed", "bassMotifEmbellishConnectSeed", "bassShapeSeed", "bassShapeIndicesSeed",
             "bassMotifDistributionSeed", "bassMotifDistributionIndicesSeed"],
    "structure": ["songStructureSeed", "glueSeed", "phraseGroupSeed", "phraseGroupSimilaritySeed", "groupSimilaritySeed",
                  "groupDifferenceSeed", "introSeed", "endSeed"],
}

_lock = threading.Lock()


def available() -> bool:
    try:
        import py_mini_racer  # noqa: F401
        return True
    except ImportError:
        return False


def _context():
    """a fresh composer (loads in a few ms); close it when done, or V8's thread keeps Python from exiting"""
    from py_mini_racer import MiniRacer
    ctx = MiniRacer()
    ctx.eval("var self = this; var console = { log: function () {}, warn: function () {}, error: function () {} };"
             "function logit(s) {}")
    ctx.eval(SRC.read_text(encoding="utf-8"))
    ctx.eval(GLUE % json.dumps(GROUPS))
    return ctx


def compose_songs(settings: dict, seeds=(), count: int = 0, out: Path = Path("songs"), prefix: str = "song",
                  pin: Path | None = None, reroll: list[str] | None = None):
    """Yields (file, seed, beats, sections) per song, as gen.js prints them."""
    with _lock:
        ctx = _context()
        try:
            yield from _songs(ctx, settings, seeds, count, out, prefix, pin, reroll)
        finally:
            ctx.close()


def _songs(ctx, settings, seeds, count, out, prefix, pin, reroll):
    for k in json.loads(ctx.call("__unknownSettings", json.dumps(settings)))[:1]:
        raise ValueError(f"unknown composer setting: {k}")
    seeds = list(seeds) + [random.randint(1, 2147483646) for _ in range(count)]
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    pin_json = Path(pin).read_text(encoding="utf-8") if pin else None
    for seed in seeds:
        name = f"{prefix}-{seed}"
        doc, beats, sections = json.loads(ctx.call("__song", seed, json.dumps(settings), pin_json,
                                                   str(pin) if pin else None, list(reroll or []), name))
        f = out / f"{name}.am.json"
        f.write_text(doc, encoding="utf-8")
        yield f, seed, beats, sections
