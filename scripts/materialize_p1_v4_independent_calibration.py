"""Authorization-gated materializer for frozen P1V4 calibration identities.

The default mode is deliberately non-writing.  `--execute` is rejected unless
a future, separately frozen live-authorization artifact is supplied; this
script is hash-pinned by the look-120 materialization preflight.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from materialize_p1_v4_stage3 import build_blueprint, materialize


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_materialization_preflight.yaml"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def load_exact_look120_identities() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load only the frozen first calibration look; do not generate anything."""
    cfg = yaml.safe_load(PREFLIGHT_CONFIG.read_text(encoding="utf-8"))
    identity_spec = cfg["parents"]["exact_identities"]
    plan_spec = cfg["parents"]["exact_identity_plan"]
    identity_path = ROOT / identity_spec["path"]
    plan_path = ROOT / plan_spec["path"]
    if _sha(identity_path) != identity_spec["sha256"] or _sha(plan_path) != plan_spec["sha256"]:
        raise RuntimeError("frozen identity artifact hash drift")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    expected = plan["exact_scene_ids_in_execution_order"][: int(cfg["selection"]["registered_look"])]
    rows = {row["study_id"]: row for row in _rows(identity_path)}
    selected = [rows[study_id] for study_id in expected]
    if len(selected) != int(cfg["selection"]["exact_scene_count"]):
        raise RuntimeError("look-120 identity count drift")
    if any(row["role"] != cfg["selection"]["allowed_role"] for row in selected):
        raise RuntimeError("non-calibration identity selected")
    if any(row["scene_materialized"] is not False for row in selected):
        raise RuntimeError("identity claims prior materialization")
    return cfg, selected


def materialization_dry_plan() -> dict[str, Any]:
    cfg, identities = load_exact_look120_identities()
    output_root = ROOT / cfg["reserved_outputs"]["scene_root"]
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("reserved calibration scene root is not empty")
    source = yaml.safe_load((ROOT / cfg["parents"]["source_generation_preflight"]["path"]).read_text(encoding="utf-8"))
    generation = source["generation"]
    for key in (
        "family",
        "observational_sample_size",
        "node_count_range",
        "edge_count_range",
        "minimum_oracle_cpdag_unresolved_edges",
    ):
        if generation[key] != cfg["generation"][key]:
            raise RuntimeError(f"generation contract drift from frozen P1V4 source: {key}")
    # No call to build_blueprint() here: this is a pre-materialization plan only.
    return {
        "scene_ids": [row["study_id"] for row in identities],
        "scene_count": len(identities),
        "component_seed_sha256": hashlib.sha256(
            json.dumps([row["component_seeds"] for row in identities], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest().upper(),
        "generation": generation,
        "scene_root": cfg["reserved_outputs"]["scene_root"],
        "writes_performed": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args()
    if args.execute:
        raise SystemExit("live materialization requires a future authorization-gated runner; no authorization is accepted by this preflight-era script")
    if not args.dry_run:
        raise SystemExit("pass --dry-run; this script has no implicit execution mode")
    print(json.dumps(materialization_dry_plan(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
