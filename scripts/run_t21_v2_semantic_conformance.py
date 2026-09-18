"""Run the gated GPT-5.4 Nano semantic-preference conformance candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.t21_openai_backend import T21OpenAIBackend  # noqa: E402


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected YAML object")
    return value


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def render(case: dict[str, Any], template: str) -> str:
    pair = case["requested_pair"]
    pairs = json.dumps([pair], ensure_ascii=False, indent=2, sort_keys=True)
    if template.count("{{PAIRS_JSON}}") != 1 or template.count("{{STORY}}") != 1:
        raise ValueError("Prompt placeholders changed")
    return template.replace("{{PAIRS_JSON}}", pairs).replace("{{STORY}}", case["story"])


def parse(raw_text: str, case: dict[str, Any]) -> float:
    value = json.loads(raw_text)
    if not isinstance(value, dict) or set(value) != {"schema_version", "preferences"}:
        raise ValueError("Response fields mismatch")
    if value["schema_version"] != "fourgraph.p1_semantic_preferences_response.v1":
        raise ValueError("Response schema mismatch")
    rows = value["preferences"]
    if not isinstance(rows, list) or len(rows) != 1:
        raise ValueError("Expected exactly one preference")
    row = rows[0]
    required = {"left", "right", "probability_left_causes_right", "evidence"}
    if not isinstance(row, dict) or set(row) != required:
        raise ValueError("Preference row fields mismatch")
    pair = case["requested_pair"]
    if row["left"] != pair["left"] or row["right"] != pair["right"]:
        raise ValueError("Preference endpoints changed")
    probability = row["probability_left_causes_right"]
    if isinstance(probability, bool) or not isinstance(probability, (int, float)) or not 0.001 <= float(probability) <= 0.999:
        raise ValueError("Invalid probability")
    if not isinstance(row["evidence"], str) or not row["evidence"].strip():
        raise ValueError("Missing evidence")
    return float(probability)


def correct(case: dict[str, Any], probability: float) -> bool:
    low, high = case["expected_probability_interval"]
    return float(low) <= probability <= float(high)


def raw_cache(path: Path) -> dict[tuple[str, int], dict[str, Any]]:
    if not path.exists():
        return {}
    rows = load_jsonl(path)
    cache = {}
    for row in rows:
        key = (row["call_id"], int(row["attempt"]))
        if key in cache:
            raise RuntimeError("Duplicate cache key")
        if sha256_hex(row["prompt"].encode()) != row["prompt_sha256"] or sha256_hex(row["raw_text"].encode()) != row["raw_sha256"]:
            raise RuntimeError("Raw cache hash mismatch")
        cache[key] = row
    return cache


def append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(canonical_json_bytes(row, newline=True))


def retry_prompt(base: str, raw: str, error: str) -> str:
    return base + "\n\nVALIDATION RETRY:\nReturn a complete replacement JSON object.\nERROR: " + error + "\nPREVIOUS:\n" + raw


def evaluate(rows: list[dict[str, Any]], gates: dict[str, float]) -> tuple[dict[str, Any], bool]:
    total = len(rows)
    parse_rate = sum(row["parse_success"] for row in rows) / total
    first_rate = sum(row["first_attempt_schema_success"] for row in rows) / total
    by_class = {}
    for label in ("forward", "reverse", "ambiguous"):
        selected = [row for row in rows if row["expected_class"] == label]
        by_class[label] = {
            "correct": sum(row["strict_correct"] for row in selected),
            "total": len(selected),
            "accuracy": sum(row["strict_correct"] for row in selected) / len(selected),
        }
    overall = sum(row["strict_correct"] for row in rows) / total
    passed = (
        parse_rate >= gates["parse_success"]
        and first_rate >= gates["first_attempt_schema_success"]
        and by_class["forward"]["accuracy"] >= gates["forward_accuracy"]
        and by_class["reverse"]["accuracy"] >= gates["reverse_accuracy"]
        and by_class["ambiguous"]["accuracy"] >= gates["ambiguous_accuracy"]
        and overall >= gates["overall_accuracy"]
    )
    return {
        "parse_success_rate": parse_rate,
        "first_attempt_schema_success_rate": first_rate,
        "overall_accuracy": overall,
        "by_class": by_class,
    }, passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    candidate_path = ROOT / args.candidate
    candidate = load_yaml(candidate_path)
    for relative, expected in candidate["pins"].items():
        if file_hash(ROOT / relative) != expected:
            raise RuntimeError(f"Pinned dependency changed: {relative}")
    base = load_yaml(ROOT / candidate["parent_config"])
    suite = load_jsonl(ROOT / base["outputs"]["suite"])
    smoke = load_json(ROOT / base["outputs"]["smoke_manifest"])
    stage = candidate["stage"]
    if stage == "smoke_12":
        selected = [row for row in suite if row["case_id"] in set(smoke["case_ids"])]
        scores_path = ROOT / base["outputs"]["smoke_scores"]
        audit_path = ROOT / base["outputs"]["smoke_audit"]
    elif stage == "full_120":
        smoke_audit = load_json(ROOT / candidate["required_smoke_audit"])
        if smoke_audit["verdict"]["smoke_passed"] is not True:
            raise RuntimeError("Smoke gate did not authorize full execution")
        selected = suite
        scores_path = ROOT / base["outputs"]["full_scores"]
        audit_path = ROOT / base["outputs"]["full_audit"]
    else:
        raise ValueError("Unknown candidate stage")
    if len(selected) != int(candidate["live_execution"]["maximum_logical_calls"]):
        raise RuntimeError("Candidate logical-call cap and selected suite differ")
    prompt = (ROOT / base["prompt"]["path"]).read_text(encoding="utf-8")
    schema = load_json(ROOT / base["prompt"]["response_schema"])
    raw_path = ROOT / base["outputs"]["raw_calls"]
    cache = raw_cache(raw_path)
    backend = None
    if not args.check:
        load_dotenv(ROOT / ".env", override=True)
        backend = T21OpenAIBackend(
            api_key=os.environ.get(base["model"]["credential_env"], ""),
            response_schema=schema,
            schema_name="p1_t21_v2_semantic_preferences",
            model_snapshot=base["model"]["model_snapshot"],
            max_output_tokens=base["model"]["max_output_tokens"],
            timeout_seconds=base["model"]["timeout_seconds"],
            transport_max_retries=base["model"]["transport_max_retries"],
        )
    new_calls = 0
    records = []
    for case in selected:
        base_prompt = render(case, prompt)
        current_prompt = base_prompt
        attempts = []
        probability = None
        for attempt in range(base["model"]["validation_retries"] + 1):
            key = (case["case_id"], attempt)
            prompt_hash = sha256_hex(current_prompt.encode())
            if key in cache:
                raw = cache[key]
                if raw["prompt_sha256"] != prompt_hash:
                    raise RuntimeError(f"Replay prompt mismatch: {key}")
            else:
                if backend is None:
                    raise RuntimeError(f"Missing replay entry: {key}")
                if new_calls >= candidate["live_execution"]["maximum_logical_calls"]:
                    raise RuntimeError("Live call cap exceeded")
                raw = backend.call(call_id=case["case_id"], prompt=current_prompt, attempt=attempt)
                raw["prompt_sha256"] = prompt_hash
                raw["raw_sha256"] = sha256_hex(raw["raw_text"].encode())
                append(raw_path, raw)
                cache[key] = raw
                new_calls += 1
            error = None
            try:
                probability = parse(raw["raw_text"], case)
            except (json.JSONDecodeError, ValueError) as exc:
                error = str(exc)
            attempts.append(
                {
                    "attempt": attempt,
                    "prompt_sha256": prompt_hash,
                    "raw_sha256": raw["raw_sha256"],
                    "request_id": raw.get("request_id"),
                    "input_tokens": raw.get("input_tokens"),
                    "output_tokens": raw.get("output_tokens"),
                    "reasoning_tokens": raw.get("reasoning_tokens"),
                    "latency_ms": raw.get("latency_ms"),
                    "validation_error": error,
                }
            )
            if error is None:
                break
            current_prompt = retry_prompt(base_prompt, raw["raw_text"], error)
        parsed = probability is not None
        records.append(
            {
                "schema_version": "fourgraph.p1_t21_v2_semantic_score.v1",
                "case_id": case["case_id"],
                "expected_class": case["expected_class"],
                "expected_probability_interval": case["expected_probability_interval"],
                "probability_left_causes_right": probability,
                "parse_success": parsed,
                "first_attempt_schema_success": parsed and len(attempts) == 1,
                "strict_correct": parsed and correct(case, float(probability)),
                "attempts": attempts,
            }
        )
    metrics, passed = evaluate(records, candidate["gates"])
    score_bytes = b"".join(canonical_json_bytes(row, newline=True) for row in records)
    token_usage = {key: sum(int(a.get(key) or 0) for row in records for a in row["attempts"]) for key in ("input_tokens", "output_tokens", "reasoning_tokens")}
    audit = {
        "schema_version": "fourgraph.p1_t21_v2_semantic_live_audit.v1",
        "stage": stage,
        "candidate_sha256": file_hash(candidate_path),
        "counts": {
            "cases": len(records),
            "planned_new_api_calls_at_authorization": int(
                candidate["live_execution"].get(
                    "expected_new_calls", candidate["live_execution"]["maximum_logical_calls"]
                )
            ),
            "captured_attempts": sum(len(r["attempts"]) for r in records),
        },
        "metrics": metrics,
        "token_usage": token_usage,
        "outputs": {"scores_sha256": sha256_hex(score_bytes)},
        "evidence_boundary": {"P1_accessed": False, "holdout_accessed": False, "downstream_reasoner_executed": False},
        "verdict": {
            "smoke_passed": passed if stage == "smoke_12" else None,
            "full_conformance_passed": passed if stage == "full_120" else None,
            "full_execution_authorized": passed if stage == "smoke_12" else None,
            "development_rerun_authorized": passed if stage == "full_120" else False,
        },
    }
    audit_bytes = canonical_json_bytes(audit, newline=True)
    if args.check:
        if scores_path.read_bytes() != score_bytes or audit_path.read_bytes() != audit_bytes:
            raise RuntimeError("Conformance replay mismatch")
    else:
        scores_path.parent.mkdir(parents=True, exist_ok=True)
        scores_path.write_bytes(score_bytes)
        audit_path.write_bytes(audit_bytes)
    print(json.dumps({"stage": stage, "cases": len(records), "new_calls": new_calls, "metrics": metrics, "passed": passed}, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
