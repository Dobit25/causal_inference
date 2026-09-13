import ast
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from fourgraph.p1_stories import assign_aliases, public_builder_view, select_partial_edges


ROOT = Path(__file__).resolve().parents[1]
STORIES = ROOT / "data/manifests/t19_p1_story_manifest.jsonl"
ALIASES = ROOT / "data/manifests/t19_p1_alias_manifest.jsonl"
PANEL = ROOT / "data/manifests/t19_p1_blinded_review_panel.jsonl"
REVIEW = ROOT / "data/reviews/t19_p1_blinded_review.jsonl"
AUDIT = ROOT / "data/manifests/t19_p1_story_audit.json"
SHA256 = re.compile(r"^[0-9A-F]{64}$")
CANONICAL = re.compile(r"\bX[0-9]{3}\b")


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def test_t19_implementation_is_offline_and_does_not_import_execution_backends():
    paths = (ROOT / "scripts/build_p1_t19.py", ROOT / "src/fourgraph/p1_stories.py")
    imports: set[str] = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
        imports.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    forbidden = {
        name
        for name in imports
        if name == "openai"
        or name.startswith("google.genai")
        or "openai_backend" in name
        or name.endswith("reasoner")
    }
    assert forbidden == set()


def test_t19_config_preserves_frozen_variants_and_execution_boundary():
    config = yaml.safe_load((ROOT / "configs/t19_p1_semantic_stories.yaml").read_text(encoding="utf-8"))
    assert config["stories"]["variants"] == ["full", "partial", "ambiguous"]
    assert config["stories"]["partial"]["selected_edge_count"] == "round_half_up_half_of_true_edge_count"
    assert config["aliases"]["canonical_mapping_model_visible"] is False
    assert config["aliases"]["canonical_mapping_reasoner_visible"] is False
    assert config["public_builder_view"]["fields"] == ["story"]
    boundary = config["access_boundary"]
    assert boundary["api_calls"] == 0
    assert boundary["LLM_execution_authorized"] is False
    assert boundary["SCD_execution_authorized"] is False
    assert boundary["reasoner_execution_authorized"] is False
    assert boundary["H2_implementation_or_execution_authorized"] is False
    assert boundary["holdout_story_content_manual_review_authorized"] is False
    assert boundary["holdout_method_evaluation_authorized"] is False


def test_t19_story_manifest_has_three_exact_doses_per_scene_without_story_or_graph():
    rows = _jsonl(STORIES)
    by_scene: dict[str, list[dict]] = defaultdict(list)
    assert len(rows) == 300
    for row in rows:
        by_scene[row["study_id"]].append(row)
        assert SHA256.fullmatch(row["artifact_sha256"])
        assert SHA256.fullmatch(row["builder_view_sha256"])
        assert SHA256.fullmatch(row["alias_map_sha256"])
        assert row["public_names_or_story_persisted_in_manifest"] is False
        assert row["gold_graph_persisted_in_manifest"] is False
        assert "story" not in row
        assert "edges" not in row
    assert len(by_scene) == 100
    assert Counter(row["split"] for row in rows) == {"holdout": 240, "development": 60}
    for scene_rows in by_scene.values():
        variants = {row["variant"]: row for row in scene_rows}
        assert set(variants) == {"full", "partial", "ambiguous"}
        edge_count = variants["full"]["edge_claim_count"]
        assert variants["full"]["directional_claim_count"] == edge_count
        assert variants["partial"]["directional_claim_count"] == (edge_count + 1) // 2
        assert variants["ambiguous"]["directional_claim_count"] == 0
        assert len({row["alias_map_sha256"] for row in scene_rows}) == 1


def test_t19_alias_manifest_pins_mapping_without_exposing_names():
    rows = _jsonl(ALIASES)
    text = ALIASES.read_text(encoding="utf-8")
    assert len(rows) == 100
    assert " index" not in text
    assert Counter(row["split"] for row in rows) == {"holdout": 80, "development": 20}
    assert all(row["public_aliases_not_persisted_in_manifest"] for row in rows)
    assert all(row["model_visible"] is False and row["reasoner_visible"] is False for row in rows)


