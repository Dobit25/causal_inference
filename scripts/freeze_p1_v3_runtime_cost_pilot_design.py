from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import yaml

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v3_runtime_cost_pilot_design.yaml"
MANIFEST = ROOT / "data/manifests/p1_v3_runtime_cost_pilot_design.json"
AUDIT = ROOT / "data/manifests/p1_v3_runtime_cost_pilot_design_audit.json"
REPORT = ROOT / "reports/p1_v3_runtime_cost_pilot_design.md"


def canonical_line(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _sum(values: dict) -> int:
    return sum(int(value) for value in values.values())


def validate(config: dict) -> dict[str, int]:
    parent = config["parent"]
    dependencies = (
        (ROOT / parent["audit"], parent["audit_sha256"]),
        (ROOT / parent["successor_conformance_config"], parent["successor_conformance_config_sha256"]),
        (ROOT / parent["evidence_selective_protocol"], parent["evidence_selective_protocol_sha256"]),
    )
    for path, expected in dependencies:
        if sha256(path) != expected:
            raise RuntimeError(f"dependency hash mismatch: {path.relative_to(ROOT)}")
    parent_audit = json.loads(dependencies[0][0].read_text(encoding="utf-8"))
    if parent_audit["authorization"]["next_action"] != config["task"]:
        raise RuntimeError("parent audit does not authorize this offline design")

    panel = config["synthetic_panel"]
    scene_count = int(panel["scene_count"])
    for name in ("node_count", "primary_motif", "noise_family", "query_stratum"):
        if _sum(panel[name]) != scene_count:
            raise RuntimeError(f"synthetic panel marginal does not sum to {scene_count}: {name}")
    if panel["scene_ids_materialized_now"]:
        raise RuntimeError("offline design cannot materialize pilot IDs")

    schedule = config["pilot_schedule"]
    boss = schedule["bootstrap_boss"]
    measured_fits = int(boss["measured_scenes"]) * int(boss["repetitions_per_scene"])
    if measured_fits != int(boss["measured_fits"]):
        raise RuntimeError("Bootstrap-BOSS fit arithmetic mismatch")
    semantic = schedule["semantic_api"]
    logical_calls = (
        int(semantic["sampled_scenes"])
        * int(semantic["story_variants"])
        * int(semantic["prompt_variants"])
    )
    if logical_calls != int(semantic["planned_logical_calls"]):
        raise RuntimeError("semantic call arithmetic mismatch")
    gate = config["feasibility_gates"]["bootstrap_boss"]
    minimum_success = math.ceil(measured_fits * (1 - float(gate["maximum_failure_rate"])))
    if int(gate["minimum_successful_measured_fits"]) < minimum_success:
        raise RuntimeError("BOSS success gate is weaker than maximum failure-rate gate")

    full = config["full_study_projection"]
    if int(full["bootstrap_boss_fits"]) != int(full["successor_scenes"]) * int(boss["study_repetitions_remain"]):
        raise RuntimeError("full Bootstrap-BOSS projection mismatch")
    expected_calls = int(full["successor_scenes"]) * int(semantic["story_variants"]) * int(semantic["prompt_variants"])
    if int(full["semantic_logical_calls"]) != expected_calls:
        raise RuntimeError("full semantic-call projection mismatch")

    boundary = config["evidence_boundary"]
    forbidden_nonzero = (
        "synthetic_pilot_scenes_materialized", "observation_rows_generated",
        "bootstrap_or_boss_runs", "semantic_api_calls", "real_successor_scenes_generated",
    )
    if any(int(boundary[key]) != 0 for key in forbidden_nonzero):
        raise RuntimeError("offline design evidence boundary was crossed")
    if boundary["historical_cohorts_accessed"] or boundary["final_holdout_accessed"]:
        raise RuntimeError("offline design accessed a protected cohort")
    authorization = config["authorization_after_pass"]
    forbidden_authorizations = (
        "pilot_execution", "successor_cohort_generation", "study_scene_bootstrap_execution",
        "semantic_api_calls", "final_holdout_access",
    )
    if any(authorization[key] for key in forbidden_authorizations):
        raise RuntimeError("design improperly authorizes execution")
    if not config["cost_accounting"]["pricing_not_frozen_in_offline_design"]:
        raise RuntimeError("offline design must not claim that current pricing was verified")
    return {
        "synthetic_panel_scenes_planned": scene_count,
        "synthetic_panel_scenes_materialized": 0,
        "generator_measurements_planned": int(schedule["generator"]["scenes"]),
        "generator_replays_planned": int(schedule["generator"]["deterministic_replays"]),
        "boss_warmup_fits_planned": int(boss["warmup_fits"]),
        "boss_measured_fits_planned": measured_fits,
        "semantic_logical_calls_planned": logical_calls,
        "full_successor_scenes_projected": int(full["successor_scenes"]),
        "full_boss_fits_projected": int(full["bootstrap_boss_fits"]),
        "full_semantic_calls_projected": int(full["semantic_logical_calls"]),
        "executions_performed": 0,
    }


def build() -> tuple[bytes, bytes, bytes]:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    counts = validate(config)
    parent_paths = (
        ROOT / config["parent"]["audit"],
        ROOT / config["parent"]["successor_conformance_config"],
        ROOT / config["parent"]["evidence_selective_protocol"],
    )
    manifest = {
        "schema_version": "fourgraph.p1_v3_runtime_cost_pilot_design_manifest.v1",
        "task": config["task"],
        "status": config["status"],
        "purpose": config["purpose"],
        "synthetic_panel": config["synthetic_panel"],
        "pilot_schedule": config["pilot_schedule"],
        "cost_accounting": config["cost_accounting"],
        "full_study_projection": config["full_study_projection"],
        "feasibility_gates": config["feasibility_gates"],
        "preflight_requirements": config["preflight_requirements"],
        "result_boundary": config["result_boundary"],
        "counts": counts,
        "evidence_boundary": config["evidence_boundary"],
        "authorization_after_pass": config["authorization_after_pass"],
    }
    manifest_bytes = canonical_line(manifest)
    report = f"""# P1-v3 runtime/cost pilot — frozen offline design

This artifact designs an engineering feasibility pilot; it does not execute one. The future pilot uses {counts['synthetic_panel_scenes_planned']} synthetic-only scenes, measures {counts['boss_measured_fits_planned']} Bootstrap-BOSS fits after {counts['boss_warmup_fits_planned']} excluded warm-ups, and samples {counts['semantic_logical_calls_planned']} whole-graph semantic calls. It will project the frozen study envelope of {counts['full_successor_scenes_projected']} scenes, {counts['full_boss_fits_projected']} Bootstrap-BOSS fits, and {counts['full_semantic_calls_projected']} semantic calls.

The design separates engineering feasibility from scientific evidence. Pilot graphs cannot estimate edge stability, pilot responses cannot establish semantic reliability, pilot scenes cannot enter any study cohort, and no threshold or hypothesis may change from pilot outcomes. Runtime is projected with scene-stratified median, p95 and leave-one-scene-out ranges, with a 1.25 reserve multiplier.

Current API prices were deliberately not fetched or invented offline. Before execution, a separate preflight must pin the official rate card, model snapshot, remaining approved budget, machine/software environment, exact synthetic IDs, runner hashes and disk capacity. The pilot has a hard API cost cap of USD {config['cost_accounting']['pilot_hard_cost_cap_usd']:.2f}.

All gates must pass: deterministic generation/replay, at least {config['feasibility_gates']['bootstrap_boss']['minimum_successful_measured_fits']}/{counts['boss_measured_fits_planned']} measured BOSS fits with failure rate at most 1%, projected single-worker runtime with reserve at most 168 hours, all {counts['semantic_logical_calls_planned']} logical API cases complete, final schema success 100%, first-attempt schema success at least 95%, retry rate at most 5%, exact snapshot 100%, cost/storage within registered limits, and no unclassified terminal failure.

No pilot ID, observation row, Bootstrap/BOSS fit or semantic API response was created. The only next authorized action is another offline step: freeze the executable preflight. Explicit user authorization is still required before any pilot execution.
""".encode("utf-8")
    dependencies = [CONFIG, *parent_paths]
    outputs = ((MANIFEST, manifest_bytes), (REPORT, report))
    audit = {
        "schema_version": "fourgraph.p1_v3_runtime_cost_pilot_design_audit.v1",
        "task": config["task"],
        "dependencies": [
            {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path)}
            for path in dependencies
        ],
        "implementation": {
            "path": Path(__file__).relative_to(ROOT).as_posix(),
            "sha256": sha256(Path(__file__)),
        },
        "outputs": [
            {"path": path.relative_to(ROOT).as_posix(), "bytes": len(content), "sha256": sha256_hex(content)}
            for path, content in outputs
        ],
        "counts": counts,
        "evidence_boundary": config["evidence_boundary"],
        "authorization": config["authorization_after_pass"],
        "verdict": {
            "offline_design_frozen": True,
            "arithmetic_validated": True,
            "feasibility_gates_preregistered": True,
            "current_rate_card_frozen": False,
            "pilot_execution_authorized": False,
            "successor_generation_authorized": False,
            "bootstrap_boss_authorized": False,
            "semantic_api_authorized": False,
            "final_holdout_authorized": False,
        },
    }
    return manifest_bytes, canonical_line(audit), report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    built = build()
    paths = (MANIFEST, AUDIT, REPORT)
    if args.check:
        for path, expected in zip(paths, built):
            if not path.exists() or path.read_bytes() != expected:
                raise SystemExit(f"Mismatch: {path.relative_to(ROOT)}")
        print("P1-v3 runtime/cost pilot design reproduces byte-for-byte")
        return 0
    for path, content in zip(paths, built):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    print("P1-v3 runtime/cost pilot design frozen; execution remains forbidden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
