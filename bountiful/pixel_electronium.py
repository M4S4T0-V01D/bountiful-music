#!/usr/bin/env python3
"""'Clockwork Copper' (M4S4T0, composed by C-Lizzy): a pixel-tracker tune in the family of 'Put on the Pixel', with the
Electronium (electronium.py) at the controls. Slow jazzy drum & bass at 130, Bb major, on a punchy NES kit.

The grid plays the drum & bass backbone (two-step kick, backbeat snare, fills); the Electronium plays everything else, the
way Scott's machine did: five of its channels at once, each on its own tone generator (electronium_voice.py), and the
rest of the kit from its clock matrix (ghosts, hats, rim, toms, ride).
  lead      melody: before playing it thinks of 200 two-bar ideas and keeps the critic's best three as the song's themes
  sidekick  harmony, a third below the lead
  bass      the bassline sequencer on the two-step preset (p5): roots on the changes, fifths, octaves, walk-ups
  arp       a 5-cell ostinato over 8ths, phasing against the bar; the shift register rewrites a cell now and then
  counter   a slow reed line in contrary motion, in the verses and the break
The recorder plays the operator's moves back: the ostinato fades in, the lead switches gate presets for the verse, the
break mutates, the power-down thins everything out. Freezes: the last 8 notes become a climbing loop for the second
theme, the LFSR chews a 16-note loop in the break. Same Bounty, same tune.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/pixel_electronium.py [--bounty WORD_OR_NUMBER]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pixel_songs as S  # noqa: E402

blk, groove, at, zyn, xpf = S.blk, S.groove, S.at, S.zyn, S.xpf
SLUG, TITLE, SEED, BPM = "clockwork-copper", "Clockwork Copper", 791569278, 130

G = {"kick": {"a": [[0, 1.0], [10, 0.92]], "b": [[0, 1.0], [10, 0.9], [13, 0.6]], "c": [[0, 1.0], [7, 0.62], [10, 0.92]], "d": [[0, 1.0], [10, 0.9], [11, 0.66]]},
     "snare": [[4, 1.0], [12, 1.0]],
     "halfkick": [[0, 1.0], [11, 0.6]], "halfsnare": [[8, 1.0]],
     "C1": [[0, 1.0, "kick"], [4, 1.0, "snare"], [10, 0.9, "kick"]] + [[12 + i / 2, 0.45 + 0.07 * i, "tom_" + ("hi", "hi", "mid", "mid", "lo", "lo", "lo", "lo")[i]] for i in range(8)],
     "C2": [[0, 1.0, "kick"], [4, 1.0, "snare"], [7, 0.4, "ghost"], [10, 0.9, "kick"], [12, 1.0, "snare"], [13, 0.7, "snare"], [14, 0.85, "snare"], [15, 0.95, "snare"]],
     "C3": [[0, 1.0, "kick"], [3, 0.8, "tom_hi"], [4, 1.0, "snare"], [6, 0.8, "tom_mid"], [9, 0.85, "tom_lo"], [10, 0.9, "kick"], [12, 1.0, "snare"]] + [[14 + i / 2, 0.5 + 0.1 * i, "snare"] for i in range(4)]}

# the Electronium's drum layers: each a gate over the clock matrix, playing a chip-kit sound (the grid leaves them alone)
EL_DRUMS = {"el_hat": {"gate": "c2 | (r3 & ~c4)", "sound": "hat", "vel": 0.5, "density": 0.8},
            "el_ghost": {"gate": "(r3 & ~c4) | (r7 & c2 & ~c8)", "sound": "ghost", "vel": 0.3, "density": 0.55},
            "el_open": {"gate": "c8+6 & ~r5", "sound": "open", "vel": 0.36, "density": 0.6},
            "el_rim": {"gate": "r5 & ~c2", "sound": "rim", "vel": 0.42, "density": 0.5},
            "el_tomhi": {"gate": "r7 & r3", "sound": "tom_hi", "vel": 0.46, "density": 0.45},
            "el_tomlo": {"gate": "r11 & ~c4", "sound": "tom_lo", "vel": 0.5, "density": 0.4},
            "el_ride": {"gate": "c2 & ~c8+4 | (r3 & c4)", "sound": "ride", "vel": 0.42, "density": 0.85}}
TWO = ["kick", "snare", "el_hat", "el_ghost"]
FULL = TWO + ["el_open", "el_rim"]
TOMS = ["el_tomhi", "el_tomlo"]
BASS = ["bass"]

ARR = ([blk("Boot: the clocks start", "A", 4, ["arp"], ["el_hat"]), blk("Boot: rim and toms", "A", 4, ["arp", "pad"], ["el_hat", "el_rim", *TOMS])]
       + groove("Clockwork", "A", ["arp", "pad", "comp", *BASS], FULL, ["C1"], ["el_hat"])
       + groove("The machine sings", "A", ["lead", "sidekick", "arp", "pad", *BASS], FULL, ["C2", "C3"], ["el_hat"], crash=True)
       + groove("Ride the clock", "V", ["lead", "sidekick", "counter", "comp", "pad", "choir", *BASS], TWO + ["el_ride", "el_rim"], ["C1", "C3"], ["el_ride"])
       + [blk("Half-time: the register mutates", "B", 8, ["lead", "pad", "choir", "comp", "bass"], ["halfkick", "halfsnare", "el_ride", *TOMS], activity=0.8),
          blk("Half-time: sidekick alone", "B", 7, ["sidekick", "counter", "pad", "choir", "arp"], ["el_hat", "el_rim"]),
          blk("Half-time: pickup", "B", 1, ["sidekick", "pad", "choir", "arp", "bass"], ["C2"])]
       + groove("The machine sings again", "A", ["lead", "lead_hi", "sidekick", "arp", "pad", "choir", *BASS], FULL + TOMS, ["C3", "C2"], ["el_hat"], crash=True, activity=1.1)
       + groove("Ride the clock again", "V", ["lead", "sidekick", "counter", "comp", "arp", "pad", "choir", *BASS], TWO + ["el_ride", "el_rim"], ["C1", "C2"], ["el_ride"])
       + [blk("Power-down", "A", 8, ["arp", "pad", "lead", *BASS], ["kick", "el_hat", "el_rim"], activity=0.6),
          blk("Power-down: clocks", "A", 4, ["arp"], ["el_hat"])])


def electronium(bounty) -> dict:
    return {"bounty": bounty, "scale": "key", "density": 0.7, "mutation": 0.18, "modify": 0.2,
            "gate": "c4 | (c2 & r3) | (r7 & ~c8)", "register": [67, 88],
            "gravity": 0.65, "accent": 0.55, "legato": 0.8, "max_steps": 5,
            "intervals": {"repeat": 0.2, "step": 1.0, "third": 0.9, "fourth": 0.4, "fifth": 0.5, "sixth": 0.3, "octave": 0.08},
            "behaviours": {"repeat": 0.15, "reverse": 0.08, "transpose": 0.1, "invert": 0.06, "ornament": 0.14},
            "freeze": [{"bar": at(ARR, "The machine sings again 1"), "notes": 8, "bars": 7, "transform": "transpose", "amount": 1},   # climbs a step a pass
                       {"bar": at(ARR, "Half-time: the register mutates"), "notes": 16, "bars": 8, "transform": "mutate", "amount": 0.3}],
            "think": 200, "keep": 3, "phrase": ["theme", "theme", "answer", "free", "theme", "answer", "free", "cadence"],
            "channels": [
                {"name": "lead", "role": "melody", "tone": {"base": "scott-lead", "bits": 10, "cutoff": 1900, "vibrato": 10},
                 "mix": {"gain_db": -7.0, "hp": 250, "lp": 9500, "reverb": 0.18, "echo": 0.26}},
                {"name": "sidekick", "role": "harmony", "follow": "lead", "interval": "third_below", "register": [58, 79],
                 "tone": "pulse-sidekick", "mix": {"gain_db": -11.0, "pan": -0.25, "hp": 220, "lp": 8000, "reverb": 0.25, "echo": 0.12}},
                {"name": "bass", "role": "bass", "gate": "p5 | (r7 & c2 & ~c4)", "register": [29, 46], "density": 0.85,
                 "tone": {"base": "bass-sequencer", "bits": 12}, "mix": {"gain_db": -4.0, "hp": 28, "lp": 3200, "mono": True,
                                                                        "duck": {"depth": 0.3, "release": 0.1}}},
                {"name": "arp", "role": "ostinato", "gate": "c2", "length": 5, "register": [65, 86], "density": 0.45, "mutation": 0.3,
                 "tone": "ostinato-bell", "mix": {"gain_db": -13.0, "pan": 0.25, "hp": 450, "reverb": 0.15, "echo": 0.2, "width": 1.2}},
                {"name": "counter", "role": "counter", "register": [55, 72], "tone": "counter-reed",
                 "mix": {"gain_db": -15.0, "pan": -0.35, "hp": 200, "lp": 6000, "reverb": 0.35}}],
            "moves": [   # the recorder: the operator's hands on the console, bar by bar
                {"bar": 1, "to_bar": at(ARR, "Clockwork"), "channel": "arp", "set": {"density": 1.0}},
                {"bar": at(ARR, "Ride the clock 1"), "channel": "lead", "set": {"gate": "p7 | (p3 & r3)", "density": 0.8}},
                {"bar": at(ARR, "Half-time: the register mutates"), "channel": "lead", "set": {"register": [60, 81]}},
                {"bar": at(ARR, "Half-time: the register mutates"), "channel": "arp", "set": {"gate": "p2", "density": 0.8}},
                {"bar": at(ARR, "Half-time: sidekick alone"), "channel": "bass", "set": {"gate": "p1", "legato": 0.95}},
                {"bar": at(ARR, "The machine sings again 1"), "channel": "lead", "set": {"gate": "c4 | (c2 & r3) | (r7 & ~c8)", "density": 0.75,
                                                                                         "register": [67, 88]}},
                {"bar": at(ARR, "The machine sings again 1"), "channel": "arp", "set": {"gate": "c2", "density": 1.0}},
                {"bar": at(ARR, "The machine sings again 1"), "channel": "bass", "set": {"gate": "p5 | (r7 & c2 & ~c4)", "legato": 0.8}},
                {"bar": at(ARR, "Ride the clock again 1"), "channel": "lead", "set": {"gate": "p7 | (p3 & r3)", "mutation": 0.3}},
                {"bar": at(ARR, "Power-down"), "to_bar": at(ARR, "Power-down") + 7, "set": {"density": 0.3}},
                {"bar": at(ARR, "Power-down"), "to_bar": at(ARR, "Power-down: clocks") + 3, "channel": "arp", "set": {"density": 0.3}}],
            "drums": EL_DRUMS}


def make_spec(bounty="M4S4T0") -> dict:
    sp = S.spec(
        SLUG, TITLE, SEED, BPM,
        ("Written live by the Electronium: 130 in Bb major (Fadd9 - Cm9; Bbmaj9 - F9 in the verse), a punchy NES kit whose "
         "two-step backbone is a grid and whose ghosts, hats, rim, toms and ride come off the Electronium's clock matrix. "
         "Five Electronium channels on its own tone generators: a lead on themes it chose from 200 ideas, a sidekick a third "
         "below, the bassline sequencer, a 5-cell ostinato and a counter line, with the operator's moves played back; "
         f"Bounty {bounty!r}."),
        S.drum_kit("nes", SLUG, S.CHIP_STEM, S.chip_stems(hats=-10.0, perc=-8.0), kick=(230, 44, 24), kick_len=0.34, snare_clock=30000,
                   snare_ms=80, hat_clock=125000, ride_hz=1661.22),
        G, ARR,
        {"comp": (*xpf("BitInvader/epiano.xpf", "BitInvader e-piano, comping"), dict(hp=180, width=1.1, sends={"plate": 0.25, "echo": 0.1}, gain_db=-9.0)),
         "pad": (*zyn("Synth/0005-Pulse Pad 2.xiz", "Pulse Pad 2 (ZynAddSubFX - Synth)"), dict(hp=180, lp=6500, width=1.3, sends={"plate": 0.4}, gain_db=-10.0)),
         "choir": (*zyn("Laba170bank/0129-chip-SlowSawStrings.xiz", "chip SlowSawStrings (ZynAddSubFX - Laba170bank)"),
                   dict(hp=300, lp=6000, width=1.5, sends={"plate": 0.5}, gain_db=-16.0))},
        {"lead": -7.0, "sidekick": -12.0, "arp": -15.0, "counter": -17.0, "comp": -12.0, "pad": -14.0, "choir": -20.0, "bass": -2.0},
        None, layers=[("pad", "choir")],
        overrides={"swing": 0.54, "drum_cycle_per_block": False,
                   "melody": {"writer": "electronium", "register": [67, 88], "humanize_ms": 2, "velocity": [0.62, 0.95]},
                   "electronium": electronium(bounty),
                   "bass": {"style": "pattern", "register": [29, 44], "pattern": [[0, "R", 1.4, 1.0], [6, "5-", 0.3, 0.7], [10, "R", 0.6, 0.9], [14, "O", 0.4, 0.75]]},
                   "comp": {"steps": [3, 6, 11, 14], "low": 57, "high": 77, "top": 74, "notes": 4, "gate": 0.35, "humanize_ms": 4, "vel": 0.5, "accent": 0.6},
                   "arp": {"low": 65, "high": 89, "rate": 0.125, "gate": 0.12, "pattern": [0, 2, 1, 3, 2, 4], "humanize_ms": 0},
                   "pad": {"low": 53, "high": 77, "top": 72, "notes": 4, "vel": 0.48}},
        automation=[{"type": "lowpass", "tracks": ["arp"], "points": [[1, 700], [8, 5000], [9, 18000]]}])
    for k in ("album", "track"):                       # a single, not one of the album's eight
        sp.pop(k, None)
    sp["rebuild"] = "bountiful/pixel_electronium.py"
    sp["mmp_voices"] = {   # the Electronium's channels play on its own tone generators; in the .mmp, LMMS voices stand in
        "lead": xpf("TripleOscillator/OldComputerGames.xpf", "OldComputerGames (LMMS TripleOscillator)"),
        "sidekick": xpf("Organic/sequencer_64.xpf", "sequencer_64 (LMMS Organic)"),
        "arp": xpf("TripleOscillator/ArpeggioPing.xpf", "ArpeggioPing (LMMS TripleOscillator)"),
        "counter": xpf("TripleOscillator/OldComputerGames.xpf", "OldComputerGames (LMMS TripleOscillator)"),
        "bass": xpf("SID/Bass.xpf", "SID bass")}
    sp["test_bars"] = (at(ARR, "The machine sings again 1"), at(ARR, "The machine sings again 1") + 7)
    return sp


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bounty", default="M4S4T0", help="the Electronium's seed: a number or a word (default M4S4T0)")
    args = ap.parse_args()
    bounty = int(args.bounty) if args.bounty.isdigit() else args.bounty
    import lmms_tracks as LT
    import pixel_kits as K
    sp = make_spec(bounty)
    K.build(sp["kit"]["machine"], sp["kit"]["dir"], **sp["kit"]["params"])
    LT.make(sp)


if __name__ == "__main__":
    main()
