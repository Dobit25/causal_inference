"""Generate or byte-check the frozen T06 graph-contract examples and manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fourgraph.graph_adapters import (  # noqa: E402
    make_hybrid_graph_artifact,
    make_llm_graph_artifact,
    make_oracle_graph_artifact,
    make_scd_graph_artifact,
)
from fourgraph.graph_contract import (  # noqa: E402
    EdgeAuditRecord,
    GraphArtifact,
    VariableMap,
    assert_same_node_universe,
    canonical_json_bytes,
    project_cpdag_artifact,
    sha256_hex,
    validate_hybrid_relationship,
    validate_projection_relationship,
)
from fourgraph.partial_graph import PartialGraph  # noqa: E402


OUTPUTS = {
    "variable_map": Path("data/manifests/t06_variable_map_example.json"),
    "graphs": Path("data/manifests/t06_graph_contract_examples.jsonl"),
    "manifest": Path("data/manifests/graph_contract_v1.json"),
}

T05_FROZEN_HASHES = {
    "configs/t05_scd_selection.yaml": "6DDB755A2E3D2BE2F2BBCC21DFD9B78A677E69C0894CAC2C08EDD13F5D97ECCA",
    "configs/t05_scd_frozen.yaml": "729861541366775AFDCFB302E008C34866D2F2282D3614BA6578B79051330A33",
    "data/manifests/p0_scd_selection.json": "45BAACE1E4289786F927771BF37041A57A2A81D436541B1795D9D903839282F1",
    "data/manifests/t05_dev_graphs.jsonl": "60AE168B4D06AE1BD2C22B3D262D71D4CDC149CAFBA8A7013737135A62D08261",
}


def file_sha256(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _source_hash(label: str) -> str:
    return sha256_hex(label.encode("utf-8"))


def build_examples(config_sha256: str) -> tuple[VariableMap, tuple[GraphArtifact, ...]]:
    """Build one small cross-method fixture without benchmark/holdout access."""

    scene_id = "scene_999999"
    variable_map = VariableMap.build(
        scene_id,
        [
            ("Treatment", "binary"),
            ("Mediator", "continuous"),
            ("Outcome", "continuous"),
        ],
    )
    nodes = variable_map.node_ids
    llm = make_llm_graph_artifact(
        scene_id=scene_id,
        graph=PartialGraph.build(
            nodes, directed=[("X000", "X001"), ("X001", "X002")]
        ),
        builder_id="fourgraph.fixture.llm",
        builder_version="v1",
        config_sha256=config_sha256,
        input_artifact_sha256=[_source_hash("t06-public-story-fixture-v1")],
        seed=42,
    )
    scd = make_scd_graph_artifact(
        scene_id=scene_id,
        graph=PartialGraph.build(
            nodes, undirected=[("X000", "X001"), ("X001", "X002")]
        ),
        graph_type="cpdag",
        builder_id="fourgraph.fixture.scd",
        builder_version="v1",
        config_sha256=config_sha256,
        input_artifact_sha256=[_source_hash("t06-observational-fixture-v1")],
        seed=42,
    )
    projected = project_cpdag_artifact(
        scd, config_sha256=config_sha256, builder_version="v1"
    )
    hybrid_graph = PartialGraph.build(
        nodes, directed=[("X001", "X000"), ("X002", "X001")]
    )
    hybrid_audit = tuple(
        EdgeAuditRecord.build(
            step=index,
            source=source,
            target=target,
            action="orient",
            before_mark="undirected",
            after_mark="directed",
            actor="hybrid",
            reason="fixture_story_semantics",
            arbitrary=False,
            confidence=0.9,
        )
        for index, (source, target) in enumerate(sorted(hybrid_graph.directed))
    )
    hybrid = make_hybrid_graph_artifact(
        parent_scd=scd,
        graph=hybrid_graph,
        builder_id="fourgraph.fixture.hybrid",
        builder_version="v1",
        config_sha256=config_sha256,
        input_artifact_sha256=[_source_hash("t06-public-story-fixture-v1")],
        seed=42,
        edge_audit=hybrid_audit,
    )
    oracle = make_oracle_graph_artifact(
        scene_id=scene_id,
        graph=PartialGraph.build(
            nodes, directed=[("X000", "X001"), ("X002", "X001")]
        ),
        builder_id="fourgraph.fixture.oracle",
        builder_version="v1",
        config_sha256=config_sha256,
        input_artifact_sha256=[_source_hash("t06-grading-graph-fixture-v1")],
    )
    graphs = (llm, scd, projected, hybrid, oracle)
    assert_same_node_universe(graphs)
    validate_projection_relationship(scd, projected)
    validate_hybrid_relationship(scd, hybrid)
    return variable_map, graphs


def _file_record(path: Path, content: bytes, *, records: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": path.as_posix(),
        "size_bytes": len(content),
        "sha256": sha256_hex(content),
    }
    if records is not None:
        result["records"] = records
    return result


def build_artifacts(root: Path = PROJECT_ROOT) -> dict[str, bytes]:
    config_path = root / "configs/graph_contract_v1.yaml"
    config_sha256 = file_sha256(config_path)
    variable_map, graphs = build_examples(config_sha256)
    variable_bytes = variable_map.to_json_bytes()
    graph_bytes = b"".join(graph.to_json_bytes() for graph in graphs)

    dependencies = {
        path: {
            "sha256": file_sha256(root / path),
            "size_bytes": (root / path).stat().st_size,
        }
        for path in (
            "configs/graph_contract_v1.yaml",
            "schemas/graph_contract_v1.schema.json",
            "schemas/variable_map_v1.schema.json",
            "schemas/reasoner_graph_v1.schema.json",
        )
    }
    for path, expected in T05_FROZEN_HASHES.items():
        actual = file_sha256(root / path)
        if actual != expected:
            raise RuntimeError(f"Frozen T05 artifact changed: {path}: {actual}")

    manifest = {
        "manifest_version": 1,
        "task": "T06",
        "status": "complete_canonical_graph_contract_v1",
        "contract": {
            "graph_schema_version": "fourgraph.graph.v1",
            "variable_map_schema_version": "fourgraph.variable_map.v1",
            "structure_hash_scope": "canonical_nodes_and_edges_only",
            "artifact_hash_scope": "full_artifact_without_artifact_sha256",
            "semantic_validator": "fourgraph.graph_contract.GraphArtifact",
            "source_adapters": "fourgraph.graph_adapters",
            "reasoner_view": "provenance_blind_structure_only",
            "metrics_view": "normalized_PartialGraph",
        },
        "dependencies": dependencies,
        "generated": {
            "variable_map": _file_record(OUTPUTS["variable_map"], variable_bytes),
            "graph_examples": _file_record(
                OUTPUTS["graphs"], graph_bytes, records=len(graphs)
            ),
        },
        "example_coverage": [
            {"graph_method": graph.graph_method, "graph_view": graph.graph_view}
            for graph in graphs
        ],
        "invariants_verified": [
            "one_canonical_node_universe",
            "canonical_byte_serialization",
            "structure_and_artifact_hash_separation",
            "dag_acyclicity",
            "exact_completed_pdag_validation",
            "source_evidence_allowlists",
            "projection_parent_and_trace_validation",
            "hybrid_parent_and_edge_audit_validation",
            "reasoner_provenance_blinding",
        ],
        "t05_frozen_artifacts_unchanged": T05_FROZEN_HASHES,
        "experimental_data_accessed": False,
        "holdout_accessed": False,
    }
    manifest_bytes = canonical_json_bytes(manifest, newline=True)
    return {
        "variable_map": variable_bytes,
        "graphs": graph_bytes,
        "manifest": manifest_bytes,
    }


def _check_bytes(path: Path, expected: bytes) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Expected generated artifact is missing: {path}")
    if path.read_bytes() != expected:
        raise RuntimeError(f"Generated artifact is stale: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    artifacts = build_artifacts()
    if args.check:
        for name, relative_path in OUTPUTS.items():
            _check_bytes(PROJECT_ROOT / relative_path, artifacts[name])
    else:
        for name, relative_path in OUTPUTS.items():
            path = PROJECT_ROOT / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(artifacts[name])

    manifest = json.loads(artifacts["manifest"])
    print(
        json.dumps(
            {
                "mode": "check" if args.check else "write",
                "status": manifest["status"],
                "graph_examples": manifest["generated"]["graph_examples"]["records"],
                "holdout_accessed": manifest["holdout_accessed"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
