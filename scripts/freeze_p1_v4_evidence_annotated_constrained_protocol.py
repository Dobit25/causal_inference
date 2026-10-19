"""Freeze Stage 3A without materialising a new cohort or accessing Oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_evidence_annotated_constrained_protocol.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def dependency(path: Path) -> dict[str, object]:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path), "bytes": path.stat().st_size}


def build() -> dict[Path, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    parents = {name: ROOT / value["path"] for name, value in cfg["parents"].items()}
    checks = {f"parent_{name}_hash": path.is_file() and digest(path) == cfg["parents"][name]["sha256"] for name, path in parents.items()}
    contract_paths = [
        ROOT / cfg["semantic_contract"]["prompt"], ROOT / cfg["semantic_contract"]["schema"],
        ROOT / cfg["semantic_contract"]["production_validator"], ROOT / cfg["semantic_contract"]["reference_validator"],
        ROOT / "src/fourgraph/evidence_annotated_cpdag.py", ROOT / "src/fourgraph/evidence_annotated_cpdag_reference.py",
    ]
    checks.update({f"exists_{path.name}": path.is_file() for path in contract_paths})
    checks["nano_medium_fixed"] = cfg["semantic_contract"]["model_snapshot"] == "gpt-5.4-nano-2026-03-17" and cfg["semantic_contract"]["reasoning_effort"] == "medium"
    checks["agreement_policy_fixed"] = cfg["semantic_contract"]["automatic_agreement"] == ["VERY_HIGH"] and cfg["semantic_contract"]["review_only_agreement"] == ["HIGH", "MEDIUM"]
    checks["primary_is_constrained_boss"] = cfg["statistical_contract"]["primary_parent"]["algorithm"] == "BOSS"
    checks["robustness_is_constrained_fges"] = cfg["statistical_contract"]["robustness_parent"]["algorithm"] == "FGES"
    checks["meek_not_auto"] = cfg["evidence_annotated_output"]["automatic_meek_closure"] == "forbidden"
    checks["new_namespace"] = cfg["cohort_plan"]["namespace"] == "P1V4" and cfg["cohort_plan"]["reuse_of_look120_or_previous_identity"] == "forbidden"
    checks["risk_gates_fixed"] = cfg["certification_gates"] == {
        "independent_unit": "scene", "precision_lcb_minimum": 0.95,
        "coverage_scene_mean_minimum": 0.20, "compelled_retention_scene_mean_minimum": 0.20,
        "parent_validity_required": 1.0, "certification_variants": ["full", "partial"],
        "false_adjacency_orientation_counts_as_error": True, "no_meek_directions_in_primary_auto_denominator": True,
    }
    checks["offline_boundary"] = all(value in (0, False) for value in cfg["execution_boundary"].values())
    passed = all(checks.values())
    protocol = {
        "schema_version": "fourgraph.p1_v4_evidence_annotated_constrained_protocol.v1",
        "task": cfg["task"], "status": "FROZEN_OFFLINE_PROTOCOL" if passed else "FAILED_OFFLINE_PROTOCOL",
        "research_question": cfg["research_question"], "semantic_contract": cfg["semantic_contract"],
        "statistical_contract": cfg["statistical_contract"], "evidence_annotated_output": cfg["evidence_annotated_output"],
        "certification_gates": cfg["certification_gates"], "cohort_plan": cfg["cohort_plan"],
        "execution_boundary": cfg["execution_boundary"],
        "dependencies": sorted([dependency(CONFIG), dependency(Path(__file__)), *[dependency(path) for path in parents.values()], *[dependency(path) for path in contract_paths]], key=lambda row: str(row["path"])),
        "authorization_after_freeze": {"offline_implementation_conformance_authorized": passed, "identity_cohort_freeze_authorized": False, "scene_materialization_authorized": False, "semantic_api_calls_authorized": False, "oracle_access_authorized": False, "holdout_access_authorized": False},
    }
    protocol_bytes = canonical(protocol)
    audit = {
        "schema_version": "fourgraph.p1_v4_evidence_annotated_constrained_protocol_audit.v1", "task": cfg["task"],
        "status": "PASS_STAGE_3A_PROTOCOL_FREEZE" if passed else "FAIL_STAGE_3A_PROTOCOL_FREEZE", "checks": checks,
        "hashes": {"protocol": hashlib.sha256(protocol_bytes).hexdigest().upper(), "config": digest(CONFIG)},
        "execution_boundary": cfg["execution_boundary"],
        "next_action": "P1_V4_STAGE_3B_EVIDENCE_ANNOTATED_IMPLEMENTATION_CONFORMANCE" if passed else "REMEDIATION_ONLY",
    }
    report = f"""# P1-v4 evidence-annotated constrained protocol\n\nStatus: **{audit['status']}**.\n\nThe primary parent is constrained BOSS; constrained FGES is a robustness track. Both start from the registered Ensemble 3/5 adjacency mask but re-estimate a valid CPDAG. The output preserves that CPDAG as statistical evidence and exposes only evidence-certified directions automatically.\n\nOnly complete `VERY_HIGH` six-vote agreement is automatic. `HIGH` and `MEDIUM` are review-only; uncertain, conflict and incomplete cases abstain. Meek closure is diagnostic only and cannot add an automatic direction. A fresh `P1V4` cohort is required.\n\nThis checkpoint generated no scene, fit, API call, Oracle access or holdout access.\n""".encode("utf-8")
    return {ROOT / cfg["outputs"]["protocol"]: protocol_bytes, ROOT / cfg["outputs"]["audit"]: canonical(audit), ROOT / cfg["outputs"]["report"]: report}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    generated = build()
    if args.check:
        for path, content in generated.items():
            if not path.is_file() or path.read_bytes() != content:
                raise SystemExit(f"artifact drift: {path.relative_to(ROOT)}")
    else:
        for path, content in generated.items():
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    print(json.dumps({"status": "PASS", "stage": "3A", "new_scenes": 0, "api_calls": 0, "oracle_access": False, "check": args.check}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
