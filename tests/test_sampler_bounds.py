import random

import pytest

from ppa_frame_sampler.sampling.timestamp_sampler import sample_timestamp


class TestHardMargin:
    def test_stays_within_bounds(self):
        rng = random.Random(42)
        duration = 600.0
        seg = 3.0
        for _ in range(200):
            s = sample_timestamp(duration, seg, 15.0, 15.0, "hard_margin", rng=rng)
            assert 15.0 <= s <= (duration - 15.0 - seg)

    def test_fallback_when_margins_exceed_duration(self):
        rng = random.Random(42)
        s = sample_timestamp(10.0, 3.0, 100.0, 100.0, "hard_margin", rng=rng)
        assert 0.0 <= s <= 7.0


class TestSoftBias:
    def test_stays_within_bounds(self):
        rng = random.Random(42)
        duration = 600.0
        seg = 3.0
        for _ in range(200):
            s = sample_timestamp(duration, seg, 15.0, 15.0, "soft_bias", rng=rng)
            assert 15.0 <= s <= (duration - 15.0 - seg)

    def test_biased_toward_middle(self):
        """Soft bias should produce samples closer to the middle on average."""
        rng = random.Random(42)
        duration = 600.0
        seg = 3.0
        lo = 15.0
        hi = duration - 15.0 - seg
        mid = (lo + hi) / 2.0

        samples = [sample_timestamp(duration, seg, 15.0, 15.0, "soft_bias", rng=rng) for _ in range(500)]
        avg = sum(samples) / len(samples)
        # Average should be reasonably close to midpoint
        assert abs(avg - mid) < (hi - lo) * 0.1
