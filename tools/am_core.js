// Load Abundant Music's composer (upstream/abundant-music/js/composeworkersource.js, MIT, Per Nyblom)
// into a sandbox and expose generate(seed, genInfoOverrides) -> {midiData, songStructureInfo, ...}.
// This mirrors upstream's worker.js render() + MidiRenderer.getMidiData(), without a browser.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = path.join(__dirname, "..", "upstream", "abundant-music", "js", "composeworkersource.js");

function loadComposer(log) {
  const ctx = { console, Math, JSON, Date, logit: (s) => log && log(String(s)) };
  ctx.self = ctx;
  ctx.window = undefined;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(SRC, "utf8"), ctx, { filename: "composeworkersource.js" });
  // the worker's render(), verbatim in logic (upstream worker.js)
  vm.runInContext(`
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
    function __defaultGenInfo() { return new GenInfo(); }
  `, ctx);
  return ctx;
}

function seedKeys(ctx) {
  return Object.keys(ctx.__defaultGenInfo()).filter((k) => /Seed$/.test(k));
}

// Every per-aspect seed (tempoSeed, scaleSeed, songStructureSeed, melodyMotifSeed, ... 76 of them) is
// derived from the song seed, as the web app's "random" does; any of them can be pinned in overrides
// (e.g. keep songStructureSeed + harmonySeed from one song and re-roll melodyMotifSeed).
function generate(ctx, seed, overrides) {
  const gi = ctx.__defaultGenInfo();
  const rnd = new ctx.MersenneTwister(seed);
  const seeds = {};
  for (const k of seedKeys(ctx)) { gi[k] = rnd.genrand_int31(); seeds[k] = gi[k]; }
  for (const [k, v] of Object.entries(overrides || {})) gi[k] = v;
  const r = ctx.__render(seed, gi);
  r.seeds = Object.fromEntries(seedKeys(ctx).map((k) => [k, gi[k]]));
  return r;
}

module.exports = { loadComposer, generate, seedKeys };

if (require.main === module) {
  const ctx = loadComposer((s) => process.stderr.write("[am] " + s + "\n"));
  const t = Date.now();
  const r = generate(ctx, Number(process.argv[2] || 1), {});
  const ev = r.midiData.midiTracks ? r.midiData.midiTracks[0].trackEvents : r.midiData;
  console.log(JSON.stringify({ ms: Date.now() - t, keys: Object.keys(r.midiData), length: r.length, sections: r.sectionTimes.length,
    structure: Object.keys(r.songStructureInfo || {}).slice(0, 20) }));
}
