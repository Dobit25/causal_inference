"""Fixed graph-only reasoner contract and T12 scoring semantics."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from itertools import combinations, permutations
from pathlib import Path
from typing import Any, Iterable, Mapping

from fourgraph.causalds_public import (
    load_causalds_variable_map,
    read_json_object,
    resolve_public_artifact,
    sha256_file,
)
from fourgraph.graph_contract import (
    GraphArtifact,
    VariableMap,
    canonical_json_bytes,
    sha256_hex,
)
from fourgraph.llm_backend import LLMBackend, LLMCallRequest, LLMCallResponse
from fourgraph.partial_graph import PartialGraph, unshielded_colliders


QUERY_SCHEMA_VERSION = "fourgraph.reasoner_query.v1"
RESPONSE_SCHEMA_VERSION = "fourgraph.reasoner_response.v1"
SCORE_SCHEMA_VERSION = "fourgraph.reasoner_score.v1"

TASKS = (
    "identification__one_valid_adjustment_set",
    "identification__all_minimal_adjustment_sets",
    "identification__minimal_adjustment_set_size",
    "identification__n_valid_adjustment_sets",
    "bias_diagnostic__forbidden_controls_list",
)
TASK_FIELDS = {
    TASKS[0]: "adjust",
    TASKS[1]: "adjustment_sets",
    TASKS[2]: "k",
    TASKS[3]: "n",
    TASKS[4]: "forbidden",
}
_ATE_PATTERN = re.compile(
    r"population ATE of \*\*(?P<treatment>.+?)\*\* on \*\*(?P<outcome>.+?)\*\*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReasonerQuery:
    scene_id: str
    task_id: str
    treatment: str
    outcome: str
    candidate_variables: tuple[str, ...]
    response_field: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": QUERY_SCHEMA_VERSION,
            "scene_id": self.scene_id,
            "task_id": self.task_id,
            "treatment": self.treatment,
            "outcome": self.outcome,
            "candidate_variables": list(self.candidate_variables),
            "response_field": self.response_field,
            "allowed_sentinels": ["no_backdoor", "non_id", "undetermined"],
        }

    @property
    def sha256(self) -> str:
        return sha256_hex(canonical_json_bytes(self.to_dict()))


@dataclass(frozen=True)
class ParsedReasonerAnswer:
    status: str
    answer: Any

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "answer": self.answer}


@dataclass(frozen=True)
class TaskSemantics:
    """All accepted graph-derived answers for one task and one DAG."""

    task_id: str
    accepted: tuple[Any, ...]


@dataclass(frozen=True)
class ConservativeTarget:
    status: str
    accepted: tuple[Any, ...]
    extension_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "accepted": list(self.accepted),
            "compatible_dag_count": self.extension_count,
        }


@dataclass(frozen=True)
class OfficialTarget:
    task_id: str
    accepted: tuple[Any, ...]
    ground_truth_sha256: str


@dataclass(frozen=True)
class ReasonerPolicy:
    provider: str
    model_id: str
    model_version: str
    temperature: float
    max_tokens: int
    max_validation_retries: int

    def validate(self) -> None:
        if not self.provider or not self.model_id or not self.model_version:
            raise ValueError("Reasoner provider/model identity must be pinned")
        if self.temperature != 0:
            raise ValueError("T12 reasoner temperature must be zero")
        if self.max_tokens <= 0 or self.max_validation_retries < 0:
            raise ValueError("Invalid T12 token/retry policy")


@dataclass(frozen=True)
class ReasonerAttempt:
    attempt: int
    prompt: str
    response: LLMCallResponse
    validation_error: str | None

    def raw_log_record(self, call_id: str) -> dict[str, Any]:
        return {
            "raw_log_schema_version": "fourgraph.reasoner_raw_call.v1",
            "scene_id": call_id,
            "attempt": self.attempt,
            "prompt": self.prompt,
            "prompt_sha256": sha256_hex(self.prompt.encode("utf-8")),
            "raw_text": self.response.raw_text,
            "raw_sha256": self.response.raw_sha256,
            "provider": self.response.provider,
            "model_id": self.response.model_id,
            "model_version": self.response.model_version,
            "request_id": self.response.request_id,
            "input_tokens": self.response.input_tokens,
            "output_tokens": self.response.output_tokens,
            "latency_ms": self.response.latency_ms,
            "endpoint": self.response.endpoint,
            "sdk_version": self.response.sdk_version,
            "provider_response_json": self.response.provider_response_json,
            "validation_error": self.validation_error,
        }


@dataclass(frozen=True)
class ReasonerRunResult:
    parsed: ParsedReasonerAnswer | None
    attempts: tuple[ReasonerAttempt, ...]
    final_error: str | None


class ReasonerReplayBackend:
    """Replay T12 raw calls by opaque call identity and prompt hash."""

    def __init__(self, records: Mapping[tuple[str, int], tuple[str, LLMCallResponse]]) -> None:
        self._records = dict(records)

    @classmethod
    def load(cls, path: Path) -> "ReasonerReplayBackend":
        records: dict[tuple[str, int], tuple[str, LLMCallResponse]] = {}
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line:
                continue
            value = json.loads(line)
            if value.get("raw_log_schema_version") != "fourgraph.reasoner_raw_call.v1":
                raise ValueError(f"Unsupported T12 raw record at line {number}")
            key = (str(value["scene_id"]), int(value["attempt"]))
            if key in records:
                raise ValueError(f"Duplicate T12 replay key: {key}")
            if sha256_hex(str(value["prompt"]).encode("utf-8")) != value["prompt_sha256"]:
                raise ValueError(f"T12 raw prompt hash mismatch at line {number}")
            response = LLMCallResponse(
                raw_text=str(value["raw_text"]),
                provider=str(value["provider"]),
                model_id=str(value["model_id"]),
                model_version=str(value["model_version"]),
                request_id=value.get("request_id"),
                input_tokens=value.get("input_tokens"),
                output_tokens=value.get("output_tokens"),
                latency_ms=value.get("latency_ms"),
                endpoint=value.get("endpoint"),
                sdk_version=value.get("sdk_version"),
                provider_response_json=value.get("provider_response_json"),
            )
            records[key] = (str(value["prompt_sha256"]), response)
        return cls(records)

    def complete(self, request: LLMCallRequest) -> LLMCallResponse:
        key = (request.scene_id, request.attempt)
        if key not in self._records:
            raise RuntimeError(f"T12 replay response is missing: {key}")
        prompt_hash, response = self._records[key]
        if request.prompt_sha256 != prompt_hash:
            raise RuntimeError(f"T12 replay prompt hash mismatch: {key}")
        return response

    def has_call(self, call_id: str) -> bool:
        return (call_id, 0) in self._records

    def has_attempt(self, call_id: str, attempt: int) -> bool:
        return (call_id, attempt) in self._records


def noncausal_glossary(variable_map: VariableMap) -> list[dict[str, str]]:
    """Return type metadata only; public semantic names are intentionally absent."""

    return [
        {"id": item.canonical_id, "type": item.variable_type}
        for item in variable_map.variables
    ]


def load_reasoner_query(
    source_root: Path, scene_id: str, task_id: str, *, variant: str = "clean"
) -> tuple[ReasonerQuery, VariableMap, str]:
    """Extract only structured query facts from the public task artifact."""

    if task_id not in TASKS:
        raise ValueError(f"Task is outside the frozen T12 family: {task_id}")
    variable_map, _ = load_causalds_variable_map(source_root, scene_id, variant=variant)
    path = resolve_public_artifact(source_root, scene_id, variant, "tasks")
    document = read_json_object(path, label="Public tasks")
    matches = [item for item in document.get("tasks", []) if item.get("task_id") == task_id]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one frozen task {task_id} in {scene_id}")
    task = matches[0]
    prompt = task.get("prompt")
    if not isinstance(prompt, str):
        raise ValueError("Public task prompt is missing")
    match = _ATE_PATTERN.search(prompt)
    if match is None:
        raise ValueError("Cannot extract treatment/outcome from public query")
    rename = variable_map.scd_rename_map()
    try:
        treatment = rename[match.group("treatment")]
        outcome = rename[match.group("outcome")]
    except KeyError as exc:
        raise ValueError("Query treatment/outcome is absent from public schema") from exc
    inputs = task.get("inputs") or {}
    input_key = "observed_vars" if task_id == TASKS[4] else "available_vars"
    public_candidates = inputs.get(input_key)
    if not isinstance(public_candidates, list):
        raise ValueError("Frozen task candidate list is malformed")
    candidates = tuple(sorted(rename[str(name)] for name in public_candidates))
    query = ReasonerQuery(
        scene_id=scene_id,
        task_id=task_id,
        treatment=treatment,
        outcome=outcome,
        candidate_variables=candidates,
        response_field=TASK_FIELDS[task_id],
    )
    return query, variable_map, sha256_file(path)


def compatible_dags(graph: PartialGraph) -> tuple[PartialGraph, ...]:
    """Enumerate exactly the DAG extensions represented by a small CPDAG."""

    if not graph.undirected:
        return (graph,)
    target_colliders = unshielded_colliders(graph)
    found: dict[frozenset[tuple[str, str]], PartialGraph] = {}
    for order in permutations(graph.nodes):
        position = {node: index for index, node in enumerate(order)}
        directed = frozenset(
            (a, b) if position[a] < position[b] else (b, a)
            for a, b in graph.skeleton
        )
        if not graph.directed.issubset(directed):
            continue
        candidate = PartialGraph.build(graph.nodes, directed=directed)
        if unshielded_colliders(candidate) == target_colliders:
            found[candidate.directed] = candidate
    if not found:
        raise ValueError("CPDAG has no compatible DAG extension")
    return tuple(found[key] for key in sorted(found, key=lambda x: sorted(x)))


def _children(dag: PartialGraph) -> dict[str, set[str]]:
    result = {node: set() for node in dag.nodes}
    for parent, child in dag.directed:
        result[parent].add(child)
    return result


def _parents(dag: PartialGraph) -> dict[str, set[str]]:
    result = {node: set() for node in dag.nodes}
    for parent, child in dag.directed:
        result[child].add(parent)
    return result


def _descendants(dag: PartialGraph, start: str) -> set[str]:
    children = _children(dag)
    seen: set[str] = set()
    stack = list(children[start])
    while stack:
        node = stack.pop()
        if node not in seen:
            seen.add(node)
            stack.extend(children[node])
    return seen


def _all_directed_paths(dag: PartialGraph, start: str, end: str) -> list[list[str]]:
    children = _children(dag)
    paths: list[list[str]] = []

    def visit(node: str, path: list[str]) -> None:
        if node == end:
            paths.append(path)
            return
        for child in sorted(children[node]):
            if child not in path:
                visit(child, path + [child])

    visit(start, [start])
    return paths


def _d_separated(
    nodes: Iterable[str], edges: set[tuple[str, str]], left: str, right: str, z: set[str]
) -> bool:
    """D-separation through the ancestral moral graph."""

    parents = {node: set() for node in nodes}
    for parent, child in edges:
        parents[child].add(parent)
    ancestors = {left, right} | set(z)
    stack = list(ancestors)
    while stack:
        node = stack.pop()
        for parent in parents[node]:
            if parent not in ancestors:
                ancestors.add(parent)
                stack.append(parent)
    moral = {node: set() for node in ancestors}
    for parent, child in edges:
        if parent in ancestors and child in ancestors:
            moral[parent].add(child)
            moral[child].add(parent)
    for child in ancestors:
        for a, b in combinations(sorted(parents[child] & ancestors), 2):
            moral[a].add(b)
            moral[b].add(a)
    if left in z or right in z:
        return True
    seen = set(z)
    stack = [left]
    while stack:
        node = stack.pop()
        if node == right:
            return False
        if node in seen:
            continue
        seen.add(node)
        stack.extend(moral[node] - seen - z)
    return True


def _valid_adjustment_sets(dag: PartialGraph, query: ReasonerQuery) -> tuple[tuple[str, ...], ...]:
    """Reproduce CausalDS's released graph.py policy (max size 5, max 100)."""

    descendants = _descendants(dag, query.treatment)
    paths = _all_directed_paths(dag, query.treatment, query.outcome)
    on_causal_path = {node for path in paths for node in path[1:-1]}
    forbidden = descendants - on_causal_path - {query.outcome}
    candidates = tuple(node for node in query.candidate_variables if node not in forbidden)
    removed = {(a, b) for path in paths for a, b in zip(path, path[1:])}
    backdoor_edges = set(dag.directed) - removed
    valid: list[tuple[str, ...]] = []
    for size in range(0, min(5, len(candidates)) + 1):
        for subset in combinations(candidates, size):
            if _d_separated(
                dag.nodes,
                backdoor_edges,
                query.treatment,
                query.outcome,
                set(subset),
            ):
                valid.append(tuple(sorted(subset)))
                if len(valid) == 100:
                    return tuple(valid)
    return tuple(valid)


