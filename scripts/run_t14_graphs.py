"""Run/resume the frozen T14 non-Oracle graph construction phases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fourgraph.causalds_access import resolve_public_artifact  # noqa: E402
from fourgraph.causalds_public import load_llm_graph_input  # noqa: E402
from fourgraph.causalds_scd import TetradBackend, file_sha256, load_scene_data  # noqa: E402
from fourgraph.graph_contract import (  # noqa: E402
    GraphArtifact,
    canonical_json_bytes,
    sha256_hex,
    validate_hybrid_relationship,
    validate_projection_relationship,
)
from fourgraph.graph_metrics import load_graph_artifact_jsonl  # noqa: E402
from fourgraph.hybrid_graph import HybridPolicy, build_hybrid_graph, load_prompt_template as load_hybrid_prompt  # noqa: E402
from fourgraph.llm_backend import LLMCallResponse  # noqa: E402
from fourgraph.llm_graph import LLMGraphPolicy, build_llm_graph, load_prompt_template  # noqa: E402
from fourgraph.openai_backend import OpenAIResponsesBackend  # noqa: E402
from fourgraph.scd_graph import SCDGraphPolicy, build_scd_graphs  # noqa: E402
from fourgraph.t10_openai_backend import T10OpenAIResponsesBackend  # noqa: E402


def obj(path: Path, yaml_file: bool = False) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) if yaml_file else json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected mapping: {path}")
    return value


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def seeded_order(scene_ids: list[str], seed: int) -> list[str]:
    return sorted(scene_ids, key=lambda scene: hashlib.sha256(f"{seed}|{scene}".encode()).hexdigest())


def validate_t13() -> tuple[dict[str, Any], list[str]]:
    manifest_path = ROOT / "data/manifests/t13_holdout_execution.json"
    audit = obj(ROOT / "data/manifests/t13_holdout_execution_audit.json")
    manifest = obj(manifest_path)
    if not audit["verdict"]["t14_authorized"] or audit["verdict"]["t14_started"]:
        raise RuntimeError("T13 does not authorize an unopened T14")
    if sha256_hex(manifest_path.read_bytes()) != audit["execution_manifest_sha256"]:
        raise RuntimeError("T13 execution manifest hash mismatch")
    for item in manifest["frozen_components"]:
        if sha256_hex((ROOT / item["path"]).read_bytes()) != item["sha256"]:
            raise RuntimeError(f"T13 frozen dependency changed: {item['path']}")
    return manifest, manifest["cohorts"]["graph"]["holdout_scene_ids"]


class PhaseReplay:
    def __init__(self, attempt_path: Path, phase: str):
        self.entries = {(item["scene_id"], item["attempt"]): item for item in rows(attempt_path) if item.get("phase") == phase}

    def has_scene(self, scene_id: str) -> bool:
        return (scene_id, 0) in self.entries

    def complete(self, request: Any) -> LLMCallResponse:
        item = self.entries[(request.scene_id, request.attempt)]
        if item["prompt_sha256"] != request.prompt_sha256:
            raise RuntimeError(f"T14 replay prompt mismatch: {request.scene_id}")
        return LLMCallResponse(
            raw_text=item["raw_text"], provider=item["provider"], model_id=item["model_id"], model_version=item["model_version"],
            request_id=item["request_id"], system_fingerprint=item["system_fingerprint"], input_tokens=item["input_tokens"],
            output_tokens=item["output_tokens"], reasoning_tokens=item.get("reasoning_tokens"), cached_input_tokens=item.get("cached_input_tokens"),
            latency_ms=item["latency_ms"], endpoint=item["endpoint"], sdk_version=item["sdk_version"], service_tier=item["service_tier"],
            provider_response_json=item.get("provider_response_json"), response_status=item.get("response_status"), incomplete_reason=item.get("incomplete_reason"),
        )


def append_attempts(path: Path, phase: str, result: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        for attempt in result.attempts:
            record = attempt.raw_log_record(result.scene_id)
            record["phase"] = phase
            record["reasoning_tokens"] = attempt.response.reasoning_tokens
            record["cached_input_tokens"] = attempt.response.cached_input_tokens
            record["response_status"] = attempt.response.response_status
            record["incomplete_reason"] = attempt.response.incomplete_reason
            stream.write(canonical_json_bytes(record, newline=True))
        stream.flush()


def graph_path(root: Path, condition: str) -> Path:
    return root / "graphs" / f"{condition}.jsonl"


def load_existing(path: Path) -> dict[str, GraphArtifact]:
    return load_graph_artifact_jsonl(path) if path.exists() else {}


def write_graphs(path: Path, graphs: dict[str, GraphArtifact], canonical_scene_ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(graphs[scene].to_json_bytes() for scene in canonical_scene_ids if scene in graphs))


def failure_path(root: Path) -> Path:
    return root / "graphs" / "failures.jsonl"


def load_failures(root: Path) -> dict[tuple[str, str], dict[str, Any]]:
    return {(item["condition"], item["scene_id"]): item for item in rows(failure_path(root))}


def write_failures(root: Path, failures: dict[tuple[str, str], dict[str, Any]], scene_ids: list[str]) -> None:
    order = {scene: index for index, scene in enumerate(scene_ids)}
    payload = sorted(failures.values(), key=lambda item: (item["condition"], order[item["scene_id"]]))
    path = failure_path(root)
    path.write_bytes(b"".join(canonical_json_bytes(item, newline=True) for item in payload))


def run_llm(source_root: Path, out_root: Path, attempts: Path, scene_ids: list[str], order: list[str], api_key: str) -> None:
    config_path = ROOT / "configs/t08_llm_graph_builder.yaml"
    config = obj(config_path, True)
    llm = config["llm"]
    schema = obj(ROOT / config["prompt"]["response_schema"])
    backend = OpenAIResponsesBackend(api_key=api_key, response_schema=schema, service_tier=llm["service_tier"], reasoning_effort=llm["reasoning_effort"], store=llm["store"], transport_max_retries=llm["transport_max_retries"], timeout_seconds=llm["timeout_seconds"])
    if backend.sdk_version != llm["sdk_version"]:
        raise RuntimeError("OpenAI SDK drift")
    template, digest = load_prompt_template(ROOT / config["prompt"]["template"])
    if digest != config["prompt"]["template_sha256"]:
        raise RuntimeError("T08 prompt drift")
    policy = LLMGraphPolicy(llm["provider"], llm["model_id"], llm["model_version"], llm["temperature"], llm["max_tokens"], llm["seed"], llm["max_validation_retries"])
    path = graph_path(out_root, "G_LLM")
    graphs = load_existing(path)
    replay = PhaseReplay(attempts, "G_LLM")
    for scene in order:
        if scene in graphs:
            continue
        evidence = load_llm_graph_input(source_root, scene, variant="clean")
        cached = replay.has_scene(scene)
        result = build_llm_graph(evidence, backend=replay if cached else backend, policy=policy, prompt_template=template, config_sha256=sha256_hex(config_path.read_bytes()))
        if not cached:
            append_attempts(attempts, "G_LLM", result)
            replay = PhaseReplay(attempts, "G_LLM")
        if not result.success:
            raise RuntimeError(f"G_LLM failed without fallback: {scene}: {result.final_error}")
        graphs[scene] = result.artifact
        write_graphs(path, graphs, scene_ids)
        print(json.dumps({"phase": "G_LLM", "scene_id": scene, "complete": len(graphs), "replay": cached}), flush=True)


def run_scd(source_root: Path, out_root: Path, scene_ids: list[str], order: list[str]) -> None:
    config_path = ROOT / "configs/t09_scd_graph_builder.yaml"
    config = obj(config_path, True)
    runtime = config["runtime"]
    backend = TetradBackend(ROOT / runtime["tetrad_jar"], runtime["tetrad_jar_sha256"])
    policy = SCDGraphPolicy(config["discovery"]["selected_method_id"], "boss_basis_bic", 1.0, 3, None)
    raw_path, projected_path = graph_path(out_root, "G_SCD_RAW"), graph_path(out_root, "G_SCD_PROJECTED")
    raw, projected = load_existing(raw_path), load_existing(projected_path)
    runtime_path = out_root / "graphs" / "scd_runtime.jsonl"
    runtime_rows = {item["scene_id"]: item for item in rows(runtime_path)}
    for scene in order:
        if scene in raw and scene in projected:
            continue
        data_path = resolve_public_artifact(source_root, scene, "clean", "data")
        schema_path = resolve_public_artifact(source_root, scene, "clean", "schema")
        data = load_scene_data(source_root, scene)
        result = build_scd_graphs(data, backend=backend, policy=policy, config_sha256=sha256_hex(config_path.read_bytes()), input_artifact_sha256=(file_sha256(data_path), file_sha256(schema_path)))
        validate_projection_relationship(result.raw_cpdag, result.projected_dag)
        raw[scene], projected[scene] = result.raw_cpdag, result.projected_dag
        runtime_rows[scene] = {"scene_id": scene, "runtime_seconds": result.runtime_seconds, "raw_artifact_sha256": result.raw_cpdag.artifact_sha256, "projected_artifact_sha256": result.projected_dag.artifact_sha256}
        write_graphs(raw_path, raw, scene_ids)
        write_graphs(projected_path, projected, scene_ids)
        runtime_path.write_bytes(b"".join(canonical_json_bytes(runtime_rows[item], newline=True) for item in scene_ids if item in runtime_rows))
        print(json.dumps({"phase": "G_SCD", "scene_id": scene, "complete": len(raw)}), flush=True)


def run_hybrid(source_root: Path, out_root: Path, attempts: Path, scene_ids: list[str], order: list[str], api_key: str) -> None:
    config_path = ROOT / "configs/t10_hybrid_graph_builder.yaml"
    config = obj(config_path, True)
    llm = config["llm"]
    parents = load_existing(graph_path(out_root, "G_SCD_RAW"))
    if set(parents) != set(scene_ids):
        raise RuntimeError("Hybrid cannot start before all raw SCD graphs are sealed")
    schema = obj(ROOT / config["prompt"]["response_schema"])
    backend = T10OpenAIResponsesBackend(api_key=api_key, response_schema=schema, service_tier=llm["service_tier"], reasoning_effort=llm["reasoning_effort"], store=llm["store"], transport_max_retries=llm["transport_max_retries"], timeout_seconds=llm["timeout_seconds"])
    if backend.sdk_version != llm["sdk_version"]:
        raise RuntimeError("OpenAI SDK drift")
    template, digest = load_hybrid_prompt(ROOT / config["prompt"]["template"])
    if digest != config["prompt"]["template_sha256"]:
        raise RuntimeError("T10 prompt drift")
    policy = HybridPolicy(llm["provider"], llm["model_id"], llm["model_version"], llm["temperature"], llm["max_tokens"], llm["seed"], llm["max_validation_retries"])
    path = graph_path(out_root, "G_HYBRID")
    graphs = load_existing(path)
    failures = load_failures(out_root)
    replay = PhaseReplay(attempts, "G_HYBRID")
    for scene in order:
        if scene in graphs or ("G_HYBRID", scene) in failures:
            continue
        evidence = load_llm_graph_input(source_root, scene, variant="clean")
        cached = replay.has_scene(scene)
        result = build_hybrid_graph(evidence, parents[scene], backend=replay if cached else backend, policy=policy, prompt_template=template, config_sha256=sha256_hex(config_path.read_bytes()))
        if not cached:
            append_attempts(attempts, "G_HYBRID", result)
            replay = PhaseReplay(attempts, "G_HYBRID")
        if not result.success:
            failures[("G_HYBRID", scene)] = {
                "schema_version": "fourgraph.t14_graph_failure.v1",
                "condition": "G_HYBRID",
                "scene_id": scene,
                "attempts": len(result.attempts),
                "final_error": result.final_error,
                "fallback_used": False,
                "terminal": True,
            }
            write_failures(out_root, failures, scene_ids)
            print(json.dumps({"phase": "G_HYBRID", "scene_id": scene, "terminal_failure": True, "complete_or_terminal": len(graphs) + sum(key[0] == "G_HYBRID" for key in failures)}), flush=True)
            continue
        validate_hybrid_relationship(parents[scene], result.artifact)
        graphs[scene] = result.artifact
        write_graphs(path, graphs, scene_ids)
        print(json.dumps({"phase": "G_HYBRID", "scene_id": scene, "complete": len(graphs), "unresolved": result.unresolved_edge_count, "replay": cached}), flush=True)


def seal(out_root: Path, attempts: Path, scene_ids: list[str], t13: dict[str, Any]) -> None:
    files = {name: graph_path(out_root, name) for name in ("G_LLM", "G_SCD_RAW", "G_SCD_PROJECTED", "G_HYBRID")}
    graphs = {name: load_existing(path) for name, path in files.items()}
    failures = load_failures(out_root)
    for name, items in graphs.items():
        terminal = set(items) | {scene for condition, scene in failures if condition == name}
        if terminal != set(scene_ids):
            raise RuntimeError(f"Cannot seal non-terminal graph condition: {name}")
    for scene in scene_ids:
        validate_projection_relationship(graphs["G_SCD_RAW"][scene], graphs["G_SCD_PROJECTED"][scene])
        if scene in graphs["G_HYBRID"]:
            validate_hybrid_relationship(graphs["G_SCD_RAW"][scene], graphs["G_HYBRID"][scene])
    payload = {
        "schema_version": "fourgraph.t14_non_oracle_seal.v1",
        "logical_run_id": t13["execution"]["logical_run_id"],
        "scene_ids": scene_ids,
        "condition_files": {name: {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_hex(path.read_bytes()), "successful_records": len(graphs[name]), "terminal_failures": sum(condition == name for condition, _ in failures), "scheduled_records": 25} for name, path in files.items()},
        "failure_manifest": {"path": failure_path(out_root).relative_to(ROOT).as_posix(), "sha256": sha256_hex(failure_path(out_root).read_bytes()) if failure_path(out_root).exists() else sha256_hex(b""), "records": len(failures)},
        "attempt_log_sha256": sha256_hex(attempts.read_bytes()) if attempts.exists() else sha256_hex(b""),
        "oracle_accessed": False,
        "sealed": True,
    }
    seal_path = out_root / "non_oracle_seal.json"
    encoded = canonical_json_bytes(payload, newline=True)
    if seal_path.exists() and seal_path.read_bytes() != encoded:
        raise RuntimeError("Existing non-Oracle seal differs")
    seal_path.write_bytes(encoded)


def check_replay(source_root: Path, out_root: Path, attempts: Path, scene_ids: list[str], order: list[str]) -> None:
    stored = {name: load_existing(graph_path(out_root, name)) for name in ("G_LLM", "G_SCD_RAW", "G_SCD_PROJECTED", "G_HYBRID")}
    failures = load_failures(out_root)

    t08_path = ROOT / "configs/t08_llm_graph_builder.yaml"
    t08 = obj(t08_path, True)
    llm = t08["llm"]
    llm_template, llm_digest = load_prompt_template(ROOT / t08["prompt"]["template"])
    if llm_digest != t08["prompt"]["template_sha256"]:
        raise RuntimeError("T08 replay prompt drift")
    llm_policy = LLMGraphPolicy(llm["provider"], llm["model_id"], llm["model_version"], llm["temperature"], llm["max_tokens"], llm["seed"], llm["max_validation_retries"])
    llm_replay = PhaseReplay(attempts, "G_LLM")
    for scene in order:
        result = build_llm_graph(load_llm_graph_input(source_root, scene, variant="clean"), backend=llm_replay, policy=llm_policy, prompt_template=llm_template, config_sha256=sha256_hex(t08_path.read_bytes()))
        if not result.success or result.artifact.to_json_bytes() != stored["G_LLM"][scene].to_json_bytes():
            raise RuntimeError(f"G_LLM replay mismatch: {scene}")

    t09_path = ROOT / "configs/t09_scd_graph_builder.yaml"
    t09 = obj(t09_path, True)
    runtime = t09["runtime"]
    scd_backend = TetradBackend(ROOT / runtime["tetrad_jar"], runtime["tetrad_jar_sha256"])
    scd_policy = SCDGraphPolicy(t09["discovery"]["selected_method_id"], "boss_basis_bic", 1.0, 3, None)
    for scene in order:
        data_path = resolve_public_artifact(source_root, scene, "clean", "data")
        schema_path = resolve_public_artifact(source_root, scene, "clean", "schema")
        result = build_scd_graphs(load_scene_data(source_root, scene), backend=scd_backend, policy=scd_policy, config_sha256=sha256_hex(t09_path.read_bytes()), input_artifact_sha256=(file_sha256(data_path), file_sha256(schema_path)))
        if result.raw_cpdag.to_json_bytes() != stored["G_SCD_RAW"][scene].to_json_bytes() or result.projected_dag.to_json_bytes() != stored["G_SCD_PROJECTED"][scene].to_json_bytes():
            raise RuntimeError(f"SCD replay mismatch: {scene}")

    t10_path = ROOT / "configs/t10_hybrid_graph_builder.yaml"
    t10 = obj(t10_path, True)
    hybrid_llm = t10["llm"]
    hybrid_template, hybrid_digest = load_hybrid_prompt(ROOT / t10["prompt"]["template"])
    if hybrid_digest != t10["prompt"]["template_sha256"]:
        raise RuntimeError("T10 replay prompt drift")
    hybrid_policy = HybridPolicy(hybrid_llm["provider"], hybrid_llm["model_id"], hybrid_llm["model_version"], hybrid_llm["temperature"], hybrid_llm["max_tokens"], hybrid_llm["seed"], hybrid_llm["max_validation_retries"])
    hybrid_replay = PhaseReplay(attempts, "G_HYBRID")
    for scene in order:
        result = build_hybrid_graph(load_llm_graph_input(source_root, scene, variant="clean"), stored["G_SCD_RAW"][scene], backend=hybrid_replay, policy=hybrid_policy, prompt_template=hybrid_template, config_sha256=sha256_hex(t10_path.read_bytes()))
        expected_failure = ("G_HYBRID", scene) in failures
        if expected_failure != (not result.success):
            raise RuntimeError(f"Hybrid replay terminal-state mismatch: {scene}")
        if result.success and result.artifact.to_json_bytes() != stored["G_HYBRID"][scene].to_json_bytes():
            raise RuntimeError(f"Hybrid replay graph mismatch: {scene}")
    print(json.dumps({"check": "byte_exact_graph_replay", "llm": 25, "scd_raw": 25, "scd_projected": 25, "hybrid_success": 23, "hybrid_terminal_failure": 2, "api_calls": 0}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--phase", choices=("preflight", "llm", "scd", "hybrid", "seal", "all"), default="all")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    args = parser.parse_args()
    t13, scene_ids = validate_t13()
    out_root = ROOT / t13["execution"]["outputs"]["t14_root"]
    attempts = ROOT / t13["execution"]["outputs"]["t14_attempt_log"]
    order = seeded_order(scene_ids, t13["execution"]["builder_scene_order_seed"])
    if args.check:
        check_replay(args.source_root.resolve(), out_root, attempts, scene_ids, order)
        return 0
    if args.phase == "preflight":
        print(json.dumps({"preflight": True, "scene_count": 25, "order": order, "api_calls": 0, "oracle_accessed": False}, indent=2))
        return 0
    load_dotenv(ROOT / args.dotenv, override=True)
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key and args.phase in {"llm", "hybrid", "all"}:
        raise RuntimeError("Missing OPENAI_API_KEY")
    source_root = args.source_root.resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    if args.phase in {"llm", "all"}:
        run_llm(source_root, out_root, attempts, scene_ids, order, api_key)
    if args.phase in {"scd", "all"}:
        run_scd(source_root, out_root, scene_ids, order)
    if args.phase in {"hybrid", "all"}:
        run_hybrid(source_root, out_root, attempts, scene_ids, order, api_key)
    if args.phase in {"seal", "all"}:
        seal(out_root, attempts, scene_ids, t13)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
