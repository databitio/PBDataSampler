from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FilterMetrics:
    motion_score: float
    static_score: float
    edge_density: float
    overlay_coverage: float
    scene_cut_rate: float | None = None


@dataclass(frozen=True)
class FilterDecision:
    accepted: bool
    reason: str
    metrics: FilterMetrics
