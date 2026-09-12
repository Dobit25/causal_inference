import json
from dataclasses import fields
from pathlib import Path

import pytest

from fourgraph.causalds_public import PublicLLMGraphInput, load_llm_graph_input
from fourgraph.graph_contract import sha256_hex
from fourgraph.llm_backend import (
    LLMCallRequest,
    LLMCallResponse,
    ReplayBackend,
    ReplayEntry,
)
from fourgraph.openai_backend import OpenAIResponsesBackend
from fourgraph.llm_graph import (
    LLMGraphPolicy,
    build_llm_graph,
    parse_llm_graph_response,
    render_llm_graph_prompt,
)


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "prompts/llm_graph_v1.md"
SHA = "A" * 64


def _write_public_fixture(root: Path, scene_id: str = "scene_000001") -> None:
    public = root / "data/benchmark/main/scenes" / scene_id
    variant = public / "variants/clean"
    private = root / "data/benchmark/main/scenes_private" / scene_id
    variant.mkdir(parents=True)
    private.mkdir(parents=True)
    schema = {
        "n_columns": 3,
        "columns": {
            "Treatment": {"dtype": "float64", "is_binary": True},
            "Mediator": {"dtype": "float64"},
            "Outcome": {"dtype": "float64"},
        },
    }
    (variant / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
    (public / "story.md").write_text(
        "Treatment directly raises Mediator. Mediator directly raises Outcome. "
        "Treatment affects Outcome only through Mediator.",
        encoding="utf-8",
    )
    (variant / "data.parquet").write_text(
        "POISON_OBSERVATIONAL_TABLE", encoding="utf-8"
    )
    (variant / "tasks.json").write_text(
        '{"gold_answer":"POISON_TASK"}', encoding="utf-8"
    )
    (private / "ground_truth.json").write_text(
        '{"graph":"POISON_ORACLE"}', encoding="utf-8"
    )


def _decision(left, right, relation, confidence=0.8):
    return {
        "left": left,
        "right": right,
        "relation": relation,
        "confidence": confidence,
        "rationale": f"public story decision for {left} and {right}",
    }


def _raw(decisions=None) -> str:
    if decisions is None:
        decisions = [
            _decision("X000", "X001", "left_causes_right"),
            _decision("X000", "X002", "no_direct_edge"),
            _decision("X001", "X002", "left_causes_right"),
        ]
    return json.dumps(
        {
            "schema_version": "fourgraph.llm_graph_response.v1",
            "pair_decisions": decisions,
        },
        sort_keys=True,
    )


def _policy(retries=2) -> LLMGraphPolicy:
    return LLMGraphPolicy(
        provider="test_provider",
        model_id="test_model",
        model_version="snapshot_1",
        temperature=0,
        max_tokens=2000,
        seed=42,
        max_validation_retries=retries,
    )


def _response(raw_text: str) -> LLMCallResponse:
    return LLMCallResponse(
        raw_text=raw_text,
        provider="test_provider",
        model_id="test_model",
        model_version="snapshot_1",
        request_id="request_1",
        system_fingerprint="fingerprint_1",
        input_tokens=100,
        output_tokens=80,
        latency_ms=10,
    )


class SequenceBackend:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[LLMCallRequest] = []

    def complete(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def test_public_llm_input_exposes_story_and_schema_only(tmp_path):
    _write_public_fixture(tmp_path)
    evidence = load_llm_graph_input(tmp_path, "scene_000001")
    assert isinstance(evidence, PublicLLMGraphInput)
    assert {item.name for item in fields(evidence)} == {
        "scene_id",
        "story",
        "variable_map",
        "story_sha256",
        "public_schema_sha256",
    }
    serialized = json.dumps(evidence.semantic_view())
    assert "Treatment" in serialized
    for poison in ("POISON_OBSERVATIONAL_TABLE", "POISON_TASK", "POISON_ORACLE"):
        assert poison not in serialized
    assert evidence.variable_map.node_ids == ("X000", "X001", "X002")


def test_prompt_has_complete_pairs_and_no_nonpublic_evidence(tmp_path):
    _write_public_fixture(tmp_path)
    evidence = load_llm_graph_input(tmp_path, "scene_000001")
    prompt = render_llm_graph_prompt(
        evidence, PROMPT_PATH.read_text(encoding="utf-8")
    )
    for pair in (("X000", "X001"), ("X000", "X002"), ("X001", "X002")):
        assert all(node in prompt for node in pair)
    assert evidence.story in prompt
    assert "Treatment" in prompt
    assert "POISON_" not in prompt
    assert "{{" not in prompt


def test_strict_parser_builds_dag_and_audits_edges_and_nonedges():
    parsed = parse_llm_graph_response(_raw(), ("X000", "X001", "X002"))
    assert parsed.graph.directed == frozenset(
        {("X000", "X001"), ("X001", "X002")}
    )
    assert [item.step for item in parsed.edge_audit] == [0, 1, 2]
    assert {item.action for item in parsed.edge_audit} == {"add", "reject"}
    assert all(item.actor == "llm" for item in parsed.edge_audit)


@pytest.mark.parametrize(
    ("raw_text", "message"),
    [
        ("```json\n" + _raw() + "\n```", "Expecting value"),
        (
            json.dumps(
                {
                    "schema_version": "fourgraph.llm_graph_response.v1",
                    "pair_decisions": [],
                    "extra": True,
                }
            ),
            "exactly schema_version",
        ),
        (_raw([_decision("X000", "X001", "left_causes_right")]), "exact canonical pair"),
        (
            _raw(
                [
                    _decision("X000", "X001", "left_causes_right"),
                    _decision("X000", "X001", "no_direct_edge"),
                    _decision("X001", "X002", "left_causes_right"),
                ]
            ),
            "duplicates",
        ),
        (
            _raw(
                [
                    _decision("X000", "X001", "left_causes_right", float("nan")),
                    _decision("X000", "X002", "no_direct_edge"),
                    _decision("X001", "X002", "left_causes_right"),
                ]
            ),
            "finite",
        ),
        (
            _raw(
                [
                    _decision("X000", "X001", "left_causes_right"),
                    _decision("X000", "X002", "right_causes_left"),
                    _decision("X001", "X002", "left_causes_right"),
                ]
            ),
            "cycle",
        ),
    ],
)
def test_strict_parser_rejects_ambiguous_or_invalid_outputs(raw_text, message):
    with pytest.raises(ValueError, match=message):
        parse_llm_graph_response(raw_text, ("X000", "X001", "X002"))


def test_builder_retries_validation_without_silent_repair(tmp_path):
    _write_public_fixture(tmp_path)
    evidence = load_llm_graph_input(tmp_path, "scene_000001")
    backend = SequenceBackend([_response("not json"), _response(_raw())])
    result = build_llm_graph(
        evidence,
        backend=backend,
        policy=_policy(),
        prompt_template=PROMPT_PATH.read_text(encoding="utf-8"),
        config_sha256=SHA,
    )
    assert result.success is True
    assert result.retry_count == 1
    assert result.attempts[0].validation_error is not None
    assert result.attempts[1].validation_error is None
    assert backend.requests[0].prompt_sha256 != backend.requests[1].prompt_sha256
    assert "VALIDATOR ERROR" in backend.requests[1].prompt
    assert "POISON_" not in backend.requests[1].prompt
    assert result.artifact is not None
    assert result.artifact.graph_method == "llm"
    assert result.artifact.provenance.evidence_sources == (
        "public_schema_types",
        "public_story",
        "public_variable_semantics",
    )


def test_builder_records_failure_instead_of_repair_or_fallback(tmp_path):
    _write_public_fixture(tmp_path)
    evidence = load_llm_graph_input(tmp_path, "scene_000001")
    cycle = _raw(
        [
            _decision("X000", "X001", "left_causes_right"),
            _decision("X000", "X002", "right_causes_left"),
            _decision("X001", "X002", "left_causes_right"),
        ]
    )
    backend = SequenceBackend([_response(cycle), _response(cycle)])
    result = build_llm_graph(
        evidence,
        backend=backend,
        policy=_policy(retries=1),
        prompt_template=PROMPT_PATH.read_text(encoding="utf-8"),
        config_sha256=SHA,
    )
    assert result.success is False
    assert result.artifact is None
    assert result.retry_count == 1
    assert "cycle" in result.final_error.lower()


def test_replay_verifies_prompt_and_recreates_identical_artifact(tmp_path):
    _write_public_fixture(tmp_path)
    evidence = load_llm_graph_input(tmp_path, "scene_000001")
    template = PROMPT_PATH.read_text(encoding="utf-8")
    capture = SequenceBackend([_response(_raw())])
    first = build_llm_graph(
        evidence,
        backend=capture,
        policy=_policy(),
        prompt_template=template,
        config_sha256=SHA,
    )
    request = capture.requests[0]
    replay = ReplayBackend(
        [
            ReplayEntry(
                scene_id=request.scene_id,
                attempt=request.attempt,
                prompt_sha256=request.prompt_sha256,
                response=_response(_raw()),
            )
        ]
    )
    second = build_llm_graph(
        evidence,
        backend=replay,
        policy=_policy(),
        prompt_template=template,
        config_sha256=SHA,
    )
    assert first.artifact is not None and second.artifact is not None
    assert first.artifact.to_json_bytes() == second.artifact.to_json_bytes()

    wrong = ReplayBackend(
        [
            ReplayEntry(
                scene_id=request.scene_id,
                attempt=0,
                prompt_sha256=sha256_hex(b"wrong prompt"),
                response=_response(_raw()),
            )
        ]
    )
    with pytest.raises(RuntimeError, match="prompt hash mismatch"):
        build_llm_graph(
            evidence,
            backend=wrong,
            policy=_policy(),
            prompt_template=template,
            config_sha256=SHA,
        )


def test_versioned_raw_log_preserves_prompt_and_provider_payload(tmp_path):
    _write_public_fixture(tmp_path)
    evidence = load_llm_graph_input(tmp_path, "scene_000001")
    template = PROMPT_PATH.read_text(encoding="utf-8")
    capture = SequenceBackend([_response(_raw())])
    result = build_llm_graph(
        evidence,
        backend=capture,
        policy=_policy(),
        prompt_template=template,
        config_sha256=SHA,
    )
    record = result.attempts[0].raw_log_record(result.scene_id)
    assert record["raw_log_schema_version"] == "fourgraph.llm_raw_call.v1"
    assert record["prompt"] == capture.requests[0].prompt
    assert sha256_hex(record["prompt"].encode("utf-8")) == record["prompt_sha256"]
    log = tmp_path / "calls.jsonl"
    log.write_text(json.dumps(record) + "\n", encoding="utf-8")
    replay = ReplayBackend.load(log)
    assert replay.has_scene(result.scene_id)
    assert replay.complete(capture.requests[0]).raw_text == _raw()


def test_openai_backend_uses_frozen_responses_parameters(monkeypatch):
    captured = {}

    class Usage:
        input_tokens = 123
        output_tokens = 45

    class Response:
        status = "completed"
        output_text = _raw()
        model = "snapshot_1"
        _request_id = "req_test"
        system_fingerprint = "fp_test"
        service_tier = "default"
        usage = Usage()

        @staticmethod
        def model_dump(mode="json"):
            assert mode == "json"
            return {"id": "resp_test", "status": "completed"}

    class Responses:
        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            return Response()

    class FakeClient:
        responses = Responses()

    backend = object.__new__(OpenAIResponsesBackend)
    backend._client = FakeClient()
    backend._response_schema = {"type": "object"}
    backend._service_tier = "default"
    backend._reasoning_effort = "none"
    backend._store = False
    backend._sdk_version = "3.6.0"
    response = backend.complete(
        LLMCallRequest(
            scene_id="scene_000001",
            attempt=0,
            prompt="public prompt",
            provider="openai",
            model_id="snapshot_1",
            model_version="snapshot_1",
            temperature=0,
            max_tokens=6000,
            seed=None,
        )
    )
    assert captured["model"] == "snapshot_1"
    assert captured["service_tier"] == "default"
    assert captured["store"] is False
    assert captured["reasoning"] == {"effort": "none"}
    assert captured["text"]["format"]["type"] == "json_schema"
    assert captured["text"]["format"]["strict"] is True
    assert response.model_id == "snapshot_1"
    assert response.endpoint == "/v1/responses"
    assert response.input_tokens == 123
    assert json.loads(response.provider_response_json)["id"] == "resp_test"


def test_llm_builder_module_has_no_data_task_scd_or_oracle_imports():
    source = (ROOT / "src/fourgraph/llm_graph.py").read_text(encoding="utf-8")
    for forbidden in (
        "causalds_oracle",
        "causalds_scd",
        "resolve_grading_artifact",
        "resolve_public_artifact",
        "data.parquet",
        "tasks.json",
        "scenes_private",
    ):
        assert forbidden not in source


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("input_tokens", -1),
        ("output_tokens", True),
        ("latency_ms", 1.5),
    ],
)
def test_response_metadata_rejects_invalid_measurements(field_name, value):
    kwargs = {
        "raw_text": _raw(),
        "provider": "test_provider",
        "model_id": "test_model",
        "model_version": "snapshot_1",
        field_name: value,
    }
    with pytest.raises(ValueError, match=field_name):
        LLMCallResponse(**kwargs)


