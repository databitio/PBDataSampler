# PPA Frame Sampler — Developer Context

## Project Overview

PPA Frame Sampler (`ppa-frame-sampler`) is a CLI tool that samples video data from recent PPA Tour YouTube videos for CVAT labeling and model training. It requires no YouTube API key — it uses `yt-dlp` for all YouTube interactions.

The original specification is in [PLAN.txt](PLAN.txt) (§1–§16). The court detection feature spec is in [CourtDetectionPlan.md](CourtDetectionPlan.md) (§1–§16). The current implementation covers the clips pipeline (channel resolution, video cataloging, timestamp sampling, segment download). Frame extraction and burst quality filtering exist in the codebase but are not wired into the clips pipeline (see Refactors below). The court-frames pipeline is planned (see Features).

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
│   ├── court_scorer.py     # Court-presence scoring heuristics (PLANNED)
│   ├── metrics.py          # Motion, static, edge, overlay, scene-cut metrics (OpenCV)
│   └── models.py           # FilterDecision, FilterMetrics dataclasses
├── output/
│   ├── naming.py           # safe_slug() filesystem-safe naming
│   ├── manifest.py         # JSON manifest writer
│   ├── zipper.py           # Optional zip archive creation
│   └── cleanup.py          # Temp directory cleanup
└── pipeline/
    ├── collector.py        # Clips collection loop (run_collection)
    └── court_collector.py  # Court-frame collection loop (PLANNED)
```

### Pipeline Flow — Clips Mode (`--mode clips`, default)

1. Resolve channel URL (search or `--channel-url` override)
2. Fetch candidate videos via `yt-dlp --flat-playlist` + binary search for date boundaries (cached persistently)
3. Filter by age, duration, and optionally match type
4. Loop until `total_frames / frames_per_sample` clips collected:
   - Pick random video → sample biased timestamp → download short MP4 segment
5. Write `run_manifest.json` + optional zip

### Pipeline Flow — Court-Frames Mode (`--mode court-frames`, planned)

1. Resolve channel URL + fetch/filter candidates (same as clips mode)
2. For each eligible video:
   a. Generate N candidate timestamps (biased away from intros/outros)
   b. Download 1–2s clip per candidate → extract 3–5 frames
   c. Score each frame for court presence (line density, court color, geometry, overlay penalty, blur)
   d. Keep highest-scoring accepted frame (or skip video)
3. Save frames to flat `output/court_detections/` directory
4. Write `court_detection_manifest.json`

### Key Design Decisions

- **Two pipeline modes**: `--mode clips` (default) downloads short MP4 clips for CVAT labeling. `--mode court-frames` (planned) extracts one court-visible frame per video for keypoint model training.
- **Clips, not frames (clips mode)**: The clips pipeline downloads short MP4 clips rather than extracting individual JPEG/PNG frames. Frame extraction and quality filtering modules exist but were decoupled from the clips pipeline to simplify initial usage.
- **Per-run directories (clips mode)**: Each clips run creates `output/frames/<run_id>/` for isolation.
- **Flat output (court-frames mode)**: Court frames go to a single `output/court_detections/` directory (no per-run subdirs) for training data ingest.
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

- **Court Detection Dataset Mode** (2026-02-20, planned) — [Details](.claude/context-docs/features/court-detection-mode.md) | [Spec](CourtDetectionPlan.md)
  New `--mode court-frames` pipeline: extracts one court-visible frame per eligible video into a flat `output/court_detections/` directory for court keypoint model training. Uses heuristic scoring (line density, court color, geometry, overlay penalty, blur) to select the best frame per video. Reuses existing channel/catalog/sampling infrastructure; adds new court-presence scoring and per-video frame selection.

- **Match Type Filtering (Singles/Doubles)** (2026-02-16) — [Details](.claude/context-docs/features/match-type-filtering.md)
  Filter videos by match type (`--match-type singles|doubles|both`) using a title-based heuristic that detects `/` in player names to distinguish doubles from singles. Recognises multiple separator formats (`vs`, `vs.`, `takes on`, `against`, `faces`) for both current and older PPA title styles.

- **Minimum Age Filter (--min-age-days)** (2026-02-15) — [Details](.claude/context-docs/features/min-age-days-filter.md)
  Exclude videos uploaded more recently than N days ago, complementing `--max-age-days` to create a date-range window for video eligibility.

## Performance

- **Catalog Binary Search Optimization** (2026-02-16) — [Details](.claude/context-docs/performance/catalog-binary-search.md)
  Rewrote `catalog.py` to use flat-playlist + binary search for date boundaries instead of sequential `--print` mode. Any date range (including 1-2 years old) now works efficiently. Fast path for entries with `upload_date` (tests), slow path with binary search for real YouTube.

## Refactors

- **Clips-only pipeline** (2026-02-15) — Frame extraction (`media/extractor.py`) and burst quality filtering (`filter/quality_filter.py`) exist in the codebase but are not wired into `collector.py`. The clips pipeline saves MP4 clips directly. Re-integrating these into clips mode is a future task per PLAN.txt §5–§8. Note: `extractor.py` will be activated by the planned court-frames mode.

## CLI Quick Reference

```
ppa-frame-sampler [OPTIONS]

Mode:        --mode (clips|court-frames)                              # PLANNED

Shared:      --channel-query, --channel-url
             --min-age-days, --max-age-days, --max-videos, --min-video-duration-s, --match-type
             --seed

Clips mode:  --frames-per-sample, --total-frames
             --bias-mode (hard_margin|soft_bias), --intro-margin-s, --outro-margin-s
             --out, --tmp, --format (jpg|png), --zip, --keep-tmp
             --min-motion-score, --max-static-score, --min-edge-density,
             --max-overlay-coverage, --reject-on-scene-cuts, --scene-cut-rate-max
             --buffer-seconds, --max-retries-per-burst

Court mode:  --court-out-dir, --court-frame-format (jpg|png)          # PLANNED
             --court-sample-attempts-per-video, --court-intro-margin-s
             --court-outro-margin-s, --court-save-manifest
```
