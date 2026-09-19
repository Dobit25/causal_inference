from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

import yaml

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex
from fourgraph.p1_generation import scene_scm_record
from fourgraph.successor_generation import (
    SuccessorGenerationError,
    allocate_role,
    generate_blueprint,
    validate_reserved_design_arithmetic,
)
from fourgraph.successor_generation_reference import reference_assignment


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v3_successor_generator_conformance.yaml"
INVENTORY = ROOT / "data/manifests/p1_v3_successor_generator_synthetic.jsonl"
INVALID = ROOT / "data/manifests/p1_v3_successor_generator_invalid.jsonl"
AUDIT = ROOT / "data/manifests/p1_v3_successor_generator_conformance_audit.json"
REPORT = ROOT / "reports/p1_v3_successor_generator_conformance.md"


def canonical_line(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def jsonl(rows: list[dict]) -> bytes:
    return b"".join(canonical_line(row) for row in rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def blueprint_hash(blueprint: object) -> str:
    return sha256_hex(canonical_json_bytes(scene_scm_record(blueprint)))


def marginals(config: dict) -> dict[str, dict[object, int]]:
    raw = config["synthetic_suite"]["role_marginals"]
    return {
        "node_count": {int(key): int(value) for key, value in raw["node_count"].items()},
        "primary_motif": {str(key): int(value) for key, value in raw["primary_motif"].items()},
        "noise_family": {str(key): int(value) for key, value in raw["noise_family"].items()},
        "query_stratum": {str(key): int(value) for key, value in raw["query_stratum"].items()},
    }


def assert_reference_allocation(plans: tuple, expected: dict, seed: int) -> None:
    identifiers = [plan.synthetic_id for plan in plans]
    fields = (
        ("node_count", "node_count", "allocation_node_count"),
        ("primary_motif", "assigned_primary_motif", "allocation_primary_motif"),
        ("noise_family", "noise_family", "allocation_noise_family"),
        ("query_stratum", "query_target_stratum", "allocation_query_stratum"),
    )
    for marginal, attribute, component in fields:
        reference = reference_assignment(identifiers, expected[marginal], seed, component)
        observed = {plan.synthetic_id: getattr(plan, attribute) for plan in plans}
        if observed != reference:
            raise RuntimeError(f"production/reference allocation mismatch: {marginal}")


def build_valid(config: dict) -> tuple[list[dict], dict[str, int]]:
    suite = config["synthetic_suite"]
    family = config["generator_family"]
    role_marginals = marginals(config)
    edge_ranges = {
        int(key): tuple(map(int, value)) for key, value in family["edge_count_range"].items()
    }
    rows: list[dict] = []
    counts = Counter()
    role_hashes: dict[str, list[str]] = {}
    for role_index, role in enumerate(suite["roles"]):
        seed = int(suite["seed"]) + role_index * 1000
        plans = allocate_role(
            role=role,
            namespace=role,
            scene_count=int(suite["scenes_per_role"]),
            scene_number_start=900000 + role_index * 100,
            master_seed=seed,
            marginals=role_marginals,
        )
        replay = allocate_role(
            role=role,
            namespace=role,
            scene_count=int(suite["scenes_per_role"]),
            scene_number_start=900000 + role_index * 100,
            master_seed=seed,
            marginals=role_marginals,
        )
        if plans != replay:
            raise RuntimeError("allocator replay mismatch")
        assert_reference_allocation(plans, role_marginals, seed)
        role_hashes[role] = []
        for plan in plans:
            blueprint, agreements = generate_blueprint(
                plan,
                master_seed=seed,
                edge_count_ranges=edge_ranges,
                minimum_unresolved_edges=int(family["minimum_oracle_cpdag_unresolved_edges"]),
                maximum_attempts=int(family["maximum_attempts_per_scene"]),
            )
            replay_blueprint, replay_agreements = generate_blueprint(
                plan,
                master_seed=seed,
                edge_count_ranges=edge_ranges,
                minimum_unresolved_edges=int(family["minimum_oracle_cpdag_unresolved_edges"]),
                maximum_attempts=int(family["maximum_attempts_per_scene"]),
            )
            first_hash = blueprint_hash(blueprint)
            if first_hash != blueprint_hash(replay_blueprint) or agreements != replay_agreements:
                raise RuntimeError("blueprint replay mismatch")
            if agreements != int(family["task_solver_agreements_per_scene"]):
                raise RuntimeError("task solver agreement gate failed")
            role_hashes[role].append(first_hash)
            counts["scenes"] += 1
            counts["task_solver_agreements"] += agreements
            counts["deterministic_replays"] += 1
            rows.append(
                {
                    "schema_version": "fourgraph.p1_v3_successor_synthetic_case.v1",
                    "role": role,
                    "synthetic_id": plan.synthetic_id,
                    "contract_scene_id": plan.contract_scene_id,
                    "allocation": plan.to_dict(),
                    "generation_attempt": blueprint.generation_attempt,
                    "node_count": blueprint.node_count,
                    "edge_count": len(blueprint.dag.directed),
                    "oracle_cpdag_unresolved_edges": len(blueprint.oracle_cpdag.undirected),
                    "verified_motifs": list(blueprint.motifs),
                    "query": {
                        "treatment": blueprint.query_treatment,
                        "outcome": blueprint.query_outcome,
                        "stratum": blueprint.query_target_stratum,
                    },
                    "task_solver_agreements": agreements,
                    "scm_blueprint_sha256": first_hash,
                    "observation_rows_generated": 0,
                    "study_namespace_used": False,
                }
            )
        changed_blueprint, _ = generate_blueprint(
            plans[0],
            master_seed=seed + 1,
            edge_count_ranges=edge_ranges,
            minimum_unresolved_edges=int(family["minimum_oracle_cpdag_unresolved_edges"]),
            maximum_attempts=int(family["maximum_attempts_per_scene"]),
        )
        if blueprint_hash(changed_blueprint) in role_hashes[role]:
            raise RuntimeError("seed perturbation did not change role fixture")
        counts["seed_perturbation_changes"] += 1

        for feature, expected_counts in role_marginals.items():
            attribute = {
                "node_count": "node_count",
                "primary_motif": "assigned_primary_motif",
                "noise_family": "noise_family",
                "query_stratum": "query_target_stratum",
            }[feature]
            observed = Counter(getattr(plan, attribute) for plan in plans)
            if dict(observed) != expected_counts:
                raise RuntimeError(f"exact marginal gate failed: {role}/{feature}")
            counts["exact_marginal_checks"] += 1
    return rows, dict(counts)


def _real_roles(cohort_design: dict) -> dict[str, dict[str, object]]:
    return {
        name: cohort_design["roles"][name]
        for name in ("method_development", "semantic_calibration", "threshold_validation")
    }


def build_invalid(config: dict, cohort_design: dict) -> list[dict]:
    base_marginals = marginals(config)
    kinds = (
        "reserved_namespace", "non_synthetic_role", "zero_count", "missing_marginal",
        "node_count_total", "motif_total", "negative_count", "real_range_overlap",
        "real_namespace_duplicate", "real_seed_duplicate",
    )
    rows: list[dict] = []
    for index in range(int(config["synthetic_suite"]["invalid_fixtures"])):
        kind = kinds[index % len(kinds)]
        rejected, message = False, ""
        try:
            if kind in {"real_range_overlap", "real_namespace_duplicate", "real_seed_duplicate"}:
                roles = copy.deepcopy(_real_roles(cohort_design))
                if kind == "real_range_overlap":
                    roles["threshold_validation"]["reserved_scene_number_range"] = [121399, 121799]
                elif kind == "real_namespace_duplicate":
                    roles["threshold_validation"]["namespace"] = roles["semantic_calibration"]["namespace"]
                else:
                    roles["threshold_validation"]["master_seed"] = roles["semantic_calibration"]["master_seed"]
                validate_reserved_design_arithmetic(
                    roles, config["allocator"]["reserved_real_namespaces"]
                )
            else:
                role, namespace, count = "SYNBAD", "SYNBAD", 8
                broken = copy.deepcopy(base_marginals)
                if kind == "reserved_namespace":
                    namespace = "P1V3D"
                elif kind == "non_synthetic_role":
                    role = "development"
                elif kind == "zero_count":
                    count = 0
                elif kind == "missing_marginal":
                    broken.pop("noise_family")
                elif kind == "node_count_total":
                    broken["node_count"][5] += 1
                elif kind == "motif_total":
                    broken["primary_motif"]["chain"] -= 1
                elif kind == "negative_count":
                    broken["query_stratum"]["valid_empty"] = -1
                allocate_role(
                    role=role, namespace=namespace, scene_count=count,
                    scene_number_start=990000, master_seed=1, marginals=broken,
                )
        except (SuccessorGenerationError, ValueError) as exc:
            rejected, message = True, str(exc)
        if not rejected:
            raise RuntimeError(f"invalid fixture accepted: {kind}")
        rows.append(
            {
                "schema_version": "fourgraph.p1_v3_successor_invalid_fixture.v1",
                "fixture_id": f"SUCCINVALID{index:03d}",
                "fixture_type": kind,
                "rejected": True,
                "error": message,
            }
        )
    return rows


def build() -> tuple[bytes, bytes, bytes, bytes]:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    parent = ROOT / config["parent"]["audit"]
    design = ROOT / config["parent"]["design"]
    cohort_path = ROOT / config["parent"]["cohort_design"]
    implementation_parent = ROOT / config["generator_family"]["implementation_parent"]
    for path, expected in (
        (parent, config["parent"]["audit_sha256"]),
        (design, config["parent"]["design_sha256"]),
        (cohort_path, config["parent"]["cohort_design_sha256"]),
        (implementation_parent, config["generator_family"]["implementation_parent_sha256"]),
    ):
        if sha256(path) != expected:
            raise RuntimeError(f"dependency hash mismatch: {path.relative_to(ROOT)}")
    parent_record = json.loads(parent.read_text(encoding="utf-8"))
    if parent_record["authorization"]["next_action"] != config["task"]:
        raise RuntimeError("parent does not authorize successor conformance")
    cohort_design = json.loads(cohort_path.read_text(encoding="utf-8"))
    validate_reserved_design_arithmetic(
        _real_roles(cohort_design), config["allocator"]["reserved_real_namespaces"]
    )
    valid_rows, counts = build_valid(config)
    invalid_rows = build_invalid(config, cohort_design)
    suite = config["synthetic_suite"]
    if counts != {
        "scenes": suite["total_scenes"],
        "task_solver_agreements": suite["expected_task_solver_agreements"],
        "deterministic_replays": suite["expected_deterministic_replays"],
        "seed_perturbation_changes": suite["expected_seed_perturbation_changes"],
        "exact_marginal_checks": len(suite["roles"]) * 4,
    }:
        raise RuntimeError(f"synthetic count gate failed: {counts}")
    if len(invalid_rows) != suite["invalid_fixtures"]:
        raise RuntimeError("invalid fixture count gate failed")
    inventory_bytes, invalid_bytes = jsonl(valid_rows), jsonl(invalid_rows)
    report = f"""# P1-v3 successor generator and split-allocator offline conformance

The successor generator/allocator is implemented but cannot materialize the reserved `P1V3D`, `P1V3C` or `P1V3T` namespaces. It validates the frozen 40/400/400 role arithmetic and exact marginal targets without creating their IDs.

Conformance used only {counts['scenes']} synthetic fixtures across `SYNDEV`, `SYNCAL` and `SYNVAL`. Exact node/motif/noise/query margins passed in all {counts['exact_marginal_checks']} role-feature checks. Production allocation matched an independent SHA-256 reference; generation replay matched {counts['deterministic_replays']}/{counts['deterministic_replays']} blueprints, seed perturbation changed all {counts['seed_perturbation_changes']} roles, and production/reference task solvers agreed {counts['task_solver_agreements']}/{counts['task_solver_agreements']}. All {len(invalid_rows)} malformed allocation/range fixtures failed closed.

No observations or semantic stories were generated. No reserved successor scene ID was materialized, no Bootstrap/BOSS job ran, no API call was made, and no historical cohort or final holdout was accessed. The next authorized action is offline runtime/cost-pilot design only; live pilot and study execution remain forbidden.
""".encode("utf-8")
    outputs = ((INVENTORY, inventory_bytes), (INVALID, invalid_bytes), (REPORT, report))
    dependencies = [CONFIG, parent, design, cohort_path, implementation_parent]
    audit = {
        "schema_version": "fourgraph.p1_v3_successor_generator_conformance_audit.v1",
        "task": config["task"],
        "dependencies": [
            {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path)}
            for path in dependencies
        ],
        "implementations": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256(path),
            }
            for path in (
                Path(__file__),
                ROOT / "src/fourgraph/successor_generation.py",
                ROOT / "src/fourgraph/successor_generation_reference.py",
            )
        ],
        "counts": {
            **counts,
            "invalid_fixtures_rejected": len(invalid_rows),
            "real_design_roles_validated_arithmetic_only": 3,
            "real_successor_ids_materialized": 0,
            "observation_rows_generated": 0,
        },
        "outputs": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": len(content),
                "sha256": sha256_hex(content),
            }
            for path, content in outputs
        ],
        "evidence_boundary": config["evidence_boundary"],
        "authorization": config["authorization_after_pass"],
        "verdict": {
            "successor_generator_implemented": True,
            "split_allocator_implemented": True,
            "synthetic_conformance_passed": True,
            "real_successor_generation_authorized": False,
            "bootstrap_boss_execution_authorized": False,
            "semantic_api_calls_authorized": False,
            "final_holdout_authorized": False,
        },
    }
    return inventory_bytes, invalid_bytes, canonical_line(audit), report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    built = build()
    paths = (INVENTORY, INVALID, AUDIT, REPORT)
    if args.check:
        for path, expected in zip(paths, built):
            if not path.exists() or path.read_bytes() != expected:
                raise SystemExit(f"Mismatch: {path.relative_to(ROOT)}")
        print("P1-v3 successor generator conformance reproduces byte-for-byte")
        return 0
    for path, content in zip(paths, built):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    print("P1-v3 successor generator and allocator passed synthetic conformance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
