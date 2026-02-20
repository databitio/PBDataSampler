"""Unit tests for court-presence scoring heuristics using synthetic images."""
from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np

from ppa_frame_sampler.filter.court_scorer import (
    CourtScore,
    compute_blur_score,
    compute_court_color_ratio,
    compute_line_density,
    compute_overlay_penalty,
    pick_best_frame,
    score_frame,
)


# ---------------------------------------------------------------------------
# Synthetic image helpers
# ---------------------------------------------------------------------------

def _make_court_image(h: int = 480, w: int = 640) -> np.ndarray:
    """Blue background with white lines — mimics a pickleball court."""
    # Blue court surface (BGR: blue channel high)
    img = np.full((h, w, 3), (200, 100, 30), dtype=np.uint8)  # bright blue in BGR
    # Draw white court lines
    cv2.line(img, (50, 100), (590, 100), (255, 255, 255), 2)
    cv2.line(img, (50, 380), (590, 380), (255, 255, 255), 2)
    cv2.line(img, (50, 100), (50, 380), (255, 255, 255), 2)
    cv2.line(img, (590, 100), (590, 380), (255, 255, 255), 2)
    cv2.line(img, (320, 100), (320, 380), (255, 255, 255), 2)
    cv2.line(img, (50, 240), (590, 240), (255, 255, 255), 2)
    return img


def _make_blank_image(h: int = 480, w: int = 640) -> np.ndarray:
    """Solid gray image — no court features."""
    return np.full((h, w, 3), (128, 128, 128), dtype=np.uint8)


def _make_noisy_image(h: int = 480, w: int = 640, seed: int = 42) -> np.ndarray:
    """Random noise image — some edges but no court structure."""
    rng = np.random.RandomState(seed)
    return rng.randint(0, 256, (h, w, 3), dtype=np.uint8)


def _write_image(directory: Path, name: str, img: np.ndarray) -> Path:
    p = directory / name
    cv2.imwrite(str(p), img)
    return p


# ---------------------------------------------------------------------------
# compute_line_density
# ---------------------------------------------------------------------------

class TestLineDensity:

    def test_court_image_has_lines(self):
        court = _make_court_image()
        gray = cv2.cvtColor(court, cv2.COLOR_BGR2GRAY)
        density = compute_line_density(gray)
        assert density > 0.0, "Court image should have detectable lines"

    def test_blank_image_has_no_lines(self):
        blank = _make_blank_image()
        gray = cv2.cvtColor(blank, cv2.COLOR_BGR2GRAY)
        density = compute_line_density(gray)
        assert density == 0.0, "Blank image should have zero line density"


# ---------------------------------------------------------------------------
# compute_court_color_ratio
# ---------------------------------------------------------------------------

class TestCourtColorRatio:

    def test_blue_court_detected(self):
        court = _make_court_image()
        ratio = compute_court_color_ratio(court)
        assert ratio > 0.3, "Blue court should have high court color ratio"

    def test_gray_image_low_ratio(self):
        blank = _make_blank_image()
        ratio = compute_court_color_ratio(blank)
        assert ratio < 0.1, "Gray image should have near-zero court color ratio"


# ---------------------------------------------------------------------------
# compute_blur_score
# ---------------------------------------------------------------------------

class TestBlurScore:

    def test_sharp_image_high_score(self):
        court = _make_court_image()
        gray = cv2.cvtColor(court, cv2.COLOR_BGR2GRAY)
        score = compute_blur_score(gray)
        assert score > 0.0, "Sharp court image should have positive blur score"

    def test_blank_image_zero_score(self):
        blank = _make_blank_image()
        gray = cv2.cvtColor(blank, cv2.COLOR_BGR2GRAY)
        score = compute_blur_score(gray)
        assert score == 0.0, "Solid color image should have zero Laplacian variance"


# ---------------------------------------------------------------------------
# compute_overlay_penalty
# ---------------------------------------------------------------------------

class TestOverlayPenalty:

    def test_blank_image_low_penalty(self):
        blank = _make_blank_image()
        gray = cv2.cvtColor(blank, cv2.COLOR_BGR2GRAY)
        penalty = compute_overlay_penalty(gray)
        assert penalty == 0.0, "Blank image should have no overlay penalty"

    def test_noisy_image_has_penalty(self):
        noisy = _make_noisy_image()
        gray = cv2.cvtColor(noisy, cv2.COLOR_BGR2GRAY)
        penalty = compute_overlay_penalty(gray)
        assert penalty > 0.0, "Noisy image should have some overlay penalty"


# ---------------------------------------------------------------------------
# score_frame
# ---------------------------------------------------------------------------

class TestScoreFrame:

    def test_returns_court_score(self):
        court = _make_court_image()
        sc = score_frame(court)
        assert isinstance(sc, CourtScore)
        assert 0.0 <= sc.composite <= 1.0

    def test_court_scores_higher_than_blank(self):
        court = _make_court_image()
        blank = _make_blank_image()
        court_sc = score_frame(court)
        blank_sc = score_frame(blank)
        assert court_sc.composite > blank_sc.composite

    def test_resize_applied(self):
        # Large image should still work with resize
        big = _make_court_image(h=1080, w=1920)
        sc = score_frame(big, resize_width=320)
        assert isinstance(sc, CourtScore)


# ---------------------------------------------------------------------------
# pick_best_frame
# ---------------------------------------------------------------------------

class TestPickBestFrame:

    def test_selects_court_over_blank(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            p_blank = _write_image(d, "blank.jpg", _make_blank_image())
            p_court = _write_image(d, "court.jpg", _make_court_image())
            p_noise = _write_image(d, "noise.jpg", _make_noisy_image())

            result = pick_best_frame([p_blank, p_court, p_noise])
            assert result is not None
            best_path, best_score = result
            assert best_path == p_court
            assert best_score.composite > 0.0

    def test_empty_list_returns_none(self):
        result = pick_best_frame([])
        assert result is None

    def test_missing_file_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            p_court = _write_image(d, "court.jpg", _make_court_image())
            p_missing = d / "missing.jpg"

            result = pick_best_frame([p_missing, p_court])
            assert result is not None
            best_path, _ = result
            assert best_path == p_court
