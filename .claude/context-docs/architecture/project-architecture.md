# Project Architecture — PPA Frame Sampler

**Type**: Architecture
**Date**: 2026-02-15
**Status**: Complete

## Overview

PPA Frame Sampler is a modular CLI application that samples short video clips from the PPA Tour YouTube channel for CVAT labeling. The architecture follows the specification in `PLAN.txt` (sections 1-16), with a layered design separating YouTube discovery, sampling strategy, media handling, quality filtering, and output management into independent modules.

## Problem/Goal

Build a local, reproducible tool that collects representative video frames from PPA Tour matches without requiring a YouTube API key, full video downloads, or cloud infrastructure. The tool must produce datasets ready for CVAT import with full traceability via manifests.

## Solution/Implementation

### Module Layout

The codebase is organized into five functional layers under `src/ppa_frame_sampler/`:

**1. YouTube Layer (`youtube/`)**
- `channel_resolver.py` — Resolves channel URL via `yt-dlp ytsearch` with fallback to `@PPATour` handle
- `catalog.py` — Fetches video metadata via `yt-dlp --flat-playlist` + binary search for date boundaries, filters by age/duration
- `models.py` — `VideoMeta` dataclass and `classify_match_type()` title heuristic
- `cache.py` — Persistent JSON file cache for channel URLs and video catalogs (`output/.cache/youtube_cache.json`), no TTL

**2. Sampling Layer (`sampling/`)**
- `timestamp_sampler.py` — Two bias modes: `hard_margin` (uniform within margins) and `soft_bias` (Beta(2.5, 2.5) distribution)
- `segment_planner.py` — Calculates download segment length from `frames_per_sample / fps_guess + buffer_seconds`

**3. Media Layer (`media/`)**
- `downloader.py` — Uses `yt-dlp --download-sections` for segment-only downloads (no full videos)
- `extractor.py` — ffmpeg-based frame extraction (exists but not wired into current pipeline)
- `ffprobe.py` — Duration/FPS queries via ffprobe
- `tools.py` — Tool path resolution (`ensure_tool()`), subprocess helpers (`run_cmd`, `run_cmd_json`)

**4. Filter Layer (`filter/`)**
- `quality_filter.py` — Burst evaluator using OpenCV metrics (exists but not wired into current pipeline)
- `metrics.py` — Five heuristic metrics: motion score, static score, edge density, overlay coverage, scene-cut rate
- `models.py` — `FilterDecision` and `FilterMetrics` dataclasses

**5. Output Layer (`output/`)**
- `naming.py` — `safe_slug()` for filesystem-safe identifiers
- `manifest.py` — JSON manifest writer
- `zipper.py` — Optional zip archive for CVAT upload
- `cleanup.py` — Temp directory cleanup

**6. Orchestration**
- `cli.py` — Argparse CLI with all flags, fail-fast tool checks (`yt-dlp`, `ffmpeg`, `ffprobe`)
- `config.py` — `Config` and `FilterThresholds` frozen dataclasses
- `pipeline/collector.py` — Main `run_collection()` loop: resolve -> catalog -> filter -> sample -> download -> manifest
- `run_id.py` — Timestamped run-ID generation
- `logging_utils.py` — Logging setup

### Current Pipeline Flow

```
CLI (cli.py)
  └── run_collection(cfg) in collector.py
        ├── resolve_channel_url() or --channel-url override
        ├── list_recent_videos() with persistent cache
        ├── classify_match_type() filter (if --match-type != both)
        ├── Loop: total_frames / frames_per_sample iterations
        │     ├── random.choice(candidates)
        │     ├── sample_timestamp() with bias mode
        │     ├── download_segment() via yt-dlp --download-sections
        │     └── Record to manifest (collected or download_error)
        ├── write_manifest() -> run_manifest.json
        └── Optional: zip_frames()
```

### Data Flow

