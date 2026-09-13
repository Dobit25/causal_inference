"""Generate or byte-check the fully offline T20 H2 conformance suite."""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.h2_reference import reference_forced, reference_selective  # noqa: E402
from fourgraph.hybrid_h2 import (  # noqa: E402
    H2ContractError,
    PREFERENCE_SCHEMA,
    graph_sha256,
    solve_h2_forced,
    solve_h2_selective,
)
from fourgraph.p1_generation import canonical_line, graph_motifs  # noqa: E402
from fourgraph.partial_graph import (  # noqa: E402
    PartialGraph,
    consistent_extension,
    dag_to_cpdag_exact,
    unshielded_colliders,
)


CONFIG = ROOT / "configs/t20_h2_conformance.yaml"
PREFERENCE_SCHEMA_PATH = ROOT / "schemas/semantic_preference_v1.schema.json"
DECISION_SCHEMA_PATH = ROOT / "schemas/h2_decision_v1.schema.json"
PRODUCTION = ROOT / "src/fourgraph/hybrid_h2.py"
REFERENCE = ROOT / "src/fourgraph/h2_reference.py"
SCRIPT = Path(__file__).resolve()


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def _entry(path: Path, payload: bytes | None = None) -> dict[str, Any]:
    body = path.read_bytes() if payload is None else payload
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": len(body), "sha256": sha256_hex(body)}


def _graph(record: Mapping[str, Any]) -> PartialGraph:
    return PartialGraph.build(record["nodes"], record.get("directed", ()), record.get("undirected", ()))


def _validate_boundary(config: Mapping[str, Any]) -> None:
    t19 = _json(ROOT / str(config["parent_story_audit"]))
    if not t19["verdict"]["t19_complete"] or not t19["verdict"]["t20_h2_offline_conformance_authorized"]:
        raise RuntimeError("T19 does not authorize T20")
    if t19["verdict"]["live_model_calls_authorized"] or t19["verdict"]["p1_holdout_evaluation_authorized"]:
        raise RuntimeError("T19 execution boundary drift")
    boundary = config["access_boundary"]
    forbidden = (
        boundary["api_calls"],
        boundary["provider_sdk_imports_allowed"],
        boundary["P1_scm_or_story_access_authorized"],
        boundary["P1_development_execution_authorized"],
        boundary["P1_holdout_access_authorized"],
        boundary["SCD_execution_authorized"],
        boundary["LLM_execution_authorized"],
        boundary["reasoner_execution_authorized"],
        boundary["H2_on_P1_scenes_authorized"],
        boundary["threshold_selection_authorized"],
    )
    if any(forbidden):
        raise RuntimeError("T20 execution boundary drift")
    if np.__version__ != str(config["randomness"]["numpy_version"]):
        raise RuntimeError("T20 NumPy version drift")
    paths = [ROOT / str(value) for value in config["dependencies"]]
    if len(paths) != len(set(paths)) or any(not path.is_file() for path in paths):
        raise RuntimeError("T20 dependency list missing or duplicated")


def _motif_edges(target: str, order: list[str]) -> set[tuple[str, str]]:
    if target in {"chain", "mediator"}:
        return {(order[index], order[index + 1]) for index in range(len(order) - 1)}
    if target == "fork":
        edges = {(order[0], order[1]), (order[0], order[2])}
        edges.update((order[index], order[index + 1]) for index in range(2, len(order) - 1))
        if len(order) > 3:
            edges.add((order[1], order[3]))
        return edges
    if target == "collider":
        edges = {(order[0], order[2]), (order[1], order[2])}
        edges.update((order[index], order[index + 1]) for index in range(2, len(order) - 1))
        return edges
    if target == "diamond":
        edges = {(order[0], order[1]), (order[0], order[2]), (order[1], order[3]), (order[2], order[3])}
        edges.update((order[index], order[index + 1]) for index in range(3, len(order) - 1))
        return edges
    raise ValueError(target)


def _case_allocations(rng: np.random.Generator) -> tuple[list[int], list[str], list[str]]:
    node_counts = [value for value in range(3, 8) for _ in range(30)]
    first = [value for value in ("chain", "fork", "collider") for _ in range(10)]
    remaining = [value for value, count in (("chain", 20), ("fork", 20), ("collider", 20), ("mediator", 30), ("diamond", 30)) for _ in range(count)]
    remaining = [remaining[index] for index in rng.permutation(len(remaining))]
    motifs = first + remaining
    regimes = [value for value in ("strong_consistent", "weak_consistent", "uniform_tie", "mixed_conflict", "near_tie", "strong_reverse_lexicographic") for _ in range(25)]
    regimes = [regimes[index] for index in rng.permutation(len(regimes))]
    return node_counts, motifs, regimes


