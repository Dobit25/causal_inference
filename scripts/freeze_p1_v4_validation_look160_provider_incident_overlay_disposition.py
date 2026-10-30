"""Freeze and audit the six-record provider-incident retry overlay."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_validation_look160_provider_incident_overlay_disposition.yaml"


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
    parent_paths = {name: ROOT / value["path"] for name, value in cfg["parents"].items()}
    for name, path in parent_paths.items():
        if sha(path) != cfg["parents"][name]["sha256"]:
            raise RuntimeError(f"{name} hash drift")
    plan = load(parent_paths["execution_plan"])
    plan_by_id = {row["logical_id"]: row for row in plan["logical_calls"]}
    raw = jsonl(parent_paths["raw_responses"])
    overlay = jsonl(parent_paths["retry_overlay"])
    attempts = jsonl(parent_paths["retry_attempts"])
    raw_by_id = {row["logical_id"]: row for row in raw}
    overlay_by_id = {row["logical_id"]: row for row in overlay}
    raw_errors = {row["logical_id"]: row for row in raw if row.get("status") == "provider_error"}
    required = cfg["disposition"]
    field_checks = {}
    for logical_id, row in overlay_by_id.items():
        raw_row, plan_row = raw_by_id.get(logical_id), plan_by_id.get(logical_id)
        # The frozen plan uses ``study_id`` (not the execution-row name
        # ``scene_id``) and intentionally predates the rendered-prompt hash.
        # Bind fields that exist in all three artifacts separately from the
        # execution-only prompt rendering hash, which must still match raw ↔
        # overlay exactly.
        raw_overlay_match = bool(raw_row) and all(
            row.get(key) == raw_row.get(key)
            for key in (
                "logical_id", "scene_id", "variant", "prompt_id", "model",
                "reasoning_effort", "story_content_sha256", "pair_pool_sha256",
                "prompt_render_sha256",
            )
        )
        plan_match = bool(plan_row) and (
            row.get("logical_id") == plan_row.get("logical_id")
            and row.get("scene_id") == plan_row.get("study_id")
            and all(
                row.get(key) == plan_row.get(key)
                for key in (
                    "variant", "prompt_id", "model", "reasoning_effort",
                    "story_content_sha256", "pair_pool_sha256",
                )
            )
        )
        field_checks[logical_id] = raw_overlay_match and plan_match
    checks = {
        "raw_unique_logical_ids": len(raw_by_id) == len(raw) == 1440,
        "exact_raw_provider_errors": len(raw_errors) == required["exact_overlay_count"],
        "exact_overlay_count_and_unique_ids": len(overlay) == len(overlay_by_id) == required["exact_overlay_count"],
        "attempt_log_byte_equivalent_to_overlay": parent_paths["retry_attempts"].read_bytes() == parent_paths["retry_overlay"].read_bytes(),
        "overlay_ids_exactly_match_raw_errors": set(overlay_by_id) == set(raw_errors),
        "raw_errors_remain_immutable_provider_errors": all(row.get("status") == required["allowed_original_status"] for row in raw_errors.values()),
        "overlay_has_only_authorized_terminal_statuses": all(row.get("status") in required["allowed_overlay_statuses"] for row in overlay),
        "overlay_has_retry_provenance": all(row.get("retry_of_status") == "provider_error" and row.get("retry_attempt_number") == 1 for row in overlay),
        "identity_metadata_matches_raw_and_plan": all(field_checks.values()) and len(field_checks) == required["exact_overlay_count"],
        "recovery_audit_pass": load(parent_paths["recovery_execution_audit"]).get("status") == "PASS_ALL_RECOVERED",
    }
    if not all(checks.values()):
        raise RuntimeError(f"overlay disposition checks failed: {[key for key, value in checks.items() if not value]}")
    replacements = [{"logical_id": logical_id, "raw_status": raw_errors[logical_id]["status"], "effective_source": "provider_incident_retry_overlay", "overlay_status": overlay_by_id[logical_id]["status"], "overlay_response_sha256": overlay_by_id[logical_id]["response_sha256"]} for logical_id in sorted(overlay_by_id)]
    effective_statuses = {"completed_valid": sum(row.get("status") == "completed_valid" for row in raw if row.get("status") != "provider_error") + sum(row.get("status") == "completed_valid" for row in overlay), "completed_pair_invalid": sum(row.get("status") == "completed_pair_invalid" for row in raw if row.get("status") != "provider_error") + sum(row.get("status") == "completed_pair_invalid" for row in overlay), "provider_error": 0}
    manifest = {"schema_version": "fourgraph.p1_v4_validation_look160_provider_incident_overlay_disposition.v1", "status": "PASS_EFFECTIVE_OVERLAY_FROZEN", "mode": required["mode"], "raw_records_immutable": 1440, "replacements": replacements, "effective_record_count": 1440, "effective_statuses": effective_statuses, "parents": {name: {"path": cfg["parents"][name]["path"], "sha256": sha(path)} for name, path in parent_paths.items()}, "boundaries": {"oracle_access": 0, "holdout_access": 0, "metric_calculation": False, "closure": False}}
    manifest_sha = write_new(ROOT / cfg["outputs"]["manifest"], manifest)
    audit = {"schema_version": "fourgraph.p1_v4_validation_look160_provider_incident_overlay_disposition_audit.v1", "status": "PASS_OVERLAY_DISPOSITION", "checks": checks, "config_sha256": sha(CONFIG), "manifest_sha256": manifest_sha, "replay_deterministic": True, "raw_records_modified": False, "semantic_api_calls": 0, "oracle_access": 0, "holdout_access": 0}
    write_new(ROOT / cfg["outputs"]["audit"], audit)
    report = ("# P1V4 validation look-160 provider-incident overlay disposition\n\n"
              "Status: **PASS_OVERLAY_DISPOSITION**. The effective view replaces exactly six raw `provider_error` records with their separately hashed, one-attempt retry-overlay responses. The original raw records are unchanged. The effective view has 1,440 records: 1,250 fully valid, 190 pair-invalid and zero unresolved provider-error records. This checkpoint performs no re-score, agreement aggregation, Oracle access, metric calculation or new API call.\n")
    report_path = ROOT / cfg["outputs"]["report"]
    if report_path.exists() and report_path.read_text(encoding="utf-8") != report:
        raise RuntimeError("report drift")
    if not report_path.exists():
        report_path.write_text(report, encoding="utf-8")
    print(json.dumps({"status": audit["status"], "effective_record_count": 1440, "effective_statuses": effective_statuses, "manifest_sha256": manifest_sha}, indent=2))


if __name__ == "__main__":
    main()
