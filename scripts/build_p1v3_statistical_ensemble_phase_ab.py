"""Build and audit the P1-v3 statistical-ensemble Phase A-B artifacts.

This command is deliberately offline. It uses only synthetic fixture graphs and
text rendering; it never loads study observations, invokes Tetrad/R, or calls
an LLM API.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from fourgraph.statistical_ensemble import (
    BOOTSTRAP_CANDIDATES,
    PRIMARY_METHODS,
    mmpc_symmetric_skeleton,
    pag_to_skeleton,
    primary_majority_skeleton,
    shared_semantic_pair_pool,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1v3_statistical_ensemble_manifest.yaml"
ALGORITHM = ROOT / "configs/p1v3_algorithm_manifest.yaml"
FIXTURE = ROOT / "data/manifests/p1v3_statistical_ensemble_fixture.jsonl"
AUDIT = ROOT / "data/manifests/p1v3_statistical_ensemble_phase_ab_audit.json"
REPORT = ROOT / "reports/p1v3_statistical_ensemble_phase_ab.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def fixture_cases() -> list[dict[str, Any]]:
    nodes = ["X000", "X001", "X002", "X003", "X004"]
    pag_edges = [
        {"node1": "X000", "node2": "X001", "endpoint1": "CIRCLE", "endpoint2": "ARROW"},
        {"node1": "X001", "node2": "X002", "endpoint1": "ARROW", "endpoint2": "ARROW"},
        {"node1": "X003", "node2": "X004", "endpoint1": "CIRCLE", "endpoint2": "CIRCLE"},
    ]
    mmpc_matrix = {node: {other: int(node != other and {node, other} in ({"X000", "X001"}, {"X001", "X002"})) for other in nodes} for node in nodes}
    method_skeletons = {
        "single_boss": [("X000", "X001"), ("X001", "X002")],
        "bootstrap_boss": [("X000", "X001"), ("X001", "X002"), ("X002", "X003")],
        "pc": [("X000", "X001"), ("X002", "X003")],
        "mmpc": [("X000", "X001")],
        "fges": [("X000", "X001"), ("X002", "X003")],
    }
    candidates = {
        candidate: list(method_skeletons["bootstrap_boss"])
        for candidate in BOOTSTRAP_CANDIDATES
    }
    return [
        {"case_id": "FIX_PAG_ALL_ENDPOINTS", "nodes": nodes, "pag_edges": pag_edges},
        {"case_id": "FIX_MMPC_SYMMETRIC", "nodes": nodes, "mmpc_matrix": mmpc_matrix},
        {"case_id": "FIX_PRIMARY_3_OF_5", "nodes": nodes, "method_skeletons": method_skeletons},
        {"case_id": "FIX_SHARED_POOL_6_CANDIDATES", "nodes": nodes, "single_boss": method_skeletons["single_boss"], "bootstrap_candidates": candidates, "ensemble": [("X000", "X001"), ("X002", "X003")]},
    ]


def render_token_preflight(config: dict[str, Any]) -> dict[str, Any]:
    nodes = [f"X{i:03d}" for i in range(7)]
    pairs = [[nodes[i], nodes[j]] for i in range(7) for j in range(i + 1, 7)]
    story = " ".join(
        f"The public variable {node} is an index measured in the synthetic study."
        for node in nodes
    )
    prompt = (ROOT / config["semantic_shared_pool"]["prompt"]).read_text(encoding="utf-8")
    schema = (ROOT / config["semantic_shared_pool"]["schema"]).read_text(encoding="utf-8")
    payload = json.dumps({"nodes": nodes, "pairs": pairs, "story": story}, sort_keys=True)
    input_chars = len(prompt) + len(schema) + len(payload)
    # This is a deterministic planning estimate, not provider token accounting.
    estimated_input = (input_chars + 3) // 4
    estimated_output = (len(schema) + len(json.dumps(pairs)) + 3) // 4
    return {
        "max_nodes": 7,
        "max_pairs": len(pairs),
        "estimated_input_tokens_chars_div_4": estimated_input,
        "estimated_output_tokens_chars_div_4": estimated_output,
        "provider_tokenizer_verified": False,
        "validated_context_envelope_status": "pending_verification",
        "overflow_action": "STOP_AND_REPORT_AMENDMENT_NEEDED",
    }


def execute() -> dict[str, Any]:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    algorithm = yaml.safe_load(ALGORITHM.read_text(encoding="utf-8"))
    require(config["authorization"]["study_scene_materialization"] is False, "study materialization must be forbidden")
    require(config["authorization"]["semantic_api_calls"] is False, "semantic API must be forbidden")
    require(len(config["statistical_conditions"]["bootstrap_candidates"]) == 6, "six candidates required")
    require(algorithm["methods"]["fges"]["comparison_scope"] == "algorithm_plus_score_sensitivity", "FGES scope drift")
    require(algorithm["methods"]["mmpc"]["environment_status"] == "pending_verification", "MMPC must remain pending")

    counts = {"fixture_cases": 0, "pag_pass": 0, "mmpc_pass": 0, "majority_pass": 0, "pool_pass": 0, "invalid_fixtures_rejected": 0}
    records: list[dict[str, Any]] = []
    cases = fixture_cases()
    for case in cases:
        cid = case["case_id"]
        if "pag_edges" in case:
            result = sorted(map(list, pag_to_skeleton(case["nodes"], case["pag_edges"])))
            require(result == [["X000", "X001"], ["X001", "X002"], ["X003", "X004"]], "PAG fixture mismatch")
            counts["pag_pass"] += 1
            records.append({"case_id": cid, "result": result, "status": "PASS"})
        elif "mmpc_matrix" in case:
            result = sorted(map(list, mmpc_symmetric_skeleton(case["nodes"], case["mmpc_matrix"])))
            require(result == [["X000", "X001"], ["X001", "X002"]], "MMPC fixture mismatch")
            counts["mmpc_pass"] += 1
            records.append({"case_id": cid, "result": result, "status": "PASS"})
        elif "method_skeletons" in case:
            result = sorted(map(list, primary_majority_skeleton(case["method_skeletons"], case["nodes"])))
            require(result == [["X000", "X001"], ["X002", "X003"]], "majority fixture mismatch")
            counts["majority_pass"] += 1
            records.append({"case_id": cid, "result": result, "status": "PASS"})
        else:
            result = sorted(map(list, shared_semantic_pair_pool(case["nodes"], single_boss=case["single_boss"], bootstrap_candidates=case["bootstrap_candidates"], ensemble=case["ensemble"])))
            require(result == [["X000", "X001"], ["X001", "X002"], ["X002", "X003"]], "shared pool fixture mismatch")
            require(len(case["bootstrap_candidates"]) == 6, "candidate reuse mismatch")
            counts["pool_pass"] += 1
            records.append({"case_id": cid, "result": result, "status": "PASS"})
    counts["fixture_cases"] = len(records)

    try:
        mmpc_symmetric_skeleton(["X000", "X001"], {"X000": {"X000": 0, "X001": 1}, "X001": {"X000": 0, "X001": 0}})
    except ValueError:
        counts["invalid_fixtures_rejected"] += 1
    else:
        raise RuntimeError("asymmetric MMPC fixture was not rejected")
    try:
        pag_to_skeleton(["X000", "X001"], [{"node1": "X000", "node2": "X999"}])
    except ValueError:
        counts["invalid_fixtures_rejected"] += 1
    else:
        raise RuntimeError("unknown PAG node fixture was not rejected")

    token = render_token_preflight(config)
    records.append({"case_id": "TOKEN_PREFLIGHT_MAX_7_NODES", "result": token, "status": "PENDING_PROVIDER_VERIFICATION"})
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_bytes(b"".join(canonical(row) for row in records))
    audit = {
        "schema_version": "fourgraph.p1_v3_statistical_ensemble_phase_ab_audit.v1",
        "task": config["task"],
        "status": "PASS_OFFLINE_FIXTURE_CONFORMANCE_PENDING_ENVIRONMENT_AND_TOKEN_VERIFICATION",
        "counts": counts,
        "token_preflight": token,
        "verified": {
            "six_bootstrap_candidates": True,
            "primary_ensemble_3_of_5": True,
            "pag_endpoint_semantics_discarded": True,
            "mmpc_asymmetry_fails_closed": True,
            "shared_pool_reuse": True,
            "no_live_execution": True,
        },
        "pending": {
            "rscript_and_bnlearn_version": True,
            "activated_tetrad_runtime": True,
            "provider_tokenizer_context_envelope": True,
        },
        "evidence_boundary": {
            "study_scene_materialization": 0,
            "observations_loaded": False,
            "statistical_fits": 0,
            "semantic_api_calls": 0,
            "oracle_accessed": False,
            "holdout_accessed": False,
        },
        "dependencies": [
            {"path": "configs/p1v3_statistical_ensemble_manifest.yaml", "sha256": sha256(CONFIG)},
            {"path": "configs/p1v3_algorithm_manifest.yaml", "sha256": sha256(ALGORITHM)},
            {"path": "schemas/p1v3_statistical_ensemble_manifest.schema.json", "sha256": sha256(ROOT / "schemas/p1v3_statistical_ensemble_manifest.schema.json")},
            {"path": "src/fourgraph/statistical_ensemble.py", "sha256": sha256(ROOT / "src/fourgraph/statistical_ensemble.py")},
            {"path": "environment.lock", "sha256": sha256(ROOT / "environment.lock")},
            {"path": "reports/p1v3_statistical_ensemble_protocol_amendment.md", "sha256": sha256(ROOT / "reports/p1v3_statistical_ensemble_protocol_amendment.md")},
            {"path": "prompts/p1_semantic_empirical_reliability_v3.md", "sha256": sha256(ROOT / "prompts/p1_semantic_empirical_reliability_v3.md")},
            {"path": "schemas/semantic_whole_graph_response_v3.schema.json", "sha256": sha256(ROOT / "schemas/semantic_whole_graph_response_v3.schema.json")},
        ],
        "fixture_sha256": sha256(FIXTURE),
    }
    AUDIT.write_bytes(canonical(audit))
    report = f"""# P1-v3 Statistical Ensemble — Phase A–B audit