def _synthetic_parent(index: int, node_count: int, target: str, seed: int) -> tuple[PartialGraph, PartialGraph, int]:
    nodes = [f"X{value:03d}" for value in range(node_count)]
    for attempt in range(1, 1001):
        rng = np.random.Generator(np.random.PCG64DXSM(seed + index * 1009 + attempt))
        order = [nodes[position] for position in rng.permutation(node_count)]
        edges = _motif_edges(target, order)
        forward = [(order[a], order[b]) for a in range(node_count) for b in range(a + 1, node_count)]
        available = [edge for edge in forward if edge not in edges]
        extras = min(len(available), int(rng.integers(0, 3)))
        if extras:
            for position in rng.choice(len(available), size=extras, replace=False):
                candidate = available[int(position)]
                if target == "collider" and set(candidate) == {order[0], order[1]}:
                    continue
                edges.add(candidate)
        dag = PartialGraph.build(nodes, edges)
        if target not in graph_motifs(dag):
            continue
        cpdag = dag_to_cpdag_exact(dag)
        if len(cpdag.undirected) <= 10:
            return dag, cpdag, attempt
    raise RuntimeError(f"Could not generate T20 case {index}")


def _preference_artifact(parent: PartialGraph, regime: str, case_seed: int) -> dict[str, Any]:
    anchor = consistent_extension(parent)
    rng = np.random.Generator(np.random.PCG64DXSM(case_seed))
    values = [0.12, 0.28, 0.48, 0.52, 0.72, 0.88]
    rows = []
    for index, (left, right) in enumerate(sorted(parent.undirected)):
        anchor_forward = (left, right) in anchor.directed
        if regime == "strong_consistent":
            p = 0.9 if anchor_forward else 0.1
        elif regime == "weak_consistent":
            p = 0.55 if anchor_forward else 0.45
        elif regime == "uniform_tie":
            p = 0.5
        elif regime == "mixed_conflict":
            p = values[(index + int(rng.integers(0, len(values)))) % len(values)]
        elif regime == "near_tie":
            p = (0.49, 0.51, 0.45, 0.55)[index % 4]
        elif regime == "strong_reverse_lexicographic":
            p = 0.1
        else:
            raise ValueError(regime)
        rows.append({"left": left, "right": right, "probability_left_causes_right": p})
    return {"schema_version": PREFERENCE_SCHEMA, "parent_graph_sha256": graph_sha256(parent), "preferences": rows}


def _close(left: float | str | None, right: float | str | None, tolerance: float) -> bool:
    if left is None or right is None or isinstance(left, str) or isinstance(right, str):
        return left == right
    return math.isclose(float(left), float(right), abs_tol=tolerance, rel_tol=0.0)


def _local_argmax_valid(parent: PartialGraph, artifact: Mapping[str, Any]) -> bool:
    directed = set(parent.directed)
    for row in artifact["preferences"]:
        left, right, p = row["left"], row["right"], row["probability_left_causes_right"]
        directed.add((left, right) if p >= 0.5 else (right, left))
    try:
        candidate = PartialGraph.build(parent.nodes, directed)
    except ValueError:
        return False
    return unshielded_colliders(candidate) == unshielded_colliders(parent)


