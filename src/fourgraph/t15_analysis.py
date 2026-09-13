"""Deterministic statistical helpers for the frozen P0 holdout analysis."""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Mapping, Sequence


def mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("mean requires at least one value")
    return sum(values) / len(values)


def percentile(values: Sequence[float], probability: float) -> float:
    """Linearly interpolated percentile, equivalent to the common type-7 rule."""
    if not values or not 0.0 <= probability <= 1.0:
        raise ValueError("invalid percentile input")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def derived_seed(root_seed: int, namespace: str) -> int:
    digest = hashlib.sha256(f"{root_seed}|{namespace}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def paired_cluster_bootstrap(
    left: Mapping[str, float],
    right: Mapping[str, float],
    *,
    replicates: int,
    root_seed: int,
    namespace: str,
) -> dict[str, float | int]:
    scenes = sorted(set(left) & set(right))
    if not scenes or replicates <= 0:
        raise ValueError("paired bootstrap requires scenes and positive replicates")
    differences = [left[scene] - right[scene] for scene in scenes]
    effect = mean(differences)
    rng = random.Random(derived_seed(root_seed, namespace))
    boot = []
    for _ in range(replicates):
        boot.append(mean([differences[rng.randrange(len(differences))] for _ in differences]))
    lower_tail = (sum(value <= 0.0 for value in boot) + 1) / (replicates + 1)
    upper_tail = (sum(value >= 0.0 for value in boot) + 1) / (replicates + 1)
    return {
        "paired_scene_count": len(scenes),
        "effect_left_minus_right": effect,
        "ci_lower": percentile(boot, 0.025),
        "ci_upper": percentile(boot, 0.975),
        "two_sided_bootstrap_p": min(1.0, 2.0 * min(lower_tail, upper_tail)),
    }


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    if any(not 0.0 <= value <= 1.0 for value in p_values):
        raise ValueError("p-values must lie in [0, 1]")
    count = len(p_values)
    ranked = sorted(enumerate(p_values), key=lambda item: (item[1], item[0]))
    adjusted = [1.0] * count
    running = 1.0
    for rank_index in range(count - 1, -1, -1):
        original_index, value = ranked[rank_index]
        rank = rank_index + 1
        running = min(running, value * count / rank)
        adjusted[original_index] = min(1.0, running)
    return adjusted


def exact_mcnemar(left: Sequence[bool], right: Sequence[bool]) -> dict[str, float | int]:
    if len(left) != len(right):
        raise ValueError("McNemar inputs must be paired")
    left_only = sum(a and not b for a, b in zip(left, right))
    right_only = sum(b and not a for a, b in zip(left, right))
    discordant = left_only + right_only
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(math.comb(discordant, k) for k in range(min(left_only, right_only) + 1)) / (2**discordant)
        p_value = min(1.0, 2.0 * tail)
    return {
        "left_correct_right_incorrect": left_only,
        "left_incorrect_right_correct": right_only,
        "discordant": discordant,
        "two_sided_exact_p": p_value,
    }


def average_ranks(values: Mapping[str, float], *, descending: bool = True) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: ((-item[1]) if descending else item[1], item[0]))
    ranks: dict[str, float] = {}
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        rank = ((start + 1) + end) / 2.0
        for key, _ in ordered[start:end]:
            ranks[key] = rank
        start = end
    return ranks


def spearman_from_values(left: Mapping[str, float], right: Mapping[str, float]) -> float | None:
    keys = sorted(set(left) & set(right))
    if len(keys) < 2:
        return None
    left_ranks = average_ranks({key: left[key] for key in keys})
    right_ranks = average_ranks({key: right[key] for key in keys})
    x = [left_ranks[key] for key in keys]
    y = [right_ranks[key] for key in keys]
    x_mean, y_mean = mean(x), mean(y)
    numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y))
    denominator = math.sqrt(sum((a - x_mean) ** 2 for a in x) * sum((b - y_mean) ** 2 for b in y))
    return None if denominator == 0.0 else numerator / denominator

