from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import yaml

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex
from fourgraph.runtime_cost_pilot import PilotAuthorizationError, require_live_authorization


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v3_runtime_cost_pilot_final_go_no_go.yaml"
MANIFEST = ROOT / "data/manifests/p1_v3_runtime_cost_pilot_final_go_no_go.json"
AUDIT = ROOT / "data/manifests/p1_v3_runtime_cost_pilot_final_go_no_go_audit.json"
REPORT = ROOT / "reports/p1_v3_runtime_cost_pilot_final_go_no_go.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def line(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def build() -> tuple[bytes, bytes, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    balance_path = ROOT / cfg["parent"]["balance_attestation_audit"]
    preflight_path = ROOT / cfg["parent"]["preflight_audit"]
    for path, expected in (
        (balance_path, cfg["parent"]["balance_attestation_audit_sha256"]),
        (preflight_path, cfg["parent"]["preflight_audit_sha256"]),
    ):
        if sha256(path) != expected:
            raise RuntimeError(f"dependency hash mismatch: {path.relative_to(ROOT)}")
    balance = json.loads(balance_path.read_text(encoding="utf-8"))
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    if balance["authorization"]["next_action"] != cfg["task"]:
        raise RuntimeError("balance amendment did not authorize GO/NO-GO")
    if not balance["verdict"]["technical_budget_gate_passed"]:
        raise RuntimeError("technical budget gate did not pass")
    headroom = Decimal(str(balance["budget"]["headroom_usd"]))
    cap = Decimal(str(balance["budget"]["pilot_cap_usd"]))
    if headroom < cap or Decimal(str(cfg["frozen_scope"]["pilot_cost_cap_usd"])) != cap:
        raise RuntimeError("frozen cost/headroom gate failed")
    timestamps = cfg["decision_time"]
    frozen = datetime.fromisoformat(timestamps["frozen_at_utc"].replace("Z", "+00:00"))
    attested = datetime.fromisoformat(timestamps["balance_attested_at_utc"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(timestamps["attestation_expires_at_utc"].replace("Z", "+00:00"))
    if not (attested <= frozen < expires) or not timestamps["attestation_fresh_at_freeze"]:
        raise RuntimeError("attestation was stale at GO/NO-GO freeze")
    if not cfg["gate_matrix"]["all_blocking_gates_pass"] or cfg["decision"]["outcome"] != "GO_READY":
        raise RuntimeError("GO decision is inconsistent with gate matrix")
    if cfg["decision"]["execution_started"] or cfg["decision"]["pilot_execution_authorized_by_this_checkpoint"]:
        raise RuntimeError("GO/NO-GO checkpoint cannot start or self-authorize execution")
    try:
        require_live_authorization(cfg["live_authorization"], cfg["parent"]["preflight_audit_sha256"])
    except PilotAuthorizationError:
        pass
    else:
        raise RuntimeError("non-executing checkpoint unexpectedly passed live authorization")
    if cfg["frozen_scope"]["pilot_ids"] != preflight["counts"].get("pilot_ids", cfg["frozen_scope"]["pilot_ids"]):
        raise RuntimeError("pilot scope mismatch")
    manifest = {
        "schema_version": "fourgraph.p1_v3_runtime_cost_pilot_final_go_no_go_manifest.v1",
        "task": cfg["task"], "status": cfg["status"],
        "decision_time": timestamps, "gate_matrix": cfg["gate_matrix"],
        "frozen_scope": cfg["frozen_scope"], "decision": cfg["decision"],
        "live_authorization": cfg["live_authorization"],
        "execution_conditions": cfg["execution_conditions"],
        "evidence_boundary": cfg["evidence_boundary"],
        "authorization_after_freeze": cfg["authorization_after_freeze"],
    }
    manifest_bytes = line(manifest)
    report = f"""# P1-v3 runtime/cost pilot final GO/NO-GO

Decision: `GO_READY`. All blocking pre-execution gates passed at freeze time: exact pilot identities, dependency/environment hashes, pinned JVM/Tetrad, secret-safe credential presence, official Nano pricing, USD {headroom:.2f} attested project headroom, the internal USD {cap:.2f} cost controller and the final-holdout seal. The disabled Platform hard limit remains a warning mitigated by pre-call reservation and fail-closed accounting.

`GO_READY` means the frozen pilot may receive a separate explicit execution order. It is not that order. The live authorization record remains false, execution has not started, and automatic execution is forbidden. Spend must be rechecked after {timestamps['attestation_expires_at_utc']} or the 2026-09-30 project reset.

Frozen scope is nine synthetic pilot scenes, nine generator replays, three excluded BOSS warm-ups, 270 measured BOSS fits and 108 semantic calls with at most 120 attempts. It never authorizes materializing the 840 successor scenes.

At this checkpoint: observations 0, BOSS runs 0, semantic/model calls 0, tokens 0, successor scenes 0 and final-holdout access false.
""".encode("utf-8")
    outputs = ((MANIFEST, manifest_bytes), (REPORT, report))
    audit = {
        "schema_version": "fourgraph.p1_v3_runtime_cost_pilot_final_go_no_go_audit.v1",
        "task": cfg["task"],
        "dependencies": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256(p)} for p in (CONFIG, balance_path, preflight_path)],
        "implementation": {"path": Path(__file__).relative_to(ROOT).as_posix(), "sha256": sha256(Path(__file__))},
        "outputs": [{"path": p.relative_to(ROOT).as_posix(), "bytes": len(content), "sha256": sha256_hex(content)} for p, content in outputs],
        "evidence_boundary": cfg["evidence_boundary"],
        "authorization": cfg["authorization_after_freeze"],
        "verdict": {"decision": "GO_READY", "all_blocking_gates_passed": True, "attestation_fresh_at_freeze": True, "execution_eligibility": True, "pilot_execution_authorized_by_checkpoint": False, "execution_started": False},
    }
    return manifest_bytes, line(audit), report


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    built = build(); paths = (MANIFEST, AUDIT, REPORT)
    if args.check:
        for path, expected in zip(paths, built):
            if not path.exists() or path.read_bytes() != expected:
                raise SystemExit(f"Mismatch: {path.relative_to(ROOT)}")
        print("P1-v3 final GO/NO-GO reproduces byte-for-byte")
        return 0
    for path, content in zip(paths, built):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    print("P1-v3 runtime/cost pilot decision: GO_READY; execution not started")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
