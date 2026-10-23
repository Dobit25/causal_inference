"""Record explicit authorization for exactly 200 calibration Oracle commitments."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/p1_v4_look200_cumulative_oracle_scoring_live_authorization.yaml"


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def build() -> tuple[dict, dict[Path, bytes]]:
    config = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    for name, spec in config["parents"].items():
        path = ROOT / spec["path"]
        checks[f"parent_{name}"] = path.is_file() and sha256(path) == spec["sha256"]
    freeze = json.loads((ROOT / config["parents"]["execution_freeze"]["path"]).read_text(encoding="utf-8"))
    freeze_audit = json.loads((ROOT / config["parents"]["execution_freeze_audit"]["path"]).read_text(encoding="utf-8"))
    scope = config["authorization"]
    checks.update(
        {
            "freeze_ready": freeze.get("status") == "PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION",
            "freeze_audit_pass": freeze_audit.get("status") == "PASS",
            "exact_200": len(freeze.get("exact_scene_ids", [])) == 200 and scope["exact_calibration_scenes"] == 200,
            "explicit": scope["explicit_user_authorization"] is True,
            "boundary": scope["semantic_api_calls"] == 0
            and scope["statistical_reruns"] == 0
            and not scope["validation_access"]
            and not scope["holdout_access"]
            and scope["closure"] == "forbidden",
        }
    )
    passed = all(checks.values())
    authorization = {
        "schema_version": "fourgraph.p1_v4_look200_cumulative_oracle_scoring_live_authorization.v1",
        "task": config["task"],
        "status": "AUTHORIZED_CALIBRATION_LOOK200_ORACLE_SCORING" if passed else "FAIL",
        "explicit_user_authorization": True,
        "execution_freeze_sha256": sha256(ROOT / config["parents"]["execution_freeze"]["path"]),
        "scope": {
            "exact_scene_ids": freeze["exact_scene_ids"],
            "parent_conditions": ["Constrained-BOSS", "Constrained-FGES"],
            "certification_variants": ["full", "partial"],
            "ambiguous_diagnostic_scope": "first_120_only",
        },
        "permitted": [
            "reconstruct_200_registered_calibration_oracle_commitments",
            "calculate_registered_cumulative_look200_metrics",
            "apply_registered_sequential_decision_rule",
        ],
        "forbidden": [
            "semantic_api",
            "statistical_rerun",
            "validation_or_holdout",
            "meek_closure",
            "threshold_or_policy_tuning",
        ],
    }
    authorization_bytes = canonical_bytes(authorization)
    audit = {
        "schema_version": "fourgraph.p1_v4_look200_cumulative_oracle_scoring_live_authorization_audit.v1",
        "task": config["task"],
        "status": "PASS" if passed else "FAIL",
        "checks": checks,
        "authorization_sha256": hashlib.sha256(authorization_bytes).hexdigest().upper(),
        "oracle_access_before_execution": 0,
        "semantic_api_calls": 0,
        "statistical_reruns": 0,
        "validation_access": 0,
        "holdout_access": 0,
    }
    artifacts = {
        ROOT / config["outputs"]["authorization"]: authorization_bytes,
        ROOT / config["outputs"]["audit"]: canonical_bytes(audit),
    }
    return audit, artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    audit, artifacts = build()
    for path, payload in artifacts.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != payload:
                raise RuntimeError(f"authorization replay drift: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    print(json.dumps(audit, indent=2))
    return 0 if audit["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
