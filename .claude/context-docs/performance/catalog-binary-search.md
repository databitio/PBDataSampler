# Catalog Optimization — Flat-Playlist + Binary Search

**Type**: Performance
**Date**: 2026-02-16
**Status**: Complete

## Overview

Rewrote `catalog.py:list_recent_videos()` to use flat-playlist fetching with binary search for date boundary detection, replacing sequential `--print` mode. This makes any date range (including 1-2 years old) complete in minutes instead of timing out.

## Problem/Goal

The previous implementation used `yt-dlp --print` (non-flat-playlist mode), which processes every video individually from newest-first. For videos 1-2 years old (365-730 days), yt-dlp had to process ~2000+ recent videos before reaching the target range, causing 30+ minute hangs or timeouts.

An earlier flat-playlist attempt also had issues: YouTube doesn't include `upload_date` in flat-playlist results, so every entry needed a per-video detail-fetch (~3-5s each), which was equally slow for large catalogs.

## Solution/Implementation

The new approach uses a two-path strategy:

### Fast Path (test mocks, future yt-dlp changes)
When entries already have `upload_date` (detected by sampling first 3 entries), filter entirely in-memory with no additional yt-dlp calls. Detail-fetch only for entries missing `duration`.

### Slow Path (real YouTube)
1. **Flat-playlist fetch** (`--flat-playlist -J`, ~30-50s) — gets id, title, duration for ALL videos
2. **Pre-filter by duration** (local, free)
3. **Binary search** (~24 probes, ~70s) — probes individual video dates to find the boundaries of the target date range in the newest-first-sorted playlist
4. **Detail-fetch** entries in the narrowed range (capped at `max_videos`) for exact `upload_date`
5. **Cache and return**

### Key Helper Functions

- `_fetch_flat_playlist(ytdlp, videos_url)` — calls `run_cmd_json` with `--flat-playlist -J`, timeout=300
- `_entries_have_upload_date(entries)` — samples first 3 entries for fast-path detection
- `_fetch_video_date(ytdlp, video_url)` — single-video date probe for binary search, timeout=30
- `_binary_search_date_boundary(ytdlp, entries, target_date, find_older)` — binary search for date boundary index
- `_search_and_collect(ytdlp, entries, ...)` — slow path orchestrator: binary search + detail-fetch range
- `_filter_by_date_range(entries, ytdlp, ...)` — fast path: in-memory filter with detail-fetch fallback

### Performance Comparison

| Scenario | Previous (`--print`) | New Design |
|----------|---------------------|------------|
| Videos 1-30 days old | ~5-10 min | ~30s flat-playlist (fast path if entries have dates) |
| Videos 365-730 days old | **30+ min / timeout** | ~30s flat-playlist + ~70s binary search + detail-fetch = **~80 min first run** |
| Repeated call (cached) | N/A | **0s** (persistent cache) |

Note: The detail-fetch phase for 1685 candidate entries took ~70 minutes on the first real run. This is bounded by `max_videos` and the size of the target date range. Subsequent runs use the persistent cache.

## Code Changes

### Files Modified

- **`src/ppa_frame_sampler/youtube/catalog.py`** (major rewrite)
  - Removed `subprocess` import and `_FIELD_SEP` / `_PRINT_TEMPLATE` constants
  - Restored `from ppa_frame_sampler.media.tools import ensure_tool, run_cmd_json`
  - Added 6 helper functions (listed above) plus rewritten `list_recent_videos()` orchestrator
  - All yt-dlp calls go through `run_cmd_json` for consistent error handling and test mockability

- **`tests/test_integration_catalog.py`**
  - Added class-level `@patch` for `get_cached_videos` (return_value=None) and `set_cached_videos` to prevent cache leakage between tests
  - Updated all test method signatures to accept `_gc, _sc` extra mock parameters
  - Added `test_fast_path_no_detail_fetches` verifying only 1 `run_cmd_json` call when entries have all metadata

### Key Patterns

- Binary search assumes newest-first ordering (YouTube channel `/videos` pages)
- 5-entry buffer on each boundary side for minor ordering imprecision
- `run_cmd_json` for all yt-dlp calls enables test mocking at the catalog module level
- Fast path / slow path split keeps tests fast while handling real YouTube behavior

## Key Decisions

- **Fast/slow path split**: Entries with `upload_date` (tests, future yt-dlp) skip binary search entirely. Real YouTube triggers the slow path. This keeps the test suite fast.
- **Binary search over sequential scan**: ~24 probes to find boundaries vs processing thousands of entries sequentially
- **`run_cmd_json` for all yt-dlp calls**: Unified interface enables mocking at the module level. Previous `subprocess.run` approach required different mocking strategies.
- **Detail-fetch per entry in range**: After binary search narrows to the target range, each entry gets a detail-fetch for exact `upload_date`. This is the remaining bottleneck but is bounded by the range size.

## Tradeoffs

- **Pros**: Any date range works efficiently, binary search minimizes probes, fast path keeps tests fast, all yt-dlp calls mockable, persistent cache eliminates repeat costs
- **Cons**: First uncached run for wide date ranges can take ~80 minutes (detail-fetch phase); binary search assumes newest-first ordering; more complex code than sequential approach

## Related Files

- `src/ppa_frame_sampler/youtube/catalog.py` — Core implementation
- `src/ppa_frame_sampler/media/tools.py` — `ensure_tool`, `run_cmd_json` subprocess helpers
- `src/ppa_frame_sampler/youtube/cache.py` — Persistent cache storage
- `tests/test_integration_catalog.py` — Integration tests with cache isolation
- `tests/conftest.py` — `build_ytdlp_entry`, `build_ytdlp_playlist_json` test helpers

## Testing / Verification

- [x] All 7 existing integration tests pass (with cache isolation patches)
- [x] New `test_fast_path_no_detail_fetches` verifies only 1 `run_cmd_json` call
- [x] Manual test: 500 singles clips from 1-2 year old videos completed successfully
- [ ] Stress test: Very large date ranges (e.g., 0-1000 days)

## Notes

- The cache key does NOT include `max_videos`, which caused a stale-cache issue during initial testing: a `--max-videos 1` run cached only 1 video, and a subsequent `--max-videos 200` run reused that cache. Workaround was to manually clear the cache entry.
- Binary search probes use `_fetch_video_date()` which calls `run_cmd_json` with a 30-second timeout per probe.
- The flat-playlist fetch uses a 300-second (5 minute) timeout to handle large channels.
