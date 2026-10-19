"""Independently structured reference for the sentence-ID contract."""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence

from fourgraph.p1_stories import DIRECTIONAL_CLAUSE, SYMMETRIC_CLAUSE


def split_story(text: str) -> list[tuple[str, str]]:
    chunks = [chunk.strip() for chunk in text.split(".") if chunk.strip()]
    return [(f"S{i:03d}", chunk + ".") for i, chunk in enumerate(chunks, 1)]


def reference_validate(row: object, pair: Mapping[str, str], story: str) -> dict[str, object]:
    bad = lambda code: {"pair_id": pair["pair_id"], "pair_valid": False,
                        "validator_status": code, "direction": None}
    fields = {"pair_id", "status", "cause", "effect", "evidence_sentence_ids"}
    if not isinstance(row, Mapping) or set(row) != fields or row.get("pair_id") != pair["pair_id"]:
        return bad("INVALID_SCHEMA")
    status = row.get("status")
    if status not in {"DIRECTED", "NO_DIRECT_DIRECTION_EVIDENCE", "PROCESSING_UNCERTAIN"}:
        return bad("INVALID_SCHEMA")
    ids = row.get("evidence_sentence_ids")
    if not isinstance(ids, list) or len(ids) > 3 or len(ids) != len(set(ids)) or any(not isinstance(x, str) for x in ids):
        return bad("INVALID_SCHEMA")
    sentences = dict(split_story(story))
    if any(x not in sentences for x in ids) or ids != sorted(ids, key=lambda x: int(x[1:])):
        return bad("INVALID_EVIDENCE_ID")
    cause, effect = row.get("cause"), row.get("effect")
    if status == "DIRECTED":
        if not isinstance(cause, str) or not isinstance(effect, str) or cause == effect or {cause, effect} != {pair["A"], pair["B"]}:
            return bad("INVALID_MAPPING")
    elif cause is not None or effect is not None:
        return bad("INVALID_MAPPING")
    selected = [sentences[x] for x in ids]
    combined = " ".join(selected)
    relations = []
    for sid, sentence in split_story(story):
        direct, ambiguous = DIRECTIONAL_CLAUSE.fullmatch(sentence), SYMMETRIC_CLAUSE.fullmatch(sentence)
        if direct and set(direct.groups()) == {pair["A"], pair["B"]}:
            relations.append((sid, "D", direct.group(1), direct.group(2)))
        elif ambiguous and set(ambiguous.groups()) == {pair["A"], pair["B"]}:
            relations.append((sid, "U", None, None))
    chosen = [x for x in relations if x[0] in ids]
    if status in {"DIRECTED", "PROCESSING_UNCERTAIN"}:
        if not 1 <= len(ids) <= 3 or pair["A"] not in combined or pair["B"] not in combined:
            return bad("INVALID_EVIDENCE_ID")
    if status == "DIRECTED":
        directed = [x for x in chosen if x[1] == "D"]
        if not directed or any((x[2], x[3]) != (cause, effect) for x in directed) or any(x[1] == "U" for x in chosen):
            return bad("INVALID_DIRECTION_EVIDENCE")
        direction = "A_TO_B" if (cause, effect) == (pair["A"], pair["B"]) else "B_TO_A"
    elif status == "PROCESSING_UNCERTAIN":
        dirs = {(x[2], x[3]) for x in relations if x[1] == "D"}
        if not any(x[1] == "U" for x in chosen) and not (len(dirs) > 1 and any(x[1] == "D" for x in chosen)):
            return bad("INVALID_DIRECTION_EVIDENCE")
        direction = "UNDETERMINED"
    else:
        if ids:
            return bad("INVALID_EVIDENCE_ID")
        if relations:
            return bad("INVALID_FALSE_NO_EVIDENCE")
        direction = "UNDETERMINED"
    return {"pair_id": pair["pair_id"], "pair_valid": True, "validator_status": "VALID",
            "direction": direction}


def reference_aggregate(votes: Sequence[Mapping[str, object]], balanced: bool = True) -> dict[str, object]:
    if len(votes) != 6 or sorted(str(v["prompt_id"]) for v in votes) != [f"P{i}" for i in range(1, 7)]:
        raise ValueError("bad six-vote identities")
    usable = [v for v in votes if v.get("pair_valid") is True and v.get("validator_status") == "VALID"]
    counts = Counter(v.get("direction") for v in usable)
    left, right, undecided = counts["A_TO_B"], counts["B_TO_A"], counts["UNDETERMINED"]
    completeness = "COMPLETE" if len(usable) == 6 else "NEAR_COMPLETE" if len(usable) == 5 else "INCOMPLETE"
    if left and right:
        label = "CONFLICT"
    elif balanced:
        strongest = max(left, right)
        label = "VERY_HIGH" if strongest == 6 else "HIGH" if strongest == 5 else "MEDIUM" if strongest == 4 else "UNCERTAIN"
    elif len(usable) != 6:
        label = "NEAR_COMPLETE_DIAGNOSTIC_ONLY" if len(usable) == 5 else "INCOMPLETE_ABSTAIN"
    elif max(left, right) == 6:
        label = "VERY_HIGH"
    elif max(left, right) == 5 and undecided == 1:
        label = "HIGH"
    elif max(left, right) == 4 and undecided == 2:
        label = "MEDIUM"
    else:
        label = "UNCERTAIN"
    chosen = label in {"VERY_HIGH", "HIGH", "MEDIUM"}
    return {"valid_votes": len(usable), "completeness": completeness, "agreement": label,
            "automatic_candidate": label in {"VERY_HIGH", "HIGH"}, "review_candidate": label == "MEDIUM",
            "candidate_direction": "A_TO_B" if chosen and left > right else "B_TO_A" if chosen and right > left else None}
