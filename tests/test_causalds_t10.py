import json
from pathlib import Path

import pytest

from fourgraph.causalds_public import PublicLLMGraphInput
from fourgraph.graph_adapters import make_scd_graph_artifact
from fourgraph.graph_contract import VariableMap, validate_hybrid_relationship
from fourgraph.hybrid_graph import HybridPolicy, build_hybrid_graph, load_graph_jsonl, parse_hybrid_response, render_hybrid_prompt
from fourgraph.llm_backend import LLMCallResponse
from fourgraph.partial_graph import PartialGraph


ROOT = Path(__file__).resolve().parents[1]
SHA = "A" * 64


def _evidence():
    return PublicLLMGraphInput(
        "scene_000001",
        "Treatment directly causes Mediator, which directly causes Outcome.",
        VariableMap.build("scene_000001", [("Treatment", "binary"), ("Mediator", "continuous"), ("Outcome", "continuous")]),
        "B" * 64,
        "C" * 64,
    )


def _parent():
    return make_scd_graph_artifact(
        scene_id="scene_000001",
        graph=PartialGraph.build(("X000", "X001", "X002"), undirected=(("X000", "X001"), ("X001", "X002"))),
        graph_type="cpdag",
        builder_id="test.scd",
        builder_version="v1",
        config_sha256=SHA,
        input_artifact_sha256=("D" * 64,),
        seed=None,
    )


def _raw(second="left_causes_right"):
    return json.dumps({
        "schema_version": "fourgraph.hybrid_orientation_response.v1",
        "orientation_decisions": [
            {"left": "X000", "right": "X001", "relation": "left_causes_right", "confidence": 0.9, "rationale": "Treatment directly causes Mediator."},
            {"left": "X001", "right": "X002", "relation": second, "confidence": 0.9, "rationale": "Mediator directly causes Outcome."},
        ],
    }, sort_keys=True)


class Backend:
    def __init__(self, responses):
        self.responses = iter(responses)

    def complete(self, request):
        return LLMCallResponse(next(self.responses), "test", "model", "snapshot")


def _policy(retries=2):
    return HybridPolicy("test", "model", "snapshot", 0, 6000, None, retries)


def test_prompt_contains_only_parent_structure_and_public_semantics():
    prompt = render_hybrid_prompt(_evidence(), _parent(), (ROOT / "prompts/hybrid_orientation_v1.md").read_text(encoding="utf-8"))
    assert "Treatment" in prompt and "X000" in prompt
    assert "UNRESOLVED_EDGES" in prompt
    assert "POISON" not in prompt


def test_parser_requires_exact_unresolved_edges_and_rejects_no_edge():
    parsed = parse_hybrid_response(_raw(), _parent())
    assert parsed.graph.directed == frozenset({("X000", "X001"), ("X001", "X002")})
    bad = json.loads(_raw())
    bad["orientation_decisions"][0]["relation"] = "no_direct_edge"
    with pytest.raises(ValueError, match="Unsupported Hybrid orientation"):
        parse_hybrid_response(json.dumps(bad), _parent())
    bad = json.loads(_raw())
    bad["orientation_decisions"].pop()
    with pytest.raises(ValueError, match="exact unresolved"):
        parse_hybrid_response(json.dumps(bad), _parent())


def test_builder_retries_invalid_equivalence_class_without_repair():
    result = build_hybrid_graph(
        _evidence(),
        _parent(),
        backend=Backend([_raw("right_causes_left"), _raw()]),
        policy=_policy(),
        prompt_template=(ROOT / "prompts/hybrid_orientation_v1.md").read_text(encoding="utf-8"),
        config_sha256=SHA,
    )
    assert result.success and result.retry_count == 1
    assert "equivalence class" in result.attempts[0].validation_error
    assert result.attempts[1].validation_error is None
    validate_hybrid_relationship(_parent(), result.artifact)
    assert len(result.artifact.edge_audit) == 2


def test_builder_never_falls_back_after_retry_budget():
    result = build_hybrid_graph(
        _evidence(), _parent(), backend=Backend([_raw("right_causes_left")]),
        policy=_policy(retries=0), prompt_template=(ROOT / "prompts/hybrid_orientation_v1.md").read_text(encoding="utf-8"), config_sha256=SHA,
    )
    assert not result.success and result.artifact is None


def test_t10_config_reuses_exact_t08_model_policy():
    import yaml
    t08 = yaml.safe_load((ROOT / "configs/t08_llm_graph_builder.yaml").read_text(encoding="utf-8"))["llm"]
    t10 = yaml.safe_load((ROOT / "configs/t10_hybrid_graph_builder.yaml").read_text(encoding="utf-8"))["llm"]
    keys = ("provider", "model_id", "model_version", "endpoint", "sdk", "sdk_version", "credential_env", "service_tier", "store", "structured_outputs", "reasoning_effort", "temperature", "max_tokens", "seed", "max_validation_retries", "transport_max_retries", "timeout_seconds")
    assert {key: t10[key] for key in keys} == {key: t08[key] for key in keys}


def test_frozen_t10_artifacts_preserve_all_parent_contracts():
    parents = load_graph_jsonl(ROOT / "data/manifests/t09_dev_scd_cpdag.jsonl")
    children = load_graph_jsonl(ROOT / "data/manifests/t10_dev_hybrid_graphs.jsonl")
    assert set(children) == set(parents) and len(children) == 8
    assert sum(len(child.edge_audit) for child in children.values()) == 27
    for scene_id, child in children.items():
        validate_hybrid_relationship(parents[scene_id], child)
        assert child.provenance.evidence_sources == (
            "parent_graph", "public_schema_types", "public_story", "public_variable_semantics"
        )


def test_t10_versioned_audit_records_complete_leakage_boundary():
    audit = json.loads((ROOT / "data/manifests/t10_hybrid_graph_builder_audit.json").read_text(encoding="utf-8"))
    assert audit["verdict"] == {"blocker": None, "hybrid_graph_builder_ready": True, "t10_complete": True}
    assert audit["development_build"]["scenes_succeeded"] == 8
    assert audit["development_build"]["orientations_audited"] == 27
    assert audit["development_build"]["skeleton_changes"] == 0
    assert audit["development_build"]["compelled_direction_changes"] == 0
    forbidden = ("holdout_accessed", "observational_data_accessed", "t08_llm_graph_accessed", "t09_projected_dag_accessed", "tasks_or_queries_accessed", "grading_or_oracle_accessed")
    assert all(audit["scope"][key] is False for key in forbidden)
