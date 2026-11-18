# Bountiful Music: agent guide

How to make a finished, mastered track with this program from a coding agent: what to run, what a track script contains,
how the breaks, bass and master work, and what goes wrong. The user-facing app is described in `../README.md`; this file
is about building tracks from scripts. The worked examples are `bountiful/jungle174.py` ("Haze Theory") and
`bountiful/night_signal.py` ("Night Signal"), atmospheric jungle tracks at 150 and 138 bpm on the two real breaks in `breaks/`,
and `bountiful/tidewater.py` ("Tidewater", 136 bpm, F minor), which uses all three breaks and imports Night Signal's edits.

## 1. Running things

Always run from the project folder (`~/Documents/Projects/bountiful-music`) with the intelligent-jungle venv, in
isolated mode:

```sh
PY=~/Documents/Projects/intelligent-jungle/.venv/bin/python
$PY -I bountiful/night_signal.py                    # sample the breaks (if needed), compose, render, master, validate
$PY -I bountiful/night_signal.py --validate         # the checks only, on the last render
$PY -I bountiful/jungle174.py --synthetic-break     # a performed synthetic break instead of breaks/break.mp3
```

- `-I` drops the script's folder from `sys.path`. Every track script must therefore add its own folder before
  importing siblings: `sys.path.insert(0, str(Path(__file__).resolve().parent))`, then `import jungle174 as J`,
  `import lmms_tracks as LT` and so on. Without that line you get `ModuleNotFoundError`.
- A full build takes about 6 minutes, most of it the LMMS/Zyn render. Run it in the background and keep the log:
  `$PY -I bountiful/x.py > /tmp/x.log 2>&1; echo "EXIT $?" >> /tmp/x.log`.
- Read the log with a grep rather than in full: `grep -E "checks pass|FAIL|checks:|Master:|EXIT|rror" /tmp/x.log`.
- Before you rebuild a track you want to keep, move the old render aside: `mv tracks/<slug> tracks/_archive-<slug>-v<N>`.

## 2. Layout

| Path | What it is |
|---|---|
| `bountiful/<track>.py` | a track script: SPEC, arrangement, drum programs, `validate()` |
| `bountiful/lmms_tracks.py` | `make(SPEC)`: produce the MIDI, set up instruments, run a test render, trim, run the full render, write the README and .mmp |
| `bountiful/build.py` | the producer: loops, `arrange()`, `rank()`, transposition, `loop_continuous` |
| `bountiful/producer.py`, `melodist.py`, `harmony`… | composition: harmony colours, melody, bass and comp generators |
| `bountiful/break_maker.py` | break analysis helpers (onsets, slicing) |
| `genres/` | genre defaults that SPEC `overrides` deep-merge into (e.g. `atmospheric-jungle-95`) |
| `songs/<set>/` | skeleton songs (`*.am.json`) and `ranking.json` |
| `breaks/` | the user's source breaks: `break.mp3` (the Amen, ~137 bpm), `break2.wav` (~114 bpm), `break3.wav` (the cowbell break, ~108 bpm) |
| `samples/breaks/haze<bpm>-real/` | the sampled, sped-up, grid-laid takes and slices (written by `J.build_break()`), one folder per tempo |
| `tracks/<slug>/` | output: `<slug>.mid`, `exports/<slug>.wav` + `.mp3`, `exports/render_info.json`, `stems/*.wav`, `<slug>.mmp`, `instruments.toml`, `notes.txt`, `README.md`, `validation.md` |
| `~/Documents/Projects/intelligent-jungle/studio/render_midi.py` | the renderer: LMMS Zyn voices, engine instruments, sends, automation, mix |
| `~/Documents/Projects/intelligent-jungle/engine/render.py` | `master()`: the mastering chain |
| `/usr/share/lmms/presets/ZynAddSubFX/` | the Zyn banks voices point at |

## 3. The pipeline

1. **Skeleton.** `SPEC["song"]` is a skeleton `.am.json`, which supplies the chord progressions for the chorus (loop A),
   verse (V) and bridge (B). Pick one from `songs/<set>/ranking.json`: entries list the seed and each section's chords,
   ranked by `build.py rank()`. Choose chords that suit the mood, then move the key with a per-block `transpose`
   (Night Signal: an A-minor skeleton, `transpose=-2`, so G minor).
2. **Producer.** `B.produce` merges the genre with `SPEC["overrides"]`, generates the harmony, melody, bass, comp, vox and
   pad parts for each loop, lays them out by `overrides["arrangement"]`, writes the drums from `overrides["grid"]` and
   writes `<slug>.mid`.
