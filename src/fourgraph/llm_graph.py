"""Public-story-only LLM graph prompting, parsing, retry, and artifacts."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from fourgraph.causalds_public import PublicLLMGraphInput
from fourgraph.graph_adapters import make_llm_graph_artifact
from fourgraph.graph_contract import EdgeAuditRecord, GraphArtifact, sha256_hex
from fourgraph.llm_backend import LLMBackend, LLMCallRequest, LLMCallResponse
from fourgraph.partial_graph import PartialGraph


LLM_RESPONSE_SCHEMA_VERSION = "fourgraph.llm_graph_response.v1"
RELATIONS = frozenset(
    {"left_causes_right", "right_causes_left", "no_direct_edge"}
)


@dataclass(frozen=True, order=True)
class PairDecision:
    left: str
    right: str
    relation: str
    confidence: float
    rationale: str


@dataclass(frozen=True)
class ParsedLLMGraph:
    graph: PartialGraph
    decisions: tuple[PairDecision, ...]
    edge_audit: tuple[EdgeAuditRecord, ...]


@dataclass(frozen=True)
class LLMGraphPolicy:
    provider: str
    model_id: str
    model_version: str
    temperature: float
    max_tokens: int
    seed: int | None
    max_validation_retries: int
    builder_version: str = "v1"

    def validate(self) -> None:
        if not self.provider or not self.model_id or not self.model_version:
            raise ValueError("Provider, model_id, and model_version must be pinned")
        if (
            isinstance(self.temperature, bool)
            or not isinstance(self.temperature, (int, float))
            or not math.isfinite(self.temperature)
            or self.temperature < 0
        ):
            raise ValueError("Temperature must be finite and non-negative")
        if (
            isinstance(self.max_tokens, bool)
            or not isinstance(self.max_tokens, int)
            or self.max_tokens <= 0
        ):
            raise ValueError("max_tokens must be a positive integer")
        if (
            isinstance(self.max_validation_retries, bool)
            or not isinstance(self.max_validation_retries, int)
            or self.max_validation_retries < 0
        ):
            raise ValueError("max_validation_retries must be non-negative")
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise ValueError("seed must be an integer or null")
        if not self.builder_version:
            raise ValueError("builder_version cannot be empty")


@dataclass(frozen=True)
class LLMBuildAttempt:
    attempt: int
    prompt_sha256: str
    prompt: str
    raw_sha256: str
    raw_text: str
    response: LLMCallResponse
    validation_error: str | None

    def manifest_record(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "prompt_sha256": self.prompt_sha256,
            "raw_sha256": self.raw_sha256,
            "provider": self.response.provider,
            "model_id": self.response.model_id,
            "model_version": self.response.model_version,
            "request_id": self.response.request_id,
            "system_fingerprint": self.response.system_fingerprint,
            "endpoint": self.response.endpoint,
            "sdk_version": self.response.sdk_version,
            "service_tier": self.response.service_tier,
            "input_tokens": self.response.input_tokens,
            "output_tokens": self.response.output_tokens,
            "latency_ms": self.response.latency_ms,
            "validation_error": self.validation_error,
        }

    def raw_log_record(self, scene_id: str) -> dict[str, Any]:
        return {
            "raw_log_schema_version": "fourgraph.llm_raw_call.v1",
            "scene_id": scene_id,
            "attempt": self.attempt,
            "prompt_sha256": self.prompt_sha256,
            "prompt": self.prompt,
            "raw_text": self.raw_text,
            "provider": self.response.provider,
            "model_id": self.response.model_id,
            "model_version": self.response.model_version,
            "request_id": self.response.request_id,
            "system_fingerprint": self.response.system_fingerprint,
            "input_tokens": self.response.input_tokens,
            "output_tokens": self.response.output_tokens,
            "latency_ms": self.response.latency_ms,
            "endpoint": self.response.endpoint,
            "sdk_version": self.response.sdk_version,
            "service_tier": self.response.service_tier,
            "provider_response_json": self.response.provider_response_json,
        }


@dataclass(frozen=True)
class LLMGraphBuildResult:
    scene_id: str
    artifact: GraphArtifact | None
    attempts: tuple[LLMBuildAttempt, ...]
    final_error: str | None

    @property
    def success(self) -> bool:
        return self.artifact is not None

    @property
    def retry_count(self) -> int:
        return max(0, len(self.attempts) - 1)

    def manifest_record(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "success": self.success,
            "retry_count": self.retry_count,
            "final_error": self.final_error,
            "graph_sha256": (
                self.artifact.graph_sha256 if self.artifact is not None else None
            ),
            "graph_artifact_sha256": (
                self.artifact.artifact_sha256
                if self.artifact is not None
                else None
            ),
            "attempts": [attempt.manifest_record() for attempt in self.attempts],
        }


def expected_pairs(nodes: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    return tuple(combinations(nodes, 2))


def render_llm_graph_prompt(
    evidence: PublicLLMGraphInput,
    template: str,
) -> str:
    placeholders = ("{{VARIABLES_JSON}}", "{{PAIRS_JSON}}", "{{STORY}}")
    if any(template.count(placeholder) != 1 for placeholder in placeholders):
        raise ValueError("Prompt template placeholders must each occur exactly once")
    variables = evidence.variable_map.semantic_builder_view()["nodes"]
    pairs = [
        {"left": left, "right": right}
        for left, right in expected_pairs(evidence.variable_map.node_ids)
    ]
    return (
        template.replace(
            "{{VARIABLES_JSON}}",
            json.dumps(variables, ensure_ascii=False, indent=2, sort_keys=True),
        )
        .replace(
            "{{PAIRS_JSON}}",
            json.dumps(pairs, ensure_ascii=False, indent=2, sort_keys=True),
        )
        .replace("{{STORY}}", evidence.story)
    )


def _retry_prompt(base_prompt: str, raw_text: str, error: str) -> str:
    return (
        base_prompt
        + "\n\nVALIDATION RETRY:\n"
        + "The previous response was invalid. Return a complete replacement JSON "
        + "object using the same evidence and instructions. Do not discuss the error.\n"
        + f"VALIDATOR ERROR: {error}\n"
        + "PREVIOUS RESPONSE:\n"
        + raw_text
    )


def parse_llm_graph_response(raw_text: str, nodes: tuple[str, ...]) -> ParsedLLMGraph:
    value = json.loads(raw_text)
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "pair_decisions",
    }:
        raise ValueError("Response must contain exactly schema_version and pair_decisions")
    if value["schema_version"] != LLM_RESPONSE_SCHEMA_VERSION:
        raise ValueError("Unsupported LLM graph response schema version")
    raw_decisions = value["pair_decisions"]
    if not isinstance(raw_decisions, list):
        raise ValueError("pair_decisions must be an array")

    decisions: list[PairDecision] = []
    for item in raw_decisions:
        required = {"left", "right", "relation", "confidence", "rationale"}
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError("Pair decision has missing or unknown fields")
        left = str(item["left"])
        right = str(item["right"])
        if left >= right:
            raise ValueError("Pair endpoints must preserve left < right ordering")
        relation = str(item["relation"])
        if relation not in RELATIONS:
            raise ValueError(f"Unsupported pair relation: {relation}")
        confidence = item["confidence"]
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("Pair confidence must be finite and in [0, 1]")
        rationale = str(item["rationale"]).strip()
        if not rationale:
            raise ValueError("Pair rationale cannot be empty")
        decisions.append(
            PairDecision(left, right, relation, float(confidence), rationale)
        )

    pairs = [(item.left, item.right) for item in decisions]
    expected = expected_pairs(nodes)
    if len(pairs) != len(set(pairs)):
        raise ValueError("Pair decisions contain duplicates")
    if set(pairs) != set(expected) or len(pairs) != len(expected):
        raise ValueError("Pair decisions do not cover the exact canonical pair set")
    decisions.sort()

    directed: list[tuple[str, str]] = []
    audit: list[EdgeAuditRecord] = []
    for step, decision in enumerate(decisions):
        if decision.relation == "left_causes_right":
            source, target = decision.left, decision.right
            action, after_mark = "add", "directed"
            directed.append((source, target))
        elif decision.relation == "right_causes_left":
            source, target = decision.right, decision.left
            action, after_mark = "add", "directed"
            directed.append((source, target))
        else:
            source, target = decision.left, decision.right
            action, after_mark = "reject", "absent"
        audit.append(
            EdgeAuditRecord.build(
                step=step,
                source=source,
                target=target,
                action=action,
                before_mark="absent",
                after_mark=after_mark,
                actor="llm",
                reason=decision.rationale,
                arbitrary=False,
                confidence=decision.confidence,
            )
        )
    graph = PartialGraph.build(nodes, directed=directed)
    return ParsedLLMGraph(graph, tuple(decisions), tuple(audit))


def _validate_response_identity(
    response: LLMCallResponse, policy: LLMGraphPolicy
) -> None:
    actual = (response.provider, response.model_id, response.model_version)
    expected = (policy.provider, policy.model_id, policy.model_version)
    if actual != expected:
        raise RuntimeError(
            f"LLM backend identity mismatch: expected={expected}, actual={actual}"
        )


def build_llm_graph(
    evidence: PublicLLMGraphInput,
    *,
    backend: LLMBackend,
    policy: LLMGraphPolicy,
    prompt_template: str,
    config_sha256: str,
) -> LLMGraphBuildResult:
    """Build one DAG; validation retries never add non-public evidence."""

    policy.validate()
    base_prompt = render_llm_graph_prompt(evidence, prompt_template)
    prompt = base_prompt
    attempts: list[LLMBuildAttempt] = []
    final_error: str | None = None
    for attempt_number in range(policy.max_validation_retries + 1):
        request = LLMCallRequest(
            scene_id=evidence.scene_id,
            attempt=attempt_number,
            prompt=prompt,
            provider=policy.provider,
            model_id=policy.model_id,
            model_version=policy.model_version,
            temperature=policy.temperature,
            max_tokens=policy.max_tokens,
            seed=policy.seed,
        )
        response = backend.complete(request)
        _validate_response_identity(response, policy)
        try:
            parsed = parse_llm_graph_response(
                response.raw_text, evidence.variable_map.node_ids
            )
        except (json.JSONDecodeError, ValueError) as exc:
            final_error = str(exc)
            attempts.append(
                LLMBuildAttempt(
                    attempt=attempt_number,
                    prompt_sha256=request.prompt_sha256,
                    prompt=request.prompt,
                    raw_sha256=response.raw_sha256,
                    raw_text=response.raw_text,
                    response=response,
                    validation_error=final_error,
                )
            )
            if attempt_number < policy.max_validation_retries:
                prompt = _retry_prompt(base_prompt, response.raw_text, final_error)
            continue

        attempts.append(
            LLMBuildAttempt(
                attempt=attempt_number,
                prompt_sha256=request.prompt_sha256,
                prompt=request.prompt,
                raw_sha256=response.raw_sha256,
                raw_text=response.raw_text,
                response=response,
                validation_error=None,
            )
        )
        artifact = make_llm_graph_artifact(
            scene_id=evidence.scene_id,
            graph=parsed.graph,
            builder_id="fourgraph.llm_graph_builder",
            builder_version=policy.builder_version,
            config_sha256=config_sha256,
            input_artifact_sha256=evidence.input_artifact_sha256,
            seed=policy.seed,
            edge_audit=parsed.edge_audit,
        )
        return LLMGraphBuildResult(
            scene_id=evidence.scene_id,
            artifact=artifact,
            attempts=tuple(attempts),
            final_error=None,
        )
    return LLMGraphBuildResult(
        scene_id=evidence.scene_id,
        artifact=None,
        attempts=tuple(attempts),
        final_error=final_error,
    )


def load_prompt_template(path: str | Path) -> tuple[str, str]:
    content = Path(path).read_text(encoding="utf-8")
    return content, sha256_hex(content.encode("utf-8"))
