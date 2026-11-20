"""Shared action-cluster helper (v3.3): the camera and the elimination wall both track the largest group of alive
heroes packed inside a sliding horizontal window, instead of stretching across a 2000 px spread or chasing one runaway."""
from __future__ import annotations


def action_cluster(xs: list[float], window: float = 750.0, k: int = 6) -> list[int]:
    """Indices (into xs) of the front-most densest group: up to k members inside a `window`-wide span.
    Ties prefer the group further ahead along the course."""
    if not xs:
        return []
    order = sorted(range(len(xs)), key=lambda i: xs[i], reverse=True)
    best: list[int] = []
    for a, i in enumerate(order):
        members = [j for j in order[a:] if xs[i] - xs[j] <= window]
        if len(members) > len(best):
            best = members
    return best[:k]


def cluster_center(xs: list[float], window: float = 750.0, k: int = 6) -> float:
    m = action_cluster(xs, window, k)
    if not m:
        return 0.0
    w = [1.3 if n == 0 else 1.0 for n in range(len(m))]          # the cluster's front-runner pulls slightly
    return sum(xs[j] * wj for j, wj in zip(m, w)) / sum(w)
