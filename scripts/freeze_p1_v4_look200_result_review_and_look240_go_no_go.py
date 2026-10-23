"""Freeze the registered look-200 decision without changing the policy."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/p1_v4_look200_result_review_and_look240_go_no_go.yaml"


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def build() -> tuple[dict, dict[Path, bytes]]:
    config = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    for name, spec in config["inputs"].items():
        path = ROOT / spec["path"]
        checks[f"input_{name}"] = path.is_file() and sha256(path) == spec["sha256"]
    results = json.loads((ROOT / config["inputs"]["results"]["path"]).read_text(encoding="utf-8"))
    audit_input = json.loads((ROOT / config["inputs"]["audit"]["path"]).read_text(encoding="utf-8"))
    primary = results["conditions"][results["primary_condition"]]
    full = primary["variants"]["full"]
    partial = primary["variants"]["partial"]
    checks.update(
        {
            "oracle_audit_pass": audit_input.get("status") == "PASS_ORACLE_SCORING",
            "status_registered": results.get("status") == config["registered_decision"]["expected_status"],
            "full_gate_pass": full["registered_gate_pass"] is True,
            "partial_precision_pass": partial["precision_confidence_sequence"]["pass"] is True,
            "partial_coverage_pass": partial["coverage"]["crosses"] is True,
            "partial_high_guardrail_pending": partial["High_guardrail"]["pass"] is False
            and partial["High_guardrail"]["contributing_scenes"] < config["registered_decision"]["minimum_high_contributing_scenes"],
            "ambiguous_pass": primary["ambiguous_abstention_diagnostic"]["pass"] is True,
            "not_futile": not any(row["futile"] for row in results["futility"].values()),
            "policy_frozen": all(config["frozen_policy"].values()),
            "boundary_zero": all(value == 0 for value in config["boundaries"].values()),
        }
    )
    passed = all(checks.values())
    review = {
        "schema_version": "fourgraph.p1_v4_look200_result_review_and_look240_go_no_go.v1",
        "task": config["task"],
        "status": "PASS" if passed else "FAIL",
        "decision": "CONTINUE_TO_REGISTERED_LOOK_240" if passed else "STOP_REVIEW_FAILED",
        "reason": "Full passed all gates; Partial passed precision and coverage but has only 22 High-contributing scenes versus the registered minimum of 60. Futility is false.",
        "look200_results_sha256": config["inputs"]["results"]["sha256"],
        "primary_condition": results["primary_condition"],
        "primary_summary": {
            "full": full,
            "partial": partial,
            "ambiguous": primary["ambiguous_abstention_diagnostic"],
        },
        "futility": results["futility"],
        "policy_change": False,
        "validation_authorized": False,
        "look240_execution_authorized": False,
        "holdout_access": 0,
    }
    review_bytes = canonical_bytes(review)
    audit = {
        "schema_version": "fourgraph.p1_v4_look200_result_review_and_look240_go_no_go_audit.v1",
        "task": config["task"],
        "status": "PASS" if passed else "FAIL",
        "checks": checks,
        "review_sha256": hashlib.sha256(review_bytes).hexdigest().upper(),
        "semantic_api_calls": 0,
        "statistical_reruns": 0,
        "validation_access": 0,
        "holdout_access": 0,
    }
    report = (
        "# P1V4 look 200 result review\n\n"
        "Decision: **CONTINUE_TO_REGISTERED_LOOK_240**. Full passed every registered gate. Partial passed the "
        "precision confidence sequence and coverage gate, but only 22 scenes contributed a published HIGH edge, "
        "below the preregistered minimum of 60. The design is not futile, so no policy or threshold is changed.\n"
    ).encode()
    artifacts = {
        ROOT / config["outputs"]["review"]: review_bytes,
        ROOT / config["outputs"]["audit"]: canonical_bytes(audit),
        ROOT / config["outputs"]["report"]: report,
    }
    return audit, artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    audit, artifacts = build()
    for path, payload in artifacts.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != payload:
                raise RuntimeError(f"review replay drift: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    print(json.dumps(audit, indent=2))
    return 0 if audit["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
