"""Freeze one explicit retry per each of the seven batch-4 provider errors."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_validation_look160_mini_batch4_provider_retry.yaml"
RUNNER = ROOT / "scripts/run_p1_v4_validation_look160_mini_batch4_provider_retry.py"


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) if path.suffix in {".yaml", ".yml"} else json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"mapping expected: {path}")
    return value


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_new(path: Path, value: object) -> str:
    body = canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != body:
        raise RuntimeError(f"artifact drift: {path}")
    if not path.exists():
        path.write_bytes(body)
    return hashlib.sha256(body).hexdigest().upper()


def main() -> None:
    cfg = load(CONFIG)
    parents = {name: ROOT / item["path"] for name, item in cfg["parents"].items()}
    for name, path in parents.items():
        if sha(path) != cfg["parents"][name]["sha256"]:
            raise RuntimeError(f"{name} hash drift")
    raw = jsonl(parents["raw_responses"])
    by_id = {row["logical_id"]: row for row in raw}
    ids = cfg["retry_scope"]["logical_ids"]
    rows = [by_id.get(logical_id) for logical_id in ids]
    checks = {
        "exact_raw_count": len(raw) == len(by_id) == 1920,
        "exact_retry_scope": len(ids) == 7 and len(set(ids)) == 7,
        "all_ids_present": all(row is not None for row in rows),
        "all_ids_are_provider_errors": all(row is not None and row.get("status") == "provider_error" for row in rows),
        "no_semantic_output_or_usage": all(row is not None and row.get("request_id") is None and row.get("response_sha256") is None and row.get("total_tokens") is None for row in rows),
        "one_attempt_only": cfg["retry_scope"]["maximum_attempts_per_logical_id"] == 1,
        "original_error_overwrite_forbidden": cfg["retry_scope"]["overwrite_original_error"] == "forbidden",
        "hard_token_stop": cfg["token_control"]["hard_stop_tokens"] == 3_000_000,
        "hard_spend_stop": cfg["spend_control"]["project_hard_stop_usd"] == 18.0 and cfg["spend_control"]["hard_limit_enforced"] is True,
        "oracle_holdout_locked": cfg["boundary"]["oracle_access"] is False and cfg["boundary"]["holdout_access"] is False,
        "metric_closure_locked": cfg["boundary"]["metric_calculation"] is False and cfg["boundary"]["closure"] == "forbidden",
        "retry_artifacts_not_created": not any((ROOT / cfg["runtime"][key]).exists() for key in ("retry_overlay", "retry_attempts", "retry_token_ledger")),
    }
    if not all(checks.values()):
        raise RuntimeError(f"retry authorization failed: {[key for key, value in checks.items() if not value]}")
    checkpoint = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_batch4_provider_retry_checkpoint.v1",
        "status": "PASS_READY_NOT_EXECUTED",
        "checks": checks,
        "config_sha256": sha(CONFIG),
        "runner_sha256": sha(RUNNER),
        "parents": {name: {"path": cfg["parents"][name]["path"], "sha256": sha(path)} for name, path in parents.items()},
        "retry_scope": {"logical_ids": ids, "maximum_attempts_per_logical_id": 1},
        "oracle_access": 0,
        "holdout_access": 0,
    }
    checkpoint_sha = write_new(ROOT / cfg["outputs"]["authorization_checkpoint"], checkpoint)
    authorization = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_batch4_provider_retry_authorization.v1",
        "status": "PASS_LIVE_AUTHORIZED",
        "explicit_user_live_authorization": True,
        "user_authorization_scope": "exactly one retry per seven batch-4 provider errors",
        "checkpoint_sha256": checkpoint_sha,
        "logical_ids": ids,
        "maximum_attempts_per_logical_id": 1,
        "retry_overlay_only": True,
        "overwrite_original_error": False,
        "oracle_access": 0,
        "holdout_access": 0,
    }
    authorization_sha = write_new(ROOT / cfg["outputs"]["authorization"], authorization)
    audit = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_batch4_provider_retry_authorization_audit.v1",
        "status": "PASS_RETRY_AUTHORIZATION",
        "checks": checks,
        "config_sha256": sha(CONFIG),
        "checkpoint_sha256": checkpoint_sha,
        "authorization_sha256": authorization_sha,
        "authorized_retry_calls": 7,
        "executed_retry_calls": 0,
        "api_calls": 0,
        "oracle_access": 0,
        "holdout_access": 0,
    }
    write_new(ROOT / cfg["outputs"]["authorization_audit"], audit)
    print(json.dumps({"status": audit["status"], "authorized_retry_calls": 7, "authorization_sha256": authorization_sha}, indent=2))


if __name__ == "__main__":
    main()
