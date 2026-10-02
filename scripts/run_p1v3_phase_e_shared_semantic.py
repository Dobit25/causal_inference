"""Phase E provider preflight and fail-closed shared semantic execution gate.

The provider preflight is allowed by the Phase E authorization. Study execution
requires a separately hash-pinned semantic-input manifest; this runner refuses
to manufacture stories from hidden SCM/Oracle state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from openai import OpenAI
import yaml

from fourgraph.semantic_pair_contract_v2 import StablePair
from fourgraph.semantic_pair_contract_v3 import render_cause_effect_prompt

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "data/manifests/p1v3_phase_e_shared_semantic_authorization_audit.json"
SCHEMA = ROOT / "schemas/semantic_whole_graph_response_v3.schema.json"
PROMPT = ROOT / "prompts/p1_semantic_empirical_reliability_v3.md"
PREFLIGHT = ROOT / "data/manifests/p1v3_phase_e_provider_preflight.json"
EXEC_AUDIT = ROOT / "data/manifests/p1v3_phase_e_shared_semantic_execution_audit.json"
RAW_ROOT = ROOT / "results/raw/p1v3_phase_e_shared_semantic"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def worst_case_prompt() -> str:
    aliases = ["Amber index", "Beryl index", "Cobalt index", "Dahlia index", "Ember index", "Fallow index", "Grove index"]
    pairs = []
    for i, left in enumerate(aliases):
        for j in range(i + 1, len(aliases)):
            pairs.append(StablePair(f"pair_{len(pairs)+1:02d}", left, aliases[j], f"X{i:03d}", f"X{j:03d}"))
    story = "This synthetic process contains the following measured quantities: " + ", ".join(aliases) + ". "
    story += "The statements below describe direct relationships. "
    story += " ".join(f"Within this process, changes in {a} directly influence {b}." for a, b in zip(aliases, aliases[1:]))
    return render_cause_effect_prompt(prompt_id="P1", story=story, pairs=pairs)


def provider_preflight() -> dict:
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    if checkpoint.get("status") != "PASS_CHECKPOINT_NO_LIVE_EXECUTION":
        raise RuntimeError("Phase E checkpoint is not PASS")
    # Keep the frozen execution environment minimal: parse only the key/value
    # needed here instead of adding a runtime dependency to the pinned env.
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENAI_API_KEY=") and not os.environ.get("OPENAI_API_KEY"):
                os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    prompt = worst_case_prompt()
    client = OpenAI(api_key=key)
    started = time.perf_counter()
    try:
        response = client.responses.create(
            model="gpt-5.4-nano-2026-03-17",
            input=prompt,
            reasoning={"effort": "medium"},
            max_output_tokens=8192,
            service_tier="default",
            store=False,
            text={"format": {"type": "json_schema", "name": "semantic_whole_graph_response_v3", "schema": schema, "strict": True}},
            metadata={"task": "P1_V3_PHASE_E_PROVIDER_PREFLIGHT", "study_execution": "false"},
        )
        usage = response.usage
        record = {
            "schema_version": "fourgraph.p1v3_phase_e_provider_preflight.v1",
            "status": "PASS" if response.status == "completed" and response.output_text else "FAIL",
            "study_semantic_calls": 0,
            "model": response.model,
            "request_id": getattr(response, "_request_id", None),
            "input_tokens": int(usage.input_tokens),
            "output_tokens": int(usage.output_tokens),
            "total_tokens": int(getattr(usage, "total_tokens", usage.input_tokens + usage.output_tokens)),
            "reasoning_tokens": int(getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0),
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "context_limit_check": "provider_completed_without_truncation",
            "worst_case_nodes": 7,
            "worst_case_pairs": 21,
            "truncation": "disabled",
            "prompt_sha256": sha(PROMPT),
            "schema_sha256": sha(SCHEMA),
        }
    except Exception as exc:
        record = {
            "schema_version": "fourgraph.p1v3_phase_e_provider_preflight.v1",
            "status": "FAIL",
            "study_semantic_calls": 0,
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:1000],
            "worst_case_nodes": 7,
            "worst_case_pairs": 21,
            "truncation": "disabled",
            "prompt_sha256": sha(PROMPT),
            "schema_sha256": sha(SCHEMA),
        }
    PREFLIGHT.write_bytes(canonical(record))
    return record


def execute_guard() -> dict:
    """Refuse execution unless a frozen semantic-input manifest exists."""
    candidates = [
        ROOT / "data/manifests/p1v3_phase_e_shared_semantic_inputs.jsonl",
        ROOT / "data/manifests/p1_v3_successor_method_development_semantic.jsonl",
    ]
    present = [str(path.relative_to(ROOT)) for path in candidates if path.is_file()]
    audit = {
        "schema_version": "fourgraph.p1v3_phase_e_shared_semantic_execution_audit.v1",
        "status": "STOPPED_MISSING_HASH_PINNED_SEMANTIC_INPUTS",
        "planned_semantic_calls": 0,
        "actual_semantic_calls": 0,
        "provider_attempts": 0,
        "semantic_input_manifests_present": present,
        "oracle_accessed": False,
        "holdout_accessed": False,
        "downstream_reasoner_calls": 0,
        "reason": "Phase D stored observations and statistical graphs, but no hash-pinned public story/input manifest was frozen for Phase E. Runner will not derive stories from Oracle/SCM state.",
    }
    EXEC_AUDIT.write_bytes(canonical(audit))
    return audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-preflight", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.provider_preflight and not args.execute:
        raise SystemExit("choose --provider-preflight or --execute")
    if args.provider_preflight:
        result = provider_preflight()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["status"] != "PASS":
            return 1
    if args.execute:
        result = execute_guard()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
