from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import yaml

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v3_runtime_cost_pilot_balance_attestation.yaml"
MANIFEST = ROOT / "data/manifests/p1_v3_runtime_cost_pilot_balance_attestation.json"
AUDIT = ROOT / "data/manifests/p1_v3_runtime_cost_pilot_balance_attestation_audit.json"
REPORT = ROOT / "reports/p1_v3_runtime_cost_pilot_balance_attestation.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def line(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def build() -> tuple[bytes, bytes, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    parent = ROOT / cfg["parent"]["checkpoint_audit"]
    rate = ROOT / cfg["budget_gate"]["official_rate_card"]
    for path, expected in (
        (parent, cfg["parent"]["checkpoint_audit_sha256"]),
        (rate, cfg["budget_gate"]["official_rate_card_sha256"]),
    ):
        if sha256(path) != expected:
            raise RuntimeError(f"dependency hash mismatch: {path.relative_to(ROOT)}")
    parent_record = json.loads(parent.read_text(encoding="utf-8"))
    if parent_record["authorization"]["next_action"] != cfg["task"]:
        raise RuntimeError("parent checkpoint did not authorize balance attestation")
    att = cfg["attestation"]
    headroom = Decimal(str(att["project_spend_limit_usd"])) - Decimal(str(att["current_project_spend_usd"]))
    if headroom != Decimal(str(att["calculated_headroom_usd"])):
        raise RuntimeError("attested budget arithmetic mismatch")
    gate = cfg["budget_gate"]
    ratio = headroom / Decimal(str(gate["pilot_hard_cap_usd"]))
    if ratio != Decimal(str(gate["headroom_to_cap_ratio"])):
        raise RuntimeError("headroom ratio mismatch")
    if headroom < Decimal(str(gate["minimum_required_headroom_usd"])):
        raise RuntimeError("attested headroom does not cover pilot cap")
    if cfg["readiness"]["execution_authorized"] or cfg["authorization_after_freeze"]["pilot_execution"]:
        raise RuntimeError("balance attestation cannot self-authorize execution")
    if not gate["platform_hard_limit_warning"] or att["hard_limit_enforced"]:
        raise RuntimeError("hard-limit-off risk was not represented correctly")
    manifest = {
        "schema_version": "fourgraph.p1_v3_runtime_cost_pilot_balance_attestation_manifest.v1",
        "task": cfg["task"], "status": cfg["status"],
        "attestation": att, "budget_gate": gate, "readiness": cfg["readiness"],
        "evidence_boundary": cfg["evidence_boundary"],
        "authorization_after_freeze": cfg["authorization_after_freeze"],
    }
    manifest_bytes = line(manifest)
    report = f"""# P1-v3 runtime/cost pilot balance attestation

The user read the `causal_builder` project limits UI on 2026-09-19 and attested current spend USD {att['current_project_spend_usd']:.2f} against a USD {att['project_spend_limit_usd']:.2f} project limit. Exact arithmetic leaves USD {att['calculated_headroom_usd']:.2f}, or {gate['headroom_to_cap_ratio']:.2f} times the frozen USD {gate['pilot_hard_cap_usd']:.2f} pilot cap. No prepaid credits are used; the displayed reset was 11 days away, represented as 2026-09-30.

The budget gate passes, but the platform hard limit is not enforced. The frozen internal pre-call budget controller is therefore mandatory, concurrent project spend remains a risk, and the balance must be rechecked if execution occurs after the reset or more than 24 hours after this attestation.

This amendment records technical budget readiness only. It does not contain an explicit pilot-execution order and cannot authorize itself. No model call, token, observation, Bootstrap/BOSS run, successor scene or holdout access occurred. The next action is a separate final GO/NO-GO checkpoint.
""".encode("utf-8")
    outputs = ((MANIFEST, manifest_bytes), (REPORT, report))
    audit = {
        "schema_version": "fourgraph.p1_v3_runtime_cost_pilot_balance_attestation_audit.v1",
        "task": cfg["task"],
        "dependencies": [
            {"path": p.relative_to(ROOT).as_posix(), "sha256": sha256(p)}
            for p in (CONFIG, parent, rate)
        ],
        "implementation": {"path": Path(__file__).relative_to(ROOT).as_posix(), "sha256": sha256(Path(__file__))},
        "outputs": [
            {"path": p.relative_to(ROOT).as_posix(), "bytes": len(content), "sha256": sha256_hex(content)}
            for p, content in outputs
        ],
        "budget": {"spend_usd": att["current_project_spend_usd"], "limit_usd": att["project_spend_limit_usd"], "headroom_usd": att["calculated_headroom_usd"], "pilot_cap_usd": gate["pilot_hard_cap_usd"]},
        "evidence_boundary": cfg["evidence_boundary"],
        "authorization": cfg["authorization_after_freeze"],
        "verdict": {"user_balance_attested": True, "budget_arithmetic_passed": True, "technical_budget_gate_passed": True, "platform_hard_limit_enforced": False, "pilot_execution_authorized": False},
    }
    return manifest_bytes, line(audit), report


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    built = build(); paths = (MANIFEST, AUDIT, REPORT)
    if args.check:
        for path, expected in zip(paths, built):
            if not path.exists() or path.read_bytes() != expected:
                raise SystemExit(f"Mismatch: {path.relative_to(ROOT)}")
        print("P1-v3 balance attestation reproduces byte-for-byte")
        return 0
    for path, content in zip(paths, built):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    print("P1-v3 balance attested; technical budget gate passed; execution remains forbidden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
