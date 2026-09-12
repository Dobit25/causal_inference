"""Build or byte-check the frozen T09 development SCD graph artifacts."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fourgraph.causalds_access import resolve_public_artifact  # noqa: E402
from fourgraph.causalds_scd import TetradBackend, file_sha256, load_scene_data  # noqa: E402
from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.scd_graph import SCDGraphPolicy, build_scd_graphs  # noqa: E402


DEFAULT_CONFIG = Path("configs/t09_scd_graph_builder.yaml")


def _mapping(path: Path, *, yaml_file: bool = False) -> dict[str, Any]:
    value = (
        yaml.safe_load(path.read_text(encoding="utf-8"))
        if yaml_file
        else json.loads(path.read_text(encoding="utf-8"))
    )
    if not isinstance(value, dict):
        raise ValueError(f"Expected mapping: {path}")
    return value


def _policy(config: dict[str, Any]) -> SCDGraphPolicy:
    discovery = config["discovery"]
    return SCDGraphPolicy(
        candidate_id=discovery["selected_method_id"],
        family="boss_basis_bic",
        penalty_discount=discovery["parameters"]["penalty_discount"],
        truncation_limit=discovery["parameters"]["truncation_limit"],
        seed=discovery["seed"],
    )


def _validate_config(config: dict[str, Any], config_path: Path) -> tuple[str, ...]:
    if config["experiment"]["task"] != "T09":
        raise ValueError("Expected the T09 config")
    if config["source"]["variant"] != "clean":
        raise ValueError("T09 is frozen to the clean observation variant")
    scope = config["scope"]
    if scope["role"] != "dev" or scope["forbid_holdout_access"] is not True:
        raise ValueError("T09 is restricted to frozen development scenes")
    if config["evidence"]["public_artifacts"] != ["data", "schema"]:
        raise ValueError("T09 public evidence must be exactly data and schema")
    if config["evidence"]["allowed"] != [
        "public_observational_data",
        "public_schema_types",
    ]:
        raise ValueError("T09 evidence allowlist changed")
    for key in (
        "allow_story_or_semantics",
        "allow_tasks_or_queries",
        "allow_llm_graph",
        "allow_grading_or_oracle",
        "allow_gold_answers",
    ):
        if config["evidence"][key] is not False:
            raise ValueError(f"T09 config permits forbidden evidence: {key}")
    if config["preprocessing"]["pool_scenes"] is not False:
        raise ValueError("T09 cannot pool observations across causal scenes")
    expected_preprocessing = {
        "pool_scenes": False,
        "canonical_names": "X000_X001_etc",
        "preserve_row_order": True,
        "continuous": "per_scene_sample_zscore_ddof_1",
        "binary": "exact_0_1_discrete_categories",
        "reject_missing_or_nonfinite": True,
        "reject_constant_continuous": True,
    }
    if config["preprocessing"] != expected_preprocessing:
        raise ValueError("T09 preprocessing contract changed")
    discovery = config["discovery"]
    if discovery["algorithm"] != "BOSS" or discovery["score"] != "BasisFunctionBicScore":
        raise ValueError("T09 discovery family changed")
    if config["discovery"]["output"] != "CPDAG":
        raise ValueError("T09 primary output must remain a CPDAG")
    expected_parameters = {
        "penalty_discount": 1.0,
        "truncation_limit": 3,
        "singularity_lambda": 0.0,
        "do_one_equation_only": False,
        "num_starts": 1,
        "use_bes": False,
        "use_data_order": True,
        "output_cpdag": True,
    }
    if discovery["parameters"] != expected_parameters:
        raise ValueError("T09 frozen BOSS parameters changed")
    if config["projection"]["role"] != "sensitivity_only":
        raise ValueError("T09 projection must remain sensitivity-only")
    _policy(config).validate()

    for relative, expected in config["freeze_anchors"].items():
        if file_sha256(PROJECT_ROOT / relative) != expected:
            raise RuntimeError(f"Frozen dependency changed: {relative}")

    split = _mapping(PROJECT_ROOT / scope["split_manifest"])
    cohort = split["cohorts"][scope["cohort"]]
    dev_ids = tuple(cohort["dev_ids"])
    holdout_ids = set(cohort["holdout_ids"])
    if len(dev_ids) != scope["expected_scenes"] or set(dev_ids) & holdout_ids:
        raise ValueError("T09 frozen development scope is invalid")
    if config_path.resolve() != (PROJECT_ROOT / DEFAULT_CONFIG).resolve():
        # Alternate configs are allowed for tests, but never silently treated as frozen.
        _policy(config).validate()
    return dev_ids


def _validate_runtime(config: dict[str, Any], backend: TetradBackend) -> None:
    runtime = config["runtime"]
    actual = {
        "python": platform.python_version(),
        "jpype": importlib.metadata.version("JPype1"),
        "numpy": importlib.metadata.version("numpy"),
        "pyarrow": importlib.metadata.version("pyarrow"),
    }
    for key, value in actual.items():
        if value != str(runtime[key]):
            raise RuntimeError(f"T09 runtime drift for {key}: {value} != {runtime[key]}")
    if backend.jar_sha256 != runtime["tetrad_jar_sha256"]:
        raise RuntimeError("T09 Tetrad JAR hash drift")
    import jpype

    java_version = str(jpype.java.lang.System.getProperty("java.version"))
    if java_version != str(runtime["java"]):
        raise RuntimeError(
            f"T09 Java runtime drift: {java_version} != {runtime['java']}"
        )


def _scene_inputs(source_root: Path, scene_id: str, variant: str) -> tuple[str, str]:
    parquet = resolve_public_artifact(source_root, scene_id, variant, "data")
    schema = resolve_public_artifact(source_root, scene_id, variant, "schema")
    return file_sha256(parquet), file_sha256(schema)


def build_outputs(
    source_root: Path,
    *,
    config_path: Path = DEFAULT_CONFIG,
    jar_path: Path | None = None,
) -> tuple[bytes, bytes, bytes, list[dict[str, Any]]]:
    config_path = (PROJECT_ROOT / config_path).resolve()
    config = _mapping(config_path, yaml_file=True)
    dev_ids = _validate_config(config, config_path)
    runtime = config["runtime"]
    resolved_jar = (jar_path or PROJECT_ROOT / runtime["tetrad_jar"]).resolve()
    backend = TetradBackend(resolved_jar, runtime["tetrad_jar_sha256"])
    _validate_runtime(config, backend)
    config_sha256 = file_sha256(config_path)
    policy = _policy(config)

    raw_artifacts = []
    projected_artifacts = []
    audit_records = []
    runtime_records = []
    for scene_id in dev_ids:
        data_hash, schema_hash = _scene_inputs(
            source_root.resolve(), scene_id, config["source"]["variant"]
        )
        scene_data = load_scene_data(source_root.resolve(), scene_id)
        if scene_data.values.shape[0] != config["scope"]["rows_per_scene"]:
            raise ValueError(f"Unexpected row count for {scene_id}")
        result = build_scd_graphs(
            scene_data,
            backend=backend,
            policy=policy,
            config_sha256=config_sha256,
            input_artifact_sha256=[data_hash, schema_hash],
        )
        raw_artifacts.append(result.raw_cpdag)
        projected_artifacts.append(result.projected_dag)
        record = result.audit_record()
        record.update(
            {
                "data_sha256": data_hash,
                "schema_sha256": schema_hash,
                "row_count": int(scene_data.values.shape[0]),
                "binary_node_count": sum(scene_data.binary_flags),
                "continuous_node_count": len(scene_data.binary_flags)
                - sum(scene_data.binary_flags),
            }
        )
        audit_records.append(record)
        runtime_records.append(
            {
                "scene_id": scene_id,
                "runtime_seconds": result.runtime_seconds,
                "raw_graph_sha256": result.raw_cpdag.graph_sha256,
                "raw_artifact_sha256": result.raw_cpdag.artifact_sha256,
                "projected_artifact_sha256": result.projected_dag.artifact_sha256,
            }
        )

    raw_bytes = b"".join(item.to_json_bytes() for item in raw_artifacts)
    projected_bytes = b"".join(item.to_json_bytes() for item in projected_artifacts)
    audit = {
        "manifest_version": 1,
        "task": "T09",
        "status": "complete_scd_graph_builder_ready",
        "scope": {
            "cohort": "graph_dev",
            "scene_ids": list(dev_ids),
            "scene_count": len(dev_ids),
            "holdout_scene_count": 25,
            "holdout_accessed": False,
            "story_or_semantics_accessed": False,
            "tasks_or_queries_accessed": False,
            "llm_graph_accessed": False,
            "grading_or_oracle_accessed": False,
            "scenes_pooled": False,
        },
        "method": {
            "selected_method_id": config["discovery"]["selected_method_id"],
            "algorithm": config["discovery"]["algorithm"],
            "score": config["discovery"]["score"],
            "parameters": config["discovery"]["parameters"],
            "raw_output": "cpdag",
            "projected_output_role": "sensitivity_only",
        },
        "runtime": {
            "python": runtime["python"],
            "java": runtime["java"],
            "jpype": runtime["jpype"],
            "numpy": runtime["numpy"],
            "pyarrow": runtime["pyarrow"],
            "tetrad_jar_sha256": runtime["tetrad_jar_sha256"],
        },
        "contract": {
            "schema_version": config["graph"]["schema_version"],
            "config_sha256": config_sha256,
            "split_manifest_sha256": file_sha256(
                PROJECT_ROOT / config["scope"]["split_manifest"]
            ),
            "t05_frozen_config_sha256": file_sha256(
                PROJECT_ROOT / "configs/t05_scd_frozen.yaml"
            ),
            "graph_contract_sha256": file_sha256(
                PROJECT_ROOT / config["graph"]["contract_config"]
            ),
        },
        "development_build": {
            "raw_cpdag_count": len(raw_artifacts),
            "projected_dag_count": len(projected_artifacts),
            "records": audit_records,
            "raw_cpdag_set_sha256": sha256_hex(raw_bytes),
            "projected_dag_set_sha256": sha256_hex(projected_bytes),
        },
        "verdict": {
            "t09_complete": len(raw_artifacts) == len(dev_ids),
            "scd_graph_builder_ready": len(raw_artifacts) == len(dev_ids),
            "blocker": None,
        },
    }
    return (
        canonical_json_bytes(audit, newline=True),
        raw_bytes,
        projected_bytes,
        runtime_records,
    )


def run_gate(
    source_root: Path,
    scene_id: str,
    *,
    config_path: Path,
    jar_path: Path | None,
) -> dict[str, Any]:
    config_path = (PROJECT_ROOT / config_path).resolve()
    config = _mapping(config_path, yaml_file=True)
    dev_ids = _validate_config(config, config_path)
    if scene_id not in dev_ids:
        raise ValueError("T09 gate scene must be a frozen development scene")
    runtime = config["runtime"]
    resolved_jar = (jar_path or PROJECT_ROOT / runtime["tetrad_jar"]).resolve()
    backend = TetradBackend(resolved_jar, runtime["tetrad_jar_sha256"])
    _validate_runtime(config, backend)
    scene_data = load_scene_data(source_root.resolve(), scene_id)
    input_hashes = _scene_inputs(source_root.resolve(), scene_id, config["source"]["variant"])
    kwargs = {
        "backend": backend,
        "policy": _policy(config),
        "config_sha256": file_sha256(config_path),
        "input_artifact_sha256": input_hashes,
    }
    first = build_scd_graphs(scene_data, **kwargs)
    second = build_scd_graphs(scene_data, **kwargs)
    deterministic = (
        first.raw_cpdag.to_json_bytes() == second.raw_cpdag.to_json_bytes()
        and first.projected_dag.to_json_bytes() == second.projected_dag.to_json_bytes()
    )
    if not deterministic:
        raise RuntimeError("T09 one-scene deterministic gate failed")
    return {
        "scene_id": scene_id,
        "raw_cpdag_valid": True,
        "projected_dag_valid": True,
        "deterministic_rerun": True,
        "node_count": len(first.raw_cpdag.nodes),
        "adjacency_count": len(first.raw_cpdag.partial_graph.skeleton),
        "unresolved_edge_count": len(first.raw_cpdag.partial_graph.undirected),
        "holdout_accessed": False,
    }


def _check(path: Path, expected: bytes) -> None:
    if not path.is_file() or path.read_bytes() != expected:
        raise RuntimeError(f"Generated artifact is missing or stale: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--jar", type=Path)
    parser.add_argument("--gate-scene")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.gate_scene:
        result = run_gate(
            args.source_root,
            args.gate_scene,
            config_path=args.config,
            jar_path=args.jar,
        )
        print(json.dumps(result, indent=2))
        return 0

    audit_bytes, raw_bytes, projected_bytes, runtimes = build_outputs(
        args.source_root,
        config_path=args.config,
        jar_path=args.jar,
    )
    config = _mapping(PROJECT_ROOT / args.config, yaml_file=True)
    output_paths = {
        "audit": PROJECT_ROOT / config["outputs"]["audit"],
        "raw_cpdag": PROJECT_ROOT / config["outputs"]["raw_cpdag"],
        "projected_dag": PROJECT_ROOT / config["outputs"]["projected_dag"],
    }
    expected = {
        "audit": audit_bytes,
        "raw_cpdag": raw_bytes,
        "projected_dag": projected_bytes,
    }
    if args.check:
        for key, path in output_paths.items():
            _check(path, expected[key])
    else:
        for key, path in output_paths.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected[key])
        runtime_path = PROJECT_ROOT / config["logging"]["runtime_log"]
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_path.write_bytes(
            b"".join(canonical_json_bytes(item, newline=True) for item in runtimes)
        )

    audit = json.loads(audit_bytes)
    print(
        json.dumps(
            {
                "mode": "check" if args.check else "write",
                "status": audit["status"],
                "raw_cpdag": audit["development_build"]["raw_cpdag_count"],
                "projected_dag": audit["development_build"]["projected_dag_count"],
                "holdout_accessed": audit["scope"]["holdout_accessed"],
                "scd_graph_builder_ready": audit["verdict"]["scd_graph_builder_ready"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
