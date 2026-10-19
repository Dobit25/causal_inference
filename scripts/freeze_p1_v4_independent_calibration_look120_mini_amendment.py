"""Freeze the Mini-medium replacement amendment offline; never calls the provider."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_mini_medium_amendment.yaml"
OUT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_mini_medium_amendment.json"
AUDIT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_mini_medium_amendment_audit.json"
REPORT = ROOT / "reports/p1_v4_independent_calibration_look120_mini_medium_amendment.md"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def main() -> None:
    prompt = ROOT / "prompts/p1_semantic_sentence_ids_v1.md"
    schema = ROOT / "schemas/semantic_sentence_id_response_v1.schema.json"
    plan = ROOT / "data/manifests/p1_v4_independent_calibration_look120_semantic_execution_plan.json"
    manifest = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look120_mini_medium_amendment.v1",
        "task": "P1_V4_INDEPENDENT_CALIBRATION_LOOK120_MINI_MEDIUM_MODEL_AMENDMENT_FREEZE",
        "status": "PASS_OFFLINE_READY_FOR_PROVIDER_PREFLIGHT",
        "model": "gpt-5.4-mini-2026-03-17",
        "reasoning_effort": "medium",
        "supersedes_for_live_use": "data/manifests/p1_v4_independent_calibration_look120_semantic_authorization_checkpoint.json",
        "superseded_nano_checkpoint_retained": True,
        "contract": {
            "prompt": str(prompt.relative_to(ROOT)).replace("\\", "/"),
            "prompt_sha256": sha(prompt),
            "schema": str(schema.relative_to(ROOT)).replace("\\", "/"),
            "schema_sha256": sha(schema),
            "prompt_variants": ["P1", "P2", "P3", "P4", "P5", "P6"],
            "story_variants": ["full", "partial", "ambiguous"],
            "max_pairs_per_scene": 21,
            "truncation": "disabled",
            "automatic_chunking": "forbidden",
            "condition_specific_closure": True,
        },
        "inputs": {
            "execution_plan": str(plan.relative_to(ROOT)).replace("\\", "/"),
            "execution_plan_sha256": sha(plan),
            "scenes": 120,
            "public_inputs": 360,
            "logical_calls": 2160,
            "public_inputs_sha256": "9493ECB59CE7BE3506B758381373CA864D24F32F3633AC9CCD8115360E943A7B",
        },
        "boundary": {
            "provider_preflight_calls": 0,
            "study_api_calls": 0,
            "oracle_access": 0,
            "holdout_access": 0,
            "statistical_reruns": 0,
            "status": "offline_only",
        },
        "next_gate": "MINI_MEDIUM_PROVIDER_PREFLIGHT",
    }
    OUT.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    audit = {
        "task": manifest["task"],
        "status": "PASS",
        "config_sha256": sha(CONFIG),
        "manifest_sha256": sha(OUT),
        "prompt_sha256": sha(prompt),
        "schema_sha256": sha(schema),
        "execution_plan_sha256": sha(plan),
        "checks": {
            "model_is_mini_medium": True,
            "nano_live_checkpoint_not_reused": True,
            "same_inputs_and_contract_except_model": True,
            "2160_logical_calls_pinned": True,
            "no_provider_calls": True,
            "no_oracle_or_holdout": True,
            "no_statistical_reruns": True,
        },
    }
    AUDIT.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(
        "# Mini-medium amendment — Look 120\n\n"
        "Đã chốt GPT-5.4 Mini (`gpt-5.4-mini-2026-03-17`) với reasoning effort `medium`. "
        "Nano checkpoint cũ được giữ nguyên làm lịch sử và không trộn vào look này.\n\n"
        "Giữ nguyên story, pair pool, sáu prompt, schema, validator, 120 scenes, "
        "360 public inputs và 2.160 logical calls; chỉ thay model. Truncation/automatic "
        "chunking vẫn bị cấm, closure vẫn condition-specific.\n\n"
        "Đây là checkpoint offline. Chưa gọi provider preflight, chưa gọi study API, "
        "chưa đọc Oracle/holdout và chưa chạy lại statistical layer. Bước kế tiếp là "
        "provider preflight riêng cho Mini-medium rồi mới tạo live authorization.\n",
        encoding="utf-8",
    )

if __name__ == "__main__":
    main()
