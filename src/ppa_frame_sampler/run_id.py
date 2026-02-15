from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def generate_run_id(seed: Optional[int] = None) -> str:
    """Generate a unique run identifier based on current UTC time and optional seed."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    if seed is not None:
        return f"{ts}_seed{seed}"
    return ts
