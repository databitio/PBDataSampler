Feature Goal

Add a new mode that scans eligible PPA videos and extracts one representative frame per video where the pickleball court is visible, then saves all selected frames into a single directory:

output/court_detections/

This dataset will be used to train a court keypoint model (14 court keypoints).

Recommended Design Direction

Instead of forcing this into the current “clip burst” flow, add a separate sampling mode/pipeline inside the same CLI app:

Current mode (existing): burst clip sampling for CVAT

New mode: one-frame-per-video court frame extraction

That keeps your current workflow stable and avoids mixing very different logic paths.

High-Level Implementation Plan
1) Add a New CLI Mode

Add a new mode flag so the app can run either pipeline.

Option A (cleanest)

Use a top-level mode flag:

--mode clips (default, existing behavior)

--mode court-frames (new behavior)

Option B (simpler incremental)

Add a boolean flag:

--court-detection-frames

I’d recommend Option A because you’ll likely add more dataset-generation modes later.

2) Add Court-Frame Specific CLI Options

These should be separate from the burst/clip options so the intent is clear.

Suggested new flags

--court-out-dir (default: output/court_detections)

--court-max-videos (default: maybe 500 or reuse --max-videos)

--court-frame-format (jpg/png, default jpg)

--court-sample-attempts-per-video (default 5 or 8)

--court-intro-margin-s (default 20)

--court-outro-margin-s (default 20)

--court-min-detection-confidence (future-facing placeholder if you later use a model)

--court-save-manifest (on by default)

Optional but very useful:

--court-require-scorebug-absent (avoid scoreboard overlays if possible)

--court-min-court-coverage (heuristic threshold)

--court-debug-rejections (save rejected candidates for tuning)

3) Keep Video Eligibility Logic Reused

Reuse your existing pipeline components for:

Channel resolution

Video cataloging

Age filtering (--min-age-days, --max-age-days)

Duration filtering

Match type filtering (singles, doubles, both)

Caching

This is ideal because the “which videos do we consider?” logic is already solved.

4) New Court Frame Selection Pipeline (Per Video)

For each eligible video, the new flow should look like this:

Step A — Generate candidate timestamps

Try several timestamps per video (not just one), biased away from intros/outros.

Use either:

current hard_margin approach, or

current soft_bias Beta distribution

This reuses your existing timestamp sampling strategy.

Why multiple attempts?
Some frames will be:

replay graphics

player closeups

crowd shots

interviews

transitions

non-court angles

So you want a small retry loop per video.

Step B — Download a tiny clip or a single-frame window

You currently download short MP4 clips around sampled timestamps. For this feature, you can do either:

Preferred (simple + robust)

Download a very short clip (e.g., 1–2 seconds), then score/select the best frame from it.

Benefits:

Reuses your yt-dlp + ffmpeg machinery

Lets you avoid exact-timestamp misses

Gives fallback if the exact frame is bad

Alternative (faster but brittle)

Extract one frame directly at the timestamp with ffmpeg.

I’d still recommend the short clip approach first.

Step C — Score candidate frames for “court present”

This is the core new logic.

Since your court keypoint model doesn’t exist yet, use heuristics to estimate whether the court is visible.

Practical heuristic stack (good starting point)

Score each frame using a weighted combination of:

Line density / line structure

Use edge detection + Hough line transform

Court frames usually contain many straight lines

Strong horizontal/vertical/near-parallel line groups are a good signal

Court-color area

PPA courts often occupy a large region of consistent color (blue/green/etc.)

Use HSV clustering or dominant-color segmentation

Estimate whether a large contiguous region exists

Perspective geometry cues

Court frames often have converging line sets and rectangular structure

Even a simple “many long lines at 2–4 dominant angles” helps

Overlay penalty

Scorebug/graphics in corners can hurt keypoint labeling quality

Penalize large static high-contrast blocks near corners/edges

Motion/stability preference (optional)

If using a tiny clip, prefer a frame without heavy motion blur

Use Laplacian variance (blur score)

Scene-cut rejection

Reuse your scene-cut heuristics to avoid replay transitions

Output of scoring

For each candidate frame:

court_presence_score (0–1)

reason_codes (e.g., high_line_density, low_court_color, overlay_penalty)

accepted/rejected

Step D — Pick the best accepted frame for the video

If multiple attempts succeed:

keep the highest-scoring frame only

If all attempts fail:

mark the video as no_court_frame_found

log why (low score, replay-heavy, etc.)

This guarantees your “one frame per video” target while preserving quality.

5) Save Frames to a Single court_detections Directory

Output structure should be flat (as requested), but include a manifest.

Recommended structure
output/court_detections/
├── <video_id>_<timestamp_ms>.jpg
├── <video_id>_<timestamp_ms>.jpg
├── ...
└── court_detection_manifest.json
Filename format

Include enough metadata to trace back:

video_id

timestamp_ms

