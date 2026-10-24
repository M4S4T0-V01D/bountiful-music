#!/usr/bin/env node
// Compose song skeletons.  node bountiful/gen.js --settings settings.json --seed 1 --seed 2 | --count 8  --out DIR
//   [--pin song.am.json --reroll melody,bass]   keep every seed of an existing song except the named groups
// Prints one JSON line per song: {"file":..., "seed":..., "beats":..., "sections":...}
"use strict";
const fs = require("fs");
const path = require("path");
const { loadComposer, compose, GROUPS } = require("./composer.js");

const a = { seeds: [], count: 0 };
const argv = process.argv.slice(2);
for (let i = 0; i < argv.length; i++) {
  const k = argv[i];
  if (k === "--settings") a.settings = argv[++i];
  else if (k === "--seed") a.seeds.push(Number(argv[++i]));
  else if (k === "--count") a.count = Number(argv[++i]);
  else if (k === "--out") a.out = argv[++i];
  else if (k === "--pin") a.pin = argv[++i];
  else if (k === "--reroll") a.reroll = argv[++i].split(",");
  else if (k === "--prefix") a.prefix = argv[++i];
  else throw new Error("unknown argument " + k);
}
const ctx = loadComposer(null);
const settings = a.settings ? JSON.parse(fs.readFileSync(a.settings, "utf8")) : {};
const known = ctx.__defaultGenInfo();
for (const k of Object.keys(settings)) if (!(k in known)) throw new Error("unknown composer setting: " + k);
let pinned = {};
if (a.pin) {
  const doc = JSON.parse(fs.readFileSync(a.pin, "utf8"));
  const drop = new Set((a.reroll || []).flatMap((g) => GROUPS[g] || [g]));
  pinned = Object.fromEntries(Object.entries(doc.seeds).filter(([k]) => !drop.has(k)));
}
let seeds = a.seeds.slice();
for (let i = 0; i < a.count; i++) seeds.push(1 + Math.floor(Math.random() * 2147483646));
fs.mkdirSync(a.out || "songs", { recursive: true });
for (const seed of seeds) {
  const r = compose(ctx, seed, Object.assign({}, JSON.parse(JSON.stringify(settings)), pinned));
  const ssi = r.songStructureInfo || {};
  const name = `${a.prefix || "song"}-${seed}`;
  const doc = { generator: "Bountiful Music (composer core: Abundant Music by Per Nyblom, MIT)", name, seed,
                pinnedFrom: a.pin || null, rerolled: a.reroll || null, settings, seeds: r.seeds, lengthBeats: r.length,
                sectionTimes: r.sectionTimes, structure: { tempos: ssi.tempos, scaleTypes: ssi.scaleTypes, scaleBaseNotes: ssi.scaleBaseNotes,
                numerators: ssi.numerators, songPartTypes: ssi.songPartTypes }, midiData: r.midiData };
  const f = path.join(a.out || "songs", name + ".am.json");
  fs.writeFileSync(f, JSON.stringify(doc));
  console.log(JSON.stringify({ file: f, seed, beats: r.length, sections: r.sectionTimes.length }));
}
