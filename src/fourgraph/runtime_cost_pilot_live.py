"""Budget-guarded semantic live adapter for the P1-v3 engineering pilot.

Importing this module makes no network request. A caller must first pass the
separately frozen authorization contract to the outer runner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fourgraph.runtime_cost_pilot import cost_usd
from fourgraph.t21_openai_backend import T21OpenAIBackend


@dataclass
class PilotBudgetController:
    cap_usd: float
    uncached_input_rate: float
    cached_input_rate: float
    output_rate: float
    spent_usd: float = 0.0

    def reserve_or_fail(self, *, input_token_upper_bound: int, output_token_upper_bound: int) -> float:
        reserve = cost_usd(
            input_tokens=input_token_upper_bound,
            cached_input_tokens=0,
            output_tokens=output_token_upper_bound,
            uncached_input_rate=self.uncached_input_rate,
            cached_input_rate=self.cached_input_rate,
            output_rate=self.output_rate,
        )
        if self.spent_usd + reserve > self.cap_usd:
            raise RuntimeError("next semantic attempt could exceed frozen pilot cost cap")
        return reserve

    def record(self, *, input_tokens: int, cached_input_tokens: int, output_tokens: int) -> float:
        amount = cost_usd(
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            uncached_input_rate=self.uncached_input_rate,
            cached_input_rate=self.cached_input_rate,
            output_rate=self.output_rate,
        )
        self.spent_usd += amount
        if self.spent_usd > self.cap_usd:
            raise RuntimeError("recorded semantic cost exceeded frozen pilot cap")
        return amount


class BudgetedSemanticAdapter:
    def __init__(self, *, backend: T21OpenAIBackend, budget: PilotBudgetController) -> None:
        self.backend = backend
        self.budget = budget

    def call(
        self, *, call_id: str, prompt: str, attempt: int,
        input_token_upper_bound: int,
    ) -> dict[str, Any]:
        self.budget.reserve_or_fail(
            input_token_upper_bound=input_token_upper_bound,
            output_token_upper_bound=self.backend.max_output_tokens,
        )
        record = self.backend.call(call_id=call_id, prompt=prompt, attempt=attempt)
        required = ("input_tokens", "cached_input_tokens", "output_tokens")
        if any(record.get(key) is None for key in required):
            raise RuntimeError("provider usage telemetry is incomplete")
        record["accounted_cost_usd"] = self.budget.record(
            input_tokens=int(record["input_tokens"]),
            cached_input_tokens=int(record["cached_input_tokens"]),
            output_tokens=int(record["output_tokens"]),
        )
        return record
