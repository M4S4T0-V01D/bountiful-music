"""Intent-aware production: a producer's brief in plain words turned into explicit, bounded controls. No model, no
network: a lexicon and a few rules, so the same brief always gives the same controls and every control says which
words it came from.

    "make the break more restless, keep the Rhodes intimate, let the last two minutes open into something huge"

  clause    the brief is split at commas, "and", "but", "then", ";" and "."
  scope     where: a section ("the break", "the last chorus", "verse 2", "every chorus", "the intro"), a span of
            time ("the last two minutes", "the first 30 seconds", "bars 9-16", "the second half", "the end"),
            or the whole song
  target    who: a part ("the Rhodes", "the bass", "the lead", "the arp", "the drums" ...) or every voice
  quality   what: restless, calm, intimate, huge, dark, bright, sparse, dense, tense, resolved, smooth, punchy,
            strange, simple, high, low, loud, quiet, wide, dry ... with "more", "much more", "a bit", "less"
  shape     "open into", "build", "grow", "swell", "rise": a ramp across the scope instead of a step

Each clause becomes an Intent with three kinds of control, all clamped by LIMITS:
  machine      Electronium knob deltas (density, mutation, gravity, up, accent, legato) per channel and bar range
  drums        drum layers added or taken away in the sections the scope touches
  production   per-part mix deltas (gain_db, width, reverb, bright) for the producer (studio.py)

    $PY bountiful/intent.py "make the break more restless, keep the Rhodes intimate"
"""
from __future__ import annotations

import copy
import math
import re

