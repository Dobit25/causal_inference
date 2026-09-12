from __future__ import annotations

import json

import pytest

from fourgraph.graph_adapters import make_llm_graph_artifact
from fourgraph.graph_contract import VariableMap
from fourgraph.llm_backend import LLMCallResponse
from fourgraph.partial_graph import PartialGraph, dag_to_cpdag_exact
from fourgraph.reasoner import (
    OfficialTarget,
    RESPONSE_SCHEMA_VERSION,
    ReasonerPolicy,
    ReasonerQuery,
    TASKS,
    compatible_dags,
    conservative_target,
    noncausal_glossary,
    parse_reasoner_response,
    render_reasoner_prompt,
    run_fixed_reasoner,
    score_answer,
)


def query(task_id: str) -> ReasonerQuery:
    fields = {
        TASKS[0]: "adjust",
        TASKS[1]: "adjustment_sets",
        TASKS[2]: "k",
        TASKS[3]: "n",
        TASKS[4]: "forbidden",
    }
    return ReasonerQuery(
        "scene_000001", task_id, "X001", "X002", ("X000",), fields[task_id]
    )


def test_noncausal_glossary_never_contains_public_names() -> None:
    mapping = VariableMap.build(
        "scene_000001",
        [("Smoking", "binary"), ("Treatment", "binary"), ("Outcome", "continuous")],
    )
    glossary = noncausal_glossary(mapping)
    assert glossary == [
        {"id": "X000", "type": "binary"},
        {"id": "X001", "type": "binary"},
        {"id": "X002", "type": "continuous"},
    ]
    assert "Smoking" not in json.dumps(glossary)


def test_cpdag_extensions_and_conservative_ambiguity() -> None:
    dag = PartialGraph.build(
        ("X000", "X001", "X002"),
        directed=(("X000", "X001"), ("X000", "X002"), ("X001", "X002")),
    )
    cpdag = dag_to_cpdag_exact(dag)
    assert len(compatible_dags(cpdag)) == 6
    target = conservative_target(cpdag, query(TASKS[0]))
    assert target.status == "undetermined"
    assert target.extension_count == 6


def test_dag_semantics_reproduce_fork_adjustment() -> None:
    dag = PartialGraph.build(
        ("X000", "X001", "X002"),
        directed=(("X000", "X001"), ("X000", "X002"), ("X001", "X002")),
    )
    assert conservative_target(dag, query(TASKS[0])).accepted == (("X000",),)
    assert conservative_target(dag, query(TASKS[1])).accepted == ((("X000",),),)
    assert conservative_target(dag, query(TASKS[2])).accepted == (1,)
    assert conservative_target(dag, query(TASKS[3])).accepted == (1,)
    assert conservative_target(dag, query(TASKS[4])).accepted == ((),)


def test_response_parser_and_two_scorers() -> None:
    q = query(TASKS[2])
    parsed = parse_reasoner_response(
        json.dumps(
            {"schema_version": RESPONSE_SCHEMA_VERSION, "status": "answered", "answer": 1}
        ),
        q,
    )
    official = OfficialTarget(q.task_id, (1,), "A" * 64)
    invariant = conservative_target(
        PartialGraph.build(
            ("X000", "X001", "X002"),
            directed=(("X000", "X001"), ("X000", "X002"), ("X001", "X002")),
        ),
        q,
    )
    assert score_answer(parsed, official, invariant) == {
        "schema_version": "fourgraph.reasoner_score.v1",
        "oracle_answer_accuracy": True,
        "uncertainty_aware_correctness": True,
    }


class FakeBackend:
    def complete(self, request):
        return LLMCallResponse(
            raw_text=json.dumps(
                {
                    "schema_version": RESPONSE_SCHEMA_VERSION,
                    "status": "answered",
                    "answer": ["X000"],
                }
            ),
            provider="fake",
            model_id="fixed",
            model_version="fixed-v1",
        )


def test_prompt_is_provenance_blind_and_fixed_runner_parses() -> None:
    mapping = VariableMap.build(
        "scene_000001",
        [("Secret confounder label", "binary"), ("Treatment", "binary"), ("Outcome", "binary")],
    )
    artifact = make_llm_graph_artifact(
        scene_id="scene_000001",
        graph=PartialGraph.build(
            mapping.node_ids,
            directed=(("X000", "X001"), ("X000", "X002"), ("X001", "X002")),
        ),
        builder_id="test.builder",
        builder_version="v1",
        config_sha256="A" * 64,
        input_artifact_sha256=["B" * 64],
        seed=None,
    )
    template = "GRAPH={{GRAPH_JSON}}\nQUERY={{QUERY_JSON}}\nGLOSSARY={{GLOSSARY_JSON}}"
    prompt = render_reasoner_prompt(artifact, query(TASKS[0]), mapping, template)
    assert "Secret confounder label" not in prompt
    assert "graph_method" not in prompt
    assert "provenance" not in prompt
    result = run_fixed_reasoner(
        graph_artifact=artifact,
        query=query(TASKS[0]),
        variable_map=mapping,
        backend=FakeBackend(),
        policy=ReasonerPolicy("fake", "fixed", "fixed-v1", 0, 128, 0),
        prompt_template=template,
    )
    assert result.parsed is not None
    assert result.parsed.answer == ("X000",)


def test_parser_rejects_malformed_undetermined() -> None:
    with pytest.raises(ValueError, match="requires"):
        parse_reasoner_response(
            json.dumps(
                {
                    "schema_version": RESPONSE_SCHEMA_VERSION,
                    "status": "undetermined",
                    "answer": [],
                }
            ),
            query(TASKS[0]),
        )


def test_parser_accepts_json_with_only_a_markdown_fence() -> None:
    parsed = parse_reasoner_response(
        '{"schema_version":"fourgraph.reasoner_response.v1","status":"answered","answer":1}\n```',
        query(TASKS[2]),
    )
    assert parsed.answer == 1
