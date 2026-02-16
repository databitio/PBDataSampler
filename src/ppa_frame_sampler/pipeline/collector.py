from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from ppa_frame_sampler.config import Config
from ppa_frame_sampler.media.downloader import download_segment
from ppa_frame_sampler.output.manifest import write_manifest
from ppa_frame_sampler.output.naming import safe_slug
from ppa_frame_sampler.output.zipper import zip_frames
from ppa_frame_sampler.run_id import generate_run_id
from ppa_frame_sampler.sampling.segment_planner import plan_segment_len_s
from ppa_frame_sampler.sampling.timestamp_sampler import sample_timestamp
from ppa_frame_sampler.youtube.catalog import list_recent_videos
from ppa_frame_sampler.youtube.channel_resolver import resolve_channel_url
from ppa_frame_sampler.youtube.models import classify_match_type

log = logging.getLogger("ppa_frame_sampler")


def run_collection(cfg: Config) -> None:
    """Main collection loop: resolve channel, catalogue videos, download clips."""
    if cfg.seed is not None:
        random.seed(cfg.seed)

    out_root = Path(cfg.out_dir)
    tmp_dir = Path(cfg.tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # ── Resolve channel & build candidate pool ──────────────────────
    channel_url = cfg.channel_url or resolve_channel_url(cfg.channel_query)
    log.info("Channel URL: %s", channel_url)

    candidates = list_recent_videos(
        channel_url,
        cfg.max_age_days,
        cfg.max_videos,
        cfg.min_video_duration_s,
    )
    if not candidates:
        raise RuntimeError(
            "No eligible videos found. Try relaxing --max-age-days, "
            "--min-video-duration-s, or provide a different --channel-url."
        )

    log.info("Candidate pool: %d videos", len(candidates))

    # ── Filter by match type ─────────────────────────────────────────
    if cfg.match_type != "both":
        total_before = len(candidates)
        candidates = [
            v for v in candidates
            if classify_match_type(v.title) == cfg.match_type
        ]
        log.info(
            "Filtered to %d %s matches from %d candidates",
            len(candidates), cfg.match_type, total_before,
        )
        if not candidates:
            raise RuntimeError(
                f"No {cfg.match_type} matches found among candidates. "
                "Try relaxing filters or using --match-type both."
            )

    # ── Prepare manifest ────────────────────────────────────────────
    run_id = generate_run_id(cfg.seed)

    # Each run gets its own subdirectory
    out_dir = out_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    log.info("Run output directory: %s", out_dir)
    manifest: Dict[str, Any] = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "params": {
            "channel_url": channel_url,
            "max_age_days": cfg.max_age_days,
            "max_videos": cfg.max_videos,
            "min_video_duration_s": cfg.min_video_duration_s,
            "frames_per_sample": cfg.frames_per_sample,
            "total_frames": cfg.total_frames,
            "seed": cfg.seed,
            "bias_mode": cfg.bias_mode,
            "intro_margin_s": cfg.intro_margin_s,
            "outro_margin_s": cfg.outro_margin_s,
            "buffer_seconds": cfg.buffer_seconds,
            "image_format": cfg.image_format,
            "match_type": cfg.match_type,
        },
        "candidates": {"count": len(candidates)},
        "samples": [],
        "totals": {"clips_collected": 0, "download_errors": 0},
    }

    # ── Collection loop ─────────────────────────────────────────────
    total_clips = cfg.total_frames // cfg.frames_per_sample or 1
    clip_idx = 0

    while clip_idx < total_clips:
        video = random.choice(candidates)

        segment_len_s = plan_segment_len_s(
            cfg.frames_per_sample, fps_guess=30.0, buffer_seconds=cfg.buffer_seconds,
        )
        start_s = sample_timestamp(
            duration_s=video.duration_s,
            segment_len_s=segment_len_s,
            intro_margin_s=cfg.intro_margin_s,
            outro_margin_s=cfg.outro_margin_s,
            bias_mode=cfg.bias_mode,
        )
        end_s = min(video.duration_s, start_s + segment_len_s)

        ts_ms = int(start_s * 1000)
        clip_name = f"{safe_slug(video.video_id)}_{ts_ms:010d}ms"
        clip_path = out_dir / f"{clip_name}.mp4"

        try:
            download_segment(video.webpage_url, start_s, end_s, clip_path)
        except Exception as exc:
            log.warning("Download failed for %s [%.1f–%.1f]: %s", video.video_id, start_s, end_s, exc)
            manifest["totals"]["download_errors"] += 1
            _record_sample(manifest, video, start_s, end_s, "download_error", clip_name)
            continue

        clip_idx += 1
        manifest["totals"]["clips_collected"] = clip_idx
        _record_sample(manifest, video, start_s, end_s, "collected", clip_name)

        log.info(
            "Clip collected: %s (clip %d/%d)",
            clip_name, clip_idx, total_clips,
        )

    # ── Finalise ────────────────────────────────────────────────────
    write_manifest(out_dir / "run_manifest.json", manifest)
    log.info("Manifest written to %s", out_dir / "run_manifest.json")

    if cfg.make_zip:
        zip_frames(out_dir, out_dir / "cvat_upload.zip")

    log.info(
        "Done — %d clips collected, %d download errors",
        manifest["totals"]["clips_collected"],
        manifest["totals"]["download_errors"],
    )


def _record_sample(
    manifest: Dict[str, Any],
    video: Any,
    start_s: float,
    end_s: float,
    status: str,
    clip_name: str,
) -> None:
    """Append a sample record to the manifest."""
    rec: Dict[str, Any] = {
        "video_id": video.video_id,
        "video_url": video.webpage_url,
        "title": video.title,
        "upload_date": video.upload_date,
        "duration_s": video.duration_s,
        "timestamp_s": start_s,
        "segment": {"start_s": start_s, "end_s": end_s},
        "status": status,
        "clip_name": clip_name,
        "match_type": classify_match_type(video.title),
    }
    manifest["samples"].append(rec)
