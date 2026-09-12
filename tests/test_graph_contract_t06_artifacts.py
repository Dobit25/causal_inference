import hashlib
import json
import subprocess
import sys
from pathlib import Path

from fourgraph.graph_adapters import make_scd_graph_artifact
from fourgraph.graph_contract import (
    GraphArtifact,
    VariableMap,
    assert_same_node_universe,
    validate_hybrid_relationship,
    validate_projection_relationship,
)
from fourgraph.partial_graph import PartialGraph


ROOT = Path(__file__).resolve().parents[1]
SHA = "A" * 64


def _load_examples() -> list[GraphArtifact]:
    return [
        GraphArtifact.from_dict(json.loads(line))
        for line in (
            ROOT / "data/manifests/t06_graph_contract_examples.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]


def test_frozen_examples_cover_every_consumer_and_relationship():
    graphs = _load_examples()
    assert len(graphs) == 5
    assert {(item.graph_method, item.graph_view) for item in graphs} == {
        ("llm", "dag"),
        ("scd", "cpdag"),
        ("scd", "projected_dag"),
        ("hybrid", "dag"),
        ("oracle", "dag"),
    }
    assert assert_same_node_universe(graphs) == ("X000", "X001", "X002")
    scd = next(item for item in graphs if item.graph_view == "cpdag")
    projected = next(item for item in graphs if item.graph_view == "projected_dag")
    hybrid = next(item for item in graphs if item.graph_method == "hybrid")
    validate_projection_relationship(scd, projected)
    validate_hybrid_relationship(scd, hybrid)
    assert projected.graph_sha256 == hybrid.graph_sha256
    assert projected.artifact_sha256 != hybrid.artifact_sha256
    assert projected.reasoner_view() == hybrid.reasoner_view()
    assert projected.reasoner_json_bytes() == hybrid.reasoner_json_bytes()


def test_frozen_map_and_golden_structure_hashes_are_stable():
    mapping = VariableMap.from_dict(
        json.loads(
            (ROOT / "data/manifests/t06_variable_map_example.json").read_text(
                encoding="utf-8"
            )
        )
    )
    graphs = _load_examples()
    assert mapping.mapping_sha256 == (
        "4A5AF4C151672BE09E0795DC04270DC9BD558711FCF3838E1ACF16C9AF92B290"
    )
    assert graphs[0].graph_sha256 == (
        "10F99765BF75961E08207139C00ACEC784FA79F773D7A25760EDF30BE96B81E9"
    )


def test_reasoner_schema_exposes_only_the_frozen_structural_fields():
    schema = json.loads(
        (ROOT / "schemas/reasoner_graph_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    view = _load_examples()[0].reasoner_view()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "schema_version",
        "graph_type",
        "nodes",
        "edges",
    }
    assert set(view) == set(schema["required"])


def test_t06_manifest_hashes_match_versioned_files():
    manifest = json.loads(
        (ROOT / "data/manifests/graph_contract_v1.json").read_text(encoding="utf-8")
    )
    assert manifest["holdout_accessed"] is False
    for record in manifest["generated"].values():
        content = (ROOT / record["path"]).read_bytes()
        assert len(content) == record["size_bytes"]
        assert hashlib.sha256(content).hexdigest().upper() == record["sha256"]
    for path, record in manifest["dependencies"].items():
        content = (ROOT / path).read_bytes()
        assert len(content) == record["size_bytes"]
        assert hashlib.sha256(content).hexdigest().upper() == record["sha256"]


def test_t06_generator_reproduces_all_artifacts_byte_for_byte():
    result = subprocess.run(
        [sys.executable, "scripts/build_graph_contract_t06.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert '"mode": "check"' in result.stdout


def test_t05_selected_cpdag_records_upgrade_to_v1_without_rewriting_t05():
    records = [
        json.loads(line)
        for line in (ROOT / "data/manifests/t05_dev_graphs.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    selected = [
        record
        for record in records
        if record["record_type"] == "full"
        and record["candidate_id"] == "boss_basis_bic__p1__t3"
    ]
    artifacts = []
    for record in selected:
        value = record["graph"]
        artifacts.append(
            make_scd_graph_artifact(
                scene_id=record["scene_id"],
                graph=PartialGraph.build(
                    value["nodes"], value["directed"], value["undirected"]
                ),
                graph_type="cpdag",
                builder_id="fourgraph.t05.compatibility_test",
                builder_version="v1",
                config_sha256=SHA,
                input_artifact_sha256=[SHA],
                seed=42,
            )
        )
    assert len(artifacts) == 8
