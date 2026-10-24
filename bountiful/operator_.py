"""The automatic operator: someone at the Electronium's console who plays the knobs across a song.

Scott guided his machine; this does the guiding. Given the song's sections and the machine's channels it writes
the recorder's [[moves]] (knob sets and ramps by bar, mutes, gate presets, transposes) and its freezes:

  rules     a fixed arc: sparse intro, the verse settles, a ramp into each chorus, the chorus opens up, the bridge
            freezes the lead and lets the counter-line speak, the last chorus lifts, the outro thins out
  brief     your words, read by code (intent.py, no model): "make the break more restless, keep the Rhodes
            intimate" become bounded knob changes over the rules' arc, drum layers and mix changes, each with
            the words it came from. Every move is checked: bars inside the song, channels that exist, values
            clamped to range, gates that parse; anything wrong is dropped.

    $PY bountiful/operator_.py --bounty 7 [--brief "dark, slow build"]
"""
from __future__ import annotations

import argparse

import electronium as EL

RANGES = {"density": (0.05, 1.0), "mutation": (0.0, 1.0), "gravity": (0.0, 1.0), "up": (0.1, 0.9), "accent": (0.0, 1.0),
          "legato": (0.2, 1.0), "max_steps": (1, 16), "modify": (0.0, 1.0), "transpose": (-7, 7), "octave": (-1, 1)}
TRANSFORMS = ("transpose", "invert", "mutate")
KINDS = ("intro", "verse", "prechorus", "chorus", "bridge", "break", "outro")


# ------------------------------------------------------------------ checking a plan

def synth_param(key: str, value, channel: str | None, engines: dict):
    """A move's "synth.<param>" value checked against the engine(s) it reaches (clamped), or raise ValueError."""
    import synthesis as S
    name = key[6:]
    eids = [engines[channel]] if channel in engines else list(engines.values()) if channel is None else []
    params = [p for e in eids if e in S.ENGINES for p in S.engine_class(e).PARAMS if p.name == name]
    if not params:
        raise ValueError(f"no engine on {channel or 'any channel'} has a parameter {name!r}")
    return params[0].clamp(value)


def clean(plan: dict, sections: list[dict], channel_names: list[str],
          engines: dict | None = None) -> tuple[list[dict], list[dict], list[str]]:
    """(moves, freezes, problems): only what the machine can play. engines: channel -> engine id, for synth.* moves."""
    total = max(s["start"] + s["bars"] - 1 for s in sections)
    moves, freezes, bad = [], [], []
    for i, m in enumerate(plan.get("moves", []) or []):
        try:
            bar = int(m["bar"])
        except (KeyError, TypeError, ValueError):
            bad.append(f"move {i + 1}: no bar")
            continue
        if not 1 <= bar <= total:
            bad.append(f"move {i + 1}: bar {bar} outside 1-{total}")
            continue
        mv: dict = {"bar": bar}
        if m.get("to_bar") not in (None, 0, ""):
            try:
                tb = int(m["to_bar"])
                if bar < tb <= total:
                    mv["to_bar"] = tb
            except (TypeError, ValueError):
                bad.append(f"move {i + 1}: to_bar {m['to_bar']!r}")
        ch = m.get("channel") or None
        if ch is not None:
            if ch not in channel_names:
                bad.append(f"move {i + 1}: no channel {ch!r}")
                continue
            mv["channel"] = ch
        st = {}
        for k, v in (m.get("set") or {}).items():
            if k in RANGES:
                lo, hi = RANGES[k]
                try:
                    x = float(v)
                except (TypeError, ValueError):
                    bad.append(f"move {i + 1}: {k}={v!r}")
                    continue
                x = min(hi, max(lo, x))
                st[k] = int(round(x)) if isinstance(lo, int) and isinstance(hi, int) else round(x, 3)
            elif k == "mute":
                st[k] = bool(v)
            elif k == "gate":
                try:
                    EL.Gate(str(v)).eval(EL.np.arange(16), lambda n: 0)
                    st[k] = str(v)
                except ValueError as ex:
                    bad.append(f"move {i + 1}: gate {v!r}: {ex}")
            elif k.startswith("synth.") and engines:
                try:
                    st[k] = synth_param(k, v, ch, engines)
                except (ValueError, TypeError) as ex:
                    bad.append(f"move {i + 1}: {k}: {ex}")
            else:
                bad.append(f"move {i + 1}: unknown knob {k!r}")
        if st:
            mv["set"] = st
            mv["_i"] = i
            if m.get("why"):
                mv["why"] = str(m["why"])[:120]
            moves.append(mv)
    starts = sorted(s["start"] for s in sections)
    for mv in list(moves):            # a transpose that's never set back returns home at the next section
        if mv["set"].get("transpose") and not mv.get("to_bar"):
            later = [m for m in moves if m["_i"] > mv["_i"] and "transpose" in m["set"] and m.get("channel") == mv.get("channel")]
            nxt = next((x for x in starts if x > mv["bar"]), None)
            if not later and nxt:
                moves.append({"bar": nxt, **({"channel": mv["channel"]} if mv.get("channel") else {}), "set": {"transpose": 0},
                              "why": "back home", "_i": 10**6 + mv["_i"]})
    moves.sort(key=lambda m: (m["bar"], m["_i"]))
    for mv in moves:
        mv.pop("_i")
    for i, f in enumerate(plan.get("freezes", []) or []):
        try:
            bar = int(f["bar"])
        except (KeyError, TypeError, ValueError):
            bad.append(f"freeze {i + 1}: no bar")
            continue
        if not 2 <= bar <= total:
            bad.append(f"freeze {i + 1}: bar {bar} outside the song")
            continue
        tf = f.get("transform", "transpose")
        freezes.append({"bar": bar, "notes": 16 if int(f.get("notes", 8) or 8) > 8 else 8,
                        "bars": int(min(16, max(2, int(f.get("bars", 4) or 4)))),
                        "transform": tf if tf in TRANSFORMS else "transpose",
                        "amount": round(min(1.0, max(-3.0, float(f.get("amount", 1) or 1))), 2)})
    return moves, freezes, bad


