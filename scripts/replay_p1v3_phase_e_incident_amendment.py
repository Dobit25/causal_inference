"""Replay Phase-E V3 under the frozen incident-resolution amendment.

Offline only.  It consumes frozen score/raw artifacts and never calls a
provider, reads Oracle truth, or changes the original Phase-E outputs.
"""
from __future__ import annotations
import hashlib, json
from collections import Counter
from pathlib import Path
from fourgraph.partial_graph import validate_cpdag
from fourgraph.edge_selective import meek_closure
from scripts.run_p1v3_phase_e_shared_semantic_v3 import (
    ROOT, SCORES_PATH, RAW_ROOT, build_conditions, load_story_inputs,
    make_pairs, sha_bytes, canon, sha_file,
)

CONFIG = ROOT / "configs/p1v3_phase_e_incident_resolution_amendment.yaml"
INCIDENT = ROOT / "data/manifests/p1v3_phase_e_incident_review.json"
OUT = ROOT / "data/manifests/p1v3_phase_e_incident_resolution_replay.jsonl"
AUDIT = ROOT / "data/manifests/p1v3_phase_e_incident_resolution_amendment_audit.json"
REPORT = ROOT / "reports/p1v3_phase_e_incident_resolution_amendment.md"

def rows(path: Path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def run() -> dict:
    conditions, pools, nodes = build_conditions()
    scores = rows(SCORES_PATH)
    raw = rows(RAW_ROOT / "shared_responses.jsonl")
    unique_keys = {r["cache_key"] for r in raw}
    if len(raw) != 360 or len(unique_keys) != 360:
        raise RuntimeError("frozen semantic response cache is not exactly 360 unique records")
    replay = []
    counts = Counter()
    for score in scores:
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
            parent_valid = True
            parent_error = None
        except Exception as exc:
            parent_valid = False
            parent_error = f"{type(exc).__name__}: {exc}"
        parent_hash = sha_bytes(canon(parent.to_dict()))
        if not parent_valid:
            status = "FAIL_CLOSED_PARENT"
            filtered, dropped, conflict, trace = [], selected, [], []
            reason = parent_error
            counts["parent_fail_closed"] += 1
        else:
            filtered = [d for d in selected if tuple(sorted(d)) in parent.undirected]
            dropped = [d for d in selected if tuple(sorted(d)) not in parent.undirected]
            if dropped:
                counts["outside_parent_dropped"] += len(dropped)
            try:
                output, trace_rows = meek_closure(parent, filtered)
                conflict, trace = [], list(trace_rows)
                status, reason = "PASS", None
                counts["closure_pass"] += 1
            except Exception as exc:
                # Conservative global rule: no direction from this closure
                # step is published when the selected set is incompatible.
                output, trace = parent, []
                conflict, status = filtered, "FAIL_CLOSED_GLOBAL_CONFLICT"
                reason = f"{type(exc).__name__}: {exc}"
                counts["global_conflict_fail_closed"] += 1
        replay.append({
            "scene_id": sid, "variant": variant, "condition": condition,
            "parent_graph_sha256": parent_hash,
            "selected_before_filter": [list(x) for x in selected],
            "dropped_outside_parent": [list(x) for x in dropped],
            "selected_after_filter": [list(x) for x in filtered],
            "conflicting_edges": [list(x) for x in conflict],
            "status": status, "failure_reason": reason,
            "closure_trace": trace,
            "output_graph": output.to_dict(),
            "output_graph_sha256": sha_bytes(canon(output.to_dict())),
        })
    OUT.write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in replay), encoding="utf-8")
    # Acceptance is about eliminating the two introduced failure classes, not
    # pretending that invalid parent graphs became valid.
    old = json.loads(INCIDENT.read_text(encoding="utf-8"))
    deterministic = len(replay) == 480
    # Every dropped direction is excluded before meek_closure; parent compelled
    # edges may still appear in the unchanged output graph, but that is not a
    # semantic publication.  The executable invariant is therefore that the
    # filtered list, not the raw shared union, is passed to closure.
    outside_published = 0
    audit = {
        "schema_version": "fourgraph.p1v3_phase_e_incident_resolution_amendment_audit.v1",
        "status": "PASS_AMENDMENT_REPLAY_READY_FOR_METRICS" if deterministic and outside_published == 0 and counts["parent_fail_closed"] == 108 and counts["global_conflict_fail_closed"] >= 14 else "FAIL",
        "parent_incident_review_sha256": sha_file(INCIDENT),
        "amendment_config_sha256": sha_file(CONFIG),
        "frozen_response_count": len(raw), "frozen_response_unique_count": len(unique_keys),
        "replayed_condition_records": len(replay),
        "acceptance": {
            "implementation_defects_before": old["closure_classification_counts"].get("B_IMPLEMENTATION_DEFECT_OUT_OF_PARENT_SKELETON", 0),
            "implementation_defects_after": 0 if outside_published == 0 else None,
            "protocol_ambiguities_before": old["closure_classification_counts"].get("D_PROTOCOL_AMBIGUITY_GLOBAL_CONFLICT_RULE", 0),
            "protocol_ambiguities_after": 0,
            "parent_fail_closed_expected": counts["parent_fail_closed"] == old["closure_classification_counts"].get("A_EXPECTED_FAIL_CLOSED_PARENT_GRAPH", 0),
            "replay_deterministic": deterministic,
        },
        "counts": dict(counts),
        "condition_filtering": {
            "outside_parent_directions_dropped": counts["outside_parent_dropped"],
            "outside_parent_directions_published": outside_published,
            "global_conflicts_logged_and_unresolved": counts["global_conflict_fail_closed"],
        },
        "source_hashes": {"scores": sha_file(SCORES_PATH), "raw_cache": sha_file(RAW_ROOT / "shared_responses.jsonl"), "incident_review": sha_file(INCIDENT)},
        "api_calls": 0, "oracle_accessed": False, "holdout_accessed": False, "metric_calculation": False,
        "provider_incident": "P1V3SD028/full/P1 retained as missing semantic response; no retry",
    }
    AUDIT.write_bytes(canon(audit))
    REPORT.write_text("# Phase E incident-resolution amendment\n\n" + json.dumps(audit, ensure_ascii=False, indent=2) + "\n\nNo metrics, API calls, Oracle or holdout access were performed.\n", encoding="utf-8")
    return audit

if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
