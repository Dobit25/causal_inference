"""Offline-contract implementation for P1-v3 Bootstrap-BOSS evidence.

This module contains deterministic resampling helpers and aggregation logic. It
does not start Tetrad, load a study scene, or execute BOSS by itself.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Iterator, Sequence

import numpy as np

from fourgraph.partial_graph import PartialGraph, consistent_extension, validate_cpdag


PROTOCOL_ID = "causalds_fresh_p1_v3_evidence_selective"
AGGREGATE_SCHEMA = "fourgraph.bootstrap_boss_aggregate.v1"
PARENT_SCHEMA = "fourgraph.bootstrap_boss_parent.v1"
EDGE_SCHEMA = "fourgraph.statistical_edge_evidence.v1"
BOOTSTRAP_RUNS = 200
BOOTSTRAP_SAMPLE_SIZE = 2000
ADJACENCY_GRID = (0.60, 0.70, 0.80, 0.90, 0.95)
DIRECTION_GRID = (0.80, 0.90, 0.95)
_STATES = ("absent", "undirected", "A_to_B", "B_to_A")


class BootstrapBossContractError(ValueError):
    """Raised when frozen Bootstrap-BOSS inputs or outputs fail closed."""


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest().upper()


def _validate_hash(value: str, field: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise BootstrapBossContractError(f"{field} must be a SHA-256 hex string")
    try:
        int(value, 16)
    except ValueError as exc:
        raise BootstrapBossContractError(f"{field} must be hexadecimal") from exc
    if value != value.upper():
        raise BootstrapBossContractError(f"{field} must use uppercase hex")


def derive_bootstrap_seed(
    scene_id: str,
    repetition: int,
    *,
    purpose: str = "row_resample",
) -> int:
    if not scene_id or not isinstance(scene_id, str):
        raise BootstrapBossContractError("scene_id must be non-empty")
    if isinstance(repetition, bool) or not isinstance(repetition, int) or repetition < 0:
        raise BootstrapBossContractError("repetition must be a non-negative integer")
    if not purpose:
        raise BootstrapBossContractError("purpose must be non-empty")
    material = f"{PROTOCOL_ID}|{scene_id}|{repetition}|{purpose}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big", signed=False)


def iter_bootstrap_indices(
    scene_id: str,
    *,
    row_count: int = BOOTSTRAP_SAMPLE_SIZE,
    sample_size: int = BOOTSTRAP_SAMPLE_SIZE,
    repetitions: int = BOOTSTRAP_RUNS,
) -> Iterator[tuple[int, np.ndarray]]:
    for name, value in (
        ("row_count", row_count),
        ("sample_size", sample_size),
        ("repetitions", repetitions),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise BootstrapBossContractError(f"{name} must be a positive integer")
    for repetition in range(repetitions):
        seed = derive_bootstrap_seed(scene_id, repetition)
        generator = np.random.Generator(np.random.PCG64DXSM(seed))
        yield repetition, generator.integers(
            0, row_count, size=sample_size, dtype=np.int64
        )


def standardize_bootstrap_sample(values: np.ndarray, indices: np.ndarray) -> np.ndarray:
    matrix = np.asarray(values, dtype=np.float64)
    selected_indices = np.asarray(indices)
    if matrix.ndim != 2 or matrix.shape[0] <= 0 or matrix.shape[1] <= 0:
        raise BootstrapBossContractError("values must be a non-empty 2D matrix")
    if selected_indices.ndim != 1 or selected_indices.size <= 0:
        raise BootstrapBossContractError("indices must be a non-empty vector")
    if not np.issubdtype(selected_indices.dtype, np.integer):
        raise BootstrapBossContractError("indices must be integers")
    if selected_indices.min() < 0 or selected_indices.max() >= matrix.shape[0]:
        raise BootstrapBossContractError("bootstrap index outside row range")
    sample = matrix[selected_indices].copy()
    if not np.isfinite(sample).all():
        raise BootstrapBossContractError("bootstrap sample contains non-finite values")
    means = sample.mean(axis=0)
    scales = sample.std(axis=0, ddof=0)
    if np.any(scales <= 0) or not np.isfinite(scales).all():
        raise BootstrapBossContractError("bootstrap sample contains a constant column")
    standardized = (sample - means) / scales
    if not np.isfinite(standardized).all():
        raise BootstrapBossContractError("standardization produced non-finite values")
    return standardized


@dataclass(frozen=True)
class BootstrapGraphRun:
    repetition: int
    graph: PartialGraph


def _graph_signature(graph: PartialGraph) -> tuple:
    return graph.nodes, tuple(sorted(graph.directed)), tuple(sorted(graph.undirected))


def _state_for_pair(graph: PartialGraph, left: str, right: str) -> str:
    if (left, right) in graph.undirected:
        return "undirected"
    if (left, right) in graph.directed:
        return "A_to_B"
    if (right, left) in graph.directed:
        return "B_to_A"
    return "absent"


def aggregate_bootstrap_graphs(
    scene_id: str,
    nodes: Sequence[str],
    runs: Iterable[BootstrapGraphRun],
    *,
    expected_runs: int = BOOTSTRAP_RUNS,
) -> dict[str, object]:
    canonical_nodes = tuple(sorted(set(nodes)))
    if tuple(nodes) != canonical_nodes or not canonical_nodes:
        raise BootstrapBossContractError("nodes must be non-empty, unique and sorted")
    if expected_runs != BOOTSTRAP_RUNS:
        raise BootstrapBossContractError("study contract requires exactly 200 runs")
    materialized = list(runs)
    if len(materialized) != expected_runs:
        raise BootstrapBossContractError("expected exactly 200 Bootstrap-BOSS runs")
    indices = [run.repetition for run in materialized]
    if sorted(indices) != list(range(expected_runs)) or len(set(indices)) != expected_runs:
        raise BootstrapBossContractError("run indices must be unique and contiguous 0..199")

    validated_signatures: set[tuple] = set()
    for run in materialized:
        if not isinstance(run, BootstrapGraphRun):
            raise BootstrapBossContractError("run must be BootstrapGraphRun")
        if run.graph.nodes != canonical_nodes:
            raise BootstrapBossContractError("bootstrap graph changed node universe")
        signature = _graph_signature(run.graph)
        if signature not in validated_signatures:
            try:
                validate_cpdag(run.graph)
            except ValueError as exc:
                raise BootstrapBossContractError(
                    "bootstrap graph is not a valid completed PDAG"
                ) from exc
            validated_signatures.add(signature)

    edge_rows: list[dict[str, object]] = []
    for left, right in combinations(canonical_nodes, 2):
        counts = {state: 0 for state in _STATES}
        for run in materialized:
            counts[_state_for_pair(run.graph, left, right)] += 1
        rates = {state: counts[state] / expected_runs for state in _STATES}
        rates["adjacency_stability"] = 1.0 - rates["absent"]
        adjacency_count = expected_runs - counts["absent"]
        conditional = {
            "A_to_B": counts["A_to_B"] / adjacency_count if adjacency_count else None,
            "B_to_A": counts["B_to_A"] / adjacency_count if adjacency_count else None,
            "undirected": counts["undirected"] / adjacency_count if adjacency_count else None,
        }
        edge_rows.append(
            {
                "edge": [left, right],
                "counts": counts,
                "rates": rates,
                "conditional_direction_rates_diagnostic": conditional,
            }
        )
    payload: dict[str, object] = {
        "schema_version": AGGREGATE_SCHEMA,
        "scene_id": scene_id,
        "nodes": list(canonical_nodes),
        "bootstrap_runs": expected_runs,
        "edge_evidence": edge_rows,
    }
    payload["aggregate_sha256"] = _sha256(payload)
    return validate_bootstrap_aggregate(payload)


def validate_bootstrap_aggregate(payload: dict[str, object]) -> dict[str, object]:
    expected_keys = {
        "schema_version", "scene_id", "nodes", "bootstrap_runs",
        "edge_evidence", "aggregate_sha256",
    }
    if set(payload) != expected_keys:
        raise BootstrapBossContractError("aggregate fields do not match contract")
    if payload["schema_version"] != AGGREGATE_SCHEMA:
        raise BootstrapBossContractError("aggregate schema version mismatch")
    if not isinstance(payload["scene_id"], str) or not payload["scene_id"]:
        raise BootstrapBossContractError("aggregate scene_id must be non-empty")
    nodes = payload["nodes"]
    if not isinstance(nodes, list) or nodes != sorted(set(nodes)) or not nodes:
        raise BootstrapBossContractError("aggregate nodes must be sorted and unique")
    if payload["bootstrap_runs"] != BOOTSTRAP_RUNS:
        raise BootstrapBossContractError("aggregate must contain exactly 200 runs")
    rows = payload["edge_evidence"]
    pairs = [list(pair) for pair in combinations(nodes, 2)]
    if not isinstance(rows, list) or [row.get("edge") for row in rows] != pairs:
        raise BootstrapBossContractError("aggregate edge rows must cover all pairs in order")
    for row in rows:
        if set(row) != {"edge", "counts", "rates", "conditional_direction_rates_diagnostic"}:
            raise BootstrapBossContractError("edge aggregate fields do not match contract")
        counts = row["counts"]
        rates = row["rates"]
        if set(counts) != set(_STATES) or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in counts.values()
        ):
            raise BootstrapBossContractError("invalid state counts")
        if sum(counts.values()) != BOOTSTRAP_RUNS:
            raise BootstrapBossContractError("four state counts must sum to 200")
        if set(rates) != set(_STATES) | {"adjacency_stability"}:
            raise BootstrapBossContractError("invalid rate fields")
        for state in _STATES:
            if not math.isclose(rates[state], counts[state] / BOOTSTRAP_RUNS, abs_tol=1e-12):
                raise BootstrapBossContractError("state rate does not match count")
        if not math.isclose(rates["adjacency_stability"], 1.0 - rates["absent"], abs_tol=1e-12):
            raise BootstrapBossContractError("adjacency stability mismatch")
        conditional = row["conditional_direction_rates_diagnostic"]
        if set(conditional) != {"A_to_B", "B_to_A", "undirected"}:
            raise BootstrapBossContractError("invalid conditional direction fields")
        present = BOOTSTRAP_RUNS - counts["absent"]
        for state in ("A_to_B", "B_to_A", "undirected"):
            expected = counts[state] / present if present else None
            if expected is None:
                if conditional[state] is not None:
                    raise BootstrapBossContractError("conditional rate must be null when edge is absent")
            elif not math.isclose(conditional[state], expected, abs_tol=1e-12):
                raise BootstrapBossContractError("conditional direction rate mismatch")
    claimed = payload["aggregate_sha256"]
    _validate_hash(claimed, "aggregate_sha256")
    unhashed = {key: value for key, value in payload.items() if key != "aggregate_sha256"}
    if claimed != _sha256(unhashed):
        raise BootstrapBossContractError("aggregate hash mismatch")
    return payload


def _validate_threshold(value: float, allowed: tuple[float, ...], name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BootstrapBossContractError(f"{name} must be numeric")
    numeric = float(value)
    if numeric not in allowed:
        raise BootstrapBossContractError(f"{name} is outside frozen grid")
    return numeric


def build_stability_parent(
    aggregate: dict[str, object],
    *,
    tau_adjacency: float,
    tau_direction: float,
    config_sha256: str,
    observations_sha256: str,
    seed_manifest_sha256: str,
) -> dict[str, object]:
    validate_bootstrap_aggregate(aggregate)
    tau_adj = _validate_threshold(tau_adjacency, ADJACENCY_GRID, "tau_adjacency")
    tau_dir = _validate_threshold(tau_direction, DIRECTION_GRID, "tau_direction")
    for name, value in (
        ("config_sha256", config_sha256),
        ("observations_sha256", observations_sha256),
        ("seed_manifest_sha256", seed_manifest_sha256),
    ):
        _validate_hash(value, name)

    directed: list[tuple[str, str]] = []
    undirected: list[tuple[str, str]] = []
    evidence: list[dict[str, object]] = []
    for row in aggregate["edge_evidence"]:
        left, right = row["edge"]
        rates = row["rates"]
        adjacency = rates["adjacency_stability"]
        if adjacency < tau_adj:
            status = "absent" if adjacency == 0 else "weak_adjacency"
        elif rates["A_to_B"] >= tau_dir:
            status = "statistical_direction_A_to_B"
            directed.append((left, right))
        elif rates["B_to_A"] >= tau_dir:
            status = "statistical_direction_B_to_A"
            directed.append((right, left))
        else:
            status = "direction_uncertain"
            undirected.append((left, right))
        evidence.append(
            {
                "schema_version": EDGE_SCHEMA,
                "scene_id": aggregate["scene_id"],
                "edge": [left, right],
                "bootstrap": {
                    "runs": BOOTSTRAP_RUNS,
                    "sample_size": BOOTSTRAP_SAMPLE_SIZE,
                    "sampling": "rows_with_replacement",
                    "standardize_each_resample": True,
                },
                "rates": {
                    "absent": rates["absent"],
                    "undirected": rates["undirected"],
                    "A_to_B": rates["A_to_B"],
                    "B_to_A": rates["B_to_A"],
                    "adjacency_stability": adjacency,
                },
                "thresholds": {"adjacency": tau_adj, "direction": tau_dir},
                "status": status,
                "provenance": {
                    "method": "bootstrap_boss",
                    "config_sha256": config_sha256,
                    "observations_sha256": observations_sha256,
                    "seed_manifest_sha256": seed_manifest_sha256,
                },
            }
        )

    try:
        graph = PartialGraph.build(aggregate["nodes"], directed, undirected)
        extension = consistent_extension(graph)
    except ValueError as exc:
        raise BootstrapBossContractError(
            "thresholded stability parent has no consistent DAG extension"
        ) from exc
    graph_payload = graph.to_dict()
    result: dict[str, object] = {
        "schema_version": PARENT_SCHEMA,
        "scene_id": aggregate["scene_id"],
        "aggregate_sha256": aggregate["aggregate_sha256"],
        "thresholds": {"adjacency": tau_adj, "direction": tau_dir},
        "parent_graph": graph_payload,
        "parent_graph_sha256": _sha256(graph_payload),
        "consistent_extension_sha256": _sha256(extension.to_dict()),
        "edge_evidence": evidence,
        "valid": True,
    }
    result["artifact_sha256"] = _sha256(result)
    return result
