"""T12 v2 design primitives without changing the frozen T12 v1 run."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex
from fourgraph.partial_graph import PartialGraph
from fourgraph.reasoner import (
    TASKS,
    ConservativeTarget,
    ParsedReasonerAnswer,
    ReasonerQuery,
    TaskSemantics,
    _canonical_answer,
    _descendants,
    _d_separated,
    compatible_dags,
)


V2_QUERY_SCHEMA_VERSION = "fourgraph.reasoner_query.v2"
V2_CACHE_SCHEMA_VERSION = "fourgraph.reasoner_cache_key.v1"


def v2_query_view(query: ReasonerQuery) -> dict[str, Any]:
    """Prompt view without scene identity or public semantics."""

    return {
        "schema_version": V2_QUERY_SCHEMA_VERSION,
        "task_id": query.task_id,
        "treatment": query.treatment,
        "outcome": query.outcome,
        "candidate_variables": list(query.candidate_variables),
        "response_field": query.response_field,
        "allowed_sentinels": ["no_backdoor", "non_id", "undetermined"],
    }


def _standard_valid_adjustment_sets(
    dag: PartialGraph, query: ReasonerQuery
) -> tuple[tuple[str, ...], ...]:
    """Pearl back-door sensitivity: no descendants of X; remove X's arrows."""

    descendants = _descendants(dag, query.treatment)
    candidates = tuple(
        node for node in query.candidate_variables if node not in descendants
    )
    backdoor_edges = {
        (parent, child)
        for parent, child in dag.directed
        if parent != query.treatment
    }
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


def standards_task_semantics(
    dag: PartialGraph, query: ReasonerQuery
) -> TaskSemantics:
    """Standards-based total-effect sensitivity for four adjustment tasks.

    CausalDS's bespoke forbidden-controls task is intentionally excluded rather
    than silently assigning a different construct the same task name.
    """

    if query.task_id == TASKS[4]:
        raise ValueError("Standards sensitivity is not applicable to forbidden_controls_list")
    if dag.undirected:
        raise ValueError("Standards task semantics require a DAG")
    valid = _standard_valid_adjustment_sets(dag, query)
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
    else:  # pragma: no cover
        raise ValueError("Unsupported standards-based task")
    return TaskSemantics(query.task_id, accepted)


def standards_conservative_target(
    graph: PartialGraph, query: ReasonerQuery
) -> ConservativeTarget:
    semantics = [standards_task_semantics(dag, query) for dag in compatible_dags(graph)]
    if query.task_id == TASKS[0]:
        common = set(semantics[0].accepted)
        for item in semantics[1:]:
            common &= set(item.accepted)
        if common:
            return ConservativeTarget(
                "answered", tuple(sorted(common, key=repr)), len(semantics)
            )
    elif all(item.accepted == semantics[0].accepted for item in semantics[1:]):
        return ConservativeTarget("answered", semantics[0].accepted, len(semantics))
    return ConservativeTarget("undetermined", ("undetermined",), len(semantics))


def parse_task_specific_response(
    raw_text: str, query: ReasonerQuery
) -> ParsedReasonerAnswer:
    """Parse exactly one task field; infer status from the sentinel."""

    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:].lstrip()
    elif text.startswith("```"):
        text = text[3:].lstrip()
    if text.endswith("```"):
        text = text[:-3].rstrip()
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {query.response_field}:
        raise ValueError(f"Response must contain exactly {query.response_field!r}")
    answer = value[query.response_field]
    if answer == "undetermined":
        return ParsedReasonerAnswer("undetermined", "undetermined")
    canonical = _canonical_answer(query.task_id, answer)
    sentinels = {"no_backdoor", "non_id"}
    if isinstance(canonical, str):
        if canonical not in sentinels:
            raise ValueError("Unknown response sentinel")
    else:
        returned_ids: set[str] = set()
        if query.task_id in {TASKS[0], TASKS[4]}:
            returned_ids.update(canonical)
        elif query.task_id == TASKS[1]:
            returned_ids.update(node for item in canonical for node in item)
        if not returned_ids.issubset(query.candidate_variables):
            raise ValueError("Response contains a node outside candidate_variables")
        if any(not re.fullmatch(r"X[0-9]{3}", node) for node in returned_ids):
            raise ValueError("Response contains a non-canonical node ID")
    return ParsedReasonerAnswer("answered", canonical)