# per-quality deltas at amount 1.0 ("more X"); a quality's opposite is the negation
LEX = {
    "restless": {"machine": {"density": 0.18, "mutation": 0.25, "accent": 0.15, "legato": -0.15},
                 "drums": ["hat", "syntom_hi"], "production": {"bright": 0.1}},
    "calm": {"machine": {"density": -0.18, "mutation": -0.1, "accent": -0.15, "legato": 0.18},
             "drums": ["-open", "-clap", "-syntom_hi", "-syntom_lo"], "production": {"bright": -0.1}},
    "intimate": {"machine": {"density": -0.08, "legato": 0.12, "accent": -0.1},
                 "production": {"reverb": -0.4, "width": -0.3, "gain_db": -1.0}},
    "huge": {"machine": {"density": 0.15, "gravity": 0.12, "up": 0.08, "accent": 0.12},
             "drums": ["open", "clap"], "production": {"reverb": 0.35, "width": 0.35, "gain_db": 1.5}},
    "dark": {"machine": {"up": -0.14}, "production": {"bright": -0.35}},
    "bright": {"machine": {"up": 0.14}, "production": {"bright": 0.35}},
    "sparse": {"machine": {"density": -0.28}, "drums": ["-hat", "-open", "-clap"]},
    "dense": {"machine": {"density": 0.25}, "drums": ["hat"]},
    "tense": {"machine": {"mutation": 0.15, "gravity": -0.22, "accent": 0.1}},
    "resolved": {"machine": {"gravity": 0.25, "mutation": -0.1}},
    "smooth": {"machine": {"legato": 0.3, "accent": -0.1}},
    "punchy": {"machine": {"legato": -0.25, "accent": 0.22}, "production": {"gain_db": 0.5}},
    "strange": {"machine": {"mutation": 0.4, "gravity": -0.15}},
    "simple": {"machine": {"mutation": -0.15, "density": -0.08, "gravity": 0.12}},
    "high": {"machine": {"up": 0.2}},
    "low": {"machine": {"up": -0.2}},
    "loud": {"production": {"gain_db": 2.5}},
    "quiet": {"production": {"gain_db": -3.0}},
    "wide": {"production": {"width": 0.5}},
    "dry": {"production": {"reverb": -0.5}},
    "wet": {"production": {"reverb": 0.5}},
}
WORDS = {   # word stems -> (quality, sign)
    "restless": ("restless", 1), "agitat": ("restless", 1), "nervous": ("restless", 1), "frantic": ("restless", 1),
    "urgent": ("restless", 1), "busy": ("restless", 1), "jittery": ("restless", 1), "anxious": ("restless", 1),
    "calm": ("calm", 1), "settled": ("calm", 1), "relax": ("calm", 1), "gentle": ("calm", 1),
    "peaceful": ("calm", 1), "laid back": ("calm", 1), "laid-back": ("calm", 1), "chill": ("calm", 1),
    "intimate": ("intimate", 1), "close": ("intimate", 1), "small": ("intimate", 1), "personal": ("intimate", 1),
    "huge": ("huge", 1), "big": ("huge", 1), "massive": ("huge", 1), "epic": ("huge", 1), "enormous": ("huge", 1),
    "expansive": ("huge", 1), "vast": ("huge", 1), "immense": ("huge", 1), "grand": ("huge", 1), "open": ("huge", 1),
    "dark": ("dark", 1), "gloomy": ("dark", 1), "moody": ("dark", 1), "murky": ("dark", 1), "warm": ("dark", 0.5),
    "bright": ("bright", 1), "sparkl": ("bright", 1), "shiny": ("bright", 1), "airy": ("bright", 1), "crisp": ("bright", 0.6),
    "sparse": ("sparse", 1), "minimal": ("sparse", 1), "empty": ("sparse", 1), "thin": ("sparse", 1), "spacious": ("sparse", 0.7),
    "dense": ("dense", 1), "full": ("dense", 1), "thick": ("dense", 1), "packed": ("dense", 1), "lush": ("dense", 0.7),
    "tense": ("tense", 1), "tension": ("tense", 1), "uneasy": ("tense", 1), "unsettl": ("tense", 1), "suspense": ("tense", 1),
    "resolved": ("resolved", 1), "stable": ("resolved", 1), "grounded": ("resolved", 1), "inevitable": ("resolved", 0.8),
    "smooth": ("smooth", 1), "flowing": ("smooth", 1), "legato": ("smooth", 1), "liquid": ("smooth", 1), "silky": ("smooth", 1),
    "punchy": ("punchy", 1), "choppy": ("punchy", 1), "staccato": ("punchy", 1), "tight": ("punchy", 0.7), "sharp": ("punchy", 0.7),
    "strange": ("strange", 1), "weird": ("strange", 1), "wild": ("strange", 1), "chaotic": ("strange", 1),
    "unpredictable": ("strange", 1), "surpris": ("strange", 0.7), "experimental": ("strange", 1), "alien": ("strange", 1),
    "simple": ("simple", 1), "predictable": ("simple", 1), "hypnotic": ("simple", 1), "repetitive": ("simple", 1),
    "focused": ("simple", 0.7), "steady": ("simple", 0.6),
    "high": ("high", 1), "soar": ("high", 1), "lift": ("high", 0.7), "uplift": ("high", 0.7), "hopeful": ("high", 0.6),
    "low": ("low", 1), "deep": ("low", 0.7), "sad": ("low", 0.6), "melanchol": ("low", 0.6), "sombre": ("low", 0.6), "somber": ("low", 0.6),
    "loud": ("loud", 1), "louder": ("loud", 1), "forward": ("loud", 0.6), "present": ("loud", 0.5), "prominent": ("loud", 0.8),
    "quiet": ("quiet", 1), "soft": ("quiet", 0.7), "distant": ("quiet", 0.7), "background": ("quiet", 0.8), "subtle": ("quiet", 0.5),
    "wide": ("wide", 1), "wider": ("wide", 1), "narrow": ("wide", -1), "mono": ("wide", -1),
    "dry": ("dry", 1), "drier": ("dry", 1), "wet": ("wet", 1), "roomy": ("wet", 0.7), "reverb": ("wet", 0.7), "ambient": ("wet", 0.7),
}
COMPARATIVE = {"bigger": "big", "darker": "dark", "brighter": "bright", "calmer": "calm", "denser": "dense", "higher": "high",
               "lower": "low", "quieter": "quiet", "smoother": "smooth", "simpler": "simple", "stranger": "strange",
               "weirder": "weird", "wilder": "wild", "thicker": "thick", "thinner": "thin", "closer": "close", "tighter": "tight",
               "deeper": "deep", "warmer": "warm", "softer": "soft", "busier": "busy", "punchier": "punchy", "sparser": "sparse"}
