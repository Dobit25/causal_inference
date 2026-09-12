"""Google AI Studio adapter for the frozen T12 Gemma reasoner."""

from __future__ import annotations

import importlib.metadata
import json
import time
from typing import Any

from fourgraph.llm_backend import LLMCallRequest, LLMCallResponse


class GeminiReasonerBackend:
    """Synchronous Google GenAI adapter with quota-only credential rotation."""

    provider = "google_ai_studio"
    endpoint = "models.generate_content"

    def __init__(
        self,
        *,
        api_keys: list[str],
        response_schema: dict[str, Any],
        timeout_seconds: float = 120.0,
    ) -> None:
        keys = [item.strip() for item in api_keys if item.strip()]
        if not keys:
            raise ValueError("At least one Gemini API key is required")
        if len(keys) != len(set(keys)):
            raise ValueError("Gemini API key list contains duplicates")
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install the pinned google-genai SDK for live T12 calls") from exc
        self._genai = genai
        self._types = types
        self._clients = [genai.Client(api_key=key) for key in keys]
        self._slot = 0
        self._response_schema = response_schema
        self._timeout_seconds = timeout_seconds
        self._sdk_version = importlib.metadata.version("google-genai")

    @property
    def sdk_version(self) -> str:
        return self._sdk_version

    @property
    def credential_count(self) -> int:
        return len(self._clients)

    @staticmethod
    def _is_quota_error(exc: Exception) -> bool:
        code = getattr(exc, "code", None)
        status = str(getattr(exc, "status", "")).upper()
        text = str(exc).upper()
        return code == 429 or "RESOURCE_EXHAUSTED" in status or "RESOURCE_EXHAUSTED" in text or "429" in text

    def complete(self, request: LLMCallRequest) -> LLMCallResponse:
        if request.provider != self.provider:
            raise ValueError("Gemini backend received a request for another provider")
        if request.seed is not None:
            raise ValueError("T12 does not claim Gemini seed support")
        last_error: Exception | None = None
        starting_slot = self._slot
        for offset in range(len(self._clients)):
            slot = (starting_slot + offset) % len(self._clients)
            started = time.perf_counter()
            try:
                response = self._clients[slot].models.generate_content(
                    model=request.model_id,
                    contents=request.prompt,
                    config=self._types.GenerateContentConfig(
                        temperature=request.temperature,
                        max_output_tokens=request.max_tokens,
                        response_mime_type="application/json",
                        response_json_schema=self._response_schema,
                        automatic_function_calling=self._types.AutomaticFunctionCallingConfig(
                            disable=True
                        ),
                        http_options=self._types.HttpOptions(timeout=int(self._timeout_seconds * 1000)),
                    ),
                )
            except Exception as exc:
                last_error = exc
                if self._is_quota_error(exc) and offset + 1 < len(self._clients):
                    continue
                raise
            self._slot = slot
            latency_ms = round((time.perf_counter() - started) * 1000)
            raw_text = response.text
            if not raw_text:
                raise RuntimeError("Gemini response contained no text")
            usage = getattr(response, "usage_metadata", None)
            model_version = str(getattr(response, "model_version", None) or request.model_version)
            if model_version != request.model_version:
                raise RuntimeError(
                    f"Gemini model version drift: expected={request.model_version}, actual={model_version}"
                )
            dump = response.model_dump(mode="json", exclude_none=False)
            if isinstance(dump, dict):
                dump["fourgraph_credential_slot"] = slot
            return LLMCallResponse(
                raw_text=raw_text,
                provider=self.provider,
                model_id=request.model_id,
                model_version=model_version,
                request_id=getattr(response, "response_id", None),
                input_tokens=getattr(usage, "prompt_token_count", None),
                output_tokens=getattr(usage, "candidates_token_count", None),
                latency_ms=latency_ms,
                endpoint=self.endpoint,
                sdk_version=self._sdk_version,
                provider_response_json=json.dumps(
                    dump, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
                ),
            )
        assert last_error is not None
        raise last_error
