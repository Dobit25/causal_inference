from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

import yaml

from fourgraph.semantic_reliability import (
    PROMPT_IDS,
    RequestedPair,
    SemanticReliabilityContractError,
    aggregate_six_prompt_responses,
    apply_statistical_veto,
    build_empirical_reliability_records,
    proposed_direction,
    validate_whole_graph_response,
)
from fourgraph.semantic_reliability_reference import reference_agreement, reference_veto


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v3_semantic_veto_conformance.yaml"
SEMANTIC = ROOT / "data/manifests/p1_v3_semantic_agreement_conformance.jsonl"
RELIABILITY = ROOT / "data/manifests/p1_v3_empirical_reliability_conformance.jsonl"
VETO = ROOT / "data/manifests/p1_v3_statistical_veto_conformance.jsonl"
INVALID = ROOT / "data/manifests/p1_v3_semantic_invalid.jsonl"
AUDIT = ROOT / "data/manifests/p1_v3_semantic_veto_conformance_audit.json"
REPORT = ROOT / "reports/p1_v3_semantic_veto_conformance.md"

HASH = "A" * 64
PAIRS = (
    RequestedPair("pair-1", "Amber index", "Beryl index", "X000", "X001"),
    RequestedPair("pair-2", "Cobalt index", "Dune index", "X002", "X003"),
)

PATTERNS = {
    "very_high_A_to_B": ["A_TO_B"] * 6,
    "very_high_B_to_A": ["B_TO_A"] * 6,
    "high_A_to_B": ["A_TO_B"] * 5 + ["UNDETERMINED"],
    "high_B_to_A": ["B_TO_A"] * 5 + ["UNDETERMINED"],
    "medium_A_to_B": ["A_TO_B"] * 4 + ["UNDETERMINED"] * 2,
    "medium_B_to_A": ["B_TO_A"] * 4 + ["UNDETERMINED"] * 2,
    "uncertain_A_to_B": ["A_TO_B"] * 3 + ["UNDETERMINED"] * 3,
    "uncertain_all": ["UNDETERMINED"] * 6,
    "conflict_5_to_1": ["A_TO_B"] * 5 + ["B_TO_A"],
    "conflict_3_to_3": ["A_TO_B"] * 3 + ["B_TO_A"] * 3,
}


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def jsonl(rows: list[dict]) -> bytes:
    return b"".join(canonical_json(row) + b"\n" for row in rows)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def direction_clause(pair: RequestedPair, label: str) -> str:
    source, target = (
        (pair.left_alias, pair.right_alias)
        if label == "A_TO_B"
        else (pair.right_alias, pair.left_alias)
    )
    return f"Within this process, changes in {source} directly influence {target}."


def symmetric_clause(pair: RequestedPair) -> str:
    left, right = sorted((pair.left_alias, pair.right_alias))
    return (
        f"{left} and {right} are directly connected in the process, "
        "but this description does not establish which one influences the other."
    )


def story_for_patterns(patterns: list[list[str]]) -> str:
    clauses: list[str] = []
    for pair, labels in zip(PAIRS, patterns):
        if "A_TO_B" in labels:
            clauses.append(direction_clause(pair, "A_TO_B"))
        if "B_TO_A" in labels:
            clauses.append(direction_clause(pair, "B_TO_A"))
        if all(label == "UNDETERMINED" for label in labels):
            clauses.append(symmetric_clause(pair))
    return " ".join(clauses)


def judgment(pair: RequestedPair, label: str) -> dict:
    if label == "UNDETERMINED":
        return {
            "pair_id": pair.pair_id, "judgment": "undetermined",
            "cause": None, "effect": None, "evidence_quote": None,
        }
    cause, effect = (
        (pair.left_alias, pair.right_alias)
        if label == "A_TO_B"
        else (pair.right_alias, pair.left_alias)
    )
    return {
        "pair_id": pair.pair_id, "judgment": "directed",
        "cause": cause, "effect": effect,
        "evidence_quote": direction_clause(pair, label),
    }


def responses_for_patterns(patterns: list[list[str]]) -> dict[str, dict]:
    return {
        prompt_id: {
            "schema_version": "fourgraph.semantic_whole_graph_response.v1",
            "judgments": [judgment(pair, patterns[pair_index][prompt_index]) for pair_index, pair in enumerate(PAIRS)],
        }
        for prompt_index, prompt_id in enumerate(PROMPT_IDS)
    }


