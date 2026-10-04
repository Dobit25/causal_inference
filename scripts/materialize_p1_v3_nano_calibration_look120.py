"""Materialization adapter for the frozen look-120 calibration prefix.

The adapter is intentionally separate from semantic execution.  It can only
select the first 120 calibration identities from the frozen plan; it rejects
development, validation and holdout namespaces.  The default is ``--check``;
materialization requires an explicit ``--materialize`` invocation by the live
execution checkpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from materialize_p1v3_development import build_blueprint, seed64  # noqa: E402
from fourgraph.p1_generation import npy_bytes, sample_observations, scene_scm_record  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_rows(identity_path: Path) -> list[dict]:
    rows = [json.loads(line) for line in identity_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    selected = [row for row in rows if row.get("role") == "semantic_calibration" and int(row.get("sequence_index", -1)) < 120]
    selected.sort(key=lambda row: int(row["sequence_index"]))
    if len(selected) != 120 or any(not row["study_id"].startswith("P1V3SC") for row in selected):
        raise RuntimeError("materializer cohort guard failed")
    if any(row.get("role") in {"method_development", "threshold_validation"} for row in selected):
        raise RuntimeError("forbidden cohort role")
    return selected


def materialize(config_path: Path, execute: bool) -> dict:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    identity_path = ROOT / "data/manifests/p1_v3_successor_sequential_exact_identities.jsonl"
    rows = load_rows(identity_path)
    generator_cfg = yaml.safe_load((ROOT / cfg["materialization"]["generator_config"]).read_text(encoding="utf-8"))["generator"]
    root = ROOT / cfg["materialization"]["scene_root"]
    if not execute:
        return {"status": "PASS_MATERIALIZATION_PLAN", "scene_count": len(rows), "writes": 0, "root": str(root.relative_to(ROOT))}
    root.mkdir(parents=True, exist_ok=True)
    records = []
    for identity in rows:
        scene_dir = root / identity["study_id"]
        scene_dir.mkdir(parents=True, exist_ok=True)
        blueprint = build_blueprint(identity, generator_cfg)
        values = sample_observations(blueprint, int(identity["master_seed"]), int(cfg["materialization"]["observation_rows"]))
        obs_path = scene_dir / "observations.npy"
        obs_path.write_bytes(npy_bytes(values))
        scm = scene_scm_record(blueprint)
        # The SCM is internal provenance only; it is never placed in the
        # semantic story/input directory and is not used for live scoring.
        scm_path = scene_dir / "scm_internal.json"
        scm_path.write_bytes(canonical(scm))
        metadata = {
            "schema_version": "fourgraph.p1_v3_nano_calibration_execution_scene.v1",
            "study_id": identity["study_id"],
            "contract_scene_id": identity["contract_scene_id"],
            "nodes": list(blueprint.dag.nodes),
            "observation_rows": int(values.shape[0]),
            "observation_sha256": sha256(obs_path.read_bytes()),
            "scm_commitment_sha256": sha256(scm_path.read_bytes()),
            "component_seeds": dict(blueprint.component_seeds),
            "source_identity_sha256": identity["identity_sha256"],
        }
        (scene_dir / "metadata.json").write_bytes(canonical(metadata))
        records.append(metadata)
    manifest = {"schema_version": "fourgraph.p1_v3_nano_calibration_scene_manifest.v1", "scene_count": len(records), "records": records}
    (root / "manifest.json").write_bytes(canonical(manifest))
    return {"status": "PASS_MATERIALIZED", "scene_count": len(records), "writes": len(records), "root": str(root.relative_to(ROOT))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs/p1_v3_nano_medium_calibration_look120_production_runner.yaml")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--materialize", action="store_true")
    args = parser.parse_args()
    if args.materialize and not args.check:
        print(json.dumps(materialize(args.config, True), indent=2))
    else:
        print(json.dumps(materialize(args.config, False), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
