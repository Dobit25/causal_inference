from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import sys
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fourgraph.causalds_scd import (  # noqa: E402
    CandidateSpec,
    TetradBackend,
    deterministic_half_sample_indices,
    expand_candidates,
    file_sha256,
    load_scene_data,
)
from fourgraph.causalds_oracle import (  # noqa: E402
    load_oracle_dag_for_dev_scoring,
)
from fourgraph.partial_graph import (  # noqa: E402
    PartialGraph,
    consistent_extension,
    cpdag_metrics,
    graph_stability,
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def canonical_jsonl(records: list[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
        for record in records
    )


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def graph_from_dict(value: dict[str, Any]) -> PartialGraph:
    return PartialGraph.build(
        value["nodes"], value.get("directed", []), value.get("undirected", [])
    )


def mean(records: list[dict[str, Any]], key: str) -> float:
    return round(statistics.fmean(float(record[key]) for record in records), 8)


def aggregate_candidates(
    specs: list[CandidateSpec], full_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    aggregate: list[dict[str, Any]] = []
    for spec in specs:
        records = [
            record
            for record in full_records
            if record["candidate_id"] == spec.candidate_id
        ]
        successes = [record for record in records if record["status"] == "ok"]
        hard_gate = (
            len(successes) == 8
            and all(record["deterministic_rerun_match"] for record in successes)
            and all(record["consistent_extension_valid"] for record in successes)
            and all(record["runtime_seconds"] <= 120 for record in successes)
        )
        summary: dict[str, Any] = {
            "candidate_id": spec.candidate_id,
            "family": spec.family,
            "eligible_for_primary": spec.eligible_for_primary,
            "parameters": spec.parameters,
            "scenes_succeeded": len(successes),
            "hard_gate_pass": hard_gate,
            "errors": [
                {"scene_id": record["scene_id"], "error": record["error"]}
                for record in records
                if record["status"] != "ok"
            ],
        }
        if successes:
            for metric in (
                "skeleton_precision",
                "skeleton_recall",
                "skeleton_f1",
                "compelled_orientation_precision",
                "compelled_orientation_recall",
                "unresolved_edge_rate",
                "cpdag_shd",
                "runtime_seconds",
            ):
                summary[f"macro_{metric}"] = mean(successes, metric)
        aggregate.append(summary)
    return sorted(aggregate, key=lambda item: item["candidate_id"])


def finalist_order(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -int(candidate["hard_gate_pass"]),
        -int(candidate["eligible_for_primary"]),
        -float(candidate.get("macro_skeleton_f1", 0.0)),
        float(candidate.get("macro_cpdag_shd", float("inf"))),
        -float(candidate.get("macro_compelled_orientation_precision", 0.0)),
        candidate["candidate_id"],
    )


def final_order(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -float(candidate.get("macro_skeleton_f1", 0.0)),
        float(candidate.get("macro_cpdag_shd", float("inf"))),
        -float(candidate.get("macro_compelled_orientation_precision", 0.0)),
        -float(candidate.get("mean_skeleton_jaccard", 0.0)),
        -float(candidate.get("mean_endpoint_state_agreement", 0.0)),
        float(candidate.get("macro_runtime_seconds", float("inf"))),
        candidate["candidate_id"],
    )


def run_full_grid(
    backend: TetradBackend,
    source_root: Path,
    scene_ids: list[str],
    specs: list[CandidateSpec],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for scene_id in scene_ids:
        scene_data = load_scene_data(source_root, scene_id)
        java_data = backend.to_java_dataset(scene_data)
        oracle = load_oracle_dag_for_dev_scoring(
            source_root, scene_id, scene_data.anonymous_names
        )
        for spec in specs:
            base = {
                "record_type": "full",
                "scene_id": scene_id,
                "candidate_id": spec.candidate_id,
                "family": spec.family,
                "eligible_for_primary": spec.eligible_for_primary,
                "parameters": spec.parameters,
            }
            try:
                graph, runtime = backend.run(java_data, spec)
                rerun, rerun_runtime = backend.run(java_data, spec)
                projection = consistent_extension(graph)
                metrics = cpdag_metrics(graph, oracle)
                records.append(
                    {
                        **base,
                        "status": "ok",
                        "graph": graph.to_dict(),
                        "projected_dag": projection.to_dict(),
                        "runtime_seconds": round(runtime, 6),
                        "rerun_runtime_seconds": round(rerun_runtime, 6),
                        "deterministic_rerun_match": graph == rerun,
                        "consistent_extension_valid": True,
                        **metrics,
                    }
                )
            except Exception as error:  # record every preregistered failure
                records.append(
                    {
                        **base,
                        "status": "error",
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
    return sorted(records, key=lambda item: (item["scene_id"], item["candidate_id"]))


def run_stability(
    backend: TetradBackend,
    source_root: Path,
    scene_ids: list[str],
    finalists: list[CandidateSpec],
    full_records: list[dict[str, Any]],
    global_seed: int,
    replications: int,
) -> list[dict[str, Any]]:
    base_graphs = {
        (record["scene_id"], record["candidate_id"]): graph_from_dict(
            record["graph"]
        )
        for record in full_records
        if record["status"] == "ok"
    }
    records: list[dict[str, Any]] = []
    for scene_id in scene_ids:
        for replication in range(replications):
            indices = deterministic_half_sample_indices(
                16000, global_seed, scene_id, replication
            )
            index_hash = hashlib.sha256(
                ",".join(map(str, indices)).encode("ascii")
            ).hexdigest().upper()
            scene_data = load_scene_data(source_root, scene_id, indices)
            java_data = backend.to_java_dataset(scene_data)
            for spec in finalists:
                base = {
                    "record_type": "stability",
                    "scene_id": scene_id,
                    "candidate_id": spec.candidate_id,
                    "replication": replication,
                    "rows": len(indices),
                    "row_index_sha256": index_hash,
                }
                try:
                    graph, runtime = backend.run(java_data, spec)
                    stability = graph_stability(
                        base_graphs[(scene_id, spec.candidate_id)], graph
                    )
                    records.append(
                        {
                            **base,
                            "status": "ok",
                            "graph": graph.to_dict(),
                            "runtime_seconds": round(runtime, 6),
                            **stability,
                        }
                    )
                except Exception as error:
                    records.append(
                        {
                            **base,
                            "status": "error",
                            "error": f"{type(error).__name__}: {error}",
                        }
                    )
    return sorted(
        records,
        key=lambda item: (
            item["scene_id"],
            item["candidate_id"],
            item["replication"],
        ),
    )


def attach_stability(
    aggregate: list[dict[str, Any]], stability_records: list[dict[str, Any]]
) -> None:
    for candidate in aggregate:
        records = [
            record
            for record in stability_records
            if record["candidate_id"] == candidate["candidate_id"]
            and record["status"] == "ok"
        ]
        attempted = [
            record
            for record in stability_records
            if record["candidate_id"] == candidate["candidate_id"]
        ]
        if attempted:
            candidate["stability_runs_succeeded"] = len(records)
            candidate["stability_runs_expected"] = len(attempted)
            if records:
                candidate["mean_skeleton_jaccard"] = mean(
                    records, "skeleton_jaccard"
                )
                candidate["mean_endpoint_state_agreement"] = mean(
                    records, "endpoint_state_agreement"
                )


def select_candidate(
    aggregate: list[dict[str, Any]], finalist_count: int
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    eligible = [
        candidate
        for candidate in aggregate
        if candidate["eligible_for_primary"] and candidate["hard_gate_pass"]
    ]
    finalists = sorted(eligible, key=finalist_order)[:finalist_count]
    guarded = [
        candidate
        for candidate in finalists
        if candidate.get("macro_skeleton_f1", 0.0) >= 0.50
        and candidate.get("macro_compelled_orientation_precision", 0.0) >= 0.50
        and candidate.get("mean_skeleton_jaccard", 0.0) >= 0.50
        and candidate.get("stability_runs_succeeded")
        == candidate.get("stability_runs_expected")
    ]
    selected = sorted(guarded, key=final_order)[0] if guarded else None
    return finalists, selected


def generate(args: argparse.Namespace) -> dict[str, Any]:
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if config["experiment"]["status"] != "preregistered_before_dev_oracle_scoring":
        raise ValueError("T05 config is not marked as preregistered")
    expected_split_hash = config["scope"]["split_manifest_sha256"]
    if file_sha256(args.split_manifest) != expected_split_hash:
        raise ValueError("Frozen split hash differs from the preregistration")
    split = json.loads(args.split_manifest.read_text(encoding="utf-8"))
    scene_ids = split["cohorts"]["graph"]["dev_ids"]
    if scene_ids != config["scope"]["expected_scene_ids"]:
        raise ValueError("Development IDs differ from the preregistration")

    backend_config = config["backend"]
    backend = TetradBackend(args.jar, backend_config["jar_sha256"])
    specs = expand_candidates(config)
    full_records = run_full_grid(backend, args.source_root, scene_ids, specs)
    aggregate = aggregate_candidates(specs, full_records)

    finalist_count = config["dev_metrics"]["stability"]["finalist_count"]
    prelim = sorted(
        [
            candidate
            for candidate in aggregate
            if candidate["eligible_for_primary"] and candidate["hard_gate_pass"]
        ],
        key=finalist_order,
    )[:finalist_count]
    spec_by_id = {spec.candidate_id: spec for spec in specs}
    finalist_specs = [spec_by_id[item["candidate_id"]] for item in prelim]
    stability_records = run_stability(
        backend,
        args.source_root,
        scene_ids,
        finalist_specs,
        full_records,
        config["experiment"]["seed"],
        config["dev_metrics"]["stability"]["replicates_per_scene_for_finalists"],
    )
    attach_stability(aggregate, stability_records)
    finalists, selected = select_candidate(aggregate, finalist_count)

    all_records = full_records + stability_records
    graph_text = canonical_jsonl(all_records)
    args.graph_output.parent.mkdir(parents=True, exist_ok=True)
    args.graph_output.write_text(graph_text, encoding="utf-8", newline="\n")

    verdict = selected is not None
    manifest = {
        "manifest_version": 1,
        "task": "T05",
        "status": "complete",
        "p0_scd_ready": verdict,
        "reason": (
            "A preregistered basis-function candidate passed all validity, "
            "determinism, structural-quality, stability, and runtime gates."
            if verdict
            else "No preregistered assumption-eligible candidate passed every "
            "validity, structural-quality, stability, and runtime gate."
        ),
        "scope": {
            "scene_role": "graph_dev_only",
            "scene_ids": scene_ids,
            "holdout_accessed": False,
            "dev_oracle_use": "structural_scoring_after_preregistration_only",
            "downstream_reasoner_used": False,
        },
        "pins": {
            "config": args.config.as_posix(),
            "config_sha256": file_sha256(args.config),
            "frozen_split": args.split_manifest.as_posix(),
            "frozen_split_sha256": expected_split_hash,
            "py_tetrad_commit": backend_config["source_commit"],
            "tetrad_jar_implementation_version": backend_config[
                "jar_implementation_version"
            ],
            "tetrad_jar_sha256": backend.jar_sha256,
            "java": str(__import__("jpype").JClass("java.lang.System").getProperty("java.version")),
            "python": platform.python_version(),
        },
        "data_view": config["data_view"],
        "assumptions_common": config["assumptions_common"],
        "hard_gates": config["hard_gates"],
        "selection_rule": config["selection"],
        "candidate_count": len(specs),
        "full_runs": len(full_records),
        "stability_runs": len(stability_records),
        "candidate_summaries": aggregate,
        "finalists": [candidate["candidate_id"] for candidate in finalists],
        "selected": selected,
        "projection": config["projection"],
        "artifacts": {
            "dev_graphs": args.graph_output.as_posix(),
            "dev_graphs_records": len(all_records),
            "dev_graphs_sha256": text_sha256(graph_text),
        },
    }
    manifest_text = canonical_json(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(manifest_text, encoding="utf-8", newline="\n")
    return manifest


def check(args: argparse.Namespace) -> None:
    manifest = json.loads(args.output.read_text(encoding="utf-8"))
    if file_sha256(args.config) != manifest["pins"]["config_sha256"]:
        raise ValueError("T05 config hash mismatch")
    if file_sha256(args.split_manifest) != manifest["pins"]["frozen_split_sha256"]:
        raise ValueError("Frozen split hash mismatch")
    graph_hash = file_sha256(args.graph_output)
    if graph_hash != manifest["artifacts"]["dev_graphs_sha256"]:
        raise ValueError("T05 dev graph artifact hash mismatch")
    backend = TetradBackend(args.jar, manifest["pins"]["tetrad_jar_sha256"])
    if manifest["selected"] is not None:
        candidate_id = manifest["selected"]["candidate_id"]
        config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
        spec = {
            item.candidate_id: item for item in expand_candidates(config)
        }[candidate_id]
        stored = {
            record["scene_id"]: graph_from_dict(record["graph"])
            for record in (
                json.loads(line)
                for line in args.graph_output.read_text(encoding="utf-8").splitlines()
            )
            if record["record_type"] == "full"
            and record["candidate_id"] == candidate_id
            and record["status"] == "ok"
        }
        for scene_id in manifest["scope"]["scene_ids"]:
            data = load_scene_data(args.source_root, scene_id)
            graph, _ = backend.run(backend.to_java_dataset(data), spec)
            if graph != stored[scene_id]:
                raise ValueError(f"Selected graph rerun mismatch: {scene_id}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--jar", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/t05_scd_selection.yaml")
    )
    parser.add_argument(
        "--split-manifest",
        type=Path,
        default=Path("data/manifests/p0_frozen_split.json"),
    )
    parser.add_argument(
        "--graph-output",
        type=Path,
        default=Path("data/manifests/t05_dev_graphs.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/manifests/p0_scd_selection.json"),
    )
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    parsed_args = parse_args()
    if parsed_args.check:
        check(parsed_args)
        print("T05 audit check passed")
    else:
        result = generate(parsed_args)
        print(
            canonical_json(
                {
                    "p0_scd_ready": result["p0_scd_ready"],
                    "selected": (
                        result["selected"]["candidate_id"]
                        if result["selected"]
                        else None
                    ),
                    "finalists": result["finalists"],
                    "full_runs": result["full_runs"],
                    "stability_runs": result["stability_runs"],
                }
            ),
            end="",
        )