STOP = {"opening", "closing", "lowest", "highest", "fully", "closely", "presently", "shortly"}
PARTS = {   # words -> roles (the Electronium's channel roles; "drums" is the kit)
    "rhodes": "chords", "piano": "chords", "keys": "chords", "chords": "chords", "organ": "chords", "pad": "chords",
    "pads": "chords", "strings": "chords", "comp": "chords", "keyboard": "chords",
    "bass": "bass", "bassline": "bass", "low end": "bass", "sub": "bass",
    "lead": "melody", "melody": "melody", "tune": "melody", "hook": "melody", "topline": "melody", "theme": "melody",
    "arp": "ostinato", "arpeggio": "ostinato", "arpeggios": "ostinato", "sequence": "ostinato", "ostinato": "ostinato",
    "counter": "counter", "countermelody": "counter", "counterline": "counter", "counter-melody": "counter",
    "counter line": "counter", "answer": "counter",
    "sidekick": "harmony", "harmony": "harmony", "second voice": "harmony",
    "drums": "drums", "beat": "drums", "percussion": "drums", "kick": "drums", "snare": "drums", "hats": "drums",
    "groove": "drums", "break beat": "drums", "breakbeat": "drums", "kit": "drums",
}
ROLE_PART = {"chords": "keys", "bass": "bass", "melody": "lead", "ostinato": "arp", "counter": "counter",
             "harmony": "sidekick", "drums": "drums"}
RAMP = ("open into", "opens into", "open up into", "build", "grow", "swell", "rise", "bloom", "blossom", "evolve into",
        "turn into", "become", "gradually", "slowly", "ramp", "climb")
NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
       "ten": 10, "twelve": 12, "fifteen": 15, "sixteen": 16, "twenty": 20, "thirty": 30, "forty": 40, "half a": 0.5}
ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4}
LIMITS = {"density": 0.35, "mutation": 0.45, "gravity": 0.3, "up": 0.25, "accent": 0.3, "legato": 0.35,
          "gain_db": 4.0, "width": 0.6, "reverb": 0.6, "bright": 0.5}
RANGES = {"density": (0.05, 1.0), "mutation": (0.0, 1.0), "gravity": (0.0, 1.0), "up": (0.1, 0.9), "accent": (0.0, 1.0),
          "legato": (0.2, 1.0)}
SPLIT = re.compile(r"\s*(?:[,;.!]|\bbut\b|\bthen\b|\bwhile\b|\band then\b|\band\b(?=\s+(?:make|keep|let|give|have|bring|push|take|the|in|for|during|over|from|at)\b))\s*", re.I)


def _num(tok: str) -> float | None:
    tok = tok.strip().lower()
    if tok in NUM:
        return float(NUM[tok])
    try:
        return float(tok)
    except ValueError:
        return None


def _quality(words: str) -> list[tuple[str, float, str]]:
    """[(quality, sign, the word)] found in a clause, in order."""
    out, seen = [], set()
    text = " " + words.lower() + " "
    for comp, base in COMPARATIVE.items():
        text = re.sub(rf"\b{comp}\b", f"more {base}", text)
    for stem in sorted(WORDS, key=len, reverse=True):
        for m in re.finditer(rf"\b{re.escape(stem)}\w*", text):
            if any(a <= m.start() < b for a, b in seen):
                continue
            q, sign = WORDS[stem]
            if m.group(0) in STOP or any(q == o[1] for o in out):
                continue
            before = text[max(0, m.start() - 12): m.start()]
            if re.search(r"\b(not|less|never|no longer|without)\s+(\w+\s+)?$", before):
                sign = -sign
            seen.add((m.start(), m.end()))
            out.append((m.start(), q, sign, m.group(0)))
    return [(q, s, w) for _, q, s, w in sorted(out)]


def _amount(words: str) -> float:
    w = words.lower()
    if re.search(r"\b(much|way|far|a lot|really|very|totally|completely|massively|hugely|extremely)\b", w):
        return 1.5
    if re.search(r"\b(a bit|a little|slightly|somewhat|a touch|touch|gently|a tad|subtly)\b", w):
        return 0.5
    return 1.0


def _targets(words: str) -> list[str]:
    w = " " + words.lower() + " "
    out = []
    for word in sorted(PARTS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(word)}\b", w):
            if PARTS[word] not in out:
                out.append(PARTS[word])
            w = re.sub(rf"\b{re.escape(word)}\b", " ", w)
    return out


