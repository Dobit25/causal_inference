"""Seal or byte-check the completed T14 logical holdout execution."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402


def obj(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def artifact(path: Path) -> dict[str, Any]:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_hex(path.read_bytes()), "bytes": path.stat().st_size}


def build() -> bytes:
    t13_path = ROOT / "data/manifests/t13_holdout_execution.json"
    t13_audit_path = ROOT / "data/manifests/t13_holdout_execution_audit.json"
    t13, t13_audit = obj(t13_path), obj(t13_audit_path)
    if sha256_hex(t13_path.read_bytes()) != t13_audit["execution_manifest_sha256"]:
        raise RuntimeError("T13 manifest drift")
    root = ROOT / t13["execution"]["outputs"]["t14_root"]
    seal_path = root / "non_oracle_seal.json"
    metric_path = ROOT / t13["execution"]["outputs"]["t14_graph_metrics"]
    metric_audit_path = root / "graph_metrics_audit.json"
    scores_path = ROOT / t13["execution"]["outputs"]["t14_primary_scores"]
    reasoner_audit_path = root / "reasoner_audit.json"
    attempts_path = ROOT / t13["execution"]["outputs"]["t14_attempt_log"]
    cache_path = ROOT / t13["execution"]["outputs"]["t14_cache"]
    failure_path = root / "graphs/failures.jsonl"
    reasoner_failure_path = root / "reasoner_failures.jsonl"
    paths = [seal_path, metric_path, metric_audit_path, scores_path, reasoner_audit_path, attempts_path, cache_path, failure_path, reasoner_failure_path]
    if any(not path.is_file() for path in paths):
        raise FileNotFoundError("T14 final audit is missing an execution artifact")
    seal, metric_audit, reasoner_audit = obj(seal_path), obj(metric_audit_path), obj(reasoner_audit_path)
    metrics, scores, attempts = rows(metric_path), rows(scores_path), rows(attempts_path)
    graph_failures, reasoner_failures = rows(failure_path), rows(reasoner_failure_path)
    if not seal["sealed"] or seal["oracle_accessed"] or not metric_audit["complete"] or not reasoner_audit["complete"]:
        raise RuntimeError("A T14 stage is not terminal")
    if len(metrics) != 125 or len(scores) != 500:
        raise RuntimeError("T14 scheduled record count mismatch")
    primary_ids = set(t13["cohorts"]["primary_downstream"]["holdout_scene_ids"])
    if {item["scene_id"] for item in scores} != primary_ids:
        raise RuntimeError("T14 scores include a non-primary scene")
    expected = {(scene, task, condition) for scene in primary_ids for task in t13["cohorts"]["primary_downstream"]["tasks"] for condition in t13["graph_conditions"]}
    if {(item["scene_id"], item["task_id"], item["graph_condition"]) for item in scores} != expected:
        raise RuntimeError("T14 primary schedule is incomplete")
    if (root / "graphs/G_ORACLE.jsonl").exists():
        raise RuntimeError("Oracle graph edges were persisted")
    phases = Counter(item["phase"] for item in attempts)
    status_counts = Counter(item["status"] for item in scores)
    audit = {
        "schema_version": "fourgraph.t14_holdout_execution_audit.v1",
        "logical_run_id": t13["execution"]["logical_run_id"],
        "t13": {"manifest_sha256": sha256_hex(t13_path.read_bytes()), "audit_sha256": sha256_hex(t13_audit_path.read_bytes()), "authorization_valid": True},
        "scope": {"graph_scenes_opened": 25, "primary_scenes_opened": 20, "supplementary_scenes_opened_for_graphs_only": 5, "supplementary_reasoner_records": 0, "holdout_accessed": True, "opened_as_one_logical_resumable_run": True},
        "graph_build": {"scheduled_non_oracle": 100, "successful_non_oracle": sum(item["successful_records"] for item in seal["condition_files"].values()), "terminal_failures": len(graph_failures), "failures": graph_failures, "semantic_api_attempts": phases["G_LLM"] + phases["G_HYBRID"], "llm_attempts": phases["G_LLM"], "hybrid_attempts": phases["G_HYBRID"], "fallback_graphs": 0},
        "graph_metrics": {"scheduled": 125, "available": metric_audit["available_records"], "unavailable": metric_audit["unavailable_records"], "oracle_scenes_loaded": metric_audit["oracle_scene_count"], "oracle_edges_persisted": False},
        "downstream": {"scheduled": 500, "answered": status_counts["answered"], "graph_failure_records": status_counts["graph_failure"], "reasoner_failure_records": status_counts["reasoner_failure"], "unique_canonical_inputs": reasoner_audit["unique_canonical_inputs"], "canonical_reused_records": reasoner_audit["canonical_reused_records"], "reasoner_api_attempts": phases["REASONER"], "validation_retries": reasoner_audit["validation_retries"], "terminal_identity_failures": reasoner_failures},
        "usage": {"reasoner": reasoner_audit["usage"], "builder_input_tokens": sum(int(item.get("input_tokens") or 0) for item in attempts if item["phase"] != "REASONER"), "builder_output_tokens": sum(int(item.get("output_tokens") or 0) for item in attempts if item["phase"] != "REASONER"), "total_api_attempts": len(attempts)},
        "implementation": {path.relative_to(ROOT).as_posix(): sha256_hex(path.read_bytes()) for path in (ROOT / "scripts/run_t14_graphs.py", ROOT / "scripts/evaluate_t14_graph_metrics.py", ROOT / "scripts/run_t14_reasoner.py", ROOT / "scripts/audit_t14_execution.py")},
        "artifacts": {path.name if path.parent == root else path.relative_to(root).as_posix(): artifact(path) for path in paths},
        "evidence_boundary": {"non_oracle_graphs_sealed_before_oracle": True, "oracle_edges_persisted": False, "builders_retuned": False, "reasoner_retuned": False, "supplementary_pooled": False, "aggregate_ranking_computed": False, "bootstrap_or_bh_performed": False},
        "verdict": {"t14_complete": True, "all_scheduled_identities_terminal": True, "replay_ready": True, "t15_authorized": True, "t15_started": False},
    }
    return canonical_json_bytes(audit, newline=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = build()
    raw = ROOT / "results/raw/t14_holdout/audit.json"
    versioned = ROOT / "data/manifests/t14_holdout_execution_audit.json"
    if args.check:
        if raw.read_bytes() != payload or versioned.read_bytes() != payload:
            raise RuntimeError("T14 audit replay differs byte-for-byte")
    else:
        raw.write_bytes(payload)
        versioned.write_bytes(payload)
    audit = json.loads(payload)
    print(json.dumps(audit["verdict"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
