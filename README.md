# PPA Frame Sampler

A CLI tool that samples video data from recent [PPA Tour](https://www.youtube.com/@PPATour) YouTube videos for CVAT labeling and court keypoint model training.

No YouTube API key required — all interaction is handled via `yt-dlp`.

Two modes:
- **Clips mode** (default) — Downloads short MP4 clips for CVAT labeling
- **Court-frames mode** — Extracts one court-visible frame per video for court keypoint model training

## How It Works

1. **Channel Resolution** — Locates the PPA Tour YouTube channel via search (or a direct `--channel-url` override)
2. **Video Cataloging** — Fetches recent videos, filtering by age, duration, and optionally match type (singles/doubles)
3. **Timestamp Sampling** — Selects random timestamps biased away from intros/outros using either hard margins or a Beta(2.5, 2.5) distribution
4. **Segment Download** — Downloads only short MP4 clips around each sampled timestamp (no full video downloads)
5. **Output** — Saves clips to per-run directories with a JSON manifest documenting every sample

## Prerequisites

- **Python 3.10+**
- **yt-dlp** — `pip install yt-dlp` or [install separately](https://github.com/yt-dlp/yt-dlp#installation)
- **ffmpeg / ffprobe** — [Download](https://ffmpeg.org/download.html) and ensure both are on your `PATH`

## Installation

```bash
git clone <repo-url>
cd PBDataSampler
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

## Quick Start

```bash
# Sample 25 clips (500 frames / 20 frames-per-sample) from recent PPA Tour videos
ppa-frame-sampler

# Reproducible run with a fixed seed
ppa-frame-sampler --seed 42

# Only doubles matches, last 6 months, output as zip
ppa-frame-sampler --match-type doubles --max-age-days 180 --zip

# Court-frames mode: one court-visible frame per video
ppa-frame-sampler --mode court-frames --max-videos 50

# Custom output directory
ppa-frame-sampler --out my_dataset/frames --tmp my_dataset/tmp
```

## CLI Options

| Category | Flag | Default | Description |
|---|---|---|---|
| **Channel** | `--channel-query` | `"PPA Tour"` | Search query to find the channel |
| | `--channel-url` | *(auto)* | Direct channel URL override |
| **Eligibility** | `--min-age-days` | `0` | Min video age in days (exclude recent uploads) |
| | `--max-age-days` | `365` | Max video age in days |
| | `--max-videos` | `200` | Max candidate videos to consider |
| | `--min-video-duration-s` | `120` | Minimum video duration (seconds) |
| | `--match-type` | `both` | Filter: `singles`, `doubles`, or `both` |
| **Sampling** | `--frames-per-sample` | `20` | Frames per burst (determines clip length) |
| | `--total-frames` | `500` | Target total frames (clips = total / per-sample) |
| | `--seed` | *(random)* | Random seed for reproducibility |
| **Bias** | `--bias-mode` | `soft_bias` | `hard_margin` or `soft_bias` (Beta distribution) |
| | `--intro-margin-s` | `15` | Seconds to avoid at video start |
| | `--outro-margin-s` | `15` | Seconds to avoid at video end |
| **Output** | `--out` | `output/frames` | Output directory (run subdirs created within) |
| | `--tmp` | `output/tmp` | Temporary download directory |
| | `--format` | `jpg` | Image format (`jpg` or `png`) |
| | `--zip` | *(off)* | Create a zip archive of the output |
| | `--keep-tmp` | *(off)* | Keep temporary files after completion |
| **Filtering** *(not active in clips-only mode)* | `--min-motion-score` | `0.015` | Min inter-frame motion (0–1) |
| | `--max-static-score` | `0.92` | Max static frame ratio (0–1) |
| | `--min-edge-density` | `0.01` | Min Canny edge density (0–1) |
| | `--max-overlay-coverage` | `0.70` | Max static overlay coverage (0–1) |
| | `--reject-on-scene-cuts` | *(off)* | Reject bursts with high scene-cut rates |
| | `--scene-cut-rate-max` | `0.50` | Scene-cut rate threshold |
| **Retries** | `--buffer-seconds` | `1.0` | Extra seconds to download around the clip |
| | `--max-retries-per-burst` | `5` | Max download retries per burst |

## Output Structure

Each run creates an isolated subdirectory:

```
output/frames/<run_id>/
├── <video_id>_<timestamp_ms>ms.mp4    # Downloaded clip
├── <video_id>_<timestamp_ms>ms.mp4    # ...
└── run_manifest.json                  # Full run metadata
```

The `run_manifest.json` documents all parameters, candidate counts, and per-sample details (video ID, timestamp, status, match type).

## Match Type Filtering

Videos are classified as **singles**, **doubles**, or **unknown** based on title heuristics:

- Titles containing a matchup separator with `/` in player names are classified as **doubles** (e.g., `"Johns/Tardio vs Shimabukuro/Funemizu"`)
- Titles with a separator but no `/` are **singles** (e.g., `"Hunter Johnson vs Christian Alshon"`)
- Titles without a recognised separator are **unknown** and are always included (highlights, compilations, etc.)

Recognised separators (case-insensitive): `vs`, `vs.`, `v`, `takes on`, `against`, `faces`

```bash
ppa-frame-sampler --match-type singles   # Singles matches only
ppa-frame-sampler --match-type doubles   # Doubles matches only
ppa-frame-sampler --match-type both      # All videos (default)
```

## Court-Frames Mode

Use `--mode court-frames` to extract one court-visible frame per eligible video for court keypoint model training:

```bash
# Extract court frames from up to 50 recent videos
ppa-frame-sampler --mode court-frames --max-videos 50

# With stricter quality threshold and PNG output
ppa-frame-sampler --mode court-frames --court-min-score 0.25 --court-frame-format png

# Doubles matches only, custom output directory
ppa-frame-sampler --mode court-frames --match-type doubles --court-out-dir my_court_data/
```

The pipeline scores candidate frames using heuristics (line density, court color, blur, overlay penalty) and keeps the best frame per video above the `--court-min-score` threshold (default 0.15).

Output is a flat directory:

```
output/court_detections/
├── <video_id>_<timestamp_ms>ms.jpg
├── <video_id>_<timestamp_ms>ms.jpg
└── court_detection_manifest.json
```

| Flag | Default | Description |
|---|---|---|
| `--court-out-dir` | `output/court_detections` | Output directory |
| `--court-frame-format` | `jpg` | Image format (`jpg` or `png`) |
| `--court-sample-attempts` | `5` | Candidate timestamps per video |
| `--court-frames-per-attempt` | `3` | Frames extracted per candidate clip |
| `--court-segment-seconds` | `2.0` | Clip length per candidate |
| `--court-intro-margin-s` | `20` | Seconds to skip at video start |
| `--court-outro-margin-s` | `20` | Seconds to skip at video end |
| `--court-resize-width` | `640` | Resize width for scoring |
| `--court-min-score` | `0.15` | Minimum composite score to accept a frame |
| `--no-court-save-manifest` | *(on)* | Disable manifest writing |

## Caching

YouTube lookups (channel resolution and video catalog) are cached indefinitely in `output/.cache/youtube_cache.json` to avoid redundant yt-dlp calls across runs. Each cache entry includes a `cached_date` for reference. Delete individual entries or the entire file to force a refresh.

## Testing

```bash
pytest
```

## Specification

The full project specification is in [PLAN.txt](PLAN.txt) (§1–§16). The court detection feature spec is in [CourtDetectionPlan.md](CourtDetectionPlan.md) (§1–§16). Burst quality filtering and frame extraction modules exist but are not yet wired into the clips pipeline. Note that some filter threshold defaults in the code differ from the spec (tuned for real-world PPA content).

## License

Private / Internal use.
