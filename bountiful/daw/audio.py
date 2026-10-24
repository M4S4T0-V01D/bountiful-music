"""Sound for the DAW: one output stream (PortAudio via sounddevice) and sources it plays.

A feeder thread renders the source a little ahead (blocks of BLOCK frames into a queue); the audio callback only
copies from the queue, so a slow render never clicks. Sources:
  StemsSource   a track's stems, mixed live (gain, pan, mute, solo per stem, meters), or its mastered export
  ArraySource   audio in memory (an idea's audition)
  LiveSource    the live Electronium (live.Live), bar by bar
"""
from __future__ import annotations

import collections
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf

BLOCK = 2048


def soft_clip(x: np.ndarray, knee: float = 0.85) -> np.ndarray:
    """Untouched below the knee, a smooth ceiling at 1.0 above it."""
    a = np.abs(x)
    over = a > knee
    if over.any():
        x = x.copy()
        x[over] = np.sign(x[over]) * (knee + (1 - knee) * np.tanh((a[over] - knee) / (1 - knee)))
    return x


class Source:
    sr = 44100
    ahead_s = 0.35                   # how far ahead the feeder renders
    length: int | None = None        # frames, None = endless

    def render(self, pos: int, n: int) -> np.ndarray:
        raise NotImplementedError

    def meters(self) -> dict:
        return {}

    def close(self):
        ...


class ArraySource(Source):
    def __init__(self, x: np.ndarray, sr: int = 44100):
        x = np.asarray(x, np.float32)
        self.x = np.stack([x, x], 1) if x.ndim == 1 else x
        self.sr, self.length = sr, len(self.x)

    def render(self, pos, n):
        y = np.zeros((n, 2), np.float32)
        seg = self.x[pos:pos + n]
        y[: len(seg)] = seg
        return y


class StemsSource(Source):
    """The stems of a rendered track mixed as you set them, or (master=True) the mastered export."""

    def __init__(self, stems: dict[str, Path], master: Path | None = None, makeup: float = 1.0):
        self.files = {k: sf.SoundFile(str(p)) for k, p in sorted(stems.items())}
        self.master_file = sf.SoundFile(str(master)) if master and master.exists() else None
        any_f = next(iter(self.files.values()), None) or self.master_file
        if any_f is None:
            raise ValueError("nothing to play: the track has no stems or export yet (render it first)")
        self.sr = any_f.samplerate
        self.length = max(f.frames for f in [*self.files.values(), *([self.master_file] if self.master_file else [])])
        self.makeup = makeup
        self.gain = {k: 1.0 for k in self.files}
        self.pan = {k: 0.0 for k in self.files}
        self.mute: set[str] = set()
        self.solo: set[str] = set()
        self.master = not self.files
        self.lock = threading.Lock()
        self._meters: dict[str, float] = {}

    @staticmethod
    def _read(f: sf.SoundFile, pos: int, n: int) -> np.ndarray:
        if pos >= f.frames:
            return np.zeros((n, 2), np.float32)
        f.seek(pos)
        y = f.read(n, dtype="float32", always_2d=True)
        if y.shape[1] == 1:
            y = np.repeat(y, 2, 1)
        if len(y) < n:
            y = np.vstack([y, np.zeros((n - len(y), 2), np.float32)])
        return y[:, :2]

    def render(self, pos, n):
        with self.lock:
            if self.master and self.master_file is not None:
                y = self._read(self.master_file, pos, n)
                self._meters = {"master": float(np.abs(y).max(initial=0))}
                return y
            out = np.zeros((n, 2), np.float32)
            meters = {}
            for k, f in self.files.items():
                on = (k in self.solo) if self.solo else (k not in self.mute)
                if not on:
                    meters[k] = 0.0
                    continue
                y = self._read(f, pos, n) * self.gain[k]
                p = self.pan[k]
                if p:
                    y[:, 0] *= min(1.0, 1 - p)
                    y[:, 1] *= min(1.0, 1 + p)
                meters[k] = float(np.abs(y).max(initial=0))
                out += y
            out = soft_clip(out * self.makeup)
            meters["master"] = float(np.abs(out).max(initial=0))
            self._meters = meters
            return out

    def meters(self):
        return dict(self._meters)

    def bounce(self, path: Path, log=print) -> Path:
        """The mix as you set it, to a WAV (24-bit)."""
        with sf.SoundFile(str(path), "w", self.sr, 2, "PCM_24") as w:
            for pos in range(0, self.length, self.sr * 10):
                w.write(self.render(pos, min(self.sr * 10, self.length - pos)))
        log(f"bounced the mix to {path}")
        return path

    def close(self):
        for f in self.files.values():
            f.close()
        if self.master_file:
            self.master_file.close()


