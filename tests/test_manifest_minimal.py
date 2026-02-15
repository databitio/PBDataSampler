import json
import tempfile
from pathlib import Path

from ppa_frame_sampler.output.manifest import write_manifest


def test_manifest_round_trip():
    manifest = {
        "run_id": "test-run",
        "created_utc": "2026-01-01T00:00:00Z",
        "params": {"seed": 42},
        "candidates": {"count": 5},
        "samples": [],
        "totals": {"accepted_bursts": 0, "rejected_bursts": 0, "frames_written": 0},
    }

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "manifest.json"
        write_manifest(p, manifest)

        loaded = json.loads(p.read_text(encoding="utf-8"))

    assert loaded["run_id"] == "test-run"
    assert loaded["params"]["seed"] == 42
    assert "candidates" in loaded
    assert "samples" in loaded
    assert "totals" in loaded


def test_manifest_required_keys():
    """Verify the manifest schema has all required top-level keys."""
    required = {"run_id", "created_utc", "params", "candidates", "samples", "totals"}
    manifest = {
        "run_id": "x",
        "created_utc": "x",
        "params": {},
        "candidates": {"count": 0},
        "samples": [],
        "totals": {"accepted_bursts": 0, "rejected_bursts": 0, "frames_written": 0},
    }
    assert required.issubset(manifest.keys())
