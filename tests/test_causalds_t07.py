import ast
import hashlib
import json
from pathlib import Path

import pytest

from fourgraph.causalds_access import (
    GradingPurpose,
    resolve_grading_artifact,
)
from fourgraph.causalds_oracle import (
    OracleLoadResult,
    load_causalds_oracle_graph,
    load_oracle_dag_for_dev_scoring,
)
from fourgraph.graph_contract import GraphArtifact, VariableMap


ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "data/manifests/t07_oracle_loader_audit.json"
SHA = "A" * 64
DEV_IDS = (
    "scene_000098",
    "scene_000172",
    "scene_000402",
    "scene_000415",
    "scene_000511",
    "scene_000719",
    "scene_000792",
    "scene_000814",
)


def _fixture_documents(scene_id: str) -> tuple[dict, dict]:
    names = ["Treatment", "Mediator", "Outcome"]
    schema = {
        "n_rows": 10,
        "n_columns": 3,
        "columns": {
            "Treatment": {"dtype": "float64", "is_binary": True},
            "Mediator": {"dtype": "float64"},
            "Outcome": {"dtype": "float64"},
        },
    }
    ground_truth = {
        "scene_id": scene_id,
        "graph": {
            "nodes_named": names,
            "observed_nodes_named": names,
            "latent_nodes_named": [],
            "edges_named": [["Treatment", "Mediator"], ["Mediator", "Outcome"]],
            "edges_named_observed": [
                ["Treatment", "Mediator"],
                ["Mediator", "Outcome"],
            ],
        },
        "mapping": {"X": "Treatment", "M": "Mediator", "Y": "Outcome"},
        "causal": {"valid_backdoor_sets_named": [["Mediator"]]},
        "gold_answer": "must_not_escape_loader",
    }
    return schema, ground_truth


def _write_fixture(
    root: Path,
    scene_id: str,
    *,
    mutate=None,
) -> None:
    schema, ground_truth = _fixture_documents(scene_id)
    if mutate is not None:
        mutate(schema, ground_truth)
    public = (
        root
        / "data/benchmark/main/scenes"
        / scene_id
        / "variants/clean"
    )
    grading = root / "data/benchmark/main/scenes_private" / scene_id
    public.mkdir(parents=True, exist_ok=True)
    grading.mkdir(parents=True, exist_ok=True)
    (public / "schema.json").write_text(
        json.dumps(schema), encoding="utf-8"
    )
    (grading / "ground_truth.json").write_text(
        json.dumps(ground_truth), encoding="utf-8"
    )


def test_oracle_loader_returns_only_canonical_safe_objects(tmp_path):
    _write_fixture(tmp_path, "scene_000001")
    result = load_causalds_oracle_graph(
        tmp_path, "scene_000001", config_sha256=SHA
    )
    assert isinstance(result, OracleLoadResult)
    assert isinstance(result.variable_map, VariableMap)
    assert isinstance(result.graph_artifact, GraphArtifact)
    assert result.variable_map.node_ids == ("X000", "X001", "X002")
    assert [item.variable_type for item in result.variable_map.variables] == [
        "binary",
        "continuous",
        "continuous",
    ]
    graph = result.graph_artifact
    assert (graph.graph_method, graph.graph_type, graph.graph_view) == (
        "oracle",
        "dag",
        "dag",
    )
    assert graph.partial_graph.directed == frozenset(
        {("X000", "X001"), ("X001", "X002")}
    )
    assert set(graph.provenance.evidence_sources) == {
        "grading_ground_truth",
        "public_schema_mapping",
    }
    assert len(graph.provenance.input_artifact_sha256) == 2

    safe = result.audit_record()
    assert not ({"edges", "gold_answer", "causal", "raw_ground_truth"} & set(safe))
    reasoner_payload = json.dumps(graph.reasoner_view())
    for forbidden in ("oracle", "ground_truth", "scene_", "sha256", "provenance"):
        assert forbidden not in reasoner_payload


def test_t05_dev_scoring_helper_is_oracle_module_only(tmp_path):
    _write_fixture(tmp_path, "scene_000001")
    graph = load_oracle_dag_for_dev_scoring(
        tmp_path, "scene_000001", ("X000", "X001", "X002")
    )
    assert graph.directed == frozenset(
        {("X000", "X001"), ("X001", "X002")}
    )
    with pytest.raises(ValueError, match="anonymous node set"):
        load_oracle_dag_for_dev_scoring(
            tmp_path, "scene_000001", ("A", "B", "C")
        )


