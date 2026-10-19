"""Deterministic valid-method ensemble rule for the P1V4 calibration runner."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


METHODS = ("Single-BOSS", "Bootstrap-BOSS", "PC", "MMPC", "FGES")
Edge = tuple[str, str]


@dataclass(frozen=True)
class EnsembleDecision:
    status: str
    valid_methods: tuple[str, ...]
    invalid_methods: tuple[str, ...]
    denominator: int | None
    threshold: int | None
    allowed_edges: frozenset[Edge]


def decide_valid_method_ensemble(votes: Mapping[str, set[Edge] | None]) -> EnsembleDecision:
    """Apply 3/5 normally and 3/4 only with exactly one invalid method.

    ``None`` is an invalid/no-vote method, never a vote for adjacency.  Two or
    more invalid methods fail closed; no lower denominator is permitted.
    """
    if set(votes) != set(METHODS):
        raise ValueError("ensemble votes must contain exactly the five registered methods")
    valid = tuple(method for method in METHODS if votes[method] is not None)
    invalid = tuple(method for method in METHODS if votes[method] is None)
    if len(invalid) >= 2:
        return EnsembleDecision("FAIL_CLOSED_INSUFFICIENT_VALID_METHODS", valid, invalid, None, None, frozenset())
    denominator = len(valid)
    threshold = 3
    status = "VALID_3_OF_5" if denominator == 5 else "VALID_3_OF_4"
    universe = set().union(*(votes[method] for method in valid)) if valid else set()
    allowed = frozenset(edge for edge in universe if sum(edge in votes[method] for method in valid) >= threshold)
    return EnsembleDecision(status, valid, invalid, denominator, threshold, allowed)
