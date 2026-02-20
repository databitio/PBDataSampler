from __future__ import annotations

import logging
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ppa_frame_sampler.config import Config
from ppa_frame_sampler.filter.court_scorer import CourtScore, pick_best_frame
from ppa_frame_sampler.media.downloader import download_segment
from ppa_frame_sampler.media.extractor import extract_frames
from ppa_frame_sampler.output.cleanup import cleanup_tmp
from ppa_frame_sampler.output.manifest import write_manifest
from ppa_frame_sampler.output.naming import safe_slug
from ppa_frame_sampler.sampling.timestamp_sampler import sample_timestamp
from ppa_frame_sampler.youtube.catalog import list_recent_videos
from ppa_frame_sampler.youtube.channel_resolver import resolve_channel_url
from ppa_frame_sampler.youtube.models import classify_match_type

log = logging.getLogger("ppa_frame_sampler")


def run_court_collection(cfg: Config) -> None:
    """Court-frames pipeline: extract one court-visible frame per eligible video."""
    if cfg.seed is not None:
        random.seed(cfg.seed)

    court = cfg.court
    out_dir = Path(court.court_out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
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
        cfg.min_age_days,
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
    manifest: Dict[str, Any] = {
        "mode": "court-frames",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "params": {
            "channel_url": channel_url,
            "min_age_days": cfg.min_age_days,
            "max_age_days": cfg.max_age_days,
            "max_videos": cfg.max_videos,
            "min_video_duration_s": cfg.min_video_duration_s,
            "match_type": cfg.match_type,
            "court_sample_attempts": court.court_sample_attempts,
            "court_intro_margin_s": court.court_intro_margin_s,
            "court_outro_margin_s": court.court_outro_margin_s,
            "court_segment_seconds": court.court_segment_seconds,
            "court_frames_per_attempt": court.court_frames_per_attempt,
            "court_resize_width": court.court_resize_width,
            "court_min_score": court.court_min_score,
            "seed": cfg.seed,
        },
        "candidates": {"count": len(candidates)},
        "results": [],
        "totals": {
            "videos_processed": 0,
            "frames_saved": 0,
            "videos_skipped": 0,
        },
    }

    # ── Per-video loop ───────────────────────────────────────────────
    for vid_idx, video in enumerate(candidates):
        log.info(
            "Processing video %d/%d: %s (%s)",
            vid_idx + 1, len(candidates), video.video_id, video.title,
        )

        best_path: Optional[Path] = None
        best_score: Optional[CourtScore] = None
        best_ts: float = 0.0

        for attempt in range(court.court_sample_attempts):
            ts = sample_timestamp(
                duration_s=video.duration_s,
                segment_len_s=court.court_segment_seconds,
                intro_margin_s=court.court_intro_margin_s,
                outro_margin_s=court.court_outro_margin_s,
                bias_mode=cfg.bias_mode,
            )
            end_s = min(video.duration_s, ts + court.court_segment_seconds)

            clip_name = f"court_{video.video_id}_att{attempt}"
            clip_path = tmp_dir / f"{clip_name}.mp4"
            frames_dir = tmp_dir / f"{clip_name}_frames"

            try:
                download_segment(video.webpage_url, ts, end_s, clip_path)
            except Exception as exc:
                log.warning(
                    "Download failed for %s attempt %d: %s",
                    video.video_id, attempt, exc,
                )
                continue

            try:
                frame_paths = extract_frames(
                    clip_path,
                    court.court_frames_per_attempt,
                    frames_dir,
                    prefix=clip_name,
                    image_format=court.court_frame_format,
                )
            except Exception as exc:
                log.warning(
                    "Frame extraction failed for %s attempt %d: %s",
                    video.video_id, attempt, exc,
                )
                _cleanup_attempt(clip_path, frames_dir)
                continue

            result = pick_best_frame(frame_paths, court.court_resize_width)
            if result is not None:
                candidate_path, candidate_score = result
                if best_score is None or candidate_score.composite > best_score.composite:
                    best_path = candidate_path
                    best_score = candidate_score
                    best_ts = ts

            _cleanup_attempt(clip_path, frames_dir, keep=best_path)

        # ── Save best frame or record skip ───────────────────────────
        manifest["totals"]["videos_processed"] += 1

        if best_path is not None and best_score is not None and best_score.composite >= court.court_min_score:
            ts_ms = int(best_ts * 1000)
            ext = court.court_frame_format
            out_name = f"{safe_slug(video.video_id)}_{ts_ms:010d}ms.{ext}"
            out_file = out_dir / out_name

            shutil.copy2(str(best_path), str(out_file))
            manifest["totals"]["frames_saved"] += 1

            _record_result(
                manifest, video, best_ts, "saved",
                filename=out_name,
                composite_score=best_score.composite,
            )
            log.info(
                "Saved court frame: %s (score=%.3f)",
                out_name, best_score.composite,
            )
            # Clean up the kept best frame's parent dir
            if best_path.parent.exists() and best_path.parent != tmp_dir:
                shutil.rmtree(best_path.parent, ignore_errors=True)
        else:
            manifest["totals"]["videos_skipped"] += 1
            _record_result(manifest, video, 0.0, "skipped")
            log.info("Skipped video %s (no acceptable court frame)", video.video_id)

    # ── Finalise ────────────────────────────────────────────────────
    if court.court_save_manifest:
        manifest_path = out_dir / "court_detection_manifest.json"
        write_manifest(manifest_path, manifest)
        log.info("Manifest written to %s", manifest_path)

    cleanup_tmp(tmp_dir)

    log.info(
        "Done — %d frames saved, %d videos skipped out of %d processed",
        manifest["totals"]["frames_saved"],
        manifest["totals"]["videos_skipped"],
        manifest["totals"]["videos_processed"],
    )


def _cleanup_attempt(
    clip_path: Path, frames_dir: Path, keep: Optional[Path] = None,
) -> None:
    """Remove temporary clip and extracted frames, optionally preserving *keep*."""
    if clip_path.exists():
        clip_path.unlink()
    if frames_dir.exists():
        if keep is not None and keep.parent == frames_dir:
            # Keep the frames_dir alive since best frame is there
            return
        shutil.rmtree(frames_dir, ignore_errors=True)


def _record_result(
    manifest: Dict[str, Any],
    video: Any,
    timestamp_s: float,
    status: str,
    filename: Optional[str] = None,
    composite_score: Optional[float] = None,
) -> None:
    """Append a result record to the manifest."""
    rec: Dict[str, Any] = {
        "video_id": video.video_id,
        "video_url": video.webpage_url,
        "title": video.title,
        "upload_date": video.upload_date,
        "duration_s": video.duration_s,
        "status": status,
        "match_type": classify_match_type(video.title),
    }
    if filename is not None:
        rec["filename"] = filename
        rec["timestamp_s"] = timestamp_s
        rec["composite_score"] = composite_score
    manifest["results"].append(rec)
