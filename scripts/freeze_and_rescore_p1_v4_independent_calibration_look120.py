"""Freeze Mini raw responses, validate pairs independently, and aggregate six votes offline."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from fourgraph.semantic_sentence_id_contract import aggregate_six_votes, validate_response_by_pair  # noqa: E402
from fourgraph.semantic_sentence_id_contract_reference import reference_aggregate, reference_validate  # noqa: E402
from scripts.run_p1_v4_independent_calibration_look120_mini_semantic import build_jobs  # noqa: E402

CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_response_freeze_rescore.yaml"


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_once(path: Path, value: object, *, lines: bool = False) -> None:
    payload = b"".join(canonical(item) for item in value) if lines else canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise RuntimeError(f"non-deterministic artifact drift: {path}")
    if not path.exists():
        path.write_bytes(payload)


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for parent in cfg["parents"].values():
        path = ROOT / parent["path"]
        if not path.is_file() or sha(path) != parent["sha256"]:
            raise RuntimeError(f"parent hash drift: {parent['path']}")
    raw = load_jsonl(ROOT / cfg["parents"]["raw_responses"]["path"])
    retry = load_jsonl(ROOT / cfg["parents"]["retry_responses"]["path"])
    if len(raw) != cfg["scope"]["raw_history_records"] or len({row.get("logical_id") for row in raw}) != len(raw):
        raise RuntimeError("raw response history is incomplete or duplicate")
    raw_by_id = {str(row["logical_id"]): row for row in raw}
    historical_errors = [row for row in raw if row.get("status") == "provider_error"]
    retry_by_id = {str(row.get("logical_id")): row for row in retry}
    if len(historical_errors) != 2 or len(retry_by_id) != cfg["scope"]["separately_resolved_transport_retries"]:
        raise RuntimeError("transport incident/retry cardinality drift")
    effective = dict(raw_by_id)
    for logical_id, row in retry_by_id.items():
        prior = effective.get(logical_id)
        if prior is None or prior.get("status") != "provider_error" or row.get("status") == "provider_error":
            raise RuntimeError("transport retry cannot resolve historical record")
        effective[logical_id] = row

    build_cfg = {"parents": {"execution_plan": cfg["parents"]["execution_plan"]}, "scope": {"logical_calls": cfg["scope"]["logical_calls"]}, "semantic_contract": cfg["semantic_contract"]}
    jobs = build_jobs(build_cfg)
    expected = [job["logical_id"] for job in jobs]
    if set(effective) != set(expected):
        raise RuntimeError("effective response identities do not match frozen plan")

    freeze = {"schema_version": "fourgraph.p1_v4_calibration_response_freeze.v1", "task": cfg["task"], "status": "PASS_FROZEN", "config_sha256": sha(CONFIG), "execution_plan_sha256": sha(ROOT / cfg["parents"]["execution_plan"]["path"]), "raw_response_sha256": sha(ROOT / cfg["parents"]["raw_responses"]["path"]), "retry_response_sha256": sha(ROOT / cfg["parents"]["retry_responses"]["path"]), "token_ledger_sha256": sha(ROOT / cfg["parents"]["token_ledger"]["path"]), "raw_history_records": len(raw), "effective_logical_responses": len(effective), "historical_provider_errors_retained": len(historical_errors), "resolved_transport_retries": sorted(retry_by_id), "frozen_before": ["oracle_scoring", "precision_metrics", "coverage_metrics", "closure", "threshold_selection"], "oracle_access": 0, "holdout_access": 0, "semantic_api_calls": 0}
    write_once(ROOT / cfg["outputs"]["response_freeze"], freeze)

    pairs: list[dict[str, Any]] = []
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    disagreement_count = 0
    for job in jobs:
        raw_record = effective[job["logical_id"]]
        try:
            response = json.loads(str(raw_record.get("raw_text", "")))
        except json.JSONDecodeError:
            response = object()
        production = validate_response_by_pair(response, job["pairs"], job["story"])
        by_pair = {row.get("pair_id"): row for row in response.get("judgments", [])} if isinstance(response, dict) and isinstance(response.get("judgments"), list) else {}
        for pair, prod in zip(job["pairs"], production["pairs"]):
            ref = reference_validate(by_pair.get(pair.pair_id), {"pair_id": pair.pair_id, "A": pair.node_a_alias, "B": pair.node_b_alias}, job["story"])
            if any(prod.get(key) != ref.get(key) for key in ("pair_valid", "validator_status", "direction")):
                disagreement_count += 1
            record = {"schema_version": "fourgraph.p1_v4_calibration_pair_rescore.v1", "logical_id": job["logical_id"], "scene_id": job["study_id"], "variant": job["variant"], "prompt_id": job["prompt_id"], "pair_id": pair.pair_id, "node_a_alias": pair.node_a_alias, "node_b_alias": pair.node_b_alias, "model_status": prod.get("model_status"), "validator_status": prod.get("validator_status"), "pair_valid": prod.get("pair_valid"), "direction": prod.get("direction"), "evidence_sentence_ids": prod.get("evidence_sentence_ids"), "response_sha256": raw_record.get("response_sha256"), "raw_status": raw_record.get("status"), "effective_source": "transport_retry" if job["logical_id"] in retry_by_id else "primary_raw"}
            pairs.append(record); groups[(job["study_id"], job["variant"], pair.pair_id)].append(record)

    group_rows: list[dict[str, Any]] = []
    for (scene_id, variant, pair_id), votes in sorted(groups.items()):
        votes = sorted(votes, key=lambda row: row["prompt_id"])
        prod = aggregate_six_votes(votes, balanced=True); ref = reference_aggregate(votes, balanced=True)
        if any(prod.get(key) != ref.get(key) for key in ("valid_votes", "completeness", "agreement", "automatic_candidate", "review_candidate", "candidate_direction")):
            disagreement_count += 1
        group_rows.append({"schema_version": "fourgraph.p1_v4_calibration_six_vote_group.v1", "scene_id": scene_id, "variant": variant, "pair_id": pair_id, "prompt_ids": [row["prompt_id"] for row in votes], "valid_votes": prod["valid_votes"], "invalid_votes": prod["invalid_votes"], "completeness": prod["completeness"], "agreement": prod["agreement"], "vote_counts": prod["vote_counts"], "automatic_candidate": prod["automatic_candidate"], "review_candidate": prod["review_candidate"], "candidate_direction": prod["candidate_direction"], "automatically_published": False})
    if len(group_rows) != cfg["scope"]["expected_six_vote_groups"]:
        raise RuntimeError("six-vote group count drift")
    write_once(ROOT / cfg["outputs"]["pair_records"], pairs, lines=True)
    write_once(ROOT / cfg["outputs"]["six_vote_groups"], group_rows, lines=True)
    audit = {"schema_version": "fourgraph.p1_v4_calibration_response_freeze_rescore_audit.v1", "task": cfg["task"], "status": "PASS" if disagreement_count == 0 else "FAIL_VALIDATOR_DISAGREEMENT", "response_freeze_sha256": sha(ROOT / cfg["outputs"]["response_freeze"]), "effective_logical_responses": len(effective), "pair_records": len(pairs), "six_vote_groups": len(group_rows), "production_reference_disagreements": disagreement_count, "valid_pair_records": sum(row["pair_valid"] is True for row in pairs), "invalid_pair_records": sum(row["pair_valid"] is False for row in pairs), "validator_status_counts": dict(sorted(Counter(str(row["validator_status"]) for row in pairs).items())), "agreement_counts": dict(sorted(Counter(str(row["agreement"]) for row in group_rows).items())), "completeness_counts": dict(sorted(Counter(str(row["completeness"]) for row in group_rows).items())), "automatic_candidate_groups": sum(row["automatic_candidate"] is True for row in group_rows), "review_candidate_groups": sum(row["review_candidate"] is True for row in group_rows), "oracle_access": 0, "holdout_access": 0, "semantic_api_calls": 0, "precision_metrics": 0, "coverage_metrics": 0, "closure": 0}
    write_once(ROOT / cfg["outputs"]["audit"], audit)
    report = "# P1V4 calibration look120 response freeze and offline re-score\n\nAll 2,160 logical Mini-medium responses are frozen, including a separately preserved and resolved two-record transport incident. Production and reference validators replay every pair; six votes are then aggregated deterministically. No Oracle, precision/coverage scoring, threshold selection, closure, or API call occurs here.\n"
    path = ROOT / cfg["outputs"]["report"]; path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") != report:
        raise RuntimeError("report drift")
    if not path.exists():
        path.write_text(report, encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if audit["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
