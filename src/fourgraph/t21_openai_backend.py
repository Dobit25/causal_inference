"""T21-specific OpenAI Responses transport with complete token/audit capture."""

from __future__ import annotations

import importlib.metadata
import json
import time
from typing import Any


class T21OpenAIBackend:
    def __init__(
        self,
        *,
        api_key: str,
        response_schema: dict[str, Any],
        schema_name: str,
        model_snapshot: str,
        max_output_tokens: int,
        timeout_seconds: float,
        transport_max_retries: int,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API key cannot be empty")
        from openai import OpenAI

        self.client = OpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=transport_max_retries,
        )
        self.schema = response_schema
        self.schema_name = schema_name
        self.model_snapshot = model_snapshot
        self.max_output_tokens = max_output_tokens
        self.sdk_version = importlib.metadata.version("openai")

    def call(self, *, call_id: str, prompt: str, attempt: int) -> dict[str, Any]:
        started = time.perf_counter()
        response = self.client.responses.create(
            model=self.model_snapshot,
            input=prompt,
            max_output_tokens=self.max_output_tokens,
            temperature=0,
            reasoning={"effort": "none"},
            text={
                "format": {
                    "type": "json_schema",
                    "name": self.schema_name,
                    "schema": self.schema,
                    "strict": True,
                }
            },
            service_tier="default",
            store=False,
            metadata={"task": "T21", "call_id": call_id, "attempt": str(attempt)},
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        model = str(getattr(response, "model", ""))
        if getattr(response, "status", None) != "completed":
            raise RuntimeError(f"OpenAI response incomplete: {getattr(response, 'status', None)!r}")
        if model != self.model_snapshot:
            raise RuntimeError(f"Model snapshot drift: {model} != {self.model_snapshot}")
        if not response.output_text:
            raise RuntimeError("OpenAI response contained no output text")
        usage = getattr(response, "usage", None)
        output_details = getattr(usage, "output_tokens_details", None)
        input_details = getattr(usage, "input_tokens_details", None)
        return {
            "raw_log_schema_version": "fourgraph.p1_t21_raw_call.v1",
            "call_id": call_id,
            "attempt": attempt,
            "prompt": prompt,
            "raw_text": response.output_text,
            "provider": "openai",
            "model_snapshot": model,
            "request_id": getattr(response, "_request_id", None),
            "system_fingerprint": getattr(response, "system_fingerprint", None),
            "sdk_version": self.sdk_version,
            "service_tier": getattr(response, "service_tier", None),
            "input_tokens": getattr(usage, "input_tokens", None),
            "cached_input_tokens": getattr(input_details, "cached_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "reasoning_tokens": getattr(output_details, "reasoning_tokens", None),
            "latency_ms": latency_ms,
            "provider_response_json": json.dumps(
                response.model_dump(mode="json"),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
