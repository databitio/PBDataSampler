"""End-to-end integration tests for ``run_court_collection()`` with all external
tools mocked.

Uses the same patching strategy as test_integration_end_to_end.py, extended for
the court pipeline's use of extract_frames.  Also patches the cache layer to
avoid stale entries from prior runs.
"""
from __future__ import annotations

import contextlib
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from conftest import (
    build_ytdlp_entry,
    build_ytdlp_playlist_json,
    court_frame_writer,
    days_ago_date,
    static_frame_writer,
)
from ppa_frame_sampler.config import Config, CourtConfig
from ppa_frame_sampler.pipeline.court_collector import run_court_collection

# All import sites that need patching (court pipeline uses downloader + extractor)
_ENSURE_TOOL_SITES = [
    "ppa_frame_sampler.youtube.catalog.ensure_tool",
    "ppa_frame_sampler.media.downloader.ensure_tool",
    "ppa_frame_sampler.media.extractor.ensure_tool",
    "ppa_frame_sampler.media.ffprobe.ensure_tool",
]
_RUN_CMD_SITES = [
    "ppa_frame_sampler.media.downloader.run_cmd",
    "ppa_frame_sampler.media.extractor.run_cmd",
]
_RUN_CMD_JSON_SITES = [
    "ppa_frame_sampler.youtube.catalog.run_cmd_json",
    "ppa_frame_sampler.media.ffprobe.run_cmd_json",
]
_CACHE_SITES = [
    "ppa_frame_sampler.youtube.catalog.get_cached_videos",
    "ppa_frame_sampler.youtube.catalog.set_cached_videos",
]


@contextlib.contextmanager
def mock_all_tools(run_cmd_side_effect, run_cmd_json_side_effect):
    """Patch ensure_tool / run_cmd / run_cmd_json / cache at every import site."""
    with contextlib.ExitStack() as stack:
        for t in _ENSURE_TOOL_SITES:
            stack.enter_context(
                patch(t, side_effect=lambda n: f"/fake/bin/{n}"),
            )
        for t in _RUN_CMD_SITES:
            stack.enter_context(
                patch(t, side_effect=run_cmd_side_effect),
            )
        for t in _RUN_CMD_JSON_SITES:
            stack.enter_context(
                patch(t, side_effect=run_cmd_json_side_effect),
            )
        # Bypass persistent cache so tests get fresh data
        stack.enter_context(
            patch(_CACHE_SITES[0], return_value=None),
        )
        stack.enter_context(
            patch(_CACHE_SITES[1]),
        )
        yield


# ---------------------------------------------------------------------------
# Dispatching side-effects
# ---------------------------------------------------------------------------

def _make_run_cmd_json_se(playlist_json):
    """Dispatch run_cmd_json by inspecting cmd[0]."""
    def side_effect(cmd, timeout=120):
        if "yt-dlp" in cmd[0]:
            return playlist_json
        return {}
    return side_effect


def _make_run_cmd_se(frame_writer, frames_per_call):
    """Dispatch run_cmd: yt-dlp download → no-op, ffmpeg extract → create images."""
    def side_effect(cmd, timeout=120):
        if "ffmpeg" in cmd[0] and "-frames:v" in cmd:
            pattern = cmd[-1]
            for i in range(1, frames_per_call + 1):
                path = Path(pattern % i)
                path.parent.mkdir(parents=True, exist_ok=True)
                frame_writer(path)
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr="",
        )
    return side_effect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _court_cfg(tmp, **overrides):
    court_out = Path(tmp) / "court_out"
    tmp_dir = Path(tmp) / "tmp"
    court_defaults = dict(
        court_out_dir=str(court_out),
        court_frame_format="jpg",
        court_sample_attempts=2,
        court_frames_per_attempt=3,
        court_segment_seconds=2.0,
        court_intro_margin_s=5.0,
        court_outro_margin_s=5.0,
        court_resize_width=640,
    )
    court_overrides = {
        k: overrides.pop(k)
        for k in list(overrides) if k.startswith("court_")
    }
    court_defaults.update(court_overrides)
    cc = CourtConfig(**court_defaults)

    defaults = dict(
        mode="court-frames",
        channel_url="https://example.com/@ch",
        seed=42,
        tmp_dir=str(tmp_dir),
        min_video_duration_s=120,
        max_age_days=365,
        max_videos=200,
        intro_margin_s=5.0,
        outro_margin_s=5.0,
        court=cc,
    )
    defaults.update(overrides)
    return Config(**defaults)


