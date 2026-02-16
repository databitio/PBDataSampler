# Minimum Age Filter (--min-age-days)

**Type**: Feature
**Date**: 2026-02-15
**Status**: Complete

## Overview

Added a `--min-age-days` CLI flag that excludes videos uploaded more recently than N days ago. This complements the existing `--max-age-days` flag, creating a date-range window for video eligibility (e.g., "videos between 30 and 180 days old").

## Problem/Goal

The existing `--max-age-days` filter only sets an upper bound on video age — there was no way to exclude very recent uploads. Use cases include:
- Avoiding incomplete/processing videos that were just uploaded
- Targeting a specific historical window of tournament footage (e.g., last quarter only, not this week)
- Ensuring videos have stabilized (title corrections, privacy changes) before sampling

## Solution/Implementation

Added a `min_age_days` parameter (default `0`, meaning no minimum) that flows through the full stack:

1. **CLI**: New `--min-age-days` argument (type `int`, default `0`)
2. **Config**: New `min_age_days: int = 0` field on the `Config` dataclass
3. **Catalog**: `list_recent_videos()` computes a `newest_cutoff` date and skips videos newer than it
4. **Cache**: Cache key includes `minage={min_age_days}` to prevent stale results across different filter configurations
5. **Manifest**: `min_age_days` recorded in manifest params for traceability

The filtering logic in `catalog.py` uses two cutoff dates:
- `oldest_cutoff = now - max_age_days` — videos older than this are skipped ("too old")
- `newest_cutoff = now - min_age_days` — videos newer than this are skipped ("too recent"), only when `min_age_days > 0`

## Code Changes

### Files Modified

- **`src/ppa_frame_sampler/cli.py`** — Added `--min-age-days` argument to the argparse parser (under "Video eligibility" group) and wired it to `Config(min_age_days=args.min_age_days)`.

- **`src/ppa_frame_sampler/config.py`** — Added `min_age_days: int = 0` field to the `Config` dataclass, placed alongside `max_age_days` in the YouTube/catalog section.

- **`src/ppa_frame_sampler/pipeline/collector.py`** — Passes `cfg.min_age_days` as a new argument to `list_recent_videos()` and includes `"min_age_days": cfg.min_age_days` in the manifest params dict.

- **`src/ppa_frame_sampler/youtube/catalog.py`** — Added `min_age_days: int = 0` parameter to `list_recent_videos()`. Renamed `cutoff` to `oldest_cutoff` for clarity. Added `newest_cutoff` computation and an additional filter check: `if newest_cutoff and vid_date > newest_cutoff: continue`. Updated docstring. Updated `set_cached_videos()` call to pass `min_age_days`.

- **`src/ppa_frame_sampler/youtube/cache.py`** — Added `min_age_days: int = 0` parameter to both `get_cached_videos()` and `set_cached_videos()`. Updated cache key from `{channel_url}|age={max_age_days}|dur={min_duration_s}` to `{channel_url}|age={max_age_days}|minage={min_age_days}|dur={min_duration_s}` to ensure different filter combinations use separate cache entries.

### Key Patterns

- Default `0` means the feature is a no-op unless explicitly set, preserving backward compatibility
- `newest_cutoff` is only computed when `min_age_days > 0`, avoiding unnecessary datetime math
- Cache key includes the new parameter to prevent returning stale results when the filter changes between runs

## Key Decisions

- **Default 0 (disabled)**: No minimum age by default, matching existing behavior and avoiding surprises for existing users
- **Cache key update**: Including `min_age_days` in the cache key is essential — without it, a cached catalog from a run with `--min-age-days 0` would incorrectly be reused for a run with `--min-age-days 30`
- **Variable rename**: `cutoff` was renamed to `oldest_cutoff` for clarity now that there are two date boundaries

## Tradeoffs

- **Pros**: Simple, backward compatible (default 0), full traceability in manifest, correct cache invalidation
- **Cons**: Adds a parameter to multiple function signatures; no validation that `min_age_days < max_age_days` (would result in zero candidates, caught by the existing "no eligible videos" error)

## Related Files

- `src/ppa_frame_sampler/cli.py` — `--min-age-days` CLI argument
- `src/ppa_frame_sampler/config.py` — `Config.min_age_days` field
- `src/ppa_frame_sampler/youtube/catalog.py` — `newest_cutoff` filtering logic
- `src/ppa_frame_sampler/youtube/cache.py` — Cache key with `minage=` segment
- `src/ppa_frame_sampler/pipeline/collector.py` — Manifest params and argument passing

## Testing / Verification

- [ ] Unit test: `Config(min_age_days=30)` field validation
- [ ] Unit test: `build_parser().parse_args(['--min-age-days', '30'])` CLI parsing
- [ ] Integration test: `--min-age-days 30` excludes videos from the last 30 days
- [ ] Integration test: `--min-age-days 0` (default) behaves identically to previous behavior
- [ ] Verify cache key isolation: different `min_age_days` values produce different cache entries

## Notes

- If `min_age_days >= max_age_days`, the eligible date window is empty and `list_recent_videos()` returns no candidates. This is handled by the existing "No eligible videos found" RuntimeError in `collector.py` — no special validation was added.
- Example usage: `ppa-frame-sampler --min-age-days 7 --max-age-days 90` samples from videos uploaded between 1 week and 3 months ago.
