"""Offline freeze of the Mini look-120 semantic contract and exact execution plan."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_mini_semantic_reconciliation_amendment.yaml"
NANO_PLAN = ROOT / "data/manifests/p1_v4_independent_calibration_look120_semantic_execution_plan.json"
NANO_CHECKPOINT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_semantic_authorization_checkpoint.json"
MINI_PLAN = ROOT / "data/manifests/p1_v4_independent_calibration_look120_mini_semantic_execution_plan.json"
MANIFEST = ROOT / "data/manifests/p1_v4_independent_calibration_look120_mini_semantic_reconciliation_amendment.json"
AUDIT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_mini_semantic_reconciliation_audit.json"
REPORT = ROOT / "reports/p1_v4_independent_calibration_look120_mini_semantic_reconciliation_amendment.md"

MODEL = "gpt-5.4-mini-2026-03-17"

def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def write_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise RuntimeError(f"artifact drift: {path}")
    if not path.exists():
        path.write_bytes(payload)

def build() -> tuple[dict, dict, dict, str]:
    nano = json.loads(NANO_PLAN.read_text(encoding="utf-8"))
    plan = copy.deepcopy(nano)
    plan["schema_version"] = "fourgraph.p1_v4_independent_calibration_look120_mini_semantic_execution_plan.v1"
    plan["task"] = "P1_V4_INDEPENDENT_CALIBRATION_LOOK120_MINI_SEMANTIC_EXECUTION_PLAN"
    plan["supersedes_nano_plan_sha256"] = sha(NANO_PLAN)
    plan["model"] = MODEL
    plan["reasoning_effort"] = "medium"
    plan["agreement_policy"] = {
        "automatic": ["VERY_HIGH", "HIGH"],
        "review_only": ["MEDIUM"],
        "abstain": ["UNCERTAIN", "CONFLICT"],
    }
    plan["primary_meek_closure"] = "forbidden"
    for call in plan["logical_calls"]:
        call["model"] = MODEL
        if call["reasoning_effort"] != "medium":
            raise RuntimeError("unexpected reasoning effort in parent plan")

    calls = plan["logical_calls"]
    pools = plan["pair_pools"]
    scene_ids = {call["study_id"] for call in calls}
    input_ids = {(call["study_id"], call["variant"]) for call in calls}
    total_pairs = sum(len(pool["pairs"]) for pool in pools.values())
    checks = {
        "scenes_exactly_120": len(scene_ids) == 120,
        "inputs_exactly_360": len(input_ids) == 360,
        "logical_calls_exactly_2160": len(calls) == 2160,
        "six_prompts_per_input": all(sum(1 for c in calls if (c["study_id"], c["variant"]) == ident) == 6 for ident in input_ids),
        "variants_full_partial_ambiguous_only": {c["variant"] for c in calls} == {"full", "partial", "ambiguous"},
        "nonedge_excluded": plan["scope"]["nonedge_diagnostic"] == "excluded_pending_exact_registered_pair_manifest",
        "pool_pairs_exactly_488": total_pairs == 488,
        "pool_at_most_21_per_scene": max(len(pool["pairs"]) for pool in pools.values()) <= 21,
        "all_calls_use_mini_medium": all(c["model"] == MODEL and c["reasoning_effort"] == "medium" for c in calls),
        "raw_evidence_shared_between_conditions": all(c["conditions"] == ["constrained_boss", "constrained_fges"] for c in calls),
    }
    if not all(checks.values()):
        failed = [key for key, passed in checks.items() if not passed]
        raise RuntimeError(f"reconciliation audit failed: {failed}")

    manifest = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look120_mini_semantic_reconciliation_amendment.v1",
        "task": "P1_V4_INDEPENDENT_CALIBRATION_LOOK120_MINI_SEMANTIC_RECONCILIATION_AMENDMENT",
        "status": "PASS_OFFLINE_FROZEN_PENDING_MINI_PROVIDER_PREFLIGHT",
        "supersedes_for_live_execution": {
            "nano_checkpoint": str(NANO_CHECKPOINT.relative_to(ROOT)).replace("\\", "/"),
            "nano_checkpoint_sha256": sha(NANO_CHECKPOINT),
            "disposition": "retained_historical_not_valid_for_mini_live_execution",
        },
        "contract": {
            "model": MODEL,
            "reasoning_effort": "medium",
            "prompt_sha256": sha(ROOT / "prompts/p1_semantic_sentence_ids_v1.md"),
            "schema_sha256": sha(ROOT / "schemas/semantic_sentence_id_response_v1.schema.json"),
            "automatic": ["VERY_HIGH", "HIGH"],
            "review_only": ["MEDIUM"],
            "abstain": ["UNCERTAIN", "CONFLICT"],
            "truncation": "disabled",
            "automatic_chunking": "forbidden",
            "primary_meek_closure": "forbidden",
        },
        "statistical_parents": {
            "primary": "constrained_boss",
            "robustness": "constrained_fges",
            "semantic_pool": "union_of_constrained_boss_and_constrained_fges_undirected_edges",
            "condition_specific_filtering": True,
        },
        "scope": {
            "scenes": 120,
            "public_inputs": 360,
            "variants": ["full", "partial", "ambiguous"],
            "scene_pair_records": total_pairs,
            "max_pairs_per_scene": 21,
            "logical_calls": len(calls),
            "nonedge_diagnostic": "excluded",
        },
        "execution_plan": {
            "path": str(MINI_PLAN.relative_to(ROOT)).replace("\\", "/"),
            "sha256": hashlib.sha256(canonical(plan)).hexdigest().upper(),
        },
        "boundary": {
            "provider_preflight_calls": 0,
            "study_semantic_api_calls": 0,
            "oracle_access": 0,
            "holdout_access": 0,
            "statistical_reruns": 0,
            "metric_calculation": False,
        },
        "next_gate": "P1_V4_INDEPENDENT_CALIBRATION_LOOK120_MINI_PROVIDER_PREFLIGHT",
    }
    audit = {
        "task": manifest["task"],
        "status": "PASS",
        "config_sha256": sha(CONFIG),
        "parent_nano_plan_sha256": sha(NANO_PLAN),
        "mini_plan_sha256": hashlib.sha256(canonical(plan)).hexdigest().upper(),
        "manifest_sha256": hashlib.sha256(canonical(manifest)).hexdigest().upper(),
        "checks": checks | {
            "automatic_policy_is_very_high_and_high": manifest["contract"]["automatic"] == ["VERY_HIGH", "HIGH"],
            "medium_is_review_only": manifest["contract"]["review_only"] == ["MEDIUM"],
            "primary_closure_forbidden": manifest["contract"]["primary_meek_closure"] == "forbidden",
            "no_provider_or_study_api_calls": True,
            "no_oracle_or_holdout": True,
            "no_statistical_reruns": True,
        },
    }
    report = """# P1V4 look-120 Mini semantic reconciliation amendment

