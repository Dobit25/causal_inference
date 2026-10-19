"""Freeze complete Nano/Mini raw sets, then re-score pair and six-vote records offline."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fourgraph.semantic_pair_contract_v2 import StablePair  # noqa: E402
from fourgraph.semantic_sentence_id_contract import aggregate_six_votes, validate_response_by_pair  # noqa: E402
from fourgraph.semantic_sentence_id_contract_reference import reference_aggregate, reference_validate  # noqa: E402

PLAN = ROOT / "data/manifests/p1_v4_stage3_shared_semantic_execution_plan_cau.json"
NANO = ROOT / "results/raw/p1_v4_stage3_method_development_cau/semantic/raw_responses.jsonl"
MINI = ROOT / "results/raw/p1_v4_stage3_method_development_cau/semantic_mini_medium/raw_responses.jsonl"
PUBLIC = ROOT / "data/manifests/p1_v4_stage3_public_semantic_inputs_cau.json"
POOLS = ROOT / "data/manifests/p1_v4_stage3_condition_pair_pools_cau.json"
NANO_AUDIT = ROOT / "data/manifests/p1_v4_stage3_nano_response_completion_audit.json"
MINI_AUDIT = ROOT / "data/manifests/p1_v4_stage3_mini_medium_paired_execution_audit.json"
FREEZE = ROOT / "data/manifests/p1_v4_stage3_paired_model_response_freeze.json"
AUDIT = ROOT / "data/manifests/p1_v4_stage3_paired_model_rescore_audit.json"
REPORT = ROOT / "reports/p1_v4_stage3_paired_model_response_freeze.md"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_json(path: Path, value: Any) -> None: path.write_bytes(canonical(value))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_bytes(b"".join(canonical(row) for row in rows))


def load_json(path: Path) -> Any: return json.loads(path.read_text(encoding="utf-8"))


def selected_rows(path: Path, *, nano: bool, expected: set[str]) -> dict[str, dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    terminal = {"completed_valid", "completed_pair_invalid", "completed_schema_invalid"}
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows: by_id[str(row.get("logical_id"))].append(row)
    result: dict[str, dict[str, Any]] = {}
    for logical_id, candidates in by_id.items():
        ok = [row for row in candidates if row.get("status") in terminal]
        if ok: result[logical_id] = max(ok, key=lambda row: int(row.get("attempt", 0)))
    if set(result) != expected:
        raise RuntimeError(f"missing/nonterminal logical responses in {'Nano' if nano else 'Mini'}")
    if nano and len(rows) != 361: raise RuntimeError("Nano history must preserve 361 attempt records")
    if not nano and len(rows) != 360: raise RuntimeError("Mini history must contain exactly 360 records")
    return result


def inputs() -> tuple[list[dict[str, Any]], dict[tuple[str, str], str], dict[str, tuple[StablePair, ...]]]:
    plan = load_json(PLAN)
    public = load_json(PUBLIC); pools = load_json(POOLS)
    stories = {(row["study_id"], row["variant"]): load_json(ROOT / row["artifact_path"])["builder_input"]["story"] for row in public["records"]}
    by_scene = {row["study_id"]: tuple(StablePair(**pair) for pair in row["shared_union_pairs"]) for row in pools["records"]}
    return plan["logical_calls"], stories, by_scene


def records_for_model(model_label: str, selected: dict[str, dict[str, Any]], plan_rows: list[dict[str, Any]], stories: dict[tuple[str, str], str], pairs_by_scene: dict[str, tuple[StablePair, ...]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    pair_records: list[dict[str, Any]] = []; vote_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list); disagreements = 0
    for item in plan_rows:
        raw = selected[item["logical_id"]]; pairs = pairs_by_scene[item["study_id"]]; story = stories[(item["study_id"], item["variant"])]
        try: response = json.loads(raw["raw_text"])
        except Exception: response = object()
        production = validate_response_by_pair(response, pairs, story)
        by_pair = {row.get("pair_id"): row for row in response.get("judgments", [])} if isinstance(response, dict) and isinstance(response.get("judgments"), list) else {}
        for pair, prod in zip(pairs, production["pairs"]):
            reference = reference_validate(by_pair.get(pair.pair_id), {"pair_id": pair.pair_id, "A": pair.node_a_alias, "B": pair.node_b_alias}, story)
            keys = ("pair_valid", "validator_status", "direction")
            if any(prod.get(key) != reference.get(key) for key in keys): disagreements += 1
            record = {"schema_version": "fourgraph.p1_v4_paired_model_pair_record.v1", "model_label": model_label, "model_snapshot": raw.get("model_snapshot"), "logical_id": item["logical_id"], "scene_id": item["study_id"], "variant": item["variant"], "prompt_id": item["prompt_id"], "pair_id": pair.pair_id, "node_a_alias": pair.node_a_alias, "node_b_alias": pair.node_b_alias, "model_status": prod.get("model_status"), "validator_status": prod.get("validator_status"), "pair_valid": prod.get("pair_valid"), "direction": prod.get("direction"), "evidence_sentence_ids": prod.get("evidence_sentence_ids"), "response_sha256": raw.get("response_sha256"), "raw_status": raw.get("status")}
            pair_records.append(record); vote_groups[(item["study_id"], item["variant"], pair.pair_id)].append(record)
    group_records: list[dict[str, Any]] = []
    for (scene_id, variant, pair_id), votes in sorted(vote_groups.items()):
        votes = sorted(votes, key=lambda row: row["prompt_id"])
        production = aggregate_six_votes(votes, balanced=True); reference = reference_aggregate(votes, balanced=True)
        keys = ("valid_votes", "completeness", "agreement", "automatic_candidate", "review_candidate", "candidate_direction")
        if any(production.get(key) != reference.get(key) for key in keys): disagreements += 1
        group_records.append({"schema_version": "fourgraph.p1_v4_paired_model_six_vote_group.v1", "model_label": model_label, "scene_id": scene_id, "variant": variant, "pair_id": pair_id, "prompt_ids": [row["prompt_id"] for row in votes], "valid_votes": production["valid_votes"], "invalid_votes": production["invalid_votes"], "completeness": production["completeness"], "agreement": production["agreement"], "vote_counts": production["vote_counts"], "automatic_candidate": production["automatic_candidate"], "review_candidate": production["review_candidate"], "candidate_direction": production["candidate_direction"], "automatically_published": False})
    return pair_records, group_records, disagreements


def main() -> int:
    nano_audit, mini_audit = load_json(NANO_AUDIT), load_json(MINI_AUDIT)
    if nano_audit.get("status") != "PASS_LOGICAL_COMPLETION" or mini_audit.get("status") != "PASS": raise RuntimeError("both model raw sets must complete before paired freeze")
    plan_rows, stories, pairs_by_scene = inputs(); expected = {row["logical_id"] for row in plan_rows}
    nano = selected_rows(NANO, nano=True, expected=expected); mini = selected_rows(MINI, nano=False, expected=expected)
    freeze = {"schema_version": "fourgraph.p1_v4_stage3_paired_model_response_freeze.v1", "task": "P1_V4_STAGE_3D_PAIRED_RESPONSE_FREEZE_AND_OFFLINE_RESCORE", "status": "PASS_FROZEN",
              "execution_plan_sha256": sha(PLAN), "public_story_manifest_sha256": sha(PUBLIC), "pair_pools_sha256": sha(POOLS),
              "models": {"nano_medium": {"raw_sha256": sha(NANO), "completion_audit_sha256": sha(NANO_AUDIT), "logical_responses": 360, "historical_attempt_records": 361}, "mini_medium": {"raw_sha256": sha(MINI), "execution_audit_sha256": sha(MINI_AUDIT), "logical_responses": 360, "historical_attempt_records": 360}},
              "frozen_before": ["oracle_scoring", "precision_metrics", "coverage_metrics", "closure", "scientific_comparison"], "oracle_access": 0, "holdout_access": 0}
    write_json(FREEZE, freeze)
    all_summaries: dict[str, Any] = {}
    for label, rows in (("nano_medium", nano), ("mini_medium", mini)):
        pairs, groups, disagreements = records_for_model(label, rows, plan_rows, stories, pairs_by_scene)
        pair_path = ROOT / f"data/manifests/p1_v4_stage3_{label}_pair_rescore.jsonl"; group_path = ROOT / f"data/manifests/p1_v4_stage3_{label}_six_vote_groups.jsonl"
        write_jsonl(pair_path, pairs); write_jsonl(group_path, groups)
        all_summaries[label] = {"pair_records": len(pairs), "six_vote_groups": len(groups), "production_reference_disagreements": disagreements, "pair_record_sha256": sha(pair_path), "six_vote_group_sha256": sha(group_path), "valid_pair_records": sum(row["pair_valid"] is True for row in pairs), "invalid_pair_records": sum(row["pair_valid"] is False for row in pairs), "agreement_counts": dict(sorted(Counter(row["agreement"] for row in groups).items())), "completeness_counts": dict(sorted(Counter(row["completeness"] for row in groups).items()))}
    audit = {"schema_version": "fourgraph.p1_v4_stage3_paired_model_rescore_audit.v1", "task": "P1_V4_STAGE_3D_PAIRED_RESPONSE_FREEZE_AND_OFFLINE_RESCORE", "status": "PASS" if all(value["production_reference_disagreements"] == 0 for value in all_summaries.values()) else "FAIL_VALIDATOR_DISAGREEMENT", "response_freeze_sha256": sha(FREEZE), "models": all_summaries, "expected_logical_calls_per_model": 360, "oracle_access": 0, "holdout_access": 0, "semantic_api_calls": 0, "closure": 0, "precision_metrics": 0, "coverage_metrics": 0}
    write_json(AUDIT, audit)
    REPORT.write_text("# P1V4 paired response freeze and offline re-score\n\nNano-medium and Mini-medium raw datasets are frozen together. Pair-level validator replay and balanced six-vote aggregation ran offline, with an independently structured reference validator. This artifact contains no Oracle scoring, precision/coverage metric, closure, or scientific comparison.\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2)); return 0 if audit["status"] == "PASS" else 1


if __name__ == "__main__": raise SystemExit(main())
