"""The Electronium, live: it plays a Bounty's song bar by bar while you turn the knobs.

A few bars ahead of the playhead it performs the song (electronium_song's plan, the operator's moves plus yours) and
synthesises the next bars on the channels' own tone generators and its percussion, with a spring tank on a send.
A knob you turn takes effect from the next bar and is recorded as a move, so the take can be rendered properly
afterwards (moves(), or save the patch). At the end of the song it carries on with the next Bounty.

Qt-free: the DAW pulls audio with next_block(); the command line writes a take to a WAV.
    $PY bountiful/live.py --bounty 1969 --bars 16 --wav take.wav [--set 9:density=0.9 --set 13:lead.gate=p3]
"""
from __future__ import annotations

import argparse
import threading
from pathlib import Path

import numpy as np

import electronium as EL
import electronium_drums as DR
import electronium_song as ES
import electronium_voice as V
import operator_ as OP
import producer as PR

SR = 44100
GM_TO_SOUND = {v: k for k, v in reversed(list(PR.GM.items()))}


def spring_ir(seconds: float = 1.6, period: float = 0.031) -> np.ndarray:
    rng = np.random.default_rng(11)
    n = int(seconds * SR)
    ir = np.zeros(n, np.float32)
    L = int(period * 0.9 * SR)
    tc = np.arange(L) / SR
    f = 4200 * (300 / 4200) ** ((tc / tc[-1]) ** 0.6)
    burst = (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.hanning(L)).astype(np.float32)
    k = 0
    while (i := int((0.006 + k * period) * SR)) + L < n:
        ir[i:i + L] += burst * np.exp(-6.9 * i / SR / seconds) * (1 if k % 2 == 0 else -0.85)
        k += 1
    ir += (rng.standard_normal(n) * np.exp(-np.arange(n) / SR / (seconds / 5)) * 0.15).astype(np.float32)
    return ir / np.sqrt((ir ** 2).sum())


