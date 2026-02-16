from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

BiasMode = Literal["hard_margin", "soft_bias"]
ImageFormat = Literal["jpg", "png"]


@dataclass(frozen=True)
class FilterThresholds:
    min_motion_score: float = 0.015
    max_static_score: float = 0.92
    min_edge_density: float = 0.01
    max_overlay_coverage: float = 0.70
    reject_on_scene_cuts: bool = False
    scene_cut_rate_max: float = 0.50


@dataclass(frozen=True)
class Config:
    # YouTube / catalog
    channel_query: str = "PPA Tour"
    channel_url: Optional[str] = None
    max_age_days: int = 365
    max_videos: int = 200
    min_video_duration_s: int = 120

    # Sampling
    frames_per_sample: int = 20
    total_frames: int = 500
    seed: Optional[int] = None
    bias_mode: BiasMode = "soft_bias"
    intro_margin_s: float = 15.0
    outro_margin_s: float = 15.0
    buffer_seconds: float = 1.0
    max_retries_per_burst: int = 5

    # Output
    out_dir: str = "output/frames"
    tmp_dir: str = "output/tmp"
    image_format: ImageFormat = "jpg"
    make_zip: bool = False
    keep_tmp: bool = False

    # Filter
    thresholds: FilterThresholds = field(default_factory=FilterThresholds)

    # Performance knobs
    analysis_frame_count: int = 5
    analysis_resize_width: int = 320
