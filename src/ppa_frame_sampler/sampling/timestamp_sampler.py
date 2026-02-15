from __future__ import annotations

import random
from typing import Literal

BiasMode = Literal["hard_margin", "soft_bias"]


def sample_timestamp(
    duration_s: float,
    segment_len_s: float,
    intro_margin_s: float,
    outro_margin_s: float,
    bias_mode: BiasMode,
    rng: random.Random | None = None,
) -> float:
    """Return a start timestamp (seconds) for a segment of *segment_len_s*.

    The segment ``[start, start + segment_len_s]`` is guaranteed to fit
    within the video.  Intro/outro avoidance is applied according to
    *bias_mode*:

    * ``hard_margin`` — uniform draw from
      ``[intro_margin_s, duration_s - outro_margin_s - segment_len_s]``.
    * ``soft_bias`` — Beta(2.5, 2.5) mapped to the legal range, giving
      reduced probability near both ends.
    """
    if rng is None:
        rng = random.Random()  # uses global state seeded externally

    # Legal bounds
    lo = intro_margin_s
    hi = duration_s - outro_margin_s - segment_len_s

    # Fallback: if margins eat the whole video, relax them
    if hi <= lo:
        lo = 0.0
        hi = max(0.0, duration_s - segment_len_s)

    if hi <= lo:
        return 0.0

    if bias_mode == "hard_margin":
        return rng.uniform(lo, hi)

    # soft_bias: Beta(2.5, 2.5) — bell-shaped, peaks at midpoint
    t = rng.betavariate(2.5, 2.5)  # ∈ [0, 1]
    return lo + t * (hi - lo)