```
YouTube Channel URL
  → yt-dlp flat-playlist + binary search → VideoMeta[] (persistent cache)
  → age/duration/match-type filters → candidate pool
  → random selection + biased timestamp → (video, start_s, end_s)
  → yt-dlp download-sections → MP4 clip in output/<run_id>/
  → manifest entry with video_id, timestamp, status, match_type
```

## Code Changes

### Files in Current State (vs committed)

- **`cli.py`** — Added `--min-age-days` flag (default 0) to exclude videos newer than N days
- **`config.py`** — Added `min_age_days: int = 0` field to `Config` dataclass
- **`pipeline/collector.py`** — Passes `cfg.min_age_days` to `list_recent_videos()` and includes it in manifest params
- **`youtube/catalog.py`** — Added `min_age_days` parameter with `newest_cutoff` date filter; updated docstring
- **`youtube/cache.py`** — Added `min_age_days` to cache key and function signatures for correct cache invalidation
- **`README.md`** — New file: comprehensive user-facing documentation with CLI reference, usage examples, and architecture overview

### Key Patterns

- All YouTube interaction uses `yt-dlp` subprocess calls via `tools.py` helpers (no API key)
- Configuration is immutable (`frozen=True` dataclasses)
- Cache keying includes all filter params to avoid stale data: `{channel_url}|age={max_age_days}|minage={min_age_days}|dur={min_duration_s}`
- Per-run isolation via timestamped subdirectories under `output/frames/`
- Manifest records every sample attempt (including failures) for full traceability

## Key Decisions

- **yt-dlp over YouTube API**: No API key required, simpler deployment, `--download-sections` enables segment-only downloads without full video fetches
- **Clips-only pipeline**: Frame extraction and quality filtering modules exist but were decoupled from the main pipeline (`collector.py`) to simplify initial usage. Re-integration is a future task per PLAN.txt sections 5-8
- **Beta(2.5, 2.5) for soft bias**: Bell-shaped distribution over normalized timestamp gives natural intro/outro avoidance without hard cutoffs
- **Persistent cache with filter-aware keys**: No TTL — cache entries persist indefinitely across sessions. Composite keys ensure different filter configurations use separate cache entries. Each entry includes a `cached_date` field for human reference.
- **Per-run directories**: Each run creates `output/frames/<run_id>/` to prevent overwriting previous runs and enable comparison
- **"Unknown" match types kept**: Videos that don't match singles/doubles patterns (highlights, compilations) are retained to avoid silent data loss
- **Frozen dataclasses**: `Config` and `FilterThresholds` are immutable after construction, preventing accidental mutation during the pipeline

## Tradeoffs

- **Pros**: Modular, testable, no API key needed, reproducible (seedable), minimal bandwidth (segment downloads), full traceability (manifests), cached lookups
- **Cons**: Depends on yt-dlp CLI stability, title-based match classification is fragile to format changes, quality filtering not yet integrated, no parallel downloads

## Related Files

- `PLAN.txt` — Full specification (sections 1-16) covering all planned functionality
- `pyproject.toml` — Package definition, dependencies (`yt-dlp`, `opencv-python`), entry point
- `tests/` — Unit tests (slug, sampler bounds, segment planner, manifest, config) and integration tests (catalog, burst pipeline, end-to-end)

## Testing / Verification

- [x] Unit tests: slug sanitization, timestamp sampler bounds/bias, segment planner, manifest schema, config validation
- [x] Integration tests: catalog listing, burst pipeline, end-to-end flow
- [x] Heuristic validation: static/menu frame rejection, live-play acceptance
- [ ] Integration test: min-age-days filter correctly excludes recent videos

## Notes

- The `filter/` and `media/extractor.py` modules are fully implemented but not called from `collector.py`. They were removed from the pipeline in commit `53e2f02` ("Remove quality filters, keep clips only"). Re-integrating them would involve adding frame extraction after download and quality evaluation before accepting a clip.
- External tool dependencies (`yt-dlp`, `ffmpeg`, `ffprobe`) are validated at startup via `ensure_tool()` which checks PATH availability.
- The cache file (`output/.cache/youtube_cache.json`) should be excluded from version control and is not committed.
