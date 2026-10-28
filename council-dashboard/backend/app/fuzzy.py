"""Hesitant fuzzy linguistic scoring for agent positions.

Each agent rates every option with an interval [low, high] on a 0..1 scale.
The hesitation degree is the interval width: a sure agent gives a point,
a torn agent gives a wide band. Uncertainty is mean hesitation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class HesitantScore:
    low: float
    high: float

    def __post_init__(self) -> None:
        lo = min(max(self.low, 0.0), 1.0)
        hi = min(max(self.high, 0.0), 1.0)
        if hi < lo:
            lo, hi = hi, lo
        object.__setattr__(self, "low", lo)
        object.__setattr__(self, "high", hi)

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2.0

    @property
    def hesitation(self) -> float:
        return self.high - self.low


def parse_scores(raw: Dict[str, List[float]]) -> Dict[str, HesitantScore]:
    """Accept {option: [low, high]} or {option: [point]} from model output."""
    out: Dict[str, HesitantScore] = {}
    for option, vals in raw.items():
        if len(vals) >= 2:
            out[option] = HesitantScore(vals[0], vals[1])
        elif vals:
            out[option] = HesitantScore(vals[0], vals[0])
        else:
            out[option] = HesitantScore(0.5, 0.5)
    return out


def uncertainty(scores: Dict[str, HesitantScore]) -> float:
    if not scores:
        return 1.0
    return sum(s.hesitation for s in scores.values()) / len(scores)


def competing_paths(scores: Dict[str, HesitantScore]) -> int:
    """Count options whose midpoint clears 0.5: genuine ambiguity."""
    return sum(1 for s in scores.values() if s.midpoint >= 0.5)
