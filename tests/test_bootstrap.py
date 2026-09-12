import random

import pytest

from fourgraph.cli import main
from fourgraph.config import load_config
from fourgraph.graph_contract import GraphArtifact, GraphEdge, GraphProvenance, VariableMap
from fourgraph.reproducibility import set_seed


@pytest.mark.parametrize(
    ("path", "phase", "expected_scenes"),
    [
        ("configs/p0_released.yaml", "p0_released", 33),
        ("configs/p1_fresh.yaml", "p1_fresh", 100),
    ],
)
def test_experiment_configs_load(
    path: str, phase: str, expected_scenes: int
) -> None:
    config = load_config(path)

    assert config["experiment"]["seed"] == 42
    assert config["experiment"]["phase"] == phase
    assert config["graphs"]["methods"] == ["llm", "scd", "hybrid", "oracle"]
    assert config["graphs"]["canonical_encoding"] == "fourgraph.graph.v1"
    assert config["graphs"]["variable_map_encoding"] == "fourgraph.variable_map.v1"
    actual_scenes = config.get("cohorts", {}).get("graph", {}).get(
        "expected_scenes"
    )
    if actual_scenes is None:
        actual_scenes = config["generation"]["scenes"]
    assert actual_scenes == expected_scenes


def test_config_rejects_non_mapping(tmp_path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("- item\n", encoding="utf-8")

    with pytest.raises(ValueError, match="YAML mapping"):
        load_config(path)


def test_p0_nested_cohort_contract() -> None:
    config = load_config("configs/p0_released.yaml")
    cohorts = config["cohorts"]

    assert cohorts["graph"]["expected_scenes"] == 33
    assert cohorts["primary_downstream"]["expected_scenes"] == 27
    assert cohorts["supplementary"]["expected_scenes"] == 6
    assert 27 + 6 == 33
    assert cohorts["primary_downstream"]["tasks_per_scene"] == 5
    assert cohorts["supplementary"]["downstream_role"] == "exploratory_only"
    assert cohorts["supplementary"]["pool_with_primary_accuracy"] is False
    assert config["nesting"]["preserve_split_role_across_cohorts"] is True


def test_seed_reproduces_python_randomness() -> None:
    set_seed(42)
    first = [random.random() for _ in range(3)]
    set_seed(42)
    second = [random.random() for _ in range(3)]

    assert first == second


def test_validate_config_command(capsys) -> None:
    exit_code = main(["validate-config", "configs/p0_released.yaml"])

    assert exit_code == 0
    assert "Valid config" in capsys.readouterr().out


def test_validate_graph_and_variable_map_commands(tmp_path, capsys) -> None:
    provenance = GraphProvenance.build(
        builder_id="test.oracle",
        builder_version="v1",
        operation="loaded",
        evidence_sources=["grading_ground_truth"],
        config_sha256="A" * 64,
        input_artifact_sha256=["B" * 64],
    )
    graph = GraphArtifact.build(
        scene_id="scene_000001",
        graph_method="oracle",
        graph_type="dag",
        graph_view="dag",
        nodes=["X000", "X001"],
        edges=[GraphEdge.build("X000", "X001", "directed")],
        provenance=provenance,
    )
    graph_path = tmp_path / "graph.json"
    graph.write(graph_path)
    mapping = VariableMap.build(
        "scene_000001", [("Treatment", "binary"), ("Outcome", "continuous")]
    )
    mapping_path = tmp_path / "variable_map.json"
    mapping_path.write_bytes(mapping.to_json_bytes())

    assert main(["validate-graph", str(graph_path)]) == 0
    assert "Valid graph" in capsys.readouterr().out
    assert main(["validate-variable-map", str(mapping_path)]) == 0
    assert "Valid variable map" in capsys.readouterr().out
