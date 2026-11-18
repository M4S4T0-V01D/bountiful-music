# Song Spec (draft)

A record written as data instead of a Python script, so the app can open it, change it and build it.
Draft for review, 2026-11-18. Nothing reads this format yet.

The records so far (Moss Radio, Orange Mound Fog, Window Frost) are scripts. Most of each script is data:
chords, written parts, sections, a drum grid, a kit, voices and mix targets. The rest is a small amount of
performance code (rolled chords, comping, swing, the bass doubled to the sub) and checks. Song Spec keeps the
data as TOML and turns the performance code into named **players** with parameters. Then a template is a
`.toml` file, and "change the key / tempo / instruments" means editing fields.

## One file, top to bottom

```
[meta]        title, slug, genre, bpm, swing, key, year, blurb, seed
[sounds]      which library the record may use (only cleared sources, see docs/sample-audit.md)
[chords]      chord names -> root + intervals
[loops]       named chord loops, one entry per bar
[parts.*]     written notes, per bar
[players.*]   how each track plays: hold, comp, line, sub, slide808 ...
[[sections]]  the form: name, bars, loop, what plays, which drums
[drums]       grid patterns per layer, kit sounds, buses
[voices.*]    the instrument for each track, and its effect chain
[mix]         level reference, targets, test bars, sends, automation
[master]      tape, LUFS, true peak
[[checks]]    what validate() tests
```

### Conventions

- **Notes** are `[step16, pitch, len16, vel]` per bar, as in the scripts. An optional fifth field `"s"`
  slides into the next note (the 808 in Orange Mound). Pitches can be MIDI numbers or names (`"C4"`).
- **Bars by name.** Anywhere a bar number is needed you can write `"@Break"`, `"@Break+3.5"` or `"@end"`,
  so moving a section doesn't break the automation. (The scripts use `start_bar("Break")` for this.)
- **Sounds by library id, not by path:** `gs:8:4` (GeneralUser GS bank 8, patch 4), `iowa:flute`,
  `dm:r_n_b/old_kik` (the rendered drum machines), `own:vinyl-crackle-80`. The loader resolves them
  through `paths.py`. Paths on disk aren't allowed in a template, which keeps the ~/Documents paths
  out of templates, and the loader can refuse anything that isn't on the cleared list.
- **Transforms** reuse a part: `{ part = "theme", bars = "3-4", shift = 12, vel = 0.85 }`.
  Fields: `bars` (1-based range of the part), `shift` (semitones), `vel` (scale), `rest = 4`
  (that many silent bars first).
- **Templates extend.** `extends = "moss-radio"` in `[meta]` loads that record first and merges this
  file over it. A record made in the app is a small file of changes on top of a template.

## Players

The performance code in the scripts, as named players. Every one takes `jitter_ms` and `gap`.

| Player | From | What it does |
|---|---|---|
| `hold` | Moss Radio keys, Orange Mound choir | whole chords for each chord's length, voice-led |
| `comp` | Moss Radio keys | chord hits from a pattern per bar parity, rolled `roll_ms` per note |
| `line` | guitar, flute, riff, bell, bass | plays a written part, with transforms |
| `sub` | Moss Radio sub | doubles the bass notes of length >= `min_len` an octave down (or at `octave`) |
| `slide808` | Orange Mound boom | `line` plus slides on `"s"` notes, gap 0 when tied |
| `every` | Orange Mound tubular | one note every N bars at an offset |

Voicing is shared: `voicing = { lo = 50, hi = 70, max_span = 14 }` picks the closest voice-leading, as
`voice()` does now. Swing applies to odd steps, as now.

## Moss Radio as a Song Spec

Shortened where it repeats (`...`). The full file would be about 250 lines, against 417 for the script.

