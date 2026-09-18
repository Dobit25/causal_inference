"""Offline semantic agreement, evidence validation and statistical veto logic."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from fourgraph.p1_stories import DIRECTIONAL_CLAUSE


RESPONSE_SCHEMA = "fourgraph.semantic_whole_graph_response.v1"
EVIDENCE_SCHEMA = "fourgraph.semantic_edge_evidence.v1"
RELIABILITY_SCHEMA = "fourgraph.empirical_reliability.v1"
VETO_SCHEMA = "fourgraph.statistical_veto_decision.v1"
PROMPT_IDS = ("P1", "P2", "P3", "P4", "P5", "P6")
AGREEMENT_CLASSES = ("very_high", "high", "medium", "uncertain", "conflict")
SAFE_CLASSES = ("very_high", "high")
HASH_PATTERN_LENGTH = 64


class SemanticReliabilityContractError(ValueError):
    """Raised when semantic or veto evidence violates the frozen contract."""


@dataclass(frozen=True)
class RequestedPair:
    pair_id: str
    left_alias: str
    right_alias: str
    left_node: str
    right_node: str

    def validate(self) -> None:
        values = (self.pair_id, self.left_alias, self.right_alias, self.left_node, self.right_node)
        if any(not isinstance(value, str) or not value for value in values):
            raise SemanticReliabilityContractError("requested-pair fields must be non-empty strings")
        if self.left_alias == self.right_alias or self.left_node >= self.right_node:
            raise SemanticReliabilityContractError("requested pair must use distinct aliases and canonical nodes")


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest().upper()


def _validate_hash(value: object, field: str) -> str:
    if not isinstance(value, str) or len(value) != HASH_PATTERN_LENGTH:
        raise SemanticReliabilityContractError(f"{field} must be a SHA-256 string")
    try:
        int(value, 16)
    except ValueError as exc:
        raise SemanticReliabilityContractError(f"{field} must be hexadecimal") from exc
    if value != value.upper():
        raise SemanticReliabilityContractError(f"{field} must use uppercase hex")
    return value


def validate_whole_graph_response(
    response: Mapping[str, object],
    requested_pairs: Sequence[RequestedPair],
    story: str,
) -> dict[str, str]:
    if not isinstance(story, str) or not story:
        raise SemanticReliabilityContractError("story must be non-empty text")
    if set(response) != {"schema_version", "judgments"}:
        raise SemanticReliabilityContractError("response root fields do not match contract")
    if response["schema_version"] != RESPONSE_SCHEMA:
        raise SemanticReliabilityContractError("response schema version mismatch")
    pairs: dict[str, RequestedPair] = {}
    for pair in requested_pairs:
        pair.validate()
        if pair.pair_id in pairs:
            raise SemanticReliabilityContractError("duplicate requested pair_id")
        pairs[pair.pair_id] = pair
    judgments = response["judgments"]
    if not isinstance(judgments, list):
        raise SemanticReliabilityContractError("judgments must be an array")
    if len(judgments) != len(pairs):
        raise SemanticReliabilityContractError("response must contain every requested pair exactly once")

    normalized: dict[str, str] = {}
    required = {"pair_id", "judgment", "cause", "effect", "evidence_quote"}
    for row in judgments:
        if not isinstance(row, Mapping) or set(row) != required:
            raise SemanticReliabilityContractError("judgment fields do not match contract")
        pair_id = row["pair_id"]
        if not isinstance(pair_id, str) or pair_id not in pairs or pair_id in normalized:
            raise SemanticReliabilityContractError("unknown or duplicate response pair_id")
        pair = pairs[pair_id]
        judgment = row["judgment"]
        if judgment == "undetermined":
            if any(row[field] is not None for field in ("cause", "effect", "evidence_quote")):
                raise SemanticReliabilityContractError("undetermined response fields must be null")
            normalized[pair_id] = "UNDETERMINED"
            continue
        if judgment != "directed":
            raise SemanticReliabilityContractError("judgment must be directed or undetermined")
        cause, effect, quote = row["cause"], row["effect"], row["evidence_quote"]
        if cause not in (pair.left_alias, pair.right_alias) or effect not in (
            pair.left_alias, pair.right_alias
        ) or cause == effect:
            raise SemanticReliabilityContractError("cause/effect do not match requested aliases")
        if not isinstance(quote, str) or not quote or quote not in story:
            raise SemanticReliabilityContractError("directed evidence quote must be an exact story substring")
        if pair.left_alias not in quote or pair.right_alias not in quote:
            raise SemanticReliabilityContractError("evidence quote must mention both requested aliases")
        directional = DIRECTIONAL_CLAUSE.fullmatch(quote)
        if directional is None:
            raise SemanticReliabilityContractError("association-only or malformed quote cannot support direction")
        if directional.group("source") != cause or directional.group("target") != effect:
            raise SemanticReliabilityContractError("cause/effect conflict with evidence quote")
        normalized[pair_id] = "A_TO_B" if cause == pair.left_alias else "B_TO_A"
    if set(normalized) != set(pairs):
        raise SemanticReliabilityContractError("response pair coverage mismatch")
    return normalized


def classify_vote_counts(a_to_b: int, b_to_a: int, undetermined: int) -> tuple[str, str | None]:
    counts = (a_to_b, b_to_a, undetermined)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts):
        raise SemanticReliabilityContractError("vote counts must be non-negative integers")
    if sum(counts) != 6:
        raise SemanticReliabilityContractError("six-vote classifier requires exactly six votes")
    if a_to_b and b_to_a:
        return "conflict", None
    winning = "A_TO_B" if a_to_b else "B_TO_A" if b_to_a else None
    maximum = max(a_to_b, b_to_a)
    if maximum == 6:
        return "very_high", winning
    if maximum == 5 and undetermined == 1:
        return "high", winning
    if maximum == 4 and undetermined == 2:
        return "medium", winning
    return "uncertain", winning


def aggregate_six_prompt_responses(
    *,
    scene_id: str,
    story_variant: str,
    story: str,
    requested_pairs: Sequence[RequestedPair],
    responses: Mapping[str, Mapping[str, object]],
    prompt_bundle_sha256: str,
    story_sha256: str,
    requested_pairs_sha256: str,
    response_schema_sha256: str,
) -> list[dict[str, object]]:
    if story_variant not in ("full", "partial", "ambiguous"):
        raise SemanticReliabilityContractError("invalid story variant")
    if tuple(responses) != PROMPT_IDS:
        raise SemanticReliabilityContractError("responses must contain ordered P1..P6")
    for field, value in (
        ("prompt_bundle_sha256", prompt_bundle_sha256),
        ("story_sha256", story_sha256),
        ("requested_pairs_sha256", requested_pairs_sha256),
        ("response_schema_sha256", response_schema_sha256),
    ):
        _validate_hash(value, field)
    normalized = {
        prompt_id: validate_whole_graph_response(response, requested_pairs, story)
        for prompt_id, response in responses.items()
    }
    records: list[dict[str, object]] = []
    for pair in requested_pairs:
        labels = [normalized[prompt_id][pair.pair_id] for prompt_id in PROMPT_IDS]
        votes = {
            "A_to_B": labels.count("A_TO_B"),
            "B_to_A": labels.count("B_TO_A"),
            "undetermined": labels.count("UNDETERMINED"),
            "total": 6,
        }
        agreement, _ = classify_vote_counts(
            votes["A_to_B"], votes["B_to_A"], votes["undetermined"]
        )
        records.append(
            {
                "schema_version": EVIDENCE_SCHEMA,
                "scene_id": scene_id,
                "story_variant": story_variant,
                "edge": [pair.left_node, pair.right_node],
                "votes": votes,
                "agreement_class": agreement,
                "evidence_validation": {
                    "all_directed_quotes_exact": True,
                    "aliases_match": True,
                    "cause_effect_match": True,
                    "association_guard_passed": True,
                },
                "empirical_reliability": None,
                "provenance": {
                    "model_snapshot": "gpt-5.4-nano-2026-03-17",
                    "prompt_bundle_sha256": prompt_bundle_sha256,
                    "story_sha256": story_sha256,
                    "requested_pairs_sha256": requested_pairs_sha256,
                    "response_schema_sha256": response_schema_sha256,
                },
            }
        )
    return records


def proposed_direction(semantic_record: Mapping[str, object]) -> str | None:
    votes = semantic_record["votes"]
    agreement, direction = classify_vote_counts(
        votes["A_to_B"], votes["B_to_A"], votes["undetermined"]
    )
    if agreement != semantic_record["agreement_class"]:
        raise SemanticReliabilityContractError("agreement class does not match vote counts")
    return direction


def _wilson_lower(correct: int, total: int, z: float = 1.6448536269514722) -> float:
    if total <= 0:
        raise SemanticReliabilityContractError("reliability group must be non-empty")
    point = correct / total
    z2 = z * z
    center = point + z2 / (2 * total)
    margin = z * math.sqrt(point * (1 - point) / total + z2 / (4 * total * total))
    return max(0.0, (center - margin) / (1 + z2 / total))


def build_empirical_reliability_records(
    outcomes: Iterable[Mapping[str, object]],
    *,
    calibration_manifest_sha256: str,
) -> list[dict[str, object]]:
    _validate_hash(calibration_manifest_sha256, "calibration_manifest_sha256")
    groups: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in outcomes:
        required = {
            "scene_id", "story_variant", "agreement_class", "published_direction",
            "oracle_relation",
        }
        if set(row) != required:
            raise SemanticReliabilityContractError("calibration outcome fields mismatch")
        if row["story_variant"] not in ("full", "partial", "ambiguous"):
            raise SemanticReliabilityContractError("invalid calibration story variant")
        if row["agreement_class"] not in ("very_high", "high", "medium"):
            raise SemanticReliabilityContractError("calibration requires a publishable majority class")
        if row["published_direction"] not in ("A_TO_B", "B_TO_A"):
            raise SemanticReliabilityContractError("published direction missing")
        if row["oracle_relation"] not in ("A_TO_B", "B_TO_A", "nonedge"):
            raise SemanticReliabilityContractError("invalid Oracle relation")
        groups[(row["story_variant"], row["agreement_class"])].append(row)

    records: list[dict[str, object]] = []
    for (variant, agreement), rows in sorted(groups.items()):
        correct = sum(row["published_direction"] == row["oracle_relation"] for row in rows)
        total = len(rows)
        scenes = len({row["scene_id"] for row in rows})
        records.append(
            {
                "schema_version": RELIABILITY_SCHEMA,
                "story_variant": variant,
                "agreement_class": agreement,
                "correct": correct,
                "total": total,
                "independent_scenes": scenes,
                "point_estimate": correct / total,
                "diagnostic_wilson_lower_95": _wilson_lower(correct, total),
                "false_adjacencies_count_as_errors": True,
                "certification_status": "pending_risk_control",
                "calibration_manifest_sha256": calibration_manifest_sha256,
            }
        )
    return records


def validate_reliability_record(record: Mapping[str, object]) -> None:
    required = {
        "schema_version", "story_variant", "agreement_class", "correct", "total",
        "independent_scenes", "point_estimate", "diagnostic_wilson_lower_95",
        "false_adjacencies_count_as_errors", "certification_status",
        "calibration_manifest_sha256",
    }
    if set(record) != required or record["schema_version"] != RELIABILITY_SCHEMA:
        raise SemanticReliabilityContractError("reliability record fields mismatch")
    if record["story_variant"] not in ("full", "partial", "ambiguous"):
        raise SemanticReliabilityContractError("invalid reliability variant")
    if record["agreement_class"] not in ("very_high", "high", "medium"):
        raise SemanticReliabilityContractError("invalid reliability agreement class")
    correct, total, scenes = record["correct"], record["total"], record["independent_scenes"]
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (correct, total, scenes)):
        raise SemanticReliabilityContractError("reliability counts must be integers")
    if not (0 <= correct <= total and total > 0 and scenes > 0):
        raise SemanticReliabilityContractError("invalid reliability counts")
    if not math.isclose(record["point_estimate"], correct / total, abs_tol=1e-12):
        raise SemanticReliabilityContractError("reliability point estimate mismatch")
    if not 0 <= record["diagnostic_wilson_lower_95"] <= record["point_estimate"] <= 1:
        raise SemanticReliabilityContractError("invalid reliability diagnostic bound")
    if record["false_adjacencies_count_as_errors"] is not True:
        raise SemanticReliabilityContractError("false adjacencies must count as errors")
    if record["certification_status"] not in (
        "pending_risk_control", "certified_safe", "not_certified"
    ):
        raise SemanticReliabilityContractError("invalid reliability certification status")
    _validate_hash(record["calibration_manifest_sha256"], "calibration_manifest_sha256")


def apply_statistical_veto(
    statistical_record: Mapping[str, object],
    semantic_record: Mapping[str, object] | None,
    reliability_record: Mapping[str, object] | None,
) -> dict[str, object]:
    status = statistical_record.get("status")
    edge = statistical_record.get("edge")
    if not isinstance(edge, list) or len(edge) != 2 or edge[0] >= edge[1]:
        raise SemanticReliabilityContractError("statistical edge must be canonical")
    allowed_status = {
        "weak_adjacency", "absent", "unavailable", "direction_uncertain",
        "statistical_direction_A_to_B", "statistical_direction_B_to_A",
    }
    if status not in allowed_status:
        raise SemanticReliabilityContractError("unsupported statistical status")

    semantic_direction = None
    agreement = None
    certified = False
    if semantic_record is not None:
        if semantic_record.get("edge") != edge:
            raise SemanticReliabilityContractError("statistical/semantic edge mismatch")
        agreement = semantic_record.get("agreement_class")
        semantic_direction = proposed_direction(semantic_record)
    if reliability_record is not None:
        validate_reliability_record(reliability_record)
        if semantic_record is None:
            raise SemanticReliabilityContractError("reliability supplied without semantic evidence")
        if reliability_record["story_variant"] != semantic_record["story_variant"] or reliability_record[
            "agreement_class"
        ] != agreement:
            raise SemanticReliabilityContractError("reliability group does not match semantic evidence")
        certified = reliability_record["certification_status"] == "certified_safe"

    decision = "undirected"
    direction = None
    source = "unresolved"
    veto_passed = False
    reason = "insufficient_evidence"
    if status in ("weak_adjacency", "absent"):
        decision, source, reason = "excluded", "statistical_veto", "adjacency_below_threshold"
    elif status == "unavailable":
        decision, source, reason = "unavailable", "method_failure", "statistical_method_unavailable"
    elif status == "direction_uncertain":
        veto_passed = True
        if agreement in SAFE_CLASSES and certified and semantic_direction is not None:
            decision, direction, source, reason = (
                "directed", semantic_direction, "semantic_selected", "safe_semantic_direction"
            )
        elif agreement == "conflict":
            source, reason = "conflict_abstained", "semantic_internal_conflict"
    else:
        veto_passed = True
        statistical_direction = (
            "A_TO_B" if status == "statistical_direction_A_to_B" else "B_TO_A"
        )
        if agreement == "conflict":
            source, reason = "conflict_abstained", "semantic_internal_conflict"
        elif agreement in SAFE_CLASSES and certified and semantic_direction is not None:
            if semantic_direction == statistical_direction:
                decision, direction, source, reason = (
                    "directed", statistical_direction, "statistical_semantic_agreement",
                    "safe_semantic_confirmation",
                )
            else:
                source, reason = "conflict_abstained", "safe_semantic_statistical_conflict"
        else:
            decision, direction, source, reason = (
                "directed", statistical_direction, "statistical_stable",
                "semantic_evidence_not_certified_to_override",
            )

    result: dict[str, object] = {
        "schema_version": VETO_SCHEMA,
        "edge": edge,
        "statistical_status": status,
        "semantic_agreement_class": agreement,
        "semantic_reliability_certified": certified,
        "decision": decision,
        "direction": direction,
        "source": source,
        "statistical_veto_passed": veto_passed,
        "reason": reason,
    }
    result["decision_sha256"] = _sha256(result)
    return result

