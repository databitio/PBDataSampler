from __future__ import annotations


def plan_segment_len_s(
    frames_per_sample: int,
    fps_guess: float,
    buffer_seconds: float,
) -> float:
    """Compute the clip length (seconds) to download.

    Enough to decode *frames_per_sample* frames at *fps_guess*, plus a
    *buffer_seconds* margin for seek inaccuracy.
    """
    needed = frames_per_sample / max(fps_guess, 1.0)
    return max(2.0, needed + buffer_seconds)