def _forbidden_controls(dag: PartialGraph, query: ReasonerQuery) -> tuple[str, ...]:
    descendants = _descendants(dag, query.treatment)
    paths = _all_directed_paths(dag, query.treatment, query.outcome)
    on_causal_path = {node for path in paths for node in path[1:-1]}
    forbidden_desc = descendants - on_causal_path - {query.outcome}
    colliders = {
        middle
        for left, middle, right in unshielded_colliders(dag)
        if middle not in {query.treatment, query.outcome}
        and ({left, right} & (_ancestors_and_descendants(dag, query.treatment)))
        and ({left, right} & (_ancestors_and_descendants(dag, query.outcome)))
    }
    return tuple(sorted((forbidden_desc | colliders) & set(query.candidate_variables)))


def _ancestors_and_descendants(dag: PartialGraph, node: str) -> set[str]:
    parents = _parents(dag)
    ancestors = {node}
    stack = [node]
    while stack:
        current = stack.pop()
        for parent in parents[current]:
            if parent not in ancestors:
                ancestors.add(parent)
                stack.append(parent)
    return ancestors | _descendants(dag, node)


def task_semantics(dag: PartialGraph, query: ReasonerQuery) -> TaskSemantics:
    if dag.undirected:
        raise ValueError("Task semantics require a DAG")
    valid = _valid_adjustment_sets(dag, query)
    if query.task_id == TASKS[0]:
        accepted: tuple[Any, ...] = tuple(valid) if valid else ("no_backdoor",)
    elif query.task_id == TASKS[1]:
        if valid:
            minimum = min(map(len, valid))
            accepted = (tuple(item for item in valid if len(item) == minimum),)
        else:
            accepted = ("no_backdoor",)
    elif query.task_id == TASKS[2]:
        accepted = (min(map(len, valid)),) if valid else ("no_backdoor",)
    elif query.task_id == TASKS[3]:
        accepted = (len(valid),) if valid else ("no_backdoor",)
    elif query.task_id == TASKS[4]:
        accepted = (_forbidden_controls(dag, query),) if valid else ("no_backdoor",)
    else:  # pragma: no cover - guarded by query constructor
        raise ValueError("Unsupported task")
    return TaskSemantics(query.task_id, accepted)


