// Bountiful Music: the composer core.
// Runs Abundant Music's composer (upstream/abundant-music/js/composeworkersource.js,
// Copyright (c) 2017 Per Nyblom, MIT License - see upstream/abundant-music/LICENSE) headless in Node.
// Bountiful uses it to compose a song skeleton (structure, harmony, melody and bass motion); the
// genre producer (bountiful/producer.py) then performs that skeleton in a style.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

// the vendored copy (unmodified, with its LICENSE) ships with the app; a full upstream checkout is used if present
const SRC = [path.join(__dirname, "..", "upstream", "abundant-music", "js", "composeworkersource.js"),
             path.join(__dirname, "..", "vendor", "abundant-music", "composeworkersource.js")].find(p => fs.existsSync(p));

// seed groups that the app can re-roll on their own (everything else stays pinned)
const GROUPS = {
  melody: ["melodyMotifSeed", "melodyMotifRythmSeed", "melodyMotifEmbellishConnectSeed", "melodyShapeSeed", "melodyShapeIndicesSeed",
           "melodyMotifDistributionSeed", "melodyMotifDistributionIndicesSeed", "melodyHarmonyPunctationSeed", "melodyChannelDistributionIndicesSeed"],
  harmony: ["harmonySeed", "harmonyIndicesSeed", "harmonyRythmSeed", "harmonyRythmIndicesSeed", "harmonyExtraIndicesSeed", "harmonyMotifSeed",
            "harmonyMotifRythmSeed", "harmonyMotifEmbellishConnectSeed", "suspendSeed", "suspendIndicesSeed", "tonicizationSeed", "modulationSeed"],
  bass: ["bassMotifSeed", "bassMotifRythmSeed", "bassMotifEmbellishConnectSeed", "bassShapeSeed", "bassShapeIndicesSeed", "bassMotifDistributionSeed",
         "bassMotifDistributionIndicesSeed"],
  structure: ["songStructureSeed", "glueSeed", "phraseGroupSeed", "phraseGroupSimilaritySeed", "groupSimilaritySeed", "groupDifferenceSeed", "introSeed", "endSeed"],
};

function loadComposer(log) {
  const ctx = { console, Math, JSON, Date, logit: (s) => log && log(String(s)) };
  ctx.self = ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(SRC, "utf8"), ctx, { filename: "composeworkersource.js" });
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

// All 76 per-aspect seeds derive from the song seed (upstream defaults them all to 123456, which
// makes every song nearly the same); overrides (style settings, pinned seeds) are applied after.
function compose(ctx, seed, overrides) {
  const gi = ctx.__defaultGenInfo();
  const rnd = new ctx.MersenneTwister(seed);
  for (const k of seedKeys(ctx)) gi[k] = rnd.genrand_int31();
  for (const [k, v] of Object.entries(overrides || {})) gi[k] = v;
  const r = ctx.__render(seed, gi);
  r.seeds = Object.fromEntries(seedKeys(ctx).map((k) => [k, gi[k]]));
  return r;
}

module.exports = { loadComposer, compose, seedKeys, GROUPS };
