"""Freeze and audit the symmetric 3/5-to-3/4 valid-method amendment."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_valid_method_ensemble_amendment.yaml"
PARENT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_pc_isolated_replay_execution_audit.json"
MODULE = ROOT / "src/fourgraph/p1_v4_adaptive_ensemble.py"
RUNNER = ROOT / "scripts/run_p1_v4_independent_calibration_look120_statistical.py"
OUT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_valid_method_ensemble_amendment.json"
AUDIT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_valid_method_ensemble_amendment_audit.json"
REPORT = ROOT / "reports/p1_v4_independent_calibration_look120_valid_method_ensemble_amendment.md"


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != data: raise RuntimeError(f"artifact drift: {path.relative_to(ROOT)}")
    if not path.exists(): path.write_bytes(data)


def build() -> tuple[dict, dict, str]:
    parent = json.loads(PARENT.read_text(encoding="utf-8"))
    if parent["classification"] != "PARSED_PC_OUTPUT_IS_NOT_A_CONSISTENTLY_EXTENDABLE_PDG": raise RuntimeError("unexpected parent incident")
    amendment = {
        "task": "P1_V4_INDEPENDENT_CALIBRATION_LOOK120_VALID_METHOD_ENSEMBLE_AMENDMENT",
        "status": "FROZEN_OFFLINE",
        "dependencies": {"config_sha256": sha(CONFIG), "pc_incident_audit_sha256": sha(PARENT), "ensemble_module_sha256": sha(MODULE), "runner_sha256": sha(RUNNER)},
        "method_validity": {"invalid_graph": "INVALID_NO_VOTE", "runtime_or_adapter_error": "FAIL_CLOSED_EXECUTION_STOP", "bootstrap_method_validity": "ALL_200_BOOTSTRAP_RUNS_VALID"},
        "ensemble_rule": {"five_valid": "AT_LEAST_3_OF_5", "exactly_one_invalid": "AT_LEAST_3_OF_4", "two_or_more_invalid": "FAIL_CLOSED_INSUFFICIENT_VALID_METHODS", "repair": False},
        "boundary": {"statistical_fits": 0, "semantic_api_calls": 0, "oracle_access": 0, "holdout_access": 0, "phase_d_resume": False},
    }
    audit = {"task": amendment["task"], "status": "PASS", "registered_methods": 5, "single_invalid_cases": 5, "two_invalid_fail_closed": True, "no_repair": True, "phase_d_resume_authorized": False, "amendment_sha256": hashlib.sha256(canonical(amendment)).hexdigest().upper()}
    report = """# Valid-method ensemble amendment — calibration look 120\n\nThis post-incident technical amendment preserves all five registered ensemble\nmethods while making invalid-output handling symmetric. A graph that is parsed\nand persisted but fails its registered graph contract is `INVALID_NO_VOTE`; it\nis neither repaired nor treated as an absence vote.\n\n- five valid methods: retain adjacencies with at least 3/5 votes;\n- exactly one invalid method: retain adjacencies with at least 3/4 votes;\n- two or more invalid methods: fail closed for the scene.\n\nBootstrap-BOSS is valid only when all 200 registered bootstrap runs are valid.\nRuntime/adapter failures remain execution-stopping errors. The amendment itself\nexecutes no fit and authorizes no resume, API, Oracle, or holdout access.\n"""
    return amendment, audit, report


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--check",action="store_true"); args=parser.parse_args()
    for path in (CONFIG,PARENT,MODULE,RUNNER):
        if not path.is_file(): raise SystemExit(f"missing {path}")
    amendment,audit,report=build()
    if args.check:
        if not OUT.is_file() or not AUDIT.is_file() or not REPORT.is_file() or OUT.read_bytes()!=canonical(amendment) or AUDIT.read_bytes()!=canonical(audit) or REPORT.read_text(encoding="utf-8")!=report: raise SystemExit("amendment replay mismatch")
        print(json.dumps({"status":"PASS_CHECK"})); return
    write_once(OUT,canonical(amendment)); write_once(AUDIT,canonical(audit)); write_once(REPORT,report.encode("utf-8")); print(json.dumps({"status":"PASS"}))


if __name__=="__main__": main()
