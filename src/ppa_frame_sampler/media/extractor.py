from __future__ import annotations

import logging
from pathlib import Path

from ppa_frame_sampler.media.tools import ensure_tool, run_cmd

log = logging.getLogger("ppa_frame_sampler")


def extract_frames(
    clip_path: Path,
    frames: int,
    out_dir: Path,
    prefix: str,
    image_format: str,
) -> list[Path]:
    """Extract *frames* consecutive decoded frames from *clip_path*.

    Writes files to *out_dir* named ``{prefix}_{seq:06d}.{ext}``.
    Returns the list of written file paths.
    """
    ffmpeg = ensure_tool("ffmpeg")
    out_dir.mkdir(parents=True, exist_ok=True)

    ext = "jpg" if image_format == "jpg" else "png"
    pattern = str(out_dir / f"{prefix}_%06d.{ext}")

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-i", str(clip_path),
        "-fps_mode", "passthrough",
        "-frames:v", str(frames),
    ]

    if ext == "jpg":
        cmd += ["-q:v", "2"]  # high quality JPEG

    cmd.append(pattern)

    log.debug("Extracting %d frames from %s", frames, clip_path.name)
    run_cmd(cmd, timeout=60)

    # Collect written files in deterministic order
    written: list[Path] = sorted(
        out_dir.glob(f"{prefix}_*.{ext}"),
        key=lambda p: p.name,
    )
    log.info("Extracted %d frames → %s/%s_*.%s", len(written), out_dir, prefix, ext)
    return written