3. **Instruments.** `voices`, `extra_tracks`, `sends`, `automation` and `kit_def` go into `instruments.toml`.
4. **Test render** of `test_bars`. Each LMMS part that sounds an octave off is moved, then each part is trimmed to its
   `targets` dB against the `level_ref` stem (`"break"` for the jungle tracks).
5. **Full render** to stems, mix, then `master()`; analysis goes to `exports/render_info.json`.
6. **`validate()`** (in the track script) measures the result and writes `tracks/<slug>/validation.md`. It is not part
   of `make()`: call it after `LT.make(SPEC)` in `__main__`.

## 4. A track script

The quickest correct route is to copy `night_signal.py` and change the music. It imports Haze Theory's break pipeline and
layer programs rather than duplicating them:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jungle174 as J
LT, PR, ROOT, BPM = J.LT, J.PR, J.ROOT, J.BPM
base, swap, zb, head, vary, blk, groove = J.base, J.swap, J.zb, J.head, J.vary, J.blk, J.groove
PROGRAMS = {**J.PROGRAMS, "N": N, "H": H, ...}       # shared layers + this track's own edits and fills
SPEC = {"title": ..., "song": SONG, "genre": "atmospheric-jungle-95", "rebuild": "bountiful/<file>.py",
        "overrides": {...}, "kit_def": J.kit(), "voices": {...}, "extra_tracks": {...}, ...}
if __name__ == "__main__":
    if "--validate" not in sys.argv:
        J.build_break()          # samples both breaks into samples/breaks/haze150-real
        LT.make(SPEC, log=lambda m: print(m, flush=True))
    validate()
