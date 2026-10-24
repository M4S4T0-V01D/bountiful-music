#!/usr/bin/env python3
"""Try composer settings and measure their effect on the tells (10 seeds each, same seeds for every variant).
    python tools/experiment.py styles/soviet-synthpop-86.json"""
import json, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from tells import tells
import am2mid
ROOT = Path(__file__).resolve().parent.parent
base = json.loads(Path(sys.argv[1]).read_text())
VARIANTS = {
  "base": {},
  "no passing/neighbour chords": {"passingChordsLikelihoods": [0], "neighbourChordsLikelihoods": [0]},
  "long harmony": {"harmonyLengthLikelihoods": [{"8": 1, "16": 1}]},
  "prolong harmony": {"prolongHarmonyPartBiases": [80], "prolongStaticLikelihoods": [6], "prolongDynamicLikelihoods": [1]},
  "small melody shape": {"melodyShapeAmpRanges": [[2, 4]]},
  "no leading tone": {"raiseLeadingInMinorProbabilities": [0]},
  "no triplets": {"melodyMotifZone1TripletLikelihoods": [0]},
  "slower motif rhythm": {"melodyMotifRythmCountIncreasePerIndex": 0.1, "melodyMotifRythmCountIncreaseOffsetRange": [0.2, 0.4]},
}
seeds = [11, 22, 33, 44, 55, 66, 77, 88, 99, 111]
for name, ov in VARIANTS.items():
    st = dict(base, **ov)
    with tempfile.TemporaryDirectory() as d:
        sp = Path(d) / "s.json"; sp.write_text(json.dumps(st))
        subprocess.run(["node", str(ROOT / "tools/gen.js"), "--style", str(sp), "--out", d] + sum([["--seed", str(s)] for s in seeds], []),
                       check=True, capture_output=True)
        rows = []
        for f in Path(d).glob("*.am.json"):
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                m = am2mid.convert(f)
            rows.append(tells(m))
    keys = ["octave doubling", "leaps > 5th", "melody notes/bar", "fast notes", "chord changes/bar", "leading-tone bars"]
    print(f"{name:30s} " + "  ".join(f"{k.split()[0][:7]} {np.mean([r.get(k, np.nan) for r in rows]):5.2f}" for k in keys))
