"""Build or byte-check the fully offline T21 v3-B conformance artifacts."""

from __future__ import annotations

import argparse
import copy
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fourgraph.edge_selective import (  # noqa: E402
    EDGE_SELECTIVE_SCHEMA,
    PARTIAL_GRAPH_SCHEMA,
    prepare_edge_selective,
    solve_edge_selective,
    solve_prepared_edge_selective,
    validate_edge_selective_output,
)
from fourgraph.edge_selective_reference import (  # noqa: E402
    prepare_reference_edge_selective,
    solve_prepared_reference,
)
from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.hybrid_h2 import H2ContractError, PREFERENCE_SCHEMA, graph_sha256  # noqa: E402
from fourgraph.partial_graph import PartialGraph, consistent_extension, dag_to_cpdag_exact  # noqa: E402


CONFIG = ROOT / "configs/t21_v3b_edge_selective_conformance.yaml"
VALID = ROOT / "data/manifests/t21_v3b_edge_selective_valid.jsonl"
INVALID = ROOT / "data/manifests/t21_v3b_edge_selective_invalid.jsonl"
AUDIT = ROOT / "data/manifests/t21_v3b_edge_selective_audit.json"
REPORT = ROOT / "reports/t21_v3b_edge_selective_conformance.md"
SCRIPT = Path(__file__).resolve()


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def _line(value: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _entry(path: Path, body: bytes | None = None) -> dict[str, Any]:
    payload = path.read_bytes() if body is None else body
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": len(payload), "sha256": sha256_hex(payload)}


def _boundary(config: Mapping[str, Any]) -> None:
    parent = _load_json(ROOT / str(config["parent_freeze"]))
    verdict = parent["verdict"]
    if not verdict["t21_v3a_complete"] or not verdict["t21_v3b_offline_implementation_authorized"]:
        raise RuntimeError("T21 v3-A does not authorize v3-B")
    if verdict["live_model_calls_authorized"] or verdict["validation_generation_authorized"] or verdict["p1_holdout_authorized"]:
        raise RuntimeError("T21 v3-A execution boundary drift")
    boundary = config["execution_boundary"]
    forbidden = (
        boundary["api_calls"], boundary["provider_imports"], boundary["validation_scenes_generated"],
        boundary["p1_development_scenes_accessed"], boundary["p1_holdout_scenes_accessed"],
        boundary["threshold_selected_on_study_data"], boundary["llm_scd_reasoner_executed"],
    )
    if any(forbidden):
        raise RuntimeError("T21 v3-B must remain completely offline")
    if boundary["next_action_if_pass"] != "T21_V3C_GENERATE_AND_FREEZE_NEW_20_VALIDATION_SCENES":
        raise RuntimeError("T21 v3-B next action drift")


def _dag(index: int, count: int, seed: int) -> PartialGraph:
    nodes = [f"X{i:03d}" for i in range(count)]
    rng = random.Random(seed + index * 1009)
    order = nodes[:]
    rng.shuffle(order)
    family = index % 5
    if family == 0:  # chain / mediator
        edges = {(order[i], order[i + 1]) for i in range(count - 1)}
    elif family == 1:  # fork with tail
        edges = {(order[0], order[1]), (order[0], order[2])}
        edges |= {(order[i], order[i + 1]) for i in range(2, count - 1)}
    elif family == 2:  # collider with tail
        edges = {(order[0], order[2]), (order[1], order[2])}
        edges |= {(order[i], order[i + 1]) for i in range(2, count - 1)}
    elif family == 3:  # shielded triangle plus tail
        edges = {(order[0], order[1]), (order[0], order[2]), (order[1], order[2])}
        edges |= {(order[i], order[i + 1]) for i in range(2, count - 1)}
    else:  # sparse branching chain
        edges = {(order[i], order[i + 1]) for i in range(count - 1)}
        if count >= 4:
            edges.add((order[0], order[3]))
    return PartialGraph.build(nodes, edges)


def _artifact(parent: PartialGraph, regime: str, seed: int) -> dict[str, Any]:
    anchor = consistent_extension(parent)
    rng = random.Random(seed)
    rows = []
    for position, (left, right) in enumerate(sorted(parent.undirected)):
        forward = (left, right) in anchor.directed
        if regime == "strong_consistent":
            probability = 0.999 if forward else 0.001
        elif regime == "weak_consistent":
            probability = 0.80 if forward else 0.20
        elif regime == "uniform_ambiguous":
            probability = 0.50
        elif regime == "sparse_high_confidence":
            probability = (0.999 if forward else 0.001) if position == 0 else 0.50
        elif regime == "mixed_conflict":
            probability = [0.001, 0.20, 0.50, 0.80, 0.999][(position + rng.randrange(5)) % 5]
        elif regime == "incompatible_high_confidence":
            preferred_forward = position % 2 == 0
            probability = 0.999 if preferred_forward else 0.001
        else:
            raise ValueError(regime)
        rows.append({"left": left, "right": right, "probability_left_causes_right": probability})
    return {"schema_version": PREFERENCE_SCHEMA, "parent_graph_sha256": graph_sha256(parent), "preferences": rows}


def _core(rows: list[Mapping[str, Any]]) -> list[tuple[Any, ...]]:
    return [(row["left"], row["right"], row["source"], row["target"], row["direction_source"]) for row in rows]


def _joint_selection_probe(index: int) -> tuple[PartialGraph, dict[str, Any]]:
    nodes = [f"P{index}{suffix}" for suffix in ("A", "B", "C")]
    left, middle, right = nodes
    parent = PartialGraph.build(nodes, undirected=[(left, middle), (left, right), (middle, right)])
    artifact = {
        "schema_version": PREFERENCE_SCHEMA,
        "parent_graph_sha256": graph_sha256(parent),
        "preferences": [
            {"left": left, "right": middle, "probability_left_causes_right": 0.999},
            {"left": left, "right": right, "probability_left_causes_right": 0.001},
            {"left": middle, "right": right, "probability_left_causes_right": 0.999},
        ],
    }
    return parent, artifact


def _agree(production: Mapping[str, Any], reference: Mapping[str, Any]) -> None:
    exact = (
        "consistent_extension_count", "compatible_extensions_after_selection", "output_graph", "output_graph_sha256"
    )
    for key in exact:
        if production[key] != reference[key]:
            raise RuntimeError(f"Production/reference mismatch: {key}")
    for key in ("extension_scores", "extension_weights"):
        if len(production[key]) != len(reference[key]) or any(
            not math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-12)
            for a, b in zip(production[key], reference[key])
        ):
            raise RuntimeError(f"Production/reference float mismatch: {key}")
    for key in ("candidate_directions", "selected_directions"):
        left = [(r["source"], r["target"]) for r in production[key]]
        right = [(r["source"], r["target"]) for r in reference[key]]
        if left != right:
            raise RuntimeError(f"Production/reference direction mismatch: {key}")
    if _core(production["edge_provenance"]) != _core(reference["edge_provenance_core"]):
        raise RuntimeError("Production/reference provenance mismatch")