def test_versioned_readiness_audit_records_completed_live_development_run():
    audit = json.loads(
        (ROOT / "data/manifests/t08_llm_graph_builder_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["task"] == "T08"
    assert audit["status"] == "complete_llm_graph_builder_ready"
    assert audit["verdict"] == {
        "blocker": None,
        "implementation_ready": True,
        "llm_graph_builder_ready": True,
    }
    assert audit["scope"]["scene_count"] == 8
    assert audit["scope"]["holdout_accessed"] is False
    assert audit["scope"]["tasks_or_queries_accessed"] is False
    assert audit["scope"]["observational_data_accessed"] is False
    assert audit["scope"]["grading_or_oracle_accessed"] is False
    assert audit["development_build"]["scenes_attempted"] == 8
    assert audit["development_build"]["scenes_succeeded"] == 8
    assert audit["development_build"]["replay_log_sha256"] is not None
    assert audit["development_build"]["dev_graphs_sha256"] is not None
    assert audit["model"]["provider"] == "openai"
    assert audit["model"]["model_version"] == "gpt-5.4-nano-2026-03-17"
    assert audit["model"]["service_tier"] == "default"
    assert audit["model"]["store"] is False
    forbidden = {"raw_text", "prompt", "provider_response_json"}
    assert all(
        not (forbidden & set(attempt))
        for record in audit["development_build"]["records"]
        for attempt in record["attempts"]
    )

    graphs = [
        json.loads(line)
        for line in (ROOT / "data/manifests/t08_dev_graphs.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    assert len(graphs) == 8
    assert {item["scene_id"] for item in graphs} == set(audit["scope"]["scene_ids"])
    assert all(item["graph_method"] == "llm" for item in graphs)
    assert all(item["graph_type"] == "dag" for item in graphs)
