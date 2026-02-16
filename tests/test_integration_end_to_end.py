"""End-to-end integration tests for ``run_collection()`` with all external
tools mocked.

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
    noise_frame_writer,
    static_frame_writer,
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


@contextlib.contextmanager
def mock_all_tools(run_cmd_side_effect, run_cmd_json_side_effect):
    """Patch ensure_tool / run_cmd / run_cmd_json at every import site."""
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
        yield


# ---------------------------------------------------------------------------
# Dispatching side-effects
# ---------------------------------------------------------------------------

def _make_run_cmd_json_se(playlist_json, ffprobe_json):
    """Dispatch run_cmd_json by inspecting cmd[0]."""
    def side_effect(cmd, timeout=120):
        if "yt-dlp" in cmd[0]:
            return playlist_json
        if "ffprobe" in cmd[0]:
            return ffprobe_json
        return {}
    return side_effect


def _make_run_cmd_se(frame_writer, frames_per_call):
    """Dispatch run_cmd: yt-dlp → no-op, ffmpeg → create images."""
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


def _make_alternating_run_cmd_se(frames_per_call):
    """Odd extractions → noise (accepted), even → static (rejected)."""
    state = {"count": 0}

    def side_effect(cmd, timeout=120):
        if "ffmpeg" in cmd[0] and "-frames:v" in cmd:
            state["count"] += 1
            writer = noise_frame_writer if state["count"] % 2 == 1 else static_frame_writer
            pattern = cmd[-1]
            for i in range(1, frames_per_call + 1):
                path = Path(pattern % i)
                path.parent.mkdir(parents=True, exist_ok=True)
                writer(path)
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr="",
        )
    return side_effect


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEndToEnd:

    def test_exact_frame_count(self):
        """total_frames=30, frames_per_sample=10 → exactly 30 images."""
        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td, total_frames=30, frames_per_sample=10)
            with mock_all_tools(
                _make_run_cmd_se(noise_frame_writer, 10),
                _make_run_cmd_json_se(_playlist(), build_ffprobe_json()),
            ):
                run_collection(cfg)

            assert len(list(Path(cfg.out_dir).glob("*.jpg"))) == 30

    def test_overshoot_prevention(self):
        """total_frames=25 with frames_per_sample=10 → exactly 25."""
        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td, total_frames=25, frames_per_sample=10)
            with mock_all_tools(
                _make_run_cmd_se(noise_frame_writer, 10),
                _make_run_cmd_json_se(_playlist(), build_ffprobe_json()),
            ):
                run_collection(cfg)

            assert len(list(Path(cfg.out_dir).glob("*.jpg"))) == 25

    def test_rejected_bursts_dont_count(self):
        """Alternating noise/static: only noise bursts count toward total."""
        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td, total_frames=10, frames_per_sample=10)
            with mock_all_tools(
                _make_alternating_run_cmd_se(10),
                _make_run_cmd_json_se(_playlist(), build_ffprobe_json()),
            ):
                run_collection(cfg)

            assert len(list(Path(cfg.out_dir).glob("*.jpg"))) == 10

    def test_manifest_totals(self):
        """Manifest has correct frames_written and burst counts."""
        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td, total_frames=10, frames_per_sample=10)
            with mock_all_tools(
                _make_run_cmd_se(noise_frame_writer, 10),
                _make_run_cmd_json_se(_playlist(), build_ffprobe_json()),
            ):
                run_collection(cfg)

            manifest_path = Path(cfg.out_dir).parent / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            assert manifest["totals"]["frames_written"] == 10
            assert manifest["totals"]["accepted_bursts"] >= 1
            assert isinstance(manifest["totals"]["rejected_bursts"], int)

    def test_tmp_cleaned_when_keep_tmp_false(self):
        """Tmp directory removed when keep_tmp=False."""
        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td, total_frames=10, frames_per_sample=10, keep_tmp=False)
            with mock_all_tools(
                _make_run_cmd_se(noise_frame_writer, 10),
                _make_run_cmd_json_se(_playlist(), build_ffprobe_json()),
            ):
                run_collection(cfg)

            assert not Path(cfg.tmp_dir).exists()
