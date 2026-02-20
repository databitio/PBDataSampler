"""Shared helpers for integration tests."""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

import cv2
import numpy as np

from ppa_frame_sampler.youtube.models import VideoMeta


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def days_ago_date(days: int) -> str:
    """Return YYYYMMDD string for *days* days ago from now (UTC)."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# Frame generators (write real image files to disk)
# ---------------------------------------------------------------------------

def make_noise_frames(
    directory: Path, count: int, *, seed: int = 0,
) -> List[Path]:
    """Generate *count* random-noise BGR images (high motion, good edges)."""
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.RandomState(seed)
    paths: List[Path] = []
    for i in range(count):
        img = rng.randint(0, 256, (240, 320, 3), dtype=np.uint8)
        p = directory / f"noise_{i:06d}.jpg"
        cv2.imwrite(str(p), img)
        paths.append(p)
    return paths


def make_static_frames(
    directory: Path, count: int, color: tuple = (128, 128, 128),
) -> List[Path]:
    """Generate *count* identical solid-color images (zero motion)."""
    directory.mkdir(parents=True, exist_ok=True)
    img = np.full((240, 320, 3), color, dtype=np.uint8)
    paths: List[Path] = []
    for i in range(count):
        p = directory / f"static_{i:06d}.jpg"
        cv2.imwrite(str(p), img)
        paths.append(p)
    return paths


# ---------------------------------------------------------------------------
# Frame writers (single-image callables for make_extract_side_effect)
# ---------------------------------------------------------------------------

def noise_frame_writer(path: Path) -> None:
    """Write one random-noise BGR image to *path*."""
    img = np.random.randint(0, 256, (240, 320, 3), dtype=np.uint8)
    cv2.imwrite(str(path), img)


def static_frame_writer(path: Path) -> None:
    """Write one solid-gray BGR image to *path*."""
    img = np.full((240, 320, 3), (128, 128, 128), dtype=np.uint8)
    cv2.imwrite(str(path), img)


# ---------------------------------------------------------------------------
# VideoMeta factory
# ---------------------------------------------------------------------------

def make_video_meta(
    video_id: str, duration: float = 600.0, age_days: int = 10,
) -> VideoMeta:
    """Create a synthetic ``VideoMeta`` whose upload_date is *age_days* ago."""
    return VideoMeta(
        video_id=video_id,
        title=f"Video {video_id}",
        webpage_url=f"https://www.youtube.com/watch?v={video_id}",
        duration_s=duration,
        upload_date=days_ago_date(age_days),
    )


# ---------------------------------------------------------------------------
# yt-dlp / ffprobe JSON builders
# ---------------------------------------------------------------------------

def build_ytdlp_entry(
    video_id: str, duration: float, upload_date: str,
) -> Dict[str, Any]:
    """Build one yt-dlp flat-playlist entry dict."""
    return {
        "id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": f"Video {video_id}",
        "duration": duration,
        "upload_date": upload_date,
    }


def build_ytdlp_playlist_json(
    entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Wrap *entries* in a yt-dlp ``--flat-playlist -J`` response dict."""
    return {"entries": entries}


def build_ffprobe_json(
    fps_num: int = 30000, fps_den: int = 1001,
) -> Dict[str, Any]:
    """Build an ffprobe JSON response with ``avg_frame_rate``."""
    return {
        "streams": [
            {"avg_frame_rate": f"{fps_num}/{fps_den}"}
        ],
    }


# ---------------------------------------------------------------------------
# Side-effect factory for extract_frames
# ---------------------------------------------------------------------------

def make_extract_side_effect(
    frame_writer: Callable[[Path], None],
    count: int,
) -> Callable:
    """Return a ``run_cmd`` side_effect that creates image files when ffmpeg
    is invoked (detected by ``-frames:v`` in the command).

    *frame_writer* is called once per frame with the output ``Path``.
    Needed because ``extract_frames`` globs the filesystem after calling
    ``run_cmd``.
    """
    def side_effect(cmd, timeout=120):
        if "-frames:v" in cmd:
            pattern = cmd[-1]  # e.g. "/tmp/.../prefix_%06d.jpg"
            for i in range(1, count + 1):
                path = Path(pattern % i)
                path.parent.mkdir(parents=True, exist_ok=True)
                frame_writer(path)
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr="",
        )
    return side_effect


# ---------------------------------------------------------------------------
# Court-frame writers
# ---------------------------------------------------------------------------

def court_frame_writer(path: Path) -> None:
    """Write one blue court-like image with white lines (scores high)."""
    img = np.full((480, 640, 3), (200, 100, 30), dtype=np.uint8)
    cv2.line(img, (50, 100), (590, 100), (255, 255, 255), 2)
    cv2.line(img, (50, 380), (590, 380), (255, 255, 255), 2)
    cv2.line(img, (50, 100), (50, 380), (255, 255, 255), 2)
    cv2.line(img, (590, 100), (590, 380), (255, 255, 255), 2)
    cv2.line(img, (320, 100), (320, 380), (255, 255, 255), 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)
