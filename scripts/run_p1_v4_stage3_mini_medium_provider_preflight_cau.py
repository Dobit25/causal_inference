"""Canonical-cau provider preflight for the frozen Mini-medium comparator."""
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

CONFIG = ROOT / "configs/p1_v4_stage3_mini_medium_provider_preflight_cau.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def run(execute: bool) -> dict[str, Any]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    env = cfg["canonical_environment"]
    checks = {"canonical_python": Path(sys.executable).resolve() == Path(env["python_executable"]).resolve(),
              "python_version": sys.version.split()[0] == env["python_version"], "openai_version": openai.__version__ == env["openai_version"],
              "jiter_version": getattr(jiter, "__version__", None) == env["jiter_version"], "jiter_import": bool(getattr(jiter, "__file__", None)),
              "comparator_hash": sha(ROOT / cfg["parents"]["mini_comparator_amendment"]["path"]) == cfg["parents"]["mini_comparator_amendment"]["sha256"]}
    if not all(checks.values()): raise RuntimeError(f"canonical cau environment/comparator check failed: {checks}")
    result = base.run(CONFIG, execute=execute)
    if not execute: return {"status": result["status"], "provider_calls": 0, "environment_checks": checks}
    record_path = ROOT / cfg["outputs"]["provider_preflight"]; record = json.loads(record_path.read_text(encoding="utf-8"))
    audit = {"schema_version": "fourgraph.p1_v4_stage3_mini_medium_provider_preflight_cau_audit.v1", "task": cfg["task"],
             "status": "PASS_PROVIDER_PREFLIGHT" if record.get("status") == "PASS" else "FAIL_PROVIDER_PREFLIGHT", "environment_checks": checks,
             "record_sha256": sha(record_path), "provider": {key: record.get(key) for key in ("model", "model_requested", "request_id", "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "response_status", "context_limit_check")},
             "boundary": {key: record.get(key) for key in ("study_execution", "study_scenes_loaded", "semantic_calls_after_preflight", "oracle_access", "holdout_access")}}
    audit_path = ROOT / cfg["outputs"]["audit"]; audit_path.write_bytes(canonical(audit))
    (ROOT / cfg["outputs"]["report"]).write_text("# P1V4 Mini-medium provider preflight\n\nOne synthetic 7-node/21-pair provider call; no study scene, Oracle, or holdout.\n", encoding="utf-8")
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--execute", action="store_true"); args = parser.parse_args()
    result = run(args.execute); print(json.dumps(result, ensure_ascii=False, indent=2)); raise SystemExit(0 if result["status"] in {"PASS_DRY_RUN", "PASS_PROVIDER_PREFLIGHT", "PASS_CACHED_PREFLIGHT"} else 1)