# ------------------------------------------------------------------ the rule-based operator

def rules(sections: list[dict], channels: list[dict], bounty=1, lead_gate: str | None = None) -> dict:
    """A dependable arc over the sections (kind: intro, verse, prechorus, chorus, bridge, break, outro)."""
    names = {c["name"]: c["role"] for c in channels}
    first = lambda role: next((n for n, r in names.items() if r == role), None)
    lead, arp, counter, bass, keys = first("melody"), first("ostinato"), first("counter"), first("bass"), first("chords")
    moves, freezes, choruses = [], [], [s for s in sections if s["kind"] == "chorus"]
    for k, s in enumerate(sections):
        b, n, kind = s["start"], s["bars"], s["kind"]
        end = b + n - 1
        if kind == "intro":
            moves.append({"bar": b, "set": {"density": 0.45, "mutation": 0.08}, "why": "the intro: sparse, settled"})
            if lead:
                moves.append({"bar": b, "channel": lead, "set": {"gate": "p1"}, "why": "the lead starts on quarters"})
        elif kind == "verse":
            moves.append({"bar": b, "set": {"density": 0.66, "mutation": 0.15, "accent": 0.5}, "why": "the verse settles in"})
            if lead:
                own = next(c for c in channels if c["name"] == lead).get("gate", lead_gate or EL.DEFAULT["gate"])
                moves.append({"bar": b, "channel": lead, "set": {"gate": own}, "why": "the lead's own clock back"})
            nxt = sections[k + 1] if k + 1 < len(sections) else None
            if nxt and nxt["kind"] == "chorus" and n >= 4:
                moves.append({"bar": end - 1, "to_bar": end, "set": {"density": 0.85}, "why": "lean into the chorus"})
        elif kind == "prechorus":
            moves.append({"bar": b, "to_bar": end, "set": {"density": 0.9, "accent": 0.75}, "why": "the build"})
            if arp:
                moves.append({"bar": b, "channel": arp, "to_bar": end, "set": {"density": 1.0}, "why": "the arp fills in"})
        elif kind == "chorus":
            last = s is choruses[-1] and len(choruses) > 1
            moves.append({"bar": b, "set": {"density": 0.84, "accent": 0.7, "gravity": 0.7}, "why": "the chorus opens up"})
            if keys:
                moves.append({"bar": b, "channel": keys, "set": {"mute": False}, "why": "the chords come in"})
            if last and lead:
                moves.append({"bar": b, "channel": lead, "set": {"up": 0.62, "gravity": 0.8}, "why": "the last chorus reaches higher"})
        elif kind in ("bridge", "break"):
            moves.append({"bar": b, "set": {"density": 0.55, "mutation": 0.3}, "why": "the bridge loosens"})
            if keys:
                moves.append({"bar": b, "channel": keys, "set": {"mute": True}, "why": "space"})
            if bass:
                moves.append({"bar": b, "channel": bass, "set": {"gate": "c8 | p4"}, "why": "the bass goes half-time"})
                own = next(c for c in channels if c["name"] == bass).get("gate", EL.ROLE_DEFAULTS["bass"]["gate"])
                moves.append({"bar": end + 1, "channel": bass, "set": {"gate": own}, "why": "the bass back"})
            if lead and n >= 8:
                freezes.append({"bar": b + 1, "notes": 16, "bars": n - 2, "transform": "mutate", "amount": 0.35})
        elif kind == "outro":
            moves.append({"bar": b, "to_bar": end, "set": {"density": 0.3, "mutation": 0.05}, "why": "the outro thins out"})
            if lead:
                moves.append({"bar": b, "channel": lead, "set": {"up": 0.4}, "why": "the line comes down"})
            if arp:
                moves.append({"bar": max(b, end - 1), "channel": arp, "set": {"mute": True}, "why": "the arp stops"})
            if counter:
                moves.append({"bar": b, "channel": counter, "set": {"mute": True}})
    moves = [m for m in moves if m["bar"] <= sections[-1]["start"] + sections[-1]["bars"] - 1]
    return {"moves": moves, "freezes": freezes, "summary": "the rule-based operator's arc"}


