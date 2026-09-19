"""Pure planning and fail-closed authorization helpers for the P1-v3 pilot."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping


class PilotAuthorizationError(RuntimeError):
    """Raised before any live workload when authorization is absent or stale."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def planned_counts(config: Mapping[str, object]) -> dict[str, int]:
    schedule = config["pilot_schedule"]
    boss = schedule["bootstrap_boss"]
    semantic = schedule["semantic_api"]
    return {
        "pilot_scenes": int(config["synthetic_panel"]["scene_count"]),
        "boss_warmups": int(boss["warmup_fits"]),
        "boss_measured_fits": int(boss["measured_scenes"]) * int(boss["repetitions_per_scene"]),
        "semantic_logical_calls": int(semantic["sampled_scenes"]) * int(semantic["story_variants"]) * int(semantic["prompt_variants"]),
    }


def cost_usd(
    *, input_tokens: int, cached_input_tokens: int, output_tokens: int,
    uncached_input_rate: float, cached_input_rate: float, output_rate: float,
) -> float:
    if min(input_tokens, cached_input_tokens, output_tokens) < 0:
        raise ValueError("token counts must be non-negative")
    if cached_input_tokens > input_tokens:
        raise ValueError("cached input cannot exceed total input")
    if min(uncached_input_rate, cached_input_rate, output_rate) < 0:
        raise ValueError("rates must be non-negative")
    return (
        (input_tokens - cached_input_tokens) * uncached_input_rate
        + cached_input_tokens * cached_input_rate
        + output_tokens * output_rate
    ) / 1_000_000


def require_live_authorization(record: Mapping[str, object], preflight_sha256: str) -> None:
    if record.get("schema_version") != "fourgraph.p1_v3_runtime_cost_pilot_live_authorization.v1":
        raise PilotAuthorizationError("missing versioned live-authorization contract")
    if record.get("preflight_audit_sha256") != preflight_sha256:
        raise PilotAuthorizationError("live authorization does not match frozen preflight")
    if record.get("explicit_user_authorization") is not True:
        raise PilotAuthorizationError("explicit user authorization is absent")
    if record.get("pilot_execution") is not True:
        raise PilotAuthorizationError("pilot execution remains forbidden")
    if record.get("successor_cohort_generation") is not False:
        raise PilotAuthorizationError("authorization improperly includes study generation")
    if record.get("final_holdout_access") is not False:
        raise PilotAuthorizationError("authorization improperly includes final holdout")
