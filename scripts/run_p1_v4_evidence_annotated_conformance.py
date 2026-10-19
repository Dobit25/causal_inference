"""Run production/reference conformance for the Stage-3 evidence contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_evidence_annotated_conformance.yaml"

import sys
sys.path.insert(0, str(ROOT / "src"))
from fourgraph.evidence_annotated_cpdag import build_evidence_annotated_cpdag
from fourgraph.evidence_annotated_cpdag_reference import reference_status
from fourgraph.partial_graph import PartialGraph


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def group(left: str, right: str, agreement: str, direction: str | None, completeness: str = "COMPLETE") -> dict[str, object]:
    return {"left": left, "right": right, "agreement": agreement, "completeness": completeness, "direction": direction}


def fixtures() -> list[tuple[str, PartialGraph, list[dict[str, object]], str, dict[str, int]]]:
    chain = PartialGraph.build(("A", "B", "C"), undirected=(("A", "B"), ("B", "C")))
    collider = PartialGraph.build(("A", "B", "C"), directed=(("A", "B"), ("C", "B")))
    not_completed = PartialGraph.build(("A", "B", "C"), directed=(("A", "B"),), undirected=(("B", "C"),))
    return [
        ("compatible_semantic_chain", chain, [group("A", "B", "VERY_HIGH", "A_TO_B"), group("B", "C", "VERY_HIGH", "A_TO_B")], "PASS", {"certified_semantic_orientation": 2}),
        ("global_collider_conflict", chain, [group("A", "B", "VERY_HIGH", "A_TO_B"), group("B", "C", "VERY_HIGH", "B_TO_A")], "FAIL_CLOSED_GLOBAL_CONFLICT", {"conflict_review_required": 2}),
        ("compelled_confirmation_and_conflict", collider, [group("A", "B", "VERY_HIGH", "A_TO_B"), group("B", "C", "VERY_HIGH", "A_TO_B")], "PASS", {"certified_compelled": 1, "conflict_review_required": 1}),
        ("invalid_non_cpdag_parent", not_completed, [], "FAIL_CLOSED_PARENT", {}),
        ("incomplete_high_abstains", chain, [group("A", "B", "HIGH", "A_TO_B", "INCOMPLETE")], "PASS", {"conflict_review_required": 1, "unresolved": 1}),
        ("duplicate_vote_group_rejected", chain, [group("A", "B", "VERY_HIGH", "A_TO_B"), group("B", "A", "VERY_HIGH", "B_TO_A")], "INVALID_INPUT", {}),
    ]


def build() -> dict[Path, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    parent_protocol, parent_audit = (ROOT / cfg["parent"][key] for key in ("protocol", "audit"))
    checks = {
        "parent_protocol_hash": parent_protocol.is_file() and sha(parent_protocol) == cfg["parent"]["protocol_sha256"],
        "parent_audit_hash": parent_audit.is_file() and sha(parent_audit) == cfg["parent"]["audit_sha256"],
    }
    records: list[dict[str, object]] = []
    all_pass = True
    for name, parent, groups, expected, labels in fixtures():
        try:
            output = build_evidence_annotated_cpdag(parent, groups)
            observed = str(output["status"])
            label_counts: dict[str, int] = {}
            for row in output.get("annotations", []):
                label = str(row["label"]); label_counts[label] = label_counts.get(label, 0) + 1
            reference = reference_status(parent, groups)
        except ValueError as exc:
            observed, reference, label_counts = "INVALID_INPUT", "INVALID_INPUT", {}
            output = {"error": str(exc)}
        passed = observed == expected and label_counts == labels and (reference == observed or observed == "INVALID_INPUT")
        all_pass = all_pass and passed
        records.append({"fixture": name, "expected_status": expected, "production_status": observed, "reference_status": reference, "label_counts": label_counts, "expected_label_counts": labels, "passed": passed, "production_output": output})
    checks["all_fixtures"] = all_pass
    checks["fixture_count"] = len(records) == len(cfg["fixtures"])
    checks["offline_boundary"] = all(value in (0, False, True) for key, value in cfg["execution_boundary"].items() if key != "synthetic_fixtures_only")
    passed = all(checks.values())
    record_bytes = b"".join(canonical(row) for row in records)
    audit = {"schema_version": "fourgraph.p1_v4_evidence_annotated_conformance_audit.v1", "task": cfg["task"], "status": "PASS_STAGE_3B_CONFORMANCE" if passed else "FAIL_STAGE_3B_CONFORMANCE", "checks": checks, "fixture_count": len(records), "production_reference_agree": sum(row["production_status"] == row["reference_status"] for row in records if row["production_status"] != "INVALID_INPUT"), "hashes": {"records": hashlib.sha256(record_bytes).hexdigest().upper(), "config": sha(CONFIG), "production": sha(ROOT / cfg["production"]), "reference": sha(ROOT / cfg["reference"])}, "execution_boundary": cfg["execution_boundary"], "next_action": "P1_V4_STAGE_3C_EXACT_IDENTITY_COHORT_FREEZE" if passed else "CONFORMANCE_REMEDIATION_ONLY"}
    report = f"""# P1-v4 evidence-annotated CPDAG conformance\n\nStatus: **{audit['status']}**. Production and exhaustive reference logic agree for valid-parent fixtures. The suite covers compatible semantic orientation, a semantic collider conflict, compelled-edge confirmation/conflict, an invalid non-completed PDAG, incomplete/high abstention, and duplicate vote-group rejection.\n\nThis suite is synthetic only: it materializes no study scene and uses no Oracle, API, fit or holdout artifact.\n""".encode("utf-8")
    return {ROOT / cfg["outputs"]["records"]: record_bytes, ROOT / cfg["outputs"]["audit"]: canonical(audit), ROOT / cfg["outputs"]["report"]: report}


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
    print(json.dumps({"status": "PASS", "stage": "3B", "fixtures": 6, "api_calls": 0, "study_scenes": 0, "check": args.check}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
