"""Live semantic execution for the authorized Nano-medium look-120 cohort.

The runner consumes only frozen public stories and frozen statistical outputs.
It does not materialize scenes, call Oracle, score directions, or open a later
look.  Every provider request is protected by the append-only token ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from itertools import combinations
from pathlib import Path
from typing import Any

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fourgraph.nano_calibration_control import CalibrationBudgetError, CalibrationTokenLedger  # noqa: E402
from fourgraph.semantic_pair_contract_v2 import StablePair  # noqa: E402
from fourgraph.semantic_sentence_id_contract import render_sentence_id_prompt, validate_response_by_pair  # noqa: E402

AUTH = ROOT / "configs/p1_v3_nano_medium_calibration_look120_live_authorization_v2.yaml"
AUTH_AUDIT = ROOT / "data/manifests/p1_v3_nano_medium_calibration_look120_live_authorization_v2_audit.json"
SUCCESSOR_AUTH_AUDIT = ROOT / "data/manifests/p1_v3_nano_medium_calibration_nonedge_live_authorization_audit.json"
NONEDGE_AMENDMENT_AUDIT = ROOT / "data/manifests/p1_v3_nano_medium_calibration_nonedge_amendment_audit.json"
NONEDGE_PAIR_MANIFEST = ROOT / "data/manifests/p1_v3_nano_medium_calibration_nonedge_pair_manifest.json"
PRODUCTION = ROOT / "configs/p1_v3_nano_medium_calibration_look120_production_runner.yaml"
IDENTITIES = ROOT / "data/manifests/p1_v3_successor_sequential_exact_identities.jsonl"
PLAN = ROOT / "data/manifests/p1_v3_successor_sequential_exact_identity_plan.json"
STORY_ROOT = ROOT / "data/generated/p1_v3_nano_medium_calibration_look120_stories"
SCENE_ROOT = ROOT / "data/generated/p1_v3_nano_medium_calibration_look120"
STAT_PATH = ROOT / "results/raw/p1_v3_nano_medium_calibration_look120_statistical/normalized.jsonl"
SCHEMA = ROOT / "schemas/semantic_sentence_id_response_v1.schema.json"
RAW_PATH = ROOT / "results/raw/p1_v3_nano_medium_calibration_look120/semantic_calls.jsonl"
META_PATH = ROOT / "results/runtime/p1_v3_nano_medium_calibration_look120/request_metadata.jsonl"
LEDGER_PATH = ROOT / "results/runtime/p1_v3_nano_medium_calibration_look120/token_ledger.jsonl"
AUDIT_PATH = ROOT / "data/manifests/p1_v3_nano_medium_calibration_look120_semantic_execution_audit.json"


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def canon(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_auth() -> dict[str, Any]:
    # The previous authorization is intentionally insufficient after the
    # public-story non-edge amendment.  A successor authorization must pin the
    # exact pair manifest before any provider request is possible.
    if not SUCCESSOR_AUTH_AUDIT.exists():
        raise RuntimeError("successor live authorization required after non-edge amendment")
    successor = json.loads(SUCCESSOR_AUTH_AUDIT.read_text(encoding="utf-8"))
    if successor.get("status") != "PASS_LIVE_AUTHORIZED" or successor.get("explicit_user_live_authorization") is not True:
        raise RuntimeError("successor live authorization is not PASS")
    amendment = json.loads(NONEDGE_AMENDMENT_AUDIT.read_text(encoding="utf-8"))
    if amendment.get("status") != "PASS_PUBLIC_STORY_NONEDGE_PAIR_FREEZE":
        raise RuntimeError("public-story non-edge amendment is not PASS")
    if successor.get("nonedge_pair_manifest_sha256") != amendment.get("manifest_sha256"):
        raise RuntimeError("successor authorization does not pin non-edge pair manifest")
    audit = json.loads(AUTH_AUDIT.read_text(encoding="utf-8"))
    if audit.get("status") != "PASS_LIVE_AUTHORIZED" or audit.get("explicit_user_live_authorization") is not True:
        raise RuntimeError("live authorization is not PASS")
    if audit.get("exact_scene_count") != 120 or audit.get("planned_semantic_calls") != 2640:
        raise RuntimeError("live authorization workload drift")
    return audit


def identities() -> list[dict[str, Any]]:
    rows = load_jsonl(IDENTITIES)
    selected = [r for r in rows if r.get("role") == "semantic_calibration" and int(r.get("sequence_index", -1)) < 120]
    selected.sort(key=lambda r: int(r["sequence_index"]))
    if len(selected) != 120 or len({r["study_id"] for r in selected}) != 120:
        raise RuntimeError("exact 120-scene identity drift")
    return selected


def story(scene_id: str, variant: str) -> str:
    path = STORY_ROOT / scene_id / f"story_{variant}.json"
    if not path.is_file():
        raise RuntimeError(f"missing public story: {path}")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("study_id") != scene_id or obj.get("evidence_variant") != variant:
        raise RuntimeError("story provenance drift")
    text = obj.get("builder_input", {}).get("story")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("empty public story")
    return text


def aliases(text: str) -> list[str]:
    first = text.split(".", 1)[0]
    prefix = "This synthetic process contains the following measured quantities: "
    if not first.startswith(prefix):
        raise RuntimeError("public story alias header drift")
    values = [x.strip() for x in first[len(prefix):].split(",")]
    if not 5 <= len(values) <= 7 or len(set(values)) != len(values):
        raise RuntimeError("public story alias universe drift")
    return values


def pair_pool(text: str, scene_id: str, *, nonedge: bool = False) -> tuple[StablePair, ...]:
    names = aliases(text)
    nodes = [f"X{i:03d}" for i in range(len(names))]
    all_pairs = [(a, b) for a, b in combinations(range(len(nodes)), 2)]
    if nonedge:
        if not NONEDGE_PAIR_MANIFEST.is_file():
            raise RuntimeError("frozen public-story non-edge pair manifest missing")
        manifest = json.loads(NONEDGE_PAIR_MANIFEST.read_text(encoding="utf-8"))
        rows = [r for s in manifest["scenes"] if s["scene_id"] == scene_id for r in s["pairs"]]
        if len(rows) != 3:
            raise RuntimeError(f"frozen public-story non-edge pair count drift: {scene_id}")
        lookup = {(r["node_a_id"], r["node_b_id"]): r for r in rows}
        all_pairs = [(nodes.index(a), nodes.index(b)) for a, b in lookup]
        if any(lookup[(nodes[i], nodes[j])]["direct_pair_in_public_story"] for i, j in all_pairs):
            raise RuntimeError(f"public-story non-edge leakage: {scene_id}")
    return tuple(StablePair(f"pair_{i + 1:02d}", names[a], names[b], nodes[a], nodes[b]) for i, (a, b) in enumerate(all_pairs))


def build_jobs() -> list[dict[str, Any]]:
    rows = identities()
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    ambiguous_ids = list(plan["diagnostic_subsets"]["ambiguous_semantic_calibration"])
    nonedge_ids = list(plan["diagnostic_subsets"]["nonedge_semantic_calibration"])
    jobs: list[dict[str, Any]] = []

    def add(scene_id: str, variant: str, role: str, nonedge: bool = False) -> None:
        text = story(scene_id, "full" if nonedge else variant)
        pairs = pair_pool(text, scene_id, nonedge=nonedge)
        for prompt_id in ("P1", "P2", "P3", "P4", "P5", "P6"):
            prompt = render_sentence_id_prompt(prompt_id=prompt_id, story=text, pairs=pairs)
            item = {
                "scene_id": scene_id, "story_variant": variant, "input_story_variant": "full" if nonedge else variant,
                "role": role, "prompt_variant": prompt_id, "story": text,
                "story_sha256": sha_bytes(text.encode()), "prompt": prompt,
                "prompt_render_sha256": sha_bytes(prompt.encode()),
                "pairs": [p.__dict__ for p in pairs],
                "model_snapshot": "gpt-5.4-nano-2026-03-17", "reasoning_effort": "medium",
                "schema_sha256": sha_file(SCHEMA),
            }
            item["logical_id"] = sha_bytes(canon({k: item[k] for k in ("scene_id", "story_variant", "prompt_variant", "model_snapshot", "schema_sha256")}))
            jobs.append(item)

    for row in rows:
        add(row["study_id"], "full", "certification")
        add(row["study_id"], "partial", "certification")
    for scene_id in ambiguous_ids:
        add(scene_id, "ambiguous", "diagnostic")
    for scene_id in nonedge_ids:
        add(scene_id, "nonedge", "diagnostic", nonedge=True)
    if len(jobs) != 2640 or len({j["logical_id"] for j in jobs}) != 2640:
        raise RuntimeError("semantic workload or identity drift")
    return jobs


def append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(canon(row) + b"\n")


def retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    return status == 429 or (isinstance(status, int) and status >= 500) or type(exc).__name__ in {"APIConnectionError", "APITimeoutError"}


def run() -> dict[str, Any]:
    auth = load_auth()
    jobs = build_jobs()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    cached = load_jsonl(RAW_PATH)
    cache_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in cached:
        cache_by_id.setdefault(row["logical_id"], []).append(row)
    if len({(r["logical_id"], r.get("attempt", 0)) for r in cached}) != len(cached):
        raise RuntimeError("duplicate semantic cache identity")
    ledger = CalibrationTokenLedger(LEDGER_PATH, max_total_tokens=3_000_000, reset_hour=7, timezone_name="Asia/Ho_Chi_Minh", input_rate_per_million=0.20, output_rate_per_million=1.25)
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        env = ROOT / ".env"
        if env.is_file():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("OPENAI_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    os.environ["OPENAI_API_KEY"] = key
                    break
    if not key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    client = OpenAI(api_key=key, max_retries=0)
    attempt_count = len(cached)
    new_calls = 0
    errors = 0
    last_request = 0.0
    estimate = int(json.loads((ROOT / "data/manifests/p1_v3_nano_medium_calibration_look120_provider_preflight.json").read_text())["total_tokens"])
    for item in jobs:
        existing = cache_by_id.get(item["logical_id"], [])
        if any(r.get("status") in {"completed_valid", "completed_pair_invalid", "completed_schema_invalid"} for r in existing):
            continue
        attempt = len(existing)
        try:
            reservation = ledger.reserve(item["logical_id"], attempt, estimate, metadata={"scene_id": item["scene_id"], "story_variant": item["story_variant"], "prompt_variant": item["prompt_variant"]})
        except CalibrationBudgetError as exc:
            audit = {"status": "STOPPED_HARD_TOKEN_LIMIT", "planned": len(jobs), "completed": sum(any(r.get("status", "").startswith("completed") for r in cache_by_id.get(j["logical_id"], [])) for j in jobs), "provider_attempts": attempt_count, "errors": errors, "reason": str(exc), "token_snapshot": ledger.snapshot(), "oracle_access": False, "holdout_access": False}
            AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True); AUDIT_PATH.write_bytes(canon(audit) + b"\n"); return audit
        while True:
            wait = 3.2 - (time.perf_counter() - last_request)
            if wait > 0:
                time.sleep(wait)
            started = time.perf_counter()
            try:
                response = client.responses.create(model=item["model_snapshot"], input=item["prompt"], reasoning={"effort": "medium"}, max_output_tokens=8192, service_tier="default", store=False, text={"format": {"type": "json_schema", "name": "semantic_sentence_id_response_v1", "schema": schema, "strict": True}}, metadata={"task": "P1_V3_NANO_MEDIUM_CALIBRATION_LOOK120", "logical_id": item["logical_id"], "study_execution": "true"})
                last_request = time.perf_counter()
                usage = response.usage
                usage_dict = {"input_tokens": int(usage.input_tokens), "output_tokens": int(usage.output_tokens), "total_tokens": int(getattr(usage, "total_tokens", usage.input_tokens + usage.output_tokens)), "reasoning_tokens": int(getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0)}
                ledger_record = ledger.commit_provider_usage(item["logical_id"], attempt, usage_dict, metadata={"request_id": getattr(response, "_request_id", None)})
                try:
                    parsed = json.loads(response.output_text or "")
                    pairs = tuple(StablePair(**p) for p in item["pairs"])
                    validation = validate_response_by_pair(parsed, pairs, item["story"])
                    status = "completed_valid" if validation["response_valid"] else "completed_pair_invalid"
                except Exception:
                    parsed = None; validation = {"response_valid": False, "pairs": []}; status = "completed_schema_invalid"
                rec = {"schema_version": "fourgraph.p1_v3_nano_calibration_semantic_raw.v1", "logical_id": item["logical_id"], "attempt": attempt, "status": status, "scene_id": item["scene_id"], "story_variant": item["story_variant"], "role": item["role"], "prompt_variant": item["prompt_variant"], "model_snapshot": response.model, "request_id": getattr(response, "_request_id", None), "input_tokens": usage_dict["input_tokens"], "output_tokens": usage_dict["output_tokens"], "reasoning_tokens": usage_dict["reasoning_tokens"], "total_tokens": usage_dict["total_tokens"], "latency_ms": round((time.perf_counter() - started) * 1000), "story_sha256": item["story_sha256"], "prompt_render_sha256": item["prompt_render_sha256"], "response_sha256": sha_bytes((response.output_text or "").encode()), "response_valid": validation["response_valid"], "valid_pair_count": sum(p.get("pair_valid") is True for p in validation.get("pairs", [])), "invalid_pair_count": sum(p.get("pair_valid") is False for p in validation.get("pairs", [])), "raw_text": response.output_text, "cost_usd": ledger_record["cost_usd"]}
                append(RAW_PATH, rec); append(META_PATH, {k: rec[k] for k in ("logical_id", "attempt", "scene_id", "story_variant", "prompt_variant", "request_id", "model_snapshot", "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "latency_ms", "cost_usd")})
                cache_by_id.setdefault(item["logical_id"], []).append(rec); attempt_count += 1; new_calls += 1; break
            except Exception as exc:
                last_request = time.perf_counter()
                try:
                    ledger.release(item["logical_id"], attempt, reason=f"provider_error:{type(exc).__name__}")
                except CalibrationBudgetError:
                    pass
                rec = {"schema_version": "fourgraph.p1_v3_nano_calibration_semantic_raw.v1", "logical_id": item["logical_id"], "attempt": attempt, "status": "provider_error", "scene_id": item["scene_id"], "story_variant": item["story_variant"], "role": item["role"], "prompt_variant": item["prompt_variant"], "error_type": type(exc).__name__, "error_message": str(exc)[:500], "retryable": retryable(exc), "latency_ms": round((time.perf_counter() - started) * 1000)}
                append(RAW_PATH, rec); cache_by_id.setdefault(item["logical_id"], []).append(rec); attempt_count += 1; errors += 1
                if not retryable(exc) or attempt >= 1:
                    raise
                attempt += 1
                reservation = ledger.reserve(item["logical_id"], attempt, estimate, metadata={"retry": True})
    completed = sum(any(r.get("status", "").startswith("completed") for r in cache_by_id.get(j["logical_id"], [])) for j in jobs)
    audit = {"status": "PASS_SEMANTIC_LOOK120_COMPLETE" if completed == len(jobs) and errors == 0 else "COMPLETED_WITH_ERRORS", "planned": len(jobs), "completed": completed, "provider_attempts": attempt_count, "new_calls": new_calls, "errors": errors, "token_snapshot": ledger.snapshot(), "oracle_access": False, "holdout_access": False, "statistical_reruns": 0, "next_action": "stop_before_next_look_and_before_oracle_scoring"}
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True); AUDIT_PATH.write_bytes(canon(audit) + b"\n"); return audit


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--execute", action="store_true"); parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        jobs = build_jobs(); print(json.dumps({"status": "PASS_PLAN", "planned": len(jobs), "api_calls": 0}, indent=2)); return 0
    result = run(); print(json.dumps(result, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