class Live:
    def __init__(self, bounty="1969", key=None, bpm=None, length="normal", reharm=0.25, operator: dict | None = None,
                 lookahead_bars: int = 2):
        self.lock = threading.RLock()
        self.user_moves: list[dict] = []
        self.ahead = lookahead_bars
        self.load(bounty, key, bpm, length, reharm, operator)

    # ---- the song
    def load(self, bounty, key=None, bpm=None, length="normal", reharm=0.25, operator=None):
        with self.lock:
            self.pl = ES.plan(bounty, key, bpm, length, reharm)
            self.op = operator or OP.operate(self.pl["sections"], EL.patch(self.pl["patch"]), log=lambda *_: None)
            self.bars = sum(s["bars"] for s in self.pl["sections"])
            self.beat = 60 / self.pl["bpm"]
            self.bar_n = int(round(4 * self.beat * SR))
            self.bar = 0                      # the next bar to synthesise
            self.dirty = True
            self.perf = None
            self.chans = {c["name"]: c for c in EL.channels(self.pl["patch"])}
            self.mutes: set[str] = set()
            self.tail = np.zeros((0, 2), np.float32)
            self.wet_tail = np.zeros(0, np.float32)
            self.ir = spring_ir()
            self.cache: dict = {}
            self.rng = np.random.default_rng(7)
            self.prev: dict = {}

    def section_at(self, bar: int) -> dict:
        return next((s for s in self.pl["sections"] if s["start"] - 1 <= bar < s["start"] - 1 + s["bars"]), self.pl["sections"][-1])

    def turn(self, knob: str, value, channel: str | None = None, at_bar: int | None = None):
        """Turn a knob from the next bar on (recorded as a move). knob: density, mutation, gate, mute ... (operator_.RANGES)"""
        with self.lock:
            bar = (at_bar if at_bar is not None else self.bar) + 1
            mv = {"bar": max(1, min(self.bars, bar)), "set": {knob: value}, **({"channel": channel} if channel else {})}
            moves, _, bad = OP.clean({"moves": [mv]}, self.pl["sections"], list(self.chans))
            if bad:
                raise ValueError("; ".join(bad))
            self.user_moves += moves
            self.dirty = True

    def moves(self) -> list[dict]:
        return [{k: v for k, v in m.items() if k != "why"} for m in self.op["moves"]] + self.user_moves

    def patch(self) -> dict:
        p = EL.patch(self.pl["patch"])
        p["moves"] = sorted(self.moves(), key=lambda m: m["bar"])
        p["freeze"] = self.op["freezes"]
        return {k: v for k, v in p.items() if not k.startswith("_")}

    def _perform(self):
        op = dict(self.op, moves=self.moves())
        self.perf = ES.perform(self.pl, op)
        self.dirty = False

    # ---- sound
    def _note(self, ch: str, q: int, v: float, d: float, glide) -> np.ndarray:
        t = (EL.tone(self.chans[ch]) if ch in self.chans else None) or EL.TONES["scott-lead"]
        key = (ch, q, round(d, 2), round(v * 16) / 16, glide, int(self.rng.integers(4)))
        if key not in self.cache:
            if len(self.cache) > 4000:
                self.cache.clear()
            self.cache[key] = V.note(q, v, max(0.02, d), t, self.rng, from_midi=glide)
        return self.cache[key]

    def _hit(self, sound: str, v: float) -> tuple[np.ndarray, str]:
        fn, args, stem = DR.KIT.get(sound, DR.KIT["rim"])
        key = (sound, round(v * 8) / 8, int(self.rng.integers(3)))
        if key not in self.cache:
            self.cache[key] = getattr(DR, fn)(self.rng, v, **args)
        return self.cache[key], stem

    def render_bars(self, b0: int, n: int) -> np.ndarray:
        """Stereo float32 for bars b0 .. b0+n-1 (plus nothing of the tails: they carry over in next_block)."""
        if self.dirty or self.perf is None:
            self._perform()
        L = n * self.bar_n
        out = np.zeros((L + SR * 3, 2), np.float32)
        wet = np.zeros(L + SR * 3, np.float32)
        t0 = b0 * 4
        kit = DR.kit()
        for name, notes in self.perf["parts"].items():
            if not notes or name in self.mutes:
                continue
            base = "lead" if name == "lead_hi" else name
            mix = self.chans.get(base, {}).get("mix", {})
            g = 10 ** ((mix.get("gain_db", -10) - (8 if name == "lead_hi" else 0)) / 20) * 1.6
            pan = 0.2 if name == "lead_hi" else float(mix.get("pan", 0.0))
            send = float(mix.get("spring", 0.0)) + 0.5 * float(mix.get("reverb", 0.0))
            gl, gr = np.cos((pan + 1) * np.pi / 4) * np.sqrt(2), np.sin((pan + 1) * np.pi / 4) * np.sqrt(2)
            glide_ok = (EL.tone(self.chans[base]) or {}).get("glide", 0) > 0 if base in self.chans else False
            for (t, d, q, v, o) in notes:
                if not t0 <= t < t0 + n * 4:
                    continue
                prev = self.prev.get(name)
                glide = prev[1] if glide_ok and prev and t - prev[0] < 0.1 else None
                self.prev[name] = (t + d, q)
                y = self._note(base, int(q), float(v), d * self.beat, glide) * g
                i = int(((t - t0) + o) * self.beat * SR)
                if i < 0:
                    continue
                m = min(len(y), len(out) - i)
                out[i:i + m, 0] += y[:m] * gl
                out[i:i + m, 1] += y[:m] * gr
                if send:
                    wet[i:i + m] += y[:m] * send
        for (t, d, gm, v, o) in self.perf["drums"]:
            if not t0 <= t < t0 + n * 4 or "drums" in self.mutes:
                continue
            snd = kit["map"].get(gm) or GM_TO_SOUND.get(gm, "rim")
            y, stem = self._hit(snd, float(v))
            sm = kit["stems"].get(stem, {})
            g = 10 ** (sm.get("gain_db", -10) / 20) * 1.6
            pan = float(sm.get("pan", 0.0))
            i = int(((t - t0) + o) * self.beat * SR)
            m = min(len(y), len(out) - max(0, i))
            if i < 0 or m <= 0:
                continue
            out[i:i + m, 0] += y[:m] * g * np.cos((pan + 1) * np.pi / 4) * np.sqrt(2)
            out[i:i + m, 1] += y[:m] * g * np.sin((pan + 1) * np.pi / 4) * np.sqrt(2)
            wet[i:i + m] += y[:m] * g * float(sm.get("sends", {}).get("spring", 0.0))
        from scipy.signal import oaconvolve
        w = oaconvolve(wet, self.ir)[: len(out)].astype(np.float32) * 0.5
        out[:, 0] += w
        out[:, 1] += w * 0.9
        return out

    def next_block(self) -> tuple[int, np.ndarray]:
        """(first bar, audio) for the next `lookahead` bars; tails of earlier bars are mixed in."""
        with self.lock:
            if self.bar >= self.bars:                 # the song is over: the next Bounty
                nb = EL.bounty_int(self.pl["bounty"]) + 1
                self.load(str(nb), length=self.pl["length"], reharm=self.pl["reharm"])
            b0, n = self.bar, min(self.ahead, self.bars - self.bar)
            x = self.render_bars(b0, n)
            L = n * self.bar_n
            m = min(len(self.tail), len(x))
            x[:m] += self.tail[:m]
            self.tail = x[L:].copy()
            self.bar += n
            y = x[:L]
            y = np.tanh(y * 1.1) / 1.1                   # a soft ceiling, not a mastering chain
            return b0, y.astype(np.float32)

    def seek(self, bar: int):
        with self.lock:
            self.bar = max(0, min(self.bars - 1, bar))
            self.tail = np.zeros((0, 2), np.float32)
            self.prev.clear()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bounty", default="1969")
    ap.add_argument("--bars", type=int, default=16)
    ap.add_argument("--wav", type=Path, default=Path("live-take.wav"))
    ap.add_argument("--set", action="append", default=[], help="BAR:[channel.]knob=value, e.g. 9:density=0.9")
    a = ap.parse_args()
    lv = Live(a.bounty)
    sets = []
    for s in a.set:
        bar, rest = s.split(":", 1)
        k, v = rest.split("=", 1)
        ch, _, knob = k.rpartition(".")
        val = v if knob == "gate" else (v.lower() == "true") if knob == "mute" else float(v)
        sets.append((int(bar), knob, val, ch or None))
    chunks = []
    while lv.bar < a.bars:
        for (bar, knob, val, ch) in sets:
            if lv.bar <= bar - 1 < lv.bar + lv.ahead:
                lv.turn(knob, val, ch, at_bar=bar - 1)
        b0, y = lv.next_block()
        chunks.append(y)
        print(f"bars {b0 + 1}-{b0 + len(y) // lv.bar_n}: {lv.section_at(b0)['name']}")
    x = np.concatenate(chunks)
    import wave
    with wave.open(str(a.wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    print(f"wrote {a.wav} ({len(x) / SR:.1f} s); your moves: {lv.user_moves}")


if __name__ == "__main__":
    main()