# ------------------------------------------------------------------ the operator, with the brief

def operate(sections: list[dict], p: dict, brief: str = "", log=print, intents: list[dict] | None = None,
            bpm: float | None = None) -> dict:
    """{"moves", "freezes", "summary", "by", "problems", "intents", "drums"} for a patch over the sections.

    The rules play the arc; a brief (plain words, read by intent.py) lays its controls over it. intents: the parsed
    intents, possibly with some switched off ("on": False) after a preview; default: parse the brief."""
    import intent as IN
    chans = EL.channels(p)
    names = [c["name"] for c in chans]
    engines = EL.engines(p)
    plan = rules(sections, chans, p["bounty"], p.get("gate"))
    moves, freezes, bad = clean(plan, sections, names, engines)
    if intents is None:
        parsed = IN.parse(brief, sections, bpm or p.get("_bpm") or 120.0) if brief else {"intents": [], "unread": []}
        intents = parsed["intents"]
        for u in parsed["unread"]:
            log(f"operator: not understood in the brief: {u!r}")
    live = [it for it in intents if it.get("on", True)]
    if live:
        total = max(s["start"] + s["bars"] - 1 for s in sections)
        extra = IN.machine_moves(live, p, chans, moves, total)
        more, _, bad2 = clean({"moves": moves + extra}, sections, names, engines)
        moves, bad = more, bad + bad2
        for it in live:
            log("operator: " + IN.explain(it))
    return {"moves": moves, "freezes": freezes, "by": "rules + brief" if live else "rules", "problems": bad, "brief": brief,
            "summary": plan["summary"] + (f'; the brief: "{brief}"' if live and brief else ""),
            "intents": intents, "drums": IN.drum_edits(live, sections)}


def text(res: dict) -> str:
    out = [f"operator ({res['by']}): {res['summary']}"]
    for m in res["moves"]:
        out.append(f"  bar {m['bar']:3d}" + (f"-{m['to_bar']:<3d}" if m.get("to_bar") else "    ") + f" {m.get('channel') or 'all':10s} "
                   + ", ".join(f"{k}={v}" for k, v in m["set"].items()) + (f"   # {m['why']}" if m.get("why") else ""))
    for f in res["freezes"]:
        out.append(f"  freeze at bar {f['bar']}: {f['notes']} notes for {f['bars']} bars, {f['transform']} {f['amount']}")
    return "\n".join(out)


if __name__ == "__main__":
    import electronium_song as ES
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bounty", default="1969")
    ap.add_argument("--brief", default="")
    a = ap.parse_args()
    plan = ES.plan(a.bounty)
    print(text(operate(plan["sections"], plan["patch"], a.brief, bpm=plan["bpm"])))
