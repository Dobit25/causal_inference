"""Ensure the 80-scene authorization cannot silently expand into execution stages."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import freeze_p1_v4_partial_high_supplemental80_materialization as checkpoint
import materialize_p1_v4_partial_high_supplemental80 as runner


def test_exact_scope_and_replay():
    assert checkpoint.preflight(check=True)["status"] == "PASS_OFFLINE_PREFLIGHT"
    assert checkpoint.authorize(check=True)["status"] == "PASS_SCOPED_LIVE_MATERIALIZATION_AUTHORIZATION"
    dry = runner.dry_plan()
    assert dry["scene_count"] == 80 and dry["public_story_artifacts"] == 240
    assert dry["writes_performed"] == dry["semantic_api_calls"] == dry["new_oracle_access"] == 0
    auth = json.loads((ROOT / "data/manifests/p1_v4_partial_high_supplemental80_materialization_live_authorization.json").read_text())
    assert auth["authorized_scene_ids"] == dry["scene_ids_in_execution_order"]
    assert auth["materialization_authorized"] is True
    assert all(auth[key] is False for key in ("statistical_execution_authorized", "semantic_api_authorized", "oracle_scoring_authorized", "validation_authorized", "holdout_authorized", "automatic_execution_authorized"))
    assert not (ROOT / dry["generated_root"]).exists()
    assert not (ROOT / dry["public_root"]).exists()


def test_unpinned_authorization_is_rejected_before_writes(tmp_path):
    fake=tmp_path / "fake_live_authorization.json"
    fake.write_text('{"status":"PASS_SCOPED_LIVE_MATERIALIZATION_AUTHORIZATION"}',encoding="utf-8")
    with pytest.raises(RuntimeError, match="exact scoped authorization required"):
        runner.execute(fake)
