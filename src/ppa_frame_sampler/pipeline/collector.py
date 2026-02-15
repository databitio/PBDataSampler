from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from ppa_frame_sampler.config import Config
from ppa_frame_sampler.filter.quality_filter import evaluate_burst
from ppa_frame_sampler.media.downloader import download_segment
from ppa_frame_sampler.media.extractor import extract_frames
from ppa_frame_sampler.media.ffprobe import probe_fps
from ppa_frame_sampler.output.cleanup import cleanup_tmp
from ppa_frame_sampler.output.manifest import write_manifest
from ppa_frame_sampler.output.naming import safe_slug
from ppa_frame_sampler.output.zipper import zip_frames
from ppa_frame_sampler.run_id import generate_run_id
from ppa_frame_sampler.sampling.segment_planner import plan_segment_len_s
from ppa_frame_sampler.sampling.timestamp_sampler import sample_timestamp
from ppa_frame_sampler.youtube.catalog import list_recent_videos
from ppa_frame_sampler.youtube.channel_resolver import resolve_channel_url

log = logging.getLogger("ppa_frame_sampler")


def run_collection(cfg: Config) -> None:
    """Main collection loop: resolve channel, catalogue videos, sample bursts."""
    if cfg.seed is not None:
        random.seed(cfg.seed)

    out_dir = Path(cfg.out_dir)
    tmp_dir = Path(cfg.tmp_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
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

    # ── Prepare manifest ────────────────────────────────────────────
    run_id = generate_run_id(cfg.seed)
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
        },
        "candidates": {"count": len(candidates)},
        "samples": [],
        "totals": {"accepted_bursts": 0, "rejected_bursts": 0, "frames_written": 0},
    }

    # ── Collection loop ─────────────────────────────────────────────
    collected = 0
    burst_idx = 0

    while collected < cfg.total_frames:
        video = random.choice(candidates)
        burst_idx += 1

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

        clip_path = tmp_dir / f"{safe_slug(video.video_id)}_b{burst_idx:05d}.mp4"

        accepted = False
        attempts = 0

        while attempts < cfg.max_retries_per_burst and not accepted:
            attempts += 1

            try:
                download_segment(video.webpage_url, start_s, end_s, clip_path)
            except Exception as exc:
                log.warning("Download failed for %s [%.1f–%.1f]: %s", video.video_id, start_s, end_s, exc)
                _record_sample(manifest, video, start_s, end_s, 0, False, f"download_error: {exc}", None, attempts)
                break

            # Probe actual FPS and optionally retry with longer segment
            fps = probe_fps(clip_path)
            needed_len = cfg.frames_per_sample / fps + cfg.buffer_seconds
            if (end_s - start_s) < needed_len and attempts == 1:
                # Re-download with longer segment
                new_end = min(video.duration_s, start_s + needed_len + cfg.buffer_seconds)
                if new_end > end_s:
                    log.info("Re-downloading with extended segment [%.1f–%.1f]", start_s, new_end)
                    clip_path.unlink(missing_ok=True)
                    end_s = new_end
                    try:
                        download_segment(video.webpage_url, start_s, end_s, clip_path)
                    except Exception as exc:
                        log.warning("Extended download failed: %s", exc)
                        _record_sample(manifest, video, start_s, end_s, 0, False, f"download_error: {exc}", None, attempts)
                        break

            # Extract frames
            ts_ms = int(start_s * 1000)
            prefix = f"{safe_slug(video.video_id)}_{ts_ms:010d}ms"

            remaining = cfg.total_frames - collected
            frames_to_extract = min(cfg.frames_per_sample, remaining)

            try:
                frame_paths = extract_frames(clip_path, frames_to_extract, out_dir, prefix, cfg.image_format)
            except Exception as exc:
                log.warning("Frame extraction failed: %s", exc)
                _record_sample(manifest, video, start_s, end_s, 0, False, f"extract_error: {exc}", None, attempts)
                clip_path.unlink(missing_ok=True)
                break

            if not frame_paths:
                _record_sample(manifest, video, start_s, end_s, 0, False, "no_frames_extracted", None, attempts)
                clip_path.unlink(missing_ok=True)
                break

            # Enforce overshoot cap
            if collected + len(frame_paths) > cfg.total_frames:
                overflow = (collected + len(frame_paths)) - cfg.total_frames
                for p in frame_paths[-overflow:]:
                    p.unlink(missing_ok=True)
                frame_paths = frame_paths[:-overflow]

            # Quality filter
            decision = evaluate_burst(
                frame_paths,
                thresholds=cfg.thresholds,
                analysis_resize_width=cfg.analysis_resize_width,
                analysis_frame_count=cfg.analysis_frame_count,
            )

            _record_sample(
                manifest, video, start_s, end_s,
                len(frame_paths), decision.accepted, decision.reason,
                decision.metrics, attempts, prefix,
            )

            if decision.accepted and frame_paths:
                collected += len(frame_paths)
                manifest["totals"]["accepted_bursts"] += 1
                accepted = True
                log.info(
                    "Burst accepted: %d frames (total %d/%d)",
                    len(frame_paths), collected, cfg.total_frames,
                )
            else:
                for p in frame_paths:
                    p.unlink(missing_ok=True)
                manifest["totals"]["rejected_bursts"] += 1

            # Clean up temp clip
            if not cfg.keep_tmp:
                clip_path.unlink(missing_ok=True)

        manifest["totals"]["frames_written"] = collected

    # ── Finalise ────────────────────────────────────────────────────
    output_root = Path(cfg.out_dir).parent
    write_manifest(output_root / "run_manifest.json", manifest)
    log.info("Manifest written to %s", output_root / "run_manifest.json")

    if cfg.make_zip:
        zip_frames(out_dir, output_root / "cvat_upload.zip")

    if not cfg.keep_tmp:
        cleanup_tmp(tmp_dir)

    log.info(
        "Done — %d frames written, %d bursts accepted, %d rejected",
        collected,
        manifest["totals"]["accepted_bursts"],
        manifest["totals"]["rejected_bursts"],
    )


def _record_sample(
    manifest: Dict[str, Any],
    video: Any,
    start_s: float,
    end_s: float,
    extracted: int,
    accepted: bool,
    reason: str,
    metrics: Any,
    attempt: int,
    prefix: str = "",
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
        "extracted_frames": extracted,
        "accepted": accepted,
        "filter_reason": reason,
        "attempt": attempt,
    }
    if metrics is not None:
        rec["filter_metrics"] = {
            "motion_score": metrics.motion_score,
            "static_score": metrics.static_score,
            "edge_density": metrics.edge_density,
            "overlay_coverage": metrics.overlay_coverage,
            "scene_cut_rate": metrics.scene_cut_rate,
        }
    if prefix:
        rec["output_prefix"] = prefix
    manifest["samples"].append(rec)
