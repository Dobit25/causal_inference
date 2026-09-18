from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import yaml

from fourgraph.bootstrap_boss import (
    ADJACENCY_GRID,
    BOOTSTRAP_RUNS,
    DIRECTION_GRID,
    BootstrapBossContractError,
    BootstrapGraphRun,
    aggregate_bootstrap_graphs,
    build_stability_parent,
    iter_bootstrap_indices,
    validate_bootstrap_aggregate,
)
from fourgraph.bootstrap_boss_reference import reference_counts, reference_parent_graph
from fourgraph.partial_graph import PartialGraph


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v3_bootstrap_boss_conformance.yaml"
VALID = ROOT / "data/manifests/p1_v3_bootstrap_boss_conformance.jsonl"
INVALID = ROOT / "data/manifests/p1_v3_bootstrap_boss_invalid.jsonl"
AUDIT = ROOT / "data/manifests/p1_v3_bootstrap_boss_conformance_audit.json"
REPORT = ROOT / "reports/p1_v3_bootstrap_boss_conformance.md"


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def jsonl(rows: list[dict]) -> bytes:
    return b"".join(canonical_json(row) + b"\n" for row in rows)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def synthetic_hash(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest().upper()


def templates(nodes: tuple[str, ...]) -> dict[str, PartialGraph]:
    left, right, helper = nodes[:3]
    return {
        "absent": PartialGraph.build(nodes),
        "undirected": PartialGraph.build(nodes, undirected=[(left, right)]),
        "A_to_B": PartialGraph.build(
            nodes, directed=[(left, right), (helper, right)]
        ),
        "B_to_A": PartialGraph.build(
            nodes, directed=[(right, left), (helper, left)]
        ),
    }


REGIME_COUNTS = {
    "stable_undirected": {"absent": 10, "undirected": 190, "A_to_B": 0, "B_to_A": 0},
    "unstable_adjacency": {"absent": 90, "undirected": 110, "A_to_B": 0, "B_to_A": 0},
    "stable_A_to_B": {"absent": 10, "undirected": 10, "A_to_B": 180, "B_to_A": 0},
    "stable_B_to_A": {"absent": 10, "undirected": 10, "A_to_B": 0, "B_to_A": 180},
    "direction_conflict": {"absent": 20, "undirected": 0, "A_to_B": 90, "B_to_A": 90},
    "usually_absent": {"absent": 180, "undirected": 20, "A_to_B": 0, "B_to_A": 0},
}


def make_runs(case_index: int, regime: str, nodes: tuple[str, ...], seed: int) -> list[BootstrapGraphRun]:
    library = templates(nodes)
    graphs: list[PartialGraph] = []
    for state in ("absent", "undirected", "A_to_B", "B_to_A"):
        graphs.extend([library[state]] * REGIME_COUNTS[regime][state])
    generator = np.random.Generator(np.random.PCG64DXSM(seed + case_index))
    order = generator.permutation(BOOTSTRAP_RUNS)
    return [BootstrapGraphRun(i, graphs[int(source)]) for i, source in enumerate(order)]


def target_row(aggregate: dict) -> dict:
    return next(row for row in aggregate["edge_evidence"] if row["edge"] == ["X000", "X001"])


def exercise_invalid_fixtures(base_nodes: tuple[str, ...], base_runs: list[BootstrapGraphRun], aggregate: dict) -> list[dict]:
    rows: list[dict] = []
    fixture_types = (
        "missing_run", "duplicate_index", "node_mismatch", "non_cpdag",
        "corrupt_hash", "corrupt_count",
    )
    for index in range(30):
        fixture = fixture_types[index % len(fixture_types)]
        rejected = False
        message = ""
        try:
            if fixture == "missing_run":
                aggregate_bootstrap_graphs(f"BAD{index:03d}", base_nodes, base_runs[:-1])
            elif fixture == "duplicate_index":
                broken = list(base_runs)
                broken[-1] = BootstrapGraphRun(198, broken[-1].graph)
                aggregate_bootstrap_graphs(f"BAD{index:03d}", base_nodes, broken)
            elif fixture == "node_mismatch":
                broken = list(base_runs)
                broken[-1] = BootstrapGraphRun(
                    199, PartialGraph.build((*base_nodes, "X999"))
                )
                aggregate_bootstrap_graphs(f"BAD{index:03d}", base_nodes, broken)
            elif fixture == "non_cpdag":
                broken = list(base_runs)
                broken[-1] = BootstrapGraphRun(
                    199,
                    PartialGraph.build(
                        base_nodes,
                        directed=[(base_nodes[0], base_nodes[1])],
                        undirected=[(base_nodes[1], base_nodes[2])],
                    ),
                )
                aggregate_bootstrap_graphs(f"BAD{index:03d}", base_nodes, broken)
            elif fixture == "corrupt_hash":
                broken = copy.deepcopy(aggregate)
                broken["aggregate_sha256"] = "0" * 64
                validate_bootstrap_aggregate(broken)
            elif fixture == "corrupt_count":
                broken = copy.deepcopy(aggregate)
                broken["edge_evidence"][0]["counts"]["absent"] += 1
                validate_bootstrap_aggregate(broken)
        except BootstrapBossContractError as exc:
            rejected = True
            message = str(exc)
        if not rejected:
            raise RuntimeError(f"Invalid fixture was accepted: {fixture}")
        rows.append(
            {
                "schema_version": "fourgraph.bootstrap_boss_invalid_fixture.v1",
                "fixture_id": f"BBINVALID{index:03d}",
                "fixture_type": fixture,
                "rejected": True,
                "error": message,
            }
        )
    return rows


def build() -> tuple[bytes, bytes, bytes, bytes]:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    protocol = ROOT / config["protocol"]["config"]
    freeze = ROOT / config["protocol"]["freeze_manifest"]
    if sha256(protocol) != config["protocol"]["config_sha256"]:
        raise RuntimeError("Protocol config hash mismatch")
    if sha256(freeze) != config["protocol"]["freeze_manifest_sha256"]:
        raise RuntimeError("Protocol freeze hash mismatch")
    frozen_audit = json.loads(freeze.read_text(encoding="utf-8"))
    if frozen_audit["authorization"]["next_action"] != config["task"]:
        raise RuntimeError("Protocol does not authorize this offline task")

    valid_rows: list[dict] = []
    aggregate_agreements = 0
    parent_agreements = 0
    order_invariance = 0
    node_order_normalization = 0
    input_immutability = 0
    regimes = config["suite"]["regimes"]
    seed = config["suite"]["seed"]
    first_fixture = None
    for case_index in range(config["suite"]["cases"]):
        regime = regimes[case_index % len(regimes)]
        node_count = config["suite"]["node_counts"][case_index % 5]
        nodes = tuple(f"X{i:03d}" for i in range(node_count))
        runs = make_runs(case_index, regime, nodes, seed)
        before = [(run.repetition, run.graph.to_dict()) for run in runs]
        aggregate = aggregate_bootstrap_graphs(
            f"BBSYN{case_index:03d}", nodes, runs
        )
        reference = reference_counts(nodes, runs)
        production_counts = {
            tuple(row["edge"]): row["counts"] for row in aggregate["edge_evidence"]
        }
        if production_counts != reference:
            raise RuntimeError("Production/reference aggregation disagreement")
        aggregate_agreements += 1
        reordered = aggregate_bootstrap_graphs(
            f"BBSYN{case_index:03d}", nodes, reversed(runs)
        )
        if aggregate != reordered:
            raise RuntimeError("Aggregation depends on run order")
        order_invariance += 1
        normalized_runs = [
            BootstrapGraphRun(
                run.repetition,
                PartialGraph.build(
                    reversed(run.graph.nodes),
                    run.graph.directed,
                    run.graph.undirected,
                ),
            )
            for run in runs
        ]
        normalized = aggregate_bootstrap_graphs(
            f"BBSYN{case_index:03d}", nodes, normalized_runs
        )
        if aggregate != normalized:
            raise RuntimeError("Aggregation depends on node input order")
        node_order_normalization += 1
        after = [(run.repetition, run.graph.to_dict()) for run in runs]
        if before != after:
            raise RuntimeError("Aggregation mutated inputs")
        input_immutability += 1

        decisions: list[dict] = []
        for tau_adj in ADJACENCY_GRID:
            for tau_dir in DIRECTION_GRID:
                production = build_stability_parent(
                    aggregate,
                    tau_adjacency=tau_adj,
                    tau_direction=tau_dir,
                    config_sha256=config["protocol"]["config_sha256"],
                    observations_sha256=synthetic_hash(f"obs:{case_index}"),
                    seed_manifest_sha256=synthetic_hash(f"seed:{case_index}"),
                )
                expected = reference_parent_graph(
                    nodes,
                    reference,
                    tau_adjacency=tau_adj,
                    tau_direction=tau_dir,
                )
                if production["parent_graph"] != expected.to_dict():
                    raise RuntimeError("Production/reference parent disagreement")
                parent_agreements += 1
                decisions.append(
                    {
                        "tau_adjacency": tau_adj,
                        "tau_direction": tau_dir,
                        "parent_graph": production["parent_graph"],
                        "parent_graph_sha256": production["parent_graph_sha256"],
                    }
                )
        row = {
            "schema_version": "fourgraph.bootstrap_boss_conformance_case.v1",
            "case_id": f"BBSYN{case_index:03d}",
            "regime": regime,
            "node_count": node_count,
            "bootstrap_runs": BOOTSTRAP_RUNS,
            "target_edge": ["X000", "X001"],
            "target_counts": target_row(aggregate)["counts"],
            "target_rates": target_row(aggregate)["rates"],
            "aggregate_sha256": aggregate["aggregate_sha256"],
            "threshold_decisions": decisions,
            "production_reference_agreement": True,
            "run_order_invariant": True,
            "node_input_order_normalized": True,
            "input_immutable": True,
        }
        valid_rows.append(row)
        if first_fixture is None:
            first_fixture = (nodes, runs, aggregate)

    invalid_rows = exercise_invalid_fixtures(*first_fixture)

    index_diagnostics = []
    for scene in ("BBSYN_SEED_A", "BBSYN_SEED_B"):
        for repetition, indices in iter_bootstrap_indices(scene, repetitions=2):
            index_diagnostics.append(
                {
                    "scene": scene,
                    "repetition": repetition,
                    "length": int(indices.size),
                    "unique_rows": int(np.unique(indices).size),
                    "sha256": sha256_bytes(indices.astype("<i8").tobytes()),
                }
            )

    valid_bytes = jsonl(valid_rows)
    invalid_bytes = jsonl(invalid_rows)
    report = f"""# P1-v3 Bootstrap-BOSS offline implementation and conformance

Implemented deterministic size-N row resampling, per-resample standardization, strict 200-run aggregation, four-state edge frequencies, thresholded stability-parent construction and fail-closed consistent-extension validation. This layer does not execute BOSS by itself; a later runner must supply one CPDAG for each registered bootstrap index.

The synthetic suite contains {len(valid_rows)} cases across six regimes and 3–7 nodes. Production and independently structured reference aggregation agreed on {aggregate_agreements}/{len(valid_rows)} cases. Parent graphs agreed on {parent_agreements}/{len(valid_rows) * 15} threshold decisions. Run-order invariance, node-input-order normalization and input immutability each passed {len(valid_rows)}/{len(valid_rows)}. All {len(invalid_rows)}/{len(invalid_rows)} malformed fixtures failed closed, including extendable PDAGs that were not completed PDAGs.

No observational study table was loaded, Tetrad/BOSS was not started, no successor scene was generated, no semantic API was called and the final holdout remained sealed. The next authorized step is offline implementation/conformance of six-vote semantic reliability and the statistical-veto decision table; executing 200 BOSS runs on study scenes remains forbidden.
""".encode("utf-8")

    audit = {
        "schema_version": "fourgraph.p1_v3_bootstrap_boss_conformance_audit.v1",
        "task": config["task"],
        "dependencies": [
            {"path": CONFIG.relative_to(ROOT).as_posix(), "sha256": sha256(CONFIG)},
            {"path": config["protocol"]["config"], "sha256": sha256(protocol)},
            {"path": config["protocol"]["freeze_manifest"], "sha256": sha256(freeze)},
            {"path": "src/fourgraph/bootstrap_boss.py", "sha256": sha256(ROOT / "src/fourgraph/bootstrap_boss.py")},
            {"path": "src/fourgraph/bootstrap_boss_reference.py", "sha256": sha256(ROOT / "src/fourgraph/bootstrap_boss_reference.py")},
            {"path": config["contracts"]["aggregate"], "sha256": sha256(ROOT / config["contracts"]["aggregate"])},
            {"path": config["contracts"]["thresholded_parent"], "sha256": sha256(ROOT / config["contracts"]["thresholded_parent"])},
            {"path": config["contracts"]["edge_evidence"], "sha256": sha256(ROOT / config["contracts"]["edge_evidence"])},
        ],
        "implementation": {
            "path": "scripts/build_p1_v3_bootstrap_boss_conformance.py",
            "sha256": sha256(Path(__file__)),
        },
        "counts": {
            "synthetic_cases": len(valid_rows),
            "bootstrap_graph_states_aggregated": len(valid_rows) * BOOTSTRAP_RUNS,
            "production_reference_aggregate_agreements": aggregate_agreements,
            "threshold_parent_decisions": len(valid_rows) * 15,
            "production_reference_parent_agreements": parent_agreements,
            "run_order_invariance_passes": order_invariance,
            "node_input_order_normalization_passes": node_order_normalization,
            "input_immutability_passes": input_immutability,
            "invalid_fixtures_rejected": len(invalid_rows),
        },
        "index_diagnostics": index_diagnostics,
        "outputs": [
            {"path": VALID.relative_to(ROOT).as_posix(), "bytes": len(valid_bytes), "sha256": sha256_bytes(valid_bytes)},
            {"path": INVALID.relative_to(ROOT).as_posix(), "bytes": len(invalid_bytes), "sha256": sha256_bytes(invalid_bytes)},
            {"path": REPORT.relative_to(ROOT).as_posix(), "bytes": len(report), "sha256": sha256_bytes(report)},
        ],
        "evidence_boundary": config["evidence_boundary"],
        "authorization": config["authorization_after_pass"],
        "verdict": {
            "offline_implementation_complete": True,
            "synthetic_conformance_passed": True,
            "study_scene_bootstrap_execution_authorized": False,
            "successor_cohort_generation_authorized": False,
            "semantic_api_calls_authorized": False,
            "final_holdout_access_authorized": False,
        },
    }
    return valid_bytes, invalid_bytes, canonical_json(audit) + b"\n", report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    built = build()
    outputs = tuple(zip((VALID, INVALID, AUDIT, REPORT), built))
    if args.check:
        for path, expected in outputs:
            if not path.exists() or path.read_bytes() != expected:
                raise SystemExit(f"Mismatch: {path.relative_to(ROOT)}")
        print("Bootstrap-BOSS synthetic conformance reproduces byte-for-byte")
        return 0
    for path, content in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    print("Bootstrap-BOSS offline implementation passed synthetic conformance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
