"""Audit and deterministically replay the P1V4 look-160 40-scene materialization."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_p1_v4_independent_calibration_look120_materialization import construct_scene  # noqa: E402


CONFIG = ROOT / "configs/p1_v4_look160_incremental_materialization_execution_audit.yaml"
SCRIPT = Path(__file__).resolve()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def sha_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest().upper()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical(row) for row in rows)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def build() -> dict[Path, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    dependencies: list[dict[str, Any]] = []
    paths: dict[str, Path] = {}
    for name, spec in cfg["parents"].items():
        path = ROOT / spec["path"]
        observed = sha(path) if path.is_file() else None
        checks[f"{name}_hash"] = observed == spec["sha256"]
        dependencies.append({"name": name, "path": spec["path"], "sha256": observed})
        paths[name] = path

    authorization = load_json(paths["live_authorization"])
    materialization = load_json(paths["materialization_manifest"])
    public_inputs = load_json(paths["public_input_manifest"])
    plan = load_json(paths["incremental_plan"])
    identity_by_id = {row["study_id"]: row for row in load_rows(paths["incremental_identities"])}
    exact_ids = plan["incremental_scene_ids_in_execution_order"]
    identities = [identity_by_id[scene_id] for scene_id in exact_ids]
    generation = yaml.safe_load(paths["generation_contract"].read_text(encoding="utf-8"))["generation"]
    story_config = yaml.safe_load(paths["story_protocol"].read_text(encoding="utf-8"))
    expected = cfg["expected"]

    inventory: list[dict[str, Any]] = []
    replay_matches: list[bool] = []
    leakage_passes: list[bool] = []
    for identity in identities:
        contents, _, records = construct_scene(identity, generation, story_config)
        scene_dir = ROOT / expected["generated_scene_root"] / identity["study_id"]
        public_dir = ROOT / expected["public_story_root"] / identity["study_id"]
        for kind, name in (("observation", "observations.npy"), ("metadata", "metadata.json"), ("alias_map", "alias_map.json")):
            path = scene_dir / name
            expected_bytes = contents[name]
            matches = path.is_file() and path.read_bytes() == expected_bytes
            replay_matches.append(matches)
            inventory.append({"study_id": identity["study_id"], "kind": kind, "variant": None, "path": path.relative_to(ROOT).as_posix(), "bytes": len(expected_bytes), "sha256": sha_bytes(expected_bytes), "replay_match": matches})
        for record in records:
            variant = record["variant"]
            name = f"story_{variant}.json"
            path = public_dir / name
            expected_bytes = contents[name]
            matches = path.is_file() and path.read_bytes() == expected_bytes
            replay_matches.append(matches)
            public = json.loads(expected_bytes)["builder_input"]
            story = public["story"]
            lowered = story.lower()
            leakage = not bool(re.search(r"\bX[0-9]{3}\b", story)) and not any(
                term in lowered for term in ("oracle", "cpdag", "ground truth", "holdout", "bootstrap", "p-value")
            )
            leakage_passes.append(leakage)
            inventory.append({"study_id": identity["study_id"], "kind": "public_story", "variant": variant, "path": path.relative_to(ROOT).as_posix(), "bytes": len(expected_bytes), "sha256": sha_bytes(expected_bytes), "replay_match": matches, "leakage_pass": leakage})

    scene_records = materialization["records"]
    story_records = public_inputs["records"]
    variants = {(row["study_id"], row["variant"]) for row in story_records}
    expected_variants = {(scene_id, variant) for scene_id in exact_ids for variant in expected["variants"]}
    disk_generated = [path for path in (ROOT / expected["generated_scene_root"]).rglob("*") if path.is_file()]
    disk_public = [path for path in (ROOT / expected["public_story_root"]).rglob("*") if path.is_file()]
    public_text = b"".join(path.read_bytes() for path in disk_public)
    checks.update({
        "authorization_scope_valid": authorization["status"] == "PASS_SCOPED_LOOK160_INCREMENTAL_MATERIALIZATION_AUTHORIZATION" and authorization["authorization"]["exact_scene_ids"] == exact_ids,
        "exact_scene_manifest_order": [row["study_id"] for row in scene_records] == exact_ids,
        "exact_scene_count": len(scene_records) == expected["scenes"] == 40,
        "exact_public_story_count": len(story_records) == expected["public_stories"] == 120,
        "all_variants_complete": variants == expected_variants,
        "exact_disk_file_counts": len(disk_generated) == 120 and len(disk_public) == 120 and len(inventory) == expected["files_total"] == 240,
        "all_artifacts_replay_byte_exact": all(replay_matches) and len(replay_matches) == 240,
        "all_public_stories_pass_leakage": all(leakage_passes) and len(leakage_passes) == 120,
        "no_oracle_graph_persisted_publicly": b'"oracle_dag"' not in public_text and b'"oracle_cpdag"' not in public_text,
        "manifest_observation_hashes_match": all(sha(ROOT / row["observation_path"]) == row["observation_sha256"] for row in scene_records),
        "manifest_story_hashes_match": all(sha(ROOT / row["artifact_path"]) == row["artifact_sha256"] for row in story_records),
        "scientific_boundary_respected": all(value in (0, False) for value in cfg["scientific_boundary"].values()),
    })
    if not all(checks.values()):
        raise RuntimeError(f"materialization audit failed: {[key for key, value in checks.items() if not value]}")

    inventory.sort(key=lambda row: (exact_ids.index(row["study_id"]), row["kind"], row["variant"] or ""))
    inventory_body = jsonl(inventory)
    audit = {
        "schema_version": "fourgraph.p1_v4_look160_incremental_materialization_execution_audit.v1",
        "task": cfg["task"],
        "status": "PASS_MATERIALIZATION_EXECUTION",
        "checks": checks,
        "counts": {"scenes": 40, "observations": 40, "metadata": 40, "alias_maps": 40, "public_stories": 120, "files": 240, "statistical_fits": 0, "semantic_api_calls": 0, "oracle_scoring_reads": 0},
        "variant_counts": {variant: sum(row["variant"] == variant for row in story_records) for variant in expected["variants"]},
        "hashes": {"config": sha(CONFIG), "implementation": sha(SCRIPT), "materialization_manifest": sha(paths["materialization_manifest"]), "public_input_manifest": sha(paths["public_input_manifest"]), "artifact_inventory": hashlib.sha256(inventory_body).hexdigest().upper()},
        "dependencies": dependencies,
        "scientific_boundary": cfg["scientific_boundary"],
        "next_action": "P1_V4_LOOK160_INCREMENTAL_STATISTICAL_PARENT_PREFLIGHT_AND_AUTHORIZATION_CHECKPOINT",
    }
    report = """# P1V4 look-160 incremental materialization execution

Status: **PASS**. Exactly 40 frozen calibration scenes were materialized with 40 observational arrays, 40 metadata records, 40 internal alias maps, and 120 public Full/Partial/Ambiguous story artifacts.

All 240 files replay byte-for-byte from the frozen identities, component seeds, generator and T19 story protocol. Public-story leakage checks passed. No statistical fit, semantic API call, Oracle scoring read, validation/holdout access or downstream reasoning occurred.

The next permitted step is a separate statistical-parent preflight and authorization checkpoint.
""".encode("utf-8")
    return {
        ROOT / cfg["outputs"]["inventory"]: inventory_body,
        ROOT / cfg["outputs"]["audit"]: canonical(audit),
        ROOT / cfg["outputs"]["report"]: report,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = build()
    for path, content in generated.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != content:
                raise SystemExit(f"artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.read_bytes() != content:
                raise SystemExit(f"non-deterministic artifact drift: {path.relative_to(ROOT)}")
            if not path.exists():
                path.write_bytes(content)
    audit_path = ROOT / yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["outputs"]["audit"]
    audit = json.loads(generated[audit_path])
    print(json.dumps({"status": audit["status"], "scenes": 40, "files": 240, "replay": "byte_exact", "api_calls": 0, "check": args.check}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
