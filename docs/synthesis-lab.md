# The Synthesis Lab (`bountiful/synthesis/`)

Eleven synthesis engines of Bountiful's own. They are plain code: no AI, no samples unless you give them one, no new dependencies (numpy only). The renderer is still the backbone, and every song renders through it exactly as before. The engines are extra track kinds it can play. The Electronium is still the performance brain: its channels can play engines, and its operator moves can turn their knobs.

Everything is **offline, CPU-only, bounded and deterministic**. The same project, seed and build always give the same samples.

**Switching it off.** Set `BOUNTIFUL_EXPERIMENTAL=0` in the environment, or `experimental_synthesis = false` in `~/.config/bountiful/config.toml`. Every genre and Electronium patch then plays its old sounds and ignores its engine settings. The switch governs songs only, so the Lab itself keeps working.

## The engines

| Engine | What it is | Presets |
|---|---|---|
| `ghost` | Remembers recent pitches, levels and spectrum: afterimages, a residue pad, freeze, capture, recall | afterimage-pad, haunted-keys, frozen-choir, memory-lead, residue-wash, ghost-bells |
| `gravity` | Mass-spring chains, rings, membranes and bars as normal modes; tension bend and sympathetic coupling | steel-chain, gong-ring, tom-skin, marimba-bar, bowed-chain, sympathy, slack-bass |
| `weather` | A spectral pressure field with wind, humidity, storms and seasons; notes condense pitch out of it | drizzle, monsoon-front, dry-whistle, thunderhead, aurora, desert-heat |
| `breakforge` | Procedural drums and a seeded, mutating jungle break generator; stems and MIDI export | afterimage-rollers, tearout, steppers, liquid-ride, chopped-tumble, mpc-grit, midi-kit |
| `phase_garden` | Kuramoto-coupled oscillator populations drifting in and out of sync; the order parameter drives brightness | bloom, lock-step-lead, fireflies, drift-choir, garden-bass, seasons |
| `prismatic` | Interference of a note's sources at a moving listener: path lengths, Doppler and dispersion | glass-prism, hall-of-mirrors, spinning-chord, rainbow-pluck, still-water, doppler-swarm |
| `echo` | A self-regulating colony of delay cells and resonators in a bounded feedback graph; hears audio input | cave-colony, tuned-coral, hungry-swarm, dub-cells, glass-lungs, input-eater |
| `oracle` | Local WAV analysis (f0, harmonics, formants, noise, similarity graph) resynthesised at your notes | singing-source, frozen-moment, dreaming-oracle, transposed-instrument, whisper, slow-scan |
| `material` | A body whose frequency map wears, tires, recovers and cracks with use; frozen and pristine modes | new-marimba, practice-room-piano, cracked-bell, tiring-glass, clay-pots, old-stone |
| `fractal` | Self-similar recursive subdivision of the cycle; depth sets register and decay; hard limits | binary-tree, triplet-fern, golden-clock, fractal-machine, dust-snare, slow-bloom |
| `terrain` | Wave-terrain synthesis: orbits over seeded plane-wave landscapes, a wandering centre, morphing ground, band-limited | desert-voice, pipe-lattice, crater-bell, mountain-growl, lissajous-lead, shifting-sands |

Breakforge's generating presets (afterimage-rollers, steppers, …) play their own break without a clip. `midi-kit` plays GM drum notes (36 kick, 38 snare, 42 hat …) on its kit instead. Oracle needs a WAV (`assets = { source = "voice.wav" }`). Without one it says so in `problems` and stays silent.

### One API

```python
import synthesis as S
S.engines()                         # ids, in the order above
eng = S.create("ghost", preset="afterimage-pad", params={"memory": 14}, seed=7, sr=44100)
y = eng.render(events, n, bpm=120, automation={"residue": [[0, 0.3], [64, 0.8]]}, modulation=None)  # (n, 2) float
S.engine_class("ghost").PARAMS      # Param(name, default, lo, hi, kind, choices, unit, doc); every value is clamped
S.presets("ghost")                  # {name: {param: value}}
eng.snapshot(); eng.restore(snap); eng.reset(); eng.diagnostics()
```