def build_semantic_cases(config: dict) -> tuple[list[dict], dict[tuple[str, str], dict]]:
    rows: list[dict] = []
    lookup: dict[tuple[str, str], dict] = {}
    names = list(PATTERNS)
    variants = config["suite"]["story_variants"]
    for case_index in range(config["suite"]["semantic_cases"]):
        first_name = names[case_index % len(names)]
        second_name = names[(case_index + 3) % len(names)]
        patterns = [PATTERNS[first_name], PATTERNS[second_name]]
        story = story_for_patterns(patterns)
        variant = variants[case_index % len(variants)]
        responses = responses_for_patterns(patterns)
        records = aggregate_six_prompt_responses(
            scene_id=f"SEMSYN{case_index:03d}", story_variant=variant,
            story=story, requested_pairs=PAIRS, responses=responses,
            prompt_bundle_sha256=config["protocol"]["prompt_bundle_sha256"],
            story_sha256=sha256_bytes(story.encode("utf-8")),
            requested_pairs_sha256=sha256_bytes(canonical_json([pair.__dict__ for pair in PAIRS])),
            response_schema_sha256=config["protocol"]["response_schema_sha256"],
        )
        expected = []
        for pair_index, (name, record) in enumerate(zip((first_name, second_name), records)):
            expected_class, expected_direction = reference_agreement(patterns[pair_index])
            if record["agreement_class"] != expected_class or proposed_direction(record) != expected_direction:
                raise RuntimeError("Production/reference semantic agreement mismatch")
            expected.append({"pattern": name, "agreement_class": expected_class, "direction": expected_direction})
            if expected_direction is not None:
                lookup.setdefault((expected_class, expected_direction), record)
        rows.append(
            {
                "schema_version": "fourgraph.semantic_agreement_conformance_case.v1",
                "case_id": f"SEMSYN{case_index:03d}",
                "story_variant": variant,
                "story_sha256": sha256_bytes(story.encode("utf-8")),
                "patterns": [first_name, second_name],
                "expected": expected,
                "semantic_records": records,
                "production_reference_agreement": True,
            }
        )
    return rows, lookup


def build_reliability(config: dict) -> list[dict]:
    correct_targets = {
        ("full", "very_high"): 29, ("full", "high"): 27, ("full", "medium"): 23,
        ("partial", "very_high"): 28, ("partial", "high"): 25, ("partial", "medium"): 21,
        ("ambiguous", "very_high"): 25, ("ambiguous", "high"): 21, ("ambiguous", "medium"): 18,
    }
    outcomes = []
    for (variant, agreement), correct_target in sorted(correct_targets.items()):
        for index in range(30):
            oracle = "A_TO_B" if index < correct_target else "nonedge" if index % 2 else "B_TO_A"
            outcomes.append(
                {
                    "scene_id": f"CAL_{variant}_{agreement}_{index:02d}",
                    "story_variant": variant,
                    "agreement_class": agreement,
                    "published_direction": "A_TO_B",
                    "oracle_relation": oracle,
                }
            )
    records = build_empirical_reliability_records(
        outcomes, calibration_manifest_sha256=sha256_bytes(canonical_json(outcomes))
    )
    for record in records:
        expected = correct_targets[(record["story_variant"], record["agreement_class"])]
        if record["correct"] != expected or record["total"] != 30:
            raise RuntimeError("Reliability count disagreement")
        if record["certification_status"] != "pending_risk_control":
            raise RuntimeError("Diagnostic reliability self-certified")
    return records


def reliability_fixture(variant: str, agreement: str, status: str) -> dict:
    return {
        "schema_version": "fourgraph.empirical_reliability.v1",
        "story_variant": variant, "agreement_class": agreement,
        "correct": 30, "total": 30, "independent_scenes": 30,
        "point_estimate": 1.0, "diagnostic_wilson_lower_95": 0.9178,
        "false_adjacencies_count_as_errors": True,
        "certification_status": status, "calibration_manifest_sha256": HASH,
    }


