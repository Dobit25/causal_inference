from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v3_nano_medium_calibration_look120_pre_api_preflight.yaml"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def command_version(command: str, args: list[str]) -> dict[str, Any]:
    resolved = shutil.which(command)
    if not resolved:
        return {"present": False, "path": None, "version": None}
    try:
        proc = subprocess.run([resolved, *args], capture_output=True, text=True, timeout=10)
        text = (proc.stdout + proc.stderr).strip()
        return {"present": proc.returncode == 0, "path": resolved, "version": text}
    except Exception as exc:  # pragma: no cover
        return {"present": False, "path": resolved, "version": str(exc)}


def run() -> dict[str, Any]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    parent_hashes = {}
    for item in cfg["parents"].values():
        path = ROOT / item["path"]
        actual = sha256_file(path)
        if actual != item["sha256"].upper():
            raise RuntimeError(f"parent hash drift: {item['path']}")
        parent_hashes[item["path"]] = actual
    story_audit = json.loads((ROOT / cfg["parents"]["story_audit"]["path"]).read_text(encoding="utf-8"))
    scene_manifest = json.loads((ROOT / cfg["parents"]["materialized_scene_manifest"]["path"]).read_text(encoding="utf-8"))
    python_version = platform.python_version()
    java = command_version("java", ["-version"])
    rscript = command_version("Rscript", ["--version"])
    jar_path = ROOT / cfg["environment"]["tetrad_jar"]
    jar = {"present": jar_path.is_file(), "sha256": sha256_file(jar_path) if jar_path.is_file() else None}
    checks = {
        "parent_hashes": "PASS",
        "scene_count": len(scene_manifest.get("records", [])) == 120,
        "story_audit_pass": story_audit.get("status") == "PASS_CALIBRATION_PUBLIC_STORIES_FROZEN",
        "python_exact": python_version == cfg["environment"]["python_required"],
        "java_present": java["present"],
        "rscript_present": rscript["present"],
        "tetrad_hash": jar["sha256"] == cfg["environment"]["tetrad_jar_sha256"],
    }
    status = "PASS_READY_BEFORE_STATISTICAL_EXECUTION" if all(v is True or v == "PASS" for v in checks.values()) else "BLOCKED_ENVIRONMENT_BEFORE_STATISTICAL_EXECUTION"
    return {
        "schema_version": "fourgraph.p1_v3_nano_medium_calibration_look120_pre_api_audit.v1",
        "status": status,
        "parent_hashes": parent_hashes,
        "scene_count": len(scene_manifest.get("records", [])),
        "story_count": story_audit.get("story_count"),
        "environment": {"python": python_version, "java": java, "rscript": rscript, "tetrad_jar": jar},
        "checks": checks,
        "statistical_fits": 0,
        "semantic_api_calls": 0,
        "oracle_access": False,
        "validation_access": False,
        "holdout_access": False,
        "next_action": "fix_exact_environment_then_rerun_preflight" if status.startswith("BLOCKED") else "run_statistical_parent_then_stop_before_api",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "data/manifests/p1_v3_nano_medium_calibration_look120_pre_api_preflight_audit.json")
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
