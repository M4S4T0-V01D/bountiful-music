# Sample audit

What each sound source is, and whether a build that is given or sold to other people may ship it.
This is a working list, not legal advice. Audited 2026-11-18.

| Source | Size | Origin | Ship it? |
|---|---|---|---|
| `samples/sf2/GeneralUser-GS.sf2` | 31 MB | GeneralUser GS v2.0.3, licence in `samples/sf2/LICENSE.txt` | **Yes.** Free to use and redistribute in software, music made with it can be sold. The author says some samples came from other free banks of unknown origin, so keep the licence file next to it |
| `samples/iowa/` | 2.2 GB | University of Iowa Musical Instrument Samples, "free to use in any project" (`samples/iowa/README.md`) | **Yes.** Ship the cut notes (`alto/ trumpet/ vibes/ flute/ piano/`), not `raw/` (1.5 GB), and credit the University of Iowa EMS |
| `samples/drummachines/` | 5 MB | Rendered from LMMS's DrumSynth `.ds` patches (`bountiful/drum_machines.py`) | **Yes**, they are synthesised from patch data that ships with LMMS (GPL-2). Credit LMMS |
| `samples/pixel/` | 5 MB | Synthesised by `bountiful/pixel_kits.py` | **Yes**, our own |
| `samples/breaks/clizzy/` | 38 MB | The C-Lizzy break: our own performance on LMMS sounds (`samples/breaks/clizzy/README.md`) | **Yes**, our own |
| `samples/breaks/haze174/` | 7 MB | The synthetic break (`jungle174.py --synthetic-break`) | **Yes**, our own |
| `samples/breaks/velvet162/` | 0.5 MB | Generated hat takes for `jungle_soul.py` | **Yes**, our own |
| `samples/lofi/`, `samples/phonk/` | 3.5 MB | Generated vinyl crackle, tuned 808 cowbell | **Yes**, our own |
| `breaks/` (not in git) | 7.5 MB | `break.mp3` is the Amen (The Winstons, 1969). `break2`-`break7` are downloaded breaks of unknown origin (2018-2020) | **No** |
| `samples/breaks/haze*-real/`, `handshake160/`, `undertow140/`, `undertow145/` | 140 MB | Slices of the `breaks/` files | **No**, derived from the above |
| `samples/osrs/` | 203 MB | Castle Wars by Ian Taylor / Jagex | **No**, not cleared (fan remix only) |

## Tracks that depend on sounds that can't ship

`jungle174.py` (Haze Theory), `night_signal.py`, `tidewater.py` (Tide), `undertow.py`, `handshake.py` and
`ramparts.py` use the `breaks/` files. `ramparts.py` also uses Castle Wars. These can be released as M4S4T0
records, but cannot be shipped as templates. Their templates need the C-Lizzy break, the synthetic break,
or new breaks of our own.

Moss Radio, Orange Mound Fog, Window Frost, Sonora at Midnight and the Electronium and pixel tracks use only
shippable sounds.

## Still to check before Phase 3

- The LMMS ZynAddSubFX presets the renderer uses (`/usr/share/lmms/presets/ZynAddSubFX/`) are GPL and come
  with LMMS. If the renderer ships LMMS, they come with it. If it doesn't, those voices need replacing.
- A shippable library would be roughly 700 MB (Iowa notes + GeneralUser GS + own kits). Consider FLAC for the Iowa notes.
