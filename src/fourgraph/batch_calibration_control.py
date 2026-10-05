"""Append-only token ledger with a post-batch hard stop.

The calibration protocol limits each registered batch independently.  Provider
usage is authoritative; a batch is allowed to finish, then the next batch is
blocked when its measured total exceeds the configured limit.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .nano_calibration_control import CalibrationBudgetError, TokenUsage


class BatchCalibrationTokenLedger:
    def __init__(self, path: Path, *, max_batch_tokens: int = 3_000_000, batch_size: int = 360, input_rate_per_million: float = 0.20, output_rate_per_million: float = 1.25) -> None:
        if max_batch_tokens <= 0 or batch_size <= 0:
            raise ValueError("invalid batch budget configuration")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_batch_tokens = max_batch_tokens
        self.batch_size = batch_size
        self.input_rate_per_million = input_rate_per_million
        self.output_rate_per_million = output_rate_per_million

    def _records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _append(self, row: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    def _batch(self, batch_id: int) -> list[dict[str, Any]]:
        return [r for r in self._records() if int(r.get("batch_id", -1)) == batch_id]

    def seed_carry_in(self, *, batch_id: int, logical_id: str, attempt: int, total_tokens: int, input_tokens: int = 0, output_tokens: int = 0, reason: str) -> None:
        rows = self._batch(batch_id)
        if any(r.get("event_type") == "carry_in_provider_usage" and r.get("logical_id") == logical_id for r in rows):
            return
        self._append({
            "event_type": "carry_in_provider_usage", "batch_id": batch_id,
            "logical_id": logical_id, "attempt": attempt,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "total_tokens": total_tokens, "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def _state(self, batch_id: int) -> tuple[int, set[str], set[str], set[str]]:
        rows = self._batch(batch_id)
        committed = sum(int(r.get("total_tokens", 0)) for r in rows if r.get("event_type") in {"committed", "carry_in_provider_usage"})
        committed_ids = {r["logical_id"] for r in rows if r.get("event_type") == "committed"}
        reserved_ids = {r["execution_id"] for r in rows if r.get("event_type") == "reserved"}
        released_ids = {r["execution_id"] for r in rows if r.get("event_type") == "released"}
        active = reserved_ids - released_ids - {r["execution_id"] for r in rows if r.get("event_type") == "committed"}
        return committed, committed_ids, active, {r["execution_id"] for r in rows if r.get("event_type") == "reserved"}

    def summary(self, batch_id: int) -> dict[str, Any] | None:
        for row in reversed(self._batch(batch_id)):
            if row.get("event_type") == "batch_summary":
                return row
        return None

    def reserve(self, *, batch_id: int, logical_id: str, attempt: int, estimated_total_tokens: int, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if attempt < 0 or estimated_total_tokens <= 0:
            raise CalibrationBudgetError("invalid batch reservation")
        existing = self.summary(batch_id)
        if existing and existing.get("exceeded"):
            raise CalibrationBudgetError("previous batch exceeded hard stop; no next batch")
        _, committed_ids, active, _ = self._state(batch_id)
        execution_id = f"{logical_id}:attempt:{attempt}"
        if logical_id in committed_ids or execution_id in active:
            raise CalibrationBudgetError("duplicate or completed batch execution identity")
        self._append({
            "event_type": "reserved", "batch_id": batch_id, "logical_id": logical_id,
            "execution_id": execution_id, "attempt": attempt,
            "estimated_total_tokens": estimated_total_tokens,
            "metadata": metadata or {}, "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {"execution_id": execution_id, "batch_id": batch_id}

    def release(self, *, batch_id: int, logical_id: str, attempt: int, reason: str) -> None:
        execution_id = f"{logical_id}:attempt:{attempt}"
        rows = self._batch(batch_id)
        if not any(r.get("event_type") == "reserved" and r.get("execution_id") == execution_id for r in rows):
            return
        self._append({"event_type": "released", "batch_id": batch_id, "logical_id": logical_id, "execution_id": execution_id, "attempt": attempt, "reason": reason, "timestamp": datetime.now(timezone.utc).isoformat()})

    def commit_provider_usage(self, *, batch_id: int, logical_id: str, attempt: int, usage: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        parsed = TokenUsage.from_provider(usage)
        execution_id = f"{logical_id}:attempt:{attempt}"
        rows = self._batch(batch_id)
        if not any(r.get("event_type") == "reserved" and r.get("execution_id") == execution_id for r in rows):
            raise CalibrationBudgetError("unknown or unreserved batch execution identity")
        if any(r.get("event_type") == "committed" and r.get("execution_id") == execution_id for r in rows):
            raise CalibrationBudgetError("duplicate provider usage commit")
        cost = (parsed.input_tokens * self.input_rate_per_million + parsed.output_tokens * self.output_rate_per_million) / 1_000_000
        row = {
            "event_type": "committed", "batch_id": batch_id,
            "logical_id": logical_id, "execution_id": execution_id, "attempt": attempt,
            "input_tokens": parsed.input_tokens, "output_tokens": parsed.output_tokens,
            "reasoning_tokens": parsed.reasoning_tokens, "total_tokens": parsed.total_tokens,
            "cost_usd": round(cost, 12), "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._append(row)
        return row

    def finalize_batch(self, *, batch_id: int, planned_calls: int) -> dict[str, Any]:
        prior = self.summary(batch_id)
        if prior:
            return prior
        rows = self._batch(batch_id)
        completed = {r["logical_id"] for r in rows if r.get("event_type") == "committed"}
        total = sum(int(r.get("total_tokens", 0)) for r in rows if r.get("event_type") in {"committed", "carry_in_provider_usage"})
        if len(completed) < planned_calls:
            raise CalibrationBudgetError("cannot finalize incomplete batch")
        row = {"event_type": "batch_summary", "batch_id": batch_id, "planned_calls": planned_calls, "completed_calls": len(completed), "total_tokens": total, "max_batch_tokens": self.max_batch_tokens, "exceeded": total > self.max_batch_tokens, "timestamp": datetime.now(timezone.utc).isoformat()}
        self._append(row)
        return row

    def snapshot(self, batch_id: int) -> dict[str, Any]:
        rows = self._batch(batch_id)
        total = sum(int(r.get("total_tokens", 0)) for r in rows if r.get("event_type") in {"committed", "carry_in_provider_usage"})
        completed = len({r["logical_id"] for r in rows if r.get("event_type") == "committed"})
        return {"batch_id": batch_id, "batch_size": self.batch_size, "max_batch_tokens": self.max_batch_tokens, "total_tokens": total, "completed_calls": completed, "remaining_to_limit": max(0, self.max_batch_tokens - total), "summary": self.summary(batch_id)}
