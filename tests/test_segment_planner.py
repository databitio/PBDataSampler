from ppa_frame_sampler.sampling.segment_planner import plan_segment_len_s


def test_minimum_length():
    """Segment should be at least 2 seconds."""
    length = plan_segment_len_s(1, 30.0, 0.5)
    assert length >= 2.0


def test_scales_with_frame_count():
    short = plan_segment_len_s(10, 30.0, 1.0)
    long = plan_segment_len_s(60, 30.0, 1.0)
    assert long > short


def test_includes_buffer():
    no_buf = plan_segment_len_s(30, 30.0, 0.0)
    with_buf = plan_segment_len_s(30, 30.0, 2.0)
    assert with_buf > no_buf
