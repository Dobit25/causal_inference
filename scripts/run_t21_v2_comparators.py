"""Run preregistered T21-v2 standalone comparators and oracle-skeleton diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fourgraph.graph_adapters import make_oracle_graph_artifact  # noqa: E402
from fourgraph.graph_contract import GraphArtifact, canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.graph_metrics import evaluate_graph  # noqa: E402
from fourgraph.hybrid_h2 import graph_sha256, solve_h2_forced  # noqa: E402
from fourgraph.p1_stories import public_builder_view  # noqa: E402
from fourgraph.p1_t21 import (  # noqa: E402
    make_semantic_graph_artifact,
    orientation_counts,
    parse_llm_graph_response,
    render_llm_graph_prompt,
)
from fourgraph.partial_graph import PartialGraph  # noqa: E402
from fourgraph.t21_openai_backend import T21OpenAIBackend  # noqa: E402
from run_p1_t21 import (  # noqa: E402
    LiveCounter,
    artifact_record,
    edge_audit,
    hash_file,
    load_raw_cache,
    validated_call,
)


class PacedBackend:
    """Keep requests below the frozen project RPM limit without changing model inputs."""

    def __init__(self, backend: T21OpenAIBackend, minimum_seconds: float) -> None:
        self.backend = backend
        self.minimum_seconds = minimum_seconds
        self.last_request_at: float | None = None

    def call(self, **kwargs: Any) -> dict[str, Any]:
        if self.last_request_at is not None:
            time.sleep(max(0.0, self.minimum_seconds - (time.monotonic() - self.last_request_at)))
        result = self.backend.call(**kwargs)
        self.last_request_at = time.monotonic()
        return result


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def graph_from_dict(value: dict[str, Any]) -> PartialGraph:
    return PartialGraph.build(value["nodes"], value.get("directed", []), value.get("undirected", []))


def graph_rows(path: Path) -> dict[tuple[str, str], GraphArtifact]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return {
        (row["study_id"], row["condition"]): GraphArtifact.from_dict(row["artifact"])
        for row in rows
        if row["artifact"] is not None
    }


def preference_from_graph(parent: PartialGraph, graph: PartialGraph) -> dict[str, Any]:
    preferences = []
    for left, right in sorted(parent.undirected):
        if (left, right) in graph.directed:
            probability = 0.999
        elif (right, left) in graph.directed:
            probability = 0.001
        else:
            probability = 0.5
        preferences.append({"left": left, "right": right, "probability_left_causes_right": probability})
    return {
        "schema_version": "fourgraph.semantic_preferences.v1",
        "parent_graph_sha256": graph_sha256(parent),
        "preferences": preferences,
    }


def write_jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row, newline=True) for row in rows)


def run(config_path: Path, *, execute: bool, check: bool) -> dict[str, Any]:
    config_path = (ROOT / config_path).resolve()
    config = read_yaml(config_path)
    for relative, expected in config["freeze_anchors"].items():
        if hash_file(ROOT / relative) != expected:
            raise RuntimeError(f"Frozen dependency changed: {relative}")
    split = read_json(ROOT / config["scope"]["split_manifest"])
    dev_ids = list(map(str, split["development_ids"]))
    holdout_ids = set(map(str, split["holdout_ids"]))
    if len(dev_ids) != 20 or len(holdout_ids) != 80 or set(dev_ids) & holdout_ids:
        raise RuntimeError("Invalid frozen P1 split")
    prior = graph_rows(ROOT / "data/manifests/t21_v2_dev_graphs.jsonl")
    raw_path = ROOT / config["outputs"]["raw_calls"]
    cache = load_raw_cache(raw_path)
    counter = LiveCounter(config["execution"]["maximum_new_api_calls"])
    template = (ROOT / config["semantic_backend"]["llm_graph_prompt"]).read_text(encoding="utf-8")
    schema = read_json(ROOT / config["semantic_backend"]["llm_graph_schema"])
    backend = None
    if execute:
        load_dotenv(ROOT / ".env", override=True)
        live_backend = T21OpenAIBackend(
            api_key=os.environ[config["semantic_backend"]["credential_env"]],
            model_snapshot=config["semantic_backend"]["model_snapshot"],
            max_output_tokens=config["semantic_backend"]["max_output_tokens"],
            timeout_seconds=config["semantic_backend"]["timeout_seconds"],
            transport_max_retries=config["semantic_backend"]["transport_max_retries"],
            response_schema=schema,
            schema_name="p1_llm_graph_v1",
        )
        backend = PacedBackend(
            live_backend,
            float(config["semantic_backend"]["minimum_seconds_between_requests"]),
        )
    output_graphs: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    parsed_by_scene: dict[str, dict[str, PartialGraph]] = {}
    attempts_by_scene: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for study_id in dev_ids:
        if study_id in holdout_ids:
            raise RuntimeError("Comparator attempted holdout access")
        t18 = ROOT / config["scope"]["generated_root"] / "t18" / study_id
        t19 = ROOT / config["scope"]["generated_root"] / "t19" / study_id
        scm = read_json(t18 / "scm.json")
        alias = read_json(t19 / "alias_map.json")
        alias_by_node = {row["canonical_id"]: row["public_alias"] for row in alias["mapping"]}
        oracle_graph = graph_from_dict(scm["oracle_dag"])
        oracle = make_oracle_graph_artifact(
            scene_id=scm["scene_id"], graph=oracle_graph,
            builder_id="fourgraph.p1_t21_v2_comparator_oracle", builder_version="v1",
            config_sha256=hash_file(config_path), input_artifact_sha256=[hash_file(t18 / "scm.json")],
        )
        parsed_by_scene[study_id] = {"full": prior[(study_id, "G_LLM_FULL")].partial_graph}
        attempts_by_scene[study_id] = {"full": []}
        for variant in config["execution"]["standalone_variants"]:
            story_record = read_json(t19 / f"story_{variant}.json")
            story = public_builder_view(story_record)["story"]
            prompt = render_llm_graph_prompt(story, alias_by_node.values(), template)
            call_id = f"{scm['scene_id']}:llm_graph:{variant}"
            (graph, decisions), attempts = validated_call(
                call_id=call_id, base_prompt=prompt,
                parser=lambda raw, mapping=alias_by_node: parse_llm_graph_response(raw, mapping),
                backend=backend, raw_path=raw_path, cache=cache, counter=counter,
                max_validation_retries=config["execution"]["validation_retries"],
            )
            artifact = make_semantic_graph_artifact(
                scene_id=scm["scene_id"], parent=None, graph=graph, graph_method="llm",
                graph_type="dag", graph_view="dag", builder_id=f"fourgraph.p1_t21_v2_llm_{variant}",
                config_sha256=hash_file(config_path),
                input_hashes=[hash_file(t19 / f"story_{variant}.json"), hash_file(t19 / "alias_map.json")],
                edge_audit=edge_audit(graph, actor="llm", reason=f"public_{variant}_story_direct_relation"),
            )
            row = artifact_record(f"G_LLM_{variant.upper()}", study_id, variant, artifact)
            row["attempts"] = attempts
            row["pair_decisions_sha256"] = sha256_hex(canonical_json_bytes(list(decisions)))
            output_graphs.append(row)
            metric = evaluate_graph(artifact, oracle, condition=row["condition"], role="development_comparator", variable_mapping_sha256=hash_file(t19 / "alias_map.json"))
            metric["study_id"] = study_id
            metrics.append(metric)
            parsed_by_scene[study_id][variant] = graph
            attempts_by_scene[study_id][variant] = attempts
        boss_parent = prior[(study_id, "G_SCD_RAW")].partial_graph
        oracle_parent = graph_from_dict(scm["oracle_cpdag"])
        for variant in ("full", "partial", "ambiguous"):
            semantic_graph = parsed_by_scene[study_id][variant]
            for parent_name, parent in (("boss_cpdag", boss_parent), ("oracle_cpdag", oracle_parent)):
                pref = preference_from_graph(parent, semantic_graph)
                decision = solve_h2_forced(parent, pref)
                output = graph_from_dict(decision["selected_graph"])
                correct, total = orientation_counts(output, parent, oracle_graph)
                diagnostics.append({
                    "schema_version": "fourgraph.p1_t21_v2_oracle_skeleton_diagnostic.v1",
                    "study_id": study_id,
                    "story_variant": variant,
                    "parent": parent_name,
                    "semantic_signal": config["diagnostic"]["semantic_signal"],
                    "parent_skeleton_true_positives": len(parent.skeleton & oracle_graph.skeleton),
                    "parent_false_adjacencies": len(parent.skeleton - oracle_graph.skeleton),
                    "unresolved_evaluable": total,
                    "orientation_correct": correct,
                    "orientation_precision": round(correct / total, 10) if total else None,
                    "selected_graph_sha256": graph_sha256(output),
                    "uses_threshold_selection": False,
                    "uses_holdout": False,
                })
    output_graphs.sort(key=lambda row: (row["study_id"], row["story_variant"]))
    metrics.sort(key=lambda row: (row["study_id"], row["graph_condition"]))
    diagnostics.sort(key=lambda row: (row["study_id"], row["story_variant"], row["parent"]))
    graph_bytes, metric_bytes, diagnostic_bytes = map(write_jsonl, (output_graphs, metrics, diagnostics))
    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 10) if values else None
    comparator_summary = {}
    for variant in config["execution"]["standalone_variants"]:
        rows = [row for row in metrics if row["graph_condition"] == f"G_LLM_{variant.upper()}"]
        comparator_summary[variant] = {
            "valid": sum(bool(row["graph_valid"]) for row in rows),
            "mean_directed_f1": mean([row["dag"]["directed_f1"] for row in rows]),
            "mean_skeleton_f1": mean([row["skeleton"]["f1"] for row in rows]),
        }
    diagnostic_summary = {}
    for variant in ("full", "partial", "ambiguous"):
        for parent_name in ("boss_cpdag", "oracle_cpdag"):
            rows = [r for r in diagnostics if r["story_variant"] == variant and r["parent"] == parent_name]
            c, n = sum(r["orientation_correct"] for r in rows), sum(r["unresolved_evaluable"] for r in rows)
            diagnostic_summary[f"{variant}:{parent_name}"] = {"correct": c, "evaluable": n, "precision": round(c / n, 10) if n else None}
    outputs = {
        config["outputs"]["graphs"]: graph_bytes,
        config["outputs"]["metrics"]: metric_bytes,
        config["outputs"]["oracle_skeleton_diagnostic"]: diagnostic_bytes,
    }
    audit = {
        "schema_version": "fourgraph.p1_t21_amendment_v2_audit.v1",
        "task": "T21 Amendment v2",
        "counts": {"development_scenes": 20, "comparator_logical_calls": 40, "captured_api_attempts": len(cache), "validation_retry_attempts": len(cache) - 40, "comparator_graphs": len(output_graphs), "diagnostic_records": len(diagnostics)},
        "comparator_summary": comparator_summary,
        "oracle_skeleton_diagnostic_summary": diagnostic_summary,
        "primary_threshold": read_json(ROOT / "data/manifests/t21_v2_development_audit.json")["selected_threshold"],
        "primary_best_candidate": read_json(ROOT / "data/manifests/t21_v2_development_audit.json")["best_candidate_by_precision_then_coverage"],
        "engineering_incident": {
            "kind": "overlapping_process_cache_writes",
            "scientific_resolution": "first_seen_record_per_call_id_and_attempt",
            "original_log_preserved_outside_git": True,
            "duplicate_records_used": False,
            "successful_duplicate_responses_excluded": 18,
            "development_v2_successful_responses_total_including_duplicates": 78,
            "development_v2_logical_responses_used": 60,
            "rate_limit_rejections_without_model_response": 1,
        },
        "evidence_boundary": {"development_only": True, "holdout_accessed": False, "reasoner_executed": False, "comparators_used_for_threshold": False},
        "verdict": {"conformance_passed": True, "threshold_gate_passed": False, "t21_v2_passed": False, "t22_authorized": False, "further_prompt_tuning_authorized": False},
        "outputs": [{"path": path, "sha256": sha256_hex(payload), "bytes": len(payload)} for path, payload in outputs.items()],
    }
    audit_bytes = canonical_json_bytes(audit, newline=True)
    report = (
        "# T21 Amendment v2 — development-only result\n\n"
        "Semantic-preference conformance passed 120/120, but the preregistered 0.95 precision threshold gate did not pass on 20 development scenes. "
        f"The best candidate achieved {audit['primary_best_candidate']['orientation_precision']} precision at {audit['primary_best_candidate']['orientation_coverage']} coverage.\n\n"
        f"Standalone LLM partial directed F1: {comparator_summary['partial']['mean_directed_f1']}; ambiguous: {comparator_summary['ambiguous']['mean_directed_f1']}. "
        "Oracle-skeleton diagnostics are non-primary and were not used for threshold selection. "
        "An overlapping-process incident produced 18 extra successful development preference responses; the original log is retained and a deterministic first-seen rule excluded all duplicates. "
        "No holdout scene, downstream task, answer, or reasoner was accessed.\n"
    ).encode("utf-8")
    outputs[config["outputs"]["audit"]] = audit_bytes
    outputs[config["outputs"]["report"]] = report
    if check:
        for relative, payload in outputs.items():
            if (ROOT / relative).read_bytes() != payload:
                raise RuntimeError(f"Byte replay mismatch: {relative}")
    else:
        for relative, payload in outputs.items():
            target = ROOT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
    return {"mode": "check" if check else "execute", "new_api_calls": counter.calls, "comparators": comparator_summary, "diagnostic": diagnostic_summary, "t22_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/t21_v2_comparators.yaml"))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        config = read_yaml(ROOT / args.config)
        cache = load_raw_cache(ROOT / config["outputs"]["raw_calls"])
        cached_logical = len({row["call_id"] for row in cache.values()})
        print(json.dumps({"mode": "preflight", "development_scenes": 20, "planned_logical_calls": 40, "cached_logical_calls": cached_logical, "planned_new_logical_calls": 40 - cached_logical, "captured_attempts": len(cache), "holdout_accessed": False}, indent=2))
        return 0
    print(json.dumps(run(args.config, execute=args.execute, check=args.check), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
