"""Generate or byte-check CausalDS T04 integrity and frozen manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fourgraph.causalds_integrity import build_t04_artifacts
from fourgraph.causalds_inventory import load_json


DEFAULT_OUTPUTS = {
    "integrity": Path("data/manifests/p0_data_integrity.json"),
    "primary_tasks": Path("data/manifests/p0_primary_task_manifest.jsonl"),
    "supplementary_tasks": Path(
        "data/manifests/p0_supplementary_task_manifest.jsonl"
    ),
    "frozen_split": Path("data/manifests/p0_frozen_split.json"),
}


def _check_bytes(path: Path, expected: bytes) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Expected generated artifact is missing: {path}")
    if path.read_bytes() != expected:
        raise RuntimeError(f"Generated artifact is stale: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=Path("data/manifests/causalds.json"),
    )
    parser.add_argument(
        "--provisional-split",
        type=Path,
        default=Path("data/manifests/p0_provisional_split.json"),
    )
    parser.add_argument("--integrity-output", type=Path, default=DEFAULT_OUTPUTS["integrity"])
    parser.add_argument(
        "--primary-task-output", type=Path, default=DEFAULT_OUTPUTS["primary_tasks"]
    )
    parser.add_argument(
        "--supplementary-task-output",
        type=Path,
        default=DEFAULT_OUTPUTS["supplementary_tasks"],
    )
    parser.add_argument(
        "--frozen-split-output", type=Path, default=DEFAULT_OUTPUTS["frozen_split"]
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    artifacts = build_t04_artifacts(
        args.source_root,
        load_json(args.source_manifest),
        load_json(args.provisional_split),
    )
    paths = {
        "integrity": args.integrity_output,
        "primary_tasks": args.primary_task_output,
        "supplementary_tasks": args.supplementary_task_output,
        "frozen_split": args.frozen_split_output,
    }
    if args.check:
        for name, path in paths.items():
            expected = artifacts[name]
            if expected is not None:
                _check_bytes(path, expected)
    else:
        for name, path in paths.items():
            content = artifacts[name]
            if content is None:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    integrity = json.loads(artifacts["integrity"])
    summary = {
        "mode": "check" if args.check else "write",
        "integrity_ready": integrity["integrity_ready"],
        "scenes": integrity["aggregate"]["scene_count"],
        "passed_scenes": integrity["aggregate"]["passed_scenes"],
        "failed_scene_ids": integrity["aggregate"]["failed_scene_ids"],
        "primary_task_records": integrity["outputs"]["primary_task_manifest"][
            "records"
        ],
        "supplementary_task_records": integrity["outputs"][
            "supplementary_task_manifest"
        ]["records"],
        "frozen_split_created": artifacts["frozen_split"] is not None,
    }
    print(json.dumps(summary, indent=2))
    return 0 if integrity["integrity_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
