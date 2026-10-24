"""The automatic operator: someone at the Electronium's console who plays the knobs across a song.

Scott guided his machine; this does the guiding. Given the song's sections and the machine's channels it writes
the recorder's [[moves]] (knob sets and ramps by bar, mutes, gate presets, transposes) and its freezes:

  rules     a fixed arc: sparse intro, the verse settles, a ramp into each chorus, the chorus opens up, the bridge
            freezes the lead and lets the counter-line speak, the last chorus lifts, the outro thins out
  ollama    a local LLM (your Qwen 3 through Ollama) is shown the sections, the channels and the knobs with their
            ranges and asked for a plan as JSON (Ollama's structured output). Every move is checked: bars inside the
            song, channels that exist, values clamped to range, gates that parse; anything wrong is dropped. If the
            model is unreachable or gives nothing usable, the rules play instead.

    $PY bountiful/operator_.py --bounty 7 [--ollama] [--model qwen3:14b] [--brief "dark, slow build"]
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

import electronium as EL
import paths

RANGES = {"density": (0.05, 1.0), "mutation": (0.0, 1.0), "gravity": (0.0, 1.0), "up": (0.1, 0.9), "accent": (0.0, 1.0),
          "legato": (0.2, 1.0), "max_steps": (1, 16), "modify": (0.0, 1.0), "transpose": (-7, 7), "octave": (-1, 1)}
TRANSFORMS = ("transpose", "invert", "mutate")
KINDS = ("intro", "verse", "prechorus", "chorus", "bridge", "break", "outro")


# ------------------------------------------------------------------ checking a plan

def clean(plan: dict, sections: list[dict], channel_names: list[str]) -> tuple[list[dict], list[dict], list[str]]:
    """(moves, freezes, problems): only what the machine can play."""
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


# ------------------------------------------------------------------ the Ollama operator

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "moves": {"type": "array", "items": {"type": "object", "properties": {
            "bar": {"type": "integer"}, "to_bar": {"type": "integer"}, "channel": {"type": "string"},
            "set": {"type": "object", "properties": {k: {"type": "number"} for k in RANGES} | {"mute": {"type": "boolean"}, "gate": {"type": "string"}}},
            "why": {"type": "string"}}, "required": ["bar", "set"]}},
        "freezes": {"type": "array", "items": {"type": "object", "properties": {
            "bar": {"type": "integer"}, "notes": {"type": "integer"}, "bars": {"type": "integer"},
            "transform": {"type": "string", "enum": list(TRANSFORMS)}, "amount": {"type": "number"}}, "required": ["bar"]}},
    },
    "required": ["summary", "moves", "freezes"],
}

SYSTEM = """You are the operator of the Electronium, Raymond Scott's composing machine. You do not play notes: you guide
the machine by setting its knobs at bars of the song, the way Scott did at the console. Answer with JSON only.

Knobs (set on the whole machine, or on one channel with "channel"):
  density 0.05-1   share of clock triggers that play (sparse ... busy)
  mutation 0-1     how fast the melody's interval habits drift
  gravity 0-1      pull to chord tones on strong beats
  up 0.1-0.9       upward bias of the melody's jumps
  accent 0-1       how much clock coincidences lift velocity
  legato 0.2-1     note length
  max_steps 1-16   the longest note, in 16ths
  modify 0-1       step offsets on frozen loops
  transpose -7..7  scale steps (melody channels)
  octave -1..1
  mute true/false  silence a channel
  gate             a channel's trigger pattern: rhythm presets p1..p12 (p1 quarters, p2 tresillo, p3 eighths, p4
                   offbeats, p5 two-step, p6 dotted 8ths ...) or clock logic: cN every N 16ths, cN+k shifted,
                   rN at the Bounty's phase, & | ^ ~ ( ). Examples: "p3", "c4 | p2", "(c2 & ~r3) | c8"
A move: {"bar": 17, "set": {"density": 0.8}} sets from that bar on; with "to_bar": 24 it ramps there smoothly.
A freeze: {"bar": 49, "notes": 8 or 16, "bars": 4-16, "transform": "transpose"|"invert"|"mutate", "amount": 1}
captures the melody's last notes into a loop that evolves, then breaks back into free playing.

