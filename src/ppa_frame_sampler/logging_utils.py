from __future__ import annotations

import logging
import sys


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure and return the application logger."""
    logger = logging.getLogger("ppa_frame_sampler")
    if logger.handlers:
        return logger

    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    return logger