```

The slug comes from the title (`"Night Signal"` becomes `tracks/night-signal`).

### SPEC top-level keys

| Key | Meaning |
|---|---|
| `title`, `song`, `genre`, `seed` | name, skeleton, genre defaults, composition seed |
| `rebuild`, `blurb`, `composer`, `album`, `year` | text for the track README / metadata (the artist is always stamped M4S4T0) |
| `overrides` | deep-merged over the genre (below) |
| `kit_def` | the drum kit (`J.kit()`: every break slice, take and one-shot, with chokes) |
| `layers` | doubled parts, e.g. `[("bass", "bass_mid")]` copies the bass notes onto a `bass_mid` track |
| `voices` | `name: (source, label, process)` for LMMS parts |
| `extra_tracks` | engine (non-LMMS) instruments, e.g. the sub-bass |
| `sends` | send effects: `slap`/`echo` (`type: delay`, `time_beats`, `feedback`, `taps`, `tone`), `plate` (`type: reverb`, `seconds`, `predelay`, `damp`) |
| `targets`, `level_ref`, `test_bars` | auto-trim: dB of each part relative to `level_ref`, measured over bars `(a, b)` |
| `automation` | `[{"type": "lowpass"/"highpass"/"gain"/"pan", "tracks": [...], "points": [[bar, value], ...]}]`; `tracks` can name drum stems (`break`, `break2`, `breakfx`, `ride`, `kick`, `snlay`) |
| `mmp_drums`, `kick_gain`, `drum_stems` | the .mmp export and drum stem gains (jungle scripts: `False, None, {}`) |

### `overrides` keys

| Key | Meaning |
|---|---|
| `bpm`, `swing` | tempo; `swing: 0.5` is straight |
| `drums: "grid"`, `grid` | drums come from step programs (section 5) |
| `arrangement` | the list of blocks (section 6) |
| `drum_cycle_per_block` | a program's bars `a`..`d` cycle from the start of each block |
| `loop_continuous` | consecutive blocks on the same loop carry on through its chords instead of restarting |
| `harmony` | `rhythm` (chords per bar), `dominant`, `tonic_major`, `colors` (chord quality → voicing, e.g. `"m": "m9"`) |
| `melody` | `modal`, `register [lo, hi]`, `max_leap`, `max_notes_per_bar`, `articulation`, `humanize_ms`, `velocity` |
| `bass`, `bass2` | `style: "pattern"`, `register`, `patterns` (section 7) |
| `comp`, `vox`, `pad` | chord parts: `steps` (16ths the chord hits on), `low`/`high`/`top` voicing range, `notes`, `gate`, `strum_ms`, `vel`, `accent` |
| `master` | the mastering chain (section 9) |

## 5. Breaks and drum programs

### How the breaks are sampled

`J.build_break()` runs `sample_break` on both files. It fits the tempo and downbeats from the onsets (the Amen fits
137.05 bpm, break 2 113.85), speeds up by one constant ratio to the track tempo, 150 by default (pitching up as a sampler would: x1.090 and x1.315),
crushes to 12-bit at 26 kHz, then re-lays every source 16th exactly on the grid as one continuous take. Each 16th
crossfades onto its step 220 samples (5 ms) early, in the tail of the hit before. Slices are cut on the grid with the
same 5 ms lead, which is also the kit's `preroll_ms`. As a result, slices played in order reproduce the take with no
seam, and any edit crossfades instead of clicking. Each slice rings until the next strong hit and chokes the one
before (choke groups `brk` for the Amen and `brk2` for break 2). This is why the chops flow. Do not cut slices at
onsets, and do not remove the preroll or the choke.

### Sound names (the kit)

| Names | What |
|---|---|
| `s00`..`s63` | Amen 16th slices, 4 bars x 16 (`s{16*bar+step}`) |
| `t04`, `t12`… | Amen 32nd slices (the second half of a 16th) for pickups/rolls |
| `h00`..`h15` | the high-passed hats-only take of the Amen |
| `rd0`..`rd3` | Amen ride/top loop bars (one per bar, under the chops) |
| `kick1`, `snr1`, `gh1` | one-shots cut from the Amen take |
| `s04u`, `s12d`, `s09u`, `s07d`, `s12u`, `z04u` | pitched slices (`PITCHED`: source, semitones), on the `breakfx` stem |
| `z00`..`z63`, `zt04`, `zt12` | break 2 slices and 32nds |
| `rz0`..`rz3`, `zk1`, `zs1` | break 2 ride loop and kick/snare one-shots |
| `c00`..`c63` | break 3 (the cowbell break) slices, stem `break3`, choke group `brk3` |
| `kreinf`, `snlay` | kick reinforcement and snare layer (own stems) |

### Programs

A program is a dict of bars `"a"`..`"d"`, each a list of `[step, velocity, sound]` or `[step, velocity, sound, cents]`.
Steps are 16ths (0..15); `x.5` is a 32nd. Helpers in `jungle174.py`:

- `base(b)`: Amen bar `b` as written (`s{16b+i}` on every step). `zb(b, steps, vel)` does the same for break 2.
- `swap(bar, step, entry)`: replace one step. `head(b, upto)`: the bar up to a step, for fills that break off.
- `vary(f)`: an outing of fill `f` with slices swapped (`VARY`), so a fill can come back without repeating exactly.
- Shared layer programs in `J.PROGRAMS`: `hats`, `hatsq` (quiet hats), `ride`, `rz`, `kr`/`kr2` (kick reinforcement),
  `sl`/`sl2` (snare layer), `TL` (break 2 quietly under the Amen), `T`, `T2` (break 2 leading), `A`, `A2`, `B`, `C`.

The main beats are edits of the real bars (a kick moved, a snare doubled, a ghost added, a 32nd pickup, a gap), not
patterns programmed from scratch. Fills are one-bar programs that use rolls, gaps, pitched slices and the 32nds.

## 6. Arrangement

```python
blk(name, loop, bars, parts, drums, vel=..., loop_restart=..., transpose=...)
groove(name, loop, parts, breaks, fills, extra=("kr", "sl", "ride"), restart=False)
```

- `loop` is `"A"` (chorus), `"V"` (verse) or `"B"` (bridge). `parts` lists the playing tracks (`pad`, `bass`, `bass2`,
  `lead`, `lead_hi`, `comp`, `vox`). `drums` lists program names, all layered.
- `transpose` moves the parts, not the drums.
- `groove(...)` expands into 8-bar units: 7 bars of `breaks + extra` followed by a fill bar, one block per fill.
  **Fill bars drop the `kr`/`sl`/`kr2`/`sl2` layers** so the fill speaks alone.
- Structure that works for this style (Night Signal, 168 bars): 8 bars of pads/choir alone, break 2 under a filter,
  the Amen arriving, a main groove, a long breakdown (loop B, lower velocity, quiet hats), a filtered reintroduction,
  the drop, a half-time passage, a final groove, an outro and 8 DJ-friendly bars of beat only. Change the drum program
  every 8 bars, never reuse a fill bar exactly, and put a single-bar subtraction (everything but the pad) before a drop.
- Tidewater adds:
  - A break rising out of a filter. Automation is applied per drum stem: `{"type": "lowpass", "tracks": ["break3"], ...}`.
  - An "exchange" edit, where each bar is built from pieces of different breaks (`mix(("c", 0, 0, 8), ("s", 0, 8, 16))`).
  - Half time on break 2 (`zhalf`).
  - Section bars worked out from the block names (`at("Exchange")`), so the checks follow edits to the arrangement.

## 7. Bass

The bass is two engine instruments in `extra_tracks`, built from `J.SUB`, not a Zyn patch:

- a `bass` layer: a near-pure sine sub (`sub`, `sub_h2` for a touch of second harmonic, `body`, `drive`, `glide`);
- an `analogbass` layer: saw/square through a decaying low-pass (`cutoff`, `env_amount`, `filter_decay`, `resonance`).
  This layer supplies the movement and the "alive" quality. Copy with `copy.deepcopy(J.SUB)` and tweak it per track.

The overall bus: `hp`, `eq`, `lp`, `drive`, `mono`, plus `duck` (sidechain from the kick/snare:
`{"depth", "release"}`) and `gain_db`.

Notes come from `overrides["bass"]` with `style: "pattern"`. `patterns` is a cycle with one list per bar; each note is
`[step, degree, beats, velocity]`, where the degree is `R` (root), `O` (octave), `5`, `3` or `7` of the current chord.
Keep it to chord tones (validation wants at least 90%), use a four-bar cycle with octave jumps and a busier
turnaround, and set `register` so the root sits around E1–A1. `bass2` is a sparser cycle for intros and breakdowns.
`layers: [("bass", "bass_mid")]` adds a Zyn upper-bass texture (high-passed around 180 Hz, low-passed around 1.4k) so
the bass reads on small speakers.

### The 808 (trap, Memphis, phonk)

`bountiful/tr808_voice.py` is a tuned TR-808 bass drum played as a bass: a sine with a pitch punch on fresh hits, a long
decay, slides, and saturation high-passed so it adds harmonics without muddying the sub. Use it as a `pyvoice` extra track
(knobs are listed in its docstring; `label` names it in the README):

```python
"extra_tracks": {"boom": {"kind": "pyvoice", "glide_gap": 0.04, "hp": 25, "lp": 4000, "mono": True, "gain_db": 0.0,
                          "preset": {"module": str(VOICE808), "fn": "note", "label": "Tuned TR-808 ...", "decay": 1.4}}}