@dataclass(frozen=True)
class ReasonerCacheIdentity:
    model_version: str
    prompt_template_sha256: str
    graph_reasoner_view_sha256: str
    query_sha256: str
    glossary_sha256: str
    decoding_config_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "schema_version": V2_CACHE_SCHEMA_VERSION,
            "model_version": self.model_version,
            "prompt_template_sha256": self.prompt_template_sha256,
            "graph_reasoner_view_sha256": self.graph_reasoner_view_sha256,
            "query_sha256": self.query_sha256,
            "glossary_sha256": self.glossary_sha256,
            "decoding_config_sha256": self.decoding_config_sha256,
        }

    @property
    def cache_key(self) -> str:
        return sha256_hex(canonical_json_bytes(self.to_dict()))


@dataclass(frozen=True)
class CachedReasonerResponse:
    identity: ReasonerCacheIdentity
    raw_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "fourgraph.reasoner_cache_record.v1",
            "cache_key": self.identity.cache_key,
            "identity": self.identity.to_dict(),
            "raw_text": self.raw_text,
            "raw_sha256": sha256_hex(self.raw_text.encode("utf-8")),
        }


class CanonicalResponseCache:
    """Exact-response cache keyed only by canonical model input/configuration."""

    def __init__(self, entries: Mapping[str, CachedReasonerResponse] | None = None) -> None:
        self._entries = dict(entries or {})

    @classmethod
    def load(cls, path: Path) -> "CanonicalResponseCache":
        entries: dict[str, CachedReasonerResponse] = {}
        if not path.exists():
            return cls()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line:
                continue
            value = json.loads(line)
            if value.get("schema_version") != "fourgraph.reasoner_cache_record.v1":
                raise ValueError(f"Unsupported cache record at line {number}")
            raw_identity = value.get("identity") or {}
            if raw_identity.get("schema_version") != V2_CACHE_SCHEMA_VERSION:
                raise ValueError(f"Unsupported cache identity at line {number}")
            fields = {
                key: raw_identity[key]
                for key in (
                    "model_version",
                    "prompt_template_sha256",
                    "graph_reasoner_view_sha256",
                    "query_sha256",
                    "glossary_sha256",
                    "decoding_config_sha256",
                )
            }
            identity = ReasonerCacheIdentity(**fields)
            raw_text = str(value["raw_text"])
            entry = CachedReasonerResponse(identity, raw_text)
            if value.get("cache_key") != identity.cache_key:
                raise ValueError(f"Cache-key mismatch at line {number}")
            if value.get("raw_sha256") != sha256_hex(raw_text.encode("utf-8")):
                raise ValueError(f"Cached-response hash mismatch at line {number}")
            if identity.cache_key in entries:
                raise ValueError(f"Duplicate cache key at line {number}")
            entries[identity.cache_key] = entry
        return cls(entries)

    def get(self, identity: ReasonerCacheIdentity) -> str | None:
        entry = self._entries.get(identity.cache_key)
        return entry.raw_text if entry is not None else None

    def put(self, identity: ReasonerCacheIdentity, raw_text: str) -> None:
        entry = CachedReasonerResponse(identity, str(raw_text))
        existing = self._entries.get(identity.cache_key)
        if existing is not None and existing.raw_text != entry.raw_text:
            raise ValueError("Canonical cache key cannot be overwritten with a new response")
        self._entries[identity.cache_key] = entry

    def to_jsonl_bytes(self) -> bytes:
        return b"".join(
            canonical_json_bytes(self._entries[key].to_dict(), newline=True)
            for key in sorted(self._entries)
        )

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.to_jsonl_bytes())


def build_cache_identity(
    *,
    model_version: str,
    prompt_template: str,
    graph_reasoner_view: Mapping[str, Any],
    query: ReasonerQuery,
    glossary: list[dict[str, str]],
    decoding_config: Mapping[str, Any],
) -> ReasonerCacheIdentity:
    """Hash only canonical model inputs/configuration, never graph source labels."""

    if set(graph_reasoner_view) != {"schema_version", "graph_type", "nodes", "edges"}:
        raise ValueError("Cache requires the stripped provenance-blind reasoner graph view")
    if any(set(item) != {"id", "type"} for item in glossary):
        raise ValueError("Cache glossary must contain canonical ID and type only")
    if not model_version:
        raise ValueError("Cache requires a pinned non-empty model version")

    return ReasonerCacheIdentity(
        model_version=str(model_version),
        prompt_template_sha256=sha256_hex(prompt_template.encode("utf-8")),
        graph_reasoner_view_sha256=sha256_hex(
            canonical_json_bytes(dict(graph_reasoner_view))
        ),
        query_sha256=sha256_hex(canonical_json_bytes(v2_query_view(query))),
        glossary_sha256=sha256_hex(canonical_json_bytes(glossary)),
        decoding_config_sha256=sha256_hex(
            canonical_json_bytes(dict(decoding_config))
        ),
    )
