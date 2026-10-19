"""Freeze exact constrained-parent inputs and the no-closure integration metric contract."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fourgraph.partial_graph import PartialGraph, validate_cpdag  # noqa: E402

CONFIG = ROOT / "configs/p1_v4_stage3_parent_semantic_metric_checkpoint.yaml"


def canonical(value: Any) -> bytes: return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for parent in cfg["parents"].values():
        if sha(ROOT / parent["path"]) != parent["sha256"]: raise RuntimeError(f"parent hash drift: {parent['path']}")
    auth = json.loads((ROOT / cfg["parents"]["paired_oracle_authorization"]["path"]).read_text(encoding="utf-8"))
    audit = json.loads((ROOT / cfg["parents"]["paired_oracle_audit"]["path"]).read_text(encoding="utf-8"))
    if auth.get("status") != "ELIGIBLE_WAITING_FOR_ORACLE_SCORING_EXECUTION" or audit.get("status") != "PASS": raise RuntimeError("parent semantic scoring requires completed paired Oracle audit")
    allowed = {f"P1V4SD{i:03d}" for i in range(30)}; root = ROOT / cfg["statistical_inputs"]["normalized_root"]
    parents: dict[str, dict[str, Any]] = {name: {} for name in cfg["statistical_inputs"]["conditions"]}
    for path in sorted(root.glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8")); algorithm, scene = row.get("algorithm"), row.get("scene_id")
        if algorithm not in parents or scene not in allowed: continue
        if scene in parents[algorithm]: raise RuntimeError(f"duplicate constrained parent: {algorithm}/{scene}")
        graph = row["graph"]; parsed = PartialGraph.build(graph["nodes"], [tuple(x) for x in graph["directed"]], [tuple(x) for x in graph["undirected"]])
        validate_cpdag(parsed)
        parents[algorithm][scene] = {"normalized_path": path.relative_to(ROOT).as_posix(), "normalized_sha256": sha(path), "run_id": row["run_id"], "graph": graph, "directed_count": len(parsed.directed), "undirected_count": len(parsed.undirected)}
    if any(set(records) != allowed for records in parents.values()): raise RuntimeError("not exactly 30 valid constrained parents per condition")
    manifest = {"schema_version": "fourgraph.p1_v4_stage3_parent_cpdag_metric_inputs.v1", "task": cfg["task"], "status": "PASS_FROZEN_PARENT_INPUTS", "conditions": parents, "parent_valid_cpdag_count": {name: len(records) for name, records in parents.items()}}
    manifest_path = ROOT / cfg["outputs"]["parent_manifest"]; manifest_path.write_bytes(canonical(manifest))
    checkpoint = {"schema_version": "fourgraph.p1_v4_stage3_parent_semantic_metric_checkpoint.v1", "task": cfg["task"], "status": "PASS_READY_FOR_EXPLICIT_PARENT_SEMANTIC_METRIC_AUTHORIZATION", "config_sha256": sha(CONFIG), "parents": cfg["parents"], "parent_manifest_sha256": sha(manifest_path), "statistical_inputs": cfg["statistical_inputs"], "semantic_policy": cfg["semantic_policy"], "registered_metrics_after_explicit_authorization": cfg["registered_metrics_after_explicit_authorization"], "boundaries": cfg["boundaries"]}
    checkpoint_path = ROOT / cfg["outputs"]["checkpoint"]; checkpoint_path.write_bytes(canonical(checkpoint))
    final_audit = {"schema_version": "fourgraph.p1_v4_stage3_parent_semantic_metric_checkpoint_audit.v1", "task": cfg["task"], "status": checkpoint["status"], "checkpoint_sha256": sha(checkpoint_path), "parent_manifest_sha256": sha(manifest_path), "constrained_boss_valid_cpdags": 30, "constrained_fges_valid_cpdags": 30, "oracle_access": 0, "holdout_access": 0, "semantic_api_calls": 0, "closure": 0, "metric_calculation": 0}
    audit_path = ROOT / cfg["outputs"]["audit"]; audit_path.write_bytes(canonical(final_audit))
    (ROOT / cfg["outputs"]["report"]).write_text("# P1V4 parent CPDAG + semantic-selected metric checkpoint\n\nThis checkpoint freezes 30 valid constrained-BOSS and 30 valid constrained-FGES CPDAG parents, plus the exact no-closure integration rule. It does not read Oracle or calculate metrics. A new explicit authorization is required for scoring.\n", encoding="utf-8")
    print(json.dumps(final_audit, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
