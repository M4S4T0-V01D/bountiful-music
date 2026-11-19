#!/usr/bin/env python3
"""Render LMMS's DrumSynth drum-machine patches (TR-909, TR-808, TR-606, TR-77, LinnDrum, CR-78, CR-8000, latin
percussion, R&B, misc percussion) to WAV one-shots, once, through headless LMMS, so the Python renderer can use them.

    ~/Documents/Projects/intelligent-jungle/.venv/bin/python bountiful/drum_machines.py
    -> samples/drummachines/<kit>/<name>.wav   (mono, 44.1 kHz, trimmed, peak -1 dBFS)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
sys.path.insert(0, str(paths.ENGINE))
from engine import lmms as LM  # noqa: E402

SRC = paths.LMMS_SAMPLES / "drumsynth"
OUT = paths.SAMPLES / "drummachines"
KITS = ["tr909", "tr808", "tr606", "tr77", "linn", "cr78", "cr8000", "latin", "r_n_b", "misc_perc", "acoustic"]
SR = 44100


def main():
    todo = []
    for kit in KITS:
        for ds in sorted((SRC / kit).glob("*.ds")):
            name = re.sub(r"[^A-Za-z0-9_-]+", "_", ds.stem).strip("_").lower()
            out = OUT / kit / f"{name}.wav"
            if not out.exists():
                todo.append((kit, ds, out))
    print(f"{len(todo)} patches to render", flush=True)
    for i in range(0, len(todo), 12):
        batch = todo[i:i + 12]
        parts = {f"p{j}": ({"sample": f"drumsynth/{kit}/{ds.name}", "root": 69, "vol": 100}, [(0, LM.TPB * 3, 69 - 12, 100)])
                 for j, (kit, ds, out) in enumerate(batch)}
        try:
            res = LM.render_parts(parts, 120, int(3.0 * SR), SR, timeout=300)
        except Exception as ex:
            print("  batch failed:", str(ex)[:200])
            continue
        for j, (kit, ds, out) in enumerate(batch):
            x = res.get(f"p{j}")
            if x is None:
                continue
            m = x.mean(1)
            pk = np.abs(m).max()
            if pk < 1e-4:
                print(f"  silent: {kit}/{ds.name}")
                continue
            on = int(np.argmax(np.abs(m) > pk * 0.02))
            env = np.abs(m)
            last = len(m) - int(np.argmax(env[::-1] > pk * 0.001))
            m = m[max(0, on - 16):last]
            fade = min(len(m), int(0.005 * SR))
            m[-fade:] *= np.linspace(1, 0, fade)
            out.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(out), (m / pk * 0.89).astype(np.float32), SR, subtype="PCM_24")
        print(f"  {min(i + 12, len(todo))}/{len(todo)}", flush=True)
    for kit in KITS:
        files = sorted((OUT / kit).glob("*.wav"))
        print(f"{kit:10s} {len(files):3d}: " + " ".join(f.stem for f in files)[:150])


if __name__ == "__main__":
    main()