def _valid(config: Mapping[str, Any]) -> tuple[list[dict[str, Any]], Counter[str]]:
    suite = config["suite"]
    regimes = [name for name, count in suite["preference_regimes"].items() for _ in range(int(count))]
    rng = random.Random(int(config["master_seed"]))
    rng.shuffle(regimes)
    node_counts = [value for value in suite["node_counts"] for _ in range(int(suite["cases_per_node_count"]))]
    thresholds = [(a, b) for a in suite["threshold_grid"]["semantic_confidence"] for b in suite["threshold_grid"]["global_stability"]]
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for index, (node_count, regime) in enumerate(zip(node_counts, regimes)):
        oracle = _dag(index, int(node_count), int(config["master_seed"]))
        parent = dag_to_cpdag_exact(oracle)
        artifact = _artifact(parent, regime, int(config["master_seed"]) + index)
        before = (parent.to_dict(), canonical_json_bytes(artifact))
        production_problem = prepare_edge_selective(parent, artifact)
        reference_problem = prepare_reference_edge_selective(parent, artifact)
        decisions = []
        for tau_semantic, tau_global in thresholds:
            production = solve_prepared_edge_selective(
                production_problem, tau_semantic=float(tau_semantic), tau_global=float(tau_global)
            )
            reference = solve_prepared_reference(
                reference_problem, tau_semantic=float(tau_semantic), tau_global=float(tau_global)
            )
            _agree(production, reference)
            validate_edge_selective_output(parent, production)
            counts["decisions"] += 1
            counts["valid_outputs"] += 1
            counts.update({f"source_{key}": value for key, value in production["direction_counts"].items()})
            if production["candidate_directions"] and len(production["selected_directions"]) < len(production["candidate_directions"]):
                counts["joint_conflict_cases"] += 1
            decisions.append(production)
        if before != (parent.to_dict(), canonical_json_bytes(artifact)):
            raise RuntimeError("Solver mutated a conformance input")
        counts["inputs_unchanged"] += 1
        rows.append({
            "schema_version": "fourgraph.t21_v3b_edge_selective_valid_case.v1",
            "case_id": f"V3B{index:03d}", "node_count": node_count,
            "preference_regime": regime, "oracle_dag": oracle.to_dict(),
            "parent_cpdag": parent.to_dict(), "preference_artifact": artifact,
            "threshold_decisions": decisions, "production_reference_agreement": True,
            "study_scene_used": False,
        })
    for index in range(int(suite["off_grid_joint_selection_probes"])):
        parent, artifact = _joint_selection_probe(index)
        production = solve_edge_selective(parent, artifact, tau_semantic=0.99, tau_global=0.5)
        reference = solve_prepared_reference(
            prepare_reference_edge_selective(parent, artifact), tau_semantic=0.99, tau_global=0.5
        )
        _agree(production, reference)
        if len(production["candidate_directions"]) != 3 or len(production["selected_directions"]) != 2:
            raise RuntimeError("Joint-selection probe did not reject one edge from a directed cycle")
        validate_edge_selective_output(parent, production)
        counts["off_grid_joint_selection_probes"] += 1
        rows[index]["off_grid_joint_selection_probe"] = {
            "purpose": "algorithmic_conformance_only_not_threshold_selection",
            "tau_semantic": 0.99,
            "tau_global": 0.5,
            "parent_cpdag": parent.to_dict(),
            "preference_artifact": artifact,
            "decision": production,
        }
    return rows, counts