Status: **PASS_OFFLINE_FROZEN_PENDING_MINI_PROVIDER_PREFLIGHT**.

The canonical live semantic contract is now GPT-5.4 Mini (`gpt-5.4-mini-2026-03-17`) with medium reasoning. Automatic publication candidates are **VERY_HIGH** and **HIGH**; **MEDIUM** is review-only; **UNCERTAIN** and **CONFLICT** abstain. Primary Meek closure is forbidden.

The Mini plan pins 120 scenes, 360 Full/Partial/Ambiguous public inputs, 488 scene-level undirected-pair records, six balanced prompts per input, and 2,160 logical calls. It shares raw evidence between constrained-BOSS and constrained-FGES before condition-specific filtering. Non-edge is excluded.

The earlier Nano checkpoint and provider preflight remain preserved as historical technical artifacts, but are invalid for Mini live execution. This amendment performs no provider call, no study API call, no Oracle/holdout access, no statistical rerun, and no metric calculation. The next step is a Mini-specific provider preflight.
"""
    return plan, manifest, audit, report

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path in (CONFIG, NANO_PLAN, NANO_CHECKPOINT):
        if not path.is_file():
            raise SystemExit(f"missing prerequisite: {path}")
    plan, manifest, audit, report = build()
    expected = ((MINI_PLAN, canonical(plan)), (MANIFEST, canonical(manifest)), (AUDIT, canonical(audit)), (REPORT, report.encode()))
    if args.check:
        for path, content in expected:
            if not path.is_file() or path.read_bytes() != content:
                raise SystemExit(f"replay mismatch: {path}")
        print(json.dumps({"status": "PASS_CHECK", "logical_calls": len(plan["logical_calls"]), "model": MODEL}))
        return
    for path, content in expected:
        write_once(path, content)
    print(json.dumps({"status": manifest["status"], "logical_calls": len(plan["logical_calls"]), "model": MODEL}))

if __name__ == "__main__":
    main()
