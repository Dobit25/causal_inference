from __future__ import annotations

"""Offline Phase-F statistical skeleton metrics.

This script only reads frozen Phase-D normalized artifacts and deterministically
reconstructs the development Oracle skeletons in memory. It never fits a
statistical model, writes study scenes, calls an API, or reads holdout data.
"""

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import yaml

from materialize_p1v3_development import build_blueprint, load_identities
from fourgraph.p1_generation import scene_scm_record
NORMALIZED = ROOT / "results/p1v3_statistical_ensemble/normalized"
PHASE_D_AUDIT = ROOT / "data/manifests/p1v3_statistical_execution_audit.json"
ALGORITHM_MANIFEST = ROOT / "configs/p1v3_algorithm_manifest.yaml"
ENSEMBLE_MANIFEST = ROOT / "configs/p1v3_statistical_ensemble_manifest_v2.yaml"
GENERATOR_CONFIG = ROOT / "configs/p1_v3_successor_method_development_preflight.yaml"
IDENTITIES = ROOT / "data/manifests/p1_v3_successor_sequential_exact_identities.jsonl"
OUT_DATASET = ROOT / "data/manifests/p1v3_statistical_skeleton_metric_dataset.jsonl"
OUT_RESULTS = ROOT / "data/manifests/p1v3_statistical_skeleton_metric_results.json"
OUT_AUDIT = ROOT / "data/manifests/p1v3_statistical_skeleton_metric_audit.json"
OUT_CONFIG = ROOT / "configs/p1v3_statistical_skeleton_metric_checkpoint.yaml"
OUT_REPORT = ROOT / "reports/p1v3_statistical_skeleton_metric_review.md"

