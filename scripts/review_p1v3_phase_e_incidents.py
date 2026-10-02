"""Offline incident review/replay for Phase-E V3.

No provider calls are made.  The review deliberately treats the Phase-E
outputs as immutable evidence and classifies, rather than repairs, failures.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from collections import Counter
from fourgraph.partial_graph import validate_cpdag
from fourgraph.edge_selective import meek_closure
from scripts.run_p1v3_phase_e_shared_semantic_v3 import (
    ROOT, AUDIT_PATH, SCORES_PATH, RAW_ROOT, build_conditions, load_story_inputs,
    make_pairs, sha_bytes, canon,
)

OUT = ROOT / "data/manifests/p1v3_phase_e_incident_review.json"
REPORT = ROOT / "reports/p1v3_phase_e_incident_review.md"

def load_rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def raw_hash_by_key():
    rows = load_rows(RAW_ROOT / "shared_responses.jsonl")
    return {r["cache_key"]: sha_bytes((r.get("response_text") or "").encode()) for r in rows}, rows

def review():
    conditions, pools, nodes = build_conditions()
    scores = load_rows(SCORES_PATH)
    raw_hashes, raw_rows = raw_hash_by_key()
    incidents = []
    for score in scores:
        if score["closure_status"] == "PASS":
            continue
        sid, variant, condition = score["scene_id"], score["variant"], score["condition"]
        parent = conditions[sid][condition]
        pairs = {p.pair_id: p for p in make_pairs(sid, pools[sid], nodes[sid])}
        selected = []
        for pair_id, vote in score["votes"].items():
            direction = vote.get("published_direction")
            if direction:
                p = pairs[pair_id]
                selected.append((p.node_a_id, p.node_b_id) if direction == "A_TO_B" else (p.node_b_id, p.node_a_id))
        try:
            validate_cpdag(parent)
            parent_valid = True; parent_reason = None
        except Exception as exc:
            parent_valid = False; parent_reason = f"{type(exc).__name__}: {exc}"
        if not parent_valid:
            category = "A_EXPECTED_FAIL_CLOSED_PARENT_GRAPH"
            replay_status = "DETERMINISTIC_PARENT_VALIDATION_FAIL"
            reason = parent_reason
        else:
            absent = [edge for edge in selected if tuple(sorted(edge)) not in parent.undirected]
            try:
                _, trace = meek_closure(parent, selected)
                replay_status = "REPLAY_PASS_UNEXPECTED"
                category = "D_PROTOCOL_AMBIGUITY"
                reason = "Original closure status was FAIL but replay succeeded."
            except Exception as exc:
                replay_status = "DETERMINISTIC_CLOSURE_FAIL"
                reason = f"{type(exc).__name__}: {exc}"
                if absent:
                    category = "B_IMPLEMENTATION_DEFECT_OUT_OF_PARENT_SKELETON"
                elif "cycle" in str(exc).lower():
                    # Each pair vote is contract-valid, but the protocol did
                    # not register a deterministic conflict-resolution rule
                    # for a globally cyclic vote set.
                    category = "D_PROTOCOL_AMBIGUITY_GLOBAL_CONFLICT_RULE"
                else:
                    category = "C_MALFORMED_OR_INCOMPLETE_SEMANTIC_EVIDENCE"
        raw_keys = [f"{sid}|{variant}|P{i}" for i in range(1, 7)]
        raw_hash_material = [raw_hashes.get(key) for key in raw_keys]
        semantic_raw_hash = sha_bytes(canon(raw_hash_material))
        incidents.append({
            "scene_id": sid, "variant": variant, "condition": condition,
            "parent_graph_sha256": sha_bytes(canon(parent.to_dict())),
            "semantic_raw_output_sha256": semantic_raw_hash,
            "semantic_raw_output_hashes": dict(zip(raw_keys, raw_hash_material)),
            "selected_directions": [list(x) for x in selected],
            "selected_outside_parent_undirected": [list(x) for x in locals().get("absent", [])],
            "original_closure_status": score["closure_status"],
            "replay_status": replay_status, "failure_reason": reason,
            "classification": category,
        })
    provider = next((r for r in raw_rows if r["cache_key"] == "P1V3SD028|full|P1"), None)
    provider_incident = {
        "cache_key": provider["cache_key"], "model": provider["model"], "prompt_sha256": provider["prompt_sha256"],
        "request_id": provider["request_id"], "response_sha256": raw_hashes[provider["cache_key"]],
        "error": provider["error"], "latency_ms": provider["latency_ms"],
        "input_tokens": provider["input_tokens"], "output_tokens": provider["output_tokens"], "total_tokens": provider["total_tokens"],
        "classification": "MISSING_SEMANTIC_RESPONSE_TRANSPORT_INCIDENT",
        "provider_processing_evidence": "No request_id, output, usage or response hash of provider content; transport raised APIConnectionError.",
        "disposition": "do_not_retry_or_replace; retain as missing semantic response",
    }
    summary = Counter(x["classification"] for x in incidents)
    replay = Counter(x["replay_status"] for x in incidents)
    result = {
        "schema_version": "fourgraph.p1v3_phase_e_incident_review.v1",
        "status": "STOPPED_IMPLEMENTATION_DEFECT_FOUND" if summary.get("B_IMPLEMENTATION_DEFECT_OUT_OF_PARENT_SKELETON") else "DISPOSITIONED_EXPECTED_FAILURES",
        "provider_incident": provider_incident,
        "closure_failures_reviewed": len(incidents),
        "closure_classification_counts": dict(summary),
        "replay_counts": dict(replay),
        "incidents": incidents,
        "metrics_authorized": False,
        "api_calls": 0, "oracle_accessed": False, "holdout_accessed": False,
        "source_hashes": {
            "phase_e_audit": hashlib.sha256(AUDIT_PATH.read_bytes()).hexdigest().upper(),
            "scores": hashlib.sha256(SCORES_PATH.read_bytes()).hexdigest().upper(),
            "raw": hashlib.sha256((RAW_ROOT / "shared_responses.jsonl").read_bytes()).hexdigest().upper(),
        },
    }
    OUT.write_bytes(canon(result))
    lines = ["# Phase E V3 incident-resolution review", "", f"Status: **{result['status']}**", "", "## Provider incident", json.dumps(provider_incident, ensure_ascii=False, indent=2), "", "## Closure review", f"Reviewed: {len(incidents)} failures", f"Classifications: `{dict(summary)}`", f"Replay: `{dict(replay)}`", "", "No API retry, output repair, Oracle/holdout access or official precision/coverage was performed.", "", "The dominant classification is an implementation defect when a shared-pool direction is applied to a condition whose parent graph does not contain that undirected edge. This is preserved as an incident; no result is overwritten."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result

if __name__ == "__main__":
    print(json.dumps(review(), ensure_ascii=False, indent=2))
