# Bountiful Music

Songs composed by a procedural composer, then **produced like records** in a chosen genre.

## Bountiful, the app

```bash
scripts/install.sh          # install: start menu (Multimedia → Bountiful), launcher `bountiful`, icons
```

This installs a clone of this repo into `~/.local/lib/bountiful/app`, with its own Python in `~/.local/lib/bountiful/venv`. Your music stays where it is: the `data` path in `~/.config/bountiful/config.toml`.

**Updating.** Commit changes here. Then, in the app, click **⬆ Update** in the status bar (or use Help → Check for updates). It pulls the new commits from this repository, refreshes dependencies, the menu entry and icons, and restarts.

To update from GitHub instead, point the clone there: `git -C ~/.local/lib/bountiful/app remote set-url origin <url>`.

Other install commands: `scripts/install.sh --uninstall` removes the app, launcher, menu entry and icons, but keeps your music and config. `scripts/install.sh --refresh` reinstalls dependencies, menu entry and icons only.

| View | What it does |
|---|---|
| **Start** | Make a new song in one click, jump to the main jobs, or reopen a recent track. Every tab has a short help line, and hovering over a control shows a hint. |
| **Arrange** | Every part shown as a lane, with the song's sections on top. Click to move the playhead; double-click a lane to open it in the **piano roll**. |
| **Piano roll** | Double-click to add a note, drag to move it, drag its edge to change the length. Right-click or Delete removes a note. Alt+wheel sets velocity, ↑/↓ transposes (Shift: by an octave). Ctrl+S saves the MIDI, then **Render**. |
| **Mixer** | One strip per rendered stem: fader, pan, mute, solo, meter. **Bounce** (Ctrl+B) writes the mix to `exports/<name>_mix.wav`. "Play the mastered export" switches to the mastered file. |
| **New song** | Key, tempo, length and colour (reharmonisation). The **operator** plays the machine's knobs through the song: the rules' arc, bent by your **brief** in plain words ("make the break more restless, keep the Rhodes intimate, let the last two minutes open into something huge"). Code reads the brief (`intent.py`, no model) into explicit controls you can see and untick before you make the song. **Plan** shows the chords, sections and every move with its reason; **Make & render** builds the track. |
| **Play live** | The machine plays the song as it goes, synthesised a bar ahead. Its knobs, channel mutes and gates take effect from the next bar, and each change is recorded as a move. **Make this take a song** turns the take into a track. The panel also lists its ideas, best first: **Audition** one, then 👍 / 👎 it. The critic learns your taste after 5 ratings. |
| **Sound lab** | Bountiful's own eleven engines (Ghost, Gravity, Weather, Breakforge, Phase Garden, Prismatic, Echo, Oracle, Material, Fractal, Terrain): tracks of engines and presets, routing with bounded feedback, a param form, snapshots, a look inside each engine. Exports WAV, or writes the tracks into a song. See [docs/synthesis-lab.md](docs/synthesis-lab.md). |
| **Batch of ideas** | Runs N Bounties at once, ranked by the critic plus your taste, each with an audition of its best idea. The best few are written as whole songs. You can rate them, open them, or take one to Song or Live. |
| **Game music** | Turns part of the open song into a seamless game loop with four intensity states (calm, explore, tense, combat), separate layers, stingers in the song's key, and players for Godot and Unity. **Try it like a game** plays the loop and switches states the way a game would. See [docs/game-music.md](docs/game-music.md). |
| **Ideas and history** | Ratings, the family tree of songs, the producer's changes, and new takes on bars you like. See [docs/ecosystem.md](docs/ecosystem.md). |

Command line equivalents: `bountiful/electronium_song.py`, `bountiful/live.py`, `bountiful/batch.py`, `bountiful/operator_.py`, `bountiful/taste.py`, `bountiful/gamemusic.py`, `bountiful/updater.py`.

Tests:
- `$ENGINE_PY tests/test_electronium.py`: the music
- `$ENGINE_PY tests/test_gamemusic.py`: game loops, layers, states and stingers
- `~/.local/lib/bountiful/venv/bin/python tests/test_app.py`: the updater, audio, the MIDI round trip, and a headless run of the window

The older Tk app (`./bountiful-music`) still works.

```bash
~/Documents/Projects/bountiful-music/bountiful-music        # the app
```