Each engine renders in 256-sample blocks, with a fixed voice limit and hard limits on its internal state (no NaN, no runaway, no unbounded memory). `NAME`, `VERSION` and `DESCRIPTION` describe the engine, and the version is saved with every patch and track.

**User presets.** **Save as my preset** in the Lab, or `synthesis.patches.save_user_preset(patch, name)`, writes `<data>/synthesis/presets/<engine>/<name>.json`. Patches from other engine versions still load: unknown params are dropped and missing ones take the defaults.

## Routing: engines into engines (`routing.py`)

A track can be a **graph** instead of a single engine. The nodes are engines, and the edges carry audio between them block by block:

```toml
[tracks.bells.graph]
notes = ["src"]                         # which nodes hear the track's notes
out = { src = 0.5, eco = 0.6 }          # each node's level into the stereo sum
[tracks.bells.graph.nodes.src]
engine = "material"
preset = "cracked-bell"
[tracks.bells.graph.nodes.eco]
engine = "echo"
preset = "glass-lungs"
[[tracks.bells.graph.edges]]
from = "src"
to = "eco"
gain = 0.8
[[tracks.bells.graph.edges]]
from = "eco"
to = "src"
gain = 0.25
feedback = true
```

Plain edges must form a DAG; on a cycle the graph refuses to build and names the cycle. A `feedback = true` edge may close a loop. It carries the previous block, its gain is capped at 0.9 and it passes through tanh, so a loop cannot run away. Only engines with audio input listen to their inputs (echo, ghost, prismatic, weather, oracle); the others ignore them.

## Modulation and automation (`modulation.py`)

- **Automation:** `automation = { param = [[beat, value], ...] }`, interpolated per block.
- **Modulation matrix:** `modulation = { seed = 0, routes = [{ source = { type = "lfo", rate_beats = 8 }, target = "param", amount = 0.3 }] }`. Each route adds source × amount × the param's range, after automation. The sources are:
  - `lfo`: sine, tri, saw, square or sh; set it in Hz or beats.
  - `envelope`: follows the gate.
  - `step`: a step sequencer.
  - `cc`: a MIDI controller's last value.
  - `song`: the song position, or the bar or beat phase.
  - `random`: a seeded walk.
  - `moves`: Electronium moves.

  All of them are deterministic.

## The Electronium plays engines

Give a channel an engine. Its usual `tone` stays as the fallback:

```toml
[[electronium.channels]]
name = "pad"
role = "harmony"
tone = "ostinato-bell"
engine = { engine = "ghost", preset = "frozen-choir", params = { memory = 10 } }   # or engine = "ghost"
```

Operator moves can set or ramp any engine param as `synth.<param>`. Bars are 1-based, as for every move:

```toml
[[electronium.moves]]
bar = 9
to_bar = 17
channel = "pad"
set = { "synth.residue" = 0.9 }
```

The operator (the rules and your brief) and Live check these moves against that channel's engine and clamp the values. A `synth.` key that the channel's engine doesn't have is reported as a problem and dropped. The machine itself ignores `engine` and `synth.*`, so the notes are the same with or without engines. With the engines switched off, the channel plays its `tone` as always.

## Genres: `[experimental_synthesis]`

```toml
[experimental_synthesis]
enabled = false                       # off: the genre renders exactly as it always has
drums = "breakforge"
breakforge = { preset = "afterimage-rollers", tune = -1 }

[experimental_synthesis.tracks.pad]
engine = "ghost"
preset = "afterimage-pad"
gain_db = -14                         # plus the renderer's usual track keys (pan, sends, hp, duck, ...)
```

It is off unless the table says `enabled = true`, or you pass `--experimental`:

```bash
$PY bountiful/build.py produce --genre atmospheric-jungle-95 --experimental --render
```

The part's original sound stays on as the track's fallback. Songs with synthesis tracks render through `bountiful/synthesis/render.py`, which is the normal renderer lending it the engines. Every other song renders by the very same command as before, sample for sample.

