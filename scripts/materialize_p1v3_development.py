from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from fourgraph.p1_generation import (
    SceneBlueprint,
    _edge_weights,
    _find_query,
    _weakly_connected,
    graph_motifs,
    npy_bytes,
    sample_observations,
    scene_scm_record,
    seed64,
)
from fourgraph.partial_graph import PartialGraph, dag_to_cpdag_exact


ROOT = Path(__file__).resolve().parents[1]


class MaterializationError(RuntimeError):
    pass


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _line(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load_identities(path: Path) -> list[dict[str, Any]]:
    all_rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    # The frozen exact-identity file also contains calibration/validation rows.
    # Execution plumbing is allowed to materialize only the registered method-
    # development role; it must never silently take the first 30 rows.
    rows = [row for row in all_rows if row.get("role") == "method_development"]
    rows.sort(key=lambda row: row["study_id"])
    if len(rows) != 30 or {row["study_id"] for row in rows} != {f"P1V3SD{i:03d}" for i in range(30)}:
        raise MaterializationError("development identity plan is not exactly P1V3SD000-P1V3SD029")
    return rows


def build_blueprint(identity: dict[str, Any], generator: dict[str, Any]) -> SceneBlueprint:
    study_id = identity["study_id"]
    master_seed = int(identity["master_seed"])
    node_count = int(identity["node_count"])
    nodes = tuple(f"X{i:03d}" for i in range(node_count))
    ranges = generator["edge_count_range"]
    raw_range = ranges.get(node_count, ranges.get(str(node_count)))
    if raw_range is None:
        raise MaterializationError(f"missing edge-count range for {node_count} nodes")
    if isinstance(raw_range, dict):
        raw_range = list(raw_range.values())
    lower, upper = map(int, raw_range)
    rng = np.random.Generator(np.random.PCG64DXSM(seed64(master_seed, study_id, "graph_candidates")))
    accepted = None
    for attempt in range(1, int(generator.get("maximum_attempts_per_scene", 500)) + 1):
        order = tuple(str(node) for node in rng.permutation(nodes))
        possible = [(order[i], order[j]) for i in range(node_count) for j in range(i + 1, node_count)]
        edge_count = int(rng.integers(lower, upper + 1))
        selected = rng.choice(len(possible), size=edge_count, replace=False)
        dag = PartialGraph.build(nodes, directed=[possible[int(position)] for position in selected])
        if not _weakly_connected(dag) or identity["assigned_primary_motif"] not in graph_motifs(dag):
            continue
        cpdag = dag_to_cpdag_exact(dag)
        if len(cpdag.undirected) < int(generator["minimum_oracle_cpdag_unresolved_edges"]):
            continue
        query = _find_query(dag, study_id, identity["contract_scene_id"], identity["query_target_stratum"], seed64(master_seed, study_id, "query_order"))
        if query is not None:
            accepted = attempt, order, dag, cpdag, graph_motifs(dag), query[0], query[1]
            break
    if accepted is None:
        raise MaterializationError(f"generator exhausted for {study_id}")
    attempt, order, dag, cpdag, motifs, treatment, outcome = accepted
    seeds = tuple((component, seed64(master_seed, study_id, component)) for component in ("graph_candidates", "edge_weights", "observations", "query_order"))
    expected = identity["component_seeds"]
    if any(expected.get(name) != value for name, value in seeds):
        raise MaterializationError(f"component seed drift for {study_id}")
    return SceneBlueprint(study_id, identity["contract_scene_id"], node_count, identity["assigned_primary_motif"], identity["noise_family"], identity["query_target_stratum"], attempt, order, dag, cpdag, motifs, treatment, outcome, _edge_weights(dag, master_seed, study_id), seeds)


def materialize(identities: list[dict[str, Any]], generator: dict[str, Any], output_root: Path) -> list[dict[str, Any]]:
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for identity in identities:
        blueprint = build_blueprint(identity, generator)
        values = sample_observations(blueprint, int(identity["master_seed"]), int(generator["observational_sample_size"]))
        scene_dir = output_root / identity["study_id"]
        scene_dir.mkdir(parents=True, exist_ok=True)
        obs_path = scene_dir / "observations.npy"
        obs_path.write_bytes(npy_bytes(values))
        scm = scene_scm_record(blueprint)
        metadata = {"schema_version": "fourgraph.p1v3_execution_scene.v1", "study_id": identity["study_id"], "scene_id": identity["contract_scene_id"], "nodes": list(blueprint.dag.nodes), "observation_rows": int(values.shape[0]), "observation_sha256": _sha(obs_path.read_bytes()), "scm_commitment_sha256": _sha(_line(scm)), "component_seeds": dict(blueprint.component_seeds)}
        meta_path = scene_dir / "metadata.json"
        meta_path.write_bytes(_line(metadata))
        records.append({"study_id": identity["study_id"], "scene_id": identity["contract_scene_id"], "observation_path": str(obs_path.relative_to(ROOT)).replace("\\", "/"), "metadata_path": str(meta_path.relative_to(ROOT)).replace("\\", "/"), "input_sha256": metadata["observation_sha256"], "scm_commitment_sha256": metadata["scm_commitment_sha256"]})
    return records
