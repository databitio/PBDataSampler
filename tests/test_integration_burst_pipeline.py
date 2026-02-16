"""Integration tests for the single burst pipeline: extract → filter.

Mocks target the import sites in each module (not the tools module itself),
because each consumer does ``from ppa_frame_sampler.media.tools import …``.
``evaluate_burst`` runs real OpenCV on the synthetic images.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from conftest import (
    build_ffprobe_json,
    make_extract_side_effect,
    noise_frame_writer,
    static_frame_writer,
)
from ppa_frame_sampler.config import FilterThresholds
from ppa_frame_sampler.filter.quality_filter import evaluate_burst
from ppa_frame_sampler.media.extractor import extract_frames
from ppa_frame_sampler.media.ffprobe import probe_fps

EXTRACTOR = "ppa_frame_sampler.media.extractor"
FFPROBE = "ppa_frame_sampler.media.ffprobe"


class TestExtractFrames:
    """extract_frames with mocked run_cmd that writes real images."""

    @patch(f"{EXTRACTOR}.ensure_tool", return_value="/fake/bin/ffmpeg")
    @patch(f"{EXTRACTOR}.run_cmd")
    def test_returns_correct_count(self, mock_run, mock_tool):
        with tempfile.TemporaryDirectory() as td:
            clip = Path(td) / "clip.mp4"
            out = Path(td) / "frames"
            mock_run.side_effect = make_extract_side_effect(
                noise_frame_writer, count=10,
            )

            paths = extract_frames(clip, 10, out, "burst", "jpg")

            assert len(paths) == 10
            assert all(p.exists() for p in paths)
            assert all(p.suffix == ".jpg" for p in paths)

    @patch(f"{EXTRACTOR}.ensure_tool", return_value="/fake/bin/ffmpeg")
    @patch(f"{EXTRACTOR}.run_cmd")
    def test_returns_empty_when_no_output(self, mock_run, mock_tool):
        """ffmpeg produces nothing → empty list."""
        with tempfile.TemporaryDirectory() as td:
            clip = Path(td) / "clip.mp4"
            out = Path(td) / "frames"
            mock_run.side_effect = make_extract_side_effect(
                noise_frame_writer, count=0,
            )

            paths = extract_frames(clip, 10, out, "burst", "jpg")

            assert paths == []


class TestProbeFps:
    """probe_fps with mocked run_cmd_json."""

    @patch(f"{FFPROBE}.ensure_tool", return_value="/fake/bin/ffprobe")
    @patch(f"{FFPROBE}.run_cmd_json")
    def test_parses_fraction(self, mock_json, mock_tool):
        mock_json.return_value = build_ffprobe_json(30000, 1001)

        fps = probe_fps(Path("/fake/clip.mp4"))

        assert abs(fps - 29.97) < 0.1

    @patch(f"{FFPROBE}.ensure_tool", return_value="/fake/bin/ffprobe")
    @patch(f"{FFPROBE}.run_cmd_json")
    def test_fallback_on_bad_json(self, mock_json, mock_tool):
        mock_json.return_value = {"bad": "data"}

        fps = probe_fps(Path("/fake/clip.mp4"))

        assert fps == 30.0


class TestBurstPipeline:
    """Full burst pipeline: extract → evaluate_burst (real OpenCV)."""

    @patch(f"{EXTRACTOR}.ensure_tool", return_value="/fake/bin/ffmpeg")
    @patch(f"{EXTRACTOR}.run_cmd")
    def test_good_burst_accepted(self, mock_run, mock_tool):
        with tempfile.TemporaryDirectory() as td:
            clip = Path(td) / "clip.mp4"
            out = Path(td) / "frames"
            mock_run.side_effect = make_extract_side_effect(
                noise_frame_writer, count=10,
            )

            paths = extract_frames(clip, 10, out, "burst", "jpg")
            decision = evaluate_burst(
                paths,
                thresholds=FilterThresholds(),
                analysis_resize_width=320,
                analysis_frame_count=5,
            )

            assert decision.accepted
            assert decision.reason == "accepted"
            assert decision.metrics.motion_score >= 0.10

    @patch(f"{EXTRACTOR}.ensure_tool", return_value="/fake/bin/ffmpeg")
    @patch(f"{EXTRACTOR}.run_cmd")
    def test_bad_burst_rejected(self, mock_run, mock_tool):
        with tempfile.TemporaryDirectory() as td:
            clip = Path(td) / "clip.mp4"
            out = Path(td) / "frames"
            mock_run.side_effect = make_extract_side_effect(
                static_frame_writer, count=10,
            )

            paths = extract_frames(clip, 10, out, "burst", "jpg")
            decision = evaluate_burst(
                paths,
                thresholds=FilterThresholds(),
                analysis_resize_width=320,
                analysis_frame_count=5,
            )

            assert not decision.accepted
            assert "low_motion" in decision.reason or "high_static" in decision.reason