def build_veto_cases(lookup: dict[tuple[str, str], dict]) -> list[dict]:
    statuses = (
        "weak_adjacency", "absent", "unavailable", "direction_uncertain",
        "statistical_direction_A_to_B", "statistical_direction_B_to_A",
    )
    safe_a = lookup[("very_high", "A_TO_B")]
    safe_b = lookup[("very_high", "B_TO_A")]
    pending_a = lookup[("high", "A_TO_B")]
    medium_a = lookup[("medium", "A_TO_B")]
    scenarios = (
        ("none", None, None),
        ("safe_A", safe_a, reliability_fixture(safe_a["story_variant"], "very_high", "certified_safe")),
        ("safe_B", safe_b, reliability_fixture(safe_b["story_variant"], "very_high", "certified_safe")),
        ("pending_A", pending_a, reliability_fixture(pending_a["story_variant"], "high", "pending_risk_control")),
        ("medium_A", medium_a, reliability_fixture(medium_a["story_variant"], "medium", "pending_risk_control")),
        ("conflict", {**safe_a, "votes": {"A_to_B": 3, "B_to_A": 3, "undetermined": 0, "total": 6}, "agreement_class": "conflict"}, None),
    )
    rows = []
    for status in statuses:
        for scenario_name, semantic, reliability in scenarios:
            statistical = {
                "edge": semantic["edge"] if semantic is not None else ["X000", "X001"],
                "status": status,
            }
            decision = apply_statistical_veto(statistical, semantic, reliability)
            direction = proposed_direction(semantic) if semantic is not None else None
            certified = reliability is not None and reliability["certification_status"] == "certified_safe"
            expected = reference_veto(
                status,
                semantic["agreement_class"] if semantic is not None else None,
                direction,
                certified,
            )
            observed = (decision["decision"], decision["direction"], decision["source"])
            if observed != expected:
                raise RuntimeError(f"Production/reference veto mismatch: {status}/{scenario_name}")
            rows.append(
                {
                    "schema_version": "fourgraph.statistical_veto_conformance_case.v1",
                    "case_id": f"VETO{len(rows):03d}",
                    "statistical_status": status,
                    "semantic_scenario": scenario_name,
                    "expected": {"decision": expected[0], "direction": expected[1], "source": expected[2]},
                    "decision": decision,
                    "production_reference_agreement": True,
                }
            )
    return rows


def build_invalid() -> list[dict]:
    pair = PAIRS[0]
    base_story = " ".join((direction_clause(pair, "A_TO_B"), symmetric_clause(pair)))
    base = {
        "schema_version": "fourgraph.semantic_whole_graph_response.v1",
        "judgments": [judgment(pair, "A_TO_B")],
    }
    fixture_types = (
        "extra_root", "missing_pair", "duplicate_pair", "unknown_pair",
        "wrong_alias", "quote_not_exact", "association_quote", "quote_direction_mismatch",
    )
    rows = []
    for index in range(48):
        kind = fixture_types[index % len(fixture_types)]
        broken = copy.deepcopy(base)
        if kind == "extra_root":
            broken["extra"] = True
        elif kind == "missing_pair":
            broken["judgments"] = []
        elif kind == "duplicate_pair":
            broken["judgments"].append(copy.deepcopy(broken["judgments"][0]))
        elif kind == "unknown_pair":
            broken["judgments"][0]["pair_id"] = "unknown"
        elif kind == "wrong_alias":
            broken["judgments"][0]["cause"] = "Unknown index"
        elif kind == "quote_not_exact":
            broken["judgments"][0]["evidence_quote"] += " extra"
        elif kind == "association_quote":
            broken["judgments"][0]["evidence_quote"] = symmetric_clause(pair)
        elif kind == "quote_direction_mismatch":
            broken["judgments"][0]["cause"] = pair.right_alias
            broken["judgments"][0]["effect"] = pair.left_alias
        rejected = False
        error = ""
        try:
            validate_whole_graph_response(broken, [pair], base_story)
        except SemanticReliabilityContractError as exc:
            rejected, error = True, str(exc)
        if not rejected:
            raise RuntimeError(f"Invalid semantic fixture accepted: {kind}")
        rows.append(
            {
                "schema_version": "fourgraph.semantic_invalid_fixture.v1",
                "fixture_id": f"SEMINVALID{index:03d}",
                "fixture_type": kind, "rejected": True, "error": error,
            }
        )
    return rows


