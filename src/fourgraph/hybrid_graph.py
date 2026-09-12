"""Skeleton-preserving Hybrid H1 prompting, parsing, validation, and artifacts."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fourgraph.causalds_public import PublicLLMGraphInput
from fourgraph.graph_adapters import make_hybrid_graph_artifact
from fourgraph.graph_contract import EdgeAuditRecord, GraphArtifact, sha256_hex
from fourgraph.llm_backend import LLMBackend, LLMCallRequest, LLMCallResponse
from fourgraph.partial_graph import PartialGraph


HYBRID_RESPONSE_SCHEMA_VERSION = "fourgraph.hybrid_orientation_response.v1"
ORIENTATIONS = frozenset({"left_causes_right", "right_causes_left"})


@dataclass(frozen=True, order=True)
class OrientationDecision:
    left: str
    right: str
    relation: str
    confidence: float
    rationale: str


@dataclass(frozen=True)
class ParsedHybridGraph:
    graph: PartialGraph
    decisions: tuple[OrientationDecision, ...]
    edge_audit: tuple[EdgeAuditRecord, ...]


@dataclass(frozen=True)
class HybridPolicy:
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
        if self.temperature != 0:
            raise ValueError("Hybrid H1 must reuse T08 temperature=0")
        if isinstance(self.max_tokens, bool) or not isinstance(self.max_tokens, int) or self.max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        if isinstance(self.max_validation_retries, bool) or not isinstance(self.max_validation_retries, int) or self.max_validation_retries < 0:
            raise ValueError("max_validation_retries must be non-negative")
        if self.seed is not None:
            raise ValueError("T10 must reuse the T08 null seed")
        if not self.builder_version:
            raise ValueError("builder_version cannot be empty")


@dataclass(frozen=True)
class HybridBuildAttempt:
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
class HybridBuildResult:
    scene_id: str
    parent_artifact_sha256: str
    unresolved_edge_count: int
    artifact: GraphArtifact | None
    decisions: tuple[OrientationDecision, ...]
    attempts: tuple[HybridBuildAttempt, ...]
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
            "parent_artifact_sha256": self.parent_artifact_sha256,
            "unresolved_edge_count": self.unresolved_edge_count,
            "orientations_audited": len(self.decisions) if self.success else 0,
            "graph_sha256": self.artifact.graph_sha256 if self.artifact else None,
            "graph_artifact_sha256": self.artifact.artifact_sha256 if self.artifact else None,
            "attempts": [attempt.manifest_record() for attempt in self.attempts],
        }


def unresolved_pairs(parent: GraphArtifact) -> tuple[tuple[str, str], ...]:
    if parent.graph_method != "scd" or parent.graph_type != "cpdag":
        raise ValueError("Hybrid parent must be a raw SCD CPDAG")
    return tuple(sorted(parent.partial_graph.undirected))


def render_hybrid_prompt(evidence: PublicLLMGraphInput, parent: GraphArtifact, template: str) -> str:
    if evidence.scene_id != parent.scene_id or evidence.variable_map.node_ids != parent.nodes:
        raise ValueError("Public semantics and parent CPDAG do not share one scene/node universe")
    placeholders = (
        "{{VARIABLES_JSON}}",
        "{{COMPELLED_EDGES_JSON}}",
        "{{UNRESOLVED_EDGES_JSON}}",
        "{{STORY}}",
    )
    if any(template.count(item) != 1 for item in placeholders):
        raise ValueError("Hybrid prompt placeholders must each occur exactly once")
    variables = evidence.variable_map.semantic_builder_view()["nodes"]
    compelled = [
        {"source": source, "target": target}
        for source, target in sorted(parent.partial_graph.directed)
    ]
    unresolved = [
        {"left": left, "right": right}
        for left, right in unresolved_pairs(parent)
    ]
    return (
        template.replace("{{VARIABLES_JSON}}", json.dumps(variables, ensure_ascii=False, indent=2, sort_keys=True))
        .replace("{{COMPELLED_EDGES_JSON}}", json.dumps(compelled, ensure_ascii=False, indent=2, sort_keys=True))
        .replace("{{UNRESOLVED_EDGES_JSON}}", json.dumps(unresolved, ensure_ascii=False, indent=2, sort_keys=True))
        .replace("{{STORY}}", evidence.story)
    )


def _retry_prompt(base_prompt: str, raw_text: str, error: str) -> str:
    return (
        base_prompt
        + "\n\nVALIDATION RETRY:\n"
        + "The previous response was invalid. Return a complete replacement JSON object using only the same permitted evidence. Choose all directions jointly; do not repair the skeleton or compelled edges.\n"
        + f"VALIDATOR ERROR: {error}\n"
        + "PREVIOUS RESPONSE:\n"
        + raw_text
    )


def parse_hybrid_response(raw_text: str, parent: GraphArtifact) -> ParsedHybridGraph:
    value = json.loads(raw_text)
    if not isinstance(value, dict) or set(value) != {"schema_version", "orientation_decisions"}:
        raise ValueError("Response must contain exactly schema_version and orientation_decisions")
    if value["schema_version"] != HYBRID_RESPONSE_SCHEMA_VERSION:
        raise ValueError("Unsupported Hybrid orientation response schema version")
    raw_decisions = value["orientation_decisions"]
    if not isinstance(raw_decisions, list):
        raise ValueError("orientation_decisions must be an array")

    decisions: list[OrientationDecision] = []
    for item in raw_decisions:
        required = {"left", "right", "relation", "confidence", "rationale"}
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError("Orientation decision has missing or unknown fields")
        left, right = str(item["left"]), str(item["right"])
        if left >= right:
            raise ValueError("Orientation endpoints must preserve left < right ordering")
        relation = str(item["relation"])
        if relation not in ORIENTATIONS:
            raise ValueError(f"Unsupported Hybrid orientation: {relation}")
        confidence = item["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("Orientation confidence must be finite and in [0, 1]")
        rationale = str(item["rationale"]).strip()
        if not rationale:
            raise ValueError("Orientation rationale cannot be empty")
        decisions.append(OrientationDecision(left, right, relation, float(confidence), rationale))

    actual_pairs = [(item.left, item.right) for item in decisions]
    expected = unresolved_pairs(parent)
    if len(actual_pairs) != len(set(actual_pairs)):
        raise ValueError("Orientation decisions contain duplicate pairs")
    if set(actual_pairs) != set(expected) or len(actual_pairs) != len(expected):
        raise ValueError("Orientation decisions do not cover the exact unresolved edge set")
    decisions.sort()

    directed = list(parent.partial_graph.directed)
    audit: list[EdgeAuditRecord] = []
    for step, decision in enumerate(decisions):
        if decision.relation == "left_causes_right":
            source, target = decision.left, decision.right
        else:
            source, target = decision.right, decision.left
        directed.append((source, target))
        audit.append(
            EdgeAuditRecord.build(
                step=step,
                source=source,
                target=target,
                action="orient",
                before_mark="undirected",
                after_mark="directed",
                actor="hybrid",
                reason=decision.rationale,
                arbitrary=False,
                confidence=decision.confidence,
            )
        )
    return ParsedHybridGraph(
        PartialGraph.build(parent.nodes, directed=directed),
        tuple(decisions),
        tuple(audit),
    )


def build_hybrid_graph(
    evidence: PublicLLMGraphInput,
    parent: GraphArtifact,
    *,
    backend: LLMBackend,
    policy: HybridPolicy,
    prompt_template: str,
    config_sha256: str,
) -> HybridBuildResult:
    """Orient one parent CPDAG; invalid outputs retry without heuristic repair."""

    policy.validate()
    base_prompt = render_hybrid_prompt(evidence, parent, prompt_template)
    prompt = base_prompt
    attempts: list[HybridBuildAttempt] = []
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
        actual = (response.provider, response.model_id, response.model_version)
        expected = (policy.provider, policy.model_id, policy.model_version)
        if actual != expected:
            raise RuntimeError(f"LLM backend identity mismatch: expected={expected}, actual={actual}")
        try:
            parsed = parse_hybrid_response(response.raw_text, parent)
            artifact = make_hybrid_graph_artifact(
                parent_scd=parent,
                graph=parsed.graph,
                builder_id="fourgraph.hybrid_h1_builder",
                builder_version=policy.builder_version,
                config_sha256=config_sha256,
                input_artifact_sha256=(*evidence.input_artifact_sha256, parent.artifact_sha256),
                seed=policy.seed,
                edge_audit=parsed.edge_audit,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            final_error = str(exc)
            attempts.append(HybridBuildAttempt(attempt_number, request.prompt_sha256, request.prompt, response.raw_sha256, response.raw_text, response, final_error))
            if attempt_number < policy.max_validation_retries:
                prompt = _retry_prompt(base_prompt, response.raw_text, final_error)
            continue

        attempts.append(HybridBuildAttempt(attempt_number, request.prompt_sha256, request.prompt, response.raw_sha256, response.raw_text, response, None))
        return HybridBuildResult(
            evidence.scene_id,
            parent.artifact_sha256,
            len(unresolved_pairs(parent)),
            artifact,
            parsed.decisions,
            tuple(attempts),
            None,
        )
    return HybridBuildResult(
        evidence.scene_id,
        parent.artifact_sha256,
        len(unresolved_pairs(parent)),
        None,
        (),
        tuple(attempts),
        final_error,
    )


def load_prompt_template(path: str | Path) -> tuple[str, str]:
    content = Path(path).read_text(encoding="utf-8")
    return content, sha256_hex(content.encode("utf-8"))


def load_graph_jsonl(path: str | Path) -> dict[str, GraphArtifact]:
    artifacts: dict[str, GraphArtifact] = {}
    for line_number, line in enumerate(Path(path).read_bytes().splitlines(), start=1):
        if not line:
            continue
        artifact = GraphArtifact.from_json_bytes(line + b"\n")
        if artifact.scene_id in artifacts:
            raise ValueError(f"Duplicate graph scene at line {line_number}")
        artifacts[artifact.scene_id] = artifact
    return artifacts
