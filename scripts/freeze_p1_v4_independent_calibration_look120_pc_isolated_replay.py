"""Freeze the non-live authorization checkpoint for one PC forensic replay."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_pc_isolated_replay_amendment.yaml"
PARENT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_pc_incident_checkpoint.json"
RUNNER = ROOT / "scripts/run_p1_v4_independent_calibration_look120_pc_isolated_replay.py"
PLAN = ROOT / "data/manifests/p1_v4_independent_calibration_look120_pc_isolated_replay_plan.json"
AUTH = ROOT / "data/manifests/p1_v4_independent_calibration_look120_pc_isolated_replay_authorization.json"
AUDIT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_pc_isolated_replay_authorization_audit.json"
REPORT = ROOT / "reports/p1_v4_independent_calibration_look120_pc_isolated_replay_amendment.md"


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != data:
        raise RuntimeError(f"artifact drift: {path.relative_to(ROOT)}")
    if not path.exists():
        path.write_bytes(data)


def build() -> tuple[dict, dict, dict, str]:
    parent = json.loads(PARENT.read_text(encoding="utf-8"))
    if parent["disposition"] != "INDETERMINATE_REQUIRES_SEPARATE_REPLAY_AUTHORIZATION":
        raise RuntimeError("wrong parent incident disposition")
    plan = {"task": "P1_V4_INDEPENDENT_CALIBRATION_LOOK120_PC_ISOLATED_REPLAY", "planned_execution_id": "PC_INCIDENT_REPLAY_D823FF5FBE1D32979100E7E9185DEF94468A04F7569B8966F6A911FFB51B7DAC", "statistical_fits": 1, "semantic_api_calls": 0, "oracle_access": 0, "holdout_access": 0, "phase_d_resume": False}
    auth = {"task": "P1_V4_INDEPENDENT_CALIBRATION_LOOK120_PC_ISOLATED_REPLAY_LIVE_AUTHORIZATION", "status": "READY_FOR_EXPLICIT_LIVE_AUTHORIZATION", "dependencies": {"config_sha256": digest(CONFIG), "parent_checkpoint_sha256": digest(PARENT), "runner_sha256": digest(RUNNER)}, "authorization": {"exact_statistical_fits": 1, "semantic_api_calls": False, "oracle_access": False, "holdout_access": False, "phase_d_resume": False}}
    audit = {"task": auth["task"], "status": "PASS", "exactly_one_pc_replay_planned": True, "prevalidation_capture_required": True, "scientific_parameter_change": False, "semantic_api_calls": 0, "oracle_access": 0, "holdout_access": 0, "authorization_status": auth["status"]}
    report = """# Isolated PC replay amendment\n\nThis amendment freezes exactly one forensic PC replay for `P1V4SC307`. It uses the\noriginal frozen PC configuration and data. The replay runner writes the parsed graph\nbefore calling the CPDAG validator, so it can distinguish an invalid Tetrad/PC graph\nfrom a parser/validator disagreement.\n\nThis checkpoint is **not** live authorization. It permits no statistical execution,\nsemantic API call, Oracle/holdout access, or Phase-D resume. A separate explicit\nauthorization is required to invoke `--execute`.\n"""
    return plan, auth, audit, report


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    for path in (CONFIG, PARENT, RUNNER):
        if not path.is_file(): raise SystemExit(f"missing {path}")
    plan, auth, audit, report = build()
    if args.check:
        if not all(path.is_file() for path in (PLAN, AUTH, AUDIT, REPORT)): raise SystemExit("artifacts not frozen")
        if PLAN.read_bytes()!=canonical(plan) or AUTH.read_bytes()!=canonical(auth) or AUDIT.read_bytes()!=canonical(audit) or REPORT.read_text(encoding="utf-8")!=report: raise SystemExit("replay mismatch")
        print(json.dumps({"status":"PASS_CHECK","live_status":auth["status"]})); return
    write_once(PLAN, canonical(plan)); write_once(AUTH, canonical(auth)); write_once(AUDIT, canonical(audit)); write_once(REPORT, report.encode("utf-8"))
    print(json.dumps({"status":"PASS","live_status":auth["status"]}))


if __name__ == "__main__": main()
