from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("ppa_frame_sampler")


@dataclass(frozen=True)
class CourtScore:
    line_density: float       # Hough line pixel coverage [0,1]
    court_color_ratio: float  # Fraction of court-colored pixels [0,1]
    blur_score: float         # Laplacian variance (higher = sharper)
    overlay_penalty: float    # Edge density in scoreboard bands [0,1]
    composite: float          # Weighted combination [0,1]


# ── Individual metric functions ─────────────────────────────────────


def compute_line_density(gray: np.ndarray) -> float:
    """Canny + HoughLinesP, return fraction of image pixels covered by lines."""
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges, rho=1, theta=np.pi / 180, threshold=50,
        minLineLength=40, maxLineGap=10,
    )
    if lines is None:
        return 0.0

    h, w = gray.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    for line in lines:
        x1, y1, x2, y2 = line[0]
        cv2.line(mask, (x1, y1), (x2, y2), 255, thickness=1)

    return float(np.count_nonzero(mask)) / float(mask.size)


def compute_court_color_ratio(bgr: np.ndarray) -> float:
    """Fraction of pixels matching common pickleball court colors (blue/green/orange) in HSV."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    # Blue courts (H ~100-130)
    blue_mask = cv2.inRange(hsv, (90, 40, 40), (130, 255, 255))
    # Green courts (H ~35-85)
    green_mask = cv2.inRange(hsv, (35, 40, 40), (85, 255, 255))
    # Orange/tan courts (H ~10-25)
    orange_mask = cv2.inRange(hsv, (10, 40, 40), (25, 255, 255))

    combined = cv2.bitwise_or(blue_mask, cv2.bitwise_or(green_mask, orange_mask))
    return float(np.count_nonzero(combined)) / float(combined.size)


def compute_blur_score(gray: np.ndarray) -> float:
    """Laplacian variance — higher means sharper."""
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return float(lap.var())


def compute_overlay_penalty(gray: np.ndarray) -> float:
    """Edge density in top and bottom 15% bands (scoreboard/chyron regions)."""
    h = gray.shape[0]
    band = max(1, int(h * 0.15))

    top_band = gray[:band, :]
    bottom_band = gray[-band:, :]

    top_edges = cv2.Canny(top_band, 50, 150)
    bottom_edges = cv2.Canny(bottom_band, 50, 150)

    top_density = float(np.count_nonzero(top_edges)) / float(top_edges.size)
    bottom_density = float(np.count_nonzero(bottom_edges)) / float(bottom_edges.size)

    return (top_density + bottom_density) / 2.0


# ── Composite scoring ───────────────────────────────────────────────


def score_frame(bgr: np.ndarray, resize_width: int = 640) -> CourtScore:
    """Score a single BGR frame for court presence."""
    h, w = bgr.shape[:2]
    if w > resize_width:
        scale = resize_width / float(w)
        bgr = cv2.resize(bgr, (resize_width, int(h * scale)), interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    line_density = compute_line_density(gray)
    court_color_ratio = compute_court_color_ratio(bgr)
    blur_score = compute_blur_score(gray)
    overlay_penalty = compute_overlay_penalty(gray)

    # Normalise line_density and blur_score to ~[0,1] for composite
    line_norm = min(line_density * 50.0, 1.0)  # 2% coverage → 1.0
    blur_norm = min(blur_score / 500.0, 1.0)   # variance 500 → 1.0

    composite = (
        0.35 * line_norm
        + 0.30 * court_color_ratio
        + 0.20 * blur_norm
        - 0.15 * overlay_penalty
    )
    composite = max(0.0, min(1.0, composite))

    return CourtScore(
        line_density=line_density,
        court_color_ratio=court_color_ratio,
        blur_score=blur_score,
        overlay_penalty=overlay_penalty,
        composite=composite,
    )


def pick_best_frame(
    paths: list[Path], resize_width: int = 640,
) -> tuple[Path, CourtScore] | None:
    """Score all frames, return (path, score) of the best one, or None if no frames."""
    best_path: Path | None = None
    best_score: CourtScore | None = None

    for p in paths:
        img = cv2.imread(str(p), cv2.IMREAD_COLOR)
        if img is None:
            log.warning("Could not read frame: %s", p)
            continue

        sc = score_frame(img, resize_width)
        if best_score is None or sc.composite > best_score.composite:
            best_path = p
            best_score = sc

    if best_path is None or best_score is None:
        return None
    return best_path, best_score
