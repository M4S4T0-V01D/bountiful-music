# Song Spec

A record written as data instead of a Python script, so the app can open it, change it and build it.

- Loader: `bountiful/songspec.py`
- Records: `records/*.toml`
- Test: `tests/test_songspec.py`

```
$PY -I bountiful/songspec.py records/moss-radio.toml              # build + checks (about 6 minutes)
$PY -I bountiful/songspec.py records/moss-radio.toml --dry        # compose + lint only, seconds
$PY -I bountiful/songspec.py records/moss-radio.toml --validate   # checks on an existing render
$PY -I bountiful/songspec.py records/moss-radio.toml --as "Moss Radio spec test"   # build to another tracks/ folder
```

The records so far (Moss Radio, Orange Mound Fog, Window Frost) are scripts, and most of each script is data. The rest is
a little performance code (rolled chords, comping, swing, the bass doubled on the sub) and the checks. Song Spec keeps the
data as TOML and turns the performance code into **players** with parameters. A template is then a `.toml` file, and
changing the key, tempo or instruments means editing fields.

Ports:

| Record | Status |
|---|---|
| Moss Radio | `records/moss-radio.toml`: same notes, chord chart and LT spec as the script (unit test) |
| Orange Mound Fog | next |
| Window Frost | last in Phase 1; it needs `bend`, `cc` and `pedal` events first |

## One file, top to bottom

```
[meta]          title, genre, skeleton, key, scale, bpm, swing, seed, humanize_seed, tracks (MIDI order), blurb, extends
[perform]       humanize ("legacy" | "per-track"), swing on/off, loop_from ("section" | "song")
[sounds]        allow = the libraries the record may use
[chords]        name = { root = "Db", intervals = [4, 7, 11, 14] }
[loops]         named chord loops, one list of chords per bar (two chords split the bar)
[voicing]       mode ("lead" | "near"), lo, hi, max_span, center, start
[parts]         written notes, per bar
[players.*]     how each track plays
[producer]      the loop and parts Bountiful's producer is given (only the drum grid uses them)
[[sections]]    name, bars, loop, drums, play, notes, ring, crash, fill
[drums]         humanize_ms, kit (sound per name), buses, grid
[voices.*]      the instrument for each track and its effect chain
[mix]           level_ref, targets, test_bars, sends, automation, mmp_drums
[master]        tape, target_lufs, true_peak
[validate]      length_s, lufs_tolerance
[[checks]]      typed checks on the render
```

### Conventions

- **Notes** are `[step16, pitch, len16, vel]` per bar, as in the scripts. An optional fifth field `"s"` ties into the next
  note (`tie_gap` instead of `gap`), for the 808 slides in Orange Mound. Pitches are MIDI numbers for now. Note names
  work for chord roots and the scale, and are planned for parts (hand-written templates will use them).
- **Bars by name.** Where a bar number is needed you can write `"@Break"`, `"@Break+3.5"` or `"@Last chord-1"`, so
  moving a section doesn't break the automation.
- **Sounds by library id, not by path.**
  - `gs:8:4`: GeneralUser GS, bank 8, patch 4.
  - `dm:r_n_b/old_kik`: the rendered drum machines.
  - `iowa:<name>` and `pixel:<name>`: the other sample libraries.
  - `own:vinyl-crackle-80`: sounds we generated ourselves.
  - `engine:<kind>`: an engine voice, written out in `[voices.x.engine]`.

  A library must be in `[sounds] allow`. Paths on disk aren't accepted.
- **Transforms** reuse a part. `{ part = "theme", bars = "3-4", shift = 12, vel = 0.85, rest = 2 }` takes bars 3-4 of
  the part, an octave up, at 85% velocity, after 2 silent bars. In a section, `for = n` stops a line after n bars, and
  `last = "part"` swaps in another bar on the section's last bar.
- **Templates extend.** `extends = "moss-radio"` in `[meta]` loads that record first, then merges this file over it.
  Tables merge key by key, and lists are replaced. A record made in the app is a small file of changes on a template.

## Players

Every player takes `track` (defaults to its own name), `jitter_ms` and `gap`.

