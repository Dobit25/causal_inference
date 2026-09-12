"""Generate or verify the versioned CausalDS T03 inventory and split."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fourgraph.causalds_inventory import (
    build_scene_inventory,
    build_split_manifest,
    load_json,
    serialize_inventory,
    serialize_manifest,
)
from fourgraph.config import load_config


DEFAULT_INVENTORY = Path("data/manifests/causalds_scene_inventory.jsonl")
DEFAULT_SPLIT = Path("data/manifests/p0_provisional_split.json")


def _check_bytes(path: Path, expected: bytes) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Expected generated artifact is missing: {path}")
    actual = path.read_bytes()
    if actual != expected:
        raise RuntimeError(f"Generated artifact is stale: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--config", type=Path, default=Path("configs/p0_released.yaml"))
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=Path("data/manifests/causalds.json"),
    )
    parser.add_argument("--inventory-output", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--split-output", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    t03 = config["t03"]
    source_manifest = load_json(args.source_manifest)
    inventory = build_scene_inventory(
        args.source_root,
        required_task_ids=config["tasks"]["frozen_priority"],
    )
    inventory_bytes = serialize_inventory(inventory)
    split_manifest = build_split_manifest(
        inventory,
        inventory_bytes,
        source_manifest,
        seed=int(config["experiment"]["seed"]),
        restarts=int(t03["stratification"]["restarts"]),
    )
    split_bytes = serialize_manifest(split_manifest)

    if args.check:
        _check_bytes(args.inventory_output, inventory_bytes)
        _check_bytes(args.split_output, split_bytes)
    else:
        args.inventory_output.parent.mkdir(parents=True, exist_ok=True)
        args.split_output.parent.mkdir(parents=True, exist_ok=True)
        args.inventory_output.write_bytes(inventory_bytes)
        args.split_output.write_bytes(split_bytes)

    summary = {
        "mode": "check" if args.check else "write",
        "inventory_scenes": len(inventory),
        "graph_scenes": split_manifest["cohorts"]["graph"]["scene_count"],
        "primary_scenes": split_manifest["cohorts"]["primary_downstream"][
            "scene_count"
        ],
        "supplementary_scenes": split_manifest["cohorts"]["supplementary"][
            "scene_count"
        ],
        "graph_dev_ids": split_manifest["cohorts"]["graph"]["dev_ids"],
        "objective_loss": split_manifest["algorithm"]["selected_objective_loss"],
        "status": split_manifest["status"],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
