# PPA Frame Sampler — Developer Context

## Project Overview

PPA Frame Sampler (`ppa-frame-sampler`) is a CLI tool that samples short video clips from recent PPA Tour YouTube videos for CVAT labeling. It requires no YouTube API key — it uses `yt-dlp` for all YouTube interactions.

The original specification is in [PLAN.txt](PLAN.txt) (§1–§16). The current implementation covers the core pipeline (channel resolution, video cataloging, timestamp sampling, segment download) with clips-only output. Frame extraction and burst quality filtering exist in the codebase but are not wired into the main pipeline (see Refactors below).

## Architecture

- **Project Architecture** (2026-02-15) — [Details](.claude/context-docs/architecture/project-architecture.md)
  Full architecture documentation covering module layout, pipeline flow, data flow, and design decisions.

```
src/ppa_frame_sampler/
├── cli.py                  # Argparse CLI, entry point
├── config.py               # Config & FilterThresholds dataclasses
├── run_id.py               # Timestamped run-ID generation
├── logging_utils.py        # Logging setup
├── youtube/
│   ├── channel_resolver.py # Search-based channel URL resolution (yt-dlp ytsearch)
│   ├── catalog.py          # list_recent_videos() — flat-playlist fetch + eligibility
│   ├── models.py           # VideoMeta dataclass, classify_match_type()
│   └── cache.py            # Persistent JSON cache for channel URLs & video catalogs
├── sampling/
│   ├── timestamp_sampler.py # hard_margin / soft_bias (Beta 2.5,2.5) timestamp selection
│   └── segment_planner.py   # Compute segment length from frames_per_sample + buffer
├── media/
│   ├── downloader.py       # yt-dlp --download-sections segment download
│   ├── extractor.py        # ffmpeg frame extraction (not used in current pipeline)
│   ├── ffprobe.py          # ffprobe duration/fps queries
│   └── tools.py            # Tool path resolution, subprocess helpers
├── filter/
│   ├── quality_filter.py   # Burst quality evaluator (not used in current pipeline)
│   ├── metrics.py          # Motion, static, edge, overlay, scene-cut metrics (OpenCV)
│   └── models.py           # FilterDecision, FilterMetrics dataclasses
├── output/
│   ├── naming.py           # safe_slug() filesystem-safe naming
│   ├── manifest.py         # JSON manifest writer
│   ├── zipper.py           # Optional zip archive creation
│   └── cleanup.py          # Temp directory cleanup
└── pipeline/
    └── collector.py        # Main collection loop (run_collection)
```

### Pipeline Flow (Current)

1. Resolve channel URL (search or `--channel-url` override)
2. Fetch candidate videos via `yt-dlp --flat-playlist` + binary search for date boundaries (cached persistently)
3. Filter by age, duration, and optionally match type
4. Loop until `total_frames / frames_per_sample` clips collected:
   - Pick random video → sample biased timestamp → download short MP4 segment
5. Write `run_manifest.json` + optional zip

### Key Design Decisions

- **Clips, not frames**: The pipeline currently downloads short MP4 clips rather than extracting individual JPEG/PNG frames. Frame extraction and quality filtering modules exist but were decoupled from the pipeline to simplify initial usage.
- **Per-run directories**: Each run creates `output/frames/<run_id>/` for isolation.
- **Persistent cache**: Channel URL and video catalog lookups are cached indefinitely in `output/.cache/youtube_cache.json` (no TTL). Each entry includes a `cached_date` for reference. Delete cache entries manually to refresh.
- **No API key**: All YouTube interaction is via yt-dlp (search, flat-playlist, download-sections).

## Dependencies

- **Runtime**: Python 3.10+, `yt-dlp`, `ffmpeg`, `ffprobe`, `opencv-python`
- **Dev**: `pytest`
- Defined in `pyproject.toml`; entry point: `ppa-frame-sampler = ppa_frame_sampler.cli:main`

## Testing

```bash
pytest tests/
```

Tests cover: slug/naming sanitization, timestamp sampler bounds & bias, segment planner, manifest schema, config validation, heuristic validation (known static/live-play frames), integration tests for catalog, burst pipeline, and end-to-end flow.

## Features

- **Match Type Filtering (Singles/Doubles)** (2026-02-16) — [Details](.claude/context-docs/features/match-type-filtering.md)
  Filter videos by match type (`--match-type singles|doubles|both`) using a title-based heuristic that detects `/` in player names to distinguish doubles from singles. Recognises multiple separator formats (`vs`, `vs.`, `takes on`, `against`, `faces`) for both current and older PPA title styles.

- **Minimum Age Filter (--min-age-days)** (2026-02-15) — [Details](.claude/context-docs/features/min-age-days-filter.md)
  Exclude videos uploaded more recently than N days ago, complementing `--max-age-days` to create a date-range window for video eligibility.

## Performance

- **Catalog Binary Search Optimization** (2026-02-16) — [Details](.claude/context-docs/performance/catalog-binary-search.md)
  Rewrote `catalog.py` to use flat-playlist + binary search for date boundaries instead of sequential `--print` mode. Any date range (including 1-2 years old) now works efficiently. Fast path for entries with `upload_date` (tests), slow path with binary search for real YouTube.

## Refactors

- **Clips-only pipeline** (2026-02-15) — Frame extraction (`media/extractor.py`) and burst quality filtering (`filter/quality_filter.py`) exist in the codebase but are not wired into `collector.py`. The pipeline currently saves MP4 clips directly. Re-integrating these modules is a future task per PLAN.txt §5–§8.

## CLI Quick Reference

```
ppa-frame-sampler [OPTIONS]

Channel:     --channel-query, --channel-url
Eligibility: --min-age-days, --max-age-days, --max-videos, --min-video-duration-s, --match-type
Sampling:    --frames-per-sample, --total-frames, --seed
Bias:        --bias-mode (hard_margin|soft_bias), --intro-margin-s, --outro-margin-s
Output:      --out, --tmp, --format (jpg|png), --zip, --keep-tmp
Filtering:   --min-motion-score, --max-static-score, --min-edge-density,
             --max-overlay-coverage, --reject-on-scene-cuts, --scene-cut-rate-max
Retries:     --buffer-seconds, --max-retries-per-burst
```