def _valid_cases(config: Mapping[str, Any]) -> tuple[list[dict[str, Any]], Counter, Counter]:
    seed = int(config["randomness"]["suite_seed"])
    rng = np.random.Generator(np.random.PCG64DXSM(seed))
    node_counts, target_motifs, regimes = _case_allocations(rng)
    margins = config["h2_selective"]["threshold_grid"]["tau_margin"]
    conflicts = config["h2_selective"]["threshold_grid"]["tau_conflict"]
    tolerance = float(config["conformance"]["floating_absolute_tolerance"])
    rows: list[dict[str, Any]] = []
    decisions = Counter()
    diagnostics = Counter()
    for index, (node_count, target, regime) in enumerate(zip(node_counts, target_motifs, regimes)):
        dag, parent, attempts = _synthetic_parent(index, node_count, target, seed)
        artifact = _preference_artifact(parent, regime, seed + index * 7919)
        parent_before = parent.to_dict()
        artifact_before = canonical_json_bytes(artifact)
        production = solve_h2_forced(parent, artifact)
        reference = reference_forced(parent, artifact)
        selected = _graph(production["selected_graph"])
        agreements = {
            "selected_graph": production["selected_graph"] == reference["selected_graph"],
            "extension_count": production["consistent_extension_count"] == reference["consistent_extension_count"],
            "best_score": _close(production["best_log_score"], reference["best_log_score"], tolerance),
            "second_score": _close(production["second_best_log_score"], reference["second_best_log_score"], tolerance),
            "normalized_margin": _close(production["normalized_margin"], reference["normalized_margin"], tolerance),
            "normalized_conflict_mass": _close(production["normalized_conflict_mass"], reference["normalized_conflict_mass"], tolerance),
            "parent_nodes_preserved": selected.nodes == parent.nodes,
            "parent_skeleton_preserved": selected.skeleton == parent.skeleton,
            "compelled_directions_preserved": parent.directed.issubset(selected.directed),
            "acyclic": selected.is_directed_acyclic(),
            "unshielded_colliders_preserved": unshielded_colliders(selected) == unshielded_colliders(parent),
        }
        if not all(agreements.values()):
            raise RuntimeError(f"T20 production/reference disagreement at case {index}: {agreements}")
        selective = []
        for tau_margin in margins:
            for tau_conflict in conflicts:
                actual = solve_h2_selective(parent, production, tau_margin=tau_margin, tau_conflict=tau_conflict)
                expected_decision, expected_graph = reference_selective(
                    parent, reference, tau_margin=float(tau_margin), tau_conflict=float(tau_conflict)
                )
                if actual["decision"] != expected_decision or actual["output_graph"] != expected_graph:
                    raise RuntimeError(f"Selective disagreement at T20 case {index}")
                if actual["decision"] == "accept" and actual["output_graph"] != production["selected_graph"]:
                    raise RuntimeError("Selective accept did not return exact forced DAG")
                if actual["decision"] == "abstain" and actual["output_graph"] != parent.to_dict():
                    raise RuntimeError("Selective abstention changed raw CPDAG")
                decisions[actual["decision"]] += 1
                selective.append({"tau_margin": tau_margin, "tau_conflict": tau_conflict, "decision": actual["decision"], "output_graph_sha256": actual["output_graph_sha256"]})
        inputs_unchanged = parent.to_dict() == parent_before and canonical_json_bytes(artifact) == artifact_before
        if not inputs_unchanged:
            raise RuntimeError(f"T20 solver mutated input at case {index}")
        diagnostics["inputs_unchanged"] += 1
        local_valid = _local_argmax_valid(parent, artifact)
        diagnostics["local_argmax_valid" if local_valid else "local_argmax_invalid"] += 1
        diagnostics["single_extension" if production["consistent_extension_count"] == 1 else "multiple_extensions"] += 1
        rows.append(
            {
                "schema_version": "fourgraph.t20_h2_valid_case.v1",
                "case_id": f"T20V{index:03d}",
                "node_count": node_count,
                "target_motif": target,
                "verified_motifs": list(graph_motifs(dag)),
                "preference_regime": regime,
                "generation_attempt": attempts,
                "parent_cpdag": parent.to_dict(),
                "preference_artifact": artifact,
                "production_forced": production,
                "reference_selected_graph_sha256": reference["selected_graph_sha256"],
                "agreements": agreements,
                "local_argmax_consistent_extension": local_valid,
                "selective_decisions": selective,
                "P1_scene_or_story_used": False,
            }
        )
    return rows, decisions, diagnostics


def _invalid_base() -> tuple[PartialGraph, dict[str, Any]]:
    dag = PartialGraph.build(
        [f"X{index:03d}" for index in range(6)],
        [("X000", "X001"), ("X002", "X001"), ("X001", "X003"), ("X004", "X005")],
    )
    parent = dag_to_cpdag_exact(dag)
    artifact = _preference_artifact(parent, "strong_consistent", 999)
    return parent, artifact


