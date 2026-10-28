"""Trust-similarity fusion and clustering for Round 2.

Relationship strength fuses two signals with the Hamacher product t-norm:
preference similarity (cosine of midpoint vectors) and normalized trust
(topology in/out-degree blended with credibility). K-Means (k=2) on the
fused rows finds opinion clusters; the silhouette coefficient reports
cluster quality.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

import numpy as np

from .fuzzy import HesitantScore


def similarity_matrix(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    unit = vectors / norms
    sim = unit @ unit.T
    return (sim + 1.0) / 2.0


def trust_matrix(topology: np.ndarray, credibility: Sequence[float]) -> np.ndarray:
    n = topology.shape[0]
    out_deg = topology.sum(axis=1, keepdims=True)
    out_deg[out_deg == 0.0] = 1.0
    topo_norm = topology / out_deg
    cred = np.asarray(list(credibility), dtype=float).reshape(1, n)
    return 0.5 * topo_norm + 0.5 * np.repeat(cred, n, axis=0)


def hamacher(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    denom = a + b - a * b
    denom[denom == 0.0] = 1e-9
    return (a * b) / denom


def fuse(similarity: np.ndarray, trust: np.ndarray) -> np.ndarray:
    fused = hamacher(similarity, trust)
    return (fused + fused.T) / 2.0


def kmeans_pp_init(rng: np.random.Generator, x: np.ndarray, k: int) -> np.ndarray:
    n = x.shape[0]
    first = int(rng.integers(0, n))
    centers = [x[first]]
    for _ in range(1, k):
        d2 = np.min(
            np.stack([np.sum((x - c) ** 2, axis=1) for c in centers]), axis=0
        )
        total = d2.sum()
        probs = d2 / total if total > 0 else np.full(n, 1.0 / n)
        centers.append(x[int(rng.choice(n, p=probs))])
    return np.stack(centers)


def kmeans(
    x: np.ndarray, k: int = 2, seed: int = 7, iters: int = 100
) -> Tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    centers = kmeans_pp_init(rng, x, k)
    labels = np.zeros(x.shape[0], dtype=int)
    for _ in range(iters):
        dists = np.stack(
            [np.sum((x - c) ** 2, axis=1) for c in centers]
        )
        new_labels = np.argmin(dists, axis=0)
        new_centers = np.stack(
            [
                x[new_labels == j].mean(axis=0)
                if np.any(new_labels == j)
                else centers[j]
                for j in range(k)
            ]
        )
        if np.array_equal(new_labels, labels) and np.allclose(
            new_centers, centers
        ):
            labels = new_labels
            centers = new_centers
            break
        labels, centers = new_labels, new_centers
    return labels, centers


def silhouette(x: np.ndarray, labels: np.ndarray) -> float:
    d = np.sqrt(((x[:, None, :] - x[None, :, :]) ** 2).sum(axis=2))
    n = x.shape[0]
    uniq = sorted(set(int(v) for v in labels))
    if len(uniq) < 2:
        return 0.0
    sil = []
    for i in range(n):
        same = [j for j in range(n) if labels[j] == labels[i] and j != i]
        other = [
            min(
                d[i][[j for j in range(n) if labels[j] == c]].mean()
                for c in uniq
                if c != labels[i]
            )
        ]
        a = d[i][same].mean() if same else 0.0
        b = other[0] if other and not math.isnan(other[0]) else 0.0
        denom = max(a, b)
        sil.append((b - a) / denom if denom > 0 else 0.0)
    return float(np.mean(sil))


def preference_vectors(
    positions: Dict[str, Dict[str, HesitantScore]], options: List[str]
) -> Tuple[List[str], np.ndarray]:
    ids = sorted(positions.keys())
    mat = np.array(
        [[positions[aid][opt].midpoint for opt in options] for aid in ids]
    )
    return ids, mat
