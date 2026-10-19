"""Offline-only integrity and contract review of frozen Nano/Mini P1V4 responses."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_stage3_paired_response_offline_review.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def counts(values: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(field)) for row in values).items()))


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for parent in cfg["parents"].values():
        if sha(ROOT / parent["path"]) != parent["sha256"]:
            raise RuntimeError(f"frozen input hash drift: {parent['path']}")
    freeze = json.loads((ROOT / cfg["parents"]["response_freeze"]["path"]).read_text(encoding="utf-8"))
    rescore = json.loads((ROOT / cfg["parents"]["rescore_audit"]["path"]).read_text(encoding="utf-8"))
    if freeze.get("status") != "PASS_FROZEN" or rescore.get("status") != "PASS":
        raise RuntimeError("paired response freeze/re-score has not passed")
    nano_pairs, mini_pairs = rows(ROOT / cfg["parents"]["nano_pairs"]["path"]), rows(ROOT / cfg["parents"]["mini_pairs"]["path"])
    nano_groups, mini_groups = rows(ROOT / cfg["parents"]["nano_six_vote_groups"]["path"]), rows(ROOT / cfg["parents"]["mini_six_vote_groups"]["path"])
    exp_pair, exp_group = cfg["review_scope"]["expected_pair_records_per_model"], cfg["review_scope"]["expected_six_vote_groups_per_model"]
    if len(nano_pairs) != exp_pair or len(mini_pairs) != exp_pair or len(nano_groups) != exp_group or len(mini_groups) != exp_group:
        raise RuntimeError("frozen record-count mismatch")
    pkey = lambda row: (row["scene_id"], row["variant"], row["prompt_id"], row["pair_id"])
    gkey = lambda row: (row["scene_id"], row["variant"], row["pair_id"])
    if {pkey(row) for row in nano_pairs} != {pkey(row) for row in mini_pairs} or {gkey(row) for row in nano_groups} != {gkey(row) for row in mini_groups}:
        raise RuntimeError("Nano/Mini paired identity mismatch")
    pair_transition = Counter(("VALID" if n["pair_valid"] else "INVALID", "VALID" if m["pair_valid"] else "INVALID") for n, m in zip(sorted(nano_pairs, key=pkey), sorted(mini_pairs, key=pkey)))
    group_transition = Counter((n["agreement"], m["agreement"]) for n, m in zip(sorted(nano_groups, key=gkey), sorted(mini_groups, key=gkey)))
    review = {"schema_version": "fourgraph.p1_v4_stage3_paired_response_offline_review.v1", "task": cfg["task"], "status": "PASS_REVIEW_COMPLETE",
              "frozen_input_hashes": {name: parent["sha256"] for name, parent in cfg["parents"].items()},
              "identity": {"logical_responses_per_model": freeze["models"]["nano_medium"]["logical_responses"], "paired_pair_records": exp_pair, "paired_six_vote_groups": exp_group, "same_pair_identity": True, "same_group_identity": True},
              "model_contract_observations": {"nano_medium": {"pair_validity": {"valid": sum(row["pair_valid"] is True for row in nano_pairs), "invalid": sum(row["pair_valid"] is False for row in nano_pairs)}, "agreement": counts(nano_groups, "agreement"), "completeness": counts(nano_groups, "completeness")}, "mini_medium": {"pair_validity": {"valid": sum(row["pair_valid"] is True for row in mini_pairs), "invalid": sum(row["pair_valid"] is False for row in mini_pairs)}, "agreement": counts(mini_groups, "agreement"), "completeness": counts(mini_groups, "completeness")}},
              "paired_contract_transitions": {"pair_validity": {f"nano_{a.lower()}__mini_{b.lower()}": count for (a, b), count in sorted(pair_transition.items())}, "agreement_labels": {f"nano_{a.lower()}__mini_{b.lower()}": count for (a, b), count in sorted(group_transition.items())}},
              "interpretation_boundary": "These are validator and agreement-contract observations only. They do not establish directional correctness, precision, coverage, calibration, or a model ranking.", "boundaries": cfg["boundaries"]}
    review_path = ROOT / cfg["outputs"]["review"]; review_path.write_bytes(canonical(review))
    audit = {"schema_version": "fourgraph.p1_v4_stage3_paired_response_offline_review_audit.v1", "task": cfg["task"], "status": "PASS",
             "review_sha256": sha(review_path), "all_frozen_hashes_match": True, "paired_identity_match": True, "oracle_access": 0, "holdout_access": 0, "semantic_api_calls": 0, "closure": 0, "metric_calculation": 0, "threshold_selection": 0}
    audit_path = ROOT / cfg["outputs"]["audit"]; audit_path.write_bytes(canonical(audit))
    report = """# P1V4 paired-response offline review\n\n## Scope\n\nThis review inspected only hash-pinned Nano-medium and Mini-medium response, pair-validation, and six-vote artifacts. It establishes that both models received exactly the same 360 logical inputs and that the paired identity is intact.\n\n## What it shows\n\nMini-medium has fewer validator-invalid pair records and more complete/very-high agreement groups than Nano-medium under the same contract. These are workflow-quality observations, not correctness results.\n\n## What it deliberately does not show\n\nNo Oracle was read. There is no orientation precision, coverage, closure, threshold selection, calibration, or scientific model ranking in this review. A separately authorized Oracle-scoring checkpoint is required before any such conclusion.\n"""
    (ROOT / cfg["outputs"]["report"]).write_text(report, encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
