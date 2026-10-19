"""Freeze the final 540-call authorization checkpoint after approved transport recovery."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_mini_semantic_live_authorization_v5.yaml"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_once(path: Path, value: object) -> None:
    payload = canonical(value); path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise RuntimeError(f"artifact drift: {path}")
    if not path.exists():
        path.write_bytes(payload)


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")); parents = cfg["parents"]
    for value in parents.values():
        path = ROOT / value["path"]
        if not path.is_file() or sha(path) != value["sha256"]:
            raise RuntimeError(f"parent hash drift: {value['path']}")
    root = ROOT / cfg["runtime"]["cache_root"]
    raw_path = root / "raw_responses.jsonl"; retry_path = ROOT / cfg["runtime"]["transport_retry_overlay"]["path"]
    if sha(retry_path) != cfg["runtime"]["transport_retry_overlay"]["sha256"]:
        raise RuntimeError("retry overlay hash drift")
    raw = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    retry = [json.loads(line) for line in retry_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    raw_ids = [row.get("logical_id") for row in raw]
    retry_ids = [row.get("logical_id") for row in retry]
    if len(raw) != 1620 or len(set(raw_ids)) != 1620 or len(retry) != 2:
        raise RuntimeError("cache/retry cardinality mismatch")
    if [row.get("status") for row in raw if row.get("status") == "provider_error"] != ["provider_error", "provider_error"]:
        raise RuntimeError("historical provider incident drift")
    if set(retry_ids) != {"P1V4SC237/full/P6", "P1V4SC237/partial/P1"} or any(row.get("status") == "provider_error" for row in retry):
        raise RuntimeError("transport recovery not resolved")
    plan_path = ROOT / parents["execution_plan"]["path"]
    plan = json.loads(plan_path.read_text(encoding="utf-8")); plan_ids = [row["logical_id"] for row in plan["logical_calls"]]
    if plan_ids[:1620] != raw_ids or len(plan_ids) != 2160:
        raise RuntimeError("cached prefix does not match frozen execution plan")
    selected = plan_ids[1620:];
    if len(selected) != 540:
        raise RuntimeError("final authorization must contain exactly 540 IDs")
    outputs = cfg["outputs"]
    checkpoint = {"schema_version": "fourgraph.p1_v4_mini_final_540_authorization_checkpoint.v1", "task": cfg["task"], "status": "PASS_READY_FOR_EXPLICIT_LIVE_AUTHORIZATION", "cached_historical_records": 1620, "resolved_transport_retries": retry_ids, "selected_new_logical_calls": selected, "selected_new_logical_calls_sha256": hashlib.sha256(canonical(selected)).hexdigest().upper(), "selected_new_count": 540, "oracle_access": 0, "holdout_access": 0, "semantic_contract_changed": False, "study_api_calls_in_checkpoint": 0}
    audit = {"task": cfg["task"], "status": "PASS", "raw_cache_records": len(raw), "retry_records": len(retry), "final_pending_count": len(selected), "unique_final_pending": len(set(selected)), "overlap_with_existing": len(set(selected) & set(raw_ids)), "oracle_access": 0, "holdout_access": 0, "semantic_api_calls": 0}
    write_once(ROOT / outputs["live_authorization_checkpoint"], checkpoint)
    write_once(ROOT / outputs["live_authorization_audit"], audit)
    report = "# P1V4 Mini final-540 authorization checkpoint\n\nPASS: 1,620 recorded logical calls plus two separately resolved no-usage transport retries; exactly 540 logical calls remain. This checkpoint does not authorize those 540 calls.\n"
    rp = ROOT / outputs["report"]; rp.parent.mkdir(parents=True, exist_ok=True)
    if rp.exists() and rp.read_text(encoding="utf-8") != report:
        raise RuntimeError("report drift")
    if not rp.exists(): rp.write_text(report, encoding="utf-8")
    print(json.dumps({"status": checkpoint["status"], "final_pending_count": 540, "checkpoint_sha256": sha(ROOT / outputs["live_authorization_checkpoint"]), "audit_sha256": sha(ROOT / outputs["live_authorization_audit"])}, indent=2))


if __name__ == "__main__":
    main()
