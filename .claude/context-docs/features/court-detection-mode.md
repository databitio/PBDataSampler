# Court Detection Dataset Mode

**Type**: Feature
**Date**: 2026-02-20
**Status**: Complete

## Overview

A new `--mode court-frames` pipeline that scans eligible PPA videos and extracts one representative frame per video where the pickleball court is visible. Outputs a flat directory of JPEG/PNG frames plus a manifest, intended for training a court keypoint model (14 keypoints).

## Problem/Goal

The existing clips-only pipeline produces short MP4 bursts for general CVAT labeling. A separate dataset is needed specifically for court keypoint model training: one high-quality, court-visible frame per video in a flat directory structure. This requires different selection logic (court-presence scoring) and different output structure (single frames, not clips).

## Solution/Implementation

### CLI Mode Switch

Add a top-level `--mode` flag to the CLI:

- `--mode clips` (default) — existing burst clip sampling pipeline
- `--mode court-frames` — new one-frame-per-video court extraction pipeline

This is preferred over a boolean flag because additional dataset generation modes are likely in the future.

### Court-Frame Specific CLI Options

New flags scoped to court-frame mode:

| Flag | Default | Description |
|---|---|---|
| `--court-out-dir` | `output/court_detections` | Output directory for court frames |
| `--court-frame-format` | `jpg` | Image format (jpg/png) |
| `--court-sample-attempts` | `5` | Candidate timestamps to try per video |
| `--court-frames-per-attempt` | `3` | Frames to extract per candidate clip |
| `--court-segment-seconds` | `2.0` | Clip length per candidate timestamp |
| `--court-intro-margin-s` | `20` | Seconds to skip at video start |
| `--court-outro-margin-s` | `20` | Seconds to skip at video end |
| `--court-resize-width` | `640` | Resize width for scoring |
| `--court-min-score` | `0.15` | Minimum composite score to accept a frame |
| `--no-court-save-manifest` | *(on)* | Disable writing court_detection_manifest.json |

### Pipeline Flow (Per Video)

1. **Generate candidate timestamps** — Sample N timestamps per video using existing bias logic (hard_margin or soft_bias), biased away from intros/outros
2. **Download tiny clip** — Download a 1-2 second MP4 clip around each candidate timestamp (reuses existing yt-dlp download machinery)
3. **Extract candidate frames** — Pull 3-5 evenly spaced frames from each clip (reuses `media/extractor.py`)
4. **Score frames for court presence** — Composite heuristic scoring (`filter/court_scorer.py`):
   - Line density (Canny + HoughLinesP pixel coverage)
   - Court-color ratio (HSV masks for blue/green/orange court surfaces)
   - Blur score (Laplacian variance — prefer sharp frames)
   - Overlay penalty (edge density in top/bottom 15% scoreboard bands)
   - Composite formula: `0.35 * line_norm + 0.30 * color + 0.20 * blur_norm - 0.15 * overlay`
5. **Select best frame** — Across all attempts for a video, keep the highest-scoring frame above `court_min_score` threshold (or skip the video if all fail)
6. **Save frame + manifest entry**

### Output Structure

Flat directory (no per-run subdirectories):

```
output/court_detections/
  <video_id>_<timestamp_ms>ms.jpg
  <video_id>_<timestamp_ms>ms.jpg
  ...
  court_detection_manifest.json
```

### Manifest Schema

`court_detection_manifest.json` includes:
- Run metadata (timestamp, seed, CLI args)
- Video eligibility stats (total cataloged, eligible, attempted, success/fail counts)
- Per-video record: video_id, title, upload_date, duration_s, match_type, attempted_timestamps, selected_timestamp_ms, output_file, court_presence_score, status, rejection_reasons

### New Modules

- `pipeline/court_collector.py` — Court-frame collection loop (`run_court_collection()`)
- `filter/court_scorer.py` — Court-presence scoring (`CourtScore` dataclass, `score_frame()`, `pick_best_frame()`)

### Reused Components