```toml
[meta]
title = "Moss Radio"
slug = "moss-radio"
genre = "lofi-downtempo"
bpm = 80
swing = 0.58
key = "F minor"
year = 2026
seed = 7            # producer seed
humanize_seed = 80  # timing and velocity jitter
blurb = "Lo-fi hip-hop at 80 bpm in F minor, ..."

[sounds]
allow = ["gs", "dm", "own"]        # iowa, pixel ... when a record needs them

[chords]
Dbmaj9 = { root = "Db", intervals = [4, 7, 11, 14] }
C7b9   = { root = "C",  intervals = [4, 7, 10, 13] }
Fm9    = { root = "F",  intervals = [3, 7, 10, 14] }
# ... Ebm9 Ab13 Bbm9 Eb13 Abmaj9 Gm7b5 C7sus

[loops]
A = [["Dbmaj9"], ["C7b9"], ["Fm9"], ["Ebm9", "Ab13"]]
B = [["Bbm9"], ["Eb13"], ["Abmaj9"], ["Dbmaj9"], ["Gm7b5"], ["C7b9"], ["Fm9"], ["C7sus", "C7b9"]]
END = [["Dbmaj9"]]
scale = ["F", "G", "Ab", "Bb", "C", "Db", "Eb"]

[parts]
theme = [
  [[2, 72, 2, 0.62], [4, 75, 2, 0.68], [6, 77, 5, 0.78], [12, 75, 2, 0.60], [14, 72, 2, 0.58]],
  [[0, 73, 6, 0.75], [8, 70, 2, 0.60], [10, 68, 2, 0.60], [12, 67, 4, 0.66]],
  # ... 8 bars
]
bridge = [ ... ]
bass_a = [ ... ]         # the two 4-bar variants as one 8-bar part
bass_b = [ ... ]

[players.keys]
type = "comp"
voicing = { lo = 50, hi = 70 }
roll_ms = 14
jitter_ms = 6
even = [[0, 9, 0.68], [10, 6, 0.52]]     # [step, len, vel] on bars 1, 3, 5 ...
odd  = [[0, 13, 0.68], [14, 2, 0.45]]

[players.bass]
type = "line"
loops = { A = "bass_a", B = "bass_b" }   # which part plays over which loop

[players.sub]
type = "sub"
follows = "bass"
min_len = 2

[players.guitar]
type = "line"
[players.flute]
type = "line"
[players.pad]
type = "hold"
follows = "keys"     # the keys' voicing, an octave up
shift = 12
vel = 0.42
jitter_ms = 0

[[sections]]
name = "Intro"
bars = 4
loop = "A"
play = { keys = "hold" }
drums = ["vinyl"]

[[sections]]
name = "Theme"
bars = 8
loop = "A"
play = { keys = "comp", bass = true, guitar = "theme" }
drums = ["vinyl", "kick", "snare", "clap", "ghost", "hat", "rim"]
crash = true

[[sections]]
name = "Break"
bars = 4
loop = "A"
play = { keys = "hold", sub = "hold", flute = { part = "theme", bars = "3-4", shift = 12, rest = 2 } }
drums = ["vinyl", "hat", "rim"]

[[sections]]
name = "Theme again"
bars = 8
loop = "A"
play = { keys = "comp", bass = true, guitar = "theme", pad = true,
         flute = { part = "theme", bars = "5-8", shift = 12, vel = 0.85, rest = 4 } }
drums = ["vinyl", "kick", "snare", "clap", "ghost", "hat", "rim"]
crash = true
fill = "drop"
# ... Beat, Bridge, Bridge flute, Outro, Last chord

[drums]
humanize_ms = 8

[drums.grid.kick]
a = [[0, 0.95], [7, 0.55], [10, 0.85]]
b = [[0, 0.95], [10, 0.85], [13, 0.5]]
# ... c d

[drums.grid.snare]
a = [[4, 0.9, "snare", 16], [12, 0.92, "snare", 20]]   # [step, vel, sound, late_ms]

[drums.grid.hat]
gen = { steps = "0-14", vel = { beat = 0.5, eighth = 0.36, other = 0.22 } }   # the generated patterns
# ... ghost rim shaker vinyl

[drums.kit]
kick   = { sound = "dm:r_n_b/old_kik", bus = "kick" }
snare  = { sound = "dm:acoustic/jazzsnr", bus = "snare" }
clap   = { sound = "dm:r_n_b/clapfilt", bus = "snare", gain_db = -6 }
swell  = { sound = "own:vinyl-crackle-80", bus = "vinyl" }
# ...

[drums.buses.kick]
hp = 30
mono = true
drive = 1.3
eq = [["peak", 60, 2.0, 1.0], ["peak", 350, -2.5, 1.2]]
crush = { bits = 12, rate = 26040, mix = 0.35 }
gain_db = -3.0
# ... snare hats perc vinyl

[voices.keys]
sound = "gs:8:4"
label = "Chorused Tine EP"
fx = { hp = 90, lp = 6500, crush = "dusty", drive = 1.15, width = 0.9, sends = { room = 0.22, plate = 0.08 } }

[voices.sub]
sound = "engine:sub"      # an engine instrument, not LMMS
preset = { glide = 0.01, sub_h2 = 0.1, drive = 1.1, release = 0.1 }
fx = { hp = 28, lp = 160, mono = true, duck = { depth = 0.3, release = 0.12 }, gain_db = -12.0 }
# ... guitar flute bass pad

[mix]
level_ref = "kick"
test_bars = ["@Theme again", "@Theme again+7"]
targets = { keys = -4, guitar = -5, flute = -8, bass = -3, sub = -9, pad = -15 }
sends.echo = { type = "delay", time_beats = 0.75, feedback = 0.35, tone = 2200, taps = 5 }

[[mix.automation]]
type = "lowpass"
tracks = ["keys", "flute", "hats", "perc"]
points = [["@Break", 18000], ["@Break+0.01", 1700], ["@Break+3.5", 2600], ["@Theme again", 18000]]

[master]
target_lufs = -14.0
true_peak = -1.0
tape = { drive = 1.4, bias = 0.07, bump_db = 1.2, hf_db = -2.0, lp_hz = 14000, hiss_db = -68, wow_ms = 0.18 }

# generic checks (length, LUFS, true peak, clipping, mono low end, parts present) always run
[[checks]]
type = "silent"
what = "drums"
in = "Intro"

[[checks]]
type = "in_harmony"
parts = ["guitar", "flute"]
max_outside = 2

[[checks]]
type = "bass_on_chord"
beats = "downbeats"

[[checks]]
type = "late"
sound = "snare"
ms = [10, 40]

[[checks]]
type = "louder"
a = "Theme again"
b = "Break"
db = 2
```

