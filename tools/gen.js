#!/usr/bin/env node
// Generate songs with Abundant Music's composer, headless.
//
//   node tools/gen.js --style styles/deep-house.json --seed 42 --out songs/
//   node tools/gen.js --style styles/deep-house.json --count 8 --out songs/       (random seeds)
//   node tools/gen.js --seed 42 --set tempoRange=[90,100] --set minorScaleLikelihood=5 --out songs/
//
// A style is a JSON object of GenInfo overrides (any of its ~300 settings; `node tools/gen.js --list`
// prints them all with their defaults). Writes <out>/<name>.am.json: the MIDI events (192 ppq, one
// track, role-based channels), the seed, the settings used and the song-structure summary.
"use strict";
const fs = require("fs");
const path = require("path");
const { loadComposer, generate } = require("./am_core.js");

function parseArgs(argv) {
  const a = { set: [], seeds: [] };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (k === "--style") a.style = argv[++i];
    else if (k === "--seed") a.seeds.push(Number(argv[++i]));
    else if (k === "--count") a.count = Number(argv[++i]);
    else if (k === "--out") a.out = argv[++i];
    else if (k === "--name") a.name = argv[++i];
    else if (k === "--set") a.set.push(argv[++i]);
    else if (k === "--list") a.list = true;
    else if (k === "--verbose") a.verbose = true;
    else throw new Error("unknown argument " + k);
  }
  return a;
}

function main() {
  const a = parseArgs(process.argv.slice(2));
  const ctx = loadComposer(a.verbose ? (s) => process.stderr.write("[am] " + s + "\n") : null);
  if (a.list) {
    const g = ctx.__defaultGenInfo();
    for (const [k, v] of Object.entries(g)) if (k !== "_constructorName") console.log(k + " = " + JSON.stringify(v));
    return;
  }
  let overrides = {};
  let styleName = "default";
  if (a.style) {
    const st = JSON.parse(fs.readFileSync(a.style, "utf8"));
    styleName = st._name || path.basename(a.style, ".json");
    for (const [k, v] of Object.entries(st)) if (!k.startsWith("_")) overrides[k] = v;
  }
  for (const s of a.set) {
    const i = s.indexOf("=");
    const k = s.slice(0, i), raw = s.slice(i + 1);
    let v;
    try { v = JSON.parse(raw); } catch (e) { v = raw; }
    overrides[k] = v;
  }
  const known = ctx.__defaultGenInfo();
  for (const k of Object.keys(overrides)) if (!(k in known)) throw new Error("unknown setting: " + k + " (see --list)");

  let seeds = a.seeds.slice();
  for (let i = 0; i < (a.count || 0); i++) seeds.push(Math.floor(Math.random() * 2147483647));
  if (!seeds.length) seeds = [Math.floor(Math.random() * 2147483647)];
  const out = a.out || "songs";
  fs.mkdirSync(out, { recursive: true });
  for (const seed of seeds) {
    const t0 = Date.now();
    const r = generate(ctx, seed, JSON.parse(JSON.stringify(overrides)));
    const name = a.name && seeds.length === 1 ? a.name : `${styleName}-${seed}`;
    const ssi = r.songStructureInfo || {};
    const doc = {
      generator: "Abundant Music (Per Nyblom, MIT) composeworkersource.js, run headless",
      name, seed, style: styleName, overrides, lengthBeats: r.length, sections: r.sectionTimes.length,
      structure: { tempos: ssi.tempos, scaleTypes: ssi.scaleTypes, scaleBaseNotes: ssi.scaleBaseNotes,
                   numerators: ssi.numerators, songPartTypes: ssi.songPartTypes, baseTempo: ssi.baseTempo },
      seeds: r.seeds,
      channelMaps: r.channelMaps.map((m) => ({ channel: m.channel, program: m.program, role: m.renderChannel })),
      midiData: r.midiData,
    };
    const f = path.join(out, name + ".am.json");
    fs.writeFileSync(f, JSON.stringify(doc));
    console.log(`${f}  seed ${seed}  ${r.sectionTimes.length} sections, ${Math.round(r.length)} beats, base tempo ${Math.round(ssi.baseTempo || 0)}  (${Date.now() - t0} ms)`);
  }
}

main();
