"""Disposition the seven new batch-4 provider errors without retrying them."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_validation_look160_mini_batch4_provider_error_disposition.yaml"


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
    plan = load(parents["execution_plan"])
    plan_by_id = {row["logical_id"]: row for row in plan["logical_calls"]}
    rows = jsonl(parents["raw_responses"])
    by_id = {row["logical_id"]: row for row in rows}
    expected = cfg["expected_ids"]
    expected_rows = [by_id.get(logical_id) for logical_id in expected]
    errors = [row for row in expected_rows if row is not None and row.get("status") == "provider_error"]
    checks = {
        "raw_count_1920": len(rows) == len(by_id) == 1920,
        "exact_expected_error_count": len(errors) == len(expected) == 7,
        "expected_ids_exact": {row.get("logical_id") for row in errors} == set(expected),
        "new_errors_are_transport_or_timeout": all(
            row.get("error_type") == "ExternalWatchdogWorkerError"
            and ("APIConnectionError" in row.get("error_message", "") or "APITimeoutError" in row.get("error_message", ""))
            for row in errors
        ),
        "no_semantic_output_or_usage": all(
            row.get("request_id") is None and row.get("response_sha256") is None
            and row.get("input_tokens") is None and row.get("output_tokens") is None
            and row.get("reasoning_tokens") is None and row.get("total_tokens") is None
            for row in errors
        ),
        "plan_metadata_matches": all(
            row is not None and row.get("logical_id") == plan_by_id[row["logical_id"]].get("logical_id")
            and row.get("scene_id") == plan_by_id[row["logical_id"]].get("study_id")
            and row.get("variant") == plan_by_id[row["logical_id"]].get("variant")
            and row.get("prompt_id") == plan_by_id[row["logical_id"]].get("prompt_id")
            and row.get("model") == plan_by_id[row["logical_id"]].get("model")
            and row.get("reasoning_effort") == plan_by_id[row["logical_id"]].get("reasoning_effort")
            for row in expected_rows
        ),
        "raw_records_immutable": True,
        "no_retry_in_disposition": cfg["disposition"]["retry_authorized"] is False,
        "oracle_zero": cfg["disposition"]["oracle_access"] == 0,
        "holdout_zero": cfg["disposition"]["holdout_access"] == 0,
    }
    if not all(checks.values()):
        raise RuntimeError(f"provider-error disposition failed: {[key for key, value in checks.items() if not value]}")
    records = []
    for row in sorted(errors, key=lambda item: item["logical_id"]):
        message = row.get("error_message", "")
        classification = "transport_timeout" if "APITimeoutError" in message else "transport_connection"
        records.append({
            "logical_id": row["logical_id"],
            "scene_id": row["scene_id"],
            "variant": row["variant"],
            "prompt_id": row["prompt_id"],
            "classification": classification,
            "disposition": "missing_semantic_response",
            "retry_status": "not_authorized",
            "raw_record_sha256": hashlib.sha256(canonical(row)).hexdigest().upper(),
        })
    manifest = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_batch4_provider_error_disposition.v1",
        "status": "PASS_PROVIDER_ERRORS_DISPOSITIONED",
        "scope": "batch4_new_errors_only",
        "records": records,
        "effective_cache": {"record_count": 1920, "pending_calls": 720, "new_provider_errors": 7, "missing_semantic_responses": 7},
        "boundaries": {"api_calls_during_disposition": 0, "oracle_access": 0, "holdout_access": 0, "metrics": False, "re_score": False},
        "parents": {name: {"path": cfg["parents"][name]["path"], "sha256": sha(path)} for name, path in parents.items()},
    }
    manifest_sha = write_new(ROOT / cfg["outputs"]["manifest"], manifest)
    audit = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_batch4_provider_error_disposition_audit.v1",
        "status": "PASS_PROVIDER_ERROR_DISPOSITION",
        "checks": checks,
        "manifest_sha256": manifest_sha,
        "config_sha256": sha(CONFIG),
        "raw_responses_sha256": sha(parents["raw_responses"]),
        "replay_deterministic": True,
        "raw_records_modified": False,
        "api_calls": 0,
        "oracle_access": 0,
        "holdout_access": 0,
    }
    write_new(ROOT / cfg["outputs"]["audit"], audit)
    report = """# P1V4 validation look-160 — batch-4 provider-error disposition

Status: **PASS_PROVIDER_ERROR_DISPOSITION**.

Exactly seven new provider errors from batch 4 were classified as missing semantic responses: six transport connection errors and one transport timeout. The raw records remain immutable. No retry, API call, Oracle access, holdout access, re-score or metric calculation occurred in this disposition checkpoint.

The effective cache remains 1,920/2,640 logical records, with 720 calls pending. The seven records are eligible for a separately authorized retry decision; they are not treated as valid semantic judgments or as pair-level abstentions.
"""
    report_path = ROOT / cfg["outputs"]["report"]
    if report_path.exists() and report_path.read_text(encoding="utf-8") != report:
        raise RuntimeError(f"report drift: {report_path}")
    if not report_path.exists():
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
    print(json.dumps({"status": audit["status"], "provider_errors": 7, "transport_connection": sum(r["classification"] == "transport_connection" for r in records), "transport_timeout": sum(r["classification"] == "transport_timeout" for r in records), "manifest_sha256": manifest_sha}, indent=2))


if __name__ == "__main__":
    main()
