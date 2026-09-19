from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import yaml
from scipy.stats import beta, binom


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v3_power_cohort_design.yaml"
POWER = ROOT / "data/manifests/p1_v3_prospective_power.json"
COHORTS = ROOT / "data/manifests/p1_v3_cohort_design.json"
AUDIT = ROOT / "data/manifests/p1_v3_power_cohort_design_audit.json"
REPORT = ROOT / "reports/p1_v3_power_cohort_design.md"


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def json_bytes(value: object) -> bytes:
    return canonical_json(value) + b"\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def upper_bound(errors: int, total: int, tail: float) -> float:
    return 1.0 if errors == total else float(beta.ppf(1 - tail, errors + 1, total - errors))


def lower_bound(successes: int, total: int, tail: float) -> float:
    return 0.0 if successes == 0 else float(beta.ppf(tail, successes, total - successes + 1))


def maximum_certifiable_errors(total: int, alpha: float, tail: float) -> int:
    return max(
        (errors for errors in range(total + 1) if upper_bound(errors, total, tail) <= alpha),
        default=-1,
    )


def minimum_coverage_successes(total: int, target: float, tail: float) -> int:
    return min(
        (successes for successes in range(total + 1) if lower_bound(successes, total, tail) >= target),
        default=total + 1,
    )


def availability_simulation(config: dict) -> list[dict]:
    design = config["power_design"]
    rng = np.random.Generator(np.random.PCG64DXSM(int(design["seed"])))
    repetitions = int(design["monte_carlo_repetitions"])
    values = np.asarray(design["directions_per_contributing_scene"]["values"], dtype=np.int64)
    probabilities = np.asarray(
        design["directions_per_contributing_scene"]["probabilities"], dtype=float
    )
    if not math.isclose(float(probabilities.sum()), 1.0, abs_tol=1e-12):
        raise RuntimeError("direction-count probabilities must sum to one")
    rows: list[dict] = []
    for role in ("calibration", "validation"):
        requirements = design[role]
        scene_key = (
            "minimum_independent_contributing_scenes_per_group"
            if role == "calibration"
            else "minimum_independent_contributing_scenes_per_candidate"
        )
        edge_key = (
            "minimum_published_directions_per_group"
            if role == "calibration"
            else "minimum_answered_edges_per_candidate"
        )
        for scene_count in design["candidate_scene_counts"]:
            for prevalence in design["group_or_candidate_scene_prevalence"]:
                contributing_all = np.empty(repetitions, dtype=np.int64)
                edges_all = np.empty(repetitions, dtype=np.int64)
                passed_all = np.empty(repetitions, dtype=np.bool_)
                for start in range(0, repetitions, 2000):
                    stop = min(start + 2000, repetitions)
                    size = stop - start
                    active = rng.random((size, scene_count)) < prevalence
                    contributions = rng.choice(values, size=(size, scene_count), p=probabilities)
                    contributing = active.sum(axis=1)
                    edges = (active * contributions).sum(axis=1)
                    contributing_all[start:stop] = contributing
                    edges_all[start:stop] = edges
                    passed_all[start:stop] = (
                        (contributing >= int(requirements[scene_key]))
                        & (edges >= int(requirements[edge_key]))
                    )
                rows.append(
                    {
                        "role": role,
                        "scene_count": int(scene_count),
                        "contribution_prevalence": float(prevalence),
                        "availability_probability": float(passed_all.mean()),
                        "median_contributing_scenes": int(np.median(contributing_all)),
                        "median_published_directions": int(np.median(edges_all)),
                    }
                )
    return rows


