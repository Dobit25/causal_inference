"""Hash-freeze 960 raw Mini responses and replay pair/six-vote validators offline."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from fourgraph.semantic_sentence_id_contract import aggregate_six_votes, validate_response_by_pair
from fourgraph.semantic_sentence_id_contract_reference import reference_aggregate, reference_validate
from scripts.run_p1_v4_independent_calibration_look120_mini_semantic import build_jobs

CFG = ROOT / "configs/p1_v4_partial_high_supplemental80_response_freeze_rescore.yaml"


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build() -> tuple[dict[Path, bytes], dict]:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    for name, item in cfg["parents"].items():
        path = ROOT / item["path"]
        if not path.is_file() or sha(path) != item["sha256"]:
            raise RuntimeError(f"parent hash drift: {name}")

    scope = cfg["scope"]
    execution = json.loads((ROOT / cfg["parents"]["execution_audit"]["path"]).read_text(encoding="utf-8"))
    raw = rows(ROOT / cfg["parents"]["raw_responses"]["path"])
    metadata = rows(ROOT / cfg["parents"]["request_metadata"]["path"])
    ledger = rows(ROOT / cfg["parents"]["token_ledger"]["path"])
    n = scope["expected_logical_calls"]
    if execution.get("status") != "PASS" or execution.get("recorded_logical_calls") != n:
        raise RuntimeError("Mini execution has not passed")
    if len(raw) != n or len(metadata) != n or len(ledger) != n + 1:
        raise RuntimeError("raw/metadata/ledger cardinality drift")
    raw_by = {row["logical_id"]: row for row in raw}
    meta_by = {row["logical_id"]: row for row in metadata}
    if len(raw_by) != n or len(meta_by) != n or ledger[0].get("logical_id") != "PROVIDER_PREFLIGHT":
        raise RuntimeError("duplicate IDs or missing preflight ledger row")
    if len({row.get("logical_id") for row in ledger}) != n + 1:
        raise RuntimeError("duplicate token ledger ID")
    if any(row.get("status") == "provider_error" for row in raw):
        raise RuntimeError("unresolved provider error")
    if sum(row["total_tokens"] for row in ledger) != execution["token_window_used"]:
        raise RuntimeError("provider token ledger drift")
    if any(row.get("model") != cfg["semantic_contract"]["model"] or row.get("reasoning_effort") != "medium" for row in raw):
        raise RuntimeError("model or effort drift")
    if any(not row.get("request_id") for row in raw):
        raise RuntimeError("missing provider request ID")

    job_cfg = {"parents": {"execution_plan": cfg["parents"]["execution_plan"]},
               "scope": {"logical_calls": n}, "semantic_contract": cfg["semantic_contract"]}
    jobs = build_jobs(job_cfg)
    if set(raw_by) != {job["logical_id"] for job in jobs} or set(meta_by) != set(raw_by):
        raise RuntimeError("exact logical identity drift")
    pair_records: list[dict] = []
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    disagreements = 0
    raw_sha_mismatch = 0
    for job in jobs:
        record = raw_by[job["logical_id"]]
        if record["story_content_sha256"] != job["story_content_sha256"] or record["pair_pool_sha256"] != job["pair_pool_sha256"] or record["prompt_render_sha256"] != job["prompt_render_sha256"]:
            raise RuntimeError(f"input identity drift: {job['logical_id']}")
        if hashlib.sha256(str(record.get("raw_text", "")).encode()).hexdigest().upper() != record.get("response_sha256"):
            raw_sha_mismatch += 1
        try:
            response = json.loads(str(record.get("raw_text", "")))
        except json.JSONDecodeError:
            response = object()
        production = validate_response_by_pair(response, job["pairs"], job["story"])
        judgments = {
            row.get("pair_id"): row for row in response.get("judgments", []) if isinstance(row, dict)
        } if isinstance(response, dict) and isinstance(response.get("judgments"), list) else {}
        for pair, prod in zip(job["pairs"], production["pairs"]):
            ref = reference_validate(judgments.get(pair.pair_id),
                                     {"pair_id": pair.pair_id, "A": pair.node_a_alias, "B": pair.node_b_alias},
                                     job["story"])
            if any(prod.get(key) != ref.get(key) for key in ("pair_valid", "validator_status", "direction")):
                disagreements += 1
            output = {
                "schema_version": "fourgraph.p1_v4_partial_high_supplemental80_pair_rescore.v1",
                "logical_id": job["logical_id"], "scene_id": job["study_id"],
                "variant": job["variant"], "prompt_id": job["prompt_id"],
                "pair_id": pair.pair_id, "node_a_alias": pair.node_a_alias,
                "node_b_alias": pair.node_b_alias,
                "model_status": prod.get("model_status"),
                "validator_status": prod.get("validator_status"),
                "pair_valid": prod.get("pair_valid"), "direction": prod.get("direction"),
                "evidence_sentence_ids": prod.get("evidence_sentence_ids"),
                "response_sha256": record.get("response_sha256"),
                "raw_status": record.get("status"), "effective_source": "primary_raw",
            }
            pair_records.append(output)
            grouped[(job["study_id"], job["variant"], pair.pair_id)].append(output)

    groups: list[dict] = []
    expected_prompts = scope["prompts"]
    for (scene, variant, pair_id), votes in sorted(grouped.items()):
        votes = sorted(votes, key=lambda row: row["prompt_id"])
        if [row["prompt_id"] for row in votes] != expected_prompts:
            raise RuntimeError(f"missing or repeated six-vote prompt: {scene}/{variant}/{pair_id}")
        prod = aggregate_six_votes(votes, balanced=True)
        ref = reference_aggregate(votes, balanced=True)
        if any(prod.get(key) != ref.get(key) for key in ("valid_votes", "completeness", "agreement", "automatic_candidate", "review_candidate", "candidate_direction")):
            disagreements += 1
        groups.append({
            "schema_version": "fourgraph.p1_v4_partial_high_supplemental80_six_vote_group.v1",
            "scene_id": scene, "variant": variant, "pair_id": pair_id,
            "prompt_ids": [row["prompt_id"] for row in votes],
            "valid_votes": prod["valid_votes"], "invalid_votes": prod["invalid_votes"],
            "completeness": prod["completeness"], "agreement": prod["agreement"],
            "vote_counts": prod["vote_counts"],
            "automatic_candidate": prod["automatic_candidate"],
            "review_candidate": prod["review_candidate"],
            "candidate_direction": prod["candidate_direction"],
            "automatically_published": False,
        })

    if len(pair_records) != scope["expected_pair_records"] or len(groups) != scope["expected_six_vote_groups"]:
        raise RuntimeError(f"pair/group cardinality drift: {len(pair_records)}/{len(groups)}")
    if len({row["scene_id"] for row in groups}) != scope["expected_scenes"]:
        raise RuntimeError("scene coverage drift")
    if {row["variant"] for row in groups} != set(scope["variants"]):
        raise RuntimeError("story variant drift")
    if raw_sha_mismatch or disagreements:
        raise RuntimeError(f"replay mismatch: raw hashes={raw_sha_mismatch}, validators={disagreements}")

    freeze = {
        "schema_version": "fourgraph.p1_v4_partial_high_supplemental80_response_freeze.v1",
        "status": "PASS_FROZEN", "config_sha256": sha(CFG),
        "raw_response_sha256": sha(ROOT / cfg["parents"]["raw_responses"]["path"]),
        "request_metadata_sha256": sha(ROOT / cfg["parents"]["request_metadata"]["path"]),
        "token_ledger_sha256": sha(ROOT / cfg["parents"]["token_ledger"]["path"]),
        "effective_logical_responses": n, "provider_errors": 0,
        "frozen_before": ["oracle_scoring", "precision_metrics", "coverage_metrics", "closure", "threshold_selection"],
        "oracle_access": 0, "validation_access": 0, "holdout_access": 0, "semantic_api_calls": 0,
    }
    output = cfg["outputs"]
    artifacts = {
        ROOT / output["response_freeze"]: canonical(freeze),
        ROOT / output["pair_records"]: b"".join(canonical(row) for row in pair_records),
        ROOT / output["six_vote_groups"]: b"".join(canonical(row) for row in groups),
    }
    audit = {
        "schema_version": "fourgraph.p1_v4_partial_high_supplemental80_response_freeze_rescore_audit.v1",
        "status": "PASS", "effective_logical_responses": n,
        "pair_records": len(pair_records), "six_vote_groups": len(groups),
        "production_reference_disagreements": disagreements,
        "raw_response_hash_mismatches": raw_sha_mismatch,
        "valid_pair_records": sum(row["pair_valid"] is True for row in pair_records),
        "invalid_pair_records": sum(row["pair_valid"] is False for row in pair_records),
        "validator_status_counts": dict(sorted(Counter(str(row["validator_status"]) for row in pair_records).items())),
        "agreement_counts": dict(sorted(Counter(str(row["agreement"]) for row in groups).items())),
        "completeness_counts": dict(sorted(Counter(str(row["completeness"]) for row in groups).items())),
        "automatic_candidate_groups": sum(row["automatic_candidate"] is True for row in groups),
        "review_candidate_groups": sum(row["review_candidate"] is True for row in groups),
        "response_freeze_sha256": hashlib.sha256(artifacts[ROOT / output["response_freeze"]]).hexdigest().upper(),
        "pair_records_sha256": hashlib.sha256(artifacts[ROOT / output["pair_records"]]).hexdigest().upper(),
        "six_vote_groups_sha256": hashlib.sha256(artifacts[ROOT / output["six_vote_groups"]]).hexdigest().upper(),
        "oracle_access": 0, "validation_access": 0, "holdout_access": 0,
        "semantic_api_calls": 0, "precision_metrics": 0, "coverage_metrics": 0, "closure": 0,
    }
    artifacts[ROOT / output["audit"]] = canonical(audit)
    artifacts[ROOT / output["report"]] = (
        f"# P1V4 supplemental-80 response freeze and six-vote replay\n\n"
        f"Status: **PASS**. {n} frozen Mini responses produced {len(pair_records):,} pair records and "
        f"{len(groups):,} six-vote groups. Production/reference validators agreed on every pair and group. "
        "No API, Oracle, validation, holdout, precision/coverage metric, or closure was run.\n"
    ).encode()
    return artifacts, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="byte-for-byte replay only")
    args = parser.parse_args()
    artifacts, audit = build()
    for path, body in artifacts.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != body:
                raise RuntimeError(f"byte replay mismatch: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.read_bytes() != body:
                raise RuntimeError(f"existing artifact drift: {path}")
            if not path.exists():
                path.write_bytes(body)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
