"""Post-execution checks; pre-materialization fixtures remain historical."""
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREFIX = "p1_v4_partial_high_supplemental80"
MANIFESTS = ROOT / "data/manifests"


def load(name: str) -> dict:
    return json.loads((MANIFESTS / f"{PREFIX}_{name}.json").read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def test_response_freeze_and_replay_hashes():
    audit = load("response_freeze_rescore_audit")
    assert audit["status"] == "PASS"
    assert (audit["effective_logical_responses"], audit["pair_records"], audit["six_vote_groups"]) == (960, 6528, 1088)
    assert audit["production_reference_disagreements"] == audit["raw_response_hash_mismatches"] == 0
    for field, suffix in (
        ("response_freeze_sha256", "response_freeze.json"),
        ("pair_records_sha256", "pair_records.jsonl"),
        ("six_vote_groups_sha256", "six_vote_groups.jsonl"),
    ):
        assert audit[field] == sha(MANIFESTS / f"{PREFIX}_{suffix}")
    assert audit["oracle_access"] == audit["validation_access"] == audit["holdout_access"] == 0


def test_supplemental_oracle_scope_and_historical_decision():
    audit = load("overlay_oracle_metric_audit")
    result = load("overlay_oracle_metric_results")
    assert audit["status"] == "PASS_ORACLE_SCORING"
    assert audit["oracle_scenes_accessed"] == audit["oracle_commitments_verified"] == 80
    assert audit["metric_records"] == 2140
    assert audit["overlay_outputs"] == 320
    assert audit["semantic_api_calls"] == audit["statistical_reruns"] == audit["validation_access"] == audit["holdout_access"] == 0
    assert result["historical_look440_decision_unchanged"] == "STOP_FOR_FUTILITY"
    assert result["status"] == "PASS_SUPPLEMENTAL_CONFIRMATION"
    assert result["validation_authorized"] is False and result["holdout_authorized"] is False
    assert result["metric_dataset_sha256"] == sha(MANIFESTS / f"{PREFIX}_overlay_oracle_metric_dataset.jsonl")
    assert result["overlay_outputs_sha256"] == sha(MANIFESTS / f"{PREFIX}_overlay_outputs.jsonl")


def test_high_continuation_and_fges_robustness_are_distinct():
    result = load("overlay_oracle_metric_results")
    primary_new = result["extension_only"]["Constrained-BOSS"]["variants"]["partial"]
    primary_joint = result["combined_520"]["Constrained-BOSS"]["variants"]["partial"]
    fges_joint = result["combined_520"]["Constrained-FGES"]["variants"]["partial"]
    assert primary_new["High_contributing_scenes"] == 11
    assert primary_joint["High_guardrail"]["contributing_scenes"] == 53 + 11 == 64
    assert primary_joint["High_guardrail"]["pass"] is True
    assert primary_joint["registered_gate_pass"] is True
    assert fges_joint["High_guardrail"]["contributing_scenes"] == 58
    assert fges_joint["High_guardrail"]["pass"] is False
    assert fges_joint["registered_gate_pass"] is False
    assert result["combined_520"]["Constrained-BOSS"]["ambiguous_abstention_diagnostic"]["scenes"] == 120


def test_published_direction_counts_from_scored_dataset():
    path = MANIFESTS / f"{PREFIX}_overlay_oracle_metric_dataset.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2140
    published = [row for row in rows if row["published"]]
    assert all(row["oracle_match"] is True for row in published)
    assert all(row["oracle_relationship"] != "FALSE_ADJACENCY" for row in published)
    counts = {(condition, variant): sum(row["condition"] == condition and row["variant"] == variant for row in published)
              for condition in ("Constrained-BOSS", "Constrained-FGES") for variant in ("full", "partial")}
    assert counts == {("Constrained-BOSS", "full"): 443,
                      ("Constrained-BOSS", "partial"): 252,
                      ("Constrained-FGES", "full"): 379,
                      ("Constrained-FGES", "partial"): 222}
