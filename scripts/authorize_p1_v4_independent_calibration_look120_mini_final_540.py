"""Record explicit authorization for the final frozen 540-call Mini slice."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_mini_semantic_live_authorization_v5.yaml"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")); outputs = cfg["outputs"]
    checkpoint = ROOT / outputs["live_authorization_checkpoint"]
    audit = ROOT / outputs["live_authorization_audit"]
    cp = json.loads(checkpoint.read_text(encoding="utf-8")); au = json.loads(audit.read_text(encoding="utf-8"))
    if cp.get("status") != "PASS_READY_FOR_EXPLICIT_LIVE_AUTHORIZATION" or au.get("status") != "PASS":
        raise RuntimeError("checkpoint is not eligible")
    selected = cp.get("selected_new_logical_calls")
    if not isinstance(selected, list) or len(selected) != 540 or len(set(selected)) != 540:
        raise RuntimeError("frozen final logical IDs invalid")
    artifact = {"schema_version": "fourgraph.p1_v4_mini_final_540_live_authorization.v1", "task": cfg["task"], "status": "PASS_LIVE_AUTHORIZED", "explicit_user_live_authorization": True, "config_sha256": sha(CONFIG), "checkpoint_sha256": sha(checkpoint), "checkpoint_audit_sha256": sha(audit), "authorized_logical_calls": 2160, "execution_slice": {"max_new_calls": 540, "authorized_pending_logical_ids": selected, "authorized_pending_logical_ids_sha256": cp["selected_new_logical_calls_sha256"], "remaining_calls_not_authorized": 0}, "contract": {"model": cfg["semantic_contract"]["model"], "reasoning_effort": cfg["semantic_contract"]["reasoning_effort"], "truncation": "disabled", "automatic_chunking": "forbidden"}, "boundary": {"oracle_access": 0, "holdout_access": 0, "statistical_reruns": 0, "metric_calculation": False, "closure": "forbidden"}, "retry": {"automatic_transport_retry": False, "validation_retry": False, "separate_authorization_required": True}, "next_action": "EXECUTE_EXACTLY_THE_PINNED_FINAL_540_LOGICAL_CALLS_THEN_STOP"}
    path = ROOT / outputs["live_authorization"]; payload = canonical(artifact); path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise RuntimeError("authorization artifact drift")
    if not path.exists():
        path.write_bytes(payload)
    print(json.dumps({"status": artifact["status"], "authorized_new_calls": 540, "authorization_sha256": sha(path)}, indent=2))


if __name__ == "__main__":
    main()