def build_power(config: dict) -> dict:
    family = config["familywise_risk"]
    design = config["power_design"]
    alpha = float(family["target_error_alpha"])
    calibration_n = int(
        design["calibration"]["minimum_independent_contributing_scenes_per_group"]
    )
    validation_n = int(
        design["validation"]["minimum_independent_contributing_scenes_per_candidate"]
    )
    calibration_bonferroni = float(family["allocation"]["semantic_calibration"]) / int(
        family["semantic_groups"]
    )
    validation_bonferroni = float(family["allocation"]["threshold_validation"]) / int(
        family["threshold_candidates"]
    )
    calibration_tail = calibration_bonferroni / math.e
    validation_tail = validation_bonferroni / math.e
    calibration_max = maximum_certifiable_errors(calibration_n, alpha, calibration_tail)
    validation_max = maximum_certifiable_errors(validation_n, alpha, validation_tail)
    coverage_target = float(design["validation"]["coverage_lower_bound"])
    coverage_minimum = minimum_coverage_successes(
        validation_n, coverage_target, validation_tail
    )
    error_rates = [float(value) for value in design["sensitivity_error_rates"]]
    risk_power = {
        "semantic_calibration": {
            "independent_scenes": calibration_n,
            "family_size": int(family["semantic_groups"]),
            "one_sided_tail_after_bonferroni_and_bentkus": calibration_tail,
            "maximum_certifiable_error_equivalents": calibration_max,
            "upper_bound_at_maximum": upper_bound(
                calibration_max, calibration_n, calibration_tail
            ),
            "power_by_true_error": {
                f"{rate:.3f}": float(binom.cdf(calibration_max, calibration_n, rate))
                for rate in error_rates
            },
        },
        "threshold_validation": {
            "independent_scenes": validation_n,
            "family_size": int(family["threshold_candidates"]),
            "one_sided_tail_after_bonferroni_and_bentkus": validation_tail,
            "maximum_certifiable_error_equivalents": validation_max,
            "upper_bound_at_maximum": upper_bound(
                validation_max, validation_n, validation_tail
            ),
            "power_by_true_error": {
                f"{rate:.3f}": float(binom.cdf(validation_max, validation_n, rate))
                for rate in error_rates
            },
        },
    }
    coverage = {
        "independent_scenes": validation_n,
        "target_lower_bound": coverage_target,
        "minimum_coverage_success_equivalents": coverage_minimum,
        "lower_bound_at_minimum": lower_bound(
            coverage_minimum, validation_n, validation_tail
        ),
        "power_by_true_coverage": {
            f"{rate:.2f}": float(binom.sf(coverage_minimum - 1, validation_n, rate))
            for rate in (0.20, 0.25, 0.30, 0.35, 0.40)
        },
    }
    return {
        "schema_version": "fourgraph.p1_v3_prospective_power.v1",
        "design_inputs_not_observed_results": True,
        "selected_scene_counts": {
            "method_development": config["cohorts"]["method_development"]["scene_count"],
            "semantic_calibration": config["cohorts"]["semantic_calibration"]["scene_count"],
            "threshold_validation": config["cohorts"]["threshold_validation"]["scene_count"],
        },
        "familywise_method": family["correction"],
        "bentkus_e_factor": math.e,
        "risk_power": risk_power,
        "coverage_power": coverage,
        "availability_simulation": availability_simulation(config),
        "assumption_boundary": {
            "scene_losses_are_independent_across_generated_scenes": True,
            "within_scene_edges_are_never_counted_as_independent": True,
            "power_is_conditional_on_registered_error_and_prevalence_scenarios": True,
            "power_is_not_a_study_result": True,
            "insufficient_group_information_means_not_certified": True,
        },
    }


def role_record(name: str, row: dict) -> dict:
    count = int(row["scene_count"])
    start = int(row["scene_number_start"])
    return {
        "role": name,
        "scene_count": count,
        "namespace": row["namespace"],
        "reserved_scene_number_range": [start, start + count],
        "master_seed": row["master_seed"],
        "scene_ids_materialized": False,
        "scenes_generated": 0,
        **{
            key: value
            for key, value in row.items()
            if key
            not in {"scene_count", "namespace", "scene_number_start", "master_seed", "role"}
        },
    }


