"""OpenAI Responses transport for the T12 v2 reasoning candidate."""

from __future__ import annotations

import importlib.metadata
import json
import time
from typing import Any

from fourgraph.llm_backend import LLMCallRequest, LLMCallResponse


class T12OpenAIResponsesBackend:
    """Pinned transport for pre-registered high/medium reasoning candidates."""

    provider = "openai"
    endpoint = "/v1/responses"

    def __init__(
        self,
        *,
        api_key: str,
        response_schema: dict[str, Any],
        response_schema_name: str,
        model_version: str,
        reasoning_effort: str = "high",
        service_tier: str = "default",
        store: bool = False,
        transport_max_retries: int = 2,
        timeout_seconds: float = 180.0,
        experiment_id: str = "T12_v2_conformance",
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API key cannot be empty")
        if reasoning_effort not in {"high", "medium"}:
            raise ValueError(
                "T12 v2 GPT-5.4 Mini candidates require "
                "reasoning_effort=high or medium"
            )
        if service_tier != "default" or store is not False:
            raise ValueError("T12 v2 requires service_tier=default and store=false")
        if not response_schema_name or not model_version:
            raise ValueError("Schema name and model snapshot must be pinned")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install the pinned openai SDK for live T12 calls") from exc
        self._client = OpenAI(
            api_key=api_key,
            max_retries=transport_max_retries,
            timeout=timeout_seconds,
        )
        self._response_schema = response_schema
        self._response_schema_name = response_schema_name
        self._model_version = model_version
        self._reasoning_effort = reasoning_effort
        self._service_tier = service_tier
        self._store = store
        self._experiment_id = experiment_id
        self._sdk_version = importlib.metadata.version("openai")

    @property
    def sdk_version(self) -> str:
        return self._sdk_version

    def complete(self, request: LLMCallRequest) -> LLMCallResponse:
        if request.provider != self.provider:
            raise ValueError("T12 OpenAI backend received another provider")
        if request.model_id != self._model_version or request.model_version != self._model_version:
            raise ValueError("T12 request does not use the frozen model snapshot")
        if request.seed is not None:
            raise ValueError("Responses candidate does not claim seed support")

        started = time.perf_counter()
        response = self._client.responses.create(
            model=request.model_id,
            input=request.prompt,
            max_output_tokens=request.max_tokens,
            reasoning={"effort": self._reasoning_effort},
            text={
                "format": {
                    "type": "json_schema",
                    "name": self._response_schema_name,
                    "schema": self._response_schema,
                    "strict": True,
                }
            },
            service_tier=self._service_tier,
            store=self._store,
            metadata={
                "task": getattr(self, "_experiment_id", "T12_v2_conformance"),
                "case_id": request.scene_id,
                "attempt": str(request.attempt),
            },
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        response_status = str(getattr(response, "status", ""))
        details = getattr(response, "incomplete_details", None)
        incomplete_reason = getattr(details, "reason", None)
        if response_status not in {"completed", "incomplete"}:
            raise RuntimeError(
                f"OpenAI response failed: status={response_status!r}, details={details!r}"
            )
        # An incomplete response may contain no visible text after consuming its
        # reasoning budget. Return it to the runner so the attempt is logged
        # before local validation triggers the pre-registered retry policy.
        raw_text = response.output_text or ""
        actual_model = str(getattr(response, "model", ""))
        if actual_model != self._model_version:
            raise RuntimeError(
                f"OpenAI model snapshot drift: expected={self._model_version}, actual={actual_model}"
            )
        usage = getattr(response, "usage", None)
        input_details = getattr(usage, "input_tokens_details", None)
        output_details = getattr(usage, "output_tokens_details", None)
        return LLMCallResponse(
            raw_text=raw_text,
            provider=self.provider,
            model_id=actual_model,
            model_version=actual_model,
            request_id=getattr(response, "_request_id", None),
            system_fingerprint=getattr(response, "system_fingerprint", None),
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            reasoning_tokens=getattr(output_details, "reasoning_tokens", None),
            cached_input_tokens=getattr(input_details, "cached_tokens", None),
            latency_ms=latency_ms,
            endpoint=self.endpoint,
            sdk_version=self._sdk_version,
            service_tier=getattr(response, "service_tier", None),
            provider_response_json=json.dumps(
                response.model_dump(mode="json"),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            response_status=response_status,
            incomplete_reason=incomplete_reason,
        )
