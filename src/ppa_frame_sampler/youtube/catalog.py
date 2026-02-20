from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List

from ppa_frame_sampler.media.tools import ensure_tool, run_cmd_json
from ppa_frame_sampler.youtube.cache import get_cached_videos, set_cached_videos
from ppa_frame_sampler.youtube.models import VideoMeta

log = logging.getLogger("ppa_frame_sampler")


def _fetch_flat_playlist(ytdlp: str, videos_url: str) -> list[dict]:
    """Fetch all entries from a channel's videos page via ``--flat-playlist -J``."""
    result = run_cmd_json([
        ytdlp,
        "--no-warnings",
        "--flat-playlist",
        "-J",
        videos_url,
    ], timeout=300)
    return result.get("entries") or []


def _entries_have_upload_date(entries: list[dict]) -> bool:
    """Sample first 3 entries to detect fast-path eligibility."""
    sample = entries[:3]
    return all(e.get("upload_date") for e in sample)


def _fetch_video_date(ytdlp: str, video_url: str) -> str | None:
    """Fetch ``upload_date`` for a single video.  Returns YYYYMMDD or None."""
    try:
        detail = run_cmd_json([
            ytdlp,
            "--no-warnings",
            "--skip-download",
            "-J",
            video_url,
        ], timeout=30)
        return detail.get("upload_date")
    except Exception:
        return None


def _binary_search_date_boundary(
    ytdlp: str,
    entries: list[dict],
    target_date: str,
    find_older: bool,
) -> int:
    """Binary search for a date boundary in a newest-first entry list.

    *find_older=True*:  first index where ``upload_date <= target_date``
        (start of "old enough" entries — used for ``min_age_days``).
    *find_older=False*: first index where ``upload_date < target_date``
        (start of "too old" entries — used for ``max_age_days``).

    Returns *len(entries)* if the boundary is never reached.
    """
    lo, hi = 0, len(entries) - 1
    result = len(entries)

    while lo <= hi:
        mid = (lo + hi) // 2
        entry = entries[mid]
        url = entry.get("url") or f"https://www.youtube.com/watch?v={entry['id']}"
        date_str = _fetch_video_date(ytdlp, url)

        if date_str is None:
            lo = mid + 1
            continue

        if find_older:
            if date_str <= target_date:
                result = mid
                hi = mid - 1
            else:
                lo = mid + 1
        else:
            if date_str < target_date:
                result = mid
                hi = mid - 1
            else:
                lo = mid + 1

    return result


def _search_and_collect(
    ytdlp: str,
    entries: list[dict],
    oldest_date: str,
    newest_date: str | None,
    min_duration_s: int,
    max_videos: int,
) -> list[VideoMeta]:
    """Slow path: binary search for date boundaries then detail-fetch the range."""
    if newest_date:
        range_start = _binary_search_date_boundary(
            ytdlp, entries, newest_date, find_older=True,
        )
    else:
        range_start = 0

    range_end = _binary_search_date_boundary(
        ytdlp, entries, oldest_date, find_older=False,
    )

    # Buffer of 5 entries on each side for minor ordering imprecision.
    range_start = max(0, range_start - 5)
    range_end = min(len(entries), range_end + 5)

    log.info(
        "Binary search narrowed to entries %d–%d of %d total",
        range_start, range_end, len(entries),
    )

    candidates = entries[range_start:range_end]
    eligible: list[VideoMeta] = []

    for entry in candidates:
        if len(eligible) >= max_videos:
            break

        video_id = entry.get("id")
        if not video_id:
            continue

        url = entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"

        try:
            detail = run_cmd_json([
                ytdlp,
                "--no-warnings",
                "--skip-download",
                "-J",
                url,
            ], timeout=30)
        except Exception:
            log.debug("Detail fetch failed for %s, skipping", video_id)
            continue

        upload_date = detail.get("upload_date") or entry.get("upload_date")
        duration = detail.get("duration") or entry.get("duration")
        title = detail.get("title") or entry.get("title", "")

        if not upload_date or duration is None:
            continue

        try:
            duration = float(duration)
        except (ValueError, TypeError):
            continue

        if duration < min_duration_s:
            continue

        if upload_date < oldest_date:
            continue
        if newest_date and upload_date > newest_date:
            continue

        eligible.append(VideoMeta(
            video_id=video_id,
            title=title,
            webpage_url=url,
            duration_s=duration,
            upload_date=upload_date,
        ))

    return eligible


