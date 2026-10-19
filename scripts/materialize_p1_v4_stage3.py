"""Authorized P1V4 materializer; stores commitments, never an Oracle graph."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from fourgraph.p1_generation import SceneBlueprint, _edge_weights, _find_query, _weakly_connected, graph_motifs, npy_bytes, sample_observations, scene_scm_record
from fourgraph.partial_graph import PartialGraph, dag_to_cpdag_exact

ROOT = Path(__file__).resolve().parents[1]


def _line(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def seed64(master_seed: int, study_id: str, component: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{master_seed}|{study_id}|{component}".encode()).digest()[:8], "big")


def load_development_identities(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    rows = sorted((row for row in rows if row.get("role") == "method_development"), key=lambda row: row["study_id"])
    expected = {f"P1V4SD{i:03d}" for i in range(30)}
    if len(rows) != 30 or {row["study_id"] for row in rows} != expected:
        raise RuntimeError("P1V4 materializer requires exactly P1V4SD000-P1V4SD029")
    if any(row.get("scene_materialized") is not False for row in rows):
        raise RuntimeError("identity manifest says a P1V4 study scene was already materialized")
    return rows


def build_blueprint(identity: dict[str, Any], generation: dict[str, Any]) -> SceneBlueprint:
    study_id, master, count = identity["study_id"], int(identity["master_seed"]), int(identity["node_count"])
    nodes = tuple(f"X{i:03d}" for i in range(count))
    lower, upper = map(int, generation["edge_count_range"].get(count, generation["edge_count_range"].get(str(count))))
    rng = np.random.Generator(np.random.PCG64DXSM(seed64(master, study_id, "graph_candidates")))
    accepted = None
    for attempt in range(1, 10001):
        order = tuple(str(value) for value in rng.permutation(nodes))
        possible = [(order[i], order[j]) for i in range(count) for j in range(i + 1, count)]
        selected = rng.choice(len(possible), size=int(rng.integers(lower, upper + 1)), replace=False)
        dag = PartialGraph.build(nodes, directed=[possible[int(index)] for index in selected])
        if not _weakly_connected(dag) or identity["primary_motif"] not in graph_motifs(dag):
            continue
        cpdag = dag_to_cpdag_exact(dag)
        if len(cpdag.undirected) < int(generation["minimum_oracle_cpdag_unresolved_edges"]):
            continue
        query = _find_query(dag, study_id, identity["contract_scene_id"], identity["query_stratum"], seed64(master, study_id, "query_order"))
        if query is not None:
            accepted = attempt, order, dag, cpdag, tuple(graph_motifs(dag)), query[0], query[1]
            break
    if accepted is None:
        raise RuntimeError(f"P1V4 generator exhausted: {study_id}")
    attempt, order, dag, cpdag, motifs, treatment, outcome = accepted
    expected = identity["component_seeds"]
    for component in ("graph_candidates", "edge_weights", "observations", "query_order"):
        if expected.get(component) != seed64(master, study_id, component):
            raise RuntimeError(f"P1V4 seed drift for {study_id}/{component}")
    return SceneBlueprint(study_id, identity["contract_scene_id"], count, identity["primary_motif"], identity["noise_family"], identity["query_stratum"], attempt, order, dag, cpdag, motifs, treatment, outcome, _edge_weights(dag, master, study_id), tuple((name, seed64(master, study_id, name)) for name in ("graph_candidates", "edge_weights", "observations", "query_order")))


def materialize(identities: list[dict[str, Any]], generation: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    root.mkdir(parents=True, exist_ok=True)
    records = []
    for identity in identities:
        blueprint = build_blueprint(identity, generation)
        values = sample_observations(blueprint, int(identity["master_seed"]), int(generation["observational_sample_size"]))
        directory = root / identity["study_id"]; directory.mkdir(parents=True, exist_ok=True)
        observation = directory / "observations.npy"; observation.write_bytes(npy_bytes(values))
        # The SCM is used only to create a nonreversible commitment; no DAG is persisted for this stage.
        commitment = _sha(_line(scene_scm_record(blueprint)))
        metadata = {"schema_version": "fourgraph.p1_v4_execution_scene.v1", "study_id": identity["study_id"], "scene_id": identity["contract_scene_id"], "nodes": list(blueprint.dag.nodes), "observation_rows": int(values.shape[0]), "observation_sha256": _sha(observation.read_bytes()), "scm_commitment_sha256": commitment, "component_seeds": dict(blueprint.component_seeds)}
        meta = directory / "metadata.json"; meta.write_bytes(_line(metadata))
        records.append({"study_id": identity["study_id"], "scene_id": identity["contract_scene_id"], "observation_path": observation.relative_to(ROOT).as_posix(), "metadata_path": meta.relative_to(ROOT).as_posix(), "input_sha256": metadata["observation_sha256"], "scm_commitment_sha256": commitment})
    return records