1. Pick a **genre** (the preset selector). Optionally move the feel sliders: tempo, melody notes per bar, largest melody leap, swing, humanize.
2. **Compose** a batch of candidate songs. They are ranked for the genre, each listed with its chorus chords.
3. Select one and **▶ Preview chorus** (renders in about 10 seconds). Like it but not the tune? **New melody** keeps the song's structure, chords and bass and writes a new melody. **New chords** and **New bass** work the same way.
4. **● Build track** writes the full song to `tracks/<title>/`: MIDI, WAV, MP3, stems and `notes.txt`. Then **Open in MIDI Studio** to change sounds.

Command line: `bountiful/build.py genres | compose | produce | render | reroll` (see the file header).

## Genres (`genres/*.toml`)

| Preset | Character |
|---|---|
| NY House '93 | Morales-tradition house: 4/4, swung hats, congas and timbales, piano stabs, octave bass, strings |
| Finnish Deep House '92 | Nordic underground house: glassy organ with Leslie, deep bass, a mellow melody that breathes |
| Soviet Synth-pop '86 | Biokonstruktor school: Polivoks bass in octaves, sequencer arpeggio, Formanta strings, synthetic drums with syn-toms |
| Italo Disco '84 | LinnDrum-style 4/4 with claps, galloping octave bass, bright arpeggios, singing lead |
| Atmospheric Jungle '95 | breaks at 170 with ride, the composition at half speed, Rhodes, sub bass, long pads |
| Lo-fi Downtempo | swung boom-bap, strummed Rhodes comping, jazzy 9ths, walking bass, cassette master |
| Electronium '69 | Raymond Scott's lab: the Electronium writes the lead, a vibes sidekick a fifth below, drums from its clock matrix |

A genre file holds:

- the composer settings
- harmony: chord rhythm, colours, modal dominants
- melody: register, largest leap, density, articulation, humanize, swing, dynamics
- the bass style
- pad, comp and arpeggio parts
- the drum style and kit (`genres/kits.toml`)
- the arrangement template
- the sounds (an instrument map, rendered by `../intelligent-jungle/studio/render_midi.py`)

To make a new genre, copy a file. A genre can also have an `[experimental_synthesis]` table (off by default; `produce --experimental` switches it on) that lets the Lab's engines play its parts: see [docs/synthesis-lab.md](docs/synthesis-lab.md).

## Why it no longer sounds like the composer

The raw composer output has measurable "tells" (`tools/tells.py`). The composer's own settings barely move them, so Bountiful takes the composition as a **skeleton**: key, one chord per bar (detected per half bar from harmony and bass), one melody line, one bass line, and the sections, from which it picks chorus, verse and bridge loops itself. The **producer** (`bountiful/producer.py`) then performs that skeleton:

| Tell (raw → produced, six genres) | What the producer does |
|---|---|
| melody doubled in octaves: 28–56% → **0%** | one melody line; octave layers only where the arrangement asks |
| melodic leaps wider than a 5th: 19–41% → **0–9%** | leaps folded by octave (same note name, so the harmony is untouched), register centred |
| repeated-note runs: up to 1.3 per 8 bars → **0–0.2** | runs of 3+ become held notes; busy bars thinned (weak, short, off-chord notes go first) |
| chord changes per bar: 1.0–1.4 → **0.6–1.0** | one chord per bar (or as the genre says), voice-led voicings, colours chosen to fit the key |
| notes exactly on the grid: 95–100% → **15–43%** in played genres | humanize, push, swing; sequencer genres stay tight on purpose |
| flat dynamics | velocity follows the phrase (rises to its peak note, accents strong beats); a breath at each 4-bar phrase end |

Classical V7 cadences become modal (v) in the genres that want it. Every chord colour (m9, maj9, add9 …) is checked against the key, so an added tone never clashes with the melody. Each track's `notes.txt` lists its own before/after tells.

## The Electronium (`bountiful/electronium.py`)

A modern take on Raymond Scott's Electronium, his "instantaneous composition-performance machine", built the way his was: a console over a 12-channel sequencer where every channel has its own tone generator, a bassline sequencer and rhythm generator inside, preset rhythms that combine, a recorder for the operator's moves, and a machine that "thinks of 200 things every day. You keep the ones that are good." It doesn't step-sequence. Interlocking behaviours write the music, and you steer them. It works in any genre: tick **writes the lead** (and optionally **plays the drums**) in the app's Electronium panel, or set `[melody] writer = "electronium"` and an `[electronium]` table in a genre file.

