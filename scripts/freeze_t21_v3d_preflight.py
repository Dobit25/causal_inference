"""Freeze the T21 v3-D live-validation configuration after offline preflight."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/t21_v3d_validation.yaml"
RUNNER = ROOT / "scripts/run_t21_v3d_validation.py"
OUTPUT = ROOT / "data/manifests/t21_v3d_preflight_freeze.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    cohort = json.loads((ROOT / config["scope"]["cohort"]).read_text(encoding="utf-8"))
    parent = json.loads((ROOT / "data/manifests/t21_v3c_validation_generation_audit.json").read_text(encoding="utf-8"))
    if cohort["study_ids"] != [f"P1V{i:03d}" for i in range(20)]:
        raise RuntimeError("V3-D preflight cohort drift")
    if not parent["verdict"]["t21_v3d_authorized"]:
        raise RuntimeError("V3-C did not authorize V3-D")
    if config["execution"]["semantic_preference_calls"] != 60 or config["edge_selective"]["candidates"] != 20:
        raise RuntimeError("V3-D preflight cardinality drift")
    if config["evidence_boundary"]["final_holdout_access_authorized"]:
        raise RuntimeError("V3-D cannot authorize final holdout access")
    record = {
        "schema_version": "fourgraph.t21_v3d_preflight_freeze.v1",
        "task": "T21 Amendment v3-D",
        "config_path": CONFIG.relative_to(ROOT).as_posix(),
        "config_sha256": digest(CONFIG),
        "runner_path": RUNNER.relative_to(ROOT).as_posix(),
        "runner_sha256": digest(RUNNER),
        "parent_v3c_audit_sha256": digest(ROOT / "data/manifests/t21_v3c_validation_generation_audit.json"),
        "cohort_sha256": digest(ROOT / config["scope"]["cohort"]),
        "frozen_execution": {
            "validation_scenes": 20,
            "logical_semantic_calls": 60,
            "maximum_api_attempts": config["execution"]["maximum_new_api_attempts"],
            "threshold_candidates": 20,
            "model_snapshot": config["semantic_backend"]["model_snapshot"],
            "prompt": config["semantic_backend"]["preference_prompt"],
            "gate": {
                "graph_validity": config["edge_selective"]["graph_validity_required"],
                "precision": config["edge_selective"]["orientation_precision_minimum"],
                "answered_edges": config["edge_selective"]["minimum_answered_edges"],
                "coverage": config["edge_selective"]["minimum_orientation_coverage"],
            },
        },
        "offline_preflight": {
            "boss_scenes": 20,
            "planned_new_logical_calls": 60,
            "api_calls": 0,
            "existing_development_accessed": False,
            "final_holdout_accessed": False,
        },
        "verdict": {
            "preflight_complete": True,
            "live_validation_execution_authorized": True,
            "automatic_final_holdout_continuation": False,
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8", newline="\n")
    print(json.dumps(record["verdict"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
