"""Canonical-cau wrapper for exactly one synthetic Mini provider preflight."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import jiter
import openai

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_p1_v4_stage3_provider_preflight as base  # noqa: E402

CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_mini_provider_preflight.yaml"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def env_checks(config: dict) -> dict[str, bool]:
    env = config["canonical_environment"]
    correction = ROOT / config["parents"]["environment_correction"]["path"]
    return {
        "python_executable": Path(sys.executable).resolve() == Path(env["python_executable"]).resolve(),
        "python_version": sys.version.split()[0] == env["python_version"],
        "openai_version": openai.__version__ == env["openai_version"],
        "jiter_version": getattr(jiter, "__version__", None) == env["jiter_version"],
        "jiter_import": bool(getattr(jiter, "__file__", None)),
        "environment_correction_hash": sha(correction) == config["parents"]["environment_correction"]["sha256"],
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    config = base.yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    checks = env_checks(config)
    if not all(checks.values()):
        raise SystemExit(f"canonical cau environment check failed: {checks}")
    result = base.run(CONFIG, execute=args.execute)
    if not args.execute:
        print(json.dumps({"status": result["status"], "provider_calls": 0, "environment_checks": checks}, indent=2))
        return 0
    record_path = ROOT / config["outputs"]["provider_preflight"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    passed = record.get("status") == "PASS"
    audit = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look120_mini_provider_preflight_audit.v1",
        "task": config["task"],
        "status": "PASS_PROVIDER_PREFLIGHT" if passed else "FAIL_PROVIDER_PREFLIGHT",
        "environment_checks": checks,
        "record_sha256": sha(record_path),
        "provider": {key: record.get(key) for key in ("model", "model_requested", "request_id", "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "response_status", "context_limit_check")},
        "boundary": {key: record.get(key) for key in ("study_execution", "study_scenes_loaded", "semantic_calls_after_preflight", "oracle_access", "holdout_access")},
        "prompt_schema": {"prompt_sha256": record["dependencies"]["prompt"]["sha256"], "schema_sha256": record["dependencies"]["schema"]["sha256"], "truncation": record["truncation"], "automatic_prompt_chunking": record["automatic_prompt_chunking"]},
    }
    out = ROOT / config["outputs"]["audit"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base.canonical(audit))
    (ROOT / config["outputs"]["report"]).write_text(
        f"# Look-120 Mini provider preflight\n\nStatus: **{audit['status']}**. One synthetic 7-node / 21-pair request only; no study scene, Oracle, holdout, or study semantic execution was used.\n",
        encoding="utf-8",
    )
    print(json.dumps(audit, indent=2))
    return 0 if passed else 1

if __name__ == "__main__":
    raise SystemExit(main())
