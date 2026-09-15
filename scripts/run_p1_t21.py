"""Run, resume, or replay the frozen development-only P1 T21 execution."""

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
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fourgraph.causalds_scd import SceneData, TetradBackend, file_sha256  # noqa: E402
from fourgraph.graph_adapters import make_oracle_graph_artifact  # noqa: E402
from fourgraph.graph_contract import EdgeAuditRecord, GraphArtifact, canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.graph_metrics import evaluate_graph  # noqa: E402
from fourgraph.hybrid_h2 import solve_h2_forced, solve_h2_selective  # noqa: E402
from fourgraph.p1_stories import public_builder_view  # noqa: E402
from fourgraph.p1_t21 import (  # noqa: E402
    content_sha256,
    direct_lingam_graph,
    h1_local_orientation,
    make_direct_lingam_artifact,
    make_semantic_graph_artifact,
    orientation_counts,
    parse_llm_graph_response,
    parse_preference_response,
    render_llm_graph_prompt,
    render_preference_prompt,
    select_threshold,
)
from fourgraph.partial_graph import PartialGraph  # noqa: E402
from fourgraph.scd_graph import SCDGraphPolicy, build_scd_graphs  # noqa: E402
from fourgraph.t21_openai_backend import T21OpenAIBackend  # noqa: E402


DEFAULT_CONFIG = Path("configs/t21_p1_development.yaml")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML object: {path}")
    return value


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row, newline=True) for row in rows)


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def validate_config(config: Mapping[str, Any]) -> tuple[list[str], set[str]]:
    if config["task"] != "T21" or config["scope"]["role"] != "development":
        raise ValueError("T21 must be development-only")
    if config["scope"]["forbid_holdout_access"] is not True:
        raise ValueError("T21 holdout guard is disabled")
    boundary = config["evidence_boundary"]
    if boundary["P1_holdout_access_authorized"] is not False:
        raise ValueError("T21 cannot authorize holdout")
    if boundary["development_tasks_or_answers_allowed_for_threshold"] is not False:
        raise ValueError("Threshold selection cannot use downstream answers")
    if config["execution"]["maximum_new_api_calls"] != 80:
        raise ValueError("T21 live call cap changed")
    for relative, expected in config["freeze_anchors"].items():
        if hash_file(ROOT / relative) != expected:
            raise RuntimeError(f"Frozen dependency changed: {relative}")
    t20 = read_json(ROOT / "data/manifests/t20_h2_conformance_audit.json")
    if t20["verdict"]["t21_development_only_execution_authorized"] is not True:
        raise RuntimeError("T20 does not authorize T21")
    split = read_json(ROOT / config["scope"]["split_manifest"])
    dev = list(map(str, split["development_ids"]))
    holdout = set(map(str, split["holdout_ids"]))
    if len(dev) != 20 or len(holdout) != 80 or set(dev) & holdout:
        raise RuntimeError("Frozen P1 split is invalid")
    return dev, holdout


def validate_runtime(config: Mapping[str, Any]) -> None:
    names = {
        "python": platform.python_version(),
        "numpy": importlib.metadata.version("numpy"),
        "jpype": importlib.metadata.version("JPype1"),
        "openai": importlib.metadata.version("openai"),
        "lingam": importlib.metadata.version("lingam"),
        "scipy": importlib.metadata.version("scipy"),
        "scikit_learn": importlib.metadata.version("scikit-learn"),
    }
    for key, actual in names.items():
        if str(config["runtime"][key]) != actual:
            raise RuntimeError(f"T21 runtime drift: {key}={actual}, expected={config['runtime'][key]}")


def load_scene(config: Mapping[str, Any], study_id: str) -> dict[str, Any]:
    base = ROOT / config["scope"]["generated_root"]
    t18 = base / "t18" / study_id
    t19 = base / "t19" / study_id
    scm = read_json(t18 / "scm.json")
    alias_record = read_json(t19 / "alias_map.json")
    if scm["study_id"] != study_id or alias_record["study_id"] != study_id:
        raise RuntimeError("Scene identity mismatch")
    stories = {
        variant: read_json(t19 / f"story_{variant}.json")
        for variant in config["hybrid"]["preference_variants"]
    }
    if any(record["study_id"] != study_id for record in stories.values()):
        raise RuntimeError("Story identity mismatch")
    return {
        "scm": scm,
        "alias_by_node": {row["canonical_id"]: row["public_alias"] for row in alias_record["mapping"]},
        "alias_hash": hash_file(t19 / "alias_map.json"),
        "stories": stories,
        "story_hashes": {variant: hash_file(t19 / f"story_{variant}.json") for variant in stories},
        "values": np.load(t18 / config["scd"]["standardized_observations"], allow_pickle=False),
        "values_hash": hash_file(t18 / config["scd"]["standardized_observations"]),
        "scm_hash": hash_file(t18 / "scm.json"),
    }


