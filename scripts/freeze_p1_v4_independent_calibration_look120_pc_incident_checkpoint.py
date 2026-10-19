"""Freeze a forensic-only checkpoint for the Phase-D PC validation incident.

This script deliberately never instantiates Tetrad, R, or a study scene.  It
only records the evidence already written by the stopped runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_pc_incident_checkpoint.yaml"
ERROR = ROOT / "results/raw/p1_v4_independent_calibration/look120/statistical/errors/D823FF5FBE1D32979100E7E9185DEF94468A04F7569B8966F6A911FFB51B7DAC.json"
OUT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_pc_incident_checkpoint.json"
AUDIT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_pc_incident_checkpoint_audit.json"
REPORT = ROOT / "reports/p1_v4_independent_calibration_look120_pc_incident_checkpoint.md"
RAW = ROOT / "results/raw/p1_v4_independent_calibration/look120/statistical/raw"
NORM = ROOT / "results/raw/p1_v4_independent_calibration/look120/statistical/normalized"
RUNNER = ROOT / "scripts/run_p1_v4_independent_calibration_look120_statistical.py"
PLAN = ROOT / "data/manifests/p1_v4_independent_calibration_look120_statistical_parent_plan.json"
AUTH = ROOT / "data/manifests/p1_v4_independent_calibration_look120_statistical_execution_authorization.json"


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def tree_digest(folder: Path) -> tuple[int, str]:
    rows = []
    for path in sorted(folder.glob("*.json")):
        rows.append({"name": path.name, "sha256": sha(path)})
    return len(rows), hashlib.sha256(canonical(rows)).hexdigest().upper()


def write_exact(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise RuntimeError(f"artifact drift: {path.relative_to(ROOT)}")
        return
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)


def build() -> tuple[dict, dict, str]:
    for required in (CONFIG, ERROR, RUNNER, PLAN, AUTH):
        if not required.is_file():
            raise RuntimeError(f"missing required evidence: {required.relative_to(ROOT)}")
    error = json.loads(ERROR.read_text(encoding="utf-8"))
    expected = {
        "algorithm": "PC",
        "execution_id": "D823FF5FBE1D32979100E7E9185DEF94468A04F7569B8966F6A911FFB51B7DAC",
        "scene_id": "P1V4SC307",
        "repetition": 0,
    }
    if {key: error["job"][key] for key in expected} != expected:
        raise RuntimeError("incident identity mismatch")
    if error["error_type"] != "ValueError" or error["error"] != "PDAG has no consistent DAG extension":
        raise RuntimeError("incident error mismatch")
    raw_count, raw_digest = tree_digest(RAW)
    norm_count, norm_digest = tree_digest(NORM)
    raw_for_incident = RAW / f"{expected['execution_id']}.json"
    norm_for_incident = NORM / f"{expected['execution_id']}.json"
    checkpoint = {
        "task": "P1_V4_INDEPENDENT_CALIBRATION_LOOK120_PC_INCIDENT_CHECKPOINT",
        "status": "PASS_FORENSIC_CHECKPOINT",
        "disposition": "INDETERMINATE_REQUIRES_SEPARATE_REPLAY_AUTHORIZATION",
        "incident": error,
        "classification": {
            "pc_graph_validity": "NOT_DETERMINABLE_FROM_FROZEN_EVIDENCE",
            "adapter_validator_disagreement": "NOT_DETERMINABLE_FROM_FROZEN_EVIDENCE",
            "execution_plumbing": "OBSERVABILITY_DEFECT_RAW_PREVALIDATION_GRAPH_NOT_PERSISTED",
            "phase_d_status": "SUSPENDED_FAIL_CLOSED",
        },
        "frozen_evidence": {
            "config": {"path": str(CONFIG.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(CONFIG)},
            "runner": {"path": str(RUNNER.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(RUNNER)},
            "plan": {"path": str(PLAN.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(PLAN)},
            "authorization": {"path": str(AUTH.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(AUTH)},
            "error": {"path": str(ERROR.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(ERROR)},
            "partial_execution": {
                "raw_records": raw_count,
                "normalized_records": norm_count,
                "raw_tree_sha256": raw_digest,
                "normalized_tree_sha256": norm_digest,
                "incident_raw_present": raw_for_incident.is_file(),
                "incident_normalized_present": norm_for_incident.is_file(),
            },
        },
        "boundary": {
            "statistical_fits_executed_by_checkpoint": 0,
            "execution_resumed": False,
            "adapter_or_validator_modified": False,
            "semantic_api_calls": 0,
            "oracle_access": 0,
            "holdout_access": 0,
        },
        "required_next_authorization": "ISOLATED_PC_REPLAY_WITH_PREVALIDATION_RAW_CAPTURE",
    }
    audit = {
        "task": checkpoint["task"],
        "status": "PASS",
        "incident_identity_verified": True,
        "raw_prevalidation_graph_available": False,
        "validity_classification_determined": False,
        "no_execution_or_scientific_access": True,
        "checkpoint_sha256": hashlib.sha256(canonical(checkpoint)).hexdigest().upper(),
    }
    report = """# PC incident checkpoint — calibration look 120\n\nStatus: **forensic checkpoint pass; Phase D remains suspended fail-closed.**\n\nThe stopped PC job is `P1V4SC307`, execution identity\n`D823FF5FBE1D32979100E7E9185DEF94468A04F7569B8966F6A911FFB51B7DAC`.\nIt recorded `ValueError: PDAG has no consistent DAG extension`.\n\nThe current runner validates the parsed PC graph before persisting its raw or\nnormalized artifact. Therefore the incident graph itself is absent: frozen\nevidence cannot distinguish a genuinely non-CPDAG PC output from an adapter or\nvalidator disagreement. This is an execution-observability defect, not a\nscientific finding and not a justification to alter PC parameters.\n\nNo fits were replayed, no adapter/validator changed, and no semantic API,\nOracle, or holdout was accessed. A separately authorized isolated replay that\ncaptures the pre-validation graph is required before Phase D may resume.\n"""
    return checkpoint, audit, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    checkpoint, audit, report = build()
    if args.check:
        if not (OUT.is_file() and AUDIT.is_file() and REPORT.is_file()):
            raise SystemExit("checkpoint artifacts not frozen")
        if OUT.read_bytes() != canonical(checkpoint) or AUDIT.read_bytes() != canonical(audit) or REPORT.read_text(encoding="utf-8") != report:
            raise SystemExit("checkpoint replay mismatch")
        print(json.dumps({"status": "PASS_CHECK", "disposition": checkpoint["disposition"]}))
        return
    write_exact(OUT, canonical(checkpoint))
    write_exact(AUDIT, canonical(audit))
    write_exact(REPORT, report.encode("utf-8"))
    print(json.dumps({"status": checkpoint["status"], "disposition": checkpoint["disposition"]}))


if __name__ == "__main__":
    main()
