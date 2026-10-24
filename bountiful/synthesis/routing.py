"""Composable engines: a routing graph renders several engines block by block, feeding audio between them.

    g = Graph({"nodes": {"src": {"engine": "phase_garden", "preset": "bloom"},
                         "eco": {"engine": "echo", "preset": "tuned-coral", "input": 1.0}},
               "edges": [{"from": "src", "to": "eco", "gain": 0.8},
                         {"from": "eco", "to": "src", "gain": 0.3, "feedback": true}],
               "out": {"src": 0.6, "eco": 0.8}})
    y = g.render({"src": events}, n, bpm=120)

  edges     plain edges must form a DAG (Graph raises on a cycle, naming it). A feedback edge may close a loop: it
            carries the source's previous block, its gain is capped at FEEDBACK_MAX and it passes through tanh, so
            a loop cannot run away.
  nodes     {engine, preset?, params?, seed?, automation?, modulation?}; a node only hears inputs if its engine has
            the "audio_in" capability (others ignore them).
  out       node -> gain into the stereo sum (default: every sink at 1).
Deterministic: node seeds derive from the graph seed and the node name.
"""
from __future__ import annotations

import numpy as np

import synthesis as S
from synthesis.engine_api import BLOCK
from synthesis.modulation import Matrix, stable_seed

FEEDBACK_MAX = 0.9


class CycleError(ValueError):
    pass


def topo(nodes: list, edges: list) -> list:
    """Kahn's order over the non-feedback edges; raises CycleError naming the nodes left in a loop."""
    indeg = {n: 0 for n in nodes}
    for e in edges:
        if not e.get("feedback"):
            indeg[e["to"]] += 1
    order = [n for n in nodes if indeg[n] == 0]
    i = 0
    while i < len(order):
        for e in edges:
            if not e.get("feedback") and e["from"] == order[i]:
                indeg[e["to"]] -= 1
                if indeg[e["to"]] == 0:
                    order.append(e["to"])
        i += 1
    if len(order) != len(nodes):
        loop = sorted(n for n in nodes if n not in order)
        raise CycleError(f"routing cycle through {', '.join(loop)}: mark one edge feedback = true")
    return order


class Graph:
    def __init__(self, spec: dict, seed: int = 0, sr: int = S.SR):
        self.spec = spec
        self.seed = seed
        self.nodes = {}
        for name, nd in spec.get("nodes", {}).items():
            e = S.create(nd["engine"], nd.get("preset"), nd.get("params"), nd.get("seed", stable_seed(seed, name)), sr)
            self.nodes[name] = (e, nd)
        self.edges = []
        for ed in spec.get("edges", []):
            if ed["from"] not in self.nodes or ed["to"] not in self.nodes:
                raise KeyError(f"edge {ed['from']} -> {ed['to']}: no such node")
            if ed["from"] == ed["to"] and not ed.get("feedback"):
                raise CycleError(f"{ed['from']} routes into itself: mark it feedback = true")
            g = float(ed.get("gain", 1.0))
            if ed.get("feedback"):
                g = float(np.clip(g, -FEEDBACK_MAX, FEEDBACK_MAX))
            self.edges.append({**ed, "gain": g})
        self.order = topo(list(self.nodes), self.edges)
        sinks = [n for n in self.nodes if not any(e["from"] == n and not e.get("feedback") for e in self.edges)]
        self.out = spec.get("out") or {n: 1.0 for n in sinks}

    def render(self, events: dict, n: int, bpm: float = 120.0, t0_beats: float = 0.0, block: int = BLOCK) -> np.ndarray:
        for name, (e, nd) in self.nodes.items():
            e.begin(events.get(name, []), bpm, nd.get("automation"), Matrix.from_json(nd.get("modulation")), t0_beats)
        prev = {k: np.zeros((block, 2), np.float32) for k in self.nodes}
        out = np.zeros((n, 2), np.float32)
        for i in range(0, n, block):
            m = min(block, n - i)
            cur: dict = {}
            for name in self.order:
                e, nd = self.nodes[name]
                inp = np.zeros((m, 2), np.float32)
                heard = False
                for ed in self.edges:
                    if ed["to"] != name:
                        continue
                    heard = True
                    if ed.get("feedback"):
                        inp += np.tanh(prev[ed["from"]][:m] * ed["gain"])
                    else:
                        inp += cur[ed["from"]] * ed["gain"]
                live = heard and "audio_in" in e.CAPS
                cur[name] = e.block(m, inp * nd.get("input", 1.0) if live else None)
            for name, g in self.out.items():
                out[i:i + m] += cur[name] * g
            for k, y in cur.items():
                prev[k] = np.pad(y, ((0, block - m), (0, 0))) if m < block else y
        return out

    def diagnostics(self) -> dict:
        return {k: e.diagnostics() for k, (e, _) in self.nodes.items()}

    def snapshot(self) -> dict:
        return {k: e.snapshot() for k, (e, _) in self.nodes.items()}

    def restore(self, snap: dict) -> None:
        for k, s in snap.items():
            if k in self.nodes:
                self.nodes[k][0].restore(s)