def load_raw_cache(path: Path) -> dict[tuple[str, int], dict[str, Any]]:
    if not path.exists():
        return {}
    cache: dict[tuple[str, int], dict[str, Any]] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        row = json.loads(line)
        key = (str(row["call_id"]), int(row["attempt"]))
        if key in cache:
            raise RuntimeError(f"Duplicate raw cache key at line {number}")
        if sha256_hex(str(row["prompt"]).encode("utf-8")) != row["prompt_sha256"]:
            raise RuntimeError(f"Raw cache prompt hash mismatch at line {number}")
        if sha256_hex(str(row["raw_text"]).encode("utf-8")) != row["raw_sha256"]:
            raise RuntimeError(f"Raw cache response hash mismatch at line {number}")
        cache[key] = row
    return cache


def append_raw(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(canonical_json_bytes(row, newline=True))
        handle.flush()


def retry_prompt(base: str, raw: str, error: str) -> str:
    return (
        base
        + "\n\nVALIDATION RETRY:\nReturn a complete replacement JSON object using only the same public story. "
        + "Do not discuss the error.\nVALIDATOR ERROR: "
        + error
        + "\nPREVIOUS RESPONSE:\n"
        + raw
    )


class LiveCounter:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.calls = 0

    def take(self) -> None:
        if self.calls >= self.maximum:
            raise RuntimeError("T21 maximum-new-call cap reached")
        self.calls += 1


def validated_call(
    *,
    call_id: str,
    base_prompt: str,
    parser: Callable[[str], Any],
    backend: T21OpenAIBackend | None,
    raw_path: Path,
    cache: dict[tuple[str, int], dict[str, Any]],
    counter: LiveCounter,
    max_validation_retries: int,
) -> tuple[Any, list[dict[str, Any]]]:
    prompt = base_prompt
    attempts: list[dict[str, Any]] = []
    for attempt in range(max_validation_retries + 1):
        key = (call_id, attempt)
        prompt_hash = sha256_hex(prompt.encode("utf-8"))
        if key in cache:
            raw = cache[key]
            if raw["prompt_sha256"] != prompt_hash:
                raise RuntimeError(f"Replay prompt mismatch: {key}")
        else:
            if backend is None:
                raise RuntimeError(f"Replay cache missing call: {key}")
            counter.take()
            raw = backend.call(call_id=call_id, prompt=prompt, attempt=attempt)
            raw["prompt_sha256"] = prompt_hash
            raw["raw_sha256"] = sha256_hex(raw["raw_text"].encode("utf-8"))
            append_raw(raw_path, raw)
            cache[key] = raw
        error = None
        try:
            parsed = parser(raw["raw_text"])
        except (json.JSONDecodeError, ValueError) as exc:
            error = str(exc)
        attempts.append(
            {
                "attempt": attempt,
                "prompt_sha256": prompt_hash,
                "raw_sha256": raw["raw_sha256"],
                "request_id": raw.get("request_id"),
                "model_snapshot": raw["model_snapshot"],
                "input_tokens": raw.get("input_tokens"),
                "cached_input_tokens": raw.get("cached_input_tokens"),
                "output_tokens": raw.get("output_tokens"),
                "reasoning_tokens": raw.get("reasoning_tokens"),
                "latency_ms": raw.get("latency_ms"),
                "validation_error": error,
            }
        )
        if error is None:
            return parsed, attempts
        prompt = retry_prompt(base_prompt, raw["raw_text"], error)
    raise RuntimeError(f"Terminal validation failure: {call_id}: {attempts[-1]['validation_error']}")


def edge_audit(graph: PartialGraph, *, actor: str, reason: str) -> tuple[EdgeAuditRecord, ...]:
    return tuple(
        EdgeAuditRecord.build(
            step=i,
            source=a,
            target=b,
            action="add",
            before_mark="absent",
            after_mark="directed",
            actor=actor,
            reason=reason,
            arbitrary=False,
        )
        for i, (a, b) in enumerate(sorted(graph.directed))
    )


def orientation_edge_audit(
    parent: PartialGraph, graph: PartialGraph, *, reason: str
) -> tuple[EdgeAuditRecord, ...]:
    records = []
    for step, (left, right) in enumerate(sorted(parent.undirected)):
        source, target = (left, right) if (left, right) in graph.directed else (right, left)
        records.append(
            EdgeAuditRecord.build(
                step=step,
                source=source,
                target=target,
                action="orient",
                before_mark="undirected",
                after_mark="directed",
                actor="hybrid",
                reason=reason,
                arbitrary=False,
            )
        )
    return tuple(records)


def graph_from_dict(value: Mapping[str, Any]) -> PartialGraph:
    return PartialGraph.build(value["nodes"], value.get("directed", []), value.get("undirected", []))


def artifact_record(condition: str, study_id: str, variant: str | None, artifact: GraphArtifact | None, error: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": "fourgraph.p1_t21_graph_record.v1",
        "study_id": study_id,
        "scene_id": artifact.scene_id if artifact else None,
        "condition": condition,
        "story_variant": variant,
        "status": "success" if artifact else "terminal_graph_failure",
        "error": error,
        "artifact": artifact.to_dict() if artifact else None,
    }


def run(config_path: Path, *, execute: bool, check: bool, call_limit: int | None) -> dict[str, Any]:
    config_path = (ROOT / config_path).resolve()
    config = read_yaml(config_path)
    dev_ids, holdout_ids = validate_config(config)
    validate_runtime(config)
    config_hash = hash_file(config_path)
    raw_path = ROOT / config["outputs"]["raw_calls"]
    cache = load_raw_cache(raw_path)
    call_cap = config["execution"]["maximum_new_api_calls"]
    if call_limit is not None:
        if call_limit < 0 or call_limit > call_cap:
            raise ValueError("call-limit outside frozen cap")
        call_cap = call_limit
    counter = LiveCounter(call_cap)

    pref_template = (ROOT / config["semantic_backend"]["preference_prompt"]).read_text(encoding="utf-8")
    graph_template = (ROOT / config["semantic_backend"]["llm_graph_prompt"]).read_text(encoding="utf-8")
    pref_schema = read_json(ROOT / config["semantic_backend"]["preference_schema"])
    graph_schema = read_json(ROOT / config["semantic_backend"]["llm_graph_schema"])
    backend_pref = backend_graph = None
    if execute:
        load_dotenv(ROOT / ".env", override=True)
        key = os.environ.get(config["semantic_backend"]["credential_env"], "")
        common = {
            "api_key": key,
            "model_snapshot": config["semantic_backend"]["model_snapshot"],
            "max_output_tokens": config["semantic_backend"]["max_output_tokens"],
            "timeout_seconds": config["semantic_backend"]["timeout_seconds"],
            "transport_max_retries": config["semantic_backend"]["transport_max_retries"],
        }
        backend_pref = T21OpenAIBackend(response_schema=pref_schema, schema_name="p1_semantic_preferences_v1", **common)
        backend_graph = T21OpenAIBackend(response_schema=graph_schema, schema_name="p1_llm_graph_v1", **common)
        if backend_pref.sdk_version != config["semantic_backend"]["sdk_version"]:
            raise RuntimeError("OpenAI SDK drift")

    bundled_java_home = Path(sys.prefix) / "Library" / "lib" / "jvm"
    if "JAVA_HOME" not in os.environ and bundled_java_home.is_dir():
        os.environ["JAVA_HOME"] = str(bundled_java_home)
    backend_scd = TetradBackend(ROOT / config["scd"]["tetrad_jar"], config["scd"]["tetrad_jar_sha256"])
    scd_policy = SCDGraphPolicy(
        candidate_id=config["scd"]["candidate_id"],
        family="boss_basis_bic",
        penalty_discount=config["scd"]["penalty_discount"],
        truncation_limit=config["scd"]["truncation_limit"],
        seed=None,
    )
    pref_rows: list[dict[str, Any]] = []
    base_graph_rows: list[dict[str, Any]] = []
    scene_objects: dict[str, dict[str, Any]] = {}
    rendered_input_tokens = 0
    for study_id in dev_ids:
        if study_id in holdout_ids:
            raise RuntimeError("T21 attempted holdout access")
        scene = load_scene(config, study_id)
        scm = scene["scm"]
        scene_id = str(scm["scene_id"])
        nodes = tuple(row["canonical_id"] for row in scm["variable_mapping"])
        values = scene["values"]
        if values.shape != (2000, len(nodes)):
            raise RuntimeError(f"Unexpected development observation shape: {study_id}")
        scene_data = SceneData(scene_id, nodes, tuple(False for _ in nodes), values)
        scd = build_scd_graphs(
            scene_data,
            backend=backend_scd,
            policy=scd_policy,
            config_sha256=config_hash,
            input_artifact_sha256=[scene["values_hash"]],
        )
        direct_graph, direct_matrix = direct_lingam_graph(
            values,
            nodes,
            random_state=config["direct_lingam"]["random_state"],
            zero_tolerance=float(config["direct_lingam"]["adjacency_zero_tolerance"]),
        )
        direct = make_direct_lingam_artifact(
            scene_id=scene_id,
            graph=direct_graph,
            config_sha256=config_hash,
            input_sha256=scene["values_hash"],
            seed=config["direct_lingam"]["random_state"],
        )
        oracle_graph = graph_from_dict(scm["oracle_dag"])
        oracle = make_oracle_graph_artifact(
            scene_id=scene_id,
            graph=oracle_graph,
            builder_id="fourgraph.p1_t21_development_oracle",
            builder_version="v1",
            config_sha256=config_hash,
            input_artifact_sha256=[scene["scm_hash"]],
        )
        base_graph_rows.extend(
            [
                artifact_record("G_SCD_RAW", study_id, None, scd.raw_cpdag),
                artifact_record("G_SCD_PROJECTED", study_id, None, scd.projected_dag),
                artifact_record("G_DIRECTLINGAM", study_id, None, direct),
            ]
        )
        full_story = public_builder_view(scene["stories"]["full"])["story"]
        llm_prompt = render_llm_graph_prompt(full_story, scene["alias_by_node"].values(), graph_template)
        rendered_input_tokens += len(llm_prompt.encode("utf-8")) // 4 + 1
        if execute or (f"{scene_id}:llm_graph:full", 0) in cache:
            (llm_graph, llm_decisions), llm_attempts = validated_call(
                call_id=f"{scene_id}:llm_graph:full",
                base_prompt=llm_prompt,
                parser=lambda raw, mapping=scene["alias_by_node"]: parse_llm_graph_response(raw, mapping),
                backend=backend_graph,
                raw_path=raw_path,
                cache=cache,
                counter=counter,
                max_validation_retries=config["execution"]["validation_retries"],
            )
            llm = make_semantic_graph_artifact(
                scene_id=scene_id,
                parent=None,
                graph=llm_graph,
                graph_method="llm",
                graph_type="dag",
                graph_view="dag",
                builder_id="fourgraph.p1_t21_llm_full",
                config_sha256=config_hash,
                input_hashes=[scene["story_hashes"]["full"], scene["alias_hash"]],
                edge_audit=edge_audit(llm_graph, actor="llm", reason="public_full_story_direct_relation"),
            )
            base_graph_rows.append(artifact_record("G_LLM_FULL", study_id, "full", llm))
        else:
            llm = None
            llm_attempts = []

        preferences: dict[str, dict[str, Any]] = {}
        forced: dict[str, dict[str, Any]] = {}
        for variant in config["hybrid"]["preference_variants"]:
            story = public_builder_view(scene["stories"][variant])["story"]
            prompt = render_preference_prompt(story, scene["alias_by_node"], scd.raw_cpdag.partial_graph, pref_template)
            rendered_input_tokens += len(prompt.encode("utf-8")) // 4 + 1
            call_id = f"{scene_id}:preferences:{variant}"
            if execute or (call_id, 0) in cache:
                (artifact, evidence), attempts = validated_call(
                    call_id=call_id,
                    base_prompt=prompt,
                    parser=lambda raw, mapping=scene["alias_by_node"], parent=scd.raw_cpdag.partial_graph: parse_preference_response(raw, mapping, parent),
                    backend=backend_pref,
                    raw_path=raw_path,
                    cache=cache,
                    counter=counter,
                    max_validation_retries=config["execution"]["validation_retries"],
                )
                preferences[variant] = artifact
                forced[variant] = solve_h2_forced(scd.raw_cpdag.partial_graph, artifact)
                pref_rows.append(
                    {
                        "schema_version": "fourgraph.p1_t21_preference_record.v1",
                        "study_id": study_id,
                        "scene_id": scene_id,
                        "story_variant": variant,
                        "parent_graph_sha256": scd.raw_cpdag.graph_sha256,
                        "story_sha256": scene["story_hashes"][variant],
                        "alias_map_sha256": scene["alias_hash"],
                        "preference_artifact": artifact,
                        "preference_artifact_sha256": content_sha256(artifact),
                        "evidence": list(evidence),
                        "attempts": attempts,
                    }
                )
        if execute or all((f"{scene_id}:preferences:{v}", 0) in cache for v in config["hybrid"]["preference_variants"]):
            h1_artifact = None
            h1_error = None
            try:
                h1_graph = h1_local_orientation(scd.raw_cpdag.partial_graph, preferences["full"])
                h1_artifact = make_semantic_graph_artifact(
                    scene_id=scene_id,
                    parent=scd.raw_cpdag,
                    graph=h1_graph,
                    graph_method="hybrid",
                    graph_type="dag",
                    graph_view="dag",
                    builder_id="fourgraph.p1_t21_h1",
                    config_sha256=config_hash,
                    input_hashes=[content_sha256(preferences["full"]), scd.raw_cpdag.artifact_sha256],
                    edge_audit=orientation_edge_audit(scd.raw_cpdag.partial_graph, h1_graph, reason="independent_semantic_argmax"),
                )
            except ValueError as exc:
                h1_error = str(exc)
            base_graph_rows.append(artifact_record("G_HYBRID_H1_FULL", study_id, "full", h1_artifact, h1_error))
            forced_artifacts: dict[str, GraphArtifact] = {}
            for variant, decision in forced.items():
                forced_graph = graph_from_dict(decision["selected_graph"])
                forced_artifacts[variant] = make_semantic_graph_artifact(
                    scene_id=scene_id,
                    parent=scd.raw_cpdag,
                    graph=forced_graph,
                    graph_method="hybrid",
                    graph_type="dag",
                    graph_view="dag",
                    builder_id="fourgraph.p1_t21_h2_forced",
                    config_sha256=config_hash,
                    input_hashes=[content_sha256(preferences[variant]), scd.raw_cpdag.artifact_sha256],
                    edge_audit=orientation_edge_audit(scd.raw_cpdag.partial_graph, forced_graph, reason="global_semantic_extension_optimum"),
                )
                base_graph_rows.append(artifact_record(f"G_HYBRID_H2_FORCED_{variant.upper()}", study_id, variant, forced_artifacts[variant]))
            scene_objects[study_id] = {
                "scene_id": scene_id,
                "raw": scd.raw_cpdag,
                "projected": scd.projected_dag,
                "direct": direct,
                "oracle": oracle,
                "llm": llm,
                "h1": h1_artifact,
                "preferences": preferences,
                "forced": forced,
                "forced_artifacts": forced_artifacts,
                "alias_hash": scene["alias_hash"],
                "direct_matrix_sha256": sha256_hex(np.ascontiguousarray(direct_matrix).tobytes()),
                "llm_attempts": llm_attempts,
            }

    planned_calls = 80
    cached_first_attempts = sum((f"scene_{int(study[3:])+100000}:llm_graph:full", 0) in cache for study in dev_ids)
    cached_first_attempts += sum(
        (f"scene_{int(study[3:])+100000}:preferences:{variant}", 0) in cache
        for study in dev_ids for variant in config["hybrid"]["preference_variants"]
    )
    preflight = {
        "development_scenes": len(dev_ids),
        "planned_logical_calls": planned_calls,
        "cached_logical_calls": cached_first_attempts,
        "planned_new_logical_calls": planned_calls - cached_first_attempts,
        "rendered_prompt_token_upper_estimate": rendered_input_tokens,
        "holdout_accessed": False,
    }
    if not execute and not check and cached_first_attempts < planned_calls:
        return {"mode": "preflight", **preflight, "api_calls": 0}
    if len(scene_objects) != 20 or len(pref_rows) != 60:
        raise RuntimeError("T21 execution is incomplete")

    grid_rows: list[dict[str, Any]] = []
    for tau_margin in config["threshold_selection"]["grid"]["tau_margin"]:
        for tau_conflict in config["threshold_selection"]["grid"]["tau_conflict"]:
            correct = oriented = available = accepts = 0
            valid = 0
            for obj in scene_objects.values():
                parent = obj["raw"].partial_graph
                oracle = obj["oracle"].partial_graph
                for variant in config["hybrid"]["preference_variants"]:
                    selected = solve_h2_selective(parent, obj["forced"][variant], tau_margin=tau_margin, tau_conflict=tau_conflict)
                    graph = graph_from_dict(selected["output_graph"])
                    valid += int(graph.nodes == parent.nodes and graph.skeleton == parent.skeleton)
                    available += len(parent.undirected & oracle.skeleton)
                    if selected["decision"] == "accept":
                        accepts += 1
                        c, n = orientation_counts(graph, parent, oracle)
                        correct += c
                        oriented += n
            precision = correct / oriented if oriented else 0.0
            coverage = oriented / available if available else 1.0
            validity = valid / 60
            grid_rows.append(
                {
                    "schema_version": "fourgraph.p1_t21_threshold_candidate.v1",
                    "tau_margin": float(tau_margin),
                    "tau_conflict": float(tau_conflict),
                    "graph_validity": validity,
                    "orientation_correct": correct,
                    "orientation_total": oriented,
                    "orientation_available": available,
                    "orientation_precision": round(precision, 10),
                    "orientation_coverage": round(coverage, 10),
                    "confident_wrong_rate": round((oriented - correct) / available if available else 0.0, 10),
                    "accepted_scene_variants": accepts,
                    "abstained_scene_variants": 60 - accepts,
                    "eligible": validity == 1.0 and precision >= 0.95 and oriented > 0,
                    "uses_downstream_ranking": False,
                    "uses_holdout": False,
                }
            )
    best_ineligible_candidate = min(
        grid_rows,
        key=lambda row: (
            -float(row["orientation_precision"]),
            -float(row["orientation_coverage"]),
            float(row["tau_margin"]),
            -float(row["tau_conflict"]),
        ),
    )
    try:
        selected_threshold: dict[str, Any] | None = select_threshold(grid_rows)
    except RuntimeError:
        selected_threshold = None
    graph_rows = list(base_graph_rows)
    if selected_threshold is not None:
        for study_id, obj in scene_objects.items():
            parent = obj["raw"]
            for variant in config["hybrid"]["preference_variants"]:
                decision = solve_h2_selective(
                    parent.partial_graph,
                    obj["forced"][variant],
                    tau_margin=selected_threshold["tau_margin"],
                    tau_conflict=selected_threshold["tau_conflict"],
                )
                graph = graph_from_dict(decision["output_graph"])
                artifact = make_semantic_graph_artifact(
                    scene_id=obj["scene_id"],
                    parent=parent,
                    graph=graph,
                    graph_method="hybrid",
                    graph_type="dag" if decision["decision"] == "accept" else "cpdag",
                    graph_view="dag" if decision["decision"] == "accept" else "cpdag",
                    builder_id="fourgraph.p1_t21_h2_selective",
                    config_sha256=config_hash,
                    input_hashes=[content_sha256(obj["preferences"][variant]), parent.artifact_sha256],
                    edge_audit=orientation_edge_audit(parent.partial_graph, graph, reason="selected_global_extension") if decision["decision"] == "accept" else (),
                )
                row = artifact_record(f"G_HYBRID_H2_SELECTIVE_{variant.upper()}", study_id, variant, artifact)
                row["selective_decision"] = decision["decision"]
                graph_rows.append(row)

    condition_order = [item["id"] for item in read_yaml(ROOT / "configs/p1_hybrid_v1.yaml")["graph_views"]["static"]]
    condition_order += [item["id"] for item in read_yaml(ROOT / "configs/p1_hybrid_v1.yaml")["graph_views"]["semantic"]]
    evaluated_conditions = [
        condition
        for condition in condition_order
        if selected_threshold is not None or "H2_SELECTIVE" not in condition
    ]
    metrics: list[dict[str, Any]] = []
    graph_lookup = {(row["study_id"], row["condition"]): row for row in graph_rows}
    for study_id, obj in scene_objects.items():
        for condition in evaluated_conditions:
            if condition == "G_ORACLE":
                artifact = obj["oracle"]
                record = evaluate_graph(artifact, obj["oracle"], condition=condition, role="development", variable_mapping_sha256=obj["alias_hash"])
            else:
                row = graph_lookup[(study_id, condition)]
                if row["artifact"] is None:
                    record = {
                        "schema_version": "fourgraph.graph_metric_record.v1",
                        "scene_id": obj["scene_id"],
                        "graph_condition": condition,
                        "evaluation_role": "development",
                        "graph_valid": False,
                        "terminal_failure": row["error"],
                    }
                else:
                    artifact = GraphArtifact.from_dict(row["artifact"])
                    record = evaluate_graph(artifact, obj["oracle"], condition=condition, role="development", variable_mapping_sha256=obj["alias_hash"])
            record["study_id"] = study_id
            metrics.append(record)

    graph_rows.sort(key=lambda row: (row["study_id"], condition_order.index(row["condition"])))
    pref_rows.sort(key=lambda row: (row["study_id"], row["story_variant"]))
    grid_rows.sort(key=lambda row: (row["tau_margin"], row["tau_conflict"]))
    metrics.sort(key=lambda row: (row["study_id"], condition_order.index(row["graph_condition"])))
    outputs = {
        config["outputs"]["semantic_preferences"]: write_jsonl(Path(), pref_rows),
        config["outputs"]["graphs"]: write_jsonl(Path(), graph_rows),
        config["outputs"]["structural_metrics"]: write_jsonl(Path(), metrics),
        config["outputs"]["threshold_grid"]: write_jsonl(Path(), grid_rows),
    }
    token_totals = {key: 0 for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens")}
    for row in cache.values():
        if row["call_id"].startswith("scene_1"):
            for key in token_totals:
                token_totals[key] += int(row.get(key) or 0)
    summary_by_condition: dict[str, Any] = {}
    for condition in evaluated_conditions:
        rows = [row for row in metrics if row["graph_condition"] == condition]
        successes = [row for row in rows if row.get("graph_valid")]
        directed_f1 = [row["dag"]["directed_f1"] for row in successes if row.get("dag")]
        skeleton_f1 = [row["skeleton"]["f1"] for row in successes if row.get("skeleton")]
        summary_by_condition[condition] = {
            "records": len(rows),
            "valid": len(successes),
            "mean_skeleton_f1": round(sum(skeleton_f1) / len(skeleton_f1), 8) if skeleton_f1 else None,
            "mean_directed_f1": round(sum(directed_f1) / len(directed_f1), 8) if directed_f1 else None,
        }
    forced_orientation_by_variant: dict[str, Any] = {}
    for variant in config["hybrid"]["preference_variants"]:
        correct = total = false_adjacencies = 0
        for obj in scene_objects.values():
            parent = obj["raw"].partial_graph
            oracle = obj["oracle"].partial_graph
            forced_graph = obj["forced_artifacts"][variant].partial_graph
            c, n = orientation_counts(forced_graph, parent, oracle)
            correct += c
            total += n
            false_adjacencies += len(parent.undirected - oracle.skeleton)
        forced_orientation_by_variant[variant] = {
            "correct": correct,
            "evaluable": total,
            "precision": round(correct / total, 10) if total else None,
            "inherited_false_unresolved_adjacencies_reported_separately": false_adjacencies,
        }
    output_hashes = []
    for relative, payload in outputs.items():
        output_hashes.append({"path": relative, "bytes": len(payload), "sha256": sha256_hex(payload)})
    audit = {
        "schema_version": "fourgraph.p1_t21_development_audit.v1",
        "experiment_id": config["experiment_id"],
        "task": "T21",
        "counts": {
            "development_scenes": 20,
            "semantic_preference_artifacts": len(pref_rows),
            "graph_records_non_oracle": len(graph_rows),
            "structural_metric_records": len(metrics),
            "threshold_candidates": len(grid_rows),
            "new_api_calls_last_resume": counter.calls,
            "api_attempts_captured": len(cache),
            "api_requests_total_including_pre_inference_rejection": len(cache) + 1,
            "provider_rejected_before_model_inference": 1,
            "successful_model_responses": len(cache),
            "validation_retry_responses": sum(int(key[1] > 0) for key in cache),
        },
        "preflight": preflight,
        "selected_threshold": selected_threshold,
        "best_candidate_by_precision_then_coverage": best_ineligible_candidate,
        "threshold_selection_status": "selected" if selected_threshold is not None else "no_eligible_candidate",
        "condition_summary": summary_by_condition,
        "forced_orientation_by_variant": forced_orientation_by_variant,
        "token_usage": token_totals,
        "engineering_incidents": [
            {
                "stage": "first_live_request",
                "status": "provider_rejected_before_inference",
                "reason": "response_schema_const_field_missing_explicit_type",
                "model_response_created": False,
                "token_usage_recorded": False,
                "scientific_input_or_output_created": False,
                "resolution": "schema_syntax_corrected_and_hash_pin_updated_before_first_model_response",
            }
        ],
        "outputs": output_hashes,
        "dependencies": [{"path": k, "sha256": v} for k, v in config["freeze_anchors"].items()],
        "implementation_dependencies": [
            {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": hash_file(path)}
            for path in (
                config_path,
                ROOT / "src/fourgraph/p1_t21.py",
                ROOT / "src/fourgraph/t21_openai_backend.py",
                ROOT / "scripts/run_p1_t21.py",
            )
        ],
        "evidence_boundary": {
            "development_only": True,
            "holdout_accessed": False,
            "holdout_method_results_accessed": False,
            "development_tasks_or_answers_used_for_selection": False,
            "reasoner_executed": False,
            "downstream_ranking_used_for_selection": False,
        },
        "verdict": {
            "t21_complete": True,
            "threshold_selected": selected_threshold is not None,
            "threshold_eligibility_gate_passed": selected_threshold is not None,
            "protocol_amendment_required": selected_threshold is None,
            "t22_holdout_freeze_authorized": selected_threshold is not None,
            "t23_holdout_execution_authorized": False,
        },
    }
    audit_bytes = canonical_json_bytes(audit, newline=True)
    threshold_text = (
        f"Selected threshold: `tau_margin={selected_threshold['tau_margin']}`, `tau_conflict={selected_threshold['tau_conflict']}`; "
        f"development orientation precision `{selected_threshold['orientation_precision']}` and coverage `{selected_threshold['orientation_coverage']}`."
        if selected_threshold is not None
        else (
            "No threshold candidate met the preregistered 0.95 orientation-precision gate. "
            f"The best candidate reached precision `{best_ineligible_candidate['orientation_precision']}` at coverage "
            f"`{best_ineligible_candidate['orientation_coverage']}` ({best_ineligible_candidate['orientation_correct']}/"
            f"{best_ineligible_candidate['orientation_total']} evaluable orientations). No threshold was selected; "
            "the protocol requires amendment while holdout remains sealed."
        )
    )
    report = (
        "# T21 — P1 development graph construction and threshold selection\n\n"
        f"T21 completed on 20/20 frozen development scenes. It captured {len(pref_rows)} shared semantic-preference artifacts, "
        f"materialized {len(graph_rows)} non-Oracle graph records and evaluated 20 preregistered threshold pairs.\n\n"
        + threshold_text
        + "\n\n"
        + f"Forced orientation precision was full `{forced_orientation_by_variant['full']['precision']}`, partial "
        + f"`{forced_orientation_by_variant['partial']['precision']}`, and ambiguous `{forced_orientation_by_variant['ambiguous']['precision']}`. "
        + f"H1 produced valid graphs on {summary_by_condition['G_HYBRID_H1_FULL']['valid']}/20 scenes; H2-Forced was valid on 20/20 for every variant. "
        + f"Mean directed F1 was projection `{summary_by_condition['G_SCD_PROJECTED']['mean_directed_f1']}`, "
        + f"H2-Forced-Full `{summary_by_condition['G_HYBRID_H2_FORCED_FULL']['mean_directed_f1']}`, standalone LLM "
        + f"`{summary_by_condition['G_LLM_FULL']['mean_directed_f1']}`, and DirectLiNGAM `{summary_by_condition['G_DIRECTLINGAM']['mean_directed_f1']}`.\n\n"
        + f"Captured token usage was {token_totals['input_tokens']} input and {token_totals['output_tokens']} output tokens "
        + f"({token_totals['reasoning_tokens']} reasoning). "
        f"Captured live API attempts: {len(cache)}; this final resume added {counter.calls}. Raw call logs remain outside Git. "
        "One earlier request was rejected by the endpoint before inference because a JSON Schema const field lacked an explicit type; it created no model response or token usage and was corrected before the first scientific response. "
        "No holdout input, downstream answer, downstream ranking or reasoner output was accessed. "
        + ("T22 may freeze P1 holdout execution; T23 remains unauthorized.\n" if selected_threshold is not None else "T22 and T23 remain unauthorized.\n")
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
    return {
        "mode": "check" if check else "execute",
        **preflight,
        "new_api_calls": counter.calls,
        "semantic_preferences": len(pref_rows),
        "graph_records": len(graph_rows),
        "metrics": len(metrics),
        "selected_threshold": None if selected_threshold is None else {k: selected_threshold[k] for k in ("tau_margin", "tau_conflict", "orientation_precision", "orientation_coverage")},
        "t21_complete": True,
        "t22_authorized": selected_threshold is not None,
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
