from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def write_manifest(path: Path, manifest: Dict[str, Any]) -> None:
    """Serialise *manifest* as pretty-printed JSON to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
