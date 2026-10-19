from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np


def mixture_e_value_from_counts(
    successes: np.ndarray | int,
    total: np.ndarray | int,
    null_mean: float,
    alternatives: Iterable[float],
) -> np.ndarray:
    """Mixture likelihood-ratio e-value for Bernoulli/bounded-mean design simulations.

    Alternatives must all lie on one side of ``null_mean``.  For bounded future
    scene losses the same likelihood-ratio factors are the registered betting
    factors; Bernoulli draws are used as the conservative power model.
    """
    s = np.asarray(successes, dtype=float)
    n = np.asarray(total, dtype=float)
    alternatives_array = np.asarray(tuple(alternatives), dtype=float)
    if not 0.0 < null_mean < 1.0:
        raise ValueError("null_mean must be strictly between zero and one")
    if alternatives_array.size == 0:
        raise ValueError("at least one alternative is required")
    if np.any((alternatives_array <= 0.0) | (alternatives_array >= 1.0)):
        raise ValueError("alternatives must be strictly between zero and one")
    if not (
        np.all(alternatives_array < null_mean)
        or np.all(alternatives_array > null_mean)
    ):
        raise ValueError("alternatives must lie entirely on one side of null_mean")
    if np.any(s < 0) or np.any(n < s):
        raise ValueError("counts must satisfy 0 <= successes <= total")
    logs = []
    for alternative in alternatives_array:
        logs.append(
            s * math.log(float(alternative) / null_mean)
            + (n - s)
            * math.log((1.0 - float(alternative)) / (1.0 - null_mean))
        )
    stacked = np.stack(logs, axis=-1)
    maximum = np.max(stacked, axis=-1)
    return np.exp(maximum) * np.mean(np.exp(stacked - maximum[..., None]), axis=-1)


def risk_e_value(
    error_sum: np.ndarray | int,
    contributing_scenes: np.ndarray | int,
    error_ceiling: float,
    alternatives: Iterable[float],
) -> np.ndarray:
    """Evidence against H0: mean scene-level error >= ``error_ceiling``."""
    return mixture_e_value_from_counts(
        error_sum, contributing_scenes, error_ceiling, alternatives
    )


def coverage_e_value(
    coverage_success_sum: np.ndarray | int,
    scenes: np.ndarray | int,
    coverage_floor: float,
    alternatives: Iterable[float],
) -> np.ndarray:
    """Evidence against H0: mean scene-level coverage <= ``coverage_floor``."""
    return mixture_e_value_from_counts(
        coverage_success_sum, scenes, coverage_floor, alternatives
    )


def crosses(e_value: np.ndarray, alpha: float) -> np.ndarray:
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be strictly between zero and one")
    return np.asarray(e_value) >= (1.0 / alpha)


def minimum_zero_error_scenes(
    error_ceiling: float,
    alpha: float,
    alternatives: Iterable[float],
    maximum: int = 10000,
) -> int:
    for scenes in range(1, maximum + 1):
        if bool(
            crosses(
                risk_e_value(0, scenes, error_ceiling, alternatives), alpha
            )
        ):
            return scenes
    raise RuntimeError("zero-error crossing not reached within maximum")