## Trạng thái

Phase A–B offline đã hoàn tất fixture conformance. Chưa sinh study scene,
chưa tải observational data, chưa chạy BOSS/Bootstrap-BOSS/Tetrad/R và chưa
gọi semantic API.

## Kết quả fixture

- PAG→skeleton: {counts['pag_pass']}/1
- MMPC symmetric output: {counts['mmpc_pass']}/1
- Primary 3/5 vote: {counts['majority_pass']}/1
- Shared six-candidate pool: {counts['pool_pass']}/1
- Invalid fixture fail-closed: {counts['invalid_fixtures_rejected']}/2

## Token preflight

Tối đa 7 node tạo 21 cặp. Ước lượng offline bằng ký tự/4 là
`{token['estimated_input_tokens_chars_div_4']}` input tokens và
`{token['estimated_output_tokens_chars_div_4']}` output tokens. Đây chưa phải
provider token accounting; tokenizer/context envelope vẫn **pending verification**.
Nếu vượt envelope, live execution phải dừng và mở amendment; không chunk prompt.

## Environment pending

R/bnlearn `5.3-20260901` và runtime Tetrad/Python/Java phải được xác minh trước
live execution. `Rscript` hiện chưa có trong PATH; không thay MMPC bằng thuật toán khác.

Audit SHA-256: `{sha256(AUDIT)}`
"""
    REPORT.write_text(report, encoding="utf-8")
    return audit


def check() -> dict[str, Any]:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    fixture_bytes = FIXTURE.read_bytes()
    require(audit["fixture_sha256"] == sha256(FIXTURE), "fixture hash drift")
    require(audit["counts"]["invalid_fixtures_rejected"] == 2, "invalid fixture count drift")
    require(audit["evidence_boundary"]["statistical_fits"] == 0, "live fit occurred")
    require(audit["evidence_boundary"]["semantic_api_calls"] == 0, "API call occurred")
    require(fixture_bytes, "fixture is empty")
    return {"status": "PASS_REPLAY", "fixture_sha256": sha256(FIXTURE), "audit_sha256": sha256(AUDIT)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = check() if args.check else execute()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