| Part | What it does | Knob |
|---|---|---|
| **Bounty** (the seed) | Every random number is drawn up front from the Bounty, per step and per subsystem. The same Bounty always gives the same terrain. The knobs only set thresholds and weights over it, so turning one reshapes the music rather than re-rolling it. Words work too (`--bounty C-Lizzy`). | Bounty ◀ ▶ ⚄ |
| **Clock matrix** | One 16th-note master clock feeds dividers, and logic gates over them make the triggers. `cN` fires every N steps, `cN+k` fires k steps late, `rN` uses the Bounty's phase, `p1`–`p12` are the preset rhythm buttons (quarters, tresillo, eighths, offbeats, two-step, dotted 8ths, son clave …), combined with `& \| ^ ~ ( )`. A figure only comes round again after the lcm of its dividers (2, 3, 4, 7, 8 → 168 steps, 10.5 bars). | Gate |
| **Density** | A trigger plays when the terrain's number at that step is under the threshold. Blocks can scale it with `activity`. | Density |
| **Markov pitch** | A walk over the scale constraint (the song's key, or e.g. minor pentatonic on C). Each interval jump has a weight (repeat, step, 3rd, 4th, 5th, 6th, octave), with an up/down bias and a pull to chord tones on strong pulses. | Scale, Interval jumps, Up/down, Chord gravity |
| **Mutation** | The interval weights drift bar by bar, a mean-reverting walk scaled by this rate. | Mutation |
| **Accent** | Velocity follows how many clocks coincide on a step. | Accent |
| **Behaviours** | Each bar either generates, or treats the last bar: repeat, reverse (retrograde), transpose, invert or ornament (mordents and turns). | Behaviours |
| **Freeze & Populate** | A ring buffer holds the last 16 notes. A freeze captures the last 8 or 16 into a loop, then transposes it, inverts it, or lets a 16-bit LFSR mutate cells (Turing-machine style). Modify adds step-quantized pitch and velocity offsets that build up. When the loop ends, the machine breaks back into generation. | ❄ Freeze, Modify |
| **Sidekick** | Channel 2 (MIDI channel 7, its own stem) follows the lead by a rule: `fifth_below`, `third_below`, `root_on_downbeat`, `contrary` or `canon`. It plays in blocks that list `sidekick`, or with the lead when no block does. |
| **Channels** | Up to 12 `[[channels]]` play at once, each with a role, gate, register, density and tone. **melody** (the walk, themes, behaviours), **harmony** (follows a channel by an interval button: thirds, sixths, fifth, octave below or above, canon, contrary, root on the downbeat), **bass** (the bassline sequencer: roots on the changes, fifths, octaves, approach notes), **ostinato** (a stepping sequence of chord tones, `length` cells long, phasing against the bar; the LFSR rewrites cells), **counter** (a slow line in contrary motion that keeps off the melody's notes). A channel named after a part (bass, arp) replaces it. Without `[[channels]]` it's the classic lead and sidekick. | `[[channels]]` |
| **Thinking** | Before playing, the melody thinks of `think` (200) two-bar ideas from the Bounty and the knobs. A critic scores them on shape, range, steps and leaps, gap fill, a long last note, call and answer, one high point and syncopation. It keeps the best `keep` (3), or the idea numbers you choose. Each section gets a kept idea as its theme, which comes back with the section; an 8-bar `phrase` plan (theme, answer, free, cadence) sets where. | Think, keep ideas |
| **Recorder** | `[[moves]]` plays back the operator's hands: at a bar, set any knob (or a channel's gate, density, register, transpose, mute …), or ramp it there by `to_bar`. Freezes can be moves too. | `[[moves]]` |
| **Tone generators** | `electronium_voice.py`, one analog channel voice: band-limited oscillators (square/pulse with PWM, saw, triangle), a sub, noise, a resonant filter with its own envelope, fixed envelopes (pluck, perc, organ, swell, gate), accent, tremolo, vibrato, drift, glide, optional bit/rate crush. Presets `scott-lead`, `pulse-sidekick`, `bass-sequencer`, `ostinato-bell`, `counter-reed`, `bloop`; reverb is the plate send. The renderer plays them as `kind = "pyvoice"`. | `tone`, `mix` | Sidekick |

Each track built with it saves `electronium.toml`, the full patch, so `produce --patch` rebuilds it note for note. Its `notes.txt` shows the clock cycle and what the machine did in every bar. **Show the terrain** (or `bountiful/electronium.py --bounty 7`) prints the clock matrix as text, **Think** (or `--ideas`) lists what the machine thought of, best first.

```
$PY bountiful/build.py produce --genre italo-disco-84 --song songs/... --bounty 1969 [--electronium-drums] [--patch electronium.toml] --render
```

Demo: `tracks/bounty-1969` (Electronium '69, Bounty 1969).
Pixel-tracker single: `tracks/clockwork-copper`, built by `bountiful/pixel_electronium.py [--bounty WORD]`: a 'Put on the Pixel'
style chip DnB tune played by five Electronium channels on their own tone generators (lead on three chosen themes, sidekick,
bassline sequencer, 5-cell ostinato, counter line) with recorder moves, plus the drum lanes the grid doesn't have
(in a grid song, any drum layer missing from the grid is looked up in the Electronium's `drums` table).

## Credits and friends

- **Artist:** every release is by **M4S4T0**. The artist lives in `bountiful/credits.py`; build, LMMS tracks, albums and remixes all take it from there, and nothing overrides it.
- **Friends:** `friends.toml` remembers friends and their handle on each platform (SoundCloud, Bandcamp, YouTube, Instagram, Threads, TikTok, X, Bluesky, Mastodon, Twitch, Facebook). Manage them with the app's **Friends** button or `bountiful/friends.py add "Name" --instagram handle`.
- **Share captions:** **Share captions**, or `friends.py share tracks/<slug> --with "Name, Name"`, writes one caption per platform to `<track>/share/`. A friend is @-tagged only where they have a handle on that platform, linked on platforms without tags (Bandcamp, Facebook), and credited by name everywhere else. Friends marked `always` (C-Lizzy) are on every release, and the track remembers who's on it.
- **Nothing is posted:** the captions are for you to paste.

Tests: `$PY tests/test_electronium.py` (Electronium, credits, friends), `$PY tests/smoke_app.py` (the app's logic, without a display).

## Layout

- `bountiful/`
  - `composer.js`: the composer core, headless
  - `gen.js`: batch composing and seed pinning
  - `skeleton.py`, `producer.py`, `build.py`
  - `electronium.py`: the machine: channels, clock matrix, presets, thinking, recorder, clock-matrix drums
  - `electronium_voice.py`: its tone generator
  - `credits.py`: the artist credit
  - `friends.py`: the friends registry and share captions
  - `app.py`: the GUI
  - `synthesis/`: the Synthesis Lab: engines, routing, modulation, projects, demos ([docs/synthesis-lab.md](docs/synthesis-lab.md))
  - the ecosystem: `features.py`, `laws.py`, `evaluators.py`, `evolve.py`, `discover.py`, `lineage.py`, `network.py`, `intent.py`, `studio.py`, `timbre.py`, `observatory.py` ([docs/ecosystem.md](docs/ecosystem.md))
  - `gamemusic.py`: game-music export: loops, intensity states, layers, stingers, Godot/Unity players ([docs/game-music.md](docs/game-music.md))
  - `daw/`: the PySide6 app (`daw/start.py`: the Start page, `daw/gamemusic.py`: the Game music tab, `daw/lab.py`: the Sound lab tab, `daw/observatory.py`: the Ideas and history tab)
- `genres/`: presets and drum kits
- `songs/`: composed skeletons. `tracks/`: produced tracks. `synthesis/demos/`: the Lab's demos.
- `tools/`: the first-generation scripts (am2mid, analyze, tells, arrange) that made Downtown Protocol and Kosmodrom
- `upstream/`: the original composer, unmodified

## Credit

The composer core is **Abundant Music** by Per Nyblom (2012–2017), MIT License (`upstream/abundant-music/LICENSE`), sparse-checked out from github.com/pernyblom/pernyblom.github.io. Bountiful runs its `composeworkersource.js` unmodified in a Node sandbox. Two changes are made around it, not inside it: its 76 per-aspect seeds are derived from the song seed (upstream defaults them all to the same value), and its output is re-performed by the genre producer.

Rendering uses the engine in `../intelligent-jungle`. Python 3.11 with numpy, scipy, soundfile, mido and pyloudnorm, plus Node 22 and LAME.