Make the song breathe: contrast between sections, builds (ramps with to_bar) into choruses, something unexpected in
the bridge (a freeze there is classic), a release at the end. Use the channels: change a channel's gate for a new
groove, mute one for space, give the bass or arp a different pattern in a section. A transpose shifts the melody
along the scale against the same chords, so use it sparingly and set it back. Prefer 10-24 well-placed moves to
many small ones. Give each move a short "why"."""


def ask_ollama(sections: list[dict], channels: list[dict], p: dict, brief: str = "", model: str | None = None,
               url: str | None = None, timeout: float = 240.0, log=print) -> dict:
    """The model's plan (raw, unchecked). Raises on network or format errors."""
    o = paths.ollama()
    model, url = model or o["model"], (url or o["url"]).rstrip("/")
    song = {"bpm": p.get("_bpm"), "bounty": p["bounty"], "bars": max(s["start"] + s["bars"] - 1 for s in sections),
            "sections": [{"name": s["name"], "kind": s["kind"], "bars": f"{s['start']}-{s['start'] + s['bars'] - 1}",
                          **({"playing": s["parts"]} if s.get("parts") else {})} for s in sections],
            "channels": [{"name": c["name"], "role": c["role"], **({"gate": c["gate"]} if c.get("gate") else {})} for c in channels],
            "starting_knobs": {k: p[k] for k in ("density", "mutation", "gravity", "up", "accent", "legato")}}
    user = ("Plan the operator's moves for this song.\n" + json.dumps(song, indent=1)
            + (f"\n\nThe producer's brief: {brief}" if brief else ""))
    body = {"model": model, "stream": False, "format": SCHEMA, "think": False,
            "options": {"temperature": 0.6, "seed": EL.bounty_int(p["bounty"]) % 2**31, "num_ctx": 8192},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
    log(f"operator: asking {model} at {url} ...")

    def post(b):
        req = urllib.request.Request(url + "/api/chat", data=json.dumps(b).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    try:
        res = post(body)
    except urllib.error.HTTPError as ex:              # an older Ollama or a model without the think switch
        if ex.code != 400:
            raise
        body.pop("think")
        res = post(body)
    text = res.get("message", {}).get("content", "")
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


def models(url: str | None = None, timeout: float = 3.0) -> list[str]:
    """The models your Ollama has (empty if it isn't running)."""
    try:
        with urllib.request.urlopen((url or paths.ollama()["url"]) + "/api/tags", timeout=timeout) as r:
            return [m["name"] for m in json.loads(r.read()).get("models", [])]
    except (OSError, ValueError):
        return []


def operate(sections: list[dict], p: dict, use_ollama: bool = False, brief: str = "", model: str | None = None, log=print) -> dict:
    """{"moves", "freezes", "summary", "by": "rules" | model name, "problems": [...]} for a patch over the sections."""
    chans = EL.channels(p)
    names = [c["name"] for c in chans]
    if use_ollama:
        try:
            raw = ask_ollama(sections, chans, p, brief, model, log=log)
            moves, freezes, bad = clean(raw, sections, names)
            if moves:
                for b_ in bad:
                    log(f"  operator: dropped {b_}")
                return {"moves": moves, "freezes": freezes, "summary": str(raw.get("summary", ""))[:400],
                        "by": model or paths.ollama()["model"], "problems": bad}
            log("operator: the model's plan had no usable moves; the rules play instead")
        except Exception as ex:                       # unreachable, timed out, not JSON: the rules play
            log(f"operator: Ollama failed ({str(ex)[:160]}); the rules play instead")
    plan = rules(sections, chans, p["bounty"], p.get("gate"))
    moves, freezes, bad = clean(plan, sections, names)
    return {"moves": moves, "freezes": freezes, "summary": plan["summary"], "by": "rules", "problems": bad}


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
    ap.add_argument("--ollama", action="store_true")
    ap.add_argument("--model")
    ap.add_argument("--brief", default="")
    a = ap.parse_args()
    plan = ES.plan(a.bounty)
    print(text(operate(plan["sections"], plan["patch"], a.ollama, a.brief, a.model)))
