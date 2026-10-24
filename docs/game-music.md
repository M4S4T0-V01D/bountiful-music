# Game music

Bountiful turns part of a song into music a game can use. You get one seamless loop that can get more or less
intense as the game needs, separate layers for engines that mix their own, short stingers in the song's key, and
ready-made players for Godot and Unity. Everything is rendered locally by code. Nothing is downloaded.

## In the app

1. Open a track (from the **Start** page, the Library, or **Open a track …** on the tab).
2. In the **Game music** tab, pick the part to loop. The busiest section is marked "← busiest" and selected first.
   You can also type bars instead, e.g. `9-16` (at most 16 bars).
3. Press **Make game music**. A short loop takes about a minute.
4. **Try it like a game.** Press a state to start the loop, then switch states while it plays. Layers fade in and
   out over 1.5 s, as the game players do. Stinger buttons fire on the next beat or bar, also as in the game.
5. **Show folder** opens `<track>/game/`. Its README.txt also appears in the tab.

## What gets written

`<track>/game/`:

| File | What it is |
|---|---|
| `loop_calm.wav` … `loop_combat.wav` | The whole loop, mixed and mastered for each state. A loop point (RIFF `smpl` chunk) is written in, so Godot, FMOD, Wwise and most samplers loop it without a click |
| `layers/<layer>.wav` | The loop split into five layers, all the same length, for engines that mix layers themselves |
| `stingers/<name>.wav` | One-shots in the song's key and tempo |
| `manifest.json` | Tempo, bar and loop lengths in samples, each state's mix and level, each stinger's length and quantize |
| `README.txt` | The same information in plain words |
| `godot/BountifulMusic.gd` | A Godot 4 player node |
| `unity/BountifulMusic.cs` | A Unity MonoBehaviour |
| `*.ogg` (optional) | OGG Vorbis copies with `LOOPSTART`/`LOOPLENGTH` tags. Needs ffmpeg |

Sound that rings past the loop's end is folded back onto its start, so the loop seam is seamless.
A note pushed just ahead of the first bar moves to just ahead of the bar after the loop.

### Layers and states

| Layer | Holds |
|---|---|
| bed | pads, keys, chords |
| low | bass |
| beat | kick, hats, toms |
| drive | snare, claps, percussion, arps, cymbals |
| top | lead lines |

| State | For | Layers |
|---|---|---|
| calm | menus, safe rooms, exploring at rest | bed, low at 60% |
| explore | moving through the world | bed, low, beat at 80% |
| tense | danger is near, puzzles against the clock | bed, low, beat, drive |
| combat | fights and chases | all five |

Each state is mastered to its own level, and calm is quieter than combat. The manifest's `rms_db` records each
level, so a layer mixer can match the mastered files.

### Stingers

| Name | What | Waits for |
|---|---|---|
| victory | a rising fanfare that lands on the home chord | the next bar |
| game_over | a falling line that settles low | the next bar |
| pickup | a quick bright blip for coins, items, points | the next beat |
| alert | an urgent figure on the fifth: you have been spotted | the next beat |
| level_start | a short call to begin | the next bar |

## Using it in a game

**Godot 4.** Copy the `game` folder to `res://music/`. Add `godot/BountifulMusic.gd` to a node, then call
`set_state("combat")` and `stinger("pickup")`. The exported settings are `folder`, `start_state` and `fade_s`.

**Unity.** Copy the WAVs to `Assets/Resources/Music/<track>/` and add `BountifulMusic.cs` to a GameObject.
Then call `SetState("combat")` and `Stinger("pickup")`.

Both players crossfade the four state loops in sync and wait for the beat or bar before a stinger. They are
plain, short scripts, so you can read them before using them. They were written for these engines but have
not been run inside them. The in-app preview follows the same rules.

## Command line

```sh
$PY bountiful/gamemusic.py tracks/<slug> --list            # the sections and their energy
$PY bountiful/gamemusic.py tracks/<slug>                   # the busiest section
$PY bountiful/gamemusic.py tracks/<slug> --section 3       # or --bars 9-16
    [--no-stingers] [--ogg] [--out DIR]
```

## Limits

- Loops are at most 16 bars long.
- Stingers are at most a few seconds long.
- Every file peaks below −0.3 dBFS. The preview uses the same soft ceiling.
- Rendering is deterministic: the same track and bars give the same files.

## Tests

```sh
$PY tests/test_gamemusic.py                                       # loop wrap, layers, states, stingers, WAV loop points, MIDI loop shift
QT_QPA_PLATFORM=offscreen <daw venv>/python tests/test_app.py     # the in-app preview: glide, beat-quantized stingers
```
