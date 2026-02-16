from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class VideoMeta:
    video_id: str
    title: str
    webpage_url: str
    duration_s: float
    upload_date: str  # YYYYMMDD


def classify_match_type(title: str) -> str:
    """Classify a video title as 'singles', 'doubles', or 'unknown'.

    Doubles titles contain a '/' in the player names on either side of 'vs',
    e.g. "Johns/Tardio vs Shimabukuro/Funemizu at PPA Tour ...".
    """
    match = re.split(r"\s+vs\s+", title, maxsplit=1, flags=re.IGNORECASE)
    if len(match) < 2:
        return "unknown"

    left = match[0]
    # Strip everything from " at " onward on the right side
    right = re.split(r"\s+at\s+", match[1], maxsplit=1, flags=re.IGNORECASE)[0]

    if "/" in left or "/" in right:
        return "doubles"
    return "singles"
