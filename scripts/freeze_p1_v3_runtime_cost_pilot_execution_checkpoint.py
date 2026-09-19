from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex
from fourgraph.runtime_cost_pilot import PilotAuthorizationError, require_live_authorization


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v3_runtime_cost_pilot_execution_checkpoint.yaml"
MANIFEST = ROOT / "data/manifests/p1_v3_runtime_cost_pilot_execution_checkpoint.json"
AUDIT = ROOT / "data/manifests/p1_v3_runtime_cost_pilot_execution_checkpoint_audit.json"
REPORT = ROOT / "reports/p1_v3_runtime_cost_pilot_execution_checkpoint.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def line(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def build() -> tuple[bytes, bytes, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    paths = [
        (ROOT / cfg["parent"]["preflight_audit"], cfg["parent"]["preflight_audit_sha256"]),
        (ROOT / cfg["official_rate_card"]["record"], cfg["official_rate_card"]["record_sha256"]),
        (ROOT / cfg["live_adapter"]["library"], cfg["live_adapter"]["library_sha256"]),
        (ROOT / cfg["live_adapter"]["guarded_entrypoint"], cfg["live_adapter"]["guarded_entrypoint_sha256"]),
    ]
    for path, expected in paths:
        if sha256(path) != expected:
            raise RuntimeError(f"dependency hash mismatch: {path.relative_to(ROOT)}")
    parent = json.loads(paths[0][0].read_text(encoding="utf-8"))
    if parent["authorization"]["next_action"] != cfg["task"]:
        raise RuntimeError("preflight did not authorize this checkpoint")
    rate = json.loads(paths[1][0].read_text(encoding="utf-8"))
    expected_rates = cfg["official_rate_card"]["standard_rates_usd_per_million_tokens"]
    observed = rate["short_context"]
    if observed != {
        "input": expected_rates["uncached_input"],
        "cached_input": expected_rates["cached_input"],
        "output_including_reasoning": expected_rates["output_including_reasoning"],
    } or not rate["verified_from_official_source"]:
        raise RuntimeError("official rate-card gate failed")
    balance = cfg["platform_balance_check"]
    if balance["balance_verified"] or balance["current_platform_balance_usd"] is not None:
        raise RuntimeError("checkpoint falsely claims a verified platform balance")
    if balance["model_request_made"] or balance["token_usage"] != 0:
        raise RuntimeError("balance check crossed the no-model boundary")
    if cfg["decision"]["authorization"] != "DENY_PENDING_BALANCE_VERIFICATION":
        raise RuntimeError("unverified balance must deny authorization")
    try:
        require_live_authorization(cfg["authorization"], cfg["parent"]["preflight_audit_sha256"])
    except PilotAuthorizationError:
        pass
    else:
        raise RuntimeError("frozen DENY authorization unexpectedly passed")
    manifest = {
        "schema_version": "fourgraph.p1_v3_runtime_cost_pilot_execution_checkpoint_manifest.v1",
        "task": cfg["task"], "status": cfg["status"],
        "official_rate_card": cfg["official_rate_card"],
        "platform_balance_check": cfg["platform_balance_check"],
        "live_adapter": cfg["live_adapter"], "decision": cfg["decision"],
        "evidence_boundary": cfg["evidence_boundary"],
        "authorization": cfg["authorization"],
        "authorization_after_freeze": cfg["authorization_after_freeze"],
    }
    manifest_bytes = line(manifest)
    report = b"""# P1-v3 runtime/cost pilot execution-authorization checkpoint

OpenAI's official pricing page was checked and frozen for `gpt-5.4-nano` Standard processing: USD 0.20 per million input tokens, USD 0.02 per million cached-input tokens and USD 1.25 per million output tokens. The official model page confirms snapshot `gpt-5.4-nano-2026-03-17`.

The official organization costs endpoint requires an Admin API key. The repository environment contains only the project-scoped API key; a read-only costs request returned HTTP 403. It made no model request and consumed zero tokens. Therefore current spend/balance cannot be established from the available credential, and the checkpoint must deny pilot execution.

A separate budget-guarded semantic adapter is hash-frozen. It reserves worst-case cost before every call, requires provider usage telemetry, accounts actual token cost and fails closed at the USD 1.50 pilot cap. The guarded entrypoint rejects execution under this checkpoint before any workload starts.

Decision: `DENY_PENDING_BALANCE_VERIFICATION`. The next permissible action is a balance-attestation amendment using a current Platform Usage/Limits reading or an Admin API key kept outside Git. Pilot observations, BOSS runs, semantic calls, successor generation and holdout access remain zero/forbidden.
"""
    outputs = ((MANIFEST, manifest_bytes), (REPORT, report))
    audit = {
        "schema_version": "fourgraph.p1_v3_runtime_cost_pilot_execution_checkpoint_audit.v1",
        "task": cfg["task"],
        "dependencies": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256(p)} for p, _ in paths] + [{"path": CONFIG.relative_to(ROOT).as_posix(), "sha256": sha256(CONFIG)}],
        "implementation": {"path": Path(__file__).relative_to(ROOT).as_posix(), "sha256": sha256(Path(__file__))},
        "outputs": [{"path": p.relative_to(ROOT).as_posix(), "bytes": len(content), "sha256": sha256_hex(content)} for p, content in outputs],
        "evidence_boundary": cfg["evidence_boundary"],
        "authorization": cfg["authorization_after_freeze"],
        "verdict": {"official_rate_verified": True, "platform_balance_verified": False, "live_adapter_frozen": True, "authorization_decision": "DENY_PENDING_BALANCE_VERIFICATION", "pilot_execution_authorized": False},
    }
    return manifest_bytes, line(audit), report


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    built = build(); paths = (MANIFEST, AUDIT, REPORT)
    if args.check:
        for path, expected in zip(paths, built):
            if not path.exists() or path.read_bytes() != expected:
                raise SystemExit(f"Mismatch: {path.relative_to(ROOT)}")
        print("P1-v3 execution-authorization checkpoint reproduces byte-for-byte")
        return 0
    for path, content in zip(paths, built):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    print("P1-v3 execution checkpoint frozen DENY; pilot remains forbidden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
