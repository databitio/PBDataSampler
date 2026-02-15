from __future__ import annotations

import logging

from ppa_frame_sampler.media.tools import ensure_tool, run_cmd_json

log = logging.getLogger("ppa_frame_sampler")

_FALLBACK_CHANNEL_URL = "https://www.youtube.com/@PPATour"


def resolve_channel_url(channel_query: str) -> str:
    """Best-effort resolver: search YouTube for the channel. No API key required.

    Uses ``yt-dlp ytsearch`` to find a video matching the query, then extracts
    the uploader/channel URL from the result metadata.  Falls back to the known
    PPA Tour handle if the search fails.
    """
    ytdlp = ensure_tool("yt-dlp")

    try:
        # Search for a recent video matching the query
        cmd = [
            ytdlp,
            "--no-warnings",
            "-J",
            "--flat-playlist",
            f"ytsearch5:{channel_query}",
        ]
        data = run_cmd_json(cmd, timeout=60)

        entries = data.get("entries", [])
        for entry in entries:
            channel_url = entry.get("channel_url") or entry.get("uploader_url")
            if channel_url:
                log.info("Resolved channel URL: %s", channel_url)
                return channel_url

    except Exception as exc:
        log.warning("Channel search failed (%s), using fallback URL", exc)

    log.info("Using fallback channel URL: %s", _FALLBACK_CHANNEL_URL)
    return _FALLBACK_CHANNEL_URL
