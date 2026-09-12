import ast
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from fourgraph.causalds_scd import SceneData
from fourgraph.graph_contract import (
    GraphArtifact,
    sha256_hex,
    validate_projection_relationship,
)
from fourgraph.partial_graph import PartialGraph
from fourgraph.scd_graph import SCDGraphPolicy, build_scd_graphs


ROOT = Path(__file__).resolve().parents[1]
SHA = "A" * 64


class FakeSCDBackend:
    def __init__(self):
        self.specs = []

    def to_java_dataset(self, scene_data):
        return scene_data

    def run(self, dataset, spec):
        self.specs.append(spec)
        return (
            PartialGraph.build(
                dataset.anonymous_names,
                undirected=[("X000", "X001"), ("X001", "X002")],
            ),
            0.25,
        )


def _policy():
    return SCDGraphPolicy(
        candidate_id="boss_basis_bic__p1__t3",
        family="boss_basis_bic",
        penalty_discount=1.0,
        truncation_limit=3,
        seed=None,
    )


def _scene():
    return SceneData(
        scene_id="scene_000001",
        anonymous_names=("X000", "X001", "X002"),
        binary_flags=(False, True, False),
        values=np.asarray([[0.0, 0.0, 1.0], [1.0, 1.0, -1.0]]),
    )


def test_t09_builder_emits_raw_cpdag_and_parent_linked_projection():
    backend = FakeSCDBackend()
    result = build_scd_graphs(
        _scene(),
        backend=backend,
        policy=_policy(),
        config_sha256=SHA,
        input_artifact_sha256=["B" * 64, "C" * 64],
    )
    raw = result.raw_cpdag
    projected = result.projected_dag
    assert (raw.graph_method, raw.graph_type, raw.graph_view) == (
        "scd",
        "cpdag",
        "cpdag",
    )
    assert raw.provenance.evidence_sources == (
        "public_observational_data",
        "public_schema_types",
    )
    assert len(raw.edge_audit) == 2
    assert all(item.actor == "scd" and not item.arbitrary for item in raw.edge_audit)
    assert (projected.graph_method, projected.graph_type, projected.graph_view) == (
        "scd",
        "dag",
        "projected_dag",
    )
    assert projected.provenance.parent_artifact_sha256 == (raw.artifact_sha256,)
    assert len(projected.edge_audit) == len(raw.partial_graph.undirected)
    assert all(item.actor == "projection" and item.arbitrary for item in projected.edge_audit)
    validate_projection_relationship(raw, projected)
    assert backend.specs[0].candidate_id == "boss_basis_bic__p1__t3"


@pytest.mark.parametrize(
    "policy",
    [
        replace(_policy(), candidate_id="boss_basis_bic__p2__t3"),
        replace(_policy(), family="pcmax_basis_lrt"),
        replace(_policy(), penalty_discount=2.0),
        replace(_policy(), truncation_limit=2),
        replace(_policy(), seed=42),
    ],
)
def test_t09_policy_cannot_reopen_t05_selection(policy):
    with pytest.raises(ValueError):
        policy.validate()


def test_t09_rejects_noncanonical_backend_node_universe():
    class BadBackend(FakeSCDBackend):
        def run(self, dataset, spec):
            return PartialGraph.build(("X000", "X001"), undirected=[("X000", "X001")]), 0.1

    with pytest.raises(ValueError, match="node universe"):
        build_scd_graphs(
            _scene(),
            backend=BadBackend(),
            policy=_policy(),
            config_sha256=SHA,
            input_artifact_sha256=["B" * 64],
        )


def test_t09_modules_have_no_story_task_llm_or_oracle_dependency():
    for relative in ("src/fourgraph/scd_graph.py", "scripts/build_causalds_t09.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert not any(
            forbidden in name
            for name in imports
            for forbidden in (
                "causalds_public",
                "causalds_oracle",
                "llm_graph",
                "openai_backend",
            )
        )
        for forbidden_path in (
            "story.md",
            "tasks.json",
            "ground_truth.json",
            "scenes_private",
            "t08_dev_graphs",
        ):
            assert forbidden_path not in source


