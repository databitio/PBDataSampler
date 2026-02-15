from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VideoMeta:
    video_id: str
    title: str
    webpage_url: str
    duration_s: float
    upload_date: str  # YYYYMMDD
