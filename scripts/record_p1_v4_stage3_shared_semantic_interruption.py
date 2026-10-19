"""Record one unknown-outcome transport interruption without replacing its call."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results/raw/p1_v4_stage3_method_development_cau/semantic/raw_responses.jsonl"
PLAN = ROOT / "data/manifests/p1_v4_stage3_shared_semantic_execution_plan_cau.json"
OLD = ROOT / "data/manifests/p1_v4_stage3_shared_semantic_execution_transport_incident.json"
CORRECTION = ROOT / "data/manifests/p1_v4_stage3_shared_semantic_execution_monitoring_correction.json"
INCIDENT = ROOT / "data/manifests/p1_v4_stage3_shared_semantic_execution_interruption_incident.json"


def line(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))["logical_calls"]
    rows = [json.loads(item) for item in RAW.read_text(encoding="utf-8").splitlines() if item]
    if len(rows) != 126 or [row["logical_id"] for row in rows] != [item["logical_id"] for item in plan[:126]]:
        raise RuntimeError("interruption recovery requires the exact frozen 126-call prefix")
    target = plan[126]
    missing = {"schema_version": "fourgraph.p1_v4_shared_semantic_raw.v1", "logical_id": target["logical_id"], "ordinal": 127,
               "status": "provider_error", "scene_id": target["study_id"], "variant": target["variant"], "prompt_id": target["prompt_id"],
               "model_snapshot": target["model_snapshot"], "reasoning_effort": target["reasoning_effort"],
               "error_type": "TransportOutcomeUnknown", "error_message": "Client process was stopped while a request was pending; no response, request ID, or provider usage was received.",
               "story_content_sha256": target["story_content_sha256"], "pair_pool_sha256": target["pair_pool_sha256"],
               "provider_response": False, "provider_usage": None, "retry_authorized": False}
    with RAW.open("ab") as handle:
        handle.write(line(missing))
    correction = {"schema_version": "fourgraph.p1_v4_semantic_monitoring_correction.v1", "status": "CORRECTED_HISTORICAL_MONITORING_ARTIFACT",
                  "supersedes": {"path": str(OLD.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(OLD)},
                  "correction": "The old incident's zero-response count was a monitoring misread. The append-only raw cache proves 126 completed provider responses before interruption.",
                  "verified_raw_prefix_records": 126, "verified_completed_provider_responses": 126, "oracle_access": 0, "holdout_access": 0}
    incident = {"schema_version": "fourgraph.p1_v4_shared_semantic_interruption_incident.v1", "status": "DISPOSITIONED_MISSING_NO_RETRY",
                "target": missing, "prior_completed_prefix": 126, "plan_sha256": sha(PLAN), "raw_sha256_after_missing_record": sha(RAW),
                "policy": "No retry/replacement occurs absent separate authorization; remaining never-started logical calls may continue.",
                "oracle_access": 0, "holdout_access": 0}
    CORRECTION.write_bytes(line(correction)); INCIDENT.write_bytes(line(incident))
    print(json.dumps({"target": target["logical_id"], "cached_records": 127, "status": incident["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
