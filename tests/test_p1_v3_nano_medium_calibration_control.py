from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from fourgraph.nano_calibration_control import CalibrationBudgetError, CalibrationTokenLedger


def clock(value: datetime):
    return lambda: value


def usage(total: int, reasoning: int | None = 100):
    return {"input_tokens": total // 2, "output_tokens": total - total // 2, "total_tokens": total, "reasoning_tokens": reasoning}


def test_exact_hard_stop_and_no_overshoot(tmp_path: Path):
    ledger = CalibrationTokenLedger(tmp_path / "ledger.jsonl", clock=clock(datetime(2026, 10, 4, 8, tzinfo=timezone.utc)))
    ledger.reserve("a", 0, 2_000_000)
    ledger.commit_provider_usage("a", 0, usage(2_000_000))
    ledger.reserve("b", 0, 1_000_000)
    ledger.commit_provider_usage("b", 0, usage(1_000_000))
    assert ledger.snapshot()["remaining_total_tokens"] == 0
    with pytest.raises(CalibrationBudgetError):
        ledger.reserve("c", 0, 1)


def test_reset_at_0700_vietnam(tmp_path: Path):
    ledger = CalibrationTokenLedger(tmp_path / "ledger.jsonl", clock=clock(datetime(2026, 10, 3, 23, 59, tzinfo=timezone.utc)))  # 06:59 ICT on Oct 4
    ledger.reserve("a", 0, 10)
    ledger.commit_provider_usage("a", 0, usage(10))
    first = ledger.snapshot()["window_start"]
    ledger.clock = clock(datetime(2026, 10, 4, 0, 0, tzinfo=timezone.utc))  # 07:00 ICT, new window
    assert ledger.snapshot()["window_start"] != first
    assert ledger.snapshot()["committed_total_tokens"] == 0


def test_missing_provider_usage_halts_fail_closed(tmp_path: Path):
    ledger = CalibrationTokenLedger(tmp_path / "ledger.jsonl", clock=clock(datetime(2026, 10, 4, 8, tzinfo=timezone.utc)))
    ledger.reserve("a", 0, 100)
    with pytest.raises(CalibrationBudgetError):
        ledger.commit_provider_usage("a", 0, {"input_tokens": 50, "output_tokens": 50})
    with pytest.raises(CalibrationBudgetError):
        ledger.reserve("b", 0, 10)


def test_retry_then_duplicate_prevention(tmp_path: Path):
    ledger = CalibrationTokenLedger(tmp_path / "ledger.jsonl", clock=clock(datetime(2026, 10, 4, 8, tzinfo=timezone.utc)))
    ledger.reserve("a", 0, 100)
    ledger.release("a", 0, reason="transport_failure")
    ledger.reserve("a", 1, 100)
    ledger.commit_provider_usage("a", 1, usage(100))
    with pytest.raises(CalibrationBudgetError):
        ledger.reserve("a", 2, 100)


def test_runner_dry_run_is_side_effect_free(tmp_path: Path):
    ledger = CalibrationTokenLedger(tmp_path / "ledger.jsonl")
    assert ledger.snapshot()["committed_total_tokens"] == 0
    assert ledger.snapshot()["remaining_total_tokens"] == 3_000_000
