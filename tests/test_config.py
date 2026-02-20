from ppa_frame_sampler.config import Config, FilterThresholds


def test_default_config():
    cfg = Config()
    assert cfg.total_frames == 500
    assert cfg.frames_per_sample == 20
    assert cfg.bias_mode == "soft_bias"
    assert cfg.image_format == "jpg"


def test_filter_thresholds_defaults():
    t = FilterThresholds()
    assert t.min_motion_score == 0.015
    assert t.max_static_score == 0.92
    assert t.min_edge_density == 0.01
    assert t.max_overlay_coverage == 0.70
    assert t.reject_on_scene_cuts is False
