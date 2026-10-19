"""Freeze the paired Mini-medium comparator using exact Nano input identities."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_stage3_mini_medium_paired_comparator.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for item in cfg["parents"].values():
        path = ROOT / item["path"]
        if sha(path) != item["sha256"]:
            raise RuntimeError(f"parent hash drift: {item['path']}")
    nano = json.loads((ROOT / cfg["parents"]["nano_completion_audit"]["path"]).read_text(encoding="utf-8"))
    if nano.get("status") != "PASS_LOGICAL_COMPLETION" or nano.get("selected_terminal_responses") != 360:
        raise RuntimeError("Nano logical completion is not frozen")
    source = json.loads((ROOT / cfg["parents"]["execution_plan"]["path"]).read_text(encoding="utf-8"))
    logical = []
    for row in source["logical_calls"]:
        mini = dict(row); mini["model_snapshot"] = cfg["paired_contract"]["only_changed_factor"]["model_snapshot"]
        mini["reasoning_effort"] = cfg["paired_contract"]["only_changed_factor"]["reasoning_effort"]
        logical.append(mini)
    if len(logical) != 360 or len({row["logical_id"] for row in logical}) != 360:
        raise RuntimeError("paired Mini plan is not exactly 360 unique logical calls")
    plan = {"schema_version": "fourgraph.p1_v4_stage3_mini_medium_paired_execution_plan.v1", "task": cfg["task"],
            "source_execution_plan_sha256": cfg["parents"]["execution_plan"]["sha256"], "model_snapshot": cfg["paired_contract"]["only_changed_factor"]["model_snapshot"],
            "reasoning_effort": cfg["paired_contract"]["only_changed_factor"]["reasoning_effort"], "logical_calls": logical}
    plan_path = ROOT / cfg["outputs"]["paired_execution_plan"]; plan_path.write_bytes(canonical(plan))
    artifact = {"schema_version": "fourgraph.p1_v4_stage3_mini_medium_paired_comparator_amendment.v1", "task": cfg["task"], "status": "PASS_FROZEN",
                "config_sha256": sha(CONFIG), "parents": cfg["parents"], "paired_contract": cfg["paired_contract"], "execution": cfg["execution"],
                "boundaries": cfg["boundaries"], "paired_execution_plan_sha256": sha(plan_path)}
    artifact_path = ROOT / cfg["outputs"]["amendment"]; artifact_path.write_bytes(canonical(artifact))
    audit = {"schema_version": "fourgraph.p1_v4_stage3_mini_medium_paired_comparator_audit.v1", "task": cfg["task"], "status": "PASS",
             "logical_calls": len(logical), "same_logical_ids_as_nano": [row["logical_id"] for row in logical] == [row["logical_id"] for row in source["logical_calls"]],
             "only_contract_difference": ["model_snapshot"], "plan_sha256": sha(plan_path), "amendment_sha256": sha(artifact_path),
             "oracle_access": 0, "holdout_access": 0, "metrics": 0, "nano_rescore": 0}
    audit_path = ROOT / cfg["outputs"]["audit"]; audit_path.write_bytes(canonical(audit))
    report = "# P1V4 paired Mini-medium comparator\n\nFrozen: exactly the 360 Nano logical inputs will be rerun with GPT-5.4 Mini at medium reasoning effort. Stories, pair pools, prompt, schema, six prompt variants and validator are pinned unchanged. No Oracle, closure, metrics, or Nano re-score occurred.\n"
    (ROOT / cfg["outputs"]["report"]).write_text(report, encoding="utf-8")
    print(json.dumps({"status": "PASS", "plan_sha256": sha(plan_path), "amendment_sha256": sha(artifact_path), "audit_sha256": sha(audit_path)}, indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