def conservative_target(graph: PartialGraph, query: ReasonerQuery) -> ConservativeTarget:
    semantics = [task_semantics(dag, query) for dag in compatible_dags(graph)]
    if query.task_id == TASKS[0]:
        common = set(semantics[0].accepted)
        for item in semantics[1:]:
            common &= set(item.accepted)
        if common:
            return ConservativeTarget("answered", tuple(sorted(common, key=repr)), len(semantics))
    elif all(item.accepted == semantics[0].accepted for item in semantics[1:]):
        return ConservativeTarget("answered", semantics[0].accepted, len(semantics))
    return ConservativeTarget("undetermined", ("undetermined",), len(semantics))


def _canonical_answer(task_id: str, value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().lower()
    if task_id in {TASKS[0], TASKS[4]}:
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ValueError("Answer must be a list of canonical node IDs")
        return tuple(sorted(set(value)))
    if task_id == TASKS[1]:
        if not isinstance(value, list) or not all(isinstance(x, list) for x in value):
            raise ValueError("adjustment_sets must be a list of lists")
        return tuple(sorted({tuple(sorted(set(item))) for item in value}))
    if task_id in {TASKS[2], TASKS[3]}:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("Numeric answer must be a non-negative integer")
        return value
    raise ValueError("Unsupported task")


def parse_reasoner_response(raw_text: str, query: ReasonerQuery) -> ParsedReasonerAnswer:
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:].lstrip()
    elif text.startswith("```"):
        text = text[3:].lstrip()
    if text.endswith("```"):
        text = text[:-3].rstrip()
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {"schema_version", "status", "answer"}:
        raise ValueError("Reasoner response has missing or unknown fields")
    if value["schema_version"] != RESPONSE_SCHEMA_VERSION:
        raise ValueError("Unsupported reasoner response schema")
    status = value["status"]
    if status not in {"answered", "undetermined"}:
        raise ValueError("Reasoner status must be answered or undetermined")
    answer = value["answer"]
    if status == "undetermined":
        if answer != "undetermined":
            raise ValueError("Undetermined status requires the undetermined sentinel")
        return ParsedReasonerAnswer(status, answer)
    return ParsedReasonerAnswer(status, _canonical_answer(query.task_id, answer))


