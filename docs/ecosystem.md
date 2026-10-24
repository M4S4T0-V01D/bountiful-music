# The Bountiful ecosystem

Bountiful writes songs, plays them, judges them, breeds them, mixes them and remembers where each one came from.
All of it is code. There is no model and no network: every step is deterministic (same input, same seed, same
notes and the same sound), runs on the CPU, and works within hard limits on time and size. The Ollama hookup is gone.

`$PY` below is the engine's Python (3.11, numpy/scipy). The DAW runs in its own venv.

## The pieces

| Roadmap | Module | What it does |
|---|---|---|
| 01 Instrument Lab | `synthesis/` | The eleven experimental engines ([synthesis-lab.md](synthesis-lab.md)) |
| | `timbre.py` | Audio to instrument: fingerprints a sound, finds the nearest engine preset, refines its parameters, and keeps a timbre library |
| 02 Production Brain | `intent.py` | A brief in plain words becomes bounded controls; each control names the words it came from |
| | `operator_.py` | Plays the Electronium's knobs across a song from fixed rules plus the brief |
| | `network.py` | The parts listen to each other through typed, bounded edges (duck, answer, follow, thin, accent, swell) |
| | `studio.py` | The virtual record producer: renders passages, measures them, makes one bounded change at a time, keeps it only if the measurement improves, and saves a revertible version for every kept step |
| 03 Discovery | `features.py`, `laws.py` | Measures what a song is made of and holds it to musical laws, with evidence and the bars it points at |
| | `evaluators.py` | Six judges (composition, rhythm, arrangement, sound, production, and taste from your ratings) plus Pareto ranking |
| | `evolve.py` | Small, reversible, seeded changes (melody, rhythm, harmony, arrangement) and breeding |
| | `discover.py` | Writes hundreds of candidates, rejects any that break a law, ranks the rest, shows a few |
| 04 Studio | `daw/` | The PySide6 app: Arrange, Mixer, Song from a Bounty, Electronium live, Synthesis Lab, Observatory |
| | `live.py` | Live performance: the Electronium plays bar by bar while you turn knobs; every turn is recorded as a move |
| 05 Ecosystem | `lineage.py` | Each song's DNA (origin + list of changes), the family tree, export to a track folder |
| | `observatory.py` | The data behind the Observatory tab: ideas, ratings, producer changes, clocks, spectra, passage branching |

## A song's DNA

```json
{"v": 1, "origin": {"kind": "electronium", "bounty": "1969", "length": "normal", "reharm": 0.25, "brief": ""},
 "changes": [{"op": "reharmonize", "args": {"section": 1, "share": 0.35}, "seed": 812, "why": "harmony"}],
 "parent": "a3f09c12e1", "label": ""}
```

`lineage.grow(dna)` rebuilds the song from its DNA, note for note. Saved songs go into `<data>/lineage.jsonl`.
That file is append-only: a rating or a note adds a new line and never rewrites an old one.
`lineage.export(dna)` writes a track folder (MIDI, instruments.toml, dna.json, notes.txt) that the renderer and
the DAW can open.

## Command lines

```sh
$PY bountiful/laws.py --bounty 1969                      # the laws, with evidence
$PY bountiful/evaluators.py --bounty 1969                # six judges and their reasons
$PY bountiful/discover.py --bounty 1969 --n 200 --keep 5 --save   # breed, reject, rank, keep a shortlist
$PY bountiful/studio.py tracks/<track> --rounds 3        # the producer, on a rendered track
$PY bountiful/studio.py tracks/<track> --revert 2        # put kept version 2 back
$PY bountiful/timbre.py hit.wav --save "glass hit"       # find the instrument behind a sound and keep it
$PY bountiful/live.py --bounty 1969 --bars 16 --wav take.wav
```

## The Observatory tab

- **Clocks** (top strip): one column per bar. It shows sections, chords, the energy line, lead activity and phrase
  lines, with a third-octave heat map of the rendered mix (the master, or else the preview) underneath. Click a bar
  to choose the passage you want to branch.
- **Ideas**: the discovery machine's last shortlist plus every saved song. You can rate any of them (out of 5) or
  open one as a track.
- **Producer**: every change the virtual producer tried on this track, whether it was kept or refused, with the
  score before and after and the reason.
- **Branch a passage**: children of the song that differ only in the 4 chosen bars (plus the one beat leading into
  them). A child is rejected if no change took, if it changed anything outside the passage, or if it breaks a law
  or falls under the score floor. The rest are ranked by Pareto front and total. You can keep a child in the family
  tree or open it as a track. Branching only works for tracks that have DNA (made by `lineage.export` or from an
  Electronium song).
- **Ratings & spectrum**: your star ratings and the judged totals over time, next to the mix's average spectrum.

## Limits

- Discovery and branching: at most `MAX_BRANCHES` (48) children per passage.
- Spectra: at most 30 s for the average, and at most 512 bars for the heat map.
- Producer changes: each one has a fixed range, and every round renders short passages, not the whole song.
- Network edges: fixed caps (duck depth at most 0.5, for example).
- Old songs, presets and configs load as before. Songs without DNA open normally; only branching is unavailable.

## Tests

```sh
$PY tests/test_ecosystem.py          # laws, judges, evolution, DNA, discovery, network, producer, timbre, observatory
QT_QPA_PLATFORM=offscreen <daw venv>/python bountiful/daw/main.py --smoke
```

## Not done yet

- Hardware control and MIDI clock sync.
- CLAP/LV2 plugin hosting.
- A full DAW editor beyond the piano roll and mixer.
- Community features (sharing, voting).