```

A note slides when it starts within `glide_gap` s of the previous note's end, so end tied notes exactly on the next start
and leave a clear gap (about 0.08 beats) before a fresh hit. A repeated pitch must not slide, or it loses its attack.
Write the kick grid from the 808's fresh hits, keep the kick short (`hp` about 45 Hz) so the 808 carries the low end,
and target the 808 a few dB over the kick. `orange_mound.py` is the worked example: 70 bpm Memphis phonk with composed MIDI
(the Moss Radio pattern), a pitched 808 cowbell lead, and verses kept clear for a rapper.

## 8. Voices and levels

```python
"pad": ({"zyn": "Strings/0014-Strings Pad5.xiz"}, "Strings Pad5 (ZynAddSubFX - Strings), slow pad",
        dict(hp=150, width=0.6, crush=J.SAMPLER(32000, 0.5), sends={"plate": 0.45}, gain_db=-8.0)),
```

- `source`: `{"zyn": "<Bank>/<file>.xiz"}` relative to `/usr/share/lmms/presets/ZynAddSubFX`. Run `ls` on the bank
  to check the file exists before using it.
- process keys: `hp`, `lp`, `eq` (`[["peak", hz, db, q], ["highshelf", hz, db], ...]`), `width` (Zyn pads are very
  wide, so 0.6–0.8 keeps mono compatibility), `crush` (`J.SAMPLER(rate, mix)` gives 12-bit sampler grit), `sends`,
  `duck`, `mono`, `gain_db`, `transpose`.
- `targets` sets each part's level in dB relative to `level_ref` over `test_bars`. Choose test bars where every
  targeted part plays (normally the drop). A part silent there, such as `bass2`, is not trimmed: give it a fixed
  `gain_db`. `lead_hi` follows `lead` at -10 dB unless `lead_hi_follows_lead: False`.

## 9. Master

`overrides["master"] = {**LT.B.MASTER, ...}`. These are the keys, in signal order:

| Key | Haze/Night setting | Purpose |
|---|---|---|
| `hp`, `mono_below` | 25, 120 | rumble cut; the lows in mono |
| `tape` | `drive 1.6–1.7, bias 0.07, bump_db 1.5, hf_db -1..-1.5, lp_hz 16.5–17k, hiss_db -74, wow_ms 0.06` | the warmth: head bump, even harmonics, rounded top, hiss, wow |
| `eq` | low-mid body +1 @180, -0.8 @400, +1 @1.5k, -0.8..-1.2 @5k | fill the hollow mids, ease the hats |
| `multiband` | `freqs [150, 5000]`, three bands at `threshold_rel -3`, ratios 2.5 / 1.6 / 1.8 | a couple of dB on the loud passages |
| `bus_comp` | `threshold_rel -3, ratio 2, attack 0.03, release 0.2, sc_hp 100` | glue; the sidechain ignores the sub |
| `glue` | `{}` | the old glue stage, off (use `bus_comp` instead) |
| `target_lufs`, `ceiling`, `clip`, `true_peak` | -9.6, -1.0, 1.5, -1.0 | loudness, soft clip on drum peaks, true-peak limit |

## 10. Validation

Each track script's `validate()` reads the MIDI, stems and master and prints `PASS`/`FAIL` per check, then
`N/N checks pass`, and writes `tracks/<slug>/validation.md` with a per-section level table. Night Signal checks:

- the bar count;
- an intro without drums;
- at least 15 distinct drum bars, no repeated fill, and no repeated 8-bar block;
- the subtraction bar;
- the key (at most 2% of notes outside it);
- slice usage (pitched slices, 32nds, both breaks layered, and break 2 alone);
- the half-time snare;
- bass on chord tones and octave moves;
- the drop at least 2.5 LU louder than the breakdown;
- true peak and clipping;
- correlation below 120 Hz above 0.95.

When writing new checks, measure what a listener would notice, and read `render_info.json` for `analysis`
(`integrated_lufs`, `true_peak_dbtp_approx`) and `stem_scale` (stems are written scaled: divide by it).

## 11. Pitfalls

- **`-I` and imports.** Use the `sys.path.insert` line (section 1).
- **Degree `5-`** (the fifth below) falls under the bass register and gets folded strangely. Use `5`, `O` and `R`.
- **Chord colours vs. voice count.** If a chord has more tones than the pad/comp `notes`, `producer.voicings` drops its root. A bass playing roots
  then fails the "bass notes are chord tones" check. Night Signal hit this with m11 (6 tones) on its 5-voice pad. Keep colours at
  most as wide as the voicing, or raise `notes`.
- **Check windows.** End a measurement window about 10 ms before the next bar, or the next section's downbeat leaks in.
- **Breakdown contrast.** If drop − breakdown is under 2.5 LU, lower the breakdown's drum velocity (`vel=`) and use
  `hatsq` instead of `hats`. Making the drop louder does not help, because the limiter levels it.
- **Fill bars drop the layer programs.** A fill that needs a kick reinforcement must contain it itself.
- **Untrimmed parts.** Anything not playing in `test_bars` keeps its `gain_db`.
- **Zyn pads are wide.** Without `width` they break mono compatibility and the low-end correlation check.
- **Filtered intros.** To filter a drum stem in automation, name the stem (`break2`, `ride`), not `drums`. A `ride`
  stem carries both `rd*` and `rz*`.
- **More than 108 kit sounds.** The kit maps sounds to notes `20 + index`, so jungle174's 236 sounds run to note 255,
  past MIDI's 127. `build.write_midi` writes a drum note n > 127 on channel `DRUM_HI_CH` (15) as n − 128. The kit map
  keys those sounds `"15:<note>"` (`J.key_of`), and render_midi looks that key up first. In a validator, decode a
  `read_midi` note with `J.sound_of(note)`, never with a pitch → name dict. Before this fix, every sound from `z08` on
  played as `z08`. Night Signal's `as_was` reproduces that stutter on purpose in bars 9–12. Note 255 is the
  limit: a further sound needs a second extra channel in `write_midi`, `key_of` and render_midi.
- **Tempo.** The break tempo is `J.BPM`, read from `BOUNTIFUL_BREAK_BPM` when `jungle174` is imported (default 150). Set it before the
  import, as `night_signal.py` does with 138; each tempo gets its own sample folder.
- **Long renders.** Do not run two builds at the same tempo at once: they share the sample folder `samples/breaks/haze<bpm>-real/`.
- **`find /`** is too slow. The Zyn presets live in `/usr/share/lmms/presets/ZynAddSubFX`.