| type | From | What it does |
|---|---|---|
| `chords` | Moss Radio keys and pad, Orange Mound choir | The section's chords. `hold` plays whole chords. `comp` plays the `even`/`odd` hit patterns. A bar with two chords plays `split`. `roll_ms` per note, `bottom_vel`, `drop_bottom`, `shift`. `voicing = "near"` gives an unled voicing in `near.lo`-`near.hi`. |
| `root` | Moss Radio sub in the break | The chord root, from `octave` up |
| `line` | guitar, flute, bass, riff, bell | A written part. Either `part`, or `loops = { A = ..., B = ... }` per section loop, or what the section names. `repeat = false` plays a part once instead of cycling it. |
| `follow` | Moss Radio sub | Repeats the notes of `follows` that last at least `min_len` steps, right after each one, at `shift` |
| `every` | Orange Mound tubular | `note` every `bars` bars at `offset`, in the sections that switch it on |

In a section, `play = { keys = "comp", bass = true, guitar = "theme", flute = { part = ... } }` turns players on. A
`chords` player takes a mode (`"hold"`/`"comp"`) or a table `{ mode, hold_vel }`. `notes = { track = [[bar 1 notes], ...] }`
adds one-off notes, such as the last chord. `ring = 2` lets held chords ring two steps past the section.

Within a bar, the chord players play first, chord by chord, in the order the file lists them. The section's notes come
next, then the line players (each followed by its followers). With `humanize = "legacy"` every jitter comes from one
random stream in that order, which is what the scripts did. The three ports use it. New records use one stream per track,
so adding a part doesn't move the others.

## The gotchas, as rules the loader applies

These cost a build each time. The loader checks them in seconds, before it renders:

| Gotcha | Rule |
|---|---|
| `glide = 0` renders NaN | glide is raised to 0.01, with a note in the log (done) |
| a track that is silent in `test_bars` gets no auto-trim | error before rendering, naming the track (done) |
| m11 and other rootless voicings with nothing under them | a warning, unless the section has `rootless_ok = true` (done) |
| a grid entry without a sound name uses the layer's name | error if the kit has no sound with that name (done) |
| a sound outside the allowed libraries | error (done). A cleared-only list per library comes with the Record tab. |
| unknown chord, loop or drum layer | error naming the section (done) |
| `targets` don't trim drum stems (hats needed +20 dB, perc +14) | planned: targets for drum buses, with `gain_db` set from the test render |
| dict grid patterns cycle by `bar % len(keys)` | planned: the Record tab shows which pattern each bar uses |

## Checks

`[[checks]]` entries, each with a `type` and an optional `name`. The loader always checks length, loudness, true peak,
clipping, mono lows and that every track is in the MIDI.

| type | Fields |
|---|---|
| `no_drums` | `in` (section), `except` (sounds) |
| `absent` | `track`, `in` (sections) |
| `in_harmony` | `tracks`, `max_outside`: pitches must be chord tones or in `meta.scale` |
| `on_chord` | `track`, `every_beats`, `window_beats`: notes on the strong beats are chord tones |
| `late` | `sound`, `ms = [lo, hi]`: median distance behind the grid |
| `stops` | `in` (sections), `after_beat`, `except`: no drums after that beat in the section's last bar |
| `louder` | `a`, `b`, `db`: RMS of section a over section b |
| `bands` | `in`, `a = [lo, hi]`, `b = [lo, hi]`, `db` |
| `band_drop` | `a`, `b`, `band`, `db`: the band is quieter per bar in section b |
| `count` | `track`, `min` |

## Proving the ports

A port counts as done when the Song Spec build of the record matches the script build:

1. The same MIDI notes (start, end, pitch and velocity, compared as lists), the same chord chart and the same spec for
   `lmms_tracks.make`. This runs in seconds: `tests/test_songspec.py`.
2. The audio: LUFS within 0.1 dB of the script build and the same `validation.md` result. LMMS may not render the same
   sample for sample, so a null test is only informative.

## Decisions (2026-11-18)

1. The three ports use `humanize = "legacy"`. New records get one random stream per track.
2. Window Frost stays a script for now and is the last port of Phase 1. There is one render backend (LMMS). The `bend`,
   `cc` and `pedal` events get added when it is ported.
3. The ports store note numbers, copied from the scripts. Hand-written templates will use note names.
