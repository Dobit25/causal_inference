"""Freeze the separately authorized, one-call Nano retry amendment."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_stage3_nano_missing_response_retry_amendment.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    raw = ROOT / cfg["parent_execution"]["raw_responses"]
    if sha(raw) != cfg["parent_execution"]["raw_responses_sha256_before_retry"]:
        raise RuntimeError("cannot freeze retry: historical raw response hash differs")
    for key in ("execution_plan", "original_live_authorization", "interruption_incident"):
        path = ROOT / cfg["parent_execution"][key]
        expected = cfg["parent_execution"][f"{key}_sha256"]
        if sha(path) != expected:
            raise RuntimeError(f"parent hash drift: {key}")
    artifact = {"schema_version": "fourgraph.p1_v4_stage3_nano_missing_response_retry_amendment.v1", "task": cfg["task"],
                "status": "PASS_FROZEN_SINGLE_RETRY", "config_sha256": sha(CONFIG), "parent_execution": cfg["parent_execution"],
                "semantic_contract": cfg["semantic_contract"], "retry_scope": cfg["retry_scope"], "boundaries": cfg["boundaries"]}
    path = ROOT / cfg["outputs"]["amendment"]; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(canonical(artifact))
    print(json.dumps({"status": artifact["status"], "artifact": str(path.relative_to(ROOT)), "sha256": sha(path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
