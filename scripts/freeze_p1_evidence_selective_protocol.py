from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_evidence_selective_v1.yaml"
PROMPT = ROOT / "prompts/p1_semantic_empirical_reliability_v1.md"
SCHEMAS = (
    ROOT / "schemas/statistical_edge_evidence_v1.schema.json",
    ROOT / "schemas/semantic_edge_evidence_v1.schema.json",
    ROOT / "schemas/semantic_whole_graph_response_v1.schema.json",
    ROOT / "schemas/evidence_selective_graph_v1.schema.json",
)
REPORT = ROOT / "reports/p1_evidence_selective_protocol.md"
AUDIT = ROOT / "data/manifests/p1_evidence_selective_protocol_freeze.json"

DEPENDENCIES = (
    CONFIG,
    PROMPT,
    *SCHEMAS,
    ROOT / "data/manifests/t21_v3e_terminal_audit.json",
    ROOT / "data/manifests/t18_p1_frozen_split.json",
    ROOT / "data/manifests/t18_p1_generation_audit.json",
    ROOT / "data/manifests/t19_p1_story_audit.json",
    ROOT / "schemas/graph_contract_v1.schema.json",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def validate_protocol(config: dict) -> dict:
    terminal = json.loads((ROOT / "data/manifests/t21_v3e_terminal_audit.json").read_text(encoding="utf-8"))
    if terminal["verdict"]["p1_v3_protocol_design_authorized"] is not True:
        raise RuntimeError("T21 v3-E did not authorize P1-v3 protocol design")
    if terminal["verdict"]["p1_v3_execution_authorized"] is not False:
        raise RuntimeError("T21 v3-E execution boundary is not closed")

    assert config["schema_version"] == "fourgraph.p1_evidence_selective_protocol.v1"
    assert config["experiment"]["status"] == "protocol_frozen_pre_implementation"
    stat = config["statistical_method"]
    assert stat["primary"] == "bootstrap_boss"
    assert stat["ensemble"]["status"] == "deferred"
    assert stat["ensemble"]["used_by_primary_parent_graph"] is False
    assert stat["observations"] == {
        "primary_n": 2000,
        "bootstrap_sample_n": 2000,
        "sampling": "rows_with_replacement",
        "repetitions": 200,
        "standardize_each_resample": True,
    }
    assert stat["threshold_grid"]["adjacency_stability"] == [0.60, 0.70, 0.80, 0.90, 0.95]
    assert stat["threshold_grid"]["direction_stability"] == [0.80, 0.90, 0.95]
    assert stat["threshold_grid"]["candidate_count_before_semantic_reliability"] == 15

    semantic = config["semantic_method"]
    assert semantic["model_snapshot"] == "gpt-5.4-nano-2026-03-17"
    assert semantic["call_granularity"] == "whole_graph"
    assert semantic["prompt_variants"] == ["P1", "P2", "P3", "P4", "P5", "P6"]
    assert semantic["balanced_pair_order"] == {
        "A_first": ["P1", "P3", "P5"],
        "B_first": ["P2", "P4", "P6"],
    }
    assert semantic["automatic_orientation_eligibility"] == ["very_high", "high"]
    assert semantic["self_reported_probability_used_as_confidence"] is False

    risk = config["risk_control"]
    assert risk["target_selective_error_alpha"] == 0.05
    assert risk["failure_probability_delta"] == 0.05
    assert risk["minimum_useful_coverage"] == 0.20

    boundary = config["freeze_boundary"]
    assert boundary == {
        "protocol_frozen": True,
        "bootstrap_implementation_exists": False,
        "bootstrap_runs_executed": 0,
        "scenes_generated": 0,
        "semantic_api_calls": 0,
        "final_holdout_accessed": False,
        "next_authorized_action": "P1_V3_BOOTSTRAP_BOSS_OFFLINE_IMPLEMENTATION_AND_CONFORMANCE",
        "next_action_forbids": [
            "running_200_bootstraps_on_study_scenes",
            "generating_successor_cohorts",
            "semantic_api_calls",
            "final_holdout_access",
        ],
    }

    prompt_text = PROMPT.read_text(encoding="utf-8")
    prompt_ids = re.findall(r"^## (P[1-6]) —", prompt_text, flags=re.MULTILINE)
    if prompt_ids != ["P1", "P2", "P3", "P4", "P5", "P6"]:
        raise RuntimeError(f"Prompt variants are not exact and ordered: {prompt_ids}")

    schema_ids = []
    for path in SCHEMAS:
        schema = json.loads(path.read_text(encoding="utf-8"))
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise RuntimeError(f"Unexpected JSON Schema draft: {path}")
        if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
            raise RuntimeError(f"Schema must be a closed object: {path}")
        schema_ids.append(schema["$id"])
    return {"prompt_ids": prompt_ids, "schema_ids": schema_ids}


def build() -> tuple[bytes, bytes]:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    validation = validate_protocol(config)
    dependencies = [
        {
            "bytes": path.stat().st_size,
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256(path),
        }
        for path in DEPENDENCIES
    ]
    bundle_material = b"".join(
        row["path"].encode("utf-8") + b"\0" + row["sha256"].encode("ascii") + b"\n"
        for row in dependencies
    )

    report = """# P1-v3 Evidence-Selective Hybrid — frozen protocol

## Research objective

P1-v3 tests whether resampling stability from observational data can restrict semantic orientation to statistically supported adjacencies, while repeated fixed semantic queries provide empirical reliability rather than treating an LLM's self-reported confidence as a causal probability.

The output is an evidence-aware partial graph and an edge ledger. The method may abstain; it is not required to manufacture a complete DAG.

## Frozen statistical design

- Primary method: Bootstrap-BOSS only. The BOSS/PC/DirectLiNGAM ensemble is deferred to a later robustness experiment.
- Each scene starts from `N=2000` observations. Every bootstrap resample also contains 2,000 rows drawn with replacement and is standardized independently.
- The registered study procedure uses 200 resamples per scene. Each unordered pair is recorded as absent, undirected, A→B or B→A; all rates use all 200 runs as denominator.
- Adjacency thresholds are `0.60, 0.70, 0.80, 0.90, 0.95`; direction thresholds are `0.80, 0.90, 0.95`.
- A weak adjacency is vetoed before semantic orientation. An unstable BOSS direction is downgraded to undirected, never silently reversed. A threshold-produced PDAG without a consistent DAG extension is invalid; no heuristic repair is allowed.

Bootstrap frequency is a resampling-stability measure, not a causal probability and not proof that an edge is correct.

## Frozen semantic design

- Model snapshot: `gpt-5.4-nano-2026-03-17`.
- Call unit: one whole-graph batch for each scene × story variant × prompt variant.
- Six fixed paraphrases balance variable order three versus three. Responses are normalized deterministically to A→B, B→A or undetermined.
- Very High means 6/6 same direction; High means 5/6 plus one undetermined; Medium means 4/6 plus two undetermined; any vote in both directions is Conflict.
- Only Very High and High may be automatically oriented, and only after their agreement group attains an empirical reliability lower bound of at least 95% on an independent calibration cohort. Medium remains unresolved/human review.
- Directed answers require an exact quote from the supplied story. Association-only text cannot support a direction.

The vote fraction and any model-generated number are not called a causal probability.

## Hybrid decision and risk control

An edge may receive a semantic direction only after passing the statistical veto, empirical semantic-reliability requirement and global graph-consistency checks. Meek closure is deterministic; propagated directions are labeled separately and remain part of end-to-end error.

Candidate selection uses Learn-then-Test or an equivalent familywise risk-control procedure with target selective error `α=0.05`, failure probability `δ=0.05`, and minimum useful coverage `20%`. Thresholds maximize coverage only among candidates certified safe. If none passes, the protocol stops without lowering the gate or opening the final holdout.

## Cohorts and evidence boundary

The old 20 development scenes and 20 P1V validation scenes are historical diagnostics only. New method-development, semantic-calibration and threshold-validation roles must be disjoint at scene level. Their exact sizes will be fixed by a prospective power simulation before generation—not by budget alone. The existing 80-scene final holdout remains sealed for one-time evaluation only after every upstream gate passes.

This freeze runs no Bootstrap-BOSS repetition, generates no scene, makes no API call and accesses no final-holdout result. The next authorized action is offline implementation and synthetic conformance of Bootstrap-BOSS aggregation. Study-scene execution remains forbidden.
""".encode("utf-8")

    audit = {
        "schema_version": "fourgraph.p1_evidence_selective_protocol_freeze.v1",
        "experiment_id": config["experiment"]["id"],
        "protocol_name": config["experiment"]["name"],
        "status": config["experiment"]["status"],
        "bundle_sha256": sha256_bytes(bundle_material),
        "dependencies": dependencies,
        "report": {
            "path": REPORT.relative_to(ROOT).as_posix(),
            "sha256": sha256_bytes(report),
        },
        "implementation": {
            "path": "scripts/freeze_p1_evidence_selective_protocol.py",
            "sha256": sha256(Path(__file__)),
        },
        "frozen_decisions": {
            "primary_statistical_method": "bootstrap_boss",
            "bootstrap_repetitions": 200,
            "bootstrap_sample_size": 2000,
            "semantic_model": "gpt-5.4-nano-2026-03-17",
            "semantic_call_granularity": "whole_graph",
            "semantic_prompt_variants": validation["prompt_ids"],
            "scd_ensemble": "deferred",
            "target_selective_error_alpha": 0.05,
            "failure_probability_delta": 0.05,
            "minimum_useful_coverage": 0.20,
        },
        "contracts": validation["schema_ids"],
        "evidence_boundary": {
            "bootstrap_implementation_exists": False,
            "bootstrap_runs_executed": 0,
            "scenes_generated": 0,
            "semantic_api_calls": 0,
            "old_development_or_validation_reanalyzed": False,
            "final_holdout_accessed": False,
        },
        "authorization": {
            "next_action": "P1_V3_BOOTSTRAP_BOSS_OFFLINE_IMPLEMENTATION_AND_CONFORMANCE",
            "study_scene_bootstrap_execution": False,
            "successor_cohort_generation": False,
            "semantic_api_calls": False,
            "final_holdout_access": False,
        },
        "verdict": {
            "protocol_frozen": True,
            "p1_v3_implementation_authorized": True,
            "p1_v3_study_execution_authorized": False,
            "final_holdout_execution_authorized": False,
        },
    }
    return canonical_json(audit), report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    audit, report = build()
    outputs = ((AUDIT, audit), (REPORT, report))
    if args.check:
        for path, expected in outputs:
            if not path.exists() or path.read_bytes() != expected:
                raise SystemExit(f"Mismatch: {path.relative_to(ROOT)}")
        print("P1-v3 Evidence-Selective protocol reproduces byte-for-byte")
        return 0
    for path, content in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    print("P1-v3 Evidence-Selective protocol frozen; execution remains sealed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

