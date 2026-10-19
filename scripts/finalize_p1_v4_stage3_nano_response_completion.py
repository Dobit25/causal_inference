"""Audit logical completion after the single authorized Nano retry."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results/raw/p1_v4_stage3_method_development_cau/semantic/raw_responses.jsonl"
PLAN = ROOT / "data/manifests/p1_v4_stage3_shared_semantic_execution_plan_cau.json"
OUT = ROOT / "data/manifests/p1_v4_stage3_nano_response_completion_audit.json"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    plan = json.loads(PLAN.read_text(encoding="utf-8")); expected = {row["logical_id"] for row in plan["logical_calls"]}
    rows = [json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows: by_id[row["logical_id"]].append(row)
    terminal = {"completed_valid", "completed_pair_invalid", "completed_schema_invalid"}
    selected: dict[str, dict[str, Any]] = {}
    for logical_id, attempts in by_id.items():
        successful = [row for row in attempts if row.get("status") in terminal]
        if successful:
            selected[logical_id] = max(successful, key=lambda row: int(row.get("attempt", 0)))
    status = "PASS_LOGICAL_COMPLETION" if set(by_id) == expected and set(selected) == expected and len(rows) == 361 else "FAIL_LOGICAL_COMPLETION"
    audit = {"schema_version": "fourgraph.p1_v4_stage3_nano_response_completion_audit.v1", "task": "P1_V4_STAGE_3D_NANO_RESPONSE_COMPLETION",
             "status": status, "planned_logical_calls": len(expected), "raw_attempt_records": len(rows), "unique_logical_calls": len(by_id),
             "selected_terminal_responses": len(selected), "historical_transport_outcome_unknown_records": sum(row.get("error_type") == "TransportOutcomeUnknown" for row in rows),
             "retry_completed_responses": sum(row.get("logical_id") == "P1V4SD010/partial/P1" and row.get("attempt") == 1 and row.get("status") in terminal for row in rows),
             "selected_statuses": dict(Counter(row["status"] for row in selected.values())), "raw_responses_sha256": sha(RAW), "execution_plan_sha256": sha(PLAN),
             "oracle_access": 0, "holdout_access": 0, "metrics": 0}
    OUT.write_bytes(canonical(audit)); print(json.dumps(audit, ensure_ascii=False, indent=2)); return 0 if status.startswith("PASS") else 1


if __name__ == "__main__": raise SystemExit(main())
