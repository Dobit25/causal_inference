"""Freeze 2,640 effective validation responses and replay pair/six-vote validators offline."""
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
from fourgraph.semantic_sentence_id_contract import aggregate_six_votes, validate_response_by_pair  # noqa: E402
from fourgraph.semantic_sentence_id_contract_reference import reference_aggregate, reference_validate  # noqa: E402
from scripts.run_p1_v4_independent_calibration_look120_mini_semantic import build_jobs  # noqa: E402

CFG = ROOT / "configs/p1_v4_validation_look160_response_freeze_rescore.yaml"


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def pct(n: int, d: int) -> float:
    return round(n / d, 8) if d else 0.0


def build() -> tuple[dict[Path, bytes], dict]:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    for name, item in cfg["parents"].items():
        path = ROOT / item["path"]
        if not path.is_file() or sha(path) != item["sha256"]:
            raise RuntimeError(f"parent hash drift: {name}")
    for item in cfg["overlays"]:
        path = ROOT / item["path"]
        ledger = ROOT / item["token_ledger"]
        if sha(path) != item["sha256"] or sha(ledger) != item["token_ledger_sha256"]:
            raise RuntimeError(f"overlay or retry-ledger hash drift: {item['name']}")

    scope = cfg["scope"]
    raw_path = ROOT / cfg["parents"]["raw_responses"]["path"]
    metadata_path = ROOT / cfg["parents"]["request_metadata"]["path"]
    raw = rows(raw_path)
    metadata = rows(metadata_path)
    raw_by = {row["logical_id"]: row for row in raw}
    meta_by = {row["logical_id"]: row for row in metadata}
    n = scope["expected_logical_calls"]
    if len(raw) != len(raw_by) != n:
        raise RuntimeError("raw response cardinality/uniqueness drift")
    if len(raw) != n or len(raw_by) != n or len(metadata) != n or len(meta_by) != n:
        raise RuntimeError("raw/metadata cardinality drift")
    provider_error_ids = {lid for lid, row in raw_by.items() if row.get("status") == "provider_error"}
    if len(provider_error_ids) != scope["expected_raw_provider_errors"]:
        raise RuntimeError("raw provider-error count drift")

    overlay_by: dict[str, dict] = {}
    overlay_source: dict[str, str] = {}
    for item in cfg["overlays"]:
        for row in rows(ROOT / item["path"]):
            lid = row.get("logical_id")
            if lid in overlay_by:
                raise RuntimeError(f"duplicate overlay logical ID: {lid}")
            if lid not in provider_error_ids:
                raise RuntimeError(f"overlay does not replace raw provider error: {lid}")
            if row.get("status") == "provider_error" or not row.get("raw_text") or not row.get("response_sha256"):
                raise RuntimeError(f"unresolved/malformed overlay: {lid}")
            overlay_by[lid] = row
            overlay_source[lid] = item["name"]
    if set(overlay_by) != provider_error_ids or len(overlay_by) != scope["expected_overlay_replacements"]:
        raise RuntimeError("retry overlay coverage mismatch")

    effective: list[dict] = []
    effective_by: dict[str, dict] = {}
    for raw_row in raw:
        lid = raw_row["logical_id"]
        selected = overlay_by.get(lid, raw_row)
        source = overlay_source.get(lid, "primary_raw")
        record = {**selected, "effective_source": source, "replaces_raw_provider_error": lid in overlay_by}
        effective.append(record)
        effective_by[lid] = record
    if len(effective) != len(effective_by) != n:
        raise RuntimeError("effective response uniqueness drift")
    if len(effective) != n or len(effective_by) != n or any(row.get("status") == "provider_error" for row in effective):
        raise RuntimeError("effective response set is incomplete")
    if any(not row.get("request_id") or not row.get("response_sha256") for row in effective):
        raise RuntimeError("effective provider response lacks request/response identity")
    if any(row.get("model") != cfg["semantic_contract"]["model"] or row.get("reasoning_effort") != "medium" for row in effective):
        raise RuntimeError("model or reasoning-effort drift")

    job_cfg = {
        "parents": {"execution_plan": cfg["parents"]["execution_plan"]},
        "scope": {"logical_calls": n},
        "semantic_contract": cfg["semantic_contract"],
    }
    jobs = build_jobs(job_cfg)
    job_ids = {job["logical_id"] for job in jobs}
    if job_ids != set(effective_by) or set(meta_by) != job_ids:
        raise RuntimeError("logical identity mismatch among plan/raw/metadata")

    pair_records: list[dict] = []
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    disagreements = 0
    response_hash_mismatches = 0
    for job in jobs:
        response_record = effective_by[job["logical_id"]]
        for key in ("story_content_sha256", "pair_pool_sha256", "prompt_render_sha256"):
            if response_record.get(key) != job.get(key):
                raise RuntimeError(f"input identity drift: {job['logical_id']} / {key}")
        raw_text = str(response_record.get("raw_text", ""))
        if hashlib.sha256(raw_text.encode()).hexdigest().upper() != response_record.get("response_sha256"):
            response_hash_mismatches += 1
        try:
            response = json.loads(raw_text)
        except json.JSONDecodeError:
            response = object()
        production = validate_response_by_pair(response, job["pairs"], job["story"])
        judgments = {
            row.get("pair_id"): row for row in response.get("judgments", []) if isinstance(row, dict)
        } if isinstance(response, dict) and isinstance(response.get("judgments"), list) else {}
        for pair, prod in zip(job["pairs"], production["pairs"]):
            ref = reference_validate(
                judgments.get(pair.pair_id),
                {"pair_id": pair.pair_id, "A": pair.node_a_alias, "B": pair.node_b_alias},
                job["story"],
            )
            if any(prod.get(key) != ref.get(key) for key in ("pair_valid", "validator_status", "direction")):
                disagreements += 1
            output = {
                "schema_version": "fourgraph.p1_v4_validation_look160_pair_rescore.v1",
                "logical_id": job["logical_id"],
                "scene_id": job["study_id"],
                "variant": job["variant"],
                "prompt_id": job["prompt_id"],
                "pair_id": pair.pair_id,
                "node_a_alias": pair.node_a_alias,
                "node_b_alias": pair.node_b_alias,
                "node_a_canonical": pair.node_a_id,
                "node_b_canonical": pair.node_b_id,
                "model_status": prod.get("model_status"),
                "validator_status": prod.get("validator_status"),
                "pair_valid": prod.get("pair_valid"),
                "direction": prod.get("direction"),
                "evidence_sentence_ids": prod.get("evidence_sentence_ids"),
                "response_sha256": response_record.get("response_sha256"),
                "raw_status": response_record.get("status"),
                "effective_source": response_record["effective_source"],
            }
            pair_records.append(output)
            grouped[(job["study_id"], job["variant"], pair.pair_id)].append(output)

    groups: list[dict] = []
    expected_prompts = scope["prompts"]
    for (scene, variant, pair_id), votes in sorted(grouped.items()):
        votes = sorted(votes, key=lambda row: row["prompt_id"])
        if [row["prompt_id"] for row in votes] != expected_prompts:
            raise RuntimeError(f"missing/repeated prompt vote: {scene}/{variant}/{pair_id}")
        prod = aggregate_six_votes(votes, balanced=True)
        ref = reference_aggregate(votes, balanced=True)
        keys = ("valid_votes", "completeness", "agreement", "automatic_candidate", "review_candidate", "candidate_direction")
        if any(prod.get(key) != ref.get(key) for key in keys):
            disagreements += 1
        first = votes[0]
        groups.append({
            "schema_version": "fourgraph.p1_v4_validation_look160_six_vote_group.v1",
            "scene_id": scene,
            "variant": variant,
            "pair_id": pair_id,
            "node_a_alias": first["node_a_alias"],
            "node_b_alias": first["node_b_alias"],
            "node_a_canonical": first["node_a_canonical"],
            "node_b_canonical": first["node_b_canonical"],
            "prompt_ids": [row["prompt_id"] for row in votes],
            "valid_votes": prod["valid_votes"],
            "invalid_votes": prod["invalid_votes"],
            "completeness": prod["completeness"],
            "agreement": prod["agreement"],
            "vote_counts": prod["vote_counts"],
            "automatic_candidate": prod["automatic_candidate"],
            "review_candidate": prod["review_candidate"],
            "candidate_direction": prod["candidate_direction"],
            "automatically_published": False,
        })

    if len(pair_records) != scope["expected_pair_records"] or len(groups) != scope["expected_six_vote_groups"]:
        raise RuntimeError(f"pair/group count drift: {len(pair_records)}/{len(groups)}")
    if len({row["scene_id"] for row in groups}) != scope["expected_scenes"]:
        raise RuntimeError("scene coverage drift")
    if {row["variant"] for row in groups} != set(scope["variants"]):
        raise RuntimeError("variant drift")
    if response_hash_mismatches or disagreements:
        raise RuntimeError(f"replay mismatch: response_hash={response_hash_mismatches}, validators={disagreements}")

    validity_by_variant = {}
    coverage_by_variant = {}
    for variant in scope["variants"]:
        pv = [row for row in pair_records if row["variant"] == variant]
        gv = [row for row in groups if row["variant"] == variant]
        valid = sum(row["pair_valid"] is True for row in pv)
        automatic = sum(row["automatic_candidate"] is True for row in gv)
        review = sum(row["review_candidate"] is True for row in gv)
        validity_by_variant[variant] = {"valid": valid, "total": len(pv), "rate": pct(valid, len(pv))}
        coverage_by_variant[variant] = {
            "automatic_candidates": automatic,
            "review_candidates": review,
            "total_groups": len(gv),
            "automatic_candidate_rate": pct(automatic, len(gv)),
            "abstention_rate_before_parent_filtering": pct(len(gv) - automatic, len(gv)),
        }

    effective_body = b"".join(canonical(row) for row in effective)
    pair_body = b"".join(canonical(row) for row in pair_records)
    group_body = b"".join(canonical(row) for row in groups)
    output = cfg["outputs"]
    freeze = {
        "schema_version": "fourgraph.p1_v4_validation_look160_response_freeze.v1",
        "status": "PASS_FROZEN",
        "config_sha256": sha(CFG),
        "raw_response_sha256": sha(raw_path),
        "effective_response_sha256": hashlib.sha256(effective_body).hexdigest().upper(),
        "request_metadata_sha256": sha(metadata_path),
        "overlay_hashes": {item["name"]: item["sha256"] for item in cfg["overlays"]},
        "effective_logical_responses": n,
        "raw_provider_errors": len(provider_error_ids),
        "overlay_replacements": len(overlay_by),
        "unresolved_provider_errors": 0,
        "frozen_before": ["oracle_scoring", "precision_metrics", "coverage_metrics", "closure", "threshold_reselection"],
        "oracle_access": 0,
        "holdout_access": 0,
        "semantic_api_calls": 0,
    }
    freeze_body = canonical(freeze)
    artifacts = {
        ROOT / output["effective_responses"]: effective_body,
        ROOT / output["response_freeze"]: freeze_body,
        ROOT / output["pair_records"]: pair_body,
        ROOT / output["six_vote_groups"]: group_body,
    }
    agreement_counts = Counter(str(row["agreement"]) for row in groups)
    completeness_counts = Counter(str(row["completeness"]) for row in groups)
    audit = {
        "schema_version": "fourgraph.p1_v4_validation_look160_response_freeze_rescore_audit.v1",
        "status": "PASS",
        "effective_logical_responses": n,
        "raw_provider_errors": len(provider_error_ids),
        "overlay_replacements": len(overlay_by),
        "unresolved_provider_errors": 0,
        "effective_status_counts": dict(sorted(Counter(str(row["status"]) for row in effective).items())),
        "pair_records": len(pair_records),
        "six_vote_groups": len(groups),
        "production_reference_disagreements": disagreements,
        "response_hash_mismatches": response_hash_mismatches,
        "valid_pair_records": sum(row["pair_valid"] is True for row in pair_records),
        "invalid_pair_records": sum(row["pair_valid"] is False for row in pair_records),
        "pair_validity_by_variant": validity_by_variant,
        "validator_status_counts": dict(sorted(Counter(str(row["validator_status"]) for row in pair_records).items())),
        "agreement_counts": dict(sorted(agreement_counts.items())),
        "completeness_counts": dict(sorted(completeness_counts.items())),
        "automatic_candidate_groups": sum(row["automatic_candidate"] is True for row in groups),
        "review_candidate_groups": sum(row["review_candidate"] is True for row in groups),
        "preliminary_coverage_by_variant": coverage_by_variant,
        "effective_responses_sha256": hashlib.sha256(effective_body).hexdigest().upper(),
        "response_freeze_sha256": hashlib.sha256(freeze_body).hexdigest().upper(),
        "pair_records_sha256": hashlib.sha256(pair_body).hexdigest().upper(),
        "six_vote_groups_sha256": hashlib.sha256(group_body).hexdigest().upper(),
        "oracle_access": 0,
        "holdout_access": 0,
        "semantic_api_calls": 0,
        "precision_metrics": 0,
        "oracle_coverage_metrics": 0,
        "closure": 0,
    }
    artifacts[ROOT / output["audit"]] = canonical(audit)
    report_lines = [
        "# P1V4 independent validation look-160 response freeze and re-score",
        "",
        "Status: **PASS**.",
        "",
        f"- Effective responses: **{n:,}**",
        f"- Provider errors replaced by immutable overlays: **{len(overlay_by)}/{len(provider_error_ids)}**",
        f"- Pair records: **{len(pair_records):,}**",
        f"- Six-vote groups: **{len(groups):,}**",
        f"- Valid pair records: **{audit['valid_pair_records']:,}/{len(pair_records):,}**",
        f"- Agreement: `{dict(sorted(agreement_counts.items()))}`",
        f"- Completeness: `{dict(sorted(completeness_counts.items()))}`",
        f"- Preliminary automatic-candidate rates: `{coverage_by_variant}`",
        "- Production/reference validator agreement: **100%**",
        "- Byte-for-byte replay: verified separately with `--check`",
        "- API/Oracle/holdout/precision/closure: **not run**",
        "",
        "Preliminary coverage is the fraction of shared semantic pair groups marked automatic before condition-specific parent filtering; it is not Oracle-scored coverage.",
        "",
    ]
    artifacts[ROOT / output["report"]] = "\n".join(report_lines).encode()
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