## The gotchas, as rules the loader applies

These cost a build each time. The loader handles them, so nobody has to remember them:

| Gotcha | Rule |
|---|---|
| `glide = 0` renders NaN | clamp glide to >= 0.01, with a note in the log |
| `targets` don't trim drum stems (hats needed +20 dB, perc +14) | drum buses can have targets too; the loader sets their `gain_db` from the test render |
| a track that is silent in `test_bars` gets no auto-trim | error before rendering, naming the track and the sections where it does play |
| m11 voicings drop the root | a warning when a voicing leaves out the root and no bass plays under it |
| a grid entry without a sound name uses the layer name | the loader fills the name in, and errors if the layer has no sound with that name |
| dict grid patterns cycle by `bar % len(keys)` | written out in the docs; the Record tab shows which pattern each bar uses |
| a sound outside the cleared library | error, unless the file is marked `private = true` (records of our own that never ship) |

## Proving the ports

A port counts as done when the Song Spec build of the record matches the script build:

1. The same MIDI notes (start, end, pitch and velocity, compared as lists) and the same `instruments.toml`.
2. Then the audio: LUFS within 0.1 dB and the same `validation.md` result. LMMS may not render sample for
   sample the same, so a null test is only informative.

Step 1 runs in seconds, so it is a unit test. Step 2 is a full build (about 6 minutes per record).

## Questions for you

1. **Humanize randomness.** The scripts draw every timing and velocity jitter from one random stream, in
   the order bar by bar, keys then bass then melody. To match step 1 exactly, the loader has to draw in
   that same order. The problem: in that mode, adding a flute line also changes the guitar's timing. I'd do
   both: `humanize = "legacy"` for the three ports, and one stream per track for everything new.
   (Recommended.)
2. **Window Frost.** It doesn't use the LMMS pipeline. It writes its own MIDI with pitch bends, CC and
   pedal, renders through fluidsynth plus the Iowa samples, and mixes in its own code (wind, fire,
   vinyl). There are two options. One is to make Song Spec support a second render backend. The other is to
   leave Window Frost as a script for now and port it after Moss Radio and Orange Mound, adding the `bend`,
   `cc` and `pedal` events to Song Spec at that point (any expressive part needs them anyway). I'd go with
   the second option: one backend, and Window Frost as the last port of Phase 1.
3. **Note names or numbers.** The app will show names. The file can store either one. I'd store numbers
   in the ports (copied straight from the scripts) and names in hand-written templates.