def _invalid(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    parent = dag_to_cpdag_exact(PartialGraph.build(["X000", "X001", "X002"], [("X000", "X001"), ("X001", "X002")]))
    base = _artifact(parent, "strong_consistent", int(config["master_seed"]))
    kinds = ["threshold_type", "threshold_range", "parent_hash", "missing_edge", "probability_range", "output_hash", "output_skeleton", "output_provenance"]
    rows = []
    for index in range(int(config["suite"]["invalid_cases"])):
        kind = kinds[index % len(kinds)]
        artifact = copy.deepcopy(base)
        observed = None
        try:
            if kind == "threshold_type":
                solve_edge_selective(parent, artifact, tau_semantic=True, tau_global=0.8)
            elif kind == "threshold_range":
                solve_edge_selective(parent, artifact, tau_semantic=0.49, tau_global=0.8)
            elif kind == "parent_hash":
                artifact["parent_graph_sha256"] = "0" * 64
                solve_edge_selective(parent, artifact, tau_semantic=0.8, tau_global=0.8)
            elif kind == "missing_edge":
                artifact["preferences"] = artifact["preferences"][:-1]
                solve_edge_selective(parent, artifact, tau_semantic=0.8, tau_global=0.8)
            elif kind == "probability_range":
                artifact["preferences"][0]["probability_left_causes_right"] = 1.1
                solve_edge_selective(parent, artifact, tau_semantic=0.8, tau_global=0.8)
            else:
                result = solve_edge_selective(parent, artifact, tau_semantic=0.8, tau_global=0.8)
                if kind == "output_hash":
                    result["output_graph_sha256"] = "0" * 64
                elif kind == "output_skeleton":
                    if result["output_graph"]["directed"]:
                        result["output_graph"]["directed"] = result["output_graph"]["directed"][1:]
                    else:
                        result["output_graph"]["undirected"] = result["output_graph"]["undirected"][1:]
                else:
                    result["edge_provenance"] = result["edge_provenance"][:-1]
                validate_edge_selective_output(parent, result)
        except H2ContractError as exc:
            observed = exc.code
        expected = {
            "threshold_type": "threshold_type", "threshold_range": "threshold_range", "parent_hash": "parent_hash",
            "missing_edge": "missing_edge", "probability_range": "probability_range", "output_hash": "output_hash",
            "output_skeleton": "output_structure", "output_provenance": "output_provenance",
        }[kind]
        if observed != expected:
            raise RuntimeError(f"Invalid case {kind}: {observed} != {expected}")
        rows.append({"schema_version": "fourgraph.t21_v3b_edge_selective_invalid_case.v1", "case_id": f"V3BI{index:03d}", "invalidity": kind, "expected_error_code": expected, "observed_error_code": observed})
    return rows


def _build() -> tuple[bytes, bytes, bytes, bytes]:
    config = _load_yaml(CONFIG)
    _boundary(config)
    valid, counts = _valid(config)
    invalid = _invalid(config)
    gates = config["gates"]
    passed = (
        len(valid) == config["suite"]["valid_cases"]
        and counts["decisions"] == gates["production_reference_decisions"]
        and counts["valid_outputs"] == counts["decisions"]
        and counts["off_grid_joint_selection_probes"] == gates["production_reference_joint_selection_probes"]
        and counts["inputs_unchanged"] == len(valid)
        and len(invalid) == gates["invalid_cases_rejected"]
        and all(counts[f"source_{name}"] > 0 for name in gates["required_direction_sources"])
    )
    if not passed:
        raise RuntimeError(f"T21 v3-B conformance gate failed: {dict(counts)}")
    valid_body = b"".join(_line(row) for row in valid)
    invalid_body = b"".join(_line(row) for row in invalid)
    report_lines = [
        "# T21 v3-B — Edge-Selective offline conformance", "",
        "T21 v3-B triển khai contract partial graph, production/reference solvers và Meek R1–R4 hoàn toàn offline.", "",
        f"- Valid synthetic cases: {len(valid)}/{len(valid)}.",
        f"- Threshold decisions production/reference khớp: {counts['decisions']}/{counts['decisions']}.",
        f"- Invalid fixtures bị từ chối đúng mã lỗi: {len(invalid)}/{len(invalid)}.",
        f"- Closure-propagated direction observations: {counts['source_closure_propagated']}.",
        f"- Off-grid joint-selection cycle probes: {counts['off_grid_joint_selection_probes']}/{counts['off_grid_joint_selection_probes']}.", "",
        "Không gọi API, không sinh validation cohort, không đọc P1 development/holdout và chưa chọn threshold.",
    ]
    report_body = ("\n".join(report_lines) + "\n").encode("utf-8")
    audit = {
        "schema_version": "fourgraph.t21_v3b_edge_selective_audit.v1", "task": "T21 Amendment v3-B",
        "parent_freeze": _entry(ROOT / str(config["parent_freeze"])), "config": _entry(CONFIG),
        "implementation": [_entry(ROOT / config["implementation"]["production"]), _entry(ROOT / config["implementation"]["reference"]), _entry(SCRIPT)],
        "contracts": [_entry(ROOT / config["implementation"]["partial_graph_contract"]), _entry(ROOT / config["implementation"]["decision_contract"])],
        "outputs": [_entry(VALID, valid_body), _entry(INVALID, invalid_body), _entry(REPORT, report_body)],
        "counts": {**dict(counts), "valid_cases": len(valid), "invalid_cases_rejected": len(invalid)},
        "boundary": config["execution_boundary"],
        "verdict": {
            "t21_v3b_complete": True, "offline_conformance_passed": True,
            "production_reference_agreement": True, "partial_graph_contract_ready": True,
            "validation_scenes_generated": False, "api_calls": 0, "holdout_accessed": False,
            "t21_v3c_validation_generation_authorized": True, "live_api_calls_authorized": False,
        },
    }
    return valid_body, invalid_body, canonical_json_bytes(audit), report_body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    bodies = _build()
    paths = (VALID, INVALID, AUDIT, REPORT)
    if args.check:
        for path, body in zip(paths, bodies):
            if not path.is_file() or path.read_bytes() != body:
                raise SystemExit(f"T21 v3-B byte drift: {path.relative_to(ROOT)}")
        print(json.dumps({"check": "passed", "api_calls": 0, "holdout_accessed": False}))
    else:
        for path, body in zip(paths, bodies):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        print(json.dumps({"generated": [path.relative_to(ROOT).as_posix() for path in paths], "api_calls": 0, "holdout_accessed": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