maybe an abbreviated score (optional)

Example:

abc123XYZ_1842300ms.jpg
6) Add a Dedicated Manifest for This Mode

Create court_detection_manifest.json so you can audit and retrain later.

Include:

run metadata

timestamp

seed

CLI args

app version

video eligibility stats

total cataloged

eligible

attempted

success count

fail count

per-video record

video_id

title

upload_date

duration_s

match_type

attempted_timestamps

selected_timestamp_ms

output_file

court_presence_score

status (success, no_valid_frame, download_error, etc.)

rejection_reasons summary

This will be incredibly useful when you tune heuristics later.

7) Keep the Existing Clip Sampler Untouched

Minimize risk by isolating this feature:

Create a new module, e.g.:

court_frame_sampler.py

court_frame_scoring.py

court_manifest.py

The existing burst clip path should remain unchanged.

This makes it easier to test and avoids regressions in your CVAT clip workflow.

8) Reuse Existing Components Where Possible

You already have several pieces that can be reused directly:

YouTube channel resolution

Video catalog caching

Eligibility filters

Timestamp bias logic

yt-dlp + ffmpeg download wrappers

Frame-quality filtering utilities (some may transfer)

Retry logic patterns

Manifest writing utilities

The only truly new part is:

court presence scoring + one-frame selection

9) Suggested Heuristic MVP (Phase 1)

Keep the first version simple and tunable.

MVP scoring approach

For each sampled timestamp attempt:

Download 1–2s clip

Extract 3–5 evenly spaced frames

For each frame, compute:

edge density

Hough line count / average line length

blur score (Laplacian variance)

corner-overlay penalty (simple static block heuristic)

Normalize scores

Pick best frame in clip

Accept if score > threshold

Across all attempts, pick best accepted frame for the video

This will get you a usable dataset quickly.

10) Phase 2 Enhancements (After MVP Works)

Once you collect some labeled court frames, you can improve quality substantially:

A) Train a lightweight court-presence classifier

Even a simple binary classifier (“court visible” vs “not visible”) can replace weak heuristics.

B) Add court-line confidence heuristic

Use line intersection structure to prefer frames where all 14 keypoints are likely visible.

C) Diversity controls

Avoid collecting near-identical broadcasts/angles only:

cap per tournament/event

enforce upload-date spread

include singles + doubles mix

D) Overlay-aware cropping preview (optional)

If scorebug covers corners, flag frames for manual review or crop margins if your keypoint labeling plan allows it.

11) Testing Plan

Add tests specifically for this mode.

Unit tests

Timestamp candidate generation respects margins

Court scorer returns deterministic scores on fixture images

Manifest schema validation

Filename generation

“Best frame selection” logic

Integration tests

Mock video catalog → run court mode → outputs one frame/video

Failure handling (download fail / no valid frame)

Reproducibility with --seed

Regression tests

Existing clips mode still works unchanged

12) README Updates (What to Add)

You’ll want to extend README with a new section:

New section

Court Detection Dataset Mode

Purpose: one frame per video for court keypoint training

Output folder: output/court_detections

Example command:

ppa-frame-sampler --mode court-frames --max-age-days 365 --match-type both
Add to CLI options table

New category:

Court Dataset Mode

Add to “How It Works”

Include a second flow for court-frame extraction.

13) Implementation Sequence (Practical)

Here’s the order I’d actually build it in:

Add CLI mode switch

Reuse catalog + eligibility pipeline

Implement per-video candidate timestamp generation

Download tiny clip + extract candidate frames

Implement simple court scoring heuristics

Select one best frame/video and save

Write court manifest

Add tests

Tune thresholds on real PPA samples

Update README + PLAN.txt

14) Key Design Decisions to Lock In Early

These choices will prevent churn later:

1) One frame exactly, or allow skip?

Recommend:

At most one per video

Skip if no acceptable frame found

2) Flat folder vs nested

You asked for a single flat folder — good choice for training ingest.

3) Quality over quantity vs strict one-per-video

I’d prioritize quality:

Better to skip bad videos than include garbage frames.

4) Heuristic thresholds configurable

Do not hardcode. Make them CLI-configurable or config-file-backed.

15) Example CLI UX (Proposed)
# Generate one court-visible frame per eligible video
ppa-frame-sampler --mode court-frames

# Last 180 days only, doubles only
ppa-frame-sampler --mode court-frames --match-type doubles --max-age-days 180

# More aggressive retries per video
ppa-frame-sampler --mode court-frames --court-sample-attempts-per-video 10

# Custom output folder
ppa-frame-sampler --mode court-frames --court-out-dir output/court_detections
16) Optional Future-Proofing: Separate Subcommand (Best long-term)

If you expect more dataset generation modes, consider migrating to subcommands later:

ppa-frame-sampler clips ...

ppa-frame-sampler court-frames ...

Not necessary now, but worth keeping in mind.