from __future__ import annotations

import json
from pathlib import Path

import pytest

from fourgraph.partial_graph import PartialGraph
from fourgraph.reasoner import ReasonerQuery, TASKS, task_semantics
from fourgraph.reasoner_v2 import (
    CanonicalResponseCache,
    build_cache_identity,
    parse_task_specific_response,
    standards_task_semantics,
    v2_query_view,
)


def _query(task: str, scene: str = "scene_000001") -> ReasonerQuery:
    fields = {
        TASKS[0]: "adjust",
        TASKS[1]: "adjustment_sets",
        TASKS[2]: "k",
        TASKS[3]: "n",
        TASKS[4]: "forbidden",
    }
    return ReasonerQuery(scene, task, "X000", "X002", ("X001",), fields[task])


def test_task_specific_parser_has_exactly_one_field() -> None:
    parsed = parse_task_specific_response('{"k":0}', _query(TASKS[2]))
    assert parsed.status == "answered" and parsed.answer == 0
    undetermined = parse_task_specific_response(
        '{"k":"undetermined"}', _query(TASKS[2])
    )
    assert undetermined.status == "undetermined"
    with pytest.raises(ValueError, match="exactly"):
        parse_task_specific_response('{"k":0,"status":"answered"}', _query(TASKS[2]))
    with pytest.raises(ValueError, match="outside candidate"):
        parse_task_specific_response('{"adjust":["X999"]}', _query(TASKS[0]))
    with pytest.raises(ValueError, match="Unknown response sentinel"):
        parse_task_specific_response('{"adjust":"anything"}', _query(TASKS[0]))


def test_v2_query_prompt_view_removes_scene_identity() -> None:
    left = v2_query_view(_query(TASKS[0], "scene_000001"))
    right = v2_query_view(_query(TASKS[0], "scene_999999"))
    assert left == right
    assert "scene_id" not in left


def test_standard_backdoor_excludes_mediator_but_official_policy_allows_it() -> None:
    dag = PartialGraph.build(
        ("X000", "X001", "X002"),
        directed=(("X000", "X001"), ("X001", "X002")),
    )
    q = _query(TASKS[3])
    assert task_semantics(dag, q).accepted == (2,)
    assert standards_task_semantics(dag, q).accepted == (1,)
    with pytest.raises(ValueError, match="not applicable"):
        standards_task_semantics(dag, _query(TASKS[4]))


def test_cache_key_ignores_scene_and_source_condition_and_reuses_exact_response(
    tmp_path: Path,
) -> None:
    graph = {
        "schema_version": "fourgraph.reasoner_graph.v1",
        "graph_type": "dag",
        "nodes": ["X000", "X001", "X002"],
        "edges": [],
    }
    kwargs = {
        "model_version": "model-snapshot",
        "prompt_template": "fixed prompt",
        "graph_reasoner_view": graph,
        "glossary": [{"id": "X000", "type": "continuous"}],
        "decoding_config": {"temperature": 0},
    }
    first = build_cache_identity(query=_query(TASKS[0], "scene_000001"), **kwargs)
    second = build_cache_identity(query=_query(TASKS[0], "scene_999999"), **kwargs)
    assert first.cache_key == second.cache_key
    cache = CanonicalResponseCache()
    cache.put(first, '{"adjust":[]}')
    assert cache.get(second) == '{"adjust":[]}'
    with pytest.raises(ValueError, match="cannot be overwritten"):
        cache.put(second, '{"adjust":["X001"]}')
    path = tmp_path / "cache.jsonl"
    cache.write(path)
    assert CanonicalResponseCache.load(path).get(first) == '{"adjust":[]}'
    with pytest.raises(ValueError, match="stripped"):
        build_cache_identity(
            query=_query(TASKS[0]),
            **{**kwargs, "graph_reasoner_view": {**graph, "graph_method": "oracle"}},
        )


def test_synthetic_suite_is_balanced_and_contains_no_causalds_evidence() -> None:
    root = Path(__file__).resolve().parents[1]
    rows = [
        json.loads(line)
        for line in (root / "data/manifests/t12_v2_synthetic_conformance.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    assert len(rows) == 150
    assert all(not row["uses_causalds_story"] for row in rows)
    assert all(not row["uses_causalds_answer"] for row in rows)
    assert {sum(row["task_id"] == task for row in rows) for task in TASKS} == {30}
    assert sum(row["bucket"] == "dag_answered" for row in rows) == 75
    assert sum(row["bucket"] == "cpdag_answered" for row in rows) == 40
    assert sum(row["bucket"] == "cpdag_undetermined" for row in rows) == 35
    required = {
        "chain", "fork", "collider", "mediation", "confounding",
        "multiple_adjustment_sets", "empty_adjustment_set", "forbidden_descendant",
    }
    assert required <= {tag for row in rows for tag in row["feature_tags"]}


def test_t12_v1_artifact_hashes_remain_frozen() -> None:
    import hashlib

    root = Path(__file__).resolve().parents[1]
    expected = {
        "configs/t12_reasoner.yaml": "28DB680ECC8199320D1D331E8E4A2188AFCDC0DF89BA4DF8090C8E886E8E4126",
        "data/manifests/t12_dev_reasoner_scores.jsonl": "BF7515CA02A2DC5B97266E34BE7251A8566860577854B27036F8F146B33C7F5B",
        "data/manifests/t12_reasoner_audit.json": "7B53BEA2B06D1C441FB90F5245E8A69EBC17D9C25CBE80B01C7163B13ABF5E9C",
    }
    for relative, digest in expected.items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest().upper() == digest


def test_construct_validity_audit_reports_disagreement_without_holdout() -> None:
    root = Path(__file__).resolve().parents[1]
    audit = json.loads(
        (root / "data/manifests/t12_construct_validity_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"] == 28
    assert audit["official_and_standard_agree"] == 22
    assert audit["official_and_standard_disagree"] == 6
    assert audit["forbidden_controls_sensitivity"] == "not_applicable_construct_differs"
    assert audit["holdout_accessed"] is False


def test_all_five_v2_response_schemas_are_single_field_contracts() -> None:
    root = Path(__file__).resolve().parents[1]
    names = {
        "reasoner_one_valid_adjustment_set_v2.schema.json": "adjust",
        "reasoner_all_minimal_adjustment_sets_v2.schema.json": "adjustment_sets",
        "reasoner_minimal_adjustment_set_size_v2.schema.json": "k",
        "reasoner_n_valid_adjustment_sets_v2.schema.json": "n",
        "reasoner_forbidden_controls_list_v2.schema.json": "forbidden",
    }
    for name, field in names.items():
        schema = json.loads((root / "schemas" / name).read_text(encoding="utf-8"))
        assert schema["additionalProperties"] is False
        assert schema["required"] == [field]
        assert set(schema["properties"]) == {field}


def test_gemma_v2_conformance_result_blocks_oracle_development_and_holdout() -> None:
    root = Path(__file__).resolve().parents[1]
    audit = json.loads(
        (root / "data/manifests/t12_v2_gemma_conformance_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["cases"] == 150
    assert audit["parse_success_rate"] == 1.0
    assert audit["overall_accuracy"] == pytest.approx(20 / 150)
    assert audit["gate_results"]["parse_success"] is True
    assert sum(audit["gate_results"].values()) == 1
    assert audit["all_gates_passed"] is False
    assert audit["causalds_oracle_development_eligible"] is False
    assert audit["holdout_accessed"] is False
