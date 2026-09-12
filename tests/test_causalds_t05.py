import json
import re
from pathlib import Path

import yaml

from fourgraph.causalds_scd import expand_candidates
from fourgraph.partial_graph import PartialGraph, consistent_extension


ROOT = Path(__file__).resolve().parents[1]


def test_t05_preregistration_expands_to_frozen_grid():
    config = yaml.safe_load(
        (ROOT / "configs" / "t05_scd_selection.yaml").read_text(encoding="utf-8")
    )
    candidates = expand_candidates(config)
    assert len(candidates) == 18
    assert sum(candidate.eligible_for_primary for candidate in candidates) == 12
    assert config["scope"]["forbid_holdout_access"] is True
    assert config["scope"]["downstream_reasoner_used_for_selection"] is False


def test_t05_selection_manifest_passes_registered_gates():
    manifest = json.loads(
        (ROOT / "data" / "manifests" / "p0_scd_selection.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["p0_scd_ready"] is True
    assert manifest["scope"]["holdout_accessed"] is False
    assert manifest["full_runs"] == 144
    assert manifest["stability_runs"] == 240
    selected = manifest["selected"]
    assert selected["candidate_id"] == "boss_basis_bic__p1__t3"
    assert selected["hard_gate_pass"] is True
    assert selected["stability_runs_succeeded"] == 80
    assert selected["stability_runs_expected"] == 80


def test_selected_dev_graphs_are_anonymous_valid_cpdag_contracts():
    records = [
        json.loads(line)
        for line in (
            ROOT / "data" / "manifests" / "t05_dev_graphs.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    selected = [
        record
        for record in records
        if record["record_type"] == "full"
        and record["candidate_id"] == "boss_basis_bic__p1__t3"
    ]
    assert len(selected) == 8
    for record in selected:
        graph = PartialGraph.build(
            record["graph"]["nodes"],
            record["graph"]["directed"],
            record["graph"]["undirected"],
        )
        projection = consistent_extension(graph)
        assert projection.to_dict() == record["projected_dag"]
        assert all(re.fullmatch(r"X\d{3}", node) for node in graph.nodes)
        assert record["deterministic_rerun_match"] is True