def test_t19_blinded_panel_contains_only_development_story_stimuli():
    rows = _jsonl(PANEL)
    serialized = PANEL.read_text(encoding="utf-8")
    assert len(rows) == 20
    assert not CANONICAL.search(serialized)
    assert not re.search(r"scene_1[0-9]{5}", serialized)
    for forbidden in ("P1S", '"split"', '"variant"', "oracle", "cpdag", "seed"):
        assert forbidden not in serialized.lower() if forbidden.islower() else forbidden not in serialized
    for row in rows:
        assert set(row) == {"schema_version", "blind_scene_id", "stories"}
        assert [item["slot"] for item in row["stories"]] == ["A", "B", "C"]
        assert all(set(item) == {"slot", "story"} for item in row["stories"])


def test_t19_internal_blinded_review_is_complete_and_explicitly_limited():
    rows = _jsonl(REVIEW)
    assert len(rows) == 20
    assert all(row["scene_pass"] for row in rows)
    assert all(row["minimum_naturalness_score_1_to_5"] >= 4 for row in rows)
    assert all(row["reviewer_role"] == "codex_internal_blinded_text_qa" for row in rows)
    assert all(set(row["slot_evidence_classification"].values()) == {"all_directional", "mixed", "none_directional"} for row in rows)
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["manual_blinded_audit"]["scene_passes"] == 20
    assert audit["manual_blinded_audit"]["evidence_classifications_correct"] == 60
    assert audit["manual_blinded_audit"]["independent_external_human_review"] is False
    assert audit["limitations"]["manual_review_is_internal_not_independent_external_human_review"] is True


def test_t19_audit_pins_outputs_truth_checks_and_next_boundary():
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    counts = audit["counts"]
    assert counts["scenes"] == 100 and counts["public_stories"] == 300
    assert counts["full_directional_claims"] == counts["full_edge_claims"] == 684
    assert counts["partial_directional_claims"] == 367
    assert counts["ambiguous_directional_claims"] == 0
    assert counts["false_directional_claims"] == 0
    assert counts["nonedge_direct_claims"] == 0
    assert counts["canonical_ids_in_story"] == 0
    assert counts["manual_panel_holdout_scenes"] == 0
    evidence = audit["evidence_boundary"]
    assert evidence["api_calls"] == 0
    assert evidence["LLM_executed"] is False
    assert evidence["SCD_executed"] is False
    assert evidence["reasoner_executed"] is False
    assert evidence["H1_executed"] is False
    assert evidence["H2_implemented_or_executed"] is False
    assert evidence["holdout_story_content_manually_reviewed"] is False
    verdict = audit["verdict"]
    assert verdict["t19_complete"] is True
    assert verdict["t20_h2_offline_conformance_authorized"] is True
    assert verdict["live_model_calls_authorized"] is False
    assert verdict["p1_holdout_evaluation_authorized"] is False
    outputs = {item["path"]: item for item in audit["outputs"]}
    for relative in (
        "data/manifests/t19_p1_story_manifest.jsonl",
        "data/manifests/t19_p1_alias_manifest.jsonl",
        "data/manifests/t19_p1_blinded_review_panel.jsonl",
        "reports/t19_p1_semantic_stories.md",
    ):
        path = ROOT / relative
        assert outputs[relative]["bytes"] == path.stat().st_size
        assert outputs[relative]["sha256"] == _sha256(path)


def test_t19_alias_and_partial_selection_are_deterministic_and_separated():
    nodes = ["X000", "X001", "X002", "X003", "X004"]
    lexicon = ["A index", "B index", "C index", "D index", "E index"]
    first = assign_aliases(nodes, lexicon, 1701, "P1S000")
    assert first == assign_aliases(nodes, lexicon, 1701, "P1S000")
    assert first != assign_aliases(nodes, lexicon, 1701, "P1S001")
    edges = [("X000", "X001"), ("X000", "X002"), ("X002", "X003")]
    selected = select_partial_edges(edges, 1701, "P1S000")
    assert len(selected) == 2
    assert selected == select_partial_edges(list(reversed(edges)), 1701, "P1S000")


def test_t19_public_builder_view_is_a_strict_story_only_allowlist():
    record = {
        "study_id": "P1S000",
        "scene_id": "scene_100000",
        "evidence_variant": "full",
        "builder_input": {"story": "A public story"},
    }
    assert public_builder_view(record) == {"story": "A public story"}
    bad = {**record, "builder_input": {"story": "A public story", "scene_id": "scene_100000"}}
    try:
        public_builder_view(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("Builder allowlist accepted metadata")
