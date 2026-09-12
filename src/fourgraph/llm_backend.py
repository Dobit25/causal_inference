"""Provider-neutral LLM call and deterministic replay contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from fourgraph.graph_contract import sha256_hex


@dataclass(frozen=True)
class LLMCallRequest:
    scene_id: str
    attempt: int
    prompt: str
    provider: str
    model_id: str
    model_version: str
    temperature: float
    max_tokens: int
    seed: int | None

    def __post_init__(self) -> None:
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 0:
            raise ValueError("LLM call attempt must be a non-negative integer")
        if not self.scene_id or not self.prompt:
            raise ValueError("LLM call scene_id and prompt cannot be empty")

    @property
    def prompt_sha256(self) -> str:
        return sha256_hex(self.prompt.encode("utf-8"))


@dataclass(frozen=True)
class LLMCallResponse:
    raw_text: str
    provider: str
    model_id: str
    model_version: str
    request_id: str | None = None
    system_fingerprint: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_input_tokens: int | None = None
    latency_ms: int | None = None
    endpoint: str | None = None
    sdk_version: str | None = None
    service_tier: str | None = None
    provider_response_json: str | None = None
    response_status: str | None = None
    incomplete_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.raw_text, str):
            raise ValueError("LLM raw response must be text")
        if not self.provider or not self.model_id or not self.model_version:
            raise ValueError("LLM response identity must be complete")
        for name, value in (
            ("input_tokens", self.input_tokens),
            ("output_tokens", self.output_tokens),
            ("reasoning_tokens", self.reasoning_tokens),
            ("cached_input_tokens", self.cached_input_tokens),
            ("latency_ms", self.latency_ms),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer or null")
        if self.provider_response_json is not None:
            value = json.loads(self.provider_response_json)
            if not isinstance(value, dict):
                raise ValueError("provider_response_json must encode a JSON object")

    @property
    def raw_sha256(self) -> str:
        return sha256_hex(self.raw_text.encode("utf-8"))


class LLMBackend(Protocol):
    def complete(self, request: LLMCallRequest) -> LLMCallResponse:
        """Return one raw model response without parsing or repair."""


@dataclass(frozen=True)
class ReplayEntry:
    scene_id: str
    attempt: int
    prompt_sha256: str
    response: LLMCallResponse


class ReplayBackend:
    """Replay immutable raw calls and verify their prompt identity."""

    def __init__(self, entries: list[ReplayEntry]) -> None:
        keys = [(entry.scene_id, entry.attempt) for entry in entries]
        if len(keys) != len(set(keys)):
            raise ValueError("Replay log contains duplicate scene/attempt entries")
        self._entries = {
            (entry.scene_id, entry.attempt): entry for entry in entries
        }

    @classmethod
    def load(cls, path: str | Path) -> "ReplayBackend":
        entries: list[ReplayEntry] = []
        for line_number, line in enumerate(
            Path(path).read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line:
                continue
            value = json.loads(line)
            required = {
                "scene_id",
                "attempt",
                "prompt_sha256",
                "raw_text",
                "provider",
                "model_id",
                "model_version",
                "request_id",
                "system_fingerprint",
                "input_tokens",
                "output_tokens",
                "latency_ms",
            }
            optional = {
                "raw_log_schema_version",
                "prompt",
                "endpoint",
                "sdk_version",
                "service_tier",
                "provider_response_json",
            }
            if (
                not isinstance(value, dict)
                or not required.issubset(value)
                or not set(value).issubset(required | optional)
            ):
                raise ValueError(f"Malformed replay record at line {line_number}")
            if value.get("raw_log_schema_version") not in (
                None,
                "fourgraph.llm_raw_call.v1",
            ):
                raise ValueError(f"Unsupported raw log schema at line {line_number}")
            if "prompt" in value:
                prompt_hash = sha256_hex(str(value["prompt"]).encode("utf-8"))
                if prompt_hash != value["prompt_sha256"]:
                    raise ValueError(f"Raw prompt hash mismatch at line {line_number}")
            response = LLMCallResponse(
                raw_text=value["raw_text"],
                provider=str(value["provider"]),
                model_id=str(value["model_id"]),
                model_version=str(value["model_version"]),
                request_id=value["request_id"],
                system_fingerprint=value["system_fingerprint"],
                input_tokens=value["input_tokens"],
                output_tokens=value["output_tokens"],
                latency_ms=value["latency_ms"],
                endpoint=value.get("endpoint"),
                sdk_version=value.get("sdk_version"),
                service_tier=value.get("service_tier"),
                provider_response_json=value.get("provider_response_json"),
            )
            entries.append(
                ReplayEntry(
                    scene_id=str(value["scene_id"]),
                    attempt=int(value["attempt"]),
                    prompt_sha256=str(value["prompt_sha256"]),
                    response=response,
                )
            )
        return cls(entries)

    def complete(self, request: LLMCallRequest) -> LLMCallResponse:
        key = (request.scene_id, request.attempt)
        if key not in self._entries:
            raise RuntimeError(f"Replay response is missing: {key}")
        entry = self._entries[key]
        if entry.prompt_sha256 != request.prompt_sha256:
            raise RuntimeError(f"Replay prompt hash mismatch: {key}")
        return entry.response

    def has_scene(self, scene_id: str) -> bool:
        """Return whether a captured first attempt exists for a scene."""

        return (scene_id, 0) in self._entries

    @property
    def scene_ids(self) -> frozenset[str]:
        return frozenset(scene_id for scene_id, _ in self._entries)
