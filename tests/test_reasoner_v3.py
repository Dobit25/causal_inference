from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from fourgraph.reasoner import TASKS
from fourgraph.reasoner_v3 import PromptV3Bundle


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs/t12_v3_prompt.yaml"


def _config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _bundle() -> PromptV3Bundle:
    config = _config()["prompt_bundle"]
    return PromptV3Bundle.load(
        base_path=ROOT / config["base"],
        module_paths={task: ROOT / path for task, path in config["modules"].items()},
    )


def test_v3_keeps_mini_d_runtime_and_changes_only_prompt_contract() -> None:
    v2 = yaml.safe_load(
        (ROOT / "configs/t12_v2_openai_mini_d.yaml").read_text(encoding="utf-8")
    )
    v3 = _config()
    assert v3["reasoner"] == v2["reasoner"]
    assert v3["controlled_change"] == {
        "field": "prompt_contract",
        "from": "prompts/reasoner_cpdag_conservative_v2.txt",
        "to": "shared_base_plus_five_task_specific_v3_modules",
    }
    assert v3["graph_encoding"]["unchanged_from_mini_d"] is True
    assert v3["live_execution"]["allowed"] is False
    assert v3["holdout"]["accessed"] is False


def test_v3_routes_exactly_one_task_module_and_freezes_sentinels() -> None:
    bundle = _bundle()
    for task in TASKS:
        template = bundle.template_for(task)
        assert task in bundle.modules[task]
        assert all(
            other not in bundle.modules[task] for other in TASKS if other != task
        )
        assert "no_valid_adjustment_set" in template
        assert '"no_backdoor"' in template
        assert '"undetermined"' in template
        assert "[]" in template and "[[]]" in template
        assert "{{TASK_MODULE}}" not in template
        assert template.count("{{GRAPH_JSON}}") == 1
        assert template.count("{{QUERY_JSON}}") == 1
        assert template.count("{{GLOSSARY_JSON}}") == 1


def test_v3_render_is_provenance_blind_and_has_no_gold_or_story() -> None:
    bundle = _bundle()
    graph = {
        "schema_version": "fourgraph.reasoner_graph.v1",
        "graph_type": "dag",
        "nodes": ["X000", "X001", "X002"],
        "edges": [{"mark": "directed", "source": "X000", "target": "X001"}],
    }
    query = {
        "schema_version": "fourgraph.reasoner_query.v2",
        "task_id": TASKS[2],
        "treatment": "X000",
        "outcome": "X001",
        "candidate_variables": ["X002"],
        "response_field": "k",
        "allowed_sentinels": ["no_backdoor", "non_id", "undetermined"],
    }
    rendered = bundle.render(
        task_id=TASKS[2],
        graph_reasoner_view=graph,
        query_view=query,
        glossary=[
            {"id": "X000", "type": "continuous"},
            {"id": "X001", "type": "continuous"},
            {"id": "X002", "type": "continuous"},
        ],
    )
    assert '"graph_type":"dag"' in rendered
    assert '"response_field":"k"' in rendered
    assert "graph_sha256" not in rendered
    assert "graph_method" not in rendered
    assert "scene_id" not in rendered
    assert "gold_answer" not in rendered
    assert "public_story" not in rendered


def test_v3_examples_cover_registered_ambiguities() -> None:
    base = _bundle().base_template
    assert "empty set is valid" in base
    assert "direct outcome-to-treatment edge" in base
    assert "CPDAG invariance" in base
    assert "CPDAG non-invariance" in base
    assert "forbidden control" in base
    assert "sentinel precedence" in base.lower()


def test_v3_manifest_matches_files_and_keeps_design_record_non_live() -> None:
    manifest = json.loads(
        (ROOT / "data/manifests/t12_v3_prompt_contract.json").read_text(
            encoding="utf-8"
        )
    )
    config = _config()
    assert manifest["config_sha256"] == hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest().upper()
    assert set(manifest["prompt_components"]["modules"]) == set(TASKS)
    assert manifest["internal_no_valid_set_name"] == "no_valid_adjustment_set"
    assert manifest["official_no_valid_set_serialization"] == "no_backdoor"
    assert manifest["opened_v2_suite_role"] == "prompt_development_diagnostic_only"
    assert manifest["new_sealed_suite_status"] == "generated_independently_audited_and_frozen"
    assert manifest["live_execution_allowed"] is False
    assert manifest["holdout_accessed"] is False
    assert config["calibration"]["opened_v2_suite"]["eligible_for_v3_final_gate"] is False


def test_v2_prompt_and_mini_d_results_remain_immutable() -> None:
    frozen = {
        "prompts/reasoner_cpdag_conservative_v2.txt": "D8A5F981B6BA5B3679F37A8F2A7C694377E4847A14C5E29F0C027EA3F9A0D0D1",
        "data/manifests/t12_v2_openai_mini_d_conformance_scores.jsonl": "DD0F3D5604CA682C44939BF63C6FA4DD1013970459319C106977146264B62E62",
        "data/manifests/t12_v2_openai_mini_d_conformance_audit.json": "FCDF82156F88AE355D6A50E6C60C888FCC88BE70DCD7E8C09FC332E02F4C770A",
    }
    for relative, expected in frozen.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest().upper() == expected