def build() -> tuple[bytes, bytes, bytes, bytes, bytes, bytes]:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for key in ("audit",):
        path = ROOT / config["parent"][key]
        if sha256(path) != config["parent"][f"{key}_sha256"]:
            raise RuntimeError("Parent audit hash mismatch")
    for key in ("config", "prompt_bundle", "response_schema"):
        path = ROOT / config["protocol"][key]
        if sha256(path) != config["protocol"][f"{key}_sha256"]:
            raise RuntimeError(f"Protocol dependency hash mismatch: {key}")
    parent = json.loads((ROOT / config["parent"]["audit"]).read_text(encoding="utf-8"))
    if parent["authorization"]["next_action"] != config["task"]:
        raise RuntimeError("Parent audit does not authorize this task")

    semantic_rows, lookup = build_semantic_cases(config)
    reliability_rows = build_reliability(config)
    veto_rows = build_veto_cases(lookup)
    invalid_rows = build_invalid()
    if len(semantic_rows) != 90 or sum(len(row["semantic_records"]) for row in semantic_rows) != 180:
        raise RuntimeError("Semantic suite cardinality mismatch")
    if len(reliability_rows) != 9 or len(veto_rows) != 36 or len(invalid_rows) != 48:
        raise RuntimeError("Conformance output cardinality mismatch")
    vote_counts = Counter(
        key
        for row in semantic_rows
        for record in row["semantic_records"]
        for key, count in record["votes"].items()
        if key != "total"
        for _ in range(count)
    )
    directed_quote_count = vote_counts["A_to_B"] + vote_counts["B_to_A"]
    undetermined_count = vote_counts["undetermined"]
    if directed_quote_count != 810 or undetermined_count != 270:
        raise RuntimeError("Evidence-validator coverage mismatch")

    semantic_bytes, reliability_bytes = jsonl(semantic_rows), jsonl(reliability_rows)
    veto_bytes, invalid_bytes = jsonl(veto_rows), jsonl(invalid_rows)
    report = f"""# P1-v3 semantic reliability and statistical-veto offline conformance

Implemented strict whole-graph response parsing, exact-story directional-quote validation, deterministic normalization, six-vote agreement classes, empirical-reliability group records and the frozen statistical-veto decision table.

The suite contains {len(semantic_rows)} synthetic whole-graph cases and 180 edge records. Production classifications agreed with an independent reference on 180/180 edges. Across the six prompts, the validator accepted {directed_quote_count} exact directional quotes and {undetermined_count} correctly null evidence fields; {len(invalid_rows)}/{len(invalid_rows)} malformed responses failed closed. Nine reliability groups reproduced expected correct/total counts, included false adjacencies as errors and remained `pending_risk_control`; diagnostic point estimates never self-certified a group. The production/reference veto table agreed on {len(veto_rows)}/{len(veto_rows)} cases.

No model/API call, Bootstrap/BOSS run, study observation, historical cohort, successor scene, Oracle loader or final holdout was accessed. The next authorized step is prospective power and cohort design; study execution remains forbidden.
""".encode("utf-8")
    outputs = (
        (SEMANTIC, semantic_bytes), (RELIABILITY, reliability_bytes),
        (VETO, veto_bytes), (INVALID, invalid_bytes), (REPORT, report),
    )
    dependencies = [
        CONFIG,
        ROOT / config["parent"]["audit"],
        ROOT / config["protocol"]["config"],
        ROOT / config["protocol"]["prompt_bundle"],
        ROOT / config["protocol"]["response_schema"],
        ROOT / "schemas/semantic_edge_evidence_v1.schema.json",
        ROOT / "schemas/empirical_reliability_v1.schema.json",
        ROOT / "schemas/statistical_veto_decision_v1.schema.json",
        ROOT / "src/fourgraph/semantic_reliability.py",
        ROOT / "src/fourgraph/semantic_reliability_reference.py",
    ]
    audit = {
        "schema_version": "fourgraph.p1_v3_semantic_veto_conformance_audit.v1",
        "task": config["task"],
        "dependencies": [
            {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path)}
            for path in dependencies
        ],
        "implementation": {
            "path": "scripts/build_p1_v3_semantic_veto_conformance.py",
            "sha256": sha256(Path(__file__)),
        },
        "counts": {
            "semantic_cases": len(semantic_rows),
            "semantic_edge_records": 180,
            "production_reference_vote_agreements": 180,
            "valid_directional_evidence_quotes": directed_quote_count,
            "valid_undetermined_null_evidence_records": undetermined_count,
            "reliability_outcomes": 270,
            "reliability_groups": len(reliability_rows),
            "reliability_count_agreements": len(reliability_rows),
            "veto_decisions": len(veto_rows),
            "production_reference_veto_agreements": len(veto_rows),
            "invalid_responses_rejected": len(invalid_rows),
        },
        "outputs": [
            {"path": path.relative_to(ROOT).as_posix(), "bytes": len(content), "sha256": sha256_bytes(content)}
            for path, content in outputs
        ],
        "evidence_boundary": config["evidence_boundary"],
        "authorization": config["authorization_after_pass"],
        "verdict": {
            "offline_semantic_layer_complete": True,
            "synthetic_conformance_passed": True,
            "reliability_self_certification_allowed": False,
            "study_scene_bootstrap_execution_authorized": False,
            "successor_cohort_generation_authorized": False,
            "semantic_api_calls_authorized": False,
            "final_holdout_access_authorized": False,
        },
    }
    return semantic_bytes, reliability_bytes, veto_bytes, invalid_bytes, canonical_json(audit) + b"\n", report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    built = build()
    paths = (SEMANTIC, RELIABILITY, VETO, INVALID, AUDIT, REPORT)
    if args.check:
        for path, expected in zip(paths, built):
            if not path.exists() or path.read_bytes() != expected:
                raise SystemExit(f"Mismatch: {path.relative_to(ROOT)}")
        print("Semantic reliability/veto conformance reproduces byte-for-byte")
        return 0
    for path, content in zip(paths, built):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    print("Semantic reliability and statistical veto passed offline conformance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
