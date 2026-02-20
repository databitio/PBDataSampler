from __future__ import annotations

import logging
from pathlib import Path

from ppa_frame_sampler.config import FilterThresholds
from ppa_frame_sampler.filter import metrics as M
from ppa_frame_sampler.filter.models import FilterDecision, FilterMetrics

log = logging.getLogger("ppa_frame_sampler")


def evaluate_burst(
    frame_paths: list[Path],
    thresholds: FilterThresholds,
    analysis_resize_width: int,
    analysis_frame_count: int,
) -> FilterDecision:
    """Analyse a subset of frames and return accept/reject with metrics and reason."""
    if not frame_paths:
        return FilterDecision(
            accepted=False,
            reason="no_frames",
            metrics=FilterMetrics(0.0, 1.0, 0.0, 1.0),
        )

    # Select evenly-spaced subset for analysis
    subset_paths = _evenly_spaced(frame_paths, analysis_frame_count)
    imgs = M.load_and_resize(subset_paths, analysis_resize_width)

    if len(imgs) < 2:
        return FilterDecision(
            accepted=False,
            reason="insufficient_decoded_frames",
            metrics=FilterMetrics(0.0, 1.0, 0.0, 1.0),
        )

    motion = M.compute_motion_score(imgs)
    static = M.compute_static_score(imgs)
    edge = M.compute_edge_density(imgs[len(imgs) // 2])  # middle frame
    overlay = M.compute_overlay_coverage(imgs)

    scene_cut: float | None = None
    if thresholds.reject_on_scene_cuts:
        scene_cut = M.compute_scene_cut_rate(imgs)

    metrics = FilterMetrics(
        motion_score=round(motion, 4),
        static_score=round(static, 4),
        edge_density=round(edge, 4),
        overlay_coverage=round(overlay, 4),
        scene_cut_rate=round(scene_cut, 4) if scene_cut is not None else None,
    )

    # Decision logic (conservative: all conditions must pass)
    reasons: list[str] = []

    if motion < thresholds.min_motion_score:
        reasons.append(f"low_motion({motion:.3f}<{thresholds.min_motion_score})")

    if static > thresholds.max_static_score:
        reasons.append(f"high_static({static:.3f}>{thresholds.max_static_score})")

    if edge < thresholds.min_edge_density:
        reasons.append(f"low_edge_density({edge:.3f}<{thresholds.min_edge_density})")

    if overlay > thresholds.max_overlay_coverage:
        reasons.append(f"high_overlay({overlay:.3f}>{thresholds.max_overlay_coverage})")

    if thresholds.reject_on_scene_cuts and scene_cut is not None:
        if scene_cut > thresholds.scene_cut_rate_max:
            reasons.append(f"high_scene_cuts({scene_cut:.3f}>{thresholds.scene_cut_rate_max})")

    accepted = len(reasons) == 0
    reason = "accepted" if accepted else "; ".join(reasons)

    log.info(
        "Burst filter: %s — motion=%.3f static=%.3f edge=%.3f overlay=%.3f%s",
        "ACCEPT" if accepted else "REJECT",
        motion, static, edge, overlay,
        f" cuts={scene_cut:.3f}" if scene_cut is not None else "",
    )

    return FilterDecision(accepted=accepted, reason=reason, metrics=metrics)


def _evenly_spaced(items: list[Path], count: int) -> list[Path]:
    """Pick *count* evenly-spaced items from *items*."""
    n = len(items)
    if n <= count:
        return list(items)
    step = (n - 1) / (count - 1)
    return [items[round(i * step)] for i in range(count)]