def build_cohorts(config: dict, power_bytes: bytes) -> dict:
    configured = config["cohorts"]
    roles = {
        name: role_record(name, configured[name])
        for name in ("method_development", "semantic_calibration", "threshold_validation")
    }
    roles["existing_final_holdout"] = configured["existing_final_holdout"]
    ranges = [set(range(*roles[name]["reserved_scene_number_range"])) for name in roles if name != "existing_final_holdout"]
    if any(ranges[i] & ranges[j] for i in range(len(ranges)) for j in range(i + 1, len(ranges))):
        raise RuntimeError("reserved successor ranges overlap")
    total = sum(roles[name]["scene_count"] for name in roles if name != "existing_final_holdout")
    if total != int(configured["total_new_scenes_planned"]):
        raise RuntimeError("successor scene total mismatch")
    return {
        "schema_version": "fourgraph.p1_v3_cohort_design.v1",
        "status": "design_frozen_not_materialized",
        "cohorts_materialized": False,
        "scene_ids_materialized": False,
        "new_scene_count": total,
        "roles": roles,
        "disjointness": configured["disjointness"],
        "stratification": config["stratification"],
        "stage_boundaries": config["stage_boundaries"],
        "power_requirements": config["power_design"],
        "resource_envelope": config["prospective_resource_envelope"],
        "power_manifest_sha256": sha256_bytes(power_bytes),
        "generation_authorized": False,
        "final_holdout_access_authorized": False,
    }


def validate(config: dict, power: dict, cohorts: dict) -> None:
    target = float(config["power_design"]["target_power"])
    for role in ("semantic_calibration", "threshold_validation"):
        if power["risk_power"][role]["power_by_true_error"]["0.010"] < target:
            raise RuntimeError(f"{role} risk power is below target")
    if power["coverage_power"]["power_by_true_coverage"]["0.30"] < target:
        raise RuntimeError("coverage power is below target")
    selected = {
        "calibration": config["cohorts"]["semantic_calibration"]["scene_count"],
        "validation": config["cohorts"]["threshold_validation"]["scene_count"],
    }
    for role in ("calibration", "validation"):
        prevalence = float(config["power_design"]["availability_design_prevalence"][role])
        row = next(
            item
            for item in power["availability_simulation"]
            if item["role"] == role
            and item["scene_count"] == selected[role]
            and item["contribution_prevalence"] == prevalence
        )
        if row["availability_probability"] < target:
            raise RuntimeError(f"{role} information availability is below target")
    if cohorts["cohorts_materialized"] or cohorts["scene_ids_materialized"]:
        raise RuntimeError("design stage materialized successor data")


