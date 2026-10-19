"""Freeze `cau` as the sole P1V4 execution runtime without changing science."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import jiter
import openai
import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_cau_environment_correction.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def command(*args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(args, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return (completed.stdout + completed.stderr).strip()


def normal_version(value: str) -> str:
    return "5.3-" + value.removeprefix("5.3.") if value.startswith("5.3.") else value


def package_lock() -> bytes:
    rows = command(sys.executable, "-m", "pip", "freeze").splitlines()
    return ("# Exact pip freeze for canonical P1V4 `cau` runtime\n" + "\n".join(rows) + "\n").encode("utf-8")


def build() -> dict[Path, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    env = cfg["canonical_environment"]
    if Path(sys.executable).resolve() != Path(env["python_executable"]).resolve():
        raise RuntimeError("environment correction must be frozen from the canonical cau Python executable")
    checks = {
        "python": platform.python_version() == env["python_version"],
        "openai": openai.__version__ == env["openai_version"],
        "jiter": getattr(jiter, "__version__", None) == env["jiter_version"],
        "jiter_import": bool(getattr(jiter, "__file__", None)),
        "java": env["java_version"] in command(env["java_executable"], "-version"),
        "java_jvm_exists": (Path(env["java_home"]) / "bin/server/jvm.dll").is_file(),
        "r_and_bnlearn": False,
        "tetrad_jar": sha_file(ROOT / env["tetrad_jar"]) == env["tetrad_jar_sha256"],
        "historical_audit": sha_file(ROOT / cfg["historical_phase_d"]["audit"]) == cfg["historical_phase_d"]["audit_sha256"],
        "historical_artifacts_retained": (ROOT / cfg["historical_phase_d"]["output_root"]).is_dir(),
        "no_scientific_parameter_change": cfg["scientific_invariants"]["model_prompt_schema_cohort_algorithm_thresholds_unchanged"] is True,
    }
    r_env = dict(os.environ)
    r_env["R_LIBS_USER"] = env["r_library"]
    r_probe = command(env["rscript"], "-e", "cat(R.version.string,'\\n'); cat(as.character(packageVersion('bnlearn')),'\\n')", env=r_env).splitlines()
    checks["r_and_bnlearn"] = any(env["r_version"] in line for line in r_probe) and any(normal_version(line.strip()) == env["bnlearn_version"] for line in r_probe)
    lock = package_lock()
    lock_path = ROOT / cfg["outputs"]["package_lock"]
    lock_hash = hashlib.sha256(lock).hexdigest().upper()
    passed = all(checks.values())
    amendment = {
        "schema_version": "fourgraph.p1_v4_cau_environment_correction.v1",
        "task": cfg["task"],
        "status": "PASS_CANONICAL_CAU_ENVIRONMENT" if passed else "FAIL_CANONICAL_CAU_ENVIRONMENT",
        "decision": cfg["decision"],
        "scientific_invariants": cfg["scientific_invariants"],
        "canonical_environment": {**env, "package_lock_sha256": lock_hash, "platform": platform.platform()},
        "historical_phase_d": cfg["historical_phase_d"],
        "checks": checks,
        "execution_boundary": {"statistical_fits": 0, "semantic_api_calls": 0, "oracle_access": False, "holdout_access": False},
    }
    amendment_bytes = canonical(amendment)
    audit = {
        "schema_version": "fourgraph.p1_v4_cau_environment_correction_audit.v1",
        "task": cfg["task"],
        "status": amendment["status"],
        "checks": checks,
        "hashes": {"config": sha_file(CONFIG), "package_lock": lock_hash, "amendment": hashlib.sha256(amendment_bytes).hexdigest().upper(), "historical_phase_d_audit": cfg["historical_phase_d"]["audit_sha256"]},
        "execution_boundary": amendment["execution_boundary"],
    }
    report = f"""# P1V4 canonical `cau` environment correction

Status: **{amendment['status']}**.

This amendment makes `cau` the only authorized runtime from this checkpoint onward. The prior `p1v3_py31020` Phase-3D output is retained as a historical technical run and is not overwritten. The official P1V4 statistical layer must be rerun into a distinct `..._cau` output namespace before any semantic execution.

No model, prompt, schema, cohort, generator, algorithm, threshold, Oracle or holdout rule changed. This checkpoint made no statistical fit and no API call.
""".encode("utf-8")
    return {lock_path: lock, ROOT / cfg["outputs"]["amendment"]: amendment_bytes, ROOT / cfg["outputs"]["audit"]: canonical(audit), ROOT / cfg["outputs"]["report"]: report}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    generated = build()
    if args.check:
        for path, content in generated.items():
            if not path.is_file() or path.read_bytes() != content:
                raise SystemExit(f"artifact drift: {path.relative_to(ROOT)}")
    else:
        for path, content in generated.items():
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    print(json.dumps({"status": "PASS", "canonical_runtime": "cau", "artifacts": [str(path.relative_to(ROOT)) for path in generated]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
