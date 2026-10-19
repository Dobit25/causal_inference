from __future__ import annotations

import pytest

from fourgraph.p1_v4_adaptive_ensemble import METHODS, decide_valid_method_ensemble


EDGE = ("X000", "X001")


def votes() -> dict[str, set[tuple[str, str]] | None]:
    return {method: {EDGE} for method in METHODS}


def test_all_valid_uses_three_of_five() -> None:
    result = decide_valid_method_ensemble(votes())
    assert result.status == "VALID_3_OF_5"
    assert result.denominator == 5 and result.threshold == 3
    assert result.allowed_edges == {EDGE}


@pytest.mark.parametrize("invalid", METHODS)
def test_each_single_invalid_method_uses_three_of_four(invalid: str) -> None:
    value = votes(); value[invalid] = None
    result = decide_valid_method_ensemble(value)
    assert result.status == "VALID_3_OF_4"
    assert result.invalid_methods == (invalid,)
    assert result.allowed_edges == {EDGE}


def test_three_of_four_does_not_accept_two_votes() -> None:
    value = votes(); value["PC"] = None; value["MMPC"] = set(); value["FGES"] = set()
    result = decide_valid_method_ensemble(value)
    assert result.status == "VALID_3_OF_4"
    assert result.allowed_edges == set()


def test_two_invalid_methods_fail_closed() -> None:
    value = votes(); value["PC"] = None; value["MMPC"] = None
    result = decide_valid_method_ensemble(value)
    assert result.status == "FAIL_CLOSED_INSUFFICIENT_VALID_METHODS"
    assert not result.allowed_edges


def test_method_universe_must_be_exact() -> None:
    with pytest.raises(ValueError):
        decide_valid_method_ensemble({"PC": set()})
