"""Freeze the offline look-120 overlay review and staged look-160 decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_look120_overlay_result_review_and_look160_go_no_go.yaml"
SCRIPT = Path(__file__).resolve()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def encoded(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dependency(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
    }


def write_once(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != body:
            raise RuntimeError(f"non-deterministic artifact drift: {path.relative_to(ROOT)}")
        return
    path.write_bytes(body)


def build() -> dict[Path, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if cfg["status"] != "offline_review_requested":
        raise RuntimeError("look-120 review request status drift")

    pinned: dict[str, Path] = {}
    for section in ("dependencies", "superseded_incident_evidence"):
        for name, item in cfg[section].items():
            path = ROOT / item["path"]
            if not path.is_file():
                raise RuntimeError(f"missing pinned artifact: {name}")
            if digest(path) != item["sha256"]:
                raise RuntimeError(f"pinned artifact hash drift: {name}")
            pinned[name] = path

    results = load(pinned["overlay_results"])
    result_audit = load(pinned["overlay_audit"])
    architecture = load(pinned["final_architecture"])
    identity_plan = load(pinned["exact_identity_plan"])
    identity_audit = load(pinned["exact_identity_plan_audit"])
    response_audit = load(pinned["response_freeze_audit"])
    statistical_audit = load(pinned["statistical_final_audit"])
    old_results = load(pinned["old_results"])
    expected = cfg["expected_review"]
    policy = cfg["frozen_policy"]

    primary = results["conditions"][expected["primary_condition"]]
    variant_checks: dict[str, dict[str, bool]] = {}
    for variant in expected["certification_variants"]:
        row = primary["variants"][variant]
        variant_checks[variant] = {
            "coverage_crosses": row["coverage"]["crosses"] is True,
            "coverage_at_least_registered_floor": row["coverage"]["mean_coverage"] >= 0.20,
            "precision_sequence_not_yet_crossed": row["precision_evidence"]["crosses"] is False,
            "minimum_precision_scene_count_reached": row["precision_evidence"]["contributing_scenes"] >= 100,
            "high_guardrail_not_yet_passed": row["High_guardrail"]["pass"] is False,
            "high_scene_count_below_registered_minimum": row["High_guardrail"]["contributing_scenes"] < 60,
            "registered_gate_not_passed": row["registered_gate_pass"] is False,
            "overlay_valid_after_fail_closed": row["overlay_validity"]["pass"] is True,
            "no_false_adjacency_orientation": row["false_positive_adjacency_orientations"] == 0,
        }

    semantic = architecture["semantic_contract"]
    architecture_rules = architecture["architecture"]
    checks = {
        "overlay_replay_audit_pass": result_audit["status"] == "PASS_OVERLAY_ORACLE_REPLAY",
        "exact_120_oracle_commitments_verified": result_audit["oracle_commitments_verified"] == 120,
        "exact_720_overlay_outputs": result_audit["overlay_outputs"] == 720,
        "parent_cpdag_immutable": result_audit["parent_cpdag_mutations"] == 0,
        "no_api_or_statistical_rerun_or_closure_or_holdout": all(
            result_audit[key] == 0
            for key in ("semantic_api_calls", "statistical_reruns", "meek_closure", "holdout_access")
        ),
        "metric_dataset_hash_matches_result": results["metric_dataset_sha256"]
        == digest(pinned["overlay_metric_dataset"]),
        "overlay_output_hash_matches_result": results["overlay_outputs_sha256"]
        == digest(pinned["overlay_outputs"]),
        "registered_look_is_120": results["registered_look"] == expected["registered_look"],
        "primary_condition_frozen": results["primary_condition"] == expected["primary_condition"],
        "look120_decision_is_continue_160": results["status"] == expected["decision"],
        "full_review_checks_pass": all(variant_checks["full"].values()),
        "partial_review_checks_pass": all(variant_checks["partial"].values()),
        "ambiguous_gate_pass": primary["ambiguous_abstention_diagnostic"]["pass"] is True,
        "ambiguous_publishes_zero_directions": primary["ambiguous_abstention_diagnostic"]["automatic_direction_scenes"] == 0,
        "not_futile_at_registered_maximum": all(
            results["futility"][variant]["futile"] is False
            for variant in expected["certification_variants"]
        ),
        "no_condition_selection_performed": results["selection_performed"] is False,
        "response_freeze_pass": response_audit["status"] == "PASS",
        "statistical_execution_pass": statistical_audit["status"] == "PASS_STATISTICAL_EXECUTION",
        "identity_plan_pass_and_look160_registered": identity_audit["status"] == "PASS"
        and expected["next_registered_look"] in identity_plan["registered_looks"],
        "model_prompt_schema_locked": semantic["model_snapshot"] == policy["model"]
        and semantic["reasoning_effort"] == policy["reasoning_effort"]
        and semantic["prompt_sha256"] == policy["prompt_sha256"]
        and semantic["schema_sha256"] == policy["schema_sha256"],
        "agreement_policy_locked": semantic["automatic_agreements"] == policy["automatic_agreements"],
        "parent_methods_locked": architecture_rules["primary_parent"] == policy["primary_parent"]
        and architecture_rules["robustness_parent"] == policy["robustness_parent"],
        "closure_and_parent_mutation_forbidden": architecture_rules["closure"] == "forbidden"
        and architecture_rules["parent_mutation"] == "forbidden",
        "old_cpdag_scorer_preserved_as_distinct_incident": digest(pinned["old_results"])
        != digest(pinned["overlay_results"])
        and old_results["task"] != results["task"],
    }
    passed = all(checks.values())
    if not passed:
        failed = [name for name, value in checks.items() if not value]
        raise RuntimeError(f"look-120 review gate failed: {failed}")

    variants = {
        variant: {
            "combined_published": primary["variants"][variant]["combined_published"],
            "coverage": primary["variants"][variant]["coverage"],
            "abstention_rate_scene_mean": primary["variants"][variant]["abstention_rate_scene_mean"],
            "precision_evidence": primary["variants"][variant]["precision_evidence"],
            "high_guardrail": primary["variants"][variant]["High_guardrail"],
            "semantic_conflict_fail_closed": primary["variants"][variant]["semantic_conflict_fail_closed"],
            "false_positive_adjacency_orientations": primary["variants"][variant]["false_positive_adjacency_orientations"],
            "registered_gate_pass": primary["variants"][variant]["registered_gate_pass"],
        }
        for variant in expected["certification_variants"]
    }
    incident = {
        "classification": "SUPERSEDED_INCORRECT_CPDAG_VALIDATOR_FOR_PUBLICATION_OVERLAY",
        "scientific_use": "forbidden",
        "retention": "preserved_as_incident_evidence",
        "artifacts": [dependency(pinned[name]) for name in cfg["superseded_incident_evidence"]],
    }
    decision = {
        "schema_version": "fourgraph.p1_v4_look120_overlay_result_review_go_no_go.v1",
        "task": cfg["task"],
        "status": "PASS_OFFLINE_LOOK120_REVIEW",
        "decision": expected["decision"],
        "reason": "coverage_and_ambiguous_pass_but_precision_confidence_sequence_and_high_guardrail_need_more_scenes",
        "scope": {
            "registered_look": 120,
            "next_registered_look": 160,
            "incremental_scenes_if_later_authorized": 40,
            "primary_condition": expected["primary_condition"],
            "robustness_condition": expected["robustness_condition"],
        },
        "primary_results": {
            "variants": variants,
            "ambiguous_abstention_diagnostic": primary["ambiguous_abstention_diagnostic"],
            "futility": results["futility"],
        },
        "scientific_interpretation": {
            "coverage_gate": "PASS",
            "ambiguous_abstention_gate": "PASS",
            "precision_confidence_sequence": "INSUFFICIENT_EVIDENCE_AT_LOOK120",
            "high_guardrail": "INSUFFICIENT_CONTRIBUTING_SCENES_AT_LOOK120",
            "futility": "NOT_TRIGGERED",
            "early_certification": False,
        },
        "frozen_policy": policy,
        "policy_changes_authorized": False,
        "incident_evidence": incident,
        "permitted_next_action": "FREEZE_EXACT_INCREMENTAL_LOOK160_PLAN_FOR_40_NEW_SCENES",
        "live_look160_execution_authorized": False,
        "automatic_follow_on": False,
        "forbidden_actions": [
            "prompt_or_schema_change",
            "model_or_reasoning_effort_change",
            "agreement_rule_change",
            "parent_method_change",
            "threshold_tuning",
            "look160_live_execution_without_new_checkpoints",
            "validation_or_holdout_access",
            "downstream_reasoner_execution",
        ],
        "dependencies": sorted(
            [dependency(path) for path in pinned.values()] + [dependency(CONFIG), dependency(SCRIPT)],
            key=lambda item: item["path"],
        ),
        "execution_boundary": cfg["boundaries"],
    }
    decision_body = encoded(decision)
    audit = {
        "schema_version": "fourgraph.p1_v4_look120_overlay_result_review_go_no_go_audit.v1",
        "task": cfg["task"],
        "status": "PASS_OFFLINE_LOOK120_REVIEW_AND_GO_LOOK160_PLANNING_ONLY",
        "checks": checks,
        "variant_checks": variant_checks,
        "hashes": {
            "config": digest(CONFIG),
            "implementation": digest(SCRIPT),
            "decision": hashlib.sha256(decision_body).hexdigest().upper(),
            "overlay_results": digest(pinned["overlay_results"]),
            "overlay_audit": digest(pinned["overlay_audit"]),
            "old_incident_results": digest(pinned["old_results"]),
        },
        "verdict": {
            "look120_early_certification": False,
            "look120_futility_stop": False,
            "look160_incremental_plan_freeze_permitted": True,
            "look160_materialization_authorized": False,
            "look160_statistical_execution_authorized": False,
            "look160_semantic_api_authorized": False,
            "validation_or_holdout_authorized": False,
        },
        "evidence_boundary": cfg["boundaries"],
        "next_action": decision["permitted_next_action"],
    }
    audit_body = encoded(audit)
    report = "\n".join(
        [
            "# P1V4 look-120 overlay result review and look-160 GO/NO-GO",
            "",
            "Decision: **CONTINUE_TO_REGISTERED_LOOK_160**.",
            "",
            "The immutable-parent evidence overlay passed its offline audit. Full and Partial coverage crossed the registered gate and Ambiguous published no automatic semantic direction. No false-positive adjacency was oriented.",
            "",
            "Look 120 does not support early certification. The scene-level precision confidence sequences have not crossed their registered boundary, and the High guardrail has only 32 Full and 15 Partial contributing scenes versus the registered minimum of 60. Futility is not triggered, so the registered action is to add exactly 40 fresh calibration scenes for cumulative look 160.",
            "",
            "The superseded CPDAG-output scorer and its outputs remain hash-pinned incident evidence and are forbidden for scientific conclusions. The model, prompt, schema, six-vote agreement policy, parent methods, thresholds and no-closure rule remain unchanged.",
            "",
            "This checkpoint permits only an offline exact look-160 incremental-plan freeze. It does not authorize materialization, statistical discovery, semantic API calls, Oracle replay, validation, holdout access or downstream reasoning.",
            "",
        ]
    ).encode("utf-8")
    return {
        ROOT / cfg["outputs"]["decision"]: decision_body,
        ROOT / cfg["outputs"]["audit"]: audit_body,
        ROOT / cfg["outputs"]["report"]: report,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = build()
    if args.check:
        for path, body in generated.items():
            if not path.is_file() or path.read_bytes() != body:
                raise SystemExit(f"artifact drift: {path.relative_to(ROOT)}")
        print("look-120 review replays byte-for-byte; look-160 live work remains unauthorized")
        return 0
    for path, body in generated.items():
        write_once(path, body)
    audit_path = ROOT / yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["outputs"]["audit"]
    print(json.dumps(load(audit_path), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