def _filter_by_date_range(
    entries: list[dict],
    ytdlp: str,
    oldest_date: str,
    newest_date: str | None,
    min_duration_s: int,
    max_videos: int,
) -> list[VideoMeta]:
    """Fast path: filter entries in-memory when they already have ``upload_date``."""
    eligible: list[VideoMeta] = []

    for entry in entries:
        if len(eligible) >= max_videos:
            break

        video_id = entry.get("id")
        upload_date = entry.get("upload_date")
        duration = entry.get("duration")
        title = entry.get("title", "")
        url = entry.get("url") or (
            f"https://www.youtube.com/watch?v={video_id}" if video_id else None
        )

        if not video_id or not upload_date:
            continue

        if upload_date < oldest_date:
            continue
        if newest_date and upload_date > newest_date:
            continue

        # Detail-fetch if duration is missing
        if duration is None:
            try:
                detail = run_cmd_json([
                    ytdlp,
                    "--no-warnings",
                    "--skip-download",
                    "-J",
                    url,
                ], timeout=30)
                duration = detail.get("duration")
                upload_date = detail.get("upload_date") or upload_date
            except Exception:
                continue

        if duration is None:
            continue

        try:
            duration = float(duration)
        except (ValueError, TypeError):
            continue

        if duration < min_duration_s:
            continue

        eligible.append(VideoMeta(
            video_id=video_id,
            title=title,
            webpage_url=url,
            duration_s=duration,
            upload_date=upload_date,
        ))

    return eligible


def list_recent_videos(
    channel_url: str,
    max_age_days: int,
    max_videos: int,
    min_duration_s: int,
    min_age_days: int = 0,
) -> List[VideoMeta]:
    """Return up to *max_videos* eligible videos from *channel_url*/videos.

    Eligibility: ``upload_date`` between *min_age_days* and *max_age_days* old,
    and ``duration >= min_duration_s``.

    Results are cached persistently to avoid repeated yt-dlp lookups.

    Uses flat-playlist fetch + binary search for efficient access to any
    date range.
    """
    cached = get_cached_videos(channel_url, max_age_days, min_duration_s, min_age_days, max_videos)
    if cached is not None:
        return cached[:max_videos]

    ytdlp = ensure_tool("yt-dlp")
    videos_url = channel_url.rstrip("/") + "/videos"

    log.info("Fetching video list from %s …", videos_url)

    # Step 1: Flat-playlist fetch (~10-30s, gets id/title/duration for all)
    try:
        entries = _fetch_flat_playlist(ytdlp, videos_url)
    except Exception as exc:
        log.error("Failed to fetch channel playlist: %s", exc)
        return []

    if not entries:
        log.warning("No entries found in channel playlist")
        return []

    # Compute date boundaries as YYYYMMDD strings
    now = datetime.now(timezone.utc)
    oldest_date = (now - timedelta(days=max_age_days)).strftime("%Y%m%d")
    newest_date = (
        (now - timedelta(days=min_age_days)).strftime("%Y%m%d")
        if min_age_days > 0
        else None
    )

    # Pre-filter by duration where available (free, local)
    duration_filtered = [
        e for e in entries
        if e.get("duration") is None or e.get("duration", 0) >= min_duration_s
    ]

    # Choose fast path or slow path
    if _entries_have_upload_date(duration_filtered):
        log.info("Fast path: entries have upload_date, filtering in-memory")
        eligible = _filter_by_date_range(
            duration_filtered, ytdlp, oldest_date, newest_date,
            min_duration_s, max_videos,
        )
    else:
        log.info("Slow path: binary search for date range boundaries")
        eligible = _search_and_collect(
            ytdlp, duration_filtered, oldest_date, newest_date,
            min_duration_s, max_videos,
        )

    log.info("Found %d eligible videos (from %d total entries)", len(eligible), len(entries))
    set_cached_videos(channel_url, max_age_days, min_duration_s, eligible, min_age_days, max_videos)
    return eligible
