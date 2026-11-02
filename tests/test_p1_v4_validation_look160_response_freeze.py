import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_validation_look160_response_freeze_audit() -> None:
    audit = json.loads((ROOT / "data/manifests/p1_v4_validation_look160_response_freeze_rescore_audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "PASS"
    assert audit["effective_logical_responses"] == 2640
    assert audit["raw_provider_errors"] == audit["overlay_replacements"] == 28
    assert audit["unresolved_provider_errors"] == 0
    assert audit["pair_records"] == 18252
    assert audit["six_vote_groups"] == 3042
    assert audit["production_reference_disagreements"] == 0
    assert audit["response_hash_mismatches"] == 0
    assert audit["oracle_access"] == 0
    assert audit["holdout_access"] == 0
    assert audit["semantic_api_calls"] == 0
    assert audit["precision_metrics"] == 0
    assert audit["closure"] == 0
