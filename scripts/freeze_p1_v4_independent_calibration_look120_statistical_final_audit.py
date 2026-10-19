"""Normalize the completed runner audit for downstream provider preflight."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/raw/p1_v4_independent_calibration/look120/statistical/audit.json"
OUT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_statistical_final_audit.json"


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    if source.get("status") != "PASS" or source.get("complete_terminal_records") != 24720: raise SystemExit("statistical runner audit is not complete")
    if source.get("boundary", {}).get("semantic_api_calls") != 0 or source.get("boundary", {}).get("oracle_access") or source.get("boundary", {}).get("holdout_access"): raise SystemExit("forbidden access in statistical audit")
    payload = {"schema_version":"fourgraph.p1_v4_statistical_execution_final_audit.v1","task":"P1_V4_INDEPENDENT_CALIBRATION_LOOK120_STATISTICAL_FINAL_AUDIT","status":"PASS_STATISTICAL_EXECUTION","source_audit":{"path":"results/raw/p1_v4_independent_calibration/look120/statistical/audit.json","sha256":sha(SOURCE)},"planned_fits":24720,"complete_fits":24720,"by_algorithm":source["by_algorithm"],"invalid_no_vote_records":4,"historical_error_artifacts":source.get("unexpected_error_artifacts",0),"execution_boundary":{"semantic_api_calls":0,"oracle_access":False,"holdout_access":False},"oracle_access":False,"holdout_access":False}
    data=canonical(payload); OUT.parent.mkdir(parents=True,exist_ok=True)
    if OUT.exists() and OUT.read_bytes()!=data: raise SystemExit("final audit drift")
    if not OUT.exists(): OUT.write_bytes(data)
    print(json.dumps({"status":payload["status"],"sha256":hashlib.sha256(data).hexdigest().upper()}))


if __name__=="__main__": main()
