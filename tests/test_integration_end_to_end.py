"""End-to-end integration tests for ``run_collection()`` with all external
tools mocked.

The clips pipeline downloads short MP4 segments (no frame extraction or burst
filtering).  Each run creates a ``<run_id>/`` subdirectory under ``out_dir``
and writes ``run_manifest.json`` inside it.

Patches target every import site (catalog, downloader, extractor, ffprobe)
because each module uses ``from ppa_frame_sampler.media.tools import …``.
"""
from __future__ import annotations

import contextlib
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from conftest import (
    build_ffprobe_json,
    build_ytdlp_entry,
    build_ytdlp_playlist_json,
    days_ago_date,
)
from ppa_frame_sampler.config import Config
from ppa_frame_sampler.pipeline.collector import run_collection

# All import sites that need patching
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


def _noop_run_cmd(cmd, timeout=120):
    """No-op run_cmd: downloads succeed without creating files."""
    return subprocess.CompletedProcess(
        args=cmd, returncode=0, stdout="", stderr="",
    )


def _failing_run_cmd(cmd, timeout=120):
    """run_cmd that fails yt-dlp downloads."""
    if "yt-dlp" in str(cmd[0]) and "--download-sections" in cmd:
        raise RuntimeError("download failed")
    return subprocess.CompletedProcess(
        args=cmd, returncode=0, stdout="", stderr="",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(tmp, **overrides):
    out = Path(tmp) / "out" / "frames"
    tmp_dir = Path(tmp) / "tmp"
    defaults = dict(
        channel_url="https://example.com/@ch",
        seed=42,
        frames_per_sample=10,
        total_frames=30,
        max_retries_per_burst=1,
        out_dir=str(out),
        tmp_dir=str(tmp_dir),
        image_format="jpg",
        keep_tmp=False,
        intro_margin_s=5.0,
        outro_margin_s=5.0,
        buffer_seconds=1.0,
        min_video_duration_s=120,
        max_age_days=365,
        max_videos=200,
    )
    defaults.update(overrides)
    return Config(**defaults)


def _playlist(n=5):
    entries = [
        build_ytdlp_entry(f"v{i}", 600.0, days_ago_date(5))
        for i in range(n)
    ]
    return build_ytdlp_playlist_json(entries)


def _get_manifest(cfg):
    """Find and parse the run manifest from the output directory."""
    manifests = list(Path(cfg.out_dir).rglob("run_manifest.json"))
    assert len(manifests) == 1, f"Expected 1 manifest, found {len(manifests)}"
    return json.loads(manifests[0].read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEndToEnd:

    def test_exact_clip_count(self):
        """total_frames=30, frames_per_sample=10 → exactly 3 clips."""
        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td, total_frames=30, frames_per_sample=10)
            with mock_all_tools(
                _noop_run_cmd,
                _make_run_cmd_json_se(_playlist()),
            ):
                run_collection(cfg)

            manifest = _get_manifest(cfg)
            assert manifest["totals"]["clips_collected"] == 3

    def test_clip_count_rounding(self):
        """total_frames=25 with frames_per_sample=10 → 2 clips (25//10)."""
        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td, total_frames=25, frames_per_sample=10)
            with mock_all_tools(
                _noop_run_cmd,
                _make_run_cmd_json_se(_playlist()),
            ):
                run_collection(cfg)

            manifest = _get_manifest(cfg)
            assert manifest["totals"]["clips_collected"] == 2

    def test_download_errors_dont_count(self):
        """Download failures are recorded but don't count as collected clips."""
        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td, total_frames=10, frames_per_sample=10)

            call_count = {"n": 0}
            def fail_then_succeed(cmd, timeout=120):
                if "yt-dlp" in str(cmd[0]) and "--download-sections" in cmd:
                    call_count["n"] += 1
                    if call_count["n"] <= 2:
                        raise RuntimeError("download failed")
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="", stderr="",
                )

            with mock_all_tools(
                fail_then_succeed,
                _make_run_cmd_json_se(_playlist()),
            ):
                run_collection(cfg)

            manifest = _get_manifest(cfg)
            assert manifest["totals"]["clips_collected"] == 1
            assert manifest["totals"]["download_errors"] == 2

    def test_manifest_totals(self):
        """Manifest has correct clips_collected and download_errors keys."""
        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td, total_frames=10, frames_per_sample=10)
            with mock_all_tools(
                _noop_run_cmd,
                _make_run_cmd_json_se(_playlist()),
            ):
                run_collection(cfg)

            manifest = _get_manifest(cfg)
            assert manifest["totals"]["clips_collected"] == 1
            assert manifest["totals"]["download_errors"] == 0
            assert "run_id" in manifest
            assert "samples" in manifest
            assert len(manifest["samples"]) == 1

    def test_manifest_in_run_subdirectory(self):
        """Manifest is written inside the run_id subdirectory, not the root."""
        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td, total_frames=10, frames_per_sample=10)
            with mock_all_tools(
                _noop_run_cmd,
                _make_run_cmd_json_se(_playlist()),
            ):
                run_collection(cfg)

            # Manifest should be in a subdirectory named after the run_id
            out = Path(cfg.out_dir)
            subdirs = [d for d in out.iterdir() if d.is_dir()]
            assert len(subdirs) == 1
            assert (subdirs[0] / "run_manifest.json").exists()