def _invalid_cases() -> list[dict[str, Any]]:
    parent, base = _invalid_base()
    incomplete = PartialGraph.build(
        ["X000", "X001", "X002"], directed=[("X001", "X002")], undirected=[("X000", "X001")]
    )
    types = [
        "bad_schema", "extra_top", "bad_parent_hash", "preferences_type", "missing_edge",
        "duplicate_edge", "nonedge", "compelled_edge", "endpoint_order", "unknown_node",
        "probability_bool", "probability_string", "probability_low", "probability_high",
        "extra_preference_field", "incomplete_cpdag",
    ]
    cases: list[dict[str, Any]] = []
    for index in range(30):
        kind = types[index % len(types)]
        case_parent = parent
        artifact: Any = copy.deepcopy(base)
        expected = ""
        if kind == "bad_schema":
            artifact["schema_version"] = "wrong"; expected = "schema_version"
        elif kind == "extra_top":
            artifact["oracle"] = True; expected = "extra_top_level_field"
        elif kind == "bad_parent_hash":
            artifact["parent_graph_sha256"] = "0" * 64; expected = "parent_hash"
        elif kind == "preferences_type":
            artifact["preferences"] = {}; expected = "preferences_type"
        elif kind == "missing_edge":
            artifact["preferences"] = []; expected = "missing_edge"
        elif kind == "duplicate_edge":
            artifact["preferences"].append(copy.deepcopy(artifact["preferences"][0])); expected = "duplicate_edge"
        elif kind == "nonedge":
            artifact["preferences"][0].update(left="X000", right="X002"); expected = "nonedge"
        elif kind == "compelled_edge":
            artifact["preferences"][0].update(left="X000", right="X001"); expected = "compelled_edge"
        elif kind == "endpoint_order":
            row = artifact["preferences"][0]; row["left"], row["right"] = row["right"], row["left"]; expected = "endpoint_order"
        elif kind == "unknown_node":
            artifact["preferences"][0].update(left="X998", right="X999"); expected = "unknown_node"
        elif kind == "probability_bool":
            artifact["preferences"][0]["probability_left_causes_right"] = True; expected = "probability_type"
        elif kind == "probability_string":
            artifact["preferences"][0]["probability_left_causes_right"] = "NaN"; expected = "probability_type"
        elif kind == "probability_low":
            artifact["preferences"][0]["probability_left_causes_right"] = 0.0; expected = "probability_range"
        elif kind == "probability_high":
            artifact["preferences"][0]["probability_left_causes_right"] = 1.0; expected = "probability_range"
        elif kind == "extra_preference_field":
            artifact["preferences"][0]["gold_answer"] = None; expected = "extra_preference_field"
        elif kind == "incomplete_cpdag":
            case_parent = incomplete
            artifact = {"schema_version": PREFERENCE_SCHEMA, "parent_graph_sha256": graph_sha256(incomplete), "preferences": [{"left": "X000", "right": "X001", "probability_left_causes_right": 0.5}]}
            expected = "invalid_cpdag"
        try:
            solve_h2_forced(case_parent, artifact)
        except H2ContractError as exc:
            observed = exc.code
        else:
            raise RuntimeError(f"Invalid T20 case accepted: {kind}")
        if observed != expected:
            raise RuntimeError(f"Invalid T20 error mismatch {kind}: {observed} != {expected}")
        cases.append({"schema_version": "fourgraph.t20_h2_invalid_case.v1", "case_id": f"T20I{index:03d}", "invalidity": kind, "parent_graph": case_parent.to_dict(), "preference_artifact": artifact, "expected_error_code": expected, "observed_error_code": observed})
    return cases


