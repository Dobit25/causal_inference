"""Score frozen Nano/Mini automatic directions against regenerated development Oracle DAGs only."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
from materialize_p1_v4_stage3 import build_blueprint  # noqa: E402
from fourgraph.p1_generation import scene_scm_record  # noqa: E402

CONFIG = ROOT / "configs/p1_v4_stage3_paired_oracle_scoring_authorization_checkpoint.yaml"
AUTH = ROOT / "data/manifests/p1_v4_stage3_paired_oracle_scoring_authorization.json"
IDENTITIES = ROOT / "data/manifests/p1_v4_stage3_exact_identities.jsonl"
PREFLIGHT = ROOT / "configs/p1_v4_stage3_method_development_preflight.yaml"
POOLS = ROOT / "data/manifests/p1_v4_stage3_condition_pair_pools_cau.json"


def canonical(value: Any) -> bytes: return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()
def lines(path: Path) -> list[dict[str, Any]]: return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_oracles() -> dict[str, set[tuple[str, str]]]:
    cfg = yaml.safe_load(PREFLIGHT.read_text(encoding="utf-8")); generation = cfg["generation"]
    allowed = {f"P1V4SD{i:03d}" for i in range(30)}
    identities = [row for row in lines(IDENTITIES) if row.get("study_id") in allowed]
    if len(identities) != 30 or {row["study_id"] for row in identities} != allowed: raise RuntimeError("exact development identity scope mismatch")
    result = {}
    for identity in identities:
        blueprint = build_blueprint(identity, generation)
        commitment = hashlib.sha256(canonical(scene_scm_record(blueprint))).hexdigest().upper()
        metadata = json.loads((ROOT / "data/generated/p1_v4_stage3_method_development_cau" / identity["study_id"] / "metadata.json").read_text(encoding="utf-8"))
        if commitment != metadata.get("scm_commitment_sha256"): raise RuntimeError(f"Oracle replay commitment mismatch: {identity['study_id']}")
        result[identity["study_id"]] = set(blueprint.dag.directed)
    return result


def main() -> int:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8")); auth = json.loads(AUTH.read_text(encoding="utf-8"))
    checkpoint = ROOT / config["outputs"]["checkpoint"]
    if auth.get("status") != "ELIGIBLE_WAITING_FOR_ORACLE_SCORING_EXECUTION" or not auth.get("explicit_user_oracle_scoring_authorization") or auth.get("checkpoint_sha256") != sha(checkpoint):
        raise RuntimeError("explicit paired Oracle-scoring authorization is absent or stale")
    for parent in config["parents"].values():
        if sha(ROOT / parent["path"]) != parent["sha256"]: raise RuntimeError(f"frozen parent hash drift: {parent['path']}")
    pools = {row["study_id"]: row for row in json.loads(POOLS.read_text(encoding="utf-8"))["records"]}
    oracles = load_oracles()
    dataset: list[dict[str, Any]] = []
    summaries: dict[str, Any] = {}
    for label, group_key in (("nano_medium", "nano_six_vote_groups"), ("mini_medium", "mini_six_vote_groups")):
        groups = lines(ROOT / config["parents"][group_key]["path"])
        if len(groups) != 236: raise RuntimeError("unexpected frozen six-vote group count")
        scored = []
        for row in groups:
            pool = pools[row["scene_id"]]; pair = next((item for item in pool["shared_union_pairs"] if item["pair_id"] == row["pair_id"]), None)
            if pair is None: raise RuntimeError("group pair absent from frozen pool")
            selected = bool(row["automatic_candidate"]) and row.get("candidate_direction") in {"A_TO_B", "B_TO_A"}
            predicted = None
            if selected:
                predicted = (pair["node_a_id"], pair["node_b_id"]) if row["candidate_direction"] == "A_TO_B" else (pair["node_b_id"], pair["node_a_id"])
            correct = predicted in oracles[row["scene_id"]] if predicted else None
            record = {"schema_version": "fourgraph.p1_v4_paired_oracle_direction_record.v1", "model_label": label, "scene_id": row["scene_id"], "variant": row["variant"], "pair_id": row["pair_id"], "agreement": row["agreement"], "completeness": row["completeness"], "automatic_candidate": row["automatic_candidate"], "candidate_direction": row["candidate_direction"], "node_a_id": pair["node_a_id"], "node_b_id": pair["node_b_id"], "predicted_direction": list(predicted) if predicted else None, "oracle_match": correct}
            dataset.append(record); scored.append(record)
        strata = {}
        for variant in ("full", "partial", "all"):
            sub = [row for row in scored if variant == "all" or row["variant"] == variant]; selected = [row for row in sub if row["automatic_candidate"]]
            correct = sum(row["oracle_match"] is True for row in selected); wrong = sum(row["oracle_match"] is False for row in selected)
            by_scene = defaultdict(list)
            for row in selected: by_scene[row["scene_id"]].append(row)
            strata[variant] = {"six_vote_groups": len(sub), "automatic_directions": len(selected), "correct": correct, "wrong": wrong, "orientation_precision": (correct / len(selected)) if selected else None, "candidate_fraction": len(selected) / len(sub) if sub else None, "abstention_fraction": 1 - len(selected) / len(sub) if sub else None, "contributing_scenes": len(by_scene), "scene_macro_precision": sum(sum(x["oracle_match"] is True for x in values) / len(values) for values in by_scene.values()) / len(by_scene) if by_scene else None}
        summaries[label] = strata
    dataset_path = ROOT / "data/manifests/p1_v4_stage3_paired_oracle_metric_dataset.jsonl"; dataset_path.write_bytes(b"".join(canonical(row) for row in dataset))
    results = {"schema_version": "fourgraph.p1_v4_stage3_paired_oracle_scoring_results.v1", "task": "P1_V4_STAGE_3D_PAIRED_ORACLE_SCORING_EXECUTION", "status": "PASS", "models": summaries, "dataset_sha256": sha(dataset_path), "oracle_scope": "P1V4SD000-P1V4SD029 development only", "closure": 0, "threshold_tuning": 0, "semantic_api_calls": 0, "holdout_access": 0}
    results_path = ROOT / "data/manifests/p1_v4_stage3_paired_oracle_scoring_results.json"; results_path.write_bytes(canonical(results))
    audit = {"schema_version": "fourgraph.p1_v4_stage3_paired_oracle_scoring_audit.v1", "task": results["task"], "status": "PASS", "authorization_sha256": sha(AUTH), "metric_dataset_sha256": sha(dataset_path), "results_sha256": sha(results_path), "oracle_scenes_accessed": 30, "oracle_scene_ids": [f"P1V4SD{i:03d}" for i in range(30)], "oracle_replay_commitments_passed": 30, "holdout_access": 0, "semantic_api_calls": 0, "closure": 0, "threshold_tuning": 0}
    audit_path = ROOT / "data/manifests/p1_v4_stage3_paired_oracle_scoring_audit.json"; audit_path.write_bytes(canonical(audit))
    report = "# P1V4 paired Nano/Mini Oracle scoring\n\nThis is development-only scoring of the pre-registered automatic (`VERY_HIGH`/`HIGH`) policy on frozen six-vote groups. No closure, threshold tuning, API call, statistical rerun, or holdout access occurred.\n"
    (ROOT / "reports/p1_v4_stage3_paired_oracle_scoring.md").write_text(report, encoding="utf-8")
    print(json.dumps({"results": summaries, "audit": audit}, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
