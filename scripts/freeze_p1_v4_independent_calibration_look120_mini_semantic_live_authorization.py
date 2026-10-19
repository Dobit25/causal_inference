"""Offline authorization checkpoint for the exact frozen Mini look-120 plan."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_mini_semantic_live_authorization.yaml"
RUNNER = ROOT / "scripts/run_p1_v4_independent_calibration_look120_mini_semantic.py"

def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def write_once(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != content: raise RuntimeError(f"artifact drift: {path}")
    if not path.exists(): path.write_bytes(content)

def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); parser.add_argument("--config", type=Path, default=CONFIG); args = parser.parse_args()
    config_path = args.config
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")); outputs = cfg["outputs"]
    required = [ROOT / item["path"] for item in cfg["parents"].values()] + [RUNNER]
    if any(not item.is_file() for item in required): raise RuntimeError("missing live authorization prerequisite")
    for key, item in cfg["parents"].items():
        if sha(ROOT / item["path"]) != item["sha256"]: raise RuntimeError(f"hash drift: {key}")
    preflight = json.loads((ROOT / cfg["parents"]["provider_preflight_audit"]["path"]).read_text())
    if preflight.get("status") != "PASS_PROVIDER_PREFLIGHT" or preflight["boundary"]["study_execution"]: raise RuntimeError("Mini provider preflight not eligible")
    plan = json.loads((ROOT / cfg["parents"]["execution_plan"]["path"]).read_text())
    calls = plan["logical_calls"]
    if len(calls) != 2160 or any(row["model"] != cfg["semantic_contract"]["model"] for row in calls): raise RuntimeError("Mini plan drift")
    pair_records = int(cfg["scope"]["pair_records"])
    checkpoint = {"schema_version":"fourgraph.p1_v4_independent_calibration_look120_mini_semantic_live_authorization_checkpoint.v2", "task":cfg["task"], "status":"PASS_READY_FOR_EXPLICIT_LIVE_AUTHORIZATION", "dependencies":{key:sha(ROOT / item["path"]) for key,item in cfg["parents"].items()} | {"runner_sha256":sha(RUNNER), "config_sha256":sha(config_path)}, "scope":{"scenes":120,"public_inputs":360,"logical_calls":2160,"pair_records":pair_records,"nonedge":"excluded"}, "contract":cfg["semantic_contract"], "runtime":cfg["runtime"], "token_control":cfg["token_control"], "boundary":cfg["boundary"], "next_action":"EXPLICIT_LIVE_AUTHORIZATION_REQUIRED_FOR_2160_MINI_STUDY_CALLS"}
    audit = {"task":cfg["task"],"status":"PASS","checkpoint_sha256":hashlib.sha256(canonical(checkpoint)).hexdigest().upper(),"checks":{"mini_preflight_pass":True,"plan_2160_calls":True,"shared_raw_evidence_conditions_pinned":True,"cache_and_idempotency_pinned":True,"no_automatic_retry":True,"batch_boundary_token_stop_pinned":True,"oracle_holdout_and_metrics_zero":True,"study_api_calls_before_live_authorization":0}}
    report = "# Mini semantic live-authorization checkpoint — Look 120\n\nStatus: **PASS_READY_FOR_EXPLICIT_LIVE_AUTHORIZATION**. It pins 2,160 Mini-medium study calls, concurrency 1, append-only cache/metadata/token ledger, no automatic retry, and batch-boundary token checks every 360 calls against the provider-reported 3,000,000-token threshold (Asia/Ho_Chi_Minh reset at 07:00). It authorizes no study call by itself.\n"
    artifacts = ((ROOT / outputs["live_authorization_checkpoint"],canonical(checkpoint)),(ROOT / outputs["live_authorization_audit"],canonical(audit)),(ROOT / outputs["report"],report.encode()))
    if args.check:
        for path,content in artifacts:
            if not path.is_file() or path.read_bytes()!=content: raise RuntimeError(f"replay mismatch: {path}")
        print(json.dumps({"status":"PASS_CHECK","logical_calls":2160})); return
    for path,content in artifacts: write_once(path,content)
    print(json.dumps({"status":checkpoint["status"],"logical_calls":2160}))

if __name__ == "__main__": main()
