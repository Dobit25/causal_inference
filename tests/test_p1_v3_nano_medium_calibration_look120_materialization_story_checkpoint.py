from __future__ import annotations

from pathlib import Path

from scripts.checkpoint_p1_v3_nano_medium_calibration_look120_materialization_story import run


def test_exact_prefix_is_verified_but_live_is_blocked() -> None:
    audit = run()
    assert audit["exact_scene_count"] == 120
    assert audit["status"] == "BLOCKED_CALIBRATION_STORY_PROTOCOL"
    assert audit["scene_materialization_writes"] == 0
    assert audit["semantic_api_calls"] == 0
    assert audit["oracle_access"] is False
    assert audit["holdout_access"] is False


def test_calibration_stories_are_not_silently_reused() -> None:
    audit = run()
    inputs = audit["inputs"]
    assert inputs["story_protocol_ready"] is False
    assert "story_protocol_ready" in inputs
