"""Freeze exactly the registered 40-scene increment from calibration look 120 to 160."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look160_incremental_identity_freeze.yaml"
SCRIPT = Path(__file__).resolve()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def canonical_jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json(row) for row in rows)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def pinned_dependencies(cfg: dict[str, Any]) -> tuple[dict[str, Path], list[dict[str, Any]]]:
    paths: dict[str, Path] = {}
    records: list[dict[str, Any]] = []
    for name, spec in cfg["parents"].items():
        path = ROOT / spec["path"]
        if not path.is_file():
            raise RuntimeError(f"missing dependency: {name}")
        observed = sha256(path)
        if observed != spec["sha256"]:
            raise RuntimeError(f"dependency hash drift: {name}")
        paths[name] = path
        records.append({"name": name, "path": spec["path"], "bytes": path.stat().st_size, "sha256": observed})
    return paths, records


def build() -> dict[Path, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if cfg["status"] != "offline_identity_freeze_only":
        raise RuntimeError("checkpoint status drift")
    pinned, dependencies = pinned_dependencies(cfg)

    all_rows = load_jsonl(pinned["exact_identities"])
    parent_plan = load_json(pinned["exact_identity_plan"])
    parent_audit = load_json(pinned["exact_identity_plan_audit"])
    review = load_json(pinned["look120_review_decision"])
    review_audit = load_json(pinned["look120_review_audit"])
    look120_materialization = load_json(pinned["look120_materialization_manifest"])
    look120_materialization_audit = load_json(pinned["look120_materialization_audit"])
    selection = cfg["selection"]

    start = int(selection["execution_index_start_inclusive"])
    stop = int(selection["execution_index_end_exclusive"])
    ordered_ids = parent_plan["exact_scene_ids_in_execution_order"]
    previous_ids = ordered_ids[:start]
    incremental_ids = ordered_ids[start:stop]
    cumulative_ids = ordered_ids[:stop]
    by_id = {row["study_id"]: row for row in all_rows}
    selected = [by_id[scene_id] for scene_id in incremental_ids]
    materialized_look120_ids = [row["study_id"] for row in look120_materialization["records"]]

    reserved_absent = {
        name: not (ROOT / path).exists()
        for name, path in cfg["reserved_future_outputs"].items()
    }
    development_ids = {row["study_id"] for row in all_rows if row["role"] == "method_development"}
    checks = {
        "parent_identity_plan_pass": parent_audit["status"] == "PASS",
        "look120_review_pass_and_continue": review["status"] == "PASS_OFFLINE_LOOK120_REVIEW"
        and review["decision"] == "CONTINUE_TO_REGISTERED_LOOK_160",
        "look120_review_allows_only_identity_freeze": review["permitted_next_action"]
        == "FREEZE_EXACT_INCREMENTAL_LOOK160_PLAN_FOR_40_NEW_SCENES",
        "look120_review_audit_pass": review_audit["status"]
        == "PASS_OFFLINE_LOOK120_REVIEW_AND_GO_LOOK160_PLANNING_ONLY",
        "look120_materialization_pass": look120_materialization_audit["status"] == "PASS",
        "look120_materialized_ids_match_prefix": materialized_look120_ids == previous_ids,
        "registered_look160_exists": selection["next_registered_look"] in parent_plan["registered_looks"],
        "exact_40_incremental_ids": len(selected) == selection["incremental_scene_count"] == stop - start,
        "exact_160_cumulative_ids": len(cumulative_ids) == selection["cumulative_scene_count"] == stop,
        "increment_is_exact_registered_slice": incremental_ids == ordered_ids[120:160],
        "no_overlap_with_look120": set(previous_ids).isdisjoint(incremental_ids),
        "unique_incremental_ids": len(set(incremental_ids)) == len(incremental_ids),
        "all_identities_resolve": len(selected) == len(incremental_ids),
        "namespace_locked": all(row["study_id"].startswith(selection["namespace"]) for row in selected),
        "role_locked": all(row["role"] == selection["allowed_role"] for row in selected),
        "batch_locked": all(row["batch_id"] == selection["expected_batch_id"] for row in selected),
        "first_registered_look_locked": all(
            row["first_registered_look"] == selection["expected_first_registered_look"] for row in selected
        ),
        "look160_membership_locked": all(selection["next_registered_look"] in row["included_in_registered_looks"] for row in selected),
        "identity_hashes_unique": len({row["identity_sha256"] for row in selected}) == len(selected),
        "component_seed_keys_complete": all(
            set(row["component_seeds"])
            == {"bootstrap_boss", "edge_weights", "graph_candidates", "observations", "query_order", "story_template"}
            for row in selected
        ),
        "component_seed_vectors_unique": len(
            {tuple(sorted(row["component_seeds"].items())) for row in selected}
        ) == len(selected),
        "no_development_overlap": set(incremental_ids).isdisjoint(development_ids),
        "incremental_identities_unmaterialized_in_source": all(row["scene_materialized"] is False for row in selected),
        "no_incremental_diagnostic_reallocation": all(not row["diagnostic_memberships"] for row in selected),
        "reserved_future_outputs_absent": all(reserved_absent.values()),
        "offline_boundary_zero": all(value in (0, False) for value in cfg["boundaries"].values()),
    }
    if not all(checks.values()):
        raise RuntimeError(f"look160 identity freeze failed: {[name for name, passed in checks.items() if not passed]}")

    identities_body = canonical_jsonl(selected)
    plan = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look160_incremental_exact_identity_plan.v1",
        "task": cfg["task"],
        "status": "PASS_FROZEN_EXACT_40_IDENTITIES_OFFLINE",
        "previous_registered_look": selection["previous_registered_look"],
        "next_registered_look": selection["next_registered_look"],
        "incremental_scene_count": len(selected),
        "cumulative_scene_count": len(cumulative_ids),
        "execution_index_range": {"start_inclusive": start, "end_exclusive": stop},
        "batch_id": selection["expected_batch_id"],
        "incremental_scene_ids_in_execution_order": incremental_ids,
        "incremental_identity_sha256_by_scene": {
            row["study_id"]: row["identity_sha256"] for row in selected
        },
        "incremental_component_seeds_by_scene": {
            row["study_id"]: row["component_seeds"] for row in selected
        },
        "cumulative_scene_ids_in_execution_order": cumulative_ids,
        "diagnostics": {
            "incremental_ambiguous_memberships": 0,
            "incremental_nonedge_memberships": 0,
            "policy": cfg["diagnostics"],
        },
        "seed_policy": selection["seed_policy"],
        "reallocation": selection["reallocation"],
        "seed_regeneration": selection["seed_regeneration"],
        "incremental_identities_sha256": hashlib.sha256(identities_body).hexdigest().upper(),
        "dependencies": dependencies
        + [
            {"name": "config", "path": CONFIG.relative_to(ROOT).as_posix(), "bytes": CONFIG.stat().st_size, "sha256": sha256(CONFIG)},
            {"name": "implementation", "path": SCRIPT.relative_to(ROOT).as_posix(), "bytes": SCRIPT.stat().st_size, "sha256": sha256(SCRIPT)},
        ],
        "execution_boundary": cfg["boundaries"],
        "authorization": {
            "identity_freeze_complete": True,
            "materialization_authorized": False,
            "story_generation_authorized": False,
            "statistical_execution_authorized": False,
            "semantic_api_authorized": False,
            "oracle_access_authorized": False,
            "validation_or_holdout_authorized": False,
        },
        "next_action": "P1_V4_LOOK160_INCREMENTAL_MATERIALIZATION_PREFLIGHT_AND_AUTHORIZATION_CHECKPOINT",
    }
    plan_body = canonical_json(plan)
    audit = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look160_incremental_exact_identity_audit.v1",
        "task": cfg["task"],
        "status": "PASS_OFFLINE_EXACT_IDENTITY_FREEZE",
        "checks": checks,
        "counts": {
            "previous_scenes": len(previous_ids),
            "incremental_scenes": len(selected),
            "cumulative_scenes": len(cumulative_ids),
            "incremental_ambiguous_memberships": 0,
            "incremental_nonedge_memberships": 0,
            "new_scenes_materialized": 0,
            "statistical_fits": 0,
            "semantic_api_calls": 0,
            "oracle_reads": 0,
        },
        "node_count_distribution": {
            str(node_count): sum(row["node_count"] == node_count for row in selected)
            for node_count in (5, 6, 7)
        },
        "hashes": {
            "config": sha256(CONFIG),
            "implementation": sha256(SCRIPT),
            "incremental_identities": hashlib.sha256(identities_body).hexdigest().upper(),
            "incremental_plan": hashlib.sha256(plan_body).hexdigest().upper(),
            "parent_exact_identities": sha256(pinned["exact_identities"]),
            "look120_review_decision": sha256(pinned["look120_review_decision"]),
        },
        "reserved_future_outputs_absent": reserved_absent,
        "execution_boundary": cfg["boundaries"],
        "next_action": plan["next_action"],
    }
    report = "\n".join(
        [
            "# P1V4 calibration look-160 incremental exact-identity freeze",
            "",
            "Status: **PASS**. The checkpoint freezes exactly 40 additional calibration identities from execution indices 120–159 of the previously registered 440-scene identity plan.",
            "",
            f"The immutable increment begins with `{incremental_ids[0]}` and ends with `{incremental_ids[-1]}`. Every scene belongs to `semantic_calibration:120-160`; all component seeds and identity hashes were copied byte-for-byte from the frozen parent plan. No seed was generated or reallocated.",
            "",
            "The cumulative look now has an exact identity list of 160 scenes. Ambiguous remains the fixed 120-scene diagnostic established at look 120, and the P1V4 non-edge diagnostic remains excluded; none of the 40 new identities receives a post-hoc diagnostic assignment.",
            "",
            "This checkpoint materialized no scene or story, ran no statistical fit, made no semantic API call, read no Oracle, and accessed neither validation nor holdout. A separate materialization preflight and live authorization are required next.",
            "",
        ]
    ).encode("utf-8")
    return {
        ROOT / cfg["outputs"]["incremental_identities"]: identities_body,
        ROOT / cfg["outputs"]["incremental_plan"]: plan_body,
        ROOT / cfg["outputs"]["audit"]: canonical_json(audit),
        ROOT / cfg["outputs"]["report"]: report,
    }


def write_once(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != content:
        raise RuntimeError(f"non-deterministic artifact drift: {path.relative_to(ROOT)}")
    if not path.exists():
        path.write_bytes(content)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = build()
    if args.check:
        for path, content in generated.items():
            if not path.is_file() or path.read_bytes() != content:
                raise SystemExit(f"artifact drift: {path.relative_to(ROOT)}")
    else:
        for path, content in generated.items():
            write_once(path, content)
    audit_path = ROOT / "data/manifests/p1_v4_independent_calibration_look160_incremental_exact_identity_audit.json"
    audit = json.loads(generated[audit_path])
    print(json.dumps({
        "status": audit["status"],
        "incremental_scenes": audit["counts"]["incremental_scenes"],
        "cumulative_scenes": audit["counts"]["cumulative_scenes"],
        "materialized": audit["counts"]["new_scenes_materialized"],
        "api_calls": audit["counts"]["semantic_api_calls"],
        "check": args.check,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
