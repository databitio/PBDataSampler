from __future__ import annotations

import argparse
import sys

from ppa_frame_sampler.config import Config, FilterThresholds
from ppa_frame_sampler.logging_utils import setup_logging
from ppa_frame_sampler.media.tools import ensure_tool
from ppa_frame_sampler.pipeline.collector import run_collection


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ppa-frame-sampler",
        description="Sample consecutive frames from recent PPA Tour YouTube videos for CVAT labeling.",
    )

    # Channel
    p.add_argument("--channel-query", default="PPA Tour")
    p.add_argument("--channel-url", default=None)

    # Video eligibility
    p.add_argument("--min-age-days", type=int, default=0)
    p.add_argument("--max-age-days", type=int, default=365)
    p.add_argument("--max-videos", type=int, default=200)
    p.add_argument("--min-video-duration-s", type=int, default=120)
    p.add_argument(
        "--match-type",
        choices=["singles", "doubles", "both"],
        default="both",
    )

    # Sampling
    p.add_argument("--frames-per-sample", type=int, default=20)
    p.add_argument("--total-frames", type=int, default=500)
    p.add_argument("--seed", type=int, default=None)

    # Bias
    p.add_argument("--bias-mode", choices=["hard_margin", "soft_bias"], default="soft_bias")
    p.add_argument("--intro-margin-s", type=float, default=15.0)
    p.add_argument("--outro-margin-s", type=float, default=15.0)
    p.add_argument("--buffer-seconds", type=float, default=1.0)
    p.add_argument("--max-retries-per-burst", type=int, default=5)

    # Output
    p.add_argument("--out", dest="out_dir", default="output/frames")
    p.add_argument("--tmp", dest="tmp_dir", default="output/tmp")
    p.add_argument("--format", dest="image_format", choices=["jpg", "png"], default="jpg")
    p.add_argument("--zip", dest="make_zip", action="store_true")
    p.add_argument("--keep-tmp", dest="keep_tmp", action="store_true")

    # Filter thresholds
    p.add_argument("--min-motion-score", type=float, default=0.015)
    p.add_argument("--max-static-score", type=float, default=0.92)
    p.add_argument("--min-edge-density", type=float, default=0.01)
    p.add_argument("--max-overlay-coverage", type=float, default=0.70)
    p.add_argument("--reject-on-scene-cuts", action="store_true")
    p.add_argument("--scene-cut-rate-max", type=float, default=0.50)

    return p


def main() -> None:
    args = build_parser().parse_args()
    log = setup_logging()

    # Validate
    if args.frames_per_sample <= 0 or args.total_frames <= 0:
        print("frames-per-sample and total-frames must be > 0", file=sys.stderr)
        sys.exit(2)

    # Fail-fast tool checks
    for tool in ("yt-dlp", "ffmpeg", "ffprobe"):
        try:
            ensure_tool(tool)
        except RuntimeError as exc:
            log.error(str(exc))
            sys.exit(1)

    thresholds = FilterThresholds(
        min_motion_score=args.min_motion_score,
        max_static_score=args.max_static_score,
        min_edge_density=args.min_edge_density,
        max_overlay_coverage=args.max_overlay_coverage,
        reject_on_scene_cuts=args.reject_on_scene_cuts,
        scene_cut_rate_max=args.scene_cut_rate_max,
    )

    cfg = Config(
        channel_query=args.channel_query,
        channel_url=args.channel_url,
        min_age_days=args.min_age_days,
        max_age_days=args.max_age_days,
        max_videos=args.max_videos,
        min_video_duration_s=args.min_video_duration_s,
        match_type=args.match_type,
        frames_per_sample=args.frames_per_sample,
        total_frames=args.total_frames,
        seed=args.seed,
        bias_mode=args.bias_mode,
        intro_margin_s=args.intro_margin_s,
        outro_margin_s=args.outro_margin_s,
        buffer_seconds=args.buffer_seconds,
        max_retries_per_burst=args.max_retries_per_burst,
        out_dir=args.out_dir,
        tmp_dir=args.tmp_dir,
        image_format=args.image_format,
        make_zip=args.make_zip,
        keep_tmp=args.keep_tmp,
        thresholds=thresholds,
    )

    run_collection(cfg)


if __name__ == "__main__":
    main()
