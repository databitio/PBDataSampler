"""Tests for CourtConfig and mode-related Config construction."""
from __future__ import annotations

from ppa_frame_sampler.config import Config, CourtConfig


class TestCourtConfigDefaults:

    def test_default_values(self):
        cc = CourtConfig()
        assert cc.court_out_dir == "output/court_detections"
        assert cc.court_frame_format == "jpg"
        assert cc.court_sample_attempts == 5
        assert cc.court_intro_margin_s == 20.0
        assert cc.court_outro_margin_s == 20.0
        assert cc.court_save_manifest is True
        assert cc.court_segment_seconds == 2.0
        assert cc.court_frames_per_attempt == 3
        assert cc.court_resize_width == 640
        assert cc.court_min_score == 0.15

    def test_custom_values(self):
        cc = CourtConfig(
            court_out_dir="/custom/out",
            court_frame_format="png",
            court_sample_attempts=10,
            court_resize_width=320,
        )
        assert cc.court_out_dir == "/custom/out"
        assert cc.court_frame_format == "png"
        assert cc.court_sample_attempts == 10
        assert cc.court_resize_width == 320


class TestConfigMode:

    def test_default_mode_is_clips(self):
        cfg = Config()
        assert cfg.mode == "clips"

    def test_court_frames_mode(self):
        cfg = Config(mode="court-frames")
        assert cfg.mode == "court-frames"

    def test_config_has_default_court_config(self):
        cfg = Config()
        assert isinstance(cfg.court, CourtConfig)
        assert cfg.court.court_sample_attempts == 5

    def test_config_with_custom_court_config(self):
        cc = CourtConfig(court_sample_attempts=8, court_out_dir="/tmp/court")
        cfg = Config(mode="court-frames", court=cc)
        assert cfg.mode == "court-frames"
        assert cfg.court.court_sample_attempts == 8
        assert cfg.court.court_out_dir == "/tmp/court"


class TestCLIParsing:
    """Test that CLI args produce correct Config."""

    def test_mode_flag_parsed(self):
        from ppa_frame_sampler.cli import build_parser
        p = build_parser()

        args = p.parse_args(["--mode", "court-frames"])
        assert args.mode == "court-frames"

    def test_court_flags_parsed(self):
        from ppa_frame_sampler.cli import build_parser
        p = build_parser()

        args = p.parse_args([
            "--mode", "court-frames",
            "--court-out-dir", "/custom/out",
            "--court-frame-format", "png",
            "--court-sample-attempts", "8",
            "--court-intro-margin-s", "30.0",
            "--court-outro-margin-s", "25.0",
            "--no-court-save-manifest",
            "--court-segment-seconds", "3.0",
            "--court-frames-per-attempt", "5",
            "--court-resize-width", "320",
            "--court-min-score", "0.25",
        ])
        assert args.mode == "court-frames"
        assert args.court_out_dir == "/custom/out"
        assert args.court_frame_format == "png"
        assert args.court_sample_attempts == 8
        assert args.court_intro_margin_s == 30.0
        assert args.court_outro_margin_s == 25.0
        assert args.court_save_manifest is False
        assert args.court_segment_seconds == 3.0
        assert args.court_frames_per_attempt == 5
        assert args.court_resize_width == 320
        assert args.court_min_score == 0.25

    def test_default_mode_is_clips(self):
        from ppa_frame_sampler.cli import build_parser
        p = build_parser()
        args = p.parse_args([])
        assert args.mode == "clips"