- Channel resolution (`youtube/channel_resolver.py`)
- Video cataloging + caching (`youtube/catalog.py`, `youtube/cache.py`)
- Age/duration/match-type filtering
- Timestamp sampling with bias (`sampling/timestamp_sampler.py`)
- Segment download (`media/downloader.py`)
- Frame extraction (`media/extractor.py` — activated by this mode)
- safe_slug naming, manifest writing

## Key Decisions

- **Separate pipeline, not a modification of the existing one**: Keeps the clips workflow stable and avoids mixing different logic paths
- **`--mode` flag over boolean**: Extensible for future dataset generation modes
- **One frame per video, at most**: Skip videos with no acceptable frame rather than include garbage
- **Heuristic MVP first**: Court-presence scoring uses OpenCV heuristics (lines, color, geometry) rather than requiring a trained model. A lightweight classifier can replace heuristics in Phase 2 once labeled data exists.
- **Flat output directory**: Single directory with no run subdirectories, optimised for training data ingest
- **Quality over quantity**: Better to skip bad videos than include frames without visible courts
- **Configurable thresholds**: All heuristic thresholds are CLI-configurable, not hardcoded

## Implementation Sequence

1. Add CLI `--mode` switch and court-frame config options
2. Reuse catalog + eligibility pipeline (no changes needed)
3. Implement per-video candidate timestamp generation
4. Download tiny clip + extract candidate frames (activates `media/extractor.py`)
5. Implement court-presence scoring heuristics (`filter/court_scorer.py`)
6. Select one best frame per video and save to flat directory
7. Write `court_detection_manifest.json`
8. Add tests (unit + integration)
9. Tune thresholds on real PPA samples
10. Update README + CLAUDE.md

## Phase 2 Enhancements (Post-MVP)

- Train a lightweight binary court-presence classifier to replace heuristics
- Court-line confidence heuristic (line intersection structure for 14-keypoint coverage)
- Diversity controls (cap per tournament, enforce date spread, singles/doubles mix)
- Overlay-aware cropping preview for frames with scorebug in corners
- Possible migration to subcommands (`ppa-frame-sampler clips ...`, `ppa-frame-sampler court-frames ...`)

## Related Files

- `CourtDetectionPlan.md` — Full feature specification
- `PLAN.txt` — Original project specification (clips pipeline)
- `src/ppa_frame_sampler/pipeline/collector.py` — Existing clips pipeline (reference for new court pipeline)
- `src/ppa_frame_sampler/media/extractor.py` — Frame extraction (to be activated)
- `src/ppa_frame_sampler/filter/metrics.py` — Existing OpenCV metrics (partial reuse)

## Testing / Verification

- [x] Unit: court scorer returns deterministic scores on fixture images (`test_court_scorer.py`)
- [x] Unit: CourtConfig defaults and construction (`test_config_court.py`)
- [x] Unit: CLI arg parsing for court flags (`test_config_court.py`)
- [x] Unit: best-frame selection logic (`test_court_scorer.py::TestPickBestFrame`)
- [x] Integration: mock catalog -> run court mode -> outputs one frame/video (`test_integration_court_pipeline.py`)
- [x] Integration: failure handling — download fail / no valid frame (`test_integration_court_pipeline.py::test_skipped_videos_recorded`)
- [x] Integration: manifest structure and content (`test_integration_court_pipeline.py::test_manifest_written`)
- [x] Integration: minimum score threshold rejects low frames (`test_integration_court_pipeline.py::test_min_score_threshold_rejects_low_frames`)
- [x] Integration: PNG format support (`test_integration_court_pipeline.py::test_png_format`)
- [x] Regression: existing clips mode still works unchanged (`test_integration_court_pipeline.py::TestClipsRegressionFromCourt`)

## Notes

- The `media/extractor.py` module is now used by the court-frames pipeline (first pipeline to activate it).
- Court-presence scoring (`filter/court_scorer.py`) is the only truly new logic; everything else (catalog, sampling, download, extraction) is reused.
- The `--mode` flag dispatches to `run_collection()` or `run_court_collection()` in `cli.py`. Both pipelines share channel/eligibility arguments.
- A configurable `--court-min-score` threshold (default 0.15) rejects frames with composite scores below the minimum, ensuring quality output.
