from __future__ import annotations

import logging
from pathlib import Path

from ppa_frame_sampler.media.tools import ensure_tool, run_cmd_json

log = logging.getLogger("ppa_frame_sampler")

_DEFAULT_FPS = 30.0


def probe_fps(video_path: Path) -> float:
    """Return the average FPS of *video_path* via ffprobe, or 30 as fallback."""
    ffprobe = ensure_tool("ffprobe")
    cmd = [
        ffprobe,
        "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries", "stream=avg_frame_rate",
        "-of", "json",
        str(video_path),
    ]

    try:
        data = run_cmd_json(cmd)
        rate_str = data["streams"][0]["avg_frame_rate"]  # e.g. "30000/1001"
        num, den = rate_str.split("/")
        fps = float(num) / float(den)
        if fps <= 0:
            raise ValueError("non-positive fps")
        log.debug("Probed fps=%.2f for %s", fps, video_path.name)
        return fps
    except Exception:
        log.warning("Could not probe fps for %s, falling back to %.0f", video_path.name, _DEFAULT_FPS)
        return _DEFAULT_FPS
