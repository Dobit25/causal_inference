"""Fail-closed token budget control for the Nano-medium calibration runner.

The controller is deliberately provider-agnostic. A production adapter must
call ``reserve`` before a provider request and ``commit_provider_usage`` only
after receiving provider-reported usage. This module never calls an API.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo


class CalibrationBudgetError(RuntimeError):
    """A fail-closed budget, usage, or idempotency violation."""


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    reasoning_tokens: int | None = None

    @classmethod
    def from_provider(cls, usage: dict[str, Any]) -> "TokenUsage":
        required = ("input_tokens", "output_tokens", "total_tokens")
        if any(name not in usage or not isinstance(usage[name], int) or usage[name] < 0 for name in required):
            raise CalibrationBudgetError("provider usage must include non-negative integer input/output/total tokens")
        reasoning = usage.get("reasoning_tokens")
        if reasoning is not None and (not isinstance(reasoning, int) or reasoning < 0):
            raise CalibrationBudgetError("reasoning_tokens must be a non-negative integer or null")
        if usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
            raise CalibrationBudgetError("provider total_tokens does not equal input_tokens + output_tokens")
        return cls(usage["input_tokens"], usage["output_tokens"], usage["total_tokens"], reasoning)


def logical_identity(*, scene_id: str, story_variant: str, prompt_variant: str, model_snapshot: str, schema_sha256: str) -> str:
    payload = {"model_snapshot": model_snapshot, "prompt_variant": prompt_variant, "scene_id": scene_id, "schema_sha256": schema_sha256, "story_variant": story_variant}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest().upper()


class CalibrationTokenLedger:
    def __init__(
        self,
        path: Path,
        *,
        max_total_tokens: int = 3_000_000,
        reset_hour: int = 7,
        timezone_name: str = "Asia/Ho_Chi_Minh",
        input_rate_per_million: float = 0.20,
        output_rate_per_million: float = 1.25,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_total_tokens <= 0 or reset_hour < 0 or reset_hour > 23:
            raise ValueError("invalid token budget configuration")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_total_tokens = max_total_tokens
        self.reset_hour = reset_hour
        self.tz = ZoneInfo(timezone_name)
        self.input_rate_per_million = input_rate_per_million
        self.output_rate_per_million = output_rate_per_million
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def now_local(self) -> datetime:
        current = self.clock()
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return current.astimezone(self.tz)

    def window_start(self, current: datetime | None = None) -> datetime:
        local = (current or self.now_local()).astimezone(self.tz)
        start_date = local.date() if local.time() >= time(self.reset_hour) else local.date() - timedelta(days=1)
        return datetime.combine(start_date, time(self.reset_hour), tzinfo=self.tz)

    def _records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records = []
        for number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise CalibrationBudgetError(f"invalid token ledger JSON at line {number}") from exc
        return records

    def _append(self, record: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")

    def _window_key(self) -> str:
        return self.window_start().isoformat()

    def _window_records(self, window_key: str | None = None) -> list[dict[str, Any]]:
        key = window_key or self._window_key()
        return [row for row in self._records() if row.get("window_start") == key]

    def _halted(self, records: list[dict[str, Any]]) -> bool:
        return any(row.get("event_type") in {"invalid_usage", "budget_violation", "manual_halt"} for row in records)

    def _state(self) -> tuple[str, int, int, set[str], set[str], bool]:
        window = self._window_key()
        records = self._window_records(window)
        committed = sum(int(row.get("total_tokens", 0)) for row in records if row.get("event_type") == "committed")
        committed_execs = {row["execution_id"] for row in records if row.get("event_type") == "committed"}
        released_execs = {row["execution_id"] for row in records if row.get("event_type") == "released"}
        reserved = sum(int(row.get("estimated_total_tokens", 0)) for row in records if row.get("event_type") == "reserved" and row["execution_id"] not in committed_execs and row["execution_id"] not in released_execs)
        active = {row["execution_id"] for row in records if row.get("event_type") == "reserved"} - {row["execution_id"] for row in records if row.get("event_type") == "released"}
        completed = {row["logical_id"] for row in records if row.get("event_type") == "committed"}
        return window, committed, reserved, active, completed, self._halted(records)

    def snapshot(self) -> dict[str, Any]:
        window, committed, reserved, active, completed, halted = self._state()
        return {"window_start": window, "max_total_tokens": self.max_total_tokens, "committed_total_tokens": committed, "reserved_total_tokens": reserved, "remaining_total_tokens": max(0, self.max_total_tokens - committed - reserved), "active_reservations": len(active), "completed_logical_calls": len(completed), "halted": halted}

    def reserve(self, logical_id: str, attempt: int, estimated_total_tokens: int, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if attempt < 0 or estimated_total_tokens <= 0:
            raise CalibrationBudgetError("attempt must be non-negative and estimate must be positive")
        window, committed, reserved, active, completed, halted = self._state()
        if halted:
            raise CalibrationBudgetError("ledger is halted fail-closed; no automatic resume")
        execution_id = f"{logical_id}:attempt:{attempt}"
        if execution_id in active or logical_id in completed:
            raise CalibrationBudgetError("duplicate or already-completed logical call")
        if committed + reserved + estimated_total_tokens > self.max_total_tokens:
            self._append({"event_type": "budget_violation", "window_start": window, "logical_id": logical_id, "execution_id": execution_id, "reason": "reservation_would_exceed_total_token_hard_stop"})
            raise CalibrationBudgetError("reservation would exceed 3,000,000-token hard stop")
        record = {"event_type": "reserved", "window_start": window, "logical_id": logical_id, "execution_id": execution_id, "attempt": attempt, "estimated_total_tokens": estimated_total_tokens, "timestamp": self.now_local().isoformat(), "metadata": metadata or {}}
        self._append(record)
        return {**record, "remaining_total_tokens": self.max_total_tokens - committed - reserved - estimated_total_tokens}

    def release(self, logical_id: str, attempt: int, *, reason: str) -> None:
        window, _, _, active, completed, halted = self._state()
        execution_id = f"{logical_id}:attempt:{attempt}"
        if halted or logical_id in completed or execution_id not in active:
            raise CalibrationBudgetError("cannot release an inactive, completed, or halted reservation")
        self._append({"event_type": "released", "window_start": window, "logical_id": logical_id, "execution_id": execution_id, "attempt": attempt, "estimated_total_tokens": next(row["estimated_total_tokens"] for row in self._window_records(window) if row.get("execution_id") == execution_id and row.get("event_type") == "reserved"), "reason": reason, "timestamp": self.now_local().isoformat()})

    def commit_provider_usage(self, logical_id: str, attempt: int, usage: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        window, committed, reserved, active, completed, halted = self._state()
        execution_id = f"{logical_id}:attempt:{attempt}"
        if halted:
            raise CalibrationBudgetError("ledger is halted fail-closed; usage cannot be committed")
        if logical_id in completed or execution_id not in active:
            raise CalibrationBudgetError("unknown, duplicate, or unreserved execution identity")
        try:
            parsed = TokenUsage.from_provider(usage)
        except CalibrationBudgetError as exc:
            self._append({"event_type": "invalid_usage", "window_start": window, "logical_id": logical_id, "execution_id": execution_id, "reason": str(exc), "timestamp": self.now_local().isoformat()})
            raise
        reservation = next(row for row in self._window_records(window) if row.get("execution_id") == execution_id and row.get("event_type") == "reserved")
        if parsed.total_tokens > reservation["estimated_total_tokens"] or committed + parsed.total_tokens > self.max_total_tokens:
            self._append({"event_type": "budget_violation", "window_start": window, "logical_id": logical_id, "execution_id": execution_id, "reason": "provider_usage_exceeded_reserved_or_hard_stop", "total_tokens": parsed.total_tokens, "timestamp": self.now_local().isoformat()})
            raise CalibrationBudgetError("provider usage exceeded reservation or hard stop")
        cost = (parsed.input_tokens * self.input_rate_per_million + parsed.output_tokens * self.output_rate_per_million) / 1_000_000
        record = {"event_type": "committed", "window_start": window, "logical_id": logical_id, "execution_id": execution_id, "attempt": attempt, "input_tokens": parsed.input_tokens, "output_tokens": parsed.output_tokens, "reasoning_tokens": parsed.reasoning_tokens, "total_tokens": parsed.total_tokens, "cost_usd": round(cost, 12), "timestamp": self.now_local().isoformat(), "metadata": metadata or {}}
        self._append(record)
        return {**record, "remaining_total_tokens": self.max_total_tokens - committed - parsed.total_tokens - max(0, reserved - reservation["estimated_total_tokens"])}
