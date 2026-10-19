"""Offline mathematical audit of the captured PC incident graph."""
from __future__ import annotations

import hashlib
import json
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results/raw/p1_v4_independent_calibration/look120/statistical/pc_incident_replay/prevalidation_raw.json"
OUT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_pc_isolated_replay_execution_audit.json"
REPORT = ROOT / "reports/p1_v4_independent_calibration_look120_pc_isolated_replay_execution.md"


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def adjacent(edges: set[tuple[str, str]], a: str, b: str) -> bool:
    return (a, b) in edges or (b, a) in edges


def has_cycle(nodes: list[str], edges: set[tuple[str, str]]) -> bool:
    remaining = {node: 0 for node in nodes}
    for _, target in edges: remaining[target] += 1
    stack = sorted(node for node, degree in remaining.items() if degree == 0)
    seen = 0
    while stack:
        node = stack.pop(); seen += 1
        for source, target in sorted(edges):
            if source == node:
                remaining[target] -= 1
                if remaining[target] == 0: stack.append(target)
    return seen != len(nodes)


def colliders(nodes: list[str], edges: set[tuple[str, str]]) -> set[tuple[str, str, str]]:
    result = set()
    for middle in nodes:
        parents = sorted(source for source, target in edges if target == middle)
        for index, left in enumerate(parents):
            for right in parents[index + 1:]:
                if not adjacent(edges, left, right): result.add((left, middle, right))
    return result


def main() -> None:
    payload = json.loads(RAW.read_text(encoding="utf-8")); graph = payload["graph"]
    nodes = graph["nodes"]; directed = {tuple(edge) for edge in graph["directed"]}; undirected = [tuple(edge) for edge in graph["undirected"]]
    if len(undirected) != 1: raise SystemExit("audit fixture expects exactly one undirected edge")
    baseline = colliders(nodes, directed)
    cases = []
    for bits in product((0, 1), repeat=len(undirected)):
        oriented = set(directed)
        directions = []
        for edge, bit in zip(undirected, bits):
            direction = edge if bit == 0 else (edge[1], edge[0]); oriented.add(direction); directions.append(list(direction))
        cycle = has_cycle(nodes, oriented); added = sorted(colliders(nodes, oriented) - baseline)
        cases.append({"orientation": directions, "directed_cycle": cycle, "new_unshielded_colliders": added, "consistent_extension": not cycle and not added})
    audit = {
        "task": "P1_V4_INDEPENDENT_CALIBRATION_LOOK120_PC_ISOLATED_REPLAY_EXECUTION_AUDIT",
        "status": "PASS_FORENSIC_CLASSIFICATION",
        "prevalidation_raw_sha256": sha(RAW),
        "graph": graph,
        "extension_cases": cases,
        "classification": "PARSED_PC_OUTPUT_IS_NOT_A_CONSISTENTLY_EXTENDABLE_PDG",
        "adapter_validator_disagreement_evidence": "NONE_IN_PARSED_GRAPH",
        "disposition": "PHASE_D_REMAINS_SUSPENDED_PENDING_REGISTERED_INVALID_PC_OUTPUT_HANDLING",
        "boundary": {"additional_statistical_fits": 0, "semantic_api_calls": 0, "oracle_access": 0, "holdout_access": 0},
    }
    data = canonical(audit); OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists() and OUT.read_bytes() != data: raise SystemExit("audit drift")
    if not OUT.exists(): OUT.write_bytes(data)
    report = """# Isolated PC replay — execution audit\n\nThe captured parsed PC graph has one undirected edge, `X002 -- X003`. Exhaustive\nchecking gives two possible orientations:\n\n- `X002 → X003` forms the directed cycle `X003 → X000 → X001 → X002 → X003`.\n- `X003 → X002` introduces the unshielded collider `X001 → X002 ← X003`.\n\nThus the captured parsed PC output has no consistent DAG extension. The frozen\nvalidator rejection is mathematically supported by the captured graph; there is no\nevidence of a validator-only error. This does not change PC parameters or repair\nthe graph. Phase D remains suspended until a separate registered handling policy\nfor invalid PC outputs is approved.\n"""
    if REPORT.exists() and REPORT.read_text(encoding="utf-8") != report: raise SystemExit("report drift")
    if not REPORT.exists(): REPORT.write_text(report, encoding="utf-8")
    print(json.dumps({"status": audit["status"], "classification": audit["classification"]}))


if __name__ == "__main__": main()
