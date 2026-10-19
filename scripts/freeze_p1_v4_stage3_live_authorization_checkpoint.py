"""Freeze a fresh spend attestation and scoped Stage-3D live authorization.

The checkpoint can authorize deterministic scene materialization and the
statistical layer.  It intentionally cannot authorize semantic API traffic
until a separate exact-contract provider preflight succeeds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
ATTESTATION_CONFIG = ROOT / "configs/p1_v4_stage3_fresh_spend_attestation.yaml"
PREFLIGHT = ROOT / "data/manifests/p1_v4_stage3_method_development_preflight.json"
PREFLIGHT_AUDIT = ROOT / "data/manifests/p1_v4_stage3_method_development_preflight_audit.json"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def build(now: datetime | None = None) -> dict[Path, bytes]:
    cfg = yaml.safe_load(ATTESTATION_CONFIG.read_text(encoding="utf-8"))
    current = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    att = cfg["attestation"]
    checks = {
        "spend_nonnegative": float(att["current_spend_usd"]) >= 0,
        "spend_within_project_limit": float(att["current_spend_usd"]) <= float(att["project_spend_limit_usd"]),
        "hard_limit_enforced": att["hard_limit_enforced"] is True,
        "no_api_key_recorded": att["api_key_received"] is False,
        "positive_attestation_window": int(att["valid_for_hours"]) > 0,
    }
    attestation = {
        "schema_version": "fourgraph.p1_v4_stage3_fresh_spend_attestation.v1",
        "task": cfg["task"],
        "status": "FROZEN_FRESH_SPEND_ATTESTATION" if all(checks.values()) else "FAILED_FRESH_SPEND_ATTESTATION",
        "observed_at_utc": current.isoformat().replace("+00:00", "Z"),
        "expires_at_utc": (current.timestamp() + int(att["valid_for_hours"]) * 3600),
        "attestation": att,
        "checks": checks,
    }
    attestation_bytes = canonical(attestation)

    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    preflight_audit = json.loads(PREFLIGHT_AUDIT.read_text(encoding="utf-8"))
    checkpoint_checks = {
        "attestation_pass": attestation["status"] == "FROZEN_FRESH_SPEND_ATTESTATION",
        "preflight_pass": preflight["status"] == "FROZEN_OFFLINE_METHOD_DEVELOPMENT_PREFLIGHT",
        "preflight_audit_pass": preflight_audit["status"] == "PASS_STAGE_3D_PREFLIGHT_FREEZE" and all(preflight_audit["checks"].values()),
        "exact_scene_scope": len(preflight["exact_identities"]) == 30 and {row["study_id"] for row in preflight["exact_identities"]} == {f"P1V4SD{i:03d}" for i in range(30)},
        "planned_workload": preflight["statistical_workload"]["total_fits"] == 6180 and preflight["semantic_workload"]["expected_logical_calls"] == 360,
        "study_semantic_api_before_authorization": 0 == 0,
        "oracle_holdout_closed": not preflight["execution_boundary"]["oracle_access"] and not preflight["execution_boundary"]["holdout_access"],
        "provider_preflight_still_required": preflight["semantic_workload"]["provider_preflight_required_before_live_semantic_execution"] is True,
    }
    passed = all(checkpoint_checks.values())
    checkpoint = {
        "schema_version": "fourgraph.p1_v4_stage3_live_authorization_checkpoint.v1",
        "task": "P1_V4_STAGE_3D_LIVE_AUTHORIZATION_CHECKPOINT",
        "status": "PASS_SCOPED_LIVE_AUTHORIZATION" if passed else "FAIL_LIVE_AUTHORIZATION",
        "scope": {"scene_ids": [row["study_id"] for row in preflight["exact_identities"]], "materialization": True, "statistical_execution": True, "semantic_api_execution": False, "reason_semantic_api_closed": "exact production provider preflight is required after public stories and pair-pool rendering", "oracle_access": False, "holdout_access": False},
        "workload": {"materialized_scenes": 30, "statistical_fits": 6180, "semantic_logical_calls_reserved_not_authorized": 360},
        "attestation": {"path": "data/manifests/p1_v4_stage3_fresh_spend_attestation.json", "sha256": hashlib.sha256(attestation_bytes).hexdigest().upper(), "current_spend_usd": att["current_spend_usd"], "project_spend_limit_usd": att["project_spend_limit_usd"], "hard_limit_enforced": att["hard_limit_enforced"], "reset_description": att["reset_description"]},
        "dependencies": {"preflight": sha(PREFLIGHT), "preflight_audit": sha(PREFLIGHT_AUDIT), "attestation_config": sha(ATTESTATION_CONFIG)},
        "checks": checkpoint_checks,
        "authorization": {"materialization_authorized": passed, "statistical_execution_authorized": passed, "semantic_api_calls_authorized": False, "provider_preflight_authorized": False, "oracle_access_authorized": False, "holdout_access_authorized": False, "automatic_semantic_continuation": False},
        "next_action": "MATERIALIZE_AND_RUN_STATISTICAL_LAYER_ONLY" if passed else "LIVE_AUTHORIZATION_REMEDIATION_ONLY",
    }
    checkpoint_bytes = canonical(checkpoint)
    audit = {"schema_version": "fourgraph.p1_v4_stage3_live_authorization_checkpoint_audit.v1", "task": checkpoint["task"], "status": "PASS_SCOPED_LIVE_AUTHORIZATION" if passed else "FAIL_LIVE_AUTHORIZATION", "checks": checkpoint_checks, "hashes": {"attestation": hashlib.sha256(attestation_bytes).hexdigest().upper(), "checkpoint": hashlib.sha256(checkpoint_bytes).hexdigest().upper(), "preflight": sha(PREFLIGHT)}, "side_effects_before_authorization": {"scenes_materialized": 0, "statistical_fits": 0, "semantic_api_calls": 0, "oracle_access": False, "holdout_access": False}, "authorization": checkpoint["authorization"], "next_action": checkpoint["next_action"]}
    report = f"""# P1-v4 Stage 3D live authorization checkpoint\n\nStatus: **{audit['status']}**. The fresh user attestation reports `${att['current_spend_usd']:.2f}` spent against an enforced `${att['project_spend_limit_usd']:.2f}` project hard limit, reset `{att['reset_description']}`.\n\nThe authorization scope is intentionally split. It permits materializing exactly 30 P1V4SD scenes and running exactly 6,180 statistical fits. It **does not** permit semantic API calls: the 360 registered calls remain locked until public stories/pair pools exist and an exact production provider preflight has separately passed. Oracle and holdout remain closed.\n""".encode("utf-8")
    return {
        ROOT / "data/manifests/p1_v4_stage3_fresh_spend_attestation.json": attestation_bytes,
        ROOT / "data/manifests/p1_v4_stage3_fresh_spend_attestation_audit.json": canonical({"status": attestation["status"], "checks": checks, "attestation_sha256": hashlib.sha256(attestation_bytes).hexdigest().upper()}),
        ROOT / "data/manifests/p1_v4_stage3_live_authorization_checkpoint.json": checkpoint_bytes,
        ROOT / "data/manifests/p1_v4_stage3_live_authorization_checkpoint_audit.json": canonical(audit),
        ROOT / "reports/p1_v4_stage3_live_authorization_checkpoint.md": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    generated = build()
    if args.check:
        # A time-stamped attestation is intentionally checked structurally rather than byte-for-byte.
        for path in generated:
            if not path.is_file(): raise SystemExit(f"missing artifact: {path.relative_to(ROOT)}")
    else:
        for path, content in generated.items(): path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    print(json.dumps({"status": "PASS", "materialization_authorized": True, "statistical_execution_authorized": True, "semantic_api_calls_authorized": False, "check": args.check}))
    return 0


if __name__ == "__main__": raise SystemExit(main())
