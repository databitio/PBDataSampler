from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List

from ppa_frame_sampler.media.tools import ensure_tool, run_cmd_json
from ppa_frame_sampler.youtube.models import VideoMeta

log = logging.getLogger("ppa_frame_sampler")


def list_recent_videos(
    channel_url: str,
    max_age_days: int,
    max_videos: int,
    min_duration_s: int,
) -> List[VideoMeta]:
    """Return up to *max_videos* eligible videos from *channel_url*/videos.

    Eligibility: ``upload_date`` within *max_age_days* and
    ``duration >= min_duration_s``.
    """
    ytdlp = ensure_tool("yt-dlp")
    videos_url = channel_url.rstrip("/") + "/videos"

    log.info("Fetching video list from %s …", videos_url)

    # Step 1: flat playlist to get video ids/URLs quickly
    cmd = [
        ytdlp,
        "--no-warnings",
        "-J",
        "--flat-playlist",
        "--playlist-end", str(max_videos * 2),  # overfetch to handle filtering
        videos_url,
    ]

    try:
        data = run_cmd_json(cmd, timeout=180)
    except Exception as exc:
        log.error("Failed to fetch channel playlist: %s", exc)
        return []

    entries = data.get("entries", [])
    if not entries:
        log.warning("No entries found in channel playlist")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    eligible: List[VideoMeta] = []

    for entry in entries:
        if len(eligible) >= max_videos:
            break

        video_id = entry.get("id", "")
        url = entry.get("url") or entry.get("webpage_url") or ""
        if not url:
            if video_id:
                url = f"https://www.youtube.com/watch?v={video_id}"
            else:
                continue

        # Flat-playlist entries may have duration and upload_date already
        duration = entry.get("duration")
        upload_date = entry.get("upload_date")  # YYYYMMDD

        # If key metadata is missing, fetch individual video info
        if duration is None or upload_date is None:
            try:
                detail_cmd = [
                    ytdlp,
                    "--no-warnings",
                    "-J",
                    "--no-playlist",
                    url,
                ]
                detail = run_cmd_json(detail_cmd, timeout=60)
                duration = detail.get("duration", 0)
                upload_date = detail.get("upload_date", "")
            except Exception:
                log.debug("Skipping %s — could not fetch details", video_id)
                continue

        if not duration or not upload_date:
            continue

        # Filter: minimum duration
        if duration < min_duration_s:
            log.debug("Skipping %s — duration %.0fs < %ds", video_id, duration, min_duration_s)
            continue

        # Filter: age
        try:
            vid_date = datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)
            if vid_date < cutoff:
                log.debug("Skipping %s — too old (%s)", video_id, upload_date)
                continue
        except ValueError:
            continue

        title = entry.get("title", video_id)
        eligible.append(
            VideoMeta(
                video_id=video_id,
                title=title,
                webpage_url=url,
                duration_s=float(duration),
                upload_date=upload_date,
            )
        )

    log.info("Found %d eligible videos (from %d total entries)", len(eligible), len(entries))
    return eligible
