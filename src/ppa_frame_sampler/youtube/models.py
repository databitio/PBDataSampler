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


_VERSUS_RE = re.compile(
    r"\s+(?:vs\.?|v|takes\s+on|against|faces)\s+",
    re.IGNORECASE,
)

_CONTEXT_RE = re.compile(
    r"\s+(?:at|on|in)\s+(?:the|championship)\s+",
    re.IGNORECASE,
)


def classify_match_type(title: str) -> str:
    """Classify a video title as 'singles', 'doubles', or 'unknown'.

    Doubles titles contain a '/' in the player names on either side of a
    separator.  Recognised separators (case-insensitive):

    * ``vs``, ``vs.``, ``v``  — "Johns vs Staksrud …"
    * ``takes on``            — "Ben Johns takes on Federico Staksrud …"
    * ``against``, ``faces``  — less common variants

    Context after the matchup (tournament name, etc.) is stripped using
    " at the ", " on Championship ", " in " before checking for '/'.
    """
    parts = _VERSUS_RE.split(title, maxsplit=1)
    if len(parts) < 2:
        return "unknown"

    left = parts[0]
    # Strip tournament / context suffix from the right side
    right = _CONTEXT_RE.split(parts[1], maxsplit=1)[0]

    if "/" in left or "/" in right:
        return "doubles"
    return "singles"