def build() -> tuple[bytes, bytes, bytes, bytes]:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    parent = ROOT / config["parent"]["audit"]
    protocol = ROOT / config["protocol"]["path"]
    if sha256(parent) != config["parent"]["audit_sha256"]:
        raise RuntimeError("parent audit hash mismatch")
    if sha256(protocol) != config["protocol"]["sha256"]:
        raise RuntimeError("protocol hash mismatch")
    parent_record = json.loads(parent.read_text(encoding="utf-8"))
    if parent_record["authorization"]["next_action"] != config["task"]:
        raise RuntimeError("parent does not authorize prospective design")

    power = build_power(config)
    power_bytes = json_bytes(power)
    cohorts = build_cohorts(config, power_bytes)
    validate(config, power, cohorts)
    cohort_bytes = json_bytes(cohorts)
    calibration_power = power["risk_power"]["semantic_calibration"]["power_by_true_error"]["0.010"]
    validation_power = power["risk_power"]["threshold_validation"]["power_by_true_error"]["0.010"]
    coverage_power = power["coverage_power"]["power_by_true_coverage"]["0.30"]
    report = f"""# P1-v3 prospective power and independent-cohort design

This design treats scenes—not edges—as the independent split and inference unit. Each contributing scene supplies one bounded loss: its fraction of published directions that are wrong. Directions remain nested within scenes and false-adjacency orientations count as errors. Familywise one-sided Hoeffding–Bentkus tests therefore do not pretend that edges from one scene are independent.

The total failure probability 0.05 is split prospectively: 0.025 for six semantic calibration groups and 0.025 for fifteen threshold candidates. At the minimum independent-scene counts, calibration has {calibration_power:.3f} power and validation has {validation_power:.3f} power to certify a truly 1% error procedure against the 5% ceiling. Coverage power is {coverage_power:.3f} when true coverage is 30% and the required lower bound is 20%. These are design assumptions, not study findings.

The frozen successor roles are 40 method-development scenes, 400 semantic-calibration scenes and 400 one-time threshold-validation scenes. They use separate namespaces and seeds and must match the registered node, motif, noise and query-stratum margins. The old development/P1V cohorts remain historical diagnostics; the existing 80-scene final holdout remains unchanged and sealed.

Calibration may only certify reliability separately for full/partial/ambiguous × Very High/High groups. A group needs at least 280 independent contributing scenes and 560 published directions; otherwise it remains not certified. Validation needs at least 340 independent contributing scenes and 680 answered directions for a candidate, plus familywise risk ≤0.05 and coverage ≥0.20 under the registered tests. It selects maximum coverage only among safe candidates; no safe candidate stops the study before final holdout.

If all successor cohorts are later authorized, the envelope is 168,000 Bootstrap-BOSS runs and 15,120 whole-graph semantic calls. A runtime/cost pilot is mandatory before live execution. This design created no scene or scene ID manifest, ran no Bootstrap/BOSS job, made no API call, and accessed no historical cohort or final holdout.
""".encode("utf-8")
    outputs = ((POWER, power_bytes), (COHORTS, cohort_bytes), (REPORT, report))
    audit = {
        "schema_version": "fourgraph.p1_v3_power_cohort_design_audit.v1",
        "task": config["task"],
        "dependencies": [
            {"path": CONFIG.relative_to(ROOT).as_posix(), "sha256": sha256(CONFIG)},
            {"path": parent.relative_to(ROOT).as_posix(), "sha256": sha256(parent)},
            {"path": protocol.relative_to(ROOT).as_posix(), "sha256": sha256(protocol)},
        ],
        "implementation": {
            "path": Path(__file__).relative_to(ROOT).as_posix(),
            "sha256": sha256(Path(__file__)),
        },
        "outputs": [
            {"path": path.relative_to(ROOT).as_posix(), "bytes": len(content), "sha256": sha256_bytes(content)}
            for path, content in outputs
        ],
        "design": {
            "scene_counts": power["selected_scene_counts"],
            "total_new_scenes_planned": cohorts["new_scene_count"],
            "calibration_minimum_independent_scenes": 280,
            "validation_minimum_independent_scenes": 340,
            "calibration_power_at_one_percent_error": calibration_power,
            "validation_power_at_one_percent_error": validation_power,
            "coverage_power_at_thirty_percent": coverage_power,
        },
        "evidence_boundary": config["evidence_boundary"],
        "authorization": config["authorization_after_pass"],
        "verdict": {
            "prospective_power_complete": True,
            "independent_cohort_roles_frozen": True,
            "cohorts_generated": False,
            "study_execution_authorized": False,
            "semantic_api_calls_authorized": False,
            "final_holdout_authorized": False,
        },
    }
    return power_bytes, cohort_bytes, json_bytes(audit), report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    built = build()
    paths = (POWER, COHORTS, AUDIT, REPORT)
    if args.check:
        for path, expected in zip(paths, built):
            if not path.exists() or path.read_bytes() != expected:
                raise SystemExit(f"Mismatch: {path.relative_to(ROOT)}")
        print("P1-v3 power/cohort design reproduces byte-for-byte")
        return 0
    for path, content in zip(paths, built):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    print("P1-v3 prospective power and independent cohort design frozen offline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