def _report(audit: Mapping[str, Any]) -> bytes:
    counts = audit["counts"]
    lines = [
        "# T20 — H2 offline implementation and conformance",
        "",
        "## Kết quả",
        "",
        "T20 đã triển khai H2-Forced và H2-Selective rồi kiểm thử hoàn toàn bằng synthetic CPDAG/preference fixtures.",
        "",
        f"- Valid cases: {counts['valid_cases']}/150 production/reference agreements.",
        f"- Invalid cases: {counts['invalid_cases_rejected']}/30 bị từ chối fail-closed với đúng error code.",
        f"- Selective decisions: {counts['selective_decisions_agreed']}/3000 khớp reference.",
        f"- Local independent argmax invalid: {counts['local_argmax_invalid_cases']} cases; H2-Forced vẫn trả consistent extension hợp lệ.",
        f"- Selective accept/abstain across the frozen grid: {counts['selective_accepts']}/{counts['selective_abstentions']}.",
        "",
        "Mọi H2-Forced output giữ node/skeleton/compelled directions, acyclic và không tạo unshielded collider ngoài equivalence class. Selective accept trả exact Forced DAG; abstention trả parent CPDAG byte-equivalent.",
        "",
        "## Evidence boundary",
        "",
        "Suite không dùng P1 SCM, story, development hay holdout scene. T20 gọi 0 API, không chạy SCD/LLM/reasoner, không chạy H2 trên P1 và không chọn threshold. T21 development-only execution/selection là bước duy nhất được cấp quyền tiếp theo.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def build() -> tuple[dict[Path, bytes], dict[str, Any]]:
    config = _yaml(CONFIG)
    _validate_boundary(config)
    valid, decisions, diagnostics = _valid_cases(config)
    invalid = _invalid_cases()
    if (
        len(valid) != 150
        or len(invalid) != 30
        or sum(decisions.values()) != 3000
        or diagnostics["inputs_unchanged"] != 150
    ):
        raise RuntimeError("T20 suite cardinality gate failed")
    valid_payload = b"".join(canonical_line(row) for row in valid)
    invalid_payload = b"".join(canonical_line(row) for row in invalid)
    valid_path = ROOT / config["artifacts"]["valid_cases"]
    invalid_path = ROOT / config["artifacts"]["invalid_cases"]
    prelim = {valid_path: valid_payload, invalid_path: invalid_payload}
    dependencies = [CONFIG, PREFERENCE_SCHEMA_PATH, DECISION_SCHEMA_PATH, PRODUCTION, REFERENCE, SCRIPT]
    dependencies.extend(ROOT / path for path in config["dependencies"])
    dependencies = list(dict.fromkeys(dependencies))
    motifs = Counter(row["target_motif"] for row in valid)
    nodes = Counter(str(row["node_count"]) for row in valid)
    regimes = Counter(row["preference_regime"] for row in valid)
    audit: dict[str, Any] = {
        "schema_version": "fourgraph.t20_h2_conformance_audit.v1",
        "task": "T20",
        "experiment_id": config["experiment_id"],
        "dependencies": [_entry(path) for path in dependencies],
        "outputs": [],
        "counts": {
            "valid_cases": 150,
            "production_reference_forced_agreements": 150,
            "invalid_cases": 30,
            "invalid_cases_rejected": 30,
            "selective_decisions": 3000,
            "selective_decisions_agreed": 3000,
            "selective_accepts": decisions["accept"],
            "selective_abstentions": decisions["abstain"],
            "local_argmax_valid_cases": diagnostics["local_argmax_valid"],
            "local_argmax_invalid_cases": diagnostics["local_argmax_invalid"],
            "single_extension_cases": diagnostics["single_extension"],
            "multiple_extension_cases": diagnostics["multiple_extensions"],
            "input_immutability_cases": diagnostics["inputs_unchanged"],
        },
        "distributions": {"node_count": dict(sorted(nodes.items())), "target_motif": dict(sorted(motifs.items())), "preference_regime": dict(sorted(regimes.items()))},
        "invariants": {
            "parent_nodes_preserved": "150/150",
            "parent_skeleton_preserved": "150/150",
            "compelled_directions_preserved": "150/150",
            "acyclic": "150/150",
            "unshielded_colliders_preserved": "150/150",
            "selective_accept_exact_forced_dag": True,
            "selective_abstain_exact_parent_cpdag": True,
            "inputs_not_mutated": True,
        },
        "evidence_boundary": {"api_calls": 0, "provider_SDK_imported_or_called": False, "P1_SCMs_or_stories_accessed": False, "P1_development_scenes_executed": 0, "P1_holdout_accessed": False, "SCD_LLM_reasoner_executed": False, "H2_P1_executions": 0, "threshold_selected": False},
        "verdict": {"t20_complete": True, "h2_forced_conformant": True, "h2_selective_conformant": True, "generator_reproducible": True, "t21_development_only_execution_authorized": True, "live_model_calls_authorized_at_T20": False, "p1_holdout_evaluation_authorized": False},
    }
    report_path = ROOT / config["artifacts"]["report"]
    report_payload = _report(audit)
    outputs = {**prelim, report_path: report_payload}
    audit["outputs"] = [_entry(path, payload) for path, payload in sorted(outputs.items(), key=lambda item: item[0].as_posix())]
    audit_path = ROOT / config["artifacts"]["audit"]
    outputs[audit_path] = canonical_line(audit)
    return outputs, {"t20_complete": True, "valid": 150, "invalid_rejected": 30, "selective_agreements": 3000, "t21_authorized": True}


def _compare(path: Path, expected: bytes) -> None:
    if not path.is_file() or path.read_bytes() != expected:
        actual = sha256_hex(path.read_bytes()) if path.is_file() else "MISSING"
        raise RuntimeError(f"Byte drift: {path.relative_to(ROOT)} expected={sha256_hex(expected)} actual={actual}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--replace-provisional", action="store_true")
    args = parser.parse_args()
    if args.check and args.replace_provisional:
        raise ValueError("Lifecycle flags are mutually exclusive")
    outputs, summary = build()
    for path, payload in outputs.items():
        if args.check or (path.exists() and not args.replace_provisional):
            _compare(path, payload)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
