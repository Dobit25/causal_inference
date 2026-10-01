"""Phase C verification for the P1-v3 statistical ensemble.

The verifier is fail-closed and does not materialize scenes, run discovery,
load Oracle data, or call an API. It records environment failures so Phase D
cannot accidentally start on an unverified machine.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1v3_statistical_ensemble_phase_c_verification.yaml"
PHASE_AB_AUDIT = ROOT / "data/manifests/p1v3_statistical_ensemble_phase_ab_audit.json"
PHASE_AB_SCRIPT = ROOT / "scripts/build_p1v3_statistical_ensemble_phase_ab.py"
JAR = ROOT / "data/raw/t05/py-tetrad/pytetrad/resources/tetrad-current.jar"
AUDIT = ROOT / "data/manifests/p1v3_statistical_ensemble_phase_c_verification_audit.json"
REPORT = ROOT / "reports/p1v3_statistical_ensemble_phase_c_readiness.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def run_version(executable: str, args: list[str]) -> dict[str, Any]:
    path = shutil.which(executable)
    if not path:
        return {"available": False, "executable": executable}
    try:
        proc = subprocess.run([path, *args], capture_output=True, text=True, timeout=15)
    except Exception as exc:  # pragma: no cover - defensive environment guard
        return {"available": False, "executable": path, "error": str(exc)}
    return {
        "available": proc.returncode == 0,
        "executable": path,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def fixture_smoke() -> dict[str, Any]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.run(
        [sys.executable, str(PHASE_AB_SCRIPT), "--check"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    result: dict[str, Any] = {"returncode": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}
    result["passed"] = proc.returncode == 0
    return result


def execute() -> dict[str, Any]:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    phase_ab = json.loads(PHASE_AB_AUDIT.read_text(encoding="utf-8"))
    python_info = {
        "version": platform.python_version(),
        "executable": sys.executable,
        "expected": str(config["requirements"]["python"]),
        "exact_match": platform.python_version() == str(config["requirements"]["python"]),
    }
    java_info = run_version("java", ["-version"])
    r_info = run_version("Rscript", ["--version"])
    bnlearn_info: dict[str, Any] = {"verified": False, "reason": "Rscript unavailable"}
    if r_info.get("available"):
        probe = subprocess.run(
            [r_info["executable"], "-e", "cat(as.character(packageVersion('bnlearn')))"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        version = probe.stdout.strip()
        bnlearn_info = {
            "verified": probe.returncode == 0 and version == str(config["requirements"]["bnlearn"]),
            "observed_version": version,
            "required_version": str(config["requirements"]["bnlearn"]),
            "returncode": probe.returncode,
            "stderr": probe.stderr.strip(),
        }
    jar_info = {
        "path": str(JAR.relative_to(ROOT)).replace("\\", "/"),
        "exists": JAR.is_file(),
        "observed_sha256": sha256(JAR) if JAR.is_file() else None,
        "required_sha256": config["requirements"]["tetrad_jar_sha256"],
        "hash_match": JAR.is_file() and sha256(JAR) == config["requirements"]["tetrad_jar_sha256"],
    }
    # Tetrad cannot be considered executable if Java is absent, even when its
    # immutable jar hash is correct.
    tetrad_info = {"jar": jar_info, "runtime_available": bool(java_info.get("available") and jar_info["hash_match"])}
    token_info = dict(phase_ab["token_preflight"])
    token_info["provider_tokenizer_verified"] = False
    token_info["passed"] = False
    token_info["reason"] = "Provider tokenizer/context envelope has not been verified offline"
    smoke = fixture_smoke()
    checks = {
        "r_bnlearn": bool(r_info.get("available") and bnlearn_info.get("verified")),
        "python": python_info["exact_match"],
        "java_tetrad": tetrad_info["runtime_available"],
        "token_preflight": token_info["passed"],
        "fixture_smoke": smoke["passed"],
    }
    all_pass = all(checks.values())
    audit = {
        "schema_version": "fourgraph.p1_v3_statistical_ensemble_phase_c_verification_audit.v1",
        "task": config["task"],
        "status": "PASS_EXECUTION_READY" if all_pass else "STOP_ENVIRONMENT_OR_TOKEN_VERIFICATION_FAILED",
        "checks": checks,
        "python": python_info,
        "java": java_info,
        "rscript": r_info,
        "bnlearn": bnlearn_info,
        "tetrad": tetrad_info,
        "token_preflight": token_info,
        "fixture_smoke": smoke,
        "evidence_boundary": {
            "study_scene_materialization": 0,
            "observations_loaded": False,
            "statistical_fits": 0,
            "semantic_api_calls": 0,
            "oracle_accessed": False,
            "holdout_accessed": False,
        },
        "phase_d_authorized": all_pass,
        "phase_e_authorized": all_pass,
    }
    AUDIT.write_bytes(canonical(audit))
    failed = [name for name, passed in checks.items() if not passed]
    report = f"""# P1-v3 Phase C — execution-readiness report

## Verdict

**{'PASS — ready for separate execution authorization' if all_pass else 'STOP — do not start Phase D/E'}**

Failed checks: `{', '.join(failed) if failed else 'none'}`.

## Checks

| Check | Result |
|---|---|
| R + bnlearn | {'PASS' if checks['r_bnlearn'] else 'FAIL'} |
| Python exact version | {'PASS' if checks['python'] else 'FAIL'} |
| Java + Tetrad | {'PASS' if checks['java_tetrad'] else 'FAIL'} |
| Provider token preflight | {'PASS' if checks['token_preflight'] else 'FAIL/PENDING'} |
| End-to-end offline fixture | {'PASS' if checks['fixture_smoke'] else 'FAIL'} |

Observed Python: `{python_info['version']}` (required `{python_info['expected']}`).
Observed Tetrad JAR hash: `{jar_info['observed_sha256']}`; hash match: `{jar_info['hash_match']}`.
Rscript available: `{r_info.get('available', False)}`; bnlearn verified: `{bnlearn_info.get('verified', False)}`.

## Fail-closed boundary

No study scene was materialized, no observation loaded, no statistical fit was
run, no Oracle/holdout accessed and no semantic API call made. Phase D and E
remain locked until every check passes and a separate live authorization is
issued.

Audit SHA-256: `{sha256(AUDIT)}`
"""
    REPORT.write_text(report, encoding="utf-8")
    return audit


def check() -> dict[str, Any]:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["evidence_boundary"]["statistical_fits"] == 0
    assert audit["evidence_boundary"]["semantic_api_calls"] == 0
    assert audit["status"] != "PASS_EXECUTION_READY"
    return {"status": "PASS_FAIL_CLOSED_REPLAY", "audit_sha256": sha256(AUDIT)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(check() if args.check else execute(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