def score_answer(
    parsed: ParsedReasonerAnswer,
    official: OfficialTarget,
    uncertainty: ConservativeTarget,
) -> dict[str, Any]:
    oracle_correct = parsed.status == "answered" and parsed.answer in official.accepted
    if uncertainty.status == "undetermined":
        aware_correct = parsed.status == "undetermined"
    else:
        aware_correct = parsed.status == "answered" and parsed.answer in uncertainty.accepted
    return {
        "schema_version": SCORE_SCHEMA_VERSION,
        "oracle_answer_accuracy": bool(oracle_correct),
        "uncertainty_aware_correctness": bool(aware_correct),
    }


def render_reasoner_prompt(
    graph_artifact: GraphArtifact,
    query: ReasonerQuery,
    variable_map: VariableMap,
    template: str,
) -> str:
    placeholders = ("{{GRAPH_JSON}}", "{{QUERY_JSON}}", "{{GLOSSARY_JSON}}")
    if any(template.count(item) != 1 for item in placeholders):
        raise ValueError("Reasoner template placeholders must each occur exactly once")
    if graph_artifact.scene_id != query.scene_id or variable_map.scene_id != query.scene_id:
        raise ValueError("Reasoner inputs have different scene IDs")
    if graph_artifact.nodes != variable_map.node_ids:
        raise ValueError("Reasoner graph and variable universe disagree")
    return (
        template.replace("{{GRAPH_JSON}}", graph_artifact.reasoner_json_bytes().decode())
        .replace("{{QUERY_JSON}}", canonical_json_bytes(query.to_dict()).decode())
        .replace("{{GLOSSARY_JSON}}", canonical_json_bytes(noncausal_glossary(variable_map)).decode())
    )


