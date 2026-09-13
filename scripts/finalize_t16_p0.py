"""Seal or byte-check the T16 P0 findings and REFINE decision."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402


def obj(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def pair(
    records: list[dict[str, Any]], family: str, left: str, right: str
) -> dict[str, Any]:
    matches = [
        item for item in records
        if item["family"] == family
        and item["left_condition"] == left
        and item["right_condition"] == right
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Missing T15 contrast: {family} {left} {right}")
    return matches[0]


def build() -> bytes:
    config_path = ROOT / "configs/t16_p0_decision.yaml"
    report_path = ROOT / "reports/p0_findings.md"
    decision = config(config_path)
    if decision["decision"] != "REFINE":
        raise RuntimeError("T16 decision drift")
    if decision["next_phase"]["authorized_action"] != "T17_P1_HYBRID_PROTOCOL_DESIGN":
        raise RuntimeError("T16 next-action drift")
    if any((decision["next_phase"][key] for key in (
        "p1_generation_authorized", "h2_live_calls_authorized", "p1_holdout_access_authorized"
    ))):
        raise RuntimeError("T16 cannot authorize P1 execution")

    for parent in decision["parents"].values():
        path = ROOT / parent["path"]
        if sha256_hex(path.read_bytes()) != parent["sha256"]:
            raise RuntimeError(f"T16 parent drift: {parent['path']}")

    t15_path = ROOT / decision["parents"]["t15_analysis_audit"]["path"]
    pair_path = ROOT / decision["parents"]["t15_pairwise_results"]["path"]
    t15, pairs = obj(t15_path), rows(pair_path)
    if not t15["verdict"]["t15_complete"] or t15["scope"]["api_calls"] != 0:
        raise RuntimeError("T15 is not a sealed offline analysis")
    if t15["condition_summaries"]["downstream"]["G_ORACLE"]["scene_macro_oracle_answer_accuracy"] != 0.93:
        raise RuntimeError("T16 Oracle summary drift")
    if t15["condition_summaries"]["graph"]["G_HYBRID"]["available_scenes"] != 23:
        raise RuntimeError("T16 Hybrid completion drift")
    hybrid_projection = pair(
        pairs, "B_downstream_oracle_answer_accuracy", "G_SCD_PROJECTED", "G_HYBRID"
    )
    llm_hybrid = pair(
        pairs, "B_downstream_oracle_answer_accuracy", "G_LLM", "G_HYBRID"
    )
    if hybrid_projection["effect_left_minus_right"] != -0.6 or not hybrid_projection["bootstrap_bh_reject_alpha_0_05"]:
        raise RuntimeError("T16 Hybrid/projection inference drift")
    if llm_hybrid["bootstrap_bh_reject_alpha_0_05"]:
        raise RuntimeError("T16 cannot claim LLM/Hybrid downstream separation")

    audit = {
        "schema_version": "fourgraph.t16_p0_findings_audit.v1",
        "task": "T16",
        "phase": "released_causalds_p0",
        "decision": "REFINE",
        "inputs": {
            "decision_config": {"path": config_path.relative_to(ROOT).as_posix(), "sha256": sha256_hex(config_path.read_bytes())},
            "p0_findings": {"path": report_path.relative_to(ROOT).as_posix(), "sha256": sha256_hex(report_path.read_bytes())},
            **{name: parent for name, parent in decision["parents"].items()},
        },
        "implementation": {
            "scripts/finalize_t16_p0.py": sha256_hex((ROOT / "scripts/finalize_t16_p0.py").read_bytes()),
        },
        "claim_counts": {
            "supported": len(decision["supported_claims"]),
            "unsupported": len(decision["unsupported_claims"]),
        },
        "evidence_boundary": decision["evidence_boundary"],
        "next_phase": decision["next_phase"],
        "verdict": {
            "t16_complete": True,
            "p0_complete": True,
            "p0_decision": "REFINE",
            "p1_started": False,
            "t17_protocol_design_authorized": True,
            "p1_execution_authorized": False,
        },
    }
    return canonical_json_bytes(audit, newline=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = ROOT / "data/manifests/t16_p0_findings_audit.json"
    payload = build()
    if args.check:
        if not output.is_file() or output.read_bytes() != payload:
            raise RuntimeError("T16 audit replay differs byte-for-byte")
    else:
        output.write_bytes(payload)
    print(json.dumps(json.loads(payload)["verdict"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