def test_grading_capability_is_typed_and_artifact_scoped(tmp_path):
    with pytest.raises(PermissionError, match="Purpose cannot access"):
        resolve_grading_artifact(
            tmp_path,
            "scene_000001",
            "ground_truth",
            purpose="oracle",  # type: ignore[arg-type]
        )
    with pytest.raises(PermissionError, match="cannot access artifact"):
        resolve_grading_artifact(
            tmp_path,
            "scene_000001",
            "test",
            purpose=GradingPurpose.ORACLE,
        )
    path = resolve_grading_artifact(
        tmp_path,
        "scene_000001",
        "ground_truth",
        purpose=GradingPurpose.ORACLE,
    )
    assert "scenes_private" in path.parts


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda schema, truth: truth["graph"]["latent_nodes_named"].append("U"),
            "latent nodes",
        ),
        (
            lambda schema, truth: truth["graph"]["observed_nodes_named"].remove(
                "Outcome"
            ),
            "observed nodes",
        ),
        (
            lambda schema, truth: truth["graph"]["edges_named_observed"].append(
                ["Unknown", "Outcome"]
            ),
            "unknown public node",
        ),
        (
            lambda schema, truth: (
                truth["graph"].update(
                    {
                        "edges_named": [
                            ["Treatment", "Mediator"],
                            ["Mediator", "Outcome"],
                            ["Outcome", "Treatment"],
                        ],
                        "edges_named_observed": [
                            ["Treatment", "Mediator"],
                            ["Mediator", "Outcome"],
                            ["Outcome", "Treatment"],
                        ],
                    }
                )
            ),
            "cycle",
        ),
        (
            lambda schema, truth: truth.update({"scene_id": "scene_999999"}),
            "scene_id",
        ),
    ],
)
def test_oracle_loader_rejects_invalid_grading_graphs(tmp_path, mutate, message):
    _write_fixture(tmp_path, "scene_000001", mutate=mutate)
    with pytest.raises(ValueError, match=message):
        load_causalds_oracle_graph(
            tmp_path, "scene_000001", config_sha256=SHA
        )


def test_non_oracle_runtime_scd_has_no_grading_dependency():
    path = ROOT / "src/fourgraph/causalds_scd.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "resolve_grading_artifact" not in imported_names
    assert "fourgraph.causalds_oracle" not in imported_names
    assert "scenes_private" not in source
    assert "ground_truth" not in source


def test_grading_resolver_imports_are_allowlisted():
    allowed = {"causalds_integrity.py", "causalds_oracle.py", "causalds_scoring.py"}
    importers = set()
    for path in (ROOT / "src/fourgraph").glob("*.py"):
        if path.name == "causalds_access.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imports_resolver = isinstance(node, ast.ImportFrom) and any(
                alias.name == "resolve_grading_artifact" for alias in node.names
            )
            calls_resolver_attribute = (
                isinstance(node, ast.Attribute)
                and node.attr == "resolve_grading_artifact"
            )
            if imports_resolver or calls_resolver_attribute:
                importers.add(path.name)
    assert importers == allowed


def test_private_layout_literals_are_limited_to_access_and_historical_audit():
    allowed = {"causalds_access.py", "causalds_inventory.py"}
    users = {
        path.name
        for path in (ROOT / "src/fourgraph").glob("*.py")
        if "scenes_private" in path.read_text(encoding="utf-8")
    }
    assert users == allowed


def test_versioned_t07_audit_is_dev_only_and_edge_free():
    manifest = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    assert manifest["status"] == "complete_oracle_loader_ready"
    assert manifest["scope"]["scene_ids"] == list(DEV_IDS)
    assert manifest["scope"]["holdout_accessed"] is False
    assert manifest["scope"]["downstream_reasoner_used"] is False
    assert manifest["aggregate"]["scenes_succeeded"] == 8
    assert manifest["aggregate"]["all_valid_dags"] is True
    assert manifest["verdict"]["oracle_loader_ready"] is True
    for record in manifest["records"]:
        assert not (
            {"edges", "gold_answer", "causal", "raw_ground_truth"} & set(record)
        )


def test_t07_audit_and_config_hashes_are_indexed():
    source_manifest = json.loads(
        (ROOT / "data/manifests/causalds.json").read_text(encoding="utf-8")
    )
    record = source_manifest["derived_artifacts"]["t07_oracle_loader"]
    content = AUDIT_PATH.read_bytes()
    config = (ROOT / record["config"]).read_bytes()
    assert len(content) == record["size_bytes"]
    assert hashlib.sha256(content).hexdigest().upper() == record["sha256"]
    assert hashlib.sha256(config).hexdigest().upper() == record["config_sha256"]