Suggested tables (off by default) ship in:

| Genre | Parts |
|---|---|
| Atmospheric Jungle '95 | Breakforge rollers, Ghost pad, material cracked-bell lead, weather drizzle comp |
| NY House '93 | material practice-room piano comp, phase-garden drift-choir pad, gravity slack bass |
| Soviet Synth-pop '86 | prismatic glass-prism lead, fractal golden-clock arp, Ghost frozen-choir pad, terrain mountain-growl bass |
| Electronium '69 | phase-garden fireflies arp, echo glass-lungs pad, gravity marimba-bar bass |

## The Lab (app → **Synthesis Lab** tab)

- **Top bar:** the project's name, bpm, seed and length; New, Open, Save, **▶ Render**, **Export WAV**, and **To song**, which writes the tracks as an `instruments.toml` table.
- **Tracks:** engine, preset, gain, pan and mute per track. **Add a track** takes a name, an engine, a preset and a starter clip: arp, chords, bass, melody, drone, hits or break.
- **Route into:** turns the selected track into a graph through echo, ghost, prismatic, weather or oracle, with a feedback amount.
- **Snapshots:** capture every engine's state, then choose a snapshot for the engines to start from.
- **Right side:**
  - the engine's description
  - a form of its params, built from `PARAMS`
  - Reset to preset, Save as my preset, **▶ Solo**
  - **Look inside:** what the engine is doing, such as fractal patterns, the material's wear map, the oracle's analysis or terrain's height map
  - the problems list

## Project files (`.bflab`, `project.py`)

```json
{"format": "bountiful-synthesis-project", "format_version": 1, "name": "afterimage", "bpm": 174, "seed": 95,
 "render": {"beats": 64, "sr": 44100, "block": 256, "tail_s": 3.0},
 "tracks": {"pad": {"kind": "synthesis", "engine": "ghost", "version": 1, "preset": "afterimage-pad",
                    "params": {}, "automation": {}, "gain_db": -10, "pan": 0.0, "mute": false,
                    "clip": [[0, 4, 57, 0.8]], "start": null}},
 "snapshots": {}}
```

A Lab track is the same table a song's `instruments.toml` uses for a `kind = "synthesis"` part, so there is one format. `to_instruments` drops the Lab-only keys (`clip`, `start`, `mute`), and `from_instruments` opens a song's synthesis tracks in the Lab.

Loading is forgiving:
- Unknown keys are kept and written back.
- Missing keys take defaults.
- A track whose engine this build doesn't have is kept, and skipped when rendering.

## Demos (`synthesis/demos.py`)

```bash
cd bountiful && $PY -m synthesis.demos [--out DIR] [--only NAME] [--no-stems]
```

By default they are written to `<data>/synthesis/demos/<name>/`: the `.bflab`, the mix at −1 dBFS and the stems. Each demo opens in the Lab.

| Demo | Engines |
|---|---|
| `afterimage`: 174 bpm jungle | breakforge rollers with intensity rising, Ghost pad, gravity bass, weather drizzle, material bells → echo with feedback |
| `mechanical-garden`: 104 bpm | fractal golden clock, gravity marimba bars, phase-garden bloom, material clay pots |
| `prismatic-weather`: 80 bpm | weather monsoon front, prismatic spinning chords, Ghost frozen choir |
| `fractal-machine`: 128 bpm | fractal machine and dust snare, terrain mountain-growl bass and Lissajous lead |
| `eight-engines`: 122 bpm, 9 engines | breakforge, gravity, material, phase garden, terrain, weather, prismatic → Ghost with feedback, fractal |

## Tests

```bash
$PY tests/test_synthesis.py           # every engine: API, limits, determinism, presets, routing, modulation
$PY tests/test_synthesis_project.py   # project format, snapshots, feedback, song tables, clips, demos
$PY tests/test_electronium.py         # includes engine channels and synth.<param> moves, and switched off
~/.local/lib/bountiful/venv/bin/python tests/test_app.py   # the window, including the Lab
```
