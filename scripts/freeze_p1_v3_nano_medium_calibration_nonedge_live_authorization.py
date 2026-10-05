"""Freeze successor live authorization after the public-story non-edge amendment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "configs/p1_v3_nano_medium_calibration_nonedge_live_authorization.yaml"
AUDIT = ROOT / "data/manifests/p1_v3_nano_medium_calibration_nonedge_live_authorization_audit.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    paths = {
        "configs/p1_v3_nano_medium_calibration_look120_production_runner.yaml": ROOT / "configs/p1_v3_nano_medium_calibration_look120_production_runner.yaml",
        "configs/p1_v3_nano_medium_calibration_provider_environment_lock.yaml": ROOT / "configs/p1_v3_nano_medium_calibration_provider_environment_lock.yaml",
        "data/manifests/p1_v3_nano_medium_calibration_look120_provider_preflight.json": ROOT / "data/manifests/p1_v3_nano_medium_calibration_look120_provider_preflight.json",
        "data/manifests/p1_v3_nano_medium_calibration_look120_statistical_execution_audit.json": ROOT / "data/manifests/p1_v3_nano_medium_calibration_look120_statistical_execution_audit.json",
        "data/manifests/p1_v3_nano_medium_calibration_public_story_manifest.jsonl": ROOT / "data/manifests/p1_v3_nano_medium_calibration_public_story_manifest.jsonl",
        "data/manifests/p1_v3_nano_medium_calibration_public_story_generation_audit.json": ROOT / "data/manifests/p1_v3_nano_medium_calibration_public_story_generation_audit.json",
        "data/manifests/p1_v3_successor_sequential_exact_identity_plan.json": ROOT / "data/manifests/p1_v3_successor_sequential_exact_identity_plan.json",
        "configs/p1_v3_nano_medium_calibration_look120_nonedge_amendment.yaml": ROOT / "configs/p1_v3_nano_medium_calibration_look120_nonedge_amendment.yaml",
        "data/manifests/p1_v3_nano_medium_calibration_nonedge_pair_manifest.json": ROOT / "data/manifests/p1_v3_nano_medium_calibration_nonedge_pair_manifest.json",
        "data/manifests/p1_v3_nano_medium_calibration_nonedge_amendment_audit.json": ROOT / "data/manifests/p1_v3_nano_medium_calibration_nonedge_amendment_audit.json",
        "prompts/p1_semantic_sentence_ids_v1.md": ROOT / "prompts/p1_semantic_sentence_ids_v1.md",
        "schemas/semantic_sentence_id_response_v1.schema.json": ROOT / "schemas/semantic_sentence_id_response_v1.schema.json",
    }
    for path in paths.values():
        if not path.is_file():
            raise RuntimeError(f"missing authorization dependency: {path}")
    stat = json.loads(paths["data/manifests/p1_v3_nano_medium_calibration_look120_statistical_execution_audit.json"].read_text(encoding="utf-8"))
    provider = json.loads(paths["data/manifests/p1_v3_nano_medium_calibration_look120_provider_preflight.json"].read_text(encoding="utf-8"))
    amendment = json.loads(paths["data/manifests/p1_v3_nano_medium_calibration_nonedge_amendment_audit.json"].read_text(encoding="utf-8"))
    pair_manifest = json.loads(paths["data/manifests/p1_v3_nano_medium_calibration_nonedge_pair_manifest.json"].read_text(encoding="utf-8"))
    plan = json.loads(paths["data/manifests/p1_v3_successor_sequential_exact_identity_plan.json"].read_text(encoding="utf-8"))
    if stat.get("status") != "PASS_STATISTICAL_PARENT_COMPLETE" or stat.get("raw_records") != 24120 or stat.get("normalized_records") != 24120:
        raise RuntimeError("statistical parent is not complete")
    if provider.get("status") != "PASS" or provider.get("study_execution") or provider.get("study_scenes_loaded") != 0:
        raise RuntimeError("provider preflight is not a clean non-study PASS")
    if amendment.get("status") != "PASS_PUBLIC_STORY_NONEDGE_PAIR_FREEZE" or amendment.get("replay") != "PASS_BYTE_FOR_BYTE":
        raise RuntimeError("non-edge amendment is not PASS/replayed")
    if pair_manifest.get("scene_count") != 80 or pair_manifest.get("pair_count") != 240:
        raise RuntimeError("non-edge pair manifest cardinality drift")
    ids = plan["diagnostic_subsets"]["nonedge_semantic_calibration"]
    if len(ids) != 80 or len(set(ids)) != 80 or amendment.get("exact_scene_ids") != ids:
        raise RuntimeError("registered non-edge IDs drift")
    hashes = {name: sha(path) for name, path in paths.items()}
    body = """schema_version: fourgraph.p1_v3_nano_medium_calibration_nonedge_live_authorization.v1
