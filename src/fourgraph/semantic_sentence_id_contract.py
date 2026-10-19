"""Sentence-ID semantic extraction and coverage-oriented six-vote contract.

The module is provider-free. It exposes only public aliases and public story
text. Oracle relations are deliberately outside this validation boundary.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Mapping, Sequence

from fourgraph.p1_stories import DIRECTIONAL_CLAUSE, SYMMETRIC_CLAUSE
from fourgraph.semantic_pair_contract_v2 import StablePair, validate_pairs

RESPONSE_SCHEMA = "fourgraph.semantic_sentence_id_response.v1"
PROMPT_IDS = ("P1", "P2", "P3", "P4", "P5", "P6")
STATUSES = ("DIRECTED", "NO_DIRECT_DIRECTION_EVIDENCE", "PROCESSING_UNCERTAIN")
FIELDS = {"pair_id", "status", "cause", "effect", "evidence_sentence_ids"}

QUERY_VARIANTS = {
    "P1": "Inspect node_a before node_b and identify direct cause/effect evidence.",
    "P2": "Inspect node_b before node_a; still return the actual public cause and effect.",
    "P3": "Locate numbered direct-pair evidence before deciding direction or abstention.",
    "P4": "Review the requested pair in reverse presentation order and identify actual causal roles.",
    "P5": "Assign cause/effect only when the numbered story directly establishes those roles.",
    "P6": "Check node_b before node_a and distinguish directed, ambiguous, and absent evidence.",
}


@dataclass(frozen=True)
class NumberedSentence:
    sentence_id: str
    text: str


def number_story(story: str) -> tuple[NumberedSentence, ...]:
    if not isinstance(story, str) or not story.strip():
        raise ValueError("story must be non-empty")
    parts = [part.strip() + "." for part in story.split(".") if part.strip()]
    return tuple(NumberedSentence(f"S{index:03d}", text) for index, text in enumerate(parts, 1))


def render_sentence_id_prompt(*, prompt_id: str, story: str,
                              pairs: Sequence[StablePair]) -> str:
    if prompt_id not in PROMPT_IDS:
        raise ValueError("unknown prompt variant")
    materialized = validate_pairs(pairs)
    sentences = number_story(story)
    numbered = "\n".join(f"[{row.sentence_id}] {row.text}" for row in sentences)
    public_pairs = [pair.public_record() for pair in materialized]
    instruction = (
        "Use only the numbered public story; do not use general world knowledge. "
        "For each requested pair return DIRECTED only when one requested public variable directly causes the other; "
        "return the public names verbatim as cause/effect. Return PROCESSING_UNCERTAIN for an explicit direct "
        "connection whose direction is ambiguous or conflicting. Return NO_DIRECT_DIRECTION_EVIDENCE when no direct "
        "pair evidence is supplied. DIRECTED and PROCESSING_UNCERTAIN must cite one to three unique "
        "evidence_sentence_ids in story order; their combined text must mention both variables. "
        "NO_DIRECT_DIRECTION_EVIDENCE requires null cause/effect and an empty evidence_sentence_ids array. "
        "Association, indirect paths, pair order and candidate adjacency do not establish direction. "
        "Return every pair_id exactly once and only the registered JSON schema."
    )
    return (
        f"{instruction}\n\nQUERY VARIANT {prompt_id}:\n{QUERY_VARIANTS[prompt_id]}\n\n"
        f"NUMBERED PUBLIC STORY:\n{numbered}\n\nSTABLE REQUESTED PAIRS:\n"
        + json.dumps(public_pairs, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _invalid(pair: StablePair, status: str, model_status: object = None) -> dict[str, object]:
    return {"pair_id": pair.pair_id, "pair_valid": False, "validator_status": status,
            "model_status": model_status, "direction": None, "cause": None, "effect": None,
            "evidence_sentence_ids": [], "evidence_texts": []}


def _relevant(sentences: Sequence[NumberedSentence], pair: StablePair) -> list[dict[str, object]]:
    wanted = {pair.node_a_alias, pair.node_b_alias}
    found: list[dict[str, object]] = []
    for row in sentences:
        directed = DIRECTIONAL_CLAUSE.fullmatch(row.text)
        if directed and {directed.group("source"), directed.group("target")} == wanted:
            found.append({"sentence_id": row.sentence_id, "kind": "directed",
                          "cause": directed.group("source"), "effect": directed.group("target")})
            continue
        symmetric = SYMMETRIC_CLAUSE.fullmatch(row.text)
        if symmetric and {symmetric.group("left"), symmetric.group("right")} == wanted:
            found.append({"sentence_id": row.sentence_id, "kind": "ambiguous",
                          "cause": None, "effect": None})
    return found


def validate_pair_judgment(row: object, pair: StablePair, story: str) -> dict[str, object]:
    if not isinstance(row, Mapping) or set(row) != FIELDS or row.get("pair_id") != pair.pair_id:
        return _invalid(pair, "INVALID_SCHEMA")
    status = row.get("status")
    if status not in STATUSES:
        return _invalid(pair, "INVALID_SCHEMA", status)
    cause, effect, ids = row.get("cause"), row.get("effect"), row.get("evidence_sentence_ids")
    if not isinstance(ids, list) or len(ids) > 3 or len(ids) != len(set(ids)) \
            or any(not isinstance(value, str) for value in ids):
        return _invalid(pair, "INVALID_SCHEMA", status)
    sentences = number_story(story)
    by_id = {item.sentence_id: item for item in sentences}
    if any(value not in by_id for value in ids):
        return _invalid(pair, "INVALID_EVIDENCE_ID", status)
    if ids != sorted(ids, key=lambda value: int(value[1:])):
        return _invalid(pair, "INVALID_EVIDENCE_ID", status)
    texts = [by_id[value].text for value in ids]
    combined = " ".join(texts)
    relevant = _relevant(sentences, pair)

    if status == "DIRECTED":
        if not isinstance(cause, str) or not isinstance(effect, str) or cause == effect \
                or {cause, effect} != {pair.node_a_alias, pair.node_b_alias}:
            return _invalid(pair, "INVALID_MAPPING", status)
        if not 1 <= len(ids) <= 3 or pair.node_a_alias not in combined or pair.node_b_alias not in combined:
            return _invalid(pair, "INVALID_EVIDENCE_ID", status)
        selected = [item for item in relevant if item["sentence_id"] in ids]
        directed = [item for item in selected if item["kind"] == "directed"]
        if not directed or any((item["cause"], item["effect"]) != (cause, effect) for item in directed):
            return _invalid(pair, "INVALID_DIRECTION_EVIDENCE", status)
        if any(item["kind"] == "ambiguous" for item in selected):
            return _invalid(pair, "INVALID_DIRECTION_EVIDENCE", status)
        direction = "A_TO_B" if (cause, effect) == (pair.node_a_alias, pair.node_b_alias) else "B_TO_A"
    elif status == "PROCESSING_UNCERTAIN":
        if cause is not None or effect is not None:
            return _invalid(pair, "INVALID_MAPPING", status)
        if not 1 <= len(ids) <= 3 or pair.node_a_alias not in combined or pair.node_b_alias not in combined:
            return _invalid(pair, "INVALID_EVIDENCE_ID", status)
        selected = [item for item in relevant if item["sentence_id"] in ids]
        directions = {(item["cause"], item["effect"]) for item in relevant if item["kind"] == "directed"}
        if not any(item["kind"] == "ambiguous" for item in selected) \
                and not (len(directions) > 1 and any(item["kind"] == "directed" for item in selected)):
            return _invalid(pair, "INVALID_DIRECTION_EVIDENCE", status)
        direction = "UNDETERMINED"
    else:
        if cause is not None or effect is not None:
            return _invalid(pair, "INVALID_MAPPING", status)
        if ids:
            return _invalid(pair, "INVALID_EVIDENCE_ID", status)
        if relevant:
            return _invalid(pair, "INVALID_FALSE_NO_EVIDENCE", status)
        direction = "UNDETERMINED"

    return {"pair_id": pair.pair_id, "pair_valid": True, "validator_status": "VALID",
            "model_status": status, "direction": direction, "cause": cause, "effect": effect,
            "evidence_sentence_ids": ids, "evidence_texts": texts}


def validate_response_by_pair(response: object, pairs: Sequence[StablePair], story: str) -> dict[str, object]:
    materialized = validate_pairs(pairs)
    if not isinstance(response, Mapping) or set(response) != {"schema_version", "judgments"} \
            or response.get("schema_version") != RESPONSE_SCHEMA or not isinstance(response.get("judgments"), list):
        records = [_invalid(pair, "INVALID_SCHEMA") for pair in materialized]
        return {"response_valid": False, "response_status": "INVALID_SCHEMA", "pairs": records}
    known = {pair.pair_id for pair in materialized}
    grouped: dict[str, list[object]] = defaultdict(list)
    unknown = False
    for row in response["judgments"]:
        if not isinstance(row, Mapping) or row.get("pair_id") not in known:
            unknown = True
        else:
            grouped[str(row["pair_id"])].append(row)
    records = []
    for pair in materialized:
        rows = grouped[pair.pair_id]
        records.append(validate_pair_judgment(rows[0], pair, story) if len(rows) == 1
                       else _invalid(pair, "INVALID_SCHEMA"))
    valid = not unknown and len(response["judgments"]) == len(materialized) \
        and all(item["pair_valid"] for item in records)
    return {"response_valid": valid, "response_status": "VALID" if valid else "PAIR_LEVEL_INVALID",
            "pairs": records}


def aggregate_six_votes(votes: Sequence[Mapping[str, object]], *, balanced: bool = True) -> dict[str, object]:
    if len(votes) != 6 or {vote.get("prompt_id") for vote in votes} != set(PROMPT_IDS):
        raise ValueError("six uniquely identified P1-P6 votes required")
    valid = [vote for vote in votes if vote.get("pair_valid") is True and vote.get("validator_status") == "VALID"]
    count = Counter(str(vote.get("direction")) for vote in valid)
    a, b, abstain = count["A_TO_B"], count["B_TO_A"], count["UNDETERMINED"]
    invalid = 6 - len(valid)
    completeness = "COMPLETE" if len(valid) == 6 else "NEAR_COMPLETE" if len(valid) == 5 else "INCOMPLETE"
    if a and b:
        agreement = "CONFLICT"
    elif balanced:
        strongest = max(a, b)
        agreement = "VERY_HIGH" if strongest == 6 else "HIGH" if strongest == 5 \
            else "MEDIUM" if strongest == 4 else "UNCERTAIN"
    elif completeness != "COMPLETE":
        agreement = "NEAR_COMPLETE_DIAGNOSTIC_ONLY" if completeness == "NEAR_COMPLETE" else "INCOMPLETE_ABSTAIN"
    elif max(a, b) == 6:
        agreement = "VERY_HIGH"
    elif max(a, b) == 5 and abstain == 1:
        agreement = "HIGH"
    elif max(a, b) == 4 and abstain == 2:
        agreement = "MEDIUM"
    else:
        agreement = "UNCERTAIN"
    auto = agreement in {"VERY_HIGH", "HIGH"}
    review = agreement == "MEDIUM"
    direction = "A_TO_B" if (auto or review) and a > b else "B_TO_A" if (auto or review) and b > a else None
    return {"valid_votes": len(valid), "invalid_votes": invalid, "completeness": completeness,
            "agreement": agreement, "vote_counts": {"A_TO_B": a, "B_TO_A": b,
            "UNDETERMINED": abstain, "INVALID": invalid}, "automatic_candidate": auto,
            "review_candidate": review, "candidate_direction": direction,
            "automatically_published": False}
