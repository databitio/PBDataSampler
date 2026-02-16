from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ppa_frame_sampler.youtube.models import VideoMeta

log = logging.getLogger("ppa_frame_sampler")

_CACHE_DIR = Path("output/.cache")
_CACHE_FILE = _CACHE_DIR / "youtube_cache.json"

# Default TTL: 24 hours
_DEFAULT_TTL_S = 86400


def _load_cache() -> Dict[str, Any]:
    if not _CACHE_FILE.exists():
        return {}
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.debug("Cache file corrupt or unreadable, starting fresh")
        return {}


def _save_cache(data: Dict[str, Any]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_cached_channel_url(query: str) -> Optional[str]:
    cache = _load_cache()
    entry = cache.get("channel_urls", {}).get(query)
    if entry and time.time() - entry.get("ts", 0) < _DEFAULT_TTL_S:
        log.info("Using cached channel URL for query %r", query)
        return entry["url"]
    return None


def set_cached_channel_url(query: str, url: str) -> None:
    cache = _load_cache()
    cache.setdefault("channel_urls", {})[query] = {
        "url": url,
        "ts": time.time(),
    }
    _save_cache(cache)


def get_cached_videos(channel_url: str, max_age_days: int, min_duration_s: int) -> Optional[List[VideoMeta]]:
    cache = _load_cache()
    key = f"{channel_url}|age={max_age_days}|dur={min_duration_s}"
    entry = cache.get("video_catalogs", {}).get(key)
    if not entry:
        return None
    if time.time() - entry.get("ts", 0) >= _DEFAULT_TTL_S:
        return None
    log.info("Using cached video catalog (%d videos)", len(entry.get("videos", [])))
    return [
        VideoMeta(
            video_id=v["video_id"],
            title=v["title"],
            webpage_url=v["webpage_url"],
            duration_s=v["duration_s"],
            upload_date=v["upload_date"],
        )
        for v in entry["videos"]
    ]


def set_cached_videos(
    channel_url: str,
    max_age_days: int,
    min_duration_s: int,
    videos: List[VideoMeta],
) -> None:
    cache = _load_cache()
    key = f"{channel_url}|age={max_age_days}|dur={min_duration_s}"
    cache.setdefault("video_catalogs", {})[key] = {
        "ts": time.time(),
        "videos": [
            {
                "video_id": v.video_id,
                "title": v.title,
                "webpage_url": v.webpage_url,
                "duration_s": v.duration_s,
                "upload_date": v.upload_date,
            }
            for v in videos
        ],
    }
    _save_cache(cache)
