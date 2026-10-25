"""Review calibration look 240 and freeze the registered 40-scene look-280 increment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_look240_result_review_and_look280_identity_freeze.yaml"
SCRIPT = Path(__file__).resolve()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def canonical_jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json(row) for row in rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def build() -> tuple[dict[str, Any], dict[Path, bytes]]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if cfg["status"] != "offline_review_and_identity_freeze_only":
        raise RuntimeError("checkpoint mode drift")

    parent_paths: dict[str, Path] = {}
    dependency_records: list[dict[str, Any]] = []
    dependency_checks: dict[str, bool] = {}
    for name, spec in cfg["parents"].items():
        path = ROOT / spec["path"]
        observed = sha256(path) if path.is_file() else None
        dependency_checks[f"input_{name}"] = observed == spec["sha256"]
        parent_paths[name] = path
        dependency_records.append({"name": name, "path": spec["path"], "sha256": observed})

    results = load_json(parent_paths["results"])
    oracle_audit = load_json(parent_paths["audit"])
    identity_plan = load_json(parent_paths["exact_identity_plan"])
    all_identities = load_jsonl(parent_paths["exact_identities"])
    primary = results["conditions"][results["primary_condition"]]
    full = primary["variants"]["full"]
    partial = primary["variants"]["partial"]
    selection = cfg["identity_selection"]
    registered = cfg["registered_decision"]

    start = int(selection["execution_index_start_inclusive"])
    stop = int(selection["execution_index_end_exclusive"])
    ordered_ids = identity_plan["exact_scene_ids_in_execution_order"]
    prior_ids = ordered_ids[:start]
    incremental_ids = ordered_ids[start:stop]
    cumulative_ids = ordered_ids[:stop]
    by_id = {row["study_id"]: row for row in all_identities}
    selected = [by_id[scene_id] for scene_id in incremental_ids]

    review_checks = {
        **dependency_checks,
        "oracle_audit_pass": oracle_audit.get("status") == "PASS_ORACLE_SCORING",
        "oracle_exact_240": oracle_audit.get("oracle_scenes_accessed") == 240,
        "registered_status": results.get("status") == registered["expected_status"],
        "primary_is_constrained_boss": results.get("primary_condition") == "Constrained-BOSS",
        "full_precision_pass": full["precision_confidence_sequence"]["pass"] is True,
        "full_coverage_pass": full["coverage"]["crosses"] is True,
        "full_high_guardrail_pass": full["High_guardrail"]["pass"] is True,
        "full_registered_gate_pass": full["registered_gate_pass"] is True,
        "partial_precision_pass": partial["precision_confidence_sequence"]["pass"] is True,
        "partial_coverage_pass": partial["coverage"]["crosses"] is True,
        "partial_high_guardrail_pending": partial["High_guardrail"]["pass"] is False
        and partial["High_guardrail"]["contributing_scenes"] < registered["minimum_high_contributing_scenes"],
        "partial_registered_gate_pending": partial["registered_gate_pass"] is False,
        "ambiguous_diagnostic_pass": primary["ambiguous_abstention_diagnostic"]["pass"] is True,
        "not_futile": not any(item["futile"] for item in results["futility"].values()),
        "no_meek_closure": results.get("meek_closure") == 0,
        "no_new_api_or_statistical_run": results.get("semantic_api_calls") == 0
        and results.get("statistical_reruns") == 0,
        "validation_and_holdout_locked": results.get("validation_access") == 0
        and results.get("holdout_access") == 0,
        "policy_frozen": all(cfg["frozen_policy"].values()),
        "offline_boundary_zero": all(value == 0 for value in cfg["boundaries"].values()),
    }
    review_pass = all(review_checks.values())
    decision = "CONTINUE_TO_REGISTERED_LOOK_280" if review_pass else "STOP_REVIEW_FAILED"
    review = {
        "schema_version": "fourgraph.p1_v4_look240_result_review_and_look280_go_no_go.v1",
        "task": cfg["task"],
        "status": "PASS_OFFLINE_REVIEW" if review_pass else "FAIL",
        "decision": decision,
        "reason": (
            "Full passed all registered gates. Partial passed the precision confidence sequence and coverage gate, "
            f"but only {partial['High_guardrail']['contributing_scenes']} scenes contributed a published HIGH edge "
            f"versus the registered minimum of {registered['minimum_high_contributing_scenes']}. Futility is false."
        ),
        "look240_results_sha256": cfg["parents"]["results"]["sha256"],
        "primary_condition": results["primary_condition"],
        "primary_summary": {
            "full": full,
            "partial": partial,
            "ambiguous": primary["ambiguous_abstention_diagnostic"],
        },
        "futility": results["futility"],
        "policy_change": False,
        "validation_authorized": False,
        "look280_execution_authorized": False,
        "holdout_access": 0,
    }
    review_body = canonical_json(review)

    identity_checks = {
        "review_passes": review_pass,
        "next_look_registered": registered["next_look_if_inconclusive"] in identity_plan["registered_looks"],
        "exact_registered_slice": incremental_ids == ordered_ids[240:280],
        "exact_40_increment": len(selected) == selection["incremental_scene_count"] == stop - start,
        "exact_280_cumulative": len(cumulative_ids) == selection["cumulative_scene_count"] == stop,
        "no_overlap_with_first_240": set(prior_ids).isdisjoint(incremental_ids),
        "unique_incremental_ids": len(set(incremental_ids)) == len(incremental_ids),
        "unique_cumulative_ids": len(set(cumulative_ids)) == len(cumulative_ids),
        "all_identities_resolve": len(selected) == len(incremental_ids),
        "namespace_locked": all(row["study_id"].startswith(selection["namespace"]) for row in selected),
        "role_locked": all(row["role"] == selection["allowed_role"] for row in selected),
        "batch_locked": all(row["batch_id"] == selection["expected_batch_id"] for row in selected),
        "first_registered_look_locked": all(row["first_registered_look"] == 280 for row in selected),
        "look280_membership_locked": all(280 in row["included_in_registered_looks"] for row in selected),
        "source_unmaterialized": all(row["scene_materialized"] is False for row in selected),
        "component_seeds_complete": all(
            set(row["component_seeds"])
            == {"bootstrap_boss", "edge_weights", "graph_candidates", "observations", "query_order", "story_template"}
            for row in selected
        ),
        "no_posthoc_diagnostic_assignment": all(not row["diagnostic_memberships"] for row in selected),
    }
    identity_pass = all(identity_checks.values())
    identities_body = canonical_jsonl(selected)
    identities_hash = hashlib.sha256(identities_body).hexdigest().upper()
    incremental_plan = {
        "schema_version": "fourgraph.p1_v4_look280_incremental_exact_identity_plan.v1",
        "task": "P1_V4_LOOK280_INCREMENTAL_EXACT_IDENTITY_FREEZE",
        "status": "PASS_FROZEN_EXACT_40_IDENTITIES_OFFLINE" if identity_pass else "FAIL",
        "previous_registered_look": 240,
        "next_registered_look": 280,
        "execution_index_range": {"start_inclusive": start, "end_exclusive": stop},
        "batch_id": selection["expected_batch_id"],
        "incremental_scene_count": len(selected),
        "cumulative_scene_count": len(cumulative_ids),
        "incremental_scene_ids_in_execution_order": incremental_ids,
        "cumulative_scene_ids_in_execution_order": cumulative_ids,
        "incremental_identity_sha256_by_scene": {
            row["study_id"]: row["identity_sha256"] for row in selected
        },
        "incremental_component_seeds_by_scene": {
            row["study_id"]: row["component_seeds"] for row in selected
        },
        "incremental_identities_sha256": identities_hash,
        "seed_policy": selection["seed_policy"],
        "diagnostics": {
            "ambiguous_increment": "none_fixed_120_scene_subset",
            "nonedge_increment": "excluded_from_p1v4_calibration",
        },
        "dependencies": dependency_records
        + [
            {"name": "config", "path": CONFIG.relative_to(ROOT).as_posix(), "sha256": sha256(CONFIG)},
            {"name": "implementation", "path": SCRIPT.relative_to(ROOT).as_posix(), "sha256": sha256(SCRIPT)},
            {"name": "look240_review", "sha256": hashlib.sha256(review_body).hexdigest().upper()},
        ],
        "authorization": {
            "identity_freeze_complete": identity_pass,
            "materialization_authorized": False,
            "story_generation_authorized": False,
            "statistical_execution_authorized": False,
            "semantic_api_authorized": False,
            "oracle_access_authorized": False,
            "validation_or_holdout_authorized": False,
        },
        "next_action": "P1_V4_LOOK280_INCREMENTAL_MATERIALIZATION_PREFLIGHT_AND_AUTHORIZATION_CHECKPOINT",
    }
    plan_body = canonical_json(incremental_plan)
    review_audit = {
        "schema_version": "fourgraph.p1_v4_look240_result_review_and_look280_go_no_go_audit.v1",
        "task": "P1_V4_LOOK240_OVERLAY_RESULT_REVIEW_AND_LOOK280_GO_NO_GO",
        "status": "PASS" if review_pass else "FAIL",
        "checks": review_checks,
        "review_sha256": hashlib.sha256(review_body).hexdigest().upper(),
        "semantic_api_calls": 0,
        "statistical_reruns": 0,
        "oracle_reads": 0,
        "validation_access": 0,
        "holdout_access": 0,
    }
    identity_audit = {
        "schema_version": "fourgraph.p1_v4_look280_incremental_exact_identity_audit.v1",
        "task": "P1_V4_LOOK280_INCREMENTAL_EXACT_IDENTITY_FREEZE",
        "status": "PASS" if identity_pass else "FAIL",
        "checks": identity_checks,
        "counts": {
            "previous_scenes": len(prior_ids),
            "incremental_scenes": len(selected),
            "cumulative_scenes": len(cumulative_ids),
            "scenes_materialized": 0,
            "stories_generated": 0,
            "statistical_fits": 0,
            "semantic_api_calls": 0,
            "oracle_reads": 0,
        },
        "hashes": {
            "config": sha256(CONFIG),
            "implementation": sha256(SCRIPT),
            "incremental_identities": identities_hash,
            "incremental_plan": hashlib.sha256(plan_body).hexdigest().upper(),
            "master_identity_plan": cfg["parents"]["exact_identity_plan"]["sha256"],
            "master_identities": cfg["parents"]["exact_identities"]["sha256"],
        },
        "validation_access": 0,
        "holdout_access": 0,
        "next_action": incremental_plan["next_action"],
    }
    overall_pass = review_pass and identity_pass
    report = "\n".join(
        [
            "# P1V4 look-240 review and look-280 exact identity freeze",
            "",
            f"Status: **{'PASS' if overall_pass else 'FAIL'}**.",
            "",
            "The registered decision is **CONTINUE_TO_REGISTERED_LOOK_280**. Full passed precision, coverage, and the HIGH guardrail. Partial passed precision and coverage, but only 26 scenes contributed a HIGH publication versus the registered minimum of 60. Futility remains false.",
            "",
            f"The next increment is the immutable execution-order slice 240–279: 40 unique scenes from `{incremental_ids[0]}` through `{incremental_ids[-1]}` in registered order, with no overlap with the first 240 scenes.",
            "",
            "All identity hashes and component seeds are copied from the frozen master calibration plan. No seed was regenerated and no diagnostic membership was assigned after observing results.",
            "",
            "This checkpoint materialized no scene or story, ran no statistical fit, made no API call, and performed no new Oracle, validation, or holdout access. Look-280 execution requires separate authorization.",
            "",
        ]
    ).encode("utf-8")
    outputs = cfg["outputs"]
    artifacts = {
        ROOT / outputs["review"]: review_body,
        ROOT / outputs["review_audit"]: canonical_json(review_audit),
        ROOT / outputs["incremental_identities"]: identities_body,
        ROOT / outputs["incremental_plan"]: plan_body,
        ROOT / outputs["identity_audit"]: canonical_json(identity_audit),
        ROOT / outputs["report"]: report,
    }
    return {"status": "PASS" if overall_pass else "FAIL", "review": review_audit, "identity": identity_audit}, artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify byte-for-byte replay")
    args = parser.parse_args()
    audit, artifacts = build()
    for path, payload in artifacts.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != payload:
                raise RuntimeError(f"artifact replay drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
