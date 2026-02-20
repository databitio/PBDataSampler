from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def load_and_resize(paths: list[Path], width: int) -> list[np.ndarray]:
    """Load images from *paths* and resize to *width* (preserving aspect ratio)."""
    imgs: list[np.ndarray] = []
    for p in paths:
        img = cv2.imread(str(p), cv2.IMREAD_COLOR)
        if img is None:
            continue
        h, w = img.shape[:2]
        if w > width:
            scale = width / float(w)
            img = cv2.resize(img, (width, int(h * scale)), interpolation=cv2.INTER_AREA)
        imgs.append(img)
    return imgs


def compute_motion_score(imgs: list[np.ndarray]) -> float:
    """Mean absolute difference between consecutive grayscale frames, normalised to [0, 1]."""
    if len(imgs) < 2:
        return 0.0

    diffs: list[float] = []
    prev_gray = cv2.cvtColor(imgs[0], cv2.COLOR_BGR2GRAY).astype(np.float32)
    for img in imgs[1:]:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        diff = np.mean(np.abs(gray - prev_gray)) / 255.0
        diffs.append(float(diff))
        prev_gray = gray

    return float(np.mean(diffs))


def compute_static_score(imgs: list[np.ndarray], diff_thresh: float = 2.0) -> float:
    """Fraction of consecutive frame pairs whose mean abs diff is below *diff_thresh*."""
    if len(imgs) < 2:
        return 1.0

    static_pairs = 0
    total_pairs = 0
    prev_gray = cv2.cvtColor(imgs[0], cv2.COLOR_BGR2GRAY).astype(np.float32)
    for img in imgs[1:]:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        mean_diff = np.mean(np.abs(gray - prev_gray))
        if mean_diff < diff_thresh:
            static_pairs += 1
        total_pairs += 1
        prev_gray = gray

    return static_pairs / max(total_pairs, 1)


def compute_edge_density(img: np.ndarray) -> float:
    """Ratio of Canny edge pixels to total pixels."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    return float(np.count_nonzero(edges)) / float(edges.size)


def compute_overlay_coverage(imgs: list[np.ndarray], var_thresh: float = 2.0) -> float:
    """Fraction of pixels with near-zero variance across frames (static overlays)."""
    if len(imgs) < 2:
        return 0.0

    grays = [cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) for img in imgs]
    stack = np.stack(grays, axis=0)  # (N, H, W)
    pixel_var = np.var(stack, axis=0)  # (H, W)
    static_fraction = float(np.mean(pixel_var < var_thresh))
    return static_fraction


def compute_scene_cut_rate(imgs: list[np.ndarray], cut_thresh: float = 0.35) -> float:
    """Fraction of consecutive frame transitions that look like scene cuts.

    Uses normalised histogram correlation; a low correlation indicates a cut.
    """
    if len(imgs) < 2:
        return 0.0

    cuts = 0
    total = 0

    prev_hist = _color_histogram(imgs[0])
    for img in imgs[1:]:
        cur_hist = _color_histogram(img)
        corr = cv2.compareHist(prev_hist, cur_hist, cv2.HISTCMP_CORREL)
        if corr < (1.0 - cut_thresh):
            cuts += 1
        total += 1
        prev_hist = cur_hist

    return cuts / max(total, 1)


def _color_histogram(img: np.ndarray) -> np.ndarray:
    """Compute a normalised colour histogram for *img*."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist
