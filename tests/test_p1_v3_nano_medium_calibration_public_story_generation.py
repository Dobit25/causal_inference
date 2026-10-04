from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data/manifests/p1_v3_nano_medium_calibration_public_story_generation_audit.json"


def test_calibration_public_story_audit_passes() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["status"] == "PASS_CALIBRATION_PUBLIC_STORIES_FROZEN"
    assert audit["scene_count"] == 120
    assert audit["story_count"] == 360
    assert audit["variants"] == {"full": 120, "partial": 120, "ambiguous": 120}
    assert audit["replay"] == "PASS_BYTE_FOR_BYTE"
    assert audit["leakage_audit"] == "PASS"
    assert audit["semantic_api_calls"] == 0
    assert audit["holdout_access"] == 0


def test_public_story_files_are_model_view_only() -> None:
    root = ROOT / "data/generated/p1_v3_nano_medium_calibration_look120_stories"
    paths = sorted(root.glob("P1V3SC*/story_*.json"))
    assert len(paths) == 360
    sample = json.loads(paths[0].read_text(encoding="utf-8"))
    assert set(sample["builder_input"]) == {"story"}
    assert isinstance(sample["builder_input"]["story"], str)