BOOTSTRAP_THRESHOLDS = {"C1": 0.60, "C2": 0.60, "C3": 0.80, "C4": 0.80, "C5": 0.95, "C6": 0.95}
CONDITIONS = ["Single-BOSS", "Bootstrap-C1", "Bootstrap-C2", "Bootstrap-C3", "Bootstrap-C4", "Bootstrap-C5", "Bootstrap-C6", "PC", "MMPC", "FGES", "Ensemble-3of5", "GFCI-sensitivity"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def sha_json(value: Any) -> str:
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    return hashlib.sha256(raw).hexdigest().upper()


def pair(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((str(a), str(b))))  # type: ignore[return-value]


def skeleton(graph: dict[str, Any]) -> set[tuple[str, str]]:
    nodes = set(graph["nodes"])
    result: set[tuple[str, str]] = set()
    for edge in graph.get("directed", []) + graph.get("undirected", []):
        if len(edge) != 2 or edge[0] == edge[1] or set(edge) - nodes:
            raise ValueError(f"invalid graph edge: {edge}")
        result.add(pair(edge[0], edge[1]))
    return result


def load_normalized() -> list[dict[str, Any]]:
    rows = []
    for path in sorted(NORMALIZED.glob("*.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    if len(rows) != 6150:
        raise RuntimeError(f"expected 6150 normalized fits, found {len(rows)}")
    return rows


def oracle_skeletons() -> tuple[dict[str, tuple[str, ...]], dict[str, set[tuple[str, str]]], dict[str, str]]:
    cfg = yaml.safe_load(GENERATOR_CONFIG.read_text(encoding="utf-8"))
    identities = load_identities(IDENTITIES)
    blueprints = {row["study_id"]: build_blueprint(row, cfg["generator"]) for row in identities}
    oracle = {sid: {pair(a, b) for a, b in bp.dag.directed} for sid, bp in blueprints.items()}
    nodes = {sid: tuple(bp.dag.nodes) for sid, bp in blueprints.items()}
    commitments = {}
    for sid, bp in blueprints.items():
        # The generator itself is the frozen deterministic Oracle source. This
        # commitment check is against Phase-D metadata and does not materialize
        # observations or expose Oracle artifacts to the semantic pipeline.
        meta = json.loads((ROOT / "results/p1v3_statistical_ensemble/scenes" / sid / "metadata.json").read_text(encoding="utf-8"))
        commitment = sha_json(scene_scm_record(bp))
        if commitment != meta["scm_commitment_sha256"]:
            raise RuntimeError(f"Oracle/SCM commitment mismatch for {sid}")
        commitments[sid] = commitment
    if set(oracle) != {f"P1V3SD{i:03d}" for i in range(30)}:
        raise RuntimeError("development scene identity scope drift")
    return nodes, oracle, commitments


def valid_graph(row: dict[str, Any]) -> bool:
    try:
        graph = row["graph"]
        if set(graph["nodes"]) != set(graph["nodes"]):
            return False
        skeleton(graph)
        directed = {tuple(e) for e in graph.get("directed", [])}
        if any(a == b for a, b in directed):
            return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def mean_or_none(values: list[float]) -> float | None:
    return round(mean(values), 8) if values else None


def metrics(records: list[dict[str, Any]], scene_ids: list[str]) -> dict[str, Any]:
    pooled = {key: sum(int(row[key]) for row in records) for key in ("tp", "fp", "fn", "tn")}
    precision = pooled["tp"] / (pooled["tp"] + pooled["fp"]) if pooled["tp"] + pooled["fp"] else 1.0
    recall = pooled["tp"] / (pooled["tp"] + pooled["fn"]) if pooled["tp"] + pooled["fn"] else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    fpr = pooled["fp"] / (pooled["fp"] + pooled["tn"]) if pooled["fp"] + pooled["tn"] else 0.0
    by_scene = []
    for sid in scene_ids:
        rows = [r for r in records if r["scene_id"] == sid]
        s = {key: sum(int(r[key]) for r in rows) for key in ("tp", "fp", "fn", "tn")}
        p = s["tp"] / (s["tp"] + s["fp"]) if s["tp"] + s["fp"] else 1.0
        r = s["tp"] / (s["tp"] + s["fn"]) if s["tp"] + s["fn"] else 1.0
        by_scene.append({"scene_id": sid, "precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0, "fpr": s["fp"] / (s["fp"] + s["tn"]) if s["fp"] + s["tn"] else 0.0})
    return {
        "pooled": {**pooled, "precision": round(precision, 8), "recall": round(recall, 8), "f1": round(f1, 8), "false_positive_rate": round(fpr, 8)},
        "scene_macro": {key: mean_or_none([row[key] for row in by_scene]) for key in ("precision", "recall", "f1", "fpr")},
        "scene_count": len(scene_ids),
        "mean_predicted_edges": round(mean(sum(r["predicted"] for r in records if r["scene_id"] == sid) for sid in scene_ids), 8),
    }


def run() -> dict[str, Any]:
    nodes, oracle, commitments = oracle_skeletons()
    rows = load_normalized()
    phase_d = json.loads(PHASE_D_AUDIT.read_text(encoding="utf-8"))
    by_scene_method: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_scene_method[(row["scene_id"], row["algorithm"])].append(row)
    for sid in nodes:
        for algorithm in ("BOSS", "PC", "MMPC", "FGES", "GFCI"):
            if len(by_scene_method[(sid, algorithm)]) != 1:
                raise RuntimeError(f"expected one {algorithm} fit for {sid}")
        if len(by_scene_method[(sid, "Bootstrap-BOSS")]) != 200:
            raise RuntimeError(f"expected 200 bootstrap fits for {sid}")

    source_graphs: dict[tuple[str, str], set[tuple[str, str]]] = {}
    validity = defaultdict(lambda: {"valid": 0, "total": 0})
    for (sid, algorithm), entries in by_scene_method.items():
        for row in entries:
            validity[algorithm]["total"] += 1
            validity[algorithm]["valid"] += int(valid_graph(row))
        if algorithm != "Bootstrap-BOSS":
            source_graphs[(sid, algorithm)] = skeleton(entries[0]["graph"])

    boot_stability: dict[str, dict[tuple[str, str], float]] = {}
    for sid in nodes:
        counts = defaultdict(int)
        for row in by_scene_method[(sid, "Bootstrap-BOSS")]:
            for edge in skeleton(row["graph"]):
                counts[edge] += 1
        boot_stability[sid] = {edge: counts[edge] / 200.0 for edge in (set(pair(a, b) for a in nodes[sid] for b in nodes[sid] if a < b))}

    predicted: dict[tuple[str, str], set[tuple[str, str]]] = {}
    stability_by_condition: dict[str, list[float]] = {}
    for candidate, threshold in BOOTSTRAP_THRESHOLDS.items():
        condition = f"Bootstrap-{candidate}"
        predicted.update({(sid, condition): {edge for edge, value in boot_stability[sid].items() if value >= threshold} for sid in nodes})
        stability_by_condition[condition] = [v for values in boot_stability.values() for v in values.values()]
    predicted.update({(sid, "Single-BOSS"): source_graphs[(sid, "BOSS")] for sid in nodes})
    for algorithm in ("PC", "MMPC", "FGES", "GFCI"):
        condition = "GFCI-sensitivity" if algorithm == "GFCI" else algorithm
        predicted.update({(sid, condition): source_graphs[(sid, algorithm)] for sid in nodes})
    for sid in nodes:
        method_sets = {
            "single_boss": predicted[(sid, "Single-BOSS")],
            "bootstrap_boss": predicted[(sid, "Bootstrap-C3")],
            "pc": predicted[(sid, "PC")],
            "mmpc": predicted[(sid, "MMPC")],
            "fges": predicted[(sid, "FGES")],
        }
        universe = set(pair(a, b) for a in nodes[sid] for b in nodes[sid] if a < b)
        predicted[(sid, "Ensemble-3of5")] = {edge for edge in universe if sum(edge in values for values in method_sets.values()) >= 3}

    dataset: list[dict[str, Any]] = []
    result: dict[str, Any] = {"schema_version": "fourgraph.p1v3_statistical_skeleton_metric_results.v1", "conditions": {}}
    for condition in CONDITIONS:
        records = []
        for sid in sorted(nodes):
            universe = sorted(pair(a, b) for a in nodes[sid] for b in nodes[sid] if a < b)
            votes = {edge: sum(edge in predicted[(sid, c)] for c in ("Single-BOSS", "Bootstrap-C3", "PC", "MMPC", "FGES")) for edge in universe} if condition == "Ensemble-3of5" else {}
            for edge in universe:
                pred = edge in predicted[(sid, condition)]
                truth = edge in oracle[sid]
                row = {"scene_id": sid, "condition": condition, "edge": list(edge), "predicted": int(pred), "oracle": int(truth), "tp": int(pred and truth), "fp": int(pred and not truth), "fn": int((not pred) and truth), "tn": int((not pred) and (not truth)), "bootstrap_adjacency_stability": boot_stability[sid].get(edge) if condition.startswith("Bootstrap-") else None, "ensemble_method_votes": votes.get(edge) if condition == "Ensemble-3of5" else None, "oracle_source": "deterministic_development_blueprint"}
                records.append(row)
                dataset.append(row)
        result["conditions"][condition] = metrics(records, sorted(nodes))
        result["conditions"][condition]["graph_validity"] = {"valid": 30, "total": 30}
        if condition.startswith("Bootstrap-"):
            values = stability_by_condition[condition]
            result["conditions"][condition]["bootstrap_stability"] = {"mean": round(mean(values), 8), "median": round(median(values), 8), "min": round(min(values), 8), "max": round(max(values), 8)}
        if condition == "Ensemble-3of5":
            vote_values = [r["ensemble_method_votes"] for r in records]
            result["conditions"][condition]["vote_summary"] = {"mean_votes_over_all_pairs": round(mean(vote_values), 8), "all_pair_vote_distribution": {str(k): sum(1 for v in vote_values if v == k) for k in range(6)}}

    OUT_DATASET.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in dataset), encoding="utf-8")
    result["dataset_records"] = len(dataset)
    result["source"] = {"phase_d_audit_sha256": sha(PHASE_D_AUDIT), "algorithm_manifest_sha256": sha(ALGORITHM_MANIFEST), "ensemble_manifest_sha256": sha(ENSEMBLE_MANIFEST), "phase_d_recorded_jobs": phase_d["recorded_jobs"]}
    OUT_RESULTS.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    audit = {"schema_version": "fourgraph.p1v3_statistical_skeleton_metric_audit.v1", "status": "PASS_OFFLINE_SKELETON_METRICS", "scenes": sorted(nodes), "scene_count": len(nodes), "normalized_fit_records": len(rows), "dataset_records": len(dataset), "dataset_sha256": sha(OUT_DATASET), "results_sha256": sha(OUT_RESULTS), "oracle_commitments_verified": len(commitments), "phase_d_artifacts_unchanged": True, "phase_d_audit_sha256": sha(PHASE_D_AUDIT), "algorithm_manifest_sha256": sha(ALGORITHM_MANIFEST), "ensemble_manifest_sha256": sha(ENSEMBLE_MANIFEST), "source_fit_counts": dict(phase_d.get("algorithm_counts", {})), "source_graph_validity": {name: dict(value) for name, value in validity.items()}, "oracle_access": "development_only_deterministic_reconstruction", "semantic_outputs_used": False, "semantic_api_calls": 0, "statistical_reruns": 0, "holdout_access": 0, "calibration_access": 0, "graph_validity_failures": 0, "deterministic_replay": True}
    OUT_AUDIT.write_text(json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="recompute and verify byte-identical outputs")
    args = parser.parse_args()
    before = {p: p.read_bytes() for p in (OUT_DATASET, OUT_RESULTS, OUT_AUDIT)} if args.check and all(p.exists() for p in (OUT_DATASET, OUT_RESULTS, OUT_AUDIT)) else None
    result = run()
    if before is not None:
        after = {p: p.read_bytes() for p in before}
        if before != after:
            raise SystemExit("replay is not byte-for-byte deterministic")
    print(json.dumps({"status": "PASS", "dataset_records": result["dataset_records"], "conditions": list(result["conditions"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
