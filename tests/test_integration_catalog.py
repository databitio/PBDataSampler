"""Integration tests for ``list_recent_videos()`` with mocked yt-dlp responses."""
from __future__ import annotations

from unittest.mock import patch

from conftest import build_ytdlp_entry, build_ytdlp_playlist_json, days_ago_date
from ppa_frame_sampler.youtube.catalog import list_recent_videos

CATALOG = "ppa_frame_sampler.youtube.catalog"


@patch(f"{CATALOG}.ensure_tool", return_value="/fake/bin/yt-dlp")
@patch(f"{CATALOG}.run_cmd_json")
class TestListRecentVideos:
    """Catalog integration: filtering by age, duration, cap, and detail fetch."""

    def test_excludes_old_videos(self, mock_json, mock_tool):
        entries = [
            build_ytdlp_entry("old1", 600, days_ago_date(400)),
            build_ytdlp_entry("new1", 600, days_ago_date(10)),
        ]
        mock_json.return_value = build_ytdlp_playlist_json(entries)

        result = list_recent_videos("https://example.com/@ch", 365, 200, 120)

        assert len(result) == 1
        assert result[0].video_id == "new1"

    def test_excludes_short_videos(self, mock_json, mock_tool):
        entries = [
            build_ytdlp_entry("short1", 60, days_ago_date(5)),
            build_ytdlp_entry("long1", 600, days_ago_date(5)),
        ]
        mock_json.return_value = build_ytdlp_playlist_json(entries)

        result = list_recent_videos("https://example.com/@ch", 365, 200, 120)

        assert len(result) == 1
        assert result[0].video_id == "long1"

    def test_combined_age_and_duration_filter(self, mock_json, mock_tool):
        entries = [
            build_ytdlp_entry("old_long", 600, days_ago_date(400)),
            build_ytdlp_entry("new_short", 60, days_ago_date(5)),
            build_ytdlp_entry("old_short", 30, days_ago_date(500)),
            build_ytdlp_entry("new_long", 1200, days_ago_date(10)),
        ]
        mock_json.return_value = build_ytdlp_playlist_json(entries)

        result = list_recent_videos("https://example.com/@ch", 365, 200, 120)

        assert len(result) == 1
        assert result[0].video_id == "new_long"

    def test_max_videos_cap(self, mock_json, mock_tool):
        entries = [
            build_ytdlp_entry(f"vid{i}", 600, days_ago_date(5))
            for i in range(20)
        ]
        mock_json.return_value = build_ytdlp_playlist_json(entries)

        result = list_recent_videos("https://example.com/@ch", 365, 5, 120)

        assert len(result) == 5

    def test_empty_playlist_returns_empty(self, mock_json, mock_tool):
        mock_json.return_value = build_ytdlp_playlist_json([])

        result = list_recent_videos("https://example.com/@ch", 365, 200, 120)

        assert result == []

    def test_missing_metadata_triggers_detail_fetch(self, mock_json, mock_tool):
        entry_no_duration = {
            "id": "vid_no_dur",
            "url": "https://www.youtube.com/watch?v=vid_no_dur",
            "title": "No Duration",
            "upload_date": days_ago_date(5),
            # duration intentionally missing → triggers detail fetch
        }
        playlist = build_ytdlp_playlist_json([entry_no_duration])
        detail = {"duration": 600, "upload_date": days_ago_date(5)}
        mock_json.side_effect = [playlist, detail]

        result = list_recent_videos("https://example.com/@ch", 365, 200, 120)

        assert len(result) == 1
        assert result[0].video_id == "vid_no_dur"
        assert mock_json.call_count == 2