class LiveSource(Source):
    ahead_s = 0.9

    def __init__(self, live):
        self.live = live
        self.sr = 44100
        self.fifo = np.zeros((0, 2), np.float32)
        self.marks: list[tuple[int, int, str]] = []      # (frame, bar, bounty) where blocks start
        self.made = 0

    def render(self, pos, n):
        while len(self.fifo) < n:
            b0, y = self.live.next_block()
            self.marks.append((self.made + len(self.fifo), b0, str(self.live.pl["bounty"])))
            self.marks = self.marks[-64:]
            self.fifo = np.vstack([self.fifo, y])
        out, self.fifo = self.fifo[:n], self.fifo[n:]
        self.made += n
        return out

    def bar_at(self, frame: int) -> tuple[int, str] | None:
        """(bar, bounty) heard at a frame."""
        best = None
        for (f, b, bty) in self.marks:
            if f <= frame:
                best = (b + (frame - f) // self.live.bar_n, bty)
        return best


class Player:
    """Plays one source at a time. pos is the frame being heard (roughly: the device's latency is not counted)."""

    def __init__(self, log=print):
        self.log = log
        self.src: Source | None = None
        self.stream = None
        self.sr = None
        self.playing = False
        self.pos = 0                 # heard
        self.fpos = 0                # rendered up to
        self.q: collections.deque = collections.deque()
        self.cur = np.zeros((0, 2), np.float32)
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.ended = False
        self.volume = 1.0
        self.error = None
        self._meters: dict = {}
        self.feeder = threading.Thread(target=self._feed, daemon=True)
        self.feeder.start()

    # ---- control
    def set_source(self, src: Source | None, pos: int = 0):
        with self.lock:
            old, self.src = self.src, src
            self.q.clear()
            self.cur = np.zeros((0, 2), np.float32)
            self.pos = self.fpos = pos
            self.ended = False
            self.playing = False
        if old is not None and old is not src:
            old.close()
        if src is not None:
            self._open(src.sr)
        self.wake.set()

    def play(self):
        if self.src is None:
            return
        if self.src.length is not None and self.pos >= self.src.length:
            self.seek(0)
        self.ended = False
        self.playing = True
        self.wake.set()

    def pause(self):
        self.playing = False

    def stop(self):
        self.playing = False
        self.seek(0)

    def seek(self, frame: int):
        with self.lock:
            if self.src is not None and self.src.length is None:      # live: there is only now
                return
            if self.src is not None:
                frame = max(0, min(int(frame), self.src.length))
            self.q.clear()
            self.cur = np.zeros((0, 2), np.float32)
            self.pos = self.fpos = int(frame)
        self.wake.set()

    def invalidate(self):
        """The mix changed: re-render what's queued (from the heard position)."""
        self.seek(self.pos)

    def meters(self) -> dict:
        return dict(self._meters)

    def close(self):
        self.playing = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                ...
        self.stream = None

    # ---- the threads
    def _open(self, sr: int):
        if self.stream is not None and self.sr == sr:
            return
        self.close()
        try:
            import sounddevice as sd
            self.stream = sd.OutputStream(samplerate=sr, channels=2, dtype="float32", blocksize=2048, callback=self._cb, latency=0.1)
            self.stream.start()
            self.sr = sr
            self.error = None
        except Exception as e:           # no sound device: the app still works, silently
            self.stream, self.error = None, str(e)
            self.log(f"audio: {e}")

    def _feed(self):
        while True:
            self.wake.wait(0.05)
            self.wake.clear()
            while True:
                with self.lock:
                    src = self.src
                    queued = sum(len(b[1]) for b in self.q) + len(self.cur)
                    if src is None or queued >= src.ahead_s * src.sr or (src.length is not None and self.fpos >= src.length):
                        break
                    if not self.playing and queued >= BLOCK * 2:
                        break
                    fpos = self.fpos
                try:
                    y = src.render(fpos, BLOCK)
                except Exception as e:
                    self.log(f"audio source: {e}")
                    self.playing = False
                    break
                m = src.meters()
                with self.lock:
                    if src is self.src and fpos == self.fpos:
                        self.q.append((fpos, y, m))
                        self.fpos += BLOCK

    def _cb(self, outdata, frames, t, status):
        if not self.playing or self.src is None:
            outdata.fill(0)
            return
        out = np.zeros((frames, 2), np.float32)
        k = 0
        with self.lock:
            while k < frames:
                if not len(self.cur):
                    if not self.q:
                        break
                    _, self.cur, self._meters = self.q.popleft()
                take = min(frames - k, len(self.cur))
                out[k:k + take] = self.cur[:take]
                self.cur = self.cur[take:]
                k += take
            self.pos += k
            if self.src.length is not None and self.pos >= self.src.length:
                self.playing, self.ended = False, True
        self.wake.set()
        outdata[:] = out * self.volume


def wait_until(cond, timeout=5.0):
    t = time.time()
    while not cond() and time.time() - t < timeout:
        time.sleep(0.02)
    return cond()
