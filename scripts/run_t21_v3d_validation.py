"""Run, resume, or replay the validation-only T21 v3-D gate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
import yaml
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fourgraph.causalds_scd import SceneData, TetradBackend  # noqa: E402
from fourgraph.edge_selective import (  # noqa: E402
    prepare_edge_selective,
    score_edge_selective,
    solve_prepared_edge_selective,
)
from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.p1_stories import public_builder_view  # noqa: E402
from fourgraph.p1_t21 import parse_preference_response, render_preference_prompt  # noqa: E402
from fourgraph.partial_graph import PartialGraph  # noqa: E402
from fourgraph.scd_graph import SCDGraphPolicy, build_scd_graphs  # noqa: E402
from fourgraph.t21_openai_backend import T21OpenAIBackend  # noqa: E402


DEFAULT_CONFIG = Path("configs/t21_v3d_validation.yaml")


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _jsonl_bytes(rows: list[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row, newline=True) for row in rows)


def _graph(record: Mapping[str, Any]) -> PartialGraph:
    return PartialGraph.build(record["nodes"], record.get("directed", ()), record.get("undirected", ()))


def _validate(config: Mapping[str, Any], config_path: Path) -> tuple[list[str], dict[str, dict[str, Any]]]:
    if config["schema_version"] != "fourgraph.t21_v3d_validation.v1" or config["task"] != "T21_AMENDMENT_V3D":
        raise RuntimeError("T21 v3-D config drift")
    for relative, expected in config["freeze_anchors"].items():
        if _hash(ROOT / relative) != expected:
            raise RuntimeError(f"Frozen dependency changed: {relative}")
    audit = _json(ROOT / "data/manifests/t21_v3c_validation_generation_audit.json")
    if not audit["verdict"]["t21_v3d_authorized"] or audit["verdict"]["api_calls"] != 0:
        raise RuntimeError("T21 v3-C does not authorize v3-D")
    cohort = _json(ROOT / config["scope"]["cohort"])
    ids = list(map(str, cohort["study_ids"]))
    if ids != [f"P1V{index:03d}" for index in range(20)]:
        raise RuntimeError("Validation cohort ID drift")
    if cohort["existing_development_overlap"] or cohort["existing_holdout_overlap"]:
        raise RuntimeError("Validation cohort overlaps an existing cohort")
    inventory_rows = _jsonl(ROOT / config["scope"]["inventory"])
    inventory = {str(row["study_id"]): row for row in inventory_rows}
    if set(inventory) != set(ids) or len(inventory_rows) != 20:
        raise RuntimeError("Validation inventory drift")
    if config["execution"]["semantic_preference_calls"] != 60 or config["edge_selective"]["candidates"] != 20:
        raise RuntimeError("V3-D execution cardinality drift")
    semantic = config["edge_selective"]["threshold_grid"]["semantic_confidence"]
    stability = config["edge_selective"]["threshold_grid"]["global_stability"]
    if semantic != [0.80, 0.90, 0.95, 0.99, 0.999] or stability != [0.80, 0.90, 0.95, 1.00]:
        raise RuntimeError("V3-D threshold grid drift")
    if len(semantic) * len(stability) != 20:
        raise RuntimeError("V3-D threshold count drift")
    boundary = config["evidence_boundary"]
    if boundary["validation_tasks_or_answers_access_authorized"] or boundary["existing_development_access_authorized"] or boundary["final_holdout_access_authorized"] or boundary["reasoner_execution_authorized"]:
        raise RuntimeError("V3-D evidence boundary drift")
    freeze_path = ROOT / config["scope"]["preflight_freeze"]
    if not freeze_path.is_file():
        raise RuntimeError("T21 v3-D preflight has not been frozen")
    freeze = _json(freeze_path)
    if freeze["config_sha256"] != _hash(config_path):
        raise RuntimeError("T21 v3-D config changed after preflight freeze")
    current_runner_hash = _hash(Path(__file__).resolve())
    if freeze["runner_sha256"] != current_runner_hash:
        # A post-live replay amendment may change only audit serialization. The
        # original audit must prove that the frozen runner produced live data.
        audit_path = ROOT / config["outputs"]["audit"]
        raw_path = ROOT / config["outputs"]["raw_calls"]
        if not audit_path.is_file() or not raw_path.is_file():
            raise RuntimeError("T21 v3-D runner changed before live execution")
        prior = _json(audit_path)
        live_runner = prior.get("live_execution_freeze", {}).get("live_runner_sha256")
        if live_runner is None:
            live_runner = next(
                (row["sha256"] for row in prior["implementation_dependencies"] if row["path"] == "scripts/run_t21_v3d_validation.py"),
                None,
            )
        if live_runner != freeze["runner_sha256"] or prior["counts"]["api_attempts_captured"] != 60:
            raise RuntimeError("T21 v3-D replay amendment lacks frozen live-run evidence")
    if not freeze["verdict"]["live_validation_execution_authorized"]:
        raise RuntimeError("T21 v3-D preflight did not authorize live execution")
    return ids, inventory


def _runtime(config: Mapping[str, Any]) -> None:
    actual = {
        "python": platform.python_version(), "numpy": importlib.metadata.version("numpy"),
        "jpype": importlib.metadata.version("JPype1"), "openai": importlib.metadata.version("openai"),
    }
    for key, value in actual.items():
        if str(config["runtime"][key]) != value:
            raise RuntimeError(f"V3-D runtime drift: {key}={value}")


def _inventory_file(row: Mapping[str, Any], suffix: str) -> Path:
    matches = [item for item in row["artifacts"] if str(item["path"]).endswith(suffix)]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one inventory artifact ending {suffix}")
    path = ROOT / matches[0]["path"]
    if _hash(path) != str(matches[0]["sha256"]).upper():
        raise RuntimeError(f"Validation raw artifact hash drift: {path.relative_to(ROOT)}")
    return path


def _scene(row: Mapping[str, Any], variants: list[str]) -> dict[str, Any]:
    scm_path = _inventory_file(row, "/scm.json")
    values_path = _inventory_file(row, "/observations_standardized_n2000.npy")
    alias_path = _inventory_file(row, "/alias_map.json")
    scm = _json(scm_path)
    alias = _json(alias_path)
    stories = {}
    story_paths = {}
    for variant in variants:
        path = _inventory_file(row, f"/story_{variant}.json")
        stories[variant] = _json(path)
        story_paths[variant] = path
    if any(value["study_id"] != row["study_id"] for value in [scm, alias, *stories.values()]):
        raise RuntimeError("Validation scene identity mismatch")
    return {
        "scm": scm,
        "values": np.load(values_path, allow_pickle=False),
        "values_hash": _hash(values_path),
        "alias_by_node": {item["canonical_id"]: item["public_alias"] for item in alias["mapping"]},
        "alias_hash": _hash(alias_path), "stories": stories,
        "story_hashes": {variant: _hash(path) for variant, path in story_paths.items()},
    }


def _load_cache(path: Path) -> dict[tuple[str, int], dict[str, Any]]:
    if not path.is_file():
        return {}
    cache = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        row = json.loads(line)
        key = (str(row["call_id"]), int(row["attempt"]))
        if key in cache:
            raise RuntimeError(f"Duplicate raw cache key at line {number}")
        if sha256_hex(str(row["prompt"]).encode()) != row["prompt_sha256"]:
            raise RuntimeError(f"Prompt hash mismatch at cache line {number}")
        if sha256_hex(str(row["raw_text"]).encode()) != row["raw_sha256"]:
            raise RuntimeError(f"Response hash mismatch at cache line {number}")
        cache[key] = row
    return cache


def _append(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(canonical_json_bytes(row, newline=True))
        handle.flush()


def _retry_prompt(base: str, raw: str, error: str) -> str:
    return base + "\n\nVALIDATION RETRY:\nReturn a complete replacement JSON object using only the same public story. Do not discuss the error.\nVALIDATOR ERROR: " + error + "\nPREVIOUS RESPONSE:\n" + raw


class CallBudget:
    def __init__(self, maximum: int, minimum_interval: float) -> None:
        self.maximum = maximum
        self.minimum_interval = minimum_interval
        self.calls = 0
        self.last_finished: float | None = None

    def before(self) -> None:
        if self.calls >= self.maximum:
            raise RuntimeError("T21 v3-D API attempt cap reached")
        if self.last_finished is not None:
            remaining = self.minimum_interval - (time.monotonic() - self.last_finished)
            if remaining > 0:
                time.sleep(remaining)
        self.calls += 1

    def after(self) -> None:
        self.last_finished = time.monotonic()


def _call(
    *, call_id: str, prompt: str, parser: Callable[[str], Any], backend: T21OpenAIBackend | None,
    raw_path: Path, cache: dict[tuple[str, int], dict[str, Any]], budget: CallBudget, retries: int,
) -> tuple[Any, list[dict[str, Any]]]:
    current = prompt
    attempts = []
    for attempt in range(retries + 1):
        key = (call_id, attempt)
        prompt_hash = sha256_hex(current.encode())
        if key in cache:
            raw = cache[key]
            if raw["prompt_sha256"] != prompt_hash:
                raise RuntimeError(f"Cached prompt drift: {key}")
        else:
            if backend is None:
                raise RuntimeError(f"Replay cache missing: {key}")
            budget.before()
            try:
                raw = backend.call(call_id=call_id, prompt=current, attempt=attempt)
            finally:
                budget.after()
            raw["prompt_sha256"] = prompt_hash
            raw["raw_sha256"] = sha256_hex(raw["raw_text"].encode())
            _append(raw_path, raw)
            cache[key] = raw
        error = None
        try:
            parsed = parser(raw["raw_text"])
        except (json.JSONDecodeError, ValueError) as exc:
            error = str(exc)
        attempts.append({
            "attempt": attempt, "prompt_sha256": prompt_hash, "raw_sha256": raw["raw_sha256"],
            "request_id": raw.get("request_id"), "model_snapshot": raw["model_snapshot"],
            "input_tokens": raw.get("input_tokens"), "cached_input_tokens": raw.get("cached_input_tokens"),
            "output_tokens": raw.get("output_tokens"), "reasoning_tokens": raw.get("reasoning_tokens"),
            "latency_ms": raw.get("latency_ms"), "validation_error": error,
        })
        if error is None:
            return parsed, attempts
        current = _retry_prompt(prompt, raw["raw_text"], error)
    raise RuntimeError(f"Terminal semantic validation failure: {call_id}")


def _select(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    eligible = [row for row in rows if row["eligible"]]
    if not eligible:
        return None
    return min(eligible, key=lambda row: (
        -float(row["orientation_coverage"]), -float(row["orientation_precision"]),
        int(row["oriented_false_adjacencies"]), -float(row["tau_global"]), -float(row["tau_semantic"]),
    ))


def run(config_path: Path, *, execute: bool, check: bool, call_limit: int | None) -> dict[str, Any]:
    config_path = (ROOT / config_path).resolve()
    config = _yaml(config_path)
    study_ids, inventory = _validate(config, config_path)
    _runtime(config)
    config_hash = _hash(config_path)
    raw_path = ROOT / config["outputs"]["raw_calls"]
    cache = _load_cache(raw_path)
    cap = int(config["execution"]["maximum_new_api_attempts"])
    if call_limit is not None:
        if not 0 <= call_limit <= cap:
            raise ValueError("call-limit outside frozen cap")
        cap = call_limit
    budget = CallBudget(cap, float(config["execution"]["minimum_seconds_between_requests"]))
    template = (ROOT / config["semantic_backend"]["preference_prompt"]).read_text(encoding="utf-8")
    schema = _json(ROOT / config["semantic_backend"]["preference_schema"])
    backend = None
    if execute:
        load_dotenv(ROOT / ".env", override=True)
        key = os.environ.get(config["semantic_backend"]["credential_env"], "")
        backend = T21OpenAIBackend(
            api_key=key, response_schema=schema, schema_name="p1_semantic_preferences_v1",
            model_snapshot=config["semantic_backend"]["model_snapshot"],
            max_output_tokens=config["semantic_backend"]["max_output_tokens"],
            timeout_seconds=config["semantic_backend"]["timeout_seconds"],
            transport_max_retries=config["semantic_backend"]["transport_max_retries"],
        )
        if backend.sdk_version != config["semantic_backend"]["sdk_version"]:
            raise RuntimeError("OpenAI SDK drift")

    bundled_java_home = Path(sys.prefix) / "Library" / "lib" / "jvm"
    if "JAVA_HOME" not in os.environ and bundled_java_home.is_dir():
        os.environ["JAVA_HOME"] = str(bundled_java_home)
    tetrad = TetradBackend(ROOT / config["scd"]["tetrad_jar"], config["scd"]["tetrad_jar_sha256"])
    policy = SCDGraphPolicy(
        candidate_id=config["scd"]["candidate_id"], family="boss_basis_bic",
        penalty_discount=config["scd"]["penalty_discount"], truncation_limit=config["scd"]["truncation_limit"], seed=None,
    )
    variants = list(config["semantic_backend"]["variants"])
    preferences = []
    boss_rows = []
    scenes = {}
    rendered_token_estimate = 0
    for study_id in study_ids:
        if study_id.startswith("P1S"):
            raise RuntimeError("V3-D attempted existing P1 cohort access")
        scene = _scene(inventory[study_id], variants)
        scm = scene["scm"]
        nodes = tuple(row["canonical_id"] for row in scm["variable_mapping"])
        if scene["values"].shape != (2000, len(nodes)):
            raise RuntimeError(f"Validation observation shape drift: {study_id}")
        scene_data = SceneData(scm["scene_id"], nodes, tuple(False for _ in nodes), scene["values"])
        scd = build_scd_graphs(scene_data, backend=tetrad, policy=policy, config_sha256=config_hash, input_artifact_sha256=[scene["values_hash"]])
        parent = scd.raw_cpdag.partial_graph
        oracle = _graph(scm["oracle_dag"])
        boss_rows.append({
            "schema_version": "fourgraph.t21_v3d_boss_graph.v1", "study_id": study_id,
            "scene_id": scm["scene_id"], "condition": "G_SCD_RAW", "artifact": scd.raw_cpdag.to_dict(),
            "oracle_not_persisted": True,
        })
        scene_preferences = {}
        for variant in variants:
            story = public_builder_view(scene["stories"][variant])["story"]
            prompt = render_preference_prompt(story, scene["alias_by_node"], parent, template)
            rendered_token_estimate += len(prompt.encode()) // 4 + 1
            call_id = f"{scm['scene_id']}:preferences:{variant}"
            if execute or (call_id, 0) in cache:
                (artifact, evidence), attempts = _call(
                    call_id=call_id, prompt=prompt,
                    parser=lambda raw, mapping=scene["alias_by_node"], graph=parent: parse_preference_response(raw, mapping, graph),
                    backend=backend, raw_path=raw_path, cache=cache, budget=budget,
                    retries=int(config["execution"]["validation_retries"]),
                )
                scene_preferences[variant] = artifact
                preferences.append({
                    "schema_version": "fourgraph.t21_v3d_preference_record.v1", "study_id": study_id,
                    "scene_id": scm["scene_id"], "story_variant": variant,
                    "parent_graph_sha256": scd.raw_cpdag.graph_sha256,
                    "story_sha256": scene["story_hashes"][variant], "alias_map_sha256": scene["alias_hash"],
                    "preference_artifact": artifact, "preference_artifact_sha256": sha256_hex(canonical_json_bytes(artifact)),
                    "evidence": list(evidence), "attempts": attempts,
                })
        if len(scene_preferences) == 3:
            scenes[study_id] = {
                "scene_id": scm["scene_id"], "parent": parent, "oracle": oracle,
                "preferences": scene_preferences,
                "prepared": {
                    variant: prepare_edge_selective(parent, scene_preferences[variant])
                    for variant in variants
                },
            }

    logical_ids = [f"scene_{110000+i:06d}:preferences:{variant}" for i in range(20) for variant in variants]
    cached_logical = sum((call_id, 0) in cache for call_id in logical_ids)
    preflight = {
        "validation_scenes": 20, "planned_logical_calls": 60, "cached_logical_calls": cached_logical,
        "planned_new_logical_calls": 60 - cached_logical,
        "rendered_prompt_token_upper_estimate": rendered_token_estimate,
        "existing_development_accessed": False, "final_holdout_accessed": False,
    }
    if not execute and not check and cached_logical < 60:
        return {"mode": "preflight", **preflight, "api_calls": 0, "boss_scenes": len(boss_rows)}
    if len(scenes) != 20 or len(preferences) != 60:
        raise RuntimeError("T21 v3-D semantic execution incomplete")

    grid = []
    all_results: dict[tuple[float, float, str, str], dict[str, Any]] = {}
    for tau_semantic in config["edge_selective"]["threshold_grid"]["semantic_confidence"]:
        for tau_global in config["edge_selective"]["threshold_grid"]["global_stability"]:
            answered = correct = denominator = false_oriented = valid = 0
            direct_answered = direct_correct = closure_answered = closure_correct = 0
            for study_id, scene in scenes.items():
                for variant in variants:
                    result = solve_prepared_edge_selective(
                        scene["prepared"][variant],
                        tau_semantic=float(tau_semantic), tau_global=float(tau_global),
                    )
                    metrics = score_edge_selective(scene["parent"], result, scene["oracle"])
                    all_results[(float(tau_semantic), float(tau_global), study_id, variant)] = result
                    valid += int(metrics["graph_valid"])
                    answered += metrics["answered_edges"]
                    correct += metrics["correct_answered_edges"]
                    denominator += len(scene["parent"].undirected)
                    direct_answered += metrics["direct_semantic_answered"]
                    direct_correct += metrics["direct_semantic_correct"]
                    closure_answered += metrics["closure_answered"]
                    closure_correct += metrics["closure_correct"]
                    false_oriented += sum(
                        row["direction_source"] in {"semantic_selected", "closure_propagated"}
                        and (row["left"], row["right"]) not in scene["oracle"].skeleton
                        for row in result["edge_provenance"]
                    )
            precision = correct / answered if answered else 0.0
            coverage = answered / denominator if denominator else 0.0
            validity = valid / 60
            eligible = (
                validity == 1.0
                and precision >= float(config["edge_selective"]["orientation_precision_minimum"])
                and answered >= int(config["edge_selective"]["minimum_answered_edges"])
                and coverage >= float(config["edge_selective"]["minimum_orientation_coverage"])
            )
            grid.append({
                "schema_version": "fourgraph.t21_v3d_threshold_candidate.v1",
                "tau_semantic": float(tau_semantic), "tau_global": float(tau_global),
                "graph_validity": validity, "orientation_correct": correct,
                "answered_edges": answered, "orientation_denominator": denominator,
                "orientation_precision": round(precision, 10), "orientation_coverage": round(coverage, 10),
                "abstention_rate": round(1.0 - coverage, 10),
                "oriented_false_adjacencies": false_oriented,
                "direct_semantic_answered": direct_answered, "direct_semantic_correct": direct_correct,
                "closure_answered": closure_answered, "closure_correct": closure_correct,
                "eligible": eligible, "uses_downstream_tasks_or_answers": False,
                "uses_existing_development": False, "uses_final_holdout": False,
            })
    grid.sort(key=lambda row: (row["tau_semantic"], row["tau_global"]))
    selected = _select(grid)
    selected_rows = []
    if selected is not None:
        key_prefix = (selected["tau_semantic"], selected["tau_global"])
        for study_id in study_ids:
            for variant in variants:
                result = all_results[(*key_prefix, study_id, variant)]
                selected_rows.append({
                    "schema_version": "fourgraph.t21_v3d_selected_graph.v1",
                    "study_id": study_id, "scene_id": scenes[study_id]["scene_id"], "story_variant": variant,
                    "tau_semantic": key_prefix[0], "tau_global": key_prefix[1], "decision": result,
                })

    preferences.sort(key=lambda row: (row["study_id"], variants.index(row["story_variant"])))
    boss_rows.sort(key=lambda row: row["study_id"])
    outputs = {
        config["outputs"]["semantic_preferences"]: _jsonl_bytes(preferences),
        config["outputs"]["boss_graphs"]: _jsonl_bytes(boss_rows),
        config["outputs"]["threshold_grid"]: _jsonl_bytes(grid),
        config["outputs"]["selected_graphs"]: _jsonl_bytes(selected_rows),
    }
    tokens = {key: 0 for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens")}
    for row in cache.values():
        if str(row["call_id"]).startswith("scene_110"):
            for key in tokens:
                tokens[key] += int(row.get(key) or 0)
    best = min(grid, key=lambda row: (-row["orientation_precision"], -row["orientation_coverage"], row["oriented_false_adjacencies"], -row["tau_global"], -row["tau_semantic"]))
    output_entries = [{"path": path, "bytes": len(payload), "sha256": sha256_hex(payload)} for path, payload in outputs.items()]
    audit = {
        "schema_version": "fourgraph.t21_v3d_validation_audit.v2", "task": "T21 Amendment v3-D",
        "experiment_id": config["experiment_id"],
        "counts": {
            "validation_scenes": 20, "boss_graphs": len(boss_rows), "semantic_preference_artifacts": len(preferences),
            "threshold_candidates": len(grid), "selected_graphs": len(selected_rows),
            "api_attempts_captured": len(cache),
            "validation_retry_responses": sum(int(key[1] > 0) for key in cache),
        },
        "preflight": preflight, "selected_threshold": selected,
        "best_candidate_by_precision_then_coverage": best,
        "threshold_selection_status": "selected" if selected else "no_eligible_candidate",
        "token_usage": tokens, "outputs": output_entries,
        "dependencies": [{"path": key, "sha256": value} for key, value in config["freeze_anchors"].items()],
        "implementation_dependencies": [
            {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": _hash(path)}
            for path in (config_path, ROOT / "src/fourgraph/edge_selective.py", ROOT / "scripts/run_t21_v3d_validation.py")
        ],
        "live_execution_freeze": {
            "preflight_manifest": config["scope"]["preflight_freeze"],
            "live_runner_sha256": _json(ROOT / config["scope"]["preflight_freeze"])["runner_sha256"],
            "replay_amendment": "removed_run_local_new_api_calls_last_resume_from_canonical_audit",
            "scientific_inputs_prompts_responses_scoring_changed": False,
        },
        "evidence_boundary": {
            "validation_only": True, "validation_tasks_or_answers_accessed": False,
            "existing_development_accessed": False, "final_holdout_accessed": False,
            "reasoner_executed": False, "downstream_ranking_used_for_selection": False,
        },
        "verdict": {
            "t21_v3d_complete": True, "threshold_selected": selected is not None,
            "validation_gate_passed": selected is not None,
            "t21_v3e_holdout_freeze_decision_authorized": True,
            "t22_final_holdout_freeze_authorized": selected is not None,
            "final_holdout_execution_authorized": False,
        },
    }
    audit_bytes = canonical_json_bytes(audit, newline=True)
    if selected:
        result_text = (
            f"Selected tau_semantic={selected['tau_semantic']} and tau_global={selected['tau_global']}: "
            f"precision {selected['orientation_precision']}, answered {selected['answered_edges']}, "
            f"coverage {selected['orientation_coverage']}."
        )
    else:
        result_text = (
            f"No candidate met all frozen gates. Best precision-first candidate: tau_semantic={best['tau_semantic']}, "
            f"tau_global={best['tau_global']}, precision {best['orientation_precision']}, "
            f"answered {best['answered_edges']}, coverage {best['orientation_coverage']}."
        )
    report = (
        "# T21 v3-D — Edge-Selective validation gate\n\n"
        "V3-D ran BOSS and the frozen semantic preference model only on the 20-scene validation cohort.\n\n"
        + result_text + "\n\n"
        + f"Captured {len(preferences)} semantic artifacts in {len(cache)} API attempts. Token usage: "
        + f"{tokens['input_tokens']} input, {tokens['output_tokens']} output, {tokens['reasoning_tokens']} reasoning.\n\n"
        "No downstream task/answer, existing development result or final holdout artifact was accessed. Final holdout execution remains unauthorized.\n"
    ).encode("utf-8")
    outputs[config["outputs"]["audit"]] = audit_bytes
    outputs[config["outputs"]["report"]] = report
    if check:
        for relative, payload in outputs.items():
            path = ROOT / relative
            if not path.is_file() or path.read_bytes() != payload:
                raise RuntimeError(f"T21 v3-D byte replay mismatch: {relative}")
    else:
        for relative, payload in outputs.items():
            path = ROOT / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    return {
        "mode": "check" if check else "execute", **preflight,
        "new_api_calls": budget.calls, "boss_graphs": len(boss_rows),
        "semantic_preferences": len(preferences), "threshold_candidates": len(grid),
        "selected_threshold": None if selected is None else {
            key: selected[key] for key in ("tau_semantic", "tau_global", "orientation_precision", "answered_edges", "orientation_coverage")
        },
        "validation_gate_passed": selected is not None, "final_holdout_accessed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--call-limit", type=int)
    args = parser.parse_args()
    result = run(args.config, execute=args.execute, check=args.check, call_limit=args.call_limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