def _playlist(n=3):
    entries = [
        build_ytdlp_entry(f"v{i}", 600.0, days_ago_date(5))
        for i in range(n)
    ]
    return build_ytdlp_playlist_json(entries)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCourtPipelineEndToEnd:

    def test_one_frame_per_video(self):
        """Each video should produce exactly one output frame."""
        n_videos = 3
        with tempfile.TemporaryDirectory() as td:
            cfg = _court_cfg(td)
            with mock_all_tools(
                _make_run_cmd_se(court_frame_writer, 3),
                _make_run_cmd_json_se(_playlist(n_videos)),
            ):
                run_court_collection(cfg)

            out_dir = Path(cfg.court.court_out_dir)
            frames = list(out_dir.glob("*.jpg"))
            assert len(frames) == n_videos

    def test_filename_pattern(self):
        """Output filenames should follow {video_id}_{ts_ms}ms.{ext} pattern."""
        with tempfile.TemporaryDirectory() as td:
            cfg = _court_cfg(td)
            with mock_all_tools(
                _make_run_cmd_se(court_frame_writer, 3),
                _make_run_cmd_json_se(_playlist(1)),
            ):
                run_court_collection(cfg)

            out_dir = Path(cfg.court.court_out_dir)
            frames = list(out_dir.glob("*.jpg"))
            assert len(frames) == 1
            name = frames[0].stem
            # Should contain video id and ms suffix
            assert "v0" in name
            assert "ms" in name

    def test_manifest_written(self):
        """Manifest should be written with correct structure."""
        with tempfile.TemporaryDirectory() as td:
            cfg = _court_cfg(td)
            with mock_all_tools(
                _make_run_cmd_se(court_frame_writer, 3),
                _make_run_cmd_json_se(_playlist(2)),
            ):
                run_court_collection(cfg)

            manifest_path = Path(cfg.court.court_out_dir) / "court_detection_manifest.json"
            assert manifest_path.exists()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            assert manifest["mode"] == "court-frames"
            assert manifest["totals"]["videos_processed"] == 2
            assert manifest["totals"]["frames_saved"] == 2
            assert manifest["totals"]["videos_skipped"] == 0
            assert len(manifest["results"]) == 2
            for r in manifest["results"]:
                assert r["status"] == "saved"
                assert "filename" in r
                assert "composite_score" in r

    def test_manifest_not_written_when_disabled(self):
        """Manifest should not be written when court_save_manifest=False."""
        with tempfile.TemporaryDirectory() as td:
            cfg = _court_cfg(td, court_save_manifest=False)
            with mock_all_tools(
                _make_run_cmd_se(court_frame_writer, 3),
                _make_run_cmd_json_se(_playlist(1)),
            ):
                run_court_collection(cfg)

            manifest_path = Path(cfg.court.court_out_dir) / "court_detection_manifest.json"
            assert not manifest_path.exists()

    def test_skipped_videos_recorded(self):
        """Videos that fail all attempts should be recorded as skipped."""
        def failing_run_cmd(cmd, timeout=120):
            # Downloads fail → no frames extracted
            if "yt-dlp" in str(cmd[0]) and "--download-sections" in cmd:
                raise RuntimeError("download failed")
            if "ffmpeg" in cmd[0] and "-frames:v" in cmd:
                pattern = cmd[-1]
                for i in range(1, 4):
                    path = Path(pattern % i)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    static_frame_writer(path)
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr="",
            )

        with tempfile.TemporaryDirectory() as td:
            cfg = _court_cfg(td)
            with mock_all_tools(
                failing_run_cmd,
                _make_run_cmd_json_se(_playlist(2)),
            ):
                run_court_collection(cfg)

            manifest_path = Path(cfg.court.court_out_dir) / "court_detection_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            assert manifest["totals"]["videos_processed"] == 2
            assert manifest["totals"]["frames_saved"] == 0
            assert manifest["totals"]["videos_skipped"] == 2

    def test_tmp_cleaned_up(self):
        """Temporary directory should be cleaned up after run."""
        with tempfile.TemporaryDirectory() as td:
            cfg = _court_cfg(td)
            with mock_all_tools(
                _make_run_cmd_se(court_frame_writer, 3),
                _make_run_cmd_json_se(_playlist(1)),
            ):
                run_court_collection(cfg)

            assert not Path(cfg.tmp_dir).exists()

    def test_png_format(self):
        """Court frames can be saved as PNG."""
        def png_court_writer(path: Path) -> None:
            import cv2
            import numpy as np
            img = np.full((480, 640, 3), (200, 100, 30), dtype=np.uint8)
            cv2.line(img, (50, 100), (590, 100), (255, 255, 255), 2)
            cv2.line(img, (50, 380), (590, 380), (255, 255, 255), 2)
            path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(path), img)

        def png_run_cmd(cmd, timeout=120):
            if "ffmpeg" in cmd[0] and "-frames:v" in cmd:
                pattern = cmd[-1]
                for i in range(1, 4):
                    path = Path(pattern % i)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    png_court_writer(path)
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr="",
            )

        with tempfile.TemporaryDirectory() as td:
            cfg = _court_cfg(td, court_frame_format="png")
            with mock_all_tools(
                png_run_cmd,
                _make_run_cmd_json_se(_playlist(1)),
            ):
                run_court_collection(cfg)

            out_dir = Path(cfg.court.court_out_dir)
            frames = list(out_dir.glob("*.png"))
            assert len(frames) == 1


    def test_min_score_threshold_rejects_low_frames(self):
        """Frames below court_min_score should be skipped even if extracted."""
        with tempfile.TemporaryDirectory() as td:
            # Set threshold very high so court frames will be rejected
            cfg = _court_cfg(td, court_min_score=0.99)
            with mock_all_tools(
                _make_run_cmd_se(court_frame_writer, 3),
                _make_run_cmd_json_se(_playlist(2)),
            ):
                run_court_collection(cfg)

            out_dir = Path(cfg.court.court_out_dir)
            frames = list(out_dir.glob("*.jpg"))
            assert len(frames) == 0

            manifest_path = out_dir / "court_detection_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert manifest["totals"]["videos_processed"] == 2
            assert manifest["totals"]["frames_saved"] == 0
            assert manifest["totals"]["videos_skipped"] == 2

    def test_min_score_threshold_in_manifest_params(self):
        """court_min_score should appear in manifest params."""
        with tempfile.TemporaryDirectory() as td:
            cfg = _court_cfg(td, court_min_score=0.20)
            with mock_all_tools(
                _make_run_cmd_se(court_frame_writer, 3),
                _make_run_cmd_json_se(_playlist(1)),
            ):
                run_court_collection(cfg)

            manifest_path = Path(cfg.court.court_out_dir) / "court_detection_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert manifest["params"]["court_min_score"] == 0.20


