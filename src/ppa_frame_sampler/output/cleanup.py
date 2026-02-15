from __future__ import annotations

import logging
import shutil
from pathlib import Path

log = logging.getLogger("ppa_frame_sampler")


def cleanup_tmp(tmp_dir: Path) -> None:
    """Remove the temporary directory and all its contents."""
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
        log.info("Cleaned up tmp dir: %s", tmp_dir)
