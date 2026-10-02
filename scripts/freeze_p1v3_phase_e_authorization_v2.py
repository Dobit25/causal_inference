from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canon(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs/p1v3_phase_e_shared_semantic_authorization_v2.yaml")
    args = ap.parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    phase_d = ROOT / cfg["phase_d_audit"]
    stat = ROOT / cfg["statistical_manifest"]
    public = ROOT / cfg["public_semantic_manifest"]
    story_cfg = ROOT / cfg["story_generation_config"]
    t19 = ROOT / cfg["t19_story_config"]
    generator = ROOT / cfg["story_generator"]
    preflight = ROOT / cfg["provider_preflight"]
    pub = json.loads(public.read_text(encoding="utf-8"))
    phase = json.loads(phase_d.read_text(encoding="utf-8"))
    pf = json.loads(preflight.read_text(encoding="utf-8"))
    ids = {f"P1V3SD{i:03d}" for i in range(30)}
    records = pub.get("records", [])
    record_ids = {row.get("study_id") for row in records}
    variants = [row.get("variant") for row in records]
    checks = {
        "phase_d_pass": phase.get("status") == "PASS_EXECUTION_AUDIT" and phase.get("complete_fit_pairs") == 6150,
        "exact_30_scenes": record_ids == ids and len(record_ids) == 30,
        "exact_60_inputs": len(records) == 60 and variants.count("full") == 30 and variants.count("partial") == 30,
        "ambiguous_zero": "ambiguous" not in variants,
        "public_manifest_hash": sha(public) == "352C437599A25B7875464E68922857096942F2993EA58B973391C9C81DD17A34",
        "story_config_hash": sha(story_cfg) == "565A1AEB304106C58A73D9E0CCFDA6A1FEF6EC922225710AAA258B9BA4DAAD16",
        "t19_hash": sha(t19) == "D718E142974BABE425FAB19CBD273DC8484A8845A99E9ADEAD651F86733009E7",
        "generator_hash": sha(generator) == "73915B96BBD7E690FB95E6C7D8CDAB7B88C815655255FEC54E31597BED6A1F81",
        "provider_preflight_pass": pf.get("status") == "PASS" and pf.get("study_semantic_calls") == 0,
        "leakage_pass": all(all(not bool(v) for v in row.get("leakage_check", {}).values()) for row in records),
        "api_before_authorization_zero": pf.get("study_semantic_calls") == 0,
        "oracle_holdout_zero": phase.get("execution_boundary", {}).get("oracle_accessed") is False and phase.get("execution_boundary", {}).get("holdout_accessed") is False,
        "prompt_schema_model_frozen": cfg["semantic"]["model_snapshot"] == "gpt-5.4-nano-2026-03-17" and (ROOT / cfg["semantic"]["prompt"]).is_file() and (ROOT / cfg["semantic"]["schema"]).is_file(),
        "truncation_chunking_frozen": cfg["semantic"]["truncation"] == "disabled" and cfg["semantic"]["automatic_prompt_chunking"] == "forbidden",
    }
    hashes = {key: sha(ROOT / rel) for key, rel in {
        "phase_d_final_audit": cfg["phase_d_audit"],
        "statistical_manifest": cfg["statistical_manifest"],
        "public_semantic_manifest": cfg["public_semantic_manifest"],
        "story_generation_config": cfg["story_generation_config"],
        "t19_config": cfg["t19_story_config"],
        "story_generator": cfg["story_generator"],
        "prompt": cfg["semantic"]["prompt"],
        "schema": cfg["semantic"]["schema"],
        "provider_preflight": cfg["provider_preflight"],
    }.items()}
    passed = all(checks.values())
    result = {
        "schema_version": "fourgraph.p1v3_phase_e_shared_semantic_authorization_v2_audit.v1",
        "task": cfg["task"],
        "status": "PASS_CHECKPOINT_READY_FOR_SEPARATE_LIVE_AUTHORIZATION" if passed else "FAIL_CHECKPOINT",
        "checks": checks,
        "hashes": hashes,
        "inputs": {"scenes": 30, "records": 60, "full": 30, "partial": 30, "ambiguous": 0},
        "shared_pool": cfg["semantic"]["source_conditions"],
        "execution_boundary": {"semantic_api_calls_before_authorization": 0, "oracle_accessed": False, "holdout_accessed": False, "downstream_reasoner_calls": 0},
        "phase_e_live_authorized": False,
    }
    out = ROOT / "data/manifests/p1v3_phase_e_shared_semantic_authorization_v2_audit.json"
    out.write_bytes(canon(result))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