def test_t09_config_keeps_raw_cpdag_primary_and_projection_sensitivity_only():
    import yaml

    config = yaml.safe_load(
        (ROOT / "configs/t09_scd_graph_builder.yaml").read_text(encoding="utf-8")
    )
    assert config["scope"]["role"] == "dev"
    assert config["scope"]["forbid_holdout_access"] is True
    assert config["preprocessing"]["pool_scenes"] is False
    assert config["discovery"]["selected_method_id"] == "boss_basis_bic__p1__t3"
    assert config["discovery"]["output"] == "CPDAG"
    assert config["projection"]["role"] == "sensitivity_only"
    assert config["evidence"]["allow_story_or_semantics"] is False
    assert config["evidence"]["allow_grading_or_oracle"] is False


def _load_graph_jsonl(relative):
    return [
        GraphArtifact.from_dict(json.loads(line))
        for line in (ROOT / relative).read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_versioned_t09_artifacts_are_complete_parent_linked_and_anonymous():
    raw = _load_graph_jsonl("data/manifests/t09_dev_scd_cpdag.jsonl")
    projected = _load_graph_jsonl(
        "data/manifests/t09_dev_scd_projected_dag.jsonl"
    )
    assert len(raw) == len(projected) == 8
    raw_by_scene = {item.scene_id: item for item in raw}
    projected_by_scene = {item.scene_id: item for item in projected}
    assert set(raw_by_scene) == set(projected_by_scene)
    for scene_id, parent in raw_by_scene.items():
        child = projected_by_scene[scene_id]
        assert parent.graph_method == "scd"
        assert parent.graph_type == parent.graph_view == "cpdag"
        assert parent.provenance.evidence_sources == (
            "public_observational_data",
            "public_schema_types",
        )
        assert child.graph_type == "dag"
        assert child.graph_view == "projected_dag"
        assert child.provenance.evidence_sources == ("parent_graph",)
        assert all(node.startswith("X") for node in parent.nodes)
        validate_projection_relationship(parent, child)


def test_versioned_t09_audit_and_set_hashes_are_complete():
    audit = json.loads(
        (ROOT / "data/manifests/t09_scd_graph_builder_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["status"] == "complete_scd_graph_builder_ready"
    assert audit["verdict"] == {
        "blocker": None,
        "scd_graph_builder_ready": True,
        "t09_complete": True,
    }
    assert audit["development_build"]["raw_cpdag_count"] == 8
    assert audit["development_build"]["projected_dag_count"] == 8
    assert audit["scope"]["holdout_accessed"] is False
    assert audit["scope"]["story_or_semantics_accessed"] is False
    assert audit["scope"]["grading_or_oracle_accessed"] is False
    raw_bytes = (ROOT / "data/manifests/t09_dev_scd_cpdag.jsonl").read_bytes()
    projected_bytes = (
        ROOT / "data/manifests/t09_dev_scd_projected_dag.jsonl"
    ).read_bytes()
    assert audit["development_build"]["raw_cpdag_set_sha256"] == sha256_hex(
        raw_bytes
    )
    assert audit["development_build"]["projected_dag_set_sha256"] == sha256_hex(
        projected_bytes
    )
    serialized = json.dumps(audit)
    for forbidden in ("raw_values", "gold_answer", "ground_truth"):
        assert forbidden not in serialized


def test_t09_raw_graphs_match_t05_frozen_selected_candidate():
    selection_records = [
        json.loads(line)
        for line in (ROOT / "data/manifests/t05_dev_graphs.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    selected = {
        record["scene_id"]: record["graph"]
        for record in selection_records
        if record["record_type"] == "full"
        and record["candidate_id"] == "boss_basis_bic__p1__t3"
    }
    raw = _load_graph_jsonl("data/manifests/t09_dev_scd_cpdag.jsonl")
    assert len(selected) == len(raw) == 8
    for artifact in raw:
        assert artifact.partial_graph.to_dict() == selected[artifact.scene_id]
