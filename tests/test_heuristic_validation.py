"""Heuristic validation tests for ``evaluate_burst()`` with real OpenCV
computations on synthetic images.  **No mocking.**

Covers PLAN §14 reqs 4 & 5: known-bad rejection and known-good acceptance.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np

from conftest import make_noise_frames, make_static_frames
from ppa_frame_sampler.config import FilterThresholds
from ppa_frame_sampler.filter.quality_filter import evaluate_burst

THRESH = FilterThresholds()
RESIZE_W = 320
ANALYSIS_N = 5


# ---------------------------------------------------------------------------
# Extra frame generators for specialised scenarios
# ---------------------------------------------------------------------------

def _make_gradient_frames(directory: Path, count: int) -> list[Path]:
    """Identical horizontal gradient images — no motion between frames."""
    directory.mkdir(parents=True, exist_ok=True)
    grad = np.tile(
        np.linspace(0, 255, 320, dtype=np.uint8), (240, 1),
    )
    img = cv2.merge([grad, grad, grad])
    paths = []
    for i in range(count):
        p = directory / f"grad_{i:06d}.jpg"
        cv2.imwrite(str(p), img)
        paths.append(p)
    return paths


def _make_near_black_frames(directory: Path, count: int) -> list[Path]:
    """Near-black frames with tiny random noise — very low edge density."""
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.RandomState(99)
    paths = []
    for i in range(count):
        img = rng.randint(0, 6, (240, 320, 3), dtype=np.uint8)
        p = directory / f"black_{i:06d}.jpg"
        cv2.imwrite(str(p), img)
        paths.append(p)
    return paths


def _make_overlay_frames(directory: Path, count: int) -> list[Path]:
    """White frames with a large static rectangle overlay.

    A fixed 200x300 white block is present on every frame; only a small
    region changes → high overlay coverage.
    """
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.RandomState(7)
    paths = []
    for i in range(count):
        img = np.full((240, 320, 3), 255, dtype=np.uint8)
        # small random patch in bottom-right corner
        img[200:240, 280:320] = rng.randint(0, 256, (40, 40, 3), dtype=np.uint8)
        p = directory / f"overlay_{i:06d}.jpg"
        cv2.imwrite(str(p), img)
        paths.append(p)
    return paths


def _make_shifting_pattern_frames(directory: Path, count: int) -> list[Path]:
    """Geometric pattern with per-frame shift + heavy noise → accepted."""
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.RandomState(12)
    paths = []
    for i in range(count):
        # Start with random noise base for guaranteed edge density
        img = rng.randint(0, 256, (240, 320, 3), dtype=np.uint8)
        # Shifting rectangle for motion
        x_off = (i * 30) % 280
        cv2.rectangle(img, (x_off, 50), (x_off + 40, 190), (0, 200, 100), -1)
        cv2.circle(img, (160, 120), 40 + i * 3, (200, 50, 50), 3)
        # Grid lines for extra edges
        for y in range(0, 240, 20):
            cv2.line(img, (0, y + i * 2), (320, y + i * 2), (255, 255, 255), 1)
        p = directory / f"shift_{i:06d}.jpg"
        cv2.imwrite(str(p), img)
        paths.append(p)
    return paths


def _make_textured_frames(directory: Path, count: int) -> list[Path]:
    """Textured background + strong per-frame perturbation → accepted."""
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.RandomState(33)
    paths = []
    for i in range(count):
        # Per-frame random noise ensures motion AND edge density
        img = rng.randint(0, 256, (240, 320, 3), dtype=np.uint8)
        # Add per-frame shifting structure
        cv2.rectangle(img, (20 + i * 10, 30), (80 + i * 10, 200), (0, 0, 0), 2)
        p = directory / f"tex_{i:06d}.jpg"
        cv2.imwrite(str(p), img)
        paths.append(p)
    return paths


# ===================================================================
# Rejection tests (known-bad inputs)
# ===================================================================

class TestRejection:

    def test_solid_gray_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_static_frames(Path(td), 10, color=(128, 128, 128))
            d = evaluate_burst(paths, THRESH, RESIZE_W, ANALYSIS_N)
            assert not d.accepted
            assert "low_motion" in d.reason or "high_static" in d.reason

    def test_identical_gradient_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _make_gradient_frames(Path(td), 10)
            d = evaluate_burst(paths, THRESH, RESIZE_W, ANALYSIS_N)
            assert not d.accepted

    def test_near_black_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _make_near_black_frames(Path(td), 10)
            d = evaluate_burst(paths, THRESH, RESIZE_W, ANALYSIS_N)
            assert not d.accepted
            assert "low_edge_density" in d.reason or "low_motion" in d.reason

    def test_static_overlay_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _make_overlay_frames(Path(td), 10)
            d = evaluate_burst(paths, THRESH, RESIZE_W, ANALYSIS_N)
            assert not d.accepted


# ===================================================================
# Acceptance tests (known-good inputs)
# ===================================================================

class TestAcceptance:

    def test_random_noise_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_noise_frames(Path(td), 10)
            d = evaluate_burst(paths, THRESH, RESIZE_W, ANALYSIS_N)
            assert d.accepted
            assert d.reason == "accepted"

    def test_shifting_pattern_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _make_shifting_pattern_frames(Path(td), 10)
            d = evaluate_burst(paths, THRESH, RESIZE_W, ANALYSIS_N)
            assert d.accepted

    def test_textured_perturbation_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _make_textured_frames(Path(td), 10)
            d = evaluate_burst(paths, THRESH, RESIZE_W, ANALYSIS_N)
            assert d.accepted


# ===================================================================
# Edge cases
# ===================================================================

class TestEdgeCases:

    def test_single_frame_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_noise_frames(Path(td), 1)
            d = evaluate_burst(paths, THRESH, RESIZE_W, ANALYSIS_N)
            assert not d.accepted
            assert d.reason == "insufficient_decoded_frames"

    def test_empty_list_rejected(self):
        d = evaluate_burst([], THRESH, RESIZE_W, ANALYSIS_N)
        assert not d.accepted
        assert d.reason == "no_frames"

    def test_two_diverse_frames_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_noise_frames(Path(td), 2, seed=77)
            d = evaluate_burst(paths, THRESH, RESIZE_W, ANALYSIS_N)
            assert d.accepted
