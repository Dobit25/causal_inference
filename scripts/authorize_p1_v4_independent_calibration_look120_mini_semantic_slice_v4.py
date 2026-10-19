"""Freeze and record the separately authorized 540-call Mini calibration slice."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_mini_semantic_live_authorization_v4.yaml"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    plan_path = ROOT / cfg["parents"]["execution_plan"]["path"]
    if sha(plan_path) != cfg["parents"]["execution_plan"]["sha256"]:
        raise RuntimeError("execution plan hash drift")
    v3_auth = ROOT / cfg["parents"]["v3_live_authorization"]["path"]
    if sha(v3_auth) != cfg["parents"]["v3_live_authorization"]["sha256"]:
        raise RuntimeError("V3 authorization hash drift")

    cache_root = ROOT / cfg["runtime"]["cache_root"]
    raw_path = cache_root / "raw_responses.jsonl"
    ledger_path = cache_root / "token_ledger.jsonl"
    raw_rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ledger_rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    raw_ids = [row.get("logical_id") for row in raw_rows]
    if len(raw_rows) != 1080 or len(set(raw_ids)) != 1080 or any(not isinstance(item, str) for item in raw_ids):
        raise RuntimeError("expected exactly 1,080 unique cached logical calls")
    if any(row.get("status") == "provider_error" for row in raw_rows):
        raise RuntimeError("provider incident must be dispositioned before a new slice")
    if len(ledger_rows) != 1080 or {row.get("logical_id") for row in ledger_rows} != set(raw_ids):
        raise RuntimeError("raw/ledger identity mismatch")

    plan = load_json(plan_path)
    plan_ids = [row["logical_id"] for row in plan["logical_calls"]]
    if len(plan_ids) != 2160 or len(set(plan_ids)) != 2160 or plan_ids[:1080] != raw_ids:
        raise RuntimeError("cached calls are not the frozen initial plan prefix")
    selected = plan_ids[1080:1620]
    if len(selected) != 540:
        raise RuntimeError("expected exactly 540 newly authorized calls")

    paths = cfg["outputs"]
    checkpoint = {
        "schema_version": "fourgraph.p1_v4_mini_semantic_slice_authorization_checkpoint.v1",
        "task": cfg["task"], "status": "PASS_READY_FOR_EXPLICIT_LIVE_AUTHORIZATION",
        "prior_cache": {"raw_response_sha256": sha(raw_path), "token_ledger_sha256": sha(ledger_path), "recorded_calls": 1080},
        "selected_new_logical_calls": selected,
        "selected_new_logical_calls_sha256": hashlib.sha256(canonical(selected)).hexdigest().upper(),
        "selected_new_count": 540, "remaining_after_slice": 540,
        "oracle_access": 0, "holdout_access": 0, "semantic_contract_changed": False,
        "provider_calls_before_authorization": 0,
    }
    audit = {
        "task": cfg["task"], "status": "PASS", "cache_records": len(raw_rows),
        "ledger_records": len(ledger_rows), "selected_new_count": len(selected),
        "unique_selected": len(set(selected)), "overlap_with_cache": len(set(selected) & set(raw_ids)),
        "oracle_access": 0, "holdout_access": 0,
    }
    for key, artifact in (("live_authorization_checkpoint", checkpoint), ("live_authorization_audit", audit)):
        path = ROOT / paths[key]; path.parent.mkdir(parents=True, exist_ok=True); payload = canonical(artifact)
        if path.exists() and path.read_bytes() != payload:
            raise RuntimeError(f"{key} drift")
        if not path.exists():
            path.write_bytes(payload)

    auth = {
        "schema_version": "fourgraph.p1_v4_mini_semantic_slice_authorization.v1",
        "task": cfg["task"], "status": "PASS_LIVE_AUTHORIZED", "explicit_user_live_authorization": True,
        "checkpoint_sha256": sha(ROOT / paths["live_authorization_checkpoint"]),
        "checkpoint_audit_sha256": sha(ROOT / paths["live_authorization_audit"]),
        "config_sha256": sha(CONFIG), "authorized_logical_calls": 2160,
        "execution_slice": {"max_new_calls": 540, "authorized_pending_logical_ids": selected,
                            "authorized_pending_logical_ids_sha256": hashlib.sha256(canonical(selected)).hexdigest().upper(),
                            "remaining_calls_not_authorized": 540},
        "contract": {"model": "gpt-5.4-mini-2026-03-17", "reasoning_effort": "medium", "truncation": "disabled", "automatic_chunking": "forbidden"},
        "boundary": {"oracle_access": 0, "holdout_access": 0, "statistical_reruns": 0, "metric_calculation": False, "closure": "forbidden"},
        "retry": {"automatic_transport_retry": False, "validation_retry": False, "separate_authorization_required": True},
        "next_action": "EXECUTE_EXACTLY_THE_PINNED_540_NEW_LOGICAL_CALLS_THEN_STOP",
    }
    out = ROOT / paths["live_authorization"]; payload = canonical(auth)
    if out.exists() and out.read_bytes() != payload:
        raise RuntimeError("live authorization drift")
    if not out.exists():
        out.write_bytes(payload)
    print(json.dumps({"status": auth["status"], "selected_new_count": 540, "authorization_sha256": sha(out)}, indent=2))


if __name__ == "__main__":
    main()
