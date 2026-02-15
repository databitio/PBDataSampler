from __future__ import annotations

import logging
from pathlib import Path

from ppa_frame_sampler.media.tools import ensure_tool, run_cmd

log = logging.getLogger("ppa_frame_sampler")


def download_segment(video_url: str, start_s: float, end_s: float, out_path: Path) -> None:
    """Download only the segment [start_s, end_s] of *video_url* to *out_path*.

    Uses yt-dlp ``--download-sections`` so only a short clip is fetched.
    """
    ytdlp = ensure_tool("yt-dlp")
    section = f"*{start_s:.2f}-{end_s:.2f}"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ytdlp,
        "--no-warnings",
        "--quiet",
        "--download-sections", section,
        "--force-keyframes-at-cuts",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(out_path),
        video_url,
    ]

    log.info(
        "Downloading segment [%.1f–%.1f s] from %s",
        start_s, end_s, video_url,
    )
    run_cmd(cmd, timeout=300)
