"""Generate or byte-check the T07 development-only Oracle loader audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fourgraph.causalds_oracle import load_causalds_oracle_graph  # noqa: E402
from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402


DEFAULT_CONFIG = Path("configs/t07_oracle_loader.yaml")
DEFAULT_OUTPUT = Path("data/manifests/t07_oracle_loader_audit.json")


def file_sha256(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return value


def build_audit(
    source_root: Path,
    *,
    config_path: Path = DEFAULT_CONFIG,
) -> bytes:
    config = _load_yaml(config_path)
    scope = config["scope"]
    if scope["role"] != "dev" or scope["forbid_holdout_access"] is not True:
        raise ValueError("T07 audit is restricted to frozen development scenes")
    if config["access"]["return_raw_grading_document"] is not False:
        raise ValueError("T07 must not return raw grading documents")
    if config["audit"]["include_edges"] is not False:
        raise ValueError("T07 versioned audit must not include Oracle edges")

    split_path = PROJECT_ROOT / scope["split_manifest"]
    split = _load_json(split_path)
    cohort = split["cohorts"][scope["cohort"]]
    dev_ids = tuple(cohort["dev_ids"])
    holdout_ids = set(cohort["holdout_ids"])
    if len(dev_ids) != scope["expected_scenes"]:
        raise ValueError("Frozen development scene count does not match T07 config")
    if set(dev_ids) & holdout_ids:
        raise ValueError("Development and holdout scene IDs overlap")

    config_sha256 = file_sha256(config_path)
    records = []
    for scene_id in dev_ids:
        if scene_id in holdout_ids:
            raise RuntimeError(f"T07 attempted holdout access: {scene_id}")
        result = load_causalds_oracle_graph(
            source_root,
            scene_id,
            config_sha256=config_sha256,
            variant=config["source"]["variant"],
        )
        record = result.audit_record()
        if "edges" in record or "raw_ground_truth" in record:
            raise RuntimeError("Oracle audit record contains forbidden raw structure")
        records.append(record)

    anchors = config["t05_freeze_anchors"]
    for relative_path, expected in anchors.items():
        actual = file_sha256(PROJECT_ROOT / relative_path)
        if actual != expected:
            raise RuntimeError(f"Frozen T05 artifact changed: {relative_path}")

    graph_contract_path = PROJECT_ROOT / config["graph"]["contract_config"]
    audit = {
        "manifest_version": 1,
        "task": "T07",
        "status": "complete_oracle_loader_ready",
        "source": {
            "benchmark": config["source"]["benchmark"],
            "github_commit": config["source"]["github_commit"],
            "huggingface_revision": config["source"]["huggingface_revision"],
            "variant": config["source"]["variant"],
        },
        "scope": {
            "cohort": "graph_dev",
            "scene_ids": list(dev_ids),
            "scene_count": len(dev_ids),
            "holdout_scene_count": len(holdout_ids),
            "holdout_accessed": False,
            "downstream_reasoner_used": False,
        },
        "contract": {
            "graph_schema_version": "fourgraph.graph.v1",
            "variable_map_schema_version": "fourgraph.variable_map.v1",
            "graph_method": "oracle",
            "graph_type": "dag",
            "graph_view": "dag",
            "config_sha256": config_sha256,
            "graph_contract_config_sha256": file_sha256(graph_contract_path),
            "split_manifest_sha256": file_sha256(split_path),
        },
        "access_boundary": {
            "public_artifacts_read": ["schema"],
            "grading_artifacts_read": ["ground_truth"],
            "raw_grading_document_returned": False,
            "gold_answer_fields_consumed": False,
            "grading_test_values_read": False,
            "graph_images_read": False,
            "versioned_edges_included": False,
        },
        "aggregate": {
            "scenes_attempted": len(dev_ids),
            "scenes_succeeded": len(records),
            "all_valid_dags": all(record["valid"] for record in records),
            "node_count_min": min(record["node_count"] for record in records),
            "node_count_max": max(record["node_count"] for record in records),
            "edge_count_min": min(record["edge_count"] for record in records),
            "edge_count_max": max(record["edge_count"] for record in records),
        },
        "records": records,
        "t05_frozen_artifacts_unchanged": anchors,
        "verdict": {
            "oracle_loader_ready": True,
            "reason": (
                "All eight frozen graph-development scenes mapped public schema "
                "variables to canonical IDs and produced valid grading-only Oracle "
                "DAG artifacts without returning raw grading records or accessing "
                "holdout scenes."
            ),
        },
    }
    return canonical_json_bytes(audit, newline=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = build_audit(args.source_root, config_path=args.config)
    output = PROJECT_ROOT / args.output
    if args.check:
        if not output.is_file() or output.read_bytes() != content:
            raise RuntimeError(f"Generated artifact is missing or stale: {output}")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)

    manifest = json.loads(content)
    print(
        json.dumps(
            {
                "mode": "check" if args.check else "write",
                "status": manifest["status"],
                "scenes_succeeded": manifest["aggregate"]["scenes_succeeded"],
                "holdout_accessed": manifest["scope"]["holdout_accessed"],
                "oracle_loader_ready": manifest["verdict"]["oracle_loader_ready"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
