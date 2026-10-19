"""Record the user's explicit 2,160-call authorization with today's 1,080-call slice."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_mini_semantic_live_authorization_v3.yaml"

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()
def canonical(value: object) -> bytes: return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",", ":"))+"\n").encode()

def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")); outputs = cfg["outputs"]
    checkpoint = ROOT / outputs["live_authorization_checkpoint"]
    audit = ROOT / outputs["live_authorization_audit"]
    if not checkpoint.is_file() or not audit.is_file(): raise RuntimeError("live authorization checkpoint/audit missing")
    cp = json.loads(checkpoint.read_text()); au = json.loads(audit.read_text())
    if cp.get("status") != "PASS_READY_FOR_EXPLICIT_LIVE_AUTHORIZATION" or au.get("status") != "PASS": raise RuntimeError("checkpoint not eligible")
    artifact = {"schema_version":"fourgraph.p1_v4_independent_calibration_look120_mini_semantic_live_authorization.v1", "task":"P1_V4_INDEPENDENT_CALIBRATION_LOOK120_MINI_SEMANTIC_LIVE_AUTHORIZATION", "status":"PASS_LIVE_AUTHORIZED", "explicit_user_live_authorization":True, "checkpoint_sha256":sha(checkpoint), "checkpoint_audit_sha256":sha(audit), "config_sha256":sha(CONFIG), "authorized_logical_calls":2160, "execution_slice":{"max_new_calls":1080,"batch_size":360,"batches":3,"remaining_calls_not_authorized_today":1080}, "contract":{"model":"gpt-5.4-mini-2026-03-17","reasoning_effort":"medium","truncation":"disabled","automatic_chunking":"forbidden"}, "boundary":{"oracle_access":0,"holdout_access":0,"statistical_reruns":0,"metric_calculation":False,"closure":"forbidden"}, "retry":{"automatic_transport_retry":False,"validation_retry":False,"separate_authorization_required":True}, "next_action":"EXECUTE_AT_MOST_1080_NEW_LOGICAL_CALLS_THEN_STOP"}
    out = ROOT / outputs["live_authorization"]
    out.parent.mkdir(parents=True,exist_ok=True)
    payload=canonical(artifact)
    if out.exists() and out.read_bytes()!=payload: raise RuntimeError("live authorization artifact drift")
    if not out.exists(): out.write_bytes(payload)
    print(json.dumps({"status":artifact["status"],"authorized_logical_calls":2160,"today_max_new_calls":1080,"authorization_sha256":sha(out)}))

if __name__ == "__main__": main()