task: P1_V3_NANO_MEDIUM_CALIBRATION_LOOK120_NONEDGE_AMENDED_LIVE_AUTHORIZATION
status: LIVE_AUTHORIZED_BY_USER
explicit_user_live_authorization: true
scope: semantic_calibration_look_120_only
model: gpt-5.4-nano-2026-03-17
reasoning_effort: medium
max_output_tokens: 8192
provider_endpoint: /v1/responses
structured_outputs: true
store: false
truncation: disabled
prompt: prompts/p1_semantic_sentence_ids_v1.md
response_schema: schemas/semantic_sentence_id_response_v1.schema.json
prompt_variants: [P1, P2, P3, P4, P5, P6]
certification_story_variants: [full, partial]
diagnostic_story_variants: [ambiguous, public_story_nonedge_on_full_story]
exact_scene_count: 120
planned_semantic_calls: 2640
planned_certification_calls: 1440
planned_ambiguous_diagnostic_calls: 720
planned_nonedge_diagnostic_calls: 480
nonedge_pair_manifest:
  path: data/manifests/p1_v3_nano_medium_calibration_nonedge_pair_manifest.json
  scene_count: 80
  pairs_per_scene: 3
  selection: public_story_unlisted_pairs_only
transport_retry_max: 1
semantic_validation_retry: false
concurrency: 1
token_hard_stop: 3000000
token_reset_local_time: '07:00:00'
token_reset_timezone: Asia/Ho_Chi_Minh
provider_usage_authoritative: true
missing_usage_action: fail_closed_and_halt
overshoot_action: fail_closed_and_halt
automatic_next_look: false
automatic_validation_or_holdout: false
oracle_access: false
validation_access: false
holdout_access: false
downstream_reasoner: false
semantic_api_calls_before_authorization: 0
"""
    body += "hashes:\n" + "\n".join(f"  {name}: {value}" for name, value in sorted(hashes.items())) + "\n"
    AUTH.write_text(body, encoding="utf-8", newline="\n")
    audit = {
        "schema_version": "fourgraph.p1_v3_nano_medium_calibration_nonedge_live_authorization_audit.v1",
        "status": "PASS_LIVE_AUTHORIZED",
        "explicit_user_live_authorization": True,
        "exact_scene_count": 120,
        "planned_semantic_calls": 2640,
        "planned_certification_calls": 1440,
        "planned_ambiguous_diagnostic_calls": 720,
        "planned_nonedge_diagnostic_calls": 480,
        "statistical_parent_records": 24120,
        "nonedge_pair_manifest_sha256": hashes["data/manifests/p1_v3_nano_medium_calibration_nonedge_pair_manifest.json"],
        "nonedge_amendment_config_sha256": hashes["configs/p1_v3_nano_medium_calibration_look120_nonedge_amendment.yaml"],
        "nonedge_amendment_audit_sha256": hashes["data/manifests/p1_v3_nano_medium_calibration_nonedge_amendment_audit.json"],
        "hashes": hashes,
        "checks": {
            "statistical_parent_pass": True,
            "provider_preflight_pass": True,
            "public_story_nonedge_amendment_pass": True,
            "exact_120_identity_plan": True,
            "workload_2640": True,
            "oracle_access": False,
            "holdout_access": False,
            "semantic_calls_before_authorization": 0,
        },
        "next_action": "execute_semantic_calibration_look120_then_stop_before_next_look",
    }
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.write_bytes((json.dumps(audit, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