def _scope(words: str, sections: list[dict], bpm: float) -> tuple[int, int, str] | None:
    """(first bar, last bar, label), 1-based inclusive; None for the whole song."""
    w = words.lower()
    total = max(s["start"] + s["bars"] - 1 for s in sections)
    bars_for = lambda secs: max(1, min(total, int(math.ceil(secs * bpm / 240.0))))
    num = r"(\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|sixteen|twenty|thirty|forty|half a)"
    m = re.search(rf"\b(last|final|closing|first|opening)\s+(?:{num}\s+)?(minutes?|seconds?|secs?|bars?|measures?)\b", w)
    if m:
        n = _num(m.group(2)) if m.group(2) else 1.0
        unit = m.group(3)
        span = bars_for(n * 60) if unit.startswith("min") else bars_for(n) if unit.startswith("sec") else max(1, min(total, int(n)))
        last = m.group(1) in ("last", "final", "closing")
        a, b = (total - span + 1, total) if last else (1, span)
        return a, b, f"{m.group(1)} {m.group(2) + ' ' if m.group(2) else ''}{unit} (bars {a}-{b})"
    m = re.search(r"\bbars?\s+(\d+)\s*(?:-|to|through|–)\s*(\d+)", w)
    if m:
        a, b = sorted((int(m.group(1)), int(m.group(2))))
        a, b = max(1, a), min(total, b)
        if a <= b:
            return a, b, f"bars {a}-{b}"
    m = re.search(r"\b(?:from|after)\s+bar\s+(\d+)", w)
    if m and 1 <= int(m.group(1)) <= total:
        return int(m.group(1)), total, f"bars {int(m.group(1))}-{total}"
    m = re.search(r"\b(first|second|last)\s+half\b", w)
    if m:
        h = total // 2
        a, b = (1, h) if m.group(1) == "first" else (h + 1, total)
        return a, b, f"{m.group(1)} half (bars {a}-{b})"
    kinds = {"intro": ("intro",), "verse": ("verse",), "pre-chorus": ("prechorus",), "prechorus": ("prechorus",),
             "chorus": ("chorus",), "bridge": ("bridge",), "break": ("break", "bridge"), "breakdown": ("break", "bridge"),
             "middle eight": ("bridge",), "outro": ("outro",), "ending": ("outro",), "coda": ("outro",)}
    for word in sorted(kinds, key=len, reverse=True):
        mm = re.search(rf"\b(?:(every|all|each|the)\s+)?(?:(last|final|first|second|third|1st|2nd|3rd)\s+)?{re.escape(word)}(e?s)?\b(?:\s+(\d))?", w)
        if not mm:
            continue
        cands = [s for s in sections if s["kind"] in kinds[word][:1]] or [s for s in sections if s["kind"] in kinds[word]]
        if not cands:
            continue
        if mm.group(1) in ("every", "all", "each") or mm.group(3):
            pick = cands
        elif mm.group(2) in ("last", "final"):
            pick = cands[-1:]
        elif mm.group(2) or mm.group(4):
            k = ORD.get(mm.group(2), 0) if mm.group(2) else int(mm.group(4))
            pick = cands[k - 1: k] or cands[-1:]
        else:
            pick = cands[:1] if word not in ("chorus",) else cands
        if len(pick) > 1:
            return "multi", pick, f"every {word}"
        a, b = pick[0]["start"], pick[0]["start"] + pick[0]["bars"] - 1
        return a, b, f"{pick[0]['name'].lower()} (bars {a}-{b})"
    if re.search(r"\bthe (end|close)\b|\bat the end\b|\btowards? the end\b", w):
        s = sections[-1]
        return s["start"], total, f"the end (bars {s['start']}-{total})"
    if re.search(r"\b(the )?(start|beginning|opening)\b", w):
        s = sections[0]
        return 1, s["start"] + s["bars"] - 1, f"the start (bars 1-{s['bars']})"
    return None