class TestClipsRegressionFromCourt:
    """Verify clips pipeline still works after court-frames changes."""

    def test_clips_config_accepts_new_fields(self):
        """Config with mode='clips' and court= still constructs correctly."""
        cc = CourtConfig()
        cfg = Config(mode="clips", court=cc)
        assert cfg.mode == "clips"
        assert cfg.court.court_sample_attempts == 5

    def test_clips_pipeline_runs(self):
        """run_collection should still work with the new Config fields."""
        import subprocess as sp
        from ppa_frame_sampler.pipeline.collector import run_collection

        playlist = _playlist(5)

        def run_cmd_json_se(cmd, timeout=120):
            if "yt-dlp" in cmd[0]:
                return playlist
            return {}

        def run_cmd_se(cmd, timeout=120):
            # Create the output mp4 file so the pipeline sees it
            if "yt-dlp" in str(cmd[0]) and "-o" in cmd:
                idx = cmd.index("-o")
                out_path = Path(cmd[idx + 1])
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"\x00" * 100)
            return sp.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as td:
            cfg = Config(
                mode="clips",
                channel_url="https://example.com/@ch",
                seed=42,
                frames_per_sample=10,
                total_frames=10,
                out_dir=str(Path(td) / "out" / "frames"),
                tmp_dir=str(Path(td) / "tmp"),
                intro_margin_s=5.0,
                outro_margin_s=5.0,
                buffer_seconds=1.0,
                min_video_duration_s=120,
                max_age_days=365,
                max_videos=200,
            )

            # Patch all tool sites + cache
            with contextlib.ExitStack() as stack:
                for t in _ENSURE_TOOL_SITES:
                    stack.enter_context(
                        patch(t, side_effect=lambda n: f"/fake/bin/{n}"),
                    )
                for t in _RUN_CMD_SITES:
                    stack.enter_context(
                        patch(t, side_effect=run_cmd_se),
                    )
                for t in _RUN_CMD_JSON_SITES:
                    stack.enter_context(
                        patch(t, side_effect=run_cmd_json_se),
                    )
                stack.enter_context(
                    patch(_CACHE_SITES[0], return_value=None),
                )
                stack.enter_context(
                    patch(_CACHE_SITES[1]),
                )
                run_collection(cfg)

            # Clips pipeline writes a manifest in a run subdirectory
            out = Path(cfg.out_dir)
            manifests = list(out.rglob("run_manifest.json"))
            assert len(manifests) == 1
            manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
            assert manifest["totals"]["clips_collected"] >= 1
