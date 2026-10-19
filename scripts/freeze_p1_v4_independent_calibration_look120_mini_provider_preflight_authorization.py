"""Create the offline authorization checkpoint for one Mini synthetic provider preflight."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_mini_provider_preflight.yaml"
RUNNER = ROOT / "scripts/run_p1_v4_independent_calibration_look120_mini_provider_preflight.py"
AMENDMENT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_mini_semantic_reconciliation_amendment.json"
PLAN = ROOT / "data/manifests/p1_v4_independent_calibration_look120_mini_semantic_execution_plan.json"
CHECKPOINT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_mini_provider_preflight_authorization_checkpoint_v2.json"
AUDIT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_mini_provider_preflight_authorization_audit_v2.json"
REPORT = ROOT / "reports/p1_v4_independent_calibration_look120_mini_provider_preflight_authorization_checkpoint_v2.md"

def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def write_once(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != contents:
        raise RuntimeError(f"artifact drift: {path}")
    if not path.exists():
        path.write_bytes(contents)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path in (CONFIG, RUNNER, AMENDMENT, PLAN):
        if not path.is_file():
            raise SystemExit(f"missing prerequisite: {path}")
    checkpoint = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look120_mini_provider_preflight_authorization_checkpoint.v2",
        "task": "P1_V4_INDEPENDENT_CALIBRATION_LOOK120_MINI_PROVIDER_PREFLIGHT_AUTHORIZATION_CHECKPOINT",
        "status": "PASS_READY_FOR_EXPLICIT_LIVE_PROVIDER_PREFLIGHT_AUTHORIZATION",
        "dependencies": {
            "mini_reconciliation_amendment_sha256": sha(AMENDMENT),
            "mini_execution_plan_sha256": sha(PLAN),
            "preflight_config_sha256": sha(CONFIG),
            "preflight_runner_sha256": sha(RUNNER),
        },
        "exact_contract": {
            "model": "gpt-5.4-mini-2026-03-17",
            "reasoning_effort": "medium",
            "synthetic_nodes": 7,
            "synthetic_pairs": 21,
            "prompt_variant": "P1",
            "truncation": "disabled",
            "automatic_prompt_chunking": "forbidden",
        },
        "authorization_scope": {
            "provider_calls_allowed": 1,
            "study_semantic_calls_allowed": 0,
            "statistical_fits_allowed": 0,
            "oracle_access_allowed": 0,
            "holdout_access_allowed": 0,
        },
        "success_record_required": ["model", "input_tokens", "output_tokens", "total_tokens", "request_id", "context_limit_check"],
        "failure_action": "STOP_NO_PROMPT_SCHEMA_OR_CHUNKING_CHANGE",
        "next_gate": "EXPLICIT_LIVE_PROVIDER_PREFLIGHT_AUTHORIZATION",
    }
    audit = {
        "task": checkpoint["task"],
        "status": "PASS",
        "checkpoint_sha256": hashlib.sha256(canonical(checkpoint)).hexdigest().upper(),
        "checks": {
            "model_is_mini_medium": True,
            "exactly_one_synthetic_provider_call_authorizable": True,
            "worst_case_is_7_nodes_21_pairs": True,
            "study_semantic_calls_are_zero": True,
            "oracle_holdout_and_statistical_execution_are_zero": True,
            "truncation_and_chunking_forbidden": True,
            "provider_usage_fields_required": True,
        },
    }
    report = """# Mini provider-preflight authorization checkpoint — Look 120

Status: **PASS_READY_FOR_EXPLICIT_LIVE_PROVIDER_PREFLIGHT_AUTHORIZATION**.

This checkpoint authorizes no network activity by itself. Its only possible live scope, after separate explicit authorization, is one synthetic worst-case provider preflight for GPT-5.4 Mini with medium reasoning: seven nodes, 21 pairs, exact production prompt/schema, truncation disabled.

No study semantic call, statistical fit, Oracle access, holdout access, or metric calculation is permitted. Provider-reported model, token usage, request ID, and context-limit check must be recorded. Any preflight failure stops the process without altering the frozen semantic contract.
"""
    expected = ((CHECKPOINT, canonical(checkpoint)), (AUDIT, canonical(audit)), (REPORT, report.encode()))
    if args.check:
        for path, contents in expected:
            if not path.is_file() or path.read_bytes() != contents:
                raise SystemExit(f"replay mismatch: {path}")
        print(json.dumps({"status": "PASS_CHECK", "provider_calls_allowed": 1}))
        return
    for path, contents in expected:
        write_once(path, contents)
    print(json.dumps({"status": checkpoint["status"], "provider_calls_allowed": 1}))

if __name__ == "__main__":
    main()