def parse(brief: str, sections: list[dict], bpm: float = 120.0) -> dict:
    """{"intents": [...], "unread": [clauses with no quality]} for a brief over a song's sections."""
    intents, unread = [], []
    total = max(s["start"] + s["bars"] - 1 for s in sections)
    for clause in [c.strip() for c in SPLIT.split(brief or "") if c and c.strip()]:
        quals = _quality(clause)
        if not quals:
            if len(clause.split()) > 1:
                unread.append(clause)
            continue
        sc = _scope(clause, sections, bpm)
        if sc is None:
            spans, label = [(1, total)], "the whole song"
        elif sc[0] == "multi":
            spans, label = [(s["start"], s["start"] + s["bars"] - 1) for s in sc[1]], sc[2]
        else:
            spans, label = [(sc[0], sc[1])], sc[2]
        low = clause.lower()
        ramp = any(re.search(rf"\b{re.escape(r)}", low) for r in RAMP)
        amt = _amount(clause)
        targets = _targets(clause)
        keep = bool(re.search(r"\b(keep|stay|remain|leave)\b", low))
        for q, sign, word in quals:
            intents.append({"clause": clause, "quality": q, "word": word, "sign": sign, "amount": amt * (0.6 if keep else 1.0),
                            "spans": spans, "scope": label, "targets": targets, "ramp": ramp and not keep,
                            "keep": keep, "on": True})
    return {"intents": intents, "unread": unread}


def deltas(it: dict) -> dict:
    """The intent's bounded deltas: {"machine": {...}, "drums": [...], "production": {...}}."""
    lx = LEX[it["quality"]]
    k = it["sign"] * it["amount"]
    clip = lambda key, v: round(max(-LIMITS[key], min(LIMITS[key], v)), 3)
    drums = []
    if k > 0:
        drums = list(lx.get("drums", []))
    elif k < 0:
        drums = [d[1:] if d.startswith("-") else "-" + d for d in lx.get("drums", [])]
    return {"machine": {key: clip(key, v * k) for key, v in lx.get("machine", {}).items()},
            "drums": drums,
            "production": {key: clip(key, v * k) for key, v in lx.get("production", {}).items()}}


def explain(it: dict) -> str:
    d = deltas(it)
    who = ", ".join(ROLE_PART.get(t, t) for t in it["targets"]) or "every voice"
    bits = [f"{k} {v:+g}" for k, v in d["machine"].items()] + [f"drums {x}" for x in d["drums"]] + \
           [f"mix {k} {v:+g}" for k, v in d["production"].items()]
    shape = "ramping across" if it["ramp"] else "held through" if it["keep"] else "in"
    return f'"{it["word"]}" -> {who}, {shape} {it["scope"]}: ' + ", ".join(bits)


def controls(parsed: dict) -> list[dict]:
    """One row per control, for a preview table: clause, scope, target, kind, knob, delta."""
    rows = []
    for i, it in enumerate(parsed["intents"]):
        d = deltas(it)
        tg = ", ".join(ROLE_PART.get(t, t) for t in it["targets"]) or "all"
        for kind in ("machine", "production"):
            for k, v in d[kind].items():
                rows.append({"intent": i, "clause": it["clause"], "scope": it["scope"], "target": tg, "kind": kind,
                             "knob": k, "delta": v, "ramp": it["ramp"]})
        for x in d["drums"]:
            rows.append({"intent": i, "clause": it["clause"], "scope": it["scope"], "target": "drums", "kind": "drums",
                         "knob": x.lstrip("-"), "delta": -1 if x.startswith("-") else 1, "ramp": False})
    return rows


# ------------------------------------------------------------------ turning intents into machine moves

def _state(p: dict, moves: list[dict], bar: int, ch: dict) -> dict:
    """The knobs of channel ch at 1-based bar, as the machine's recorder would have them (ramps at their value)."""
    v = {k: p.get(k) for k in RANGES}
    v.update({k: x for k, x in ch.items() if k in RANGES})
    for m in sorted(moves, key=lambda m: m["bar"]):
        if m.get("channel") not in (None, ch["name"]) or bar < m["bar"]:
            continue
        for k, target in m.get("set", {}).items():
            if k not in RANGES or not isinstance(v.get(k), (int, float)):
                continue
            if m.get("to_bar") and bar < m["to_bar"]:
                frac = (bar - m["bar"] + 1) / (m["to_bar"] - m["bar"] + 1)
                v[k] = v[k] + (float(target) - v[k]) * frac
            else:
                v[k] = float(target)
    return v


def _clamp(k: str, x: float) -> float:
    lo, hi = RANGES[k]
    return round(min(hi, max(lo, x)), 3)


