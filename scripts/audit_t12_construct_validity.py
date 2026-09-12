"""Compare official CausalDS adjustment targets with a Pearl back-door sensitivity."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fourgraph.causalds_oracle import load_causalds_oracle_graph  # noqa: E402
from fourgraph.causalds_scoring import load_official_target  # noqa: E402
from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.reasoner import TASKS, load_reasoner_query  # noqa: E402
from fourgraph.reasoner_v2 import standards_task_semantics  # noqa: E402


OUTPUT = PROJECT_ROOT / "data/manifests/t12_construct_validity_dev.jsonl"
AUDIT = PROJECT_ROOT / "data/manifests/t12_construct_validity_audit.json"


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def build(source_root: Path) -> tuple[bytes, bytes]:
    split = _object(PROJECT_ROOT / "data/manifests/p0_frozen_split.json")
    dev_ids = tuple(split["cohorts"]["primary_downstream"]["dev_ids"])
    holdout_ids = set(split["cohorts"]["primary_downstream"]["holdout_ids"])
    if set(dev_ids) & holdout_ids or len(dev_ids) != 7:
        raise RuntimeError("Frozen primary development split changed")
    oracle_config = PROJECT_ROOT / "configs/t07_oracle_loader.yaml"
    oracle_config_sha = sha256_hex(oracle_config.read_bytes())
    records: list[dict[str, Any]] = []
    adjustment_tasks = TASKS[:4]
    for scene_id in dev_ids:
        if scene_id in holdout_ids:
            raise RuntimeError("Construct-validity audit attempted holdout access")
        for task_id in adjustment_tasks:
            query, variable_map, public_tasks_sha = load_reasoner_query(
                source_root, scene_id, task_id
            )
            oracle = load_causalds_oracle_graph(
                source_root, scene_id, config_sha256=oracle_config_sha
            ).graph_artifact
            official = load_official_target(source_root, query, variable_map)
            standard = standards_task_semantics(oracle.partial_graph, query)
            agrees = official.accepted == standard.accepted
            records.append(
                {
                    "schema_version": "fourgraph.construct_validity_record.v1",
                    "scene_id": scene_id,
                    "task_id": task_id,
                    "graph_sha256": oracle.graph_sha256,
                    "query_sha256": query.sha256,
                    "variable_mapping_sha256": variable_map.mapping_sha256,
                    "public_tasks_sha256": public_tasks_sha,
                    "official_ground_truth_sha256": official.ground_truth_sha256,
                    "official_causalds_target": list(official.accepted),
                    "pearl_backdoor_total_effect_target": list(standard.accepted),
                    "targets_agree": agrees,
                    "holdout_accessed": False,
                }
            )
    payload = b"".join(canonical_json_bytes(record, newline=True) for record in records)
    per_task = Counter(record["task_id"] for record in records if not record["targets_agree"])
    audit = {
        "schema_version": "fourgraph.construct_validity_audit.v1",
        "records": len(records),
        "development_scenes": len(dev_ids),
        "tasks": list(adjustment_tasks),
        "official_and_standard_agree": sum(record["targets_agree"] for record in records),
        "official_and_standard_disagree": sum(not record["targets_agree"] for record in records),
        "disagreements_by_task": dict(sorted(per_task.items())),
        "forbidden_controls_sensitivity": "not_applicable_construct_differs",
        "holdout_accessed": False,
        "records_sha256": sha256_hex(payload),
    }
    return payload, canonical_json_bytes(audit, newline=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload, audit = build(args.source_root.resolve())
    if args.check:
        if OUTPUT.read_bytes() != payload or AUDIT.read_bytes() != audit:
            raise RuntimeError("Construct-validity artifacts do not reproduce byte-for-byte")
    else:
        OUTPUT.write_bytes(payload)
        AUDIT.write_bytes(audit)
    print(json.dumps(json.loads(audit), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
