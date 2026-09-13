"""Open grading-only Oracle after the T14 non-Oracle seal and compute metrics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fourgraph.causalds_oracle import load_causalds_oracle_graph  # noqa: E402
from fourgraph.graph_contract import canonical_json_bytes, sha256_hex, validate_hybrid_relationship, validate_projection_relationship  # noqa: E402
from fourgraph.graph_metrics import evaluate_graph, hybrid_attribution, load_graph_artifact_jsonl  # noqa: E402


CONDITIONS = ["G_LLM", "G_SCD_RAW", "G_SCD_PROJECTED", "G_HYBRID", "G_ORACLE"]
ROLES = {"G_LLM": "primary", "G_SCD_RAW": "primary", "G_SCD_PROJECTED": "sensitivity", "G_HYBRID": "primary", "G_ORACLE": "sanity"}


def obj(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    args = parser.parse_args()
    t13_path = ROOT / "data/manifests/t13_holdout_execution.json"
    t13_audit = obj(ROOT / "data/manifests/t13_holdout_execution_audit.json")
    t13 = obj(t13_path)
    if sha256_hex(t13_path.read_bytes()) != t13_audit["execution_manifest_sha256"] or not t13_audit["verdict"]["t14_authorized"]:
        raise RuntimeError("T13 authorization failed")
    out_root = ROOT / t13["execution"]["outputs"]["t14_root"]
    seal_path = out_root / "non_oracle_seal.json"
    seal = obj(seal_path)
    if not seal["sealed"] or seal["oracle_accessed"]:
        raise RuntimeError("Non-Oracle graph seal is absent or contaminated")
    scene_ids = t13["cohorts"]["graph"]["holdout_scene_ids"]
    graphs = {
        name: load_graph_artifact_jsonl(ROOT / item["path"])
        for name, item in seal["condition_files"].items()
    }
    failures = {
        (item["condition"], item["scene_id"]): item
        for item in [json.loads(line) for line in (ROOT / seal["failure_manifest"]["path"]).read_text(encoding="utf-8").splitlines() if line]
    } if seal["failure_manifest"]["records"] else {}
    oracle_config_sha = sha256_hex((ROOT / "configs/t07_oracle_loader.yaml").read_bytes())
    oracles = {}
    variable_maps = {}
    oracle_audit = []
    for scene in scene_ids:
        loaded = load_causalds_oracle_graph(args.source_root.resolve(), scene, config_sha256=oracle_config_sha)
        oracles[scene] = loaded.graph_artifact
        variable_maps[scene] = loaded.variable_map
        oracle_audit.append(loaded.audit_record())

    records = []
    available = 0
    for scene in scene_ids:
        raw = graphs["G_SCD_RAW"][scene]
        projected = graphs["G_SCD_PROJECTED"][scene]
        validate_projection_relationship(raw, projected)
        if scene in graphs["G_HYBRID"]:
            validate_hybrid_relationship(raw, graphs["G_HYBRID"][scene])
        for condition in CONDITIONS:
            if (condition, scene) in failures:
                records.append({
                    "schema_version": "fourgraph.t14_graph_metric_schedule.v1",
                    "scene_id": scene,
                    "graph_condition": condition,
                    "status": "unavailable",
                    "reason": "terminal_graph_construction_failure",
                    "metric_record": None,
                })
                continue
            graph = oracles[scene] if condition == "G_ORACLE" else graphs[condition][scene]
            attribution = hybrid_attribution(raw, projected, graph, oracles[scene]) if condition == "G_HYBRID" else None
            metric = evaluate_graph(graph, oracles[scene], condition=condition, role=ROLES[condition], variable_mapping_sha256=variable_maps[scene].mapping_sha256, hybrid_error_attribution=attribution)
            records.append({
                "schema_version": "fourgraph.t14_graph_metric_schedule.v1",
                "scene_id": scene,
                "graph_condition": condition,
                "status": "available",
                "reason": None,
                "metric_record": metric,
            })
            available += 1
    if len(records) != 125:
        raise RuntimeError("T14 graph metric schedule must contain 125 rows")
    output = ROOT / t13["execution"]["outputs"]["t14_graph_metrics"]
    payload = b"".join(canonical_json_bytes(item, newline=True) for item in records)
    output.write_bytes(payload)
    audit = {
        "schema_version": "fourgraph.t14_graph_metrics_audit.v1",
        "logical_run_id": t13["execution"]["logical_run_id"],
        "scheduled_records": 125,
        "available_records": available,
        "unavailable_records": 125 - available,
        "unavailable_by_condition": {condition: sum(item["graph_condition"] == condition and item["status"] == "unavailable" for item in records) for condition in CONDITIONS},
        "records_sha256": sha256_hex(payload),
        "non_oracle_seal_sha256": sha256_hex(seal_path.read_bytes()),
        "oracle_scene_count": len(oracles),
        "oracle_edges_persisted": False,
        "oracle_input_audit": oracle_audit,
        "downstream_tasks_accessed": False,
        "inference_or_bh_performed": False,
        "complete": True,
    }
    (out_root / "graph_metrics_audit.json").write_bytes(canonical_json_bytes(audit, newline=True))
    print(json.dumps({"graph_metrics": 125, "available": available, "unavailable": 125 - available, "oracle_scenes": 25, "oracle_edges_persisted": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
