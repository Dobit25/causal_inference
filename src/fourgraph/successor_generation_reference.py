"""Independent reference allocator for P1-v3 successor conformance."""

from __future__ import annotations

import hashlib
from typing import Mapping, Sequence


def _rank(seed: int, component: str, identifier: str) -> str:
    return hashlib.sha256(f"{seed}:{component}:{identifier}".encode("utf-8")).hexdigest()


def reference_assignment(
    identifiers: Sequence[str], counts: Mapping[object, int], seed: int, component: str
) -> dict[str, object]:
    ordered = sorted(identifiers, key=lambda identifier: _rank(seed, component, identifier))
    slots = [value for value in sorted(counts, key=str) for _ in range(counts[value])]
    if len(ordered) != len(slots):
        raise ValueError("reference allocation does not cover identifiers")
    return dict(zip(ordered, slots))