def machine_moves(intents: list[dict], p: dict, channels: list[dict], base: list[dict], total: int) -> list[dict]:
    """Moves that lay the intents over the base (the rules') moves: at each span's first bar the channel's knobs move
    by the deltas (or ramp to them), any base move inside the span is followed by its shifted twin, and at the bar
    after the span the knobs go back to where the base had them."""
    out = []
    for it in intents:
        if not it.get("on", True):
            continue
        d = deltas(it)["machine"]
        if not d:
            continue
        roles = [t for t in it["targets"] if t != "drums"]
        if it["targets"] and not roles:
            continue                                   # drums only: the kit isn't a knob channel
        chans = [c for c in channels if not roles or c["role"] in roles]
        why = f'brief: "{it["clause"]}" ({it["word"]})'
        for a, b in it["spans"]:
            for c in chans:
                if it["ramp"]:
                    end = _state(p, base, b, c)
                    out.append({"bar": a, "to_bar": b, "channel": c["name"],
                                "set": {k: _clamp(k, end[k] + dv) for k, dv in d.items()}, "why": why})
                else:
                    st = _state(p, base, a, c)
                    out.append({"bar": a, "channel": c["name"], "set": {k: _clamp(k, st[k] + dv) for k, dv in d.items()},
                                "why": why})
                for m in base:                         # base moves inside the span keep the shift
                    if a < m["bar"] <= b and m.get("channel") in (None, c["name"]) and set(m.get("set", {})) & set(d):
                        st = _state(p, base, m.get("to_bar") or m["bar"], c)
                        tw = {"bar": m["bar"], "channel": c["name"],
                              "set": {k: _clamp(k, st[k] + d[k]) for k in d if k in m["set"]}, "why": why + ", kept"}
                        if m.get("to_bar"):
                            tw["to_bar"] = min(m["to_bar"], b)
                        out.append(tw)
                if b < total:
                    st = _state(p, base, b + 1, c)
                    out.append({"bar": b + 1, "channel": c["name"], "set": {k: round(st[k], 3) for k in d},
                                "why": why + ", released"})
    return out


def drum_edits(intents: list[dict], sections: list[dict]) -> list[dict]:
    """[{"section": index, "add": [...], "remove": [...], "why"}] for intents about the drums (or about everyone)."""
    out = []
    for it in intents:
        if not it.get("on", True) or (it["targets"] and "drums" not in it["targets"]):
            continue
        ds = deltas(it)["drums"]
        if not ds:
            continue
        for i, s in enumerate(sections):
            a, b = s["start"], s["start"] + s["bars"] - 1
            if any(a <= y and x <= b for x, y in it["spans"]) and (len(it["spans"]) > 1 or it["spans"][0] != (1, max(
                    t["start"] + t["bars"] - 1 for t in sections)) or it["targets"]):
                out.append({"section": i, "add": [x for x in ds if not x.startswith("-")],
                            "remove": [x[1:] for x in ds if x.startswith("-")], "why": f'brief: "{it["clause"]}"'})
    return out


def apply_drums(sections: list[dict], edits: list[dict]) -> list[dict]:
    """The sections with the drum edits made (a copy)."""
    secs = copy.deepcopy(sections)
    for e in edits:
        s = secs[e["section"]]
        layers = [x for x in s["drums"] if x not in e["remove"]]
        layers += [x for x in e["add"] if x not in layers]
        s["drums"] = layers
    return secs


def production(intents: list[dict], parts: list[str] | None = None) -> list[dict]:
    """Per-part mix deltas for the producer: [{"part", "spans", "changes": {...}, "why"}]."""
    out = []
    for it in intents:
        if not it.get("on", True):
            continue
        ch = deltas(it)["production"]
        if not ch:
            continue
        names = [ROLE_PART[t] for t in it["targets"]] or ["*"]
        for n in names:
            if parts is not None and n != "*" and n not in parts:
                continue
            out.append({"part": n, "spans": it["spans"], "changes": ch, "why": f'brief: "{it["clause"]}" ({it["word"]})'})
    return out


if __name__ == "__main__":
    import sys
    import electronium_song as ES
    pl = ES.plan("1969")
    res = parse(" ".join(sys.argv[1:]) or "make the break more restless, keep the Rhodes intimate, "
                "let the last two minutes open into something huge", pl["sections"], pl["bpm"])
    for it in res["intents"]:
        print(explain(it))
    for u in res["unread"]:
        print(f"(not understood: {u!r})")