def run_fixed_reasoner(
    *,
    graph_artifact: GraphArtifact,
    query: ReasonerQuery,
    variable_map: VariableMap,
    backend: LLMBackend,
    policy: ReasonerPolicy,
    prompt_template: str,
    call_id: str | None = None,
) -> ReasonerRunResult:
    policy.validate()
    base = render_reasoner_prompt(graph_artifact, query, variable_map, prompt_template)
    prompt = base
    attempts: list[ReasonerAttempt] = []
    error: str | None = None
    call_id = call_id or f"{query.scene_id}:{query.task_id}:{graph_artifact.graph_sha256}"
    for attempt in range(policy.max_validation_retries + 1):
        request = LLMCallRequest(
            scene_id=call_id,
            attempt=attempt,
            prompt=prompt,
            provider=policy.provider,
            model_id=policy.model_id,
            model_version=policy.model_version,
            temperature=policy.temperature,
            max_tokens=policy.max_tokens,
            seed=None,
        )
        response = backend.complete(request)
        if (response.provider, response.model_id, response.model_version) != (
            policy.provider,
            policy.model_id,
            policy.model_version,
        ):
            raise RuntimeError("Reasoner backend model identity drift")
        try:
            parsed = parse_reasoner_response(response.raw_text, query)
        except (json.JSONDecodeError, ValueError) as exc:
            error = str(exc)
            attempts.append(ReasonerAttempt(attempt, prompt, response, error))
            prompt = (
                base
                + "\nVALIDATION RETRY: Return a complete replacement JSON object only.\n"
                + f"ERROR: {error}\nPREVIOUS RESPONSE:\n{response.raw_text}"
            )
            continue
        attempts.append(ReasonerAttempt(attempt, prompt, response, None))
        return ReasonerRunResult(parsed, tuple(attempts), None)
    return ReasonerRunResult(None, tuple(attempts), error)
