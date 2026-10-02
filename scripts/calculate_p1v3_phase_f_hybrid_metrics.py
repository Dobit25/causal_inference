"""Compute Phase-F hybrid metrics from the frozen Case-B replay only.

This script performs no provider calls and no statistical discovery.  Oracle
development DAGs are reconstructed deterministically in memory from the
already frozen successor generator/identity plan; no new study artifact is
materialized.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

REPLAY = ROOT / "data/manifests/p1v3_phase_e_incident_resolution_replay.jsonl"
REPLAY_AUDIT = ROOT / "data/manifests/p1v3_phase_e_incident_resolution_amendment_audit.json"
AMENDMENT = ROOT / "configs/p1v3_phase_e_incident_resolution_amendment.yaml"
METRIC_CONFIG = ROOT / "configs/p1v3_phase_f_hybrid_metric_calculation.yaml"
CHECKPOINT = ROOT / "data/manifests/p1v3_phase_f_hybrid_metric_calculation_authorization_audit.json"
DATASET = ROOT / "data/manifests/p1v3_phase_f_hybrid_metric_dataset.jsonl"
RESULTS = ROOT / "data/manifests/p1v3_phase_f_hybrid_metric_results.json"
RISK = ROOT / "data/manifests/p1v3_phase_f_hybrid_risk_coverage.jsonl"
AUDIT = ROOT / "data/manifests/p1v3_phase_f_hybrid_metric_audit.json"
REPORT = ROOT / "reports/p1v3_phase_f_hybrid_metric_report.md"
IDENTITIES = ROOT / "data/manifests/p1_v3_successor_sequential_exact_identities.jsonl"
GEN_CONFIG = ROOT / "configs/p1_v3_successor_method_development_preflight.yaml"

EXPECTED = {
    "replay_audit": "AAA8FEEAC1AA5BA846338D9B5AD502623513EA9CC0986C7A8C31AFC6D63EEB40",
    "replay": "8303E74BD2F9DCD447539CFD7ED06DF94DBEF30DFCCD0D63EA3322E6AE2BCDFD",
    "amendment": "F93925E6E10321A16B8A249743D276F555DD710BBEF7129589729AC9FA70193F",
}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def canon(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def load_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def reconstruct_oracles() -> tuple[dict[str, set[tuple[str, str]]], dict[str, dict[str, Any]]]:
    # This is development-only truth reconstruction, not a statistical fit or
    # study-scene materialization.  It is checked against each frozen scene's
    # SCM commitment before metrics are accepted.
    sys.path.insert(0, str(ROOT / "scripts"))
    from materialize_p1v3_development import build_blueprint, load_identities
    from fourgraph.p1_generation import scene_scm_record

    generator = yaml.safe_load(GEN_CONFIG.read_text(encoding="utf-8"))["generator"]
    identities = load_identities(IDENTITIES)
    oracle: dict[str, set[tuple[str, str]]] = {}
    skeletons: dict[str, set[tuple[str, str]]] = {}
    for identity in identities:
        blueprint = build_blueprint(identity, generator)
        metadata = json.loads((ROOT / "results/p1v3_statistical_ensemble/scenes" / identity["study_id"] / "metadata.json").read_text())
        commitment = sha_bytes(canon(scene_scm_record(blueprint)))
        if commitment != metadata["scm_commitment_sha256"]:
            raise RuntimeError(f"SCM commitment mismatch for {identity['study_id']}")
        directed = {tuple(edge) for edge in blueprint.dag.directed}
        oracle[identity["study_id"]] = directed
        skeletons[identity["study_id"]] = {tuple(sorted(edge)) for edge in directed}
    if len(oracle) != 30:
        raise RuntimeError("development Oracle reconstruction is not exactly 30 scenes")
    return oracle, {sid: {"directed": oracle[sid], "skeleton": skeletons[sid]} for sid in oracle}


def build_parent_conditions():
    sys.path.insert(0, str(ROOT / "scripts"))
    from run_p1v3_phase_e_shared_semantic_v3 import build_conditions
    return build_conditions()[0]


def metric_row(row: dict[str, Any], parent: Any, oracle: dict[str, Any], *, idx: int) -> list[dict[str, Any]]:
    parent_undirected = {tuple(edge) for edge in parent.undirected}
    parent_directed = {tuple(edge) for edge in parent.directed}
    output_directed = {tuple(edge) for edge in row["output_graph"].get("directed", [])}
    new_published = output_directed - parent_directed
    selected = {tuple(edge) for edge in row["selected_after_filter"]}
    direct = selected & new_published if row["status"] == "PASS" else set()
    propagated = new_published - direct
    out_by_pair = {tuple(sorted(edge)): edge for edge in new_published}
    records: list[dict[str, Any]] = []
    for pair in sorted(parent_undirected):
        direction = out_by_pair.get(pair)
        source = "unresolved"
        if direction in direct:
            source = "semantic_selected"
        elif direction in propagated:
            source = "closure_propagated"
        published = direction is not None
        correct = bool(published and direction in oracle["directed"])
        false_adj = bool(published and pair not in oracle["skeleton"])
        records.append({
            "record_id": f"{row['scene_id']}|{row['variant']}|{row['condition']}|{idx:04d}",
            "scene_id": row["scene_id"], "variant": row["variant"], "condition": row["condition"],
            "parent_graph_sha256": row["parent_graph_sha256"], "replay_status": row["status"],
            "parent_candidate_pair": list(pair), "published": published,
            "direction": list(direction) if direction else None, "source": source,
            "correct": correct if published else None, "false_adjacency_orientation": false_adj if published else False,
            "parent_valid": row["status"] != "FAIL_CLOSED_PARENT",
            "global_conflict_fail_closed": row["status"] == "FAIL_CLOSED_GLOBAL_CONFLICT",
        })
    return records


def frac(num: int, den: int) -> float | None:
    return None if den == 0 else round(num / den, 8)


def run() -> dict[str, Any]:
    actual = {"replay_audit": sha_file(REPLAY_AUDIT), "replay": sha_file(REPLAY), "amendment": sha_file(AMENDMENT)}
    if actual != EXPECTED:
        raise RuntimeError(f"frozen source hash mismatch: {actual}")
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    if checkpoint.get("status") != "PASS_AUTHORIZED_OFFLINE_METRICS":
        raise RuntimeError("Phase-F authorization checkpoint is not PASS")
    replay = load_lines(REPLAY)
    if len(replay) != 480 or len({(r["scene_id"], r["variant"], r["condition"]) for r in replay}) != 480:
        raise RuntimeError("replay is not exactly 480 unique condition records")
    if sum(len(r["dropped_outside_parent"]) for r in replay if r["status"] != "FAIL_CLOSED_PARENT") != 531:
        raise RuntimeError("out-of-parent count does not match frozen audit")
    if sum(r["status"] == "FAIL_CLOSED_PARENT" for r in replay) != 108:
        raise RuntimeError("parent fail-closed count does not match frozen audit")
    if sum(r["status"] == "FAIL_CLOSED_GLOBAL_CONFLICT" for r in replay) != 15:
        raise RuntimeError("global conflict count does not match frozen audit")

    conditions = build_parent_conditions()
    _, oracles = reconstruct_oracles()
    dataset: list[dict[str, Any]] = []
    by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for idx, row in enumerate(replay):
        parent = conditions[row["scene_id"]][row["condition"]]
        records = metric_row(row, parent, oracles[row["scene_id"]], idx=idx)
        dataset.extend(records)
        by_condition[row["condition"]].extend(records)
    DATASET.write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in dataset), encoding="utf-8")

    summaries: dict[str, Any] = {}
    for condition in sorted(by_condition):
        rows = by_condition[condition]
        published = [r for r in rows if r["published"]]
        direct = [r for r in published if r["source"] == "semantic_selected"]
        closure = [r for r in published if r["source"] == "closure_propagated"]
        correct = [r for r in published if r["correct"]]
        false_adj = [r for r in published if r["false_adjacency_orientation"]]
        def source_summary(items):
            return {"published": len(items), "correct": sum(x["correct"] for x in items), "precision": frac(sum(x["correct"] for x in items), len(items))}
        by_variant = {}
        for variant in ("full", "partial"):
            v = [r for r in rows if r["variant"] == variant]
            vp = [r for r in v if r["published"]]
            by_variant[variant] = {"candidate_edges": len(v), "published": len(vp), "correct": sum(x["correct"] for x in vp), "precision": frac(sum(x["correct"] for x in vp), len(vp)), "coverage": frac(len(vp), len(v)), "abstention_rate": frac(len(v)-len(vp), len(v)), "false_adjacency_orientation_errors": sum(x["false_adjacency_orientation"] for x in vp)}
        summaries[condition] = {
            "candidate_edges": len(rows), "published_directions": len(published), "correct_directions": len(correct),
            "orientation_precision": frac(len(correct), len(published)), "coverage": frac(len(published), len(rows)),
            "abstention_rate": frac(len(rows)-len(published), len(rows)), "false_adjacency_orientation_errors": len(false_adj),
            "parent_fail_closed_records": sum(not r["parent_valid"] for r in rows),
            "global_conflict_fail_closed_records": sum(r["global_conflict_fail_closed"] for r in rows),
            "semantic_selected": source_summary(direct), "closure_propagated": source_summary(closure),
            "by_variant": by_variant,
        }

    risk_rows: list[dict[str, Any]] = []
    for condition, summary in summaries.items():
        risk_rows.append({"condition": condition, "point": "abstain_all", "coverage": 0.0, "risk": 0.0, "basis": "observed_endpoint"})
        risk_rows.append({"condition": condition, "point": "observed_output", "coverage": summary["coverage"], "risk": None if summary["orientation_precision"] is None else round(1-summary["orientation_precision"], 8), "basis": "frozen_replay_no_threshold_tuning"})
        for variant, v in summary["by_variant"].items():
            risk_rows.append({"condition": condition, "variant": variant, "point": "observed_output", "coverage": v["coverage"], "risk": None if v["precision"] is None else round(1-v["precision"], 8), "basis": "frozen_replay_no_threshold_tuning"})
    RISK.write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in risk_rows), encoding="utf-8")

    results = {"schema_version": "fourgraph.p1v3_phase_f_hybrid_metric_results.v1", "status": "COMPLETED_OFFLINE_METRICS", "dataset_records": len(dataset), "conditions": summaries, "restrictions": {"calibration": False, "threshold_tuning": False, "downstream_reasoner": False, "significance_testing": False, "api_calls": 0, "statistical_discovery": 0, "oracle_scope": "30 development scenes only", "holdout_access": 0}}
    RESULTS.write_bytes(canon(results))
    audit = {"schema_version": "fourgraph.p1v3_phase_f_hybrid_metric_audit.v1", "status": "PASS_METRICS_ONLY", "source_hashes": actual, "checkpoint_sha256": sha_file(CHECKPOINT), "replay_records": len(replay), "metric_dataset_records": len(dataset), "oracle_development_reconstructed": 30, "oracle_commitments_verified": 30, "holdout_access": 0, "api_calls": 0, "statistical_fits": 0, "calibration": False, "threshold_tuning": False, "downstream_reasoner": False, "significance_testing": False, "provider_incident": "P1V3SD028/full/P1 remains missing; no retry", "results_sha256": sha_file(RESULTS), "risk_coverage_sha256": sha_file(RISK), "dataset_sha256": sha_file(DATASET)}
    AUDIT.write_bytes(canon(audit))
    REPORT.write_text("# Phase F — Hybrid metrics\n\nStatus: **PASS — metrics computed offline only.**\n\n" + json.dumps(results, ensure_ascii=False, indent=2) + "\n\nThe frozen Case-B replay was scored against 30 development-only deterministic Oracle DAG reconstructions. No API, statistical discovery, calibration, tuning, downstream reasoner or holdout access occurred. Risk–coverage output contains observed endpoints only; no threshold was selected.\n", encoding="utf-8")
    return {"audit": audit, "results": results}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
