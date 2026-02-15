from __future__ import annotations

import zipfile
from pathlib import Path


def zip_frames(frames_dir: Path, output_zip: Path) -> None:
    """Create a ZIP archive of all files in *frames_dir*."""
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(frames_dir.iterdir()):
            if file.is_file():
                zf.write(file, file.name)
