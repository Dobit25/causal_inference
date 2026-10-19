"""Canonical-`cau` wrapper for one P1V4 non-study provider preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import jiter
import openai
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_p1_v4_stage3_provider_preflight as base

CONFIG = ROOT / "configs/p1_v4_stage3_provider_preflight_cau.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def environment_check(cfg: dict[str, Any]) -> dict[str, bool]:
    env = cfg["canonical_environment"]
    correction = ROOT / cfg["parents"]["environment_correction"]["path"]
    return {
        "canonical_python": Path(sys.executable).resolve() == Path(env["python_executable"]).resolve(),
        "python_version": sys.version.split()[0] == env["python_version"],
        "openai_version": openai.__version__ == env["openai_version"],
        "jiter_version": getattr(jiter, "__version__", None) == env["jiter_version"],
        "jiter_import": bool(getattr(jiter, "__file__", None)),
        "environment_correction_hash": sha(correction) == cfg["parents"]["environment_correction"]["sha256"],
    }


def run(execute: bool) -> dict[str, Any]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    checks = environment_check(cfg)
    if not all(checks.values()):
        raise RuntimeError(f"canonical cau environment check failed: {checks}")
    result = base.run(CONFIG, execute=execute)
    if not execute:
        return {"status": result["status"], "provider_calls": 0, "environment_checks": checks}
    record_path = ROOT / cfg["outputs"]["provider_preflight"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    passed = record.get("status") == "PASS"
    audit = {
        "schema_version": "fourgraph.p1_v4_stage3_provider_preflight_cau_audit.v1",
        "task": cfg["task"],
        "status": "PASS_PROVIDER_PREFLIGHT" if passed else "FAIL_PROVIDER_PREFLIGHT",
        "environment_checks": checks,
        "record_sha256": sha(record_path),
        "provider": {key: record.get(key) for key in ("model", "model_requested", "request_id", "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "response_status", "context_limit_check")},
        "boundary": {key: record.get(key) for key in ("study_execution", "study_scenes_loaded", "semantic_calls_after_preflight", "oracle_access", "holdout_access")},
        "prompt_schema": {"prompt_sha256": record["dependencies"]["prompt"]["sha256"], "schema_sha256": record["dependencies"]["schema"]["sha256"], "truncation": record["truncation"]},
    }
    audit_path = ROOT / cfg["outputs"]["audit"]
    audit_path.parent.mkdir(parents=True, exist_ok=True); audit_path.write_bytes(canonical(audit))
    report = f"""# P1V4 provider preflight in canonical `cau`

Status: **{audit['status']}**. This used one synthetic 7-node / 21-pair request, not a study scene. It used the frozen Nano-medium model, prompt and strict schema with truncation/chunking disabled. Provider-reported usage and request metadata are recorded in the audit. No Oracle, holdout or study semantic execution occurred.
""".encode("utf-8")
    (ROOT / cfg["outputs"]["report"]).write_bytes(report)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--execute", action="store_true"); args = parser.parse_args()
    result = run(args.execute)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"PASS_DRY_RUN", "PASS_PROVIDER_PREFLIGHT", "PASS_CACHED_PREFLIGHT"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
