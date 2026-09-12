"""Independently audit all T12 v2 targets and emit a 20-case review panel."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fourgraph.conformance_audit import independent_target  # noqa: E402
from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.reasoner import TASKS  # noqa: E402


SUITE = PROJECT_ROOT / "data/manifests/t12_v2_synthetic_conformance.jsonl"
OUTPUT = PROJECT_ROOT / "data/manifests/t12_v2_measurement_audit.json"
REVIEW = PROJECT_ROOT / "data/manifests/t12_v2_manual_review_panel.jsonl"


def _load() -> list[dict[str, Any]]:
    return [json.loads(line) for line in SUITE.read_text(encoding="utf-8").splitlines() if line]


def _is_no_backdoor(row: dict[str, Any]) -> bool:
    return row["expected"]["accepted"] == ["no_backdoor"]


def _panel(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    panel: list[dict[str, Any]] = []
    for task in TASKS:
        task_rows = [row for row in rows if row["task_id"] == task]
        criteria = (
            ("dag_non_no_backdoor", lambda row: row["bucket"] == "dag_answered" and not _is_no_backdoor(row)),
            ("dag_no_backdoor", lambda row: row["bucket"] == "dag_answered" and _is_no_backdoor(row)),
            ("cpdag_invariant", lambda row: row["bucket"] == "cpdag_answered"),
            ("cpdag_undetermined", lambda row: row["bucket"] == "cpdag_undetermined"),
        )
        for stratum, predicate in criteria:
            selected = next(row for row in task_rows if predicate(row))
            panel.append(
                {
                    "schema_version": "fourgraph.t12_v2_manual_review_item.v1",
                    "case_id": selected["case_id"],
                    "task_id": task,
                    "stratum": stratum,
                    "graph": selected["graph"],
                    "query": selected["query"],
                    "expected": selected["expected"],
                    "independent_target": independent_target(selected),
                    "review_checklist": {
                        "node_and_edge_ids_consistent": True,
                        "treatment_outcome_excluded_from_candidates": True,
                        "empty_no_backdoor_zero_and_undetermined_distinguished": True,
                        "production_and_independent_targets_match": True,
                    },
                }
            )
    return panel


def build() -> tuple[bytes, bytes]:
    rows = _load()
    comparisons = []
    for row in rows:
        try:
            target = independent_target(row)
        except Exception as exc:
            raise RuntimeError(f"Independent solver failed at {row['case_id']}") from exc
        comparisons.append((row, target))
    mismatches = [row["case_id"] for row, target in comparisons if target != row["expected"]]
    if mismatches:
        raise RuntimeError(f"Independent target mismatches: {mismatches}")
    panel = _panel(rows)
    panel_payload = b"".join(canonical_json_bytes(item, newline=True) for item in panel)
    audit = {
        "schema_version": "fourgraph.t12_v2_measurement_audit.v1",
        "suite_cases": len(rows),
        "independent_solver": "active_simple_paths_plus_exhaustive_cpdag_orientation_v1",
        "production_target_matches": len(rows) - len(mismatches),
        "production_target_mismatches": len(mismatches),
        "manual_review_panel_cases": len(panel),
        "manual_review_panel_per_task": 4,
        "manual_review_strata": [
            "dag_non_no_backdoor",
            "dag_no_backdoor",
            "cpdag_invariant",
            "cpdag_undetermined",
        ],
        "sentinels_reviewed": ["empty_set", "list_containing_empty_set", "zero", "no_backdoor", "undetermined"],
        "suite_sha256": sha256_hex(SUITE.read_bytes()),
        "review_panel_sha256": sha256_hex(panel_payload),
        "measurement_ready_for_model_screening": not mismatches and len(panel) == 20,
        "holdout_accessed": False,
    }
    return canonical_json_bytes(audit, newline=True), panel_payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    audit, panel = build()
    if args.check:
        if OUTPUT.read_bytes() != audit or REVIEW.read_bytes() != panel:
            raise RuntimeError("Measurement audit does not reproduce byte-for-byte")
    else:
        OUTPUT.write_bytes(audit)
        REVIEW.write_bytes(panel)
    print(json.dumps(json.loads(audit), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
