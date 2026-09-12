"""Pinned OpenAI Responses API adapter for the T08 graph builder."""

from __future__ import annotations

import importlib.metadata
import json
import time
from typing import Any

from fourgraph.llm_backend import LLMCallRequest, LLMCallResponse


class OpenAIResponsesBackend:
    """Thin synchronous adapter; graph parsing and validation remain provider-neutral."""

    provider = "openai"
    endpoint = "/v1/responses"

    def __init__(
        self,
        *,
        api_key: str,
        response_schema: dict[str, Any],
        service_tier: str = "default",
        reasoning_effort: str = "none",
        store: bool = False,
        transport_max_retries: int = 2,
        timeout_seconds: float = 120.0,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API key cannot be empty")
        if service_tier != "default":
            raise ValueError("T08 permits only the default OpenAI service tier")
        if reasoning_effort not in {"none", "low", "medium", "high", "xhigh"}:
            raise ValueError("Unsupported OpenAI reasoning effort")
        if store is not False:
            raise ValueError("T08 OpenAI responses must use store=false")
        if transport_max_retries < 0:
            raise ValueError("transport_max_retries must be non-negative")

        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - environment diagnostic
            raise RuntimeError("Install the pinned openai SDK before live T08 calls") from exc

        self._client = OpenAI(
            api_key=api_key,
            max_retries=transport_max_retries,
            timeout=timeout_seconds,
        )
        self._response_schema = response_schema
        self._service_tier = service_tier
        self._reasoning_effort = reasoning_effort
        self._store = store
        self._sdk_version = importlib.metadata.version("openai")

    @property
    def sdk_version(self) -> str:
        return self._sdk_version

    def complete(self, request: LLMCallRequest) -> LLMCallResponse:
        if request.provider != self.provider:
            raise ValueError("OpenAI backend received a non-OpenAI request")
        if request.seed is not None:
            raise ValueError("The pinned Responses adapter does not claim seed support")

        started = time.perf_counter()
        response = self._client.responses.create(
            model=request.model_id,
            input=request.prompt,
            max_output_tokens=request.max_tokens,
            temperature=request.temperature,
            reasoning={"effort": self._reasoning_effort},
            text={
                "format": {
                    "type": "json_schema",
                    "name": "fourgraph_llm_graph_response_v1",
                    "schema": self._response_schema,
                    "strict": True,
                }
            },
            service_tier=self._service_tier,
            store=self._store,
            metadata={
                "task": "T08",
                "scene_id": request.scene_id,
                "attempt": str(request.attempt),
            },
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        status = getattr(response, "status", None)
        if status != "completed":
            raise RuntimeError(f"OpenAI response did not complete: status={status!r}")
        raw_text = response.output_text
        if not raw_text:
            raise RuntimeError("OpenAI response contained no output text")

        usage = getattr(response, "usage", None)
        model = str(getattr(response, "model", request.model_id))
        return LLMCallResponse(
            raw_text=raw_text,
            provider=self.provider,
            model_id=model,
            model_version=model,
            request_id=getattr(response, "_request_id", None),
            system_fingerprint=getattr(response, "system_fingerprint", None),
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
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
        )
