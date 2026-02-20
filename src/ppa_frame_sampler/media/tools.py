from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Any

log = logging.getLogger("ppa_frame_sampler")


def ensure_tool(name: str) -> str:
    """Return the full path to *name* or raise RuntimeError."""
    path = shutil.which(name)
    if not path:
        raise RuntimeError(
            f"Required tool not found on PATH: {name}. "
            f"Please install it and make sure it is accessible."
        )
    return path


def run_cmd(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Run a command, log it, and return the completed process."""
    log.debug("Running: %s", " ".join(cmd))
    return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)


def run_cmd_json(cmd: list[str], timeout: int = 120) -> dict[str, Any]:
    """Run a command and parse its stdout as JSON."""
    proc = run_cmd(cmd, timeout=timeout)
    return json.loads(proc.stdout)
