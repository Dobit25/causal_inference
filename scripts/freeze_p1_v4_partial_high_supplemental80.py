"""Offline design, power and identity freeze for the P1V4 80-scene supplement."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from fourgraph.sequential_evidence import risk_e_value, coverage_e_value
from freeze_p1_v4_stage3_exact_identity_cohort import role_rows, canonical as identity_canonical, digest_bytes

CFG = ROOT / "configs/p1_v4_partial_high_supplemental80_protocol.yaml"
COMPONENTS = ("graph_candidates", "edge_weights", "observations", "query_order", "story_template", "bootstrap_boss")


def cb(obj: Any) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def must(ok: bool, reason: str) -> None:
    if not ok:
        raise RuntimeError(reason)


def source_inventory(cfg: dict[str, Any]) -> dict[str, str]:
    paths = [v["path"] if isinstance(v, dict) else v for v in cfg["historical_inputs"].values()]
    paths += list(cfg["source_contracts"])
    paths += [cfg["identity_allocator"]["sealed_holdout_identity_metadata"]]
    prior = cfg["identity_allocator"]["prior_identity_sources"]
    observed = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "data/manifests").glob("*exact_identit*.jsonl")
                      if p.relative_to(ROOT).as_posix() != cfg["outputs"]["identities"])
    if not (ROOT / cfg["outputs"]["protocol"]).exists():
        must(sorted(prior) == observed, "prior identity inventory incomplete at first freeze")
    paths += prior
    must(len(paths) == len(set(paths)), "duplicate source paths")
    out = {}
    for rel in paths:
        p = ROOT / rel
        must(p.is_file(), f"required frozen source missing: {rel}")
        out[rel] = sha(p)
    for name, pin in cfg["historical_inputs"].items():
        if "sha256" in pin:
            must(out[pin["path"]] == pin["sha256"], f"historical {name} hash drift")
    return dict(sorted(out.items()))


def historical(cfg: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    inputs = cfg["historical_inputs"]
    review, results = (load(ROOT / inputs[k]["path"]) for k in ("review", "results"))
    audit = load(ROOT / inputs["audit"]["path"])
    scorer = load(ROOT / inputs["scorer_config"])
    curves = load(ROOT / inputs["scene_arrays"])
    must(review["decision"] == "STOP_FOR_FUTILITY" and not review["validation_authorized"], "look440 decision drift")
    must(results["status"] == "STOP_FOR_FUTILITY" and audit["status"] == "PASS_ORACLE_SCORING", "look440 audit drift")
    must(audit["oracle_scenes_accessed"] == 440 and results["registered_look"] == 440, "historical scope drift")
    must(results["holdout_access"] == results["validation_access"] == 0, "historical boundary drift")
    wanted = cfg["inference"]
    gates = scorer["sequential_gates"]
    must(wanted["primary_endpoint"] == "partial_high_guardrail_constrained_boss" and scorer["scope"]["primary_parent"] == cfg["scientific_contract"]["primary_parent"], "primary endpoint drift")
    must(gates["high_guardrail"]["minimum_contributing_scenes"] == wanted["high_minimum_contributing_scenes"] == 60, "minimum changed")
    must(math.isclose(gates["high_guardrail"]["error_ceiling"], 1-wanted["high_precision_floor"], abs_tol=1e-12) and gates["high_guardrail"]["error_ceiling"] == 0.1, "high floor changed")
    must(math.isclose(gates["risk"]["error_ceiling"], 1-wanted["overall_precision_floor"], abs_tol=1e-12) and gates["risk"]["error_ceiling"] == 0.05, "precision floor changed")
    must(gates["coverage"]["floor"] == wanted["coverage_floor"] == 0.2, "coverage floor changed")
    must(scorer["scope"]["automatic_agreements"] == cfg["scientific_contract"]["automatic"], "automatic policy drift")
    must(results["conditions"]["Constrained-BOSS"]["variants"]["partial"]["High_guardrail"]["contributing_scenes"] == 53, "historical High count drift")
    for condition in ("Constrained-BOSS", "Constrained-FGES"):
        for variant in ("full", "partial"):
            curve = curves[f"{condition}/{variant}"]
            reported = results["conditions"][condition]["variants"][variant]
            must(len(curve["scene_coverage"]) == 440, "historical curve length drift")
            must(len(curve["high_scene_error"]) == reported["High_guardrail"]["contributing_scenes"], "High curve count drift")
            must(len(curve["scene_error_on_contributing"]) == reported["precision_confidence_sequence"]["contributing_scenes"], "precision curve count drift")
            for key, data, settings in (("High_guardrail", "high_scene_error", gates["high_guardrail"]), ("precision_confidence_sequence", "scene_error_on_contributing", gates["risk"])):
                alpha = settings.get("alpha", settings.get("alpha_per_policy"))
                observed = float(risk_e_value(sum(curve[data]), len(curve[data]), settings["error_ceiling"], settings["alternatives"]))
                must(math.isclose(observed, reported[key]["e_value"], rel_tol=1e-12), f"{condition}/{variant} {key} e replay mismatch")
                must((observed >= 1/alpha) == reported[key]["crosses"], "crossing drift")
            cov = float(coverage_e_value(sum(curve["scene_coverage"]), 440, gates["coverage"]["floor"], gates["coverage"]["alternatives"]))
            must(math.isclose(cov, reported["coverage"]["e_value"], rel_tol=1e-12), "coverage e replay mismatch")
    return review, results, {"gates": gates, "curves": curves}


def identities(cfg: dict[str, Any], inv: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    a = cfg["identity_allocator"]
    base_rows = rows(ROOT / "data/manifests/p1_v4_stage3_exact_identities.jsonl")
    excluded_ids = {row["study_id"] for row in base_rows}
    excluded_scene_ids = {row["contract_scene_id"] for row in base_rows}
    excluded_seeds = {value for row in base_rows for value in row["component_seeds"].values()}
    for rel in inv:
        if rel.endswith(".jsonl") and "exact_identit" in rel and "stage3_exact_identities" not in rel:
            for row in rows(ROOT / rel):
                excluded_ids.add(row.get("study_id", ""))
                if row.get("contract_scene_id"):
                    excluded_scene_ids.add(row["contract_scene_id"])
                excluded_seeds.update(row.get("component_seeds", {}).values())
    split = load(ROOT / a["sealed_holdout_identity_metadata"])
    excluded_ids.update(split["holdout_ids"])
    excluded_scene_ids.update(split["holdout_contract_scene_ids"])
    new = role_rows(a["role"], a)
    for row in new:
        must(set(row["component_seeds"]) == set(COMPONENTS), "component seed schema drift")
        payload = dict(row)
        row["identity_sha256"] = digest_bytes(identity_canonical(payload))
    ids = [r["study_id"] for r in new]
    scenes = [r["contract_scene_id"] for r in new]
    seeds = [x for r in new for x in r["component_seeds"].values()]
    checks = {
        "exact_80_ids_and_one_look": len(new) == 80 and len(set(ids)) == 80 and all(r["first_registered_look"] == 80 and r["included_in_registered_looks"] == [80] for r in new),
        "fixed_namespace_and_scene_number_range": set(ids) == {f"P1V4SH{i:03d}" for i in range(80)} and set(scenes) == {f"scene_{i:06d}" for i in range(263000, 263080)},
        "existing_identity_exclusion": not set(ids) & excluded_ids and not set(scenes) & excluded_scene_ids,
        "unique_component_seeds_and_no_old_seed_reuse": len(set(seeds)) == 480 and not set(seeds) & excluded_seeds,
        "node_marginals": {str(k):sum(r["node_count"] == k for r in new) for k in (5,6,7)} == {str(k):v for k,v in a["targets"]["node_count"].items()},
        "motif_marginals": {k:sum(r["primary_motif"] == k for r in new) for k in a["targets"]["primary_motif"]} == a["targets"]["primary_motif"],
        "noise_marginals": {k:sum(r["noise_family"] == k for r in new) for k in a["targets"]["noise_family"]} == a["targets"]["noise_family"],
        "query_marginals": {k:sum(r["query_stratum"] == k for r in new) for k in a["targets"]["query_stratum"]} == a["targets"]["query_stratum"],
        "no_scene_or_story_materialization": all(not (ROOT / cfg["reserved_paths"][k]).exists() for k in ("generated", "public", "raw")),
    }
    must(all(checks.values()), f"identity audit failed: {checks}")
    return new, {"checks": checks, "excluded_prior_study_ids": len(excluded_ids), "excluded_prior_contract_scene_ids": len(excluded_scene_ids), "prior_identity_source_hashes": {k:v for k,v in inv.items() if "exact_identit" in k or k == a["sealed_holdout_identity_metadata"]}}


def high_power(cfg: dict[str, Any], hist: dict[str, Any]) -> dict[str, Any]:
    pcfg = cfg["power"]
    n = pcfg["repetitions"]
    rng = np.random.Generator(np.random.PCG64DXSM(pcfg["seed"]))
    gates = hist["gates"]["high_guardrail"]
    old_n = 53
    old_sum = sum(hist["curves"]["Constrained-BOSS/partial"]["high_scene_error"])
    must(old_sum == 0, "historical High errors changed")
    grid = []
    for p in pcfg["high_rates"]:
        count = rng.binomial(80, p, size=n)
        for er in pcfg["high_scene_error_rates"]:
            losses = rng.binomial(count, er)
            e = risk_e_value(old_sum + losses, old_n + count, gates["error_ceiling"], gates["alternatives"])
            successes = (old_n + count >= 60) & (e >= 1/gates["alpha"])
            grid.append({"high_scene_rate": p, "high_scene_error_rate": er,
                         "mean_new_high_scenes": round(float(np.mean(count)), 4),
                         "probability_at_least_7_new_high": round(float(np.mean(count >= 7)), 6),
                         "probability_combined_high_guardrail_pass": round(float(np.mean(successes)), 6),
                         "monte_carlo_standard_error": round(math.sqrt(float(np.mean(successes))*(1-float(np.mean(successes)))/n), 6),
                         "fresh_only_mean_high_count": round(float(np.mean(count)), 4)})
    return {"simulation_assumptions_only": True,"replications_per_scenario": n,"grid": grid}


def joint_power(cfg: dict[str, Any], hist: dict[str, Any]) -> dict[str, Any]:
    """Paired empirical scene bootstrap; historical outcomes fixed, fresh errors injected."""
    p = cfg["power"]
    gates = hist["gates"]
    primary = hist["curves"]
    full = primary["Constrained-BOSS/full"]
    part = primary["Constrained-BOSS/partial"]
    n = p["repetitions"]
    rng = np.random.Generator(np.random.PCG64DXSM(p["seed"]+1))
    # High flags are tied to the same scene identities as the published metric record.
    old_ids = load(ROOT / "data/manifests/p1_v4_look440_cumulative_oracle_scoring_checkpoint.json")["exact_scene_ids"]
    must(len(old_ids) == 440 and len(set(old_ids)) == 440, "historical scene order drift")
    by_variant = {"full": set(), "partial": set()}
    for r in rows(ROOT / cfg["historical_inputs"]["scored_records"]):
        if r["condition"] == "Constrained-BOSS" and r["variant"] in by_variant and r["published"] and r["agreement"] == "HIGH":
            by_variant[r["variant"]].add(r["scene_id"])
    must(len(by_variant["full"]) == 122 and len(by_variant["partial"]) == 53, "historical scene High counts drift")
    coverage = {variant: np.asarray(primary[f"Constrained-BOSS/{variant}"]["scene_coverage"], dtype=float) for variant in ("full", "partial")}
    high = {variant: np.asarray([sid in by_variant[variant] for sid in old_ids], dtype=bool) for variant in ("full", "partial")}
    for variant in ("full", "partial"):
        must(np.all(coverage[variant][high[variant]] > 0), "HIGH scene without published edge")
    out = []
    for error_rate in p["empirical_joint_scene_bootstrap_error_rates"]:
        pass_count = 0
        for start in range(0, n, 2000):
            batch = min(2000, n-start)
            samples = rng.integers(0, 440, size=(batch,80))
            gates_all = []
            for variant in ("full", "partial"):
                c = coverage[variant][samples]
                pub = c > 0
                h = high[variant][samples]
                injected_error = rng.random((batch,80)) < error_rate
                old_risk = len(primary[f"Constrained-BOSS/{variant}"]["scene_error_on_contributing"])
                old_high = len(primary[f"Constrained-BOSS/{variant}"]["high_scene_error"])
                high_errors = np.sum(h & injected_error,axis=1)
                risk_errors = np.sum(pub & injected_error,axis=1)
                he = risk_e_value(high_errors, old_high+np.sum(h,axis=1), gates["high_guardrail"]["error_ceiling"], gates["high_guardrail"]["alternatives"])
                re = risk_e_value(risk_errors, old_risk+np.sum(pub,axis=1), gates["risk"]["error_ceiling"], gates["risk"]["alternatives"])
                old_cov = sum(primary[f"Constrained-BOSS/{variant}"]["scene_coverage"])
                ce = coverage_e_value(old_cov+np.sum(c,axis=1), 520, gates["coverage"]["floor"], gates["coverage"]["alternatives"])
                gates_all.append((old_high+np.sum(h,axis=1)>=60) & (he>=1/gates["high_guardrail"]["alpha"]) & (re>=1/gates["risk"]["alpha_per_policy"]) & (ce>=1/gates["coverage"]["alpha_per_policy"]))
            pass_count += int(np.sum(gates_all[0] & gates_all[1]))
        rate = pass_count/n
        out.append({"fresh_scene_error_rate_assumption": error_rate,
                    "joint_full_partial_pass_probability": round(rate,6),
                    "monte_carlo_standard_error": round(math.sqrt(rate*(1-rate)/n),6)})
    return {"simulation_assumptions_only": True, "model": "paired_empirical_scene_resampling_from_frozen_440_plus_scenario_error_injection", "historical_scene_high_counts": {v:len(by_variant[v]) for v in by_variant}, "scenario_results": out}


def null_audit(cfg: dict[str, Any], gates: dict[str, Any]) -> dict[str, Any]:
    """Simulate original always-valid HIGH test from t=0, never condition on the favorable old sample."""
    p = cfg["power"]
    n = p["null_repetitions"]
    rng = np.random.Generator(np.random.PCG64DXSM(p["seed"]+2))
    high_n = np.zeros(n,dtype=np.int32)
    errors = np.zeros(n,dtype=np.int32)
    ever = np.zeros(n,dtype=bool)
    prior = 0
    checkpoints = []
    for look in (120,160,200,240,280,320,360,400,440,520):
        new = rng.binomial(look-prior, 53/440, size=n)
        high_n += new
        errors += rng.binomial(new, gates["high_guardrail"]["error_ceiling"])
        e = risk_e_value(errors, high_n, gates["high_guardrail"]["error_ceiling"], gates["high_guardrail"]["alternatives"])
        crossed = (high_n>=60) & (e>=1/gates["high_guardrail"]["alpha"])
        ever |= crossed
        checkpoints.append({"total_scenes":look,"false_high_certification_rate_cumulative":round(float(np.mean(ever)),6)})
        prior = look
    rate=float(np.mean(ever))
    se=math.sqrt(rate*(1-rate)/n)
    must(rate+3*se <= gates["high_guardrail"]["alpha"]+p["null_monte_carlo_margin"], "null Monte Carlo check failed")
    return {"simulation_assumptions_only":True,"null_high_error_rate":gates["high_guardrail"]["error_ceiling"],"replications":n,"false_high_certification_rate":round(rate,6),"monte_carlo_standard_error":round(se,6),"three_se_upper":round(rate+3*se,6),"theoretical_anytime_upper":gates["high_guardrail"]["alpha"],"registered_checks":checkpoints,"full_family_joint_claim_is_IUT_not_simulated_FWER":True}


def build() -> tuple[dict[Path,bytes],dict[str,Any]]:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    inv = source_inventory(cfg)
    review, results, h = historical(cfg)
    ids, identity_audit = identities(cfg,inv)
    ident_bytes = b"".join(cb(row) for row in ids)
    must(cfg["workload"]["total_statistical_identities"] == 80*206 == sum(v for k,v in cfg["workload"].items() if k.endswith("_fits")), "fit arithmetic changed")
    must(cfg["workload"]["expected_study_semantic_calls"] == 80*2*6, "semantic arithmetic changed")
    prior_usage=load(ROOT / "data/manifests/p1_v4_look440_incremental_mini_semantic_execution_audit.json")["provider_usage"]
    must(all(prior_usage[k] == cfg["workload"]["historical_look440_480_call_usage"][k] for k in ("input_tokens","output_tokens","total_tokens")), "historical usage drift")
    must(prior_usage["reasoning_tokens"] == cfg["workload"]["historical_look440_480_call_usage"]["reasoning_tokens_within_output"], "historical reasoning usage drift")
    must(all(2*prior_usage[k] == cfg["workload"]["empirical_960_call_token_planning_estimate"][k] for k in ("input_tokens","output_tokens","total_tokens")), "planning token arithmetic drift")
    must(2*prior_usage["reasoning_tokens"] == cfg["workload"]["empirical_960_call_token_planning_estimate"]["reasoning_tokens_within_output"], "reasoning token arithmetic drift")
    must(all(value in (0,False) for key,value in cfg["boundaries"].items() if key != "historical_scored_metrics_and_identity_metadata_read") and cfg["boundaries"]["historical_scored_metrics_and_identity_metadata_read"] is True, "offline boundary changed")
    power={"high_gate":high_power(cfg,h),"joint_certification":joint_power(cfg,h),"null_check":null_audit(cfg,h["gates"])}
    central=next(r for r in power["high_gate"]["grid"] if r["high_scene_rate"] == cfg["power"]["high_rates"][2] and r["high_scene_error_rate"] == 0)
    power["planning_verdict"] = "AT_LEAST_80_PERCENT_CENTRAL_ZERO_ERROR_HIGH_GATE" if central["probability_combined_high_guardrail_pass"]>=cfg["power"]["minimum_zero_error_reference_power"] else "LOW_POWER_CENTRAL_ZERO_ERROR_HIGH_GATE_REPORT_AND_REVIEW"
    plan={"schema_version":"fourgraph.p1_v4_partial_high_supplemental80_exact_identity_plan.v1","status":"FROZEN_OFFLINE","task":cfg["task"],"role":cfg["identity_allocator"]["role"],"exact_scene_ids_in_execution_order":[r["study_id"] for r in ids],"master_seed":cfg["identity_allocator"]["master_seed"],"registered_looks":[80],"identities_sha256":hashlib.sha256(ident_bytes).hexdigest().upper(),"identity_audit":identity_audit,"data_or_stories_generated":False,"oracle_or_holdout_access":0,"next_action":"SUPPLEMENTAL_80_MATERIALIZATION_PREFLIGHT_AND_SEPARATE_LIVE_AUTHORIZATION"}
    inference={"schema_version":"fourgraph.p1_v4_partial_high_supplemental80_inference_audit.v1","status":"PASS_OFFLINE_INFERENCE_DESIGN","original_look440_decision":review["decision"],"original_look440_outcome":review["calibration_outcome"],"observed_old_partial_high_scenes":53,"minimum":60,"new_high_scenes_needed":7,"same_betting_components_and_alphas":h["gates"],"continuation_validity":"anytime_e_process_under_registered_conditional_mean_assumptions; original_stop_remains_reported; no new alpha and no fresh-only certification claim","joint_certification_error_control":"intersection-union: if any required null remains true, its own anytime test bounds erroneous joint pass; max per required test alpha 0.025; this is not simultaneous individual interval coverage","limitations":"historical stop was observed before extension size selected; extension is a registered successor confirmation, not retroactive original calibration PASS; stationarity and conditional mean assumptions are scientific assumptions, not empirically proven by null simulation","validation_access":0,"holdout_access":0,"new_oracle_access":0}
    protocol={"schema_version":"fourgraph.p1_v4_partial_high_supplemental80_frozen_protocol.v1","status":"PASS_FROZEN_OFFLINE_DESIGN","task":cfg["task"],"config_sha256":sha(CFG),"implementation_sha256":sha(Path(__file__)),"source_sha256":inv,"historical_look440_decision":review["decision"],"registered_workload":cfg["workload"],"boundaries":cfg["boundaries"],"next_action":plan["next_action"]}
    out=cfg["outputs"]
    body={"protocol":cb(protocol),"identities":ident_bytes,"identity_plan":cb(plan),"inference":cb(inference),"power":cb(power)}
    output_hashes={k:hashlib.sha256(v).hexdigest().upper() for k,v in body.items()}
    audit={"schema_version":"fourgraph.p1_v4_partial_high_supplemental80_freeze_audit.v1","status":"PASS_OFFLINE_FREEZE","config_sha256":sha(CFG),"output_hashes":output_hashes,"source_count":len(inv),"identity_checks":identity_audit["checks"],"historical_look440_decision_preserved":True,"replayed_registered_e_values":True,"simulation_seed":cfg["power"]["seed"],"simulation_repetitions":cfg["power"]["repetitions"],"statistical_fits":0,"semantic_api_calls":0,"new_oracle_access":0,"validation_data_access":0,"holdout_data_access":0}
    report=(
        "# P1V4 Partial High supplemental 80: offline protocol and power freeze\n\n"
        "Status: **PASS_OFFLINE_FREEZE**. The original 440-scene result remains **STOP_FOR_FUTILITY / negative or inconclusive**. This separately registered 80-scene supplement has one terminal look at 80.\n\n"
        f"The primary Constrained-BOSS Partial HIGH gate had 53 contributing scenes; 7 more are needed for its registered minimum of 60. At 53/440 the planning expectation is {central['mean_new_high_scenes']:.2f} new HIGH scenes. Under the optimistic zero-error and constant-rate scenario, simulated probability of passing the combined HIGH gate is **{central['probability_combined_high_guardrail_pass']:.3f}** (Monte Carlo SE {central['monte_carlo_standard_error']:.4f}). This is a planning estimate, not a result or guarantee. The full rate/error grid and joint scenario results are in the power artifact.\n\n"
        "The original e-process is continued by retaining the same mixture components, weights, loss definitions and alpha. There is no reset and no extra alpha allocation. This yields an anytime-valid test under the registered scene-level conditional-mean null; the observed stop at 440 remains part of the record. The fresh 80 scenes are also reported separately as an external check; their precision alone is not called a certified independent replication unless a separate test is registered. Scene strata and historical zero errors do not establish the conditional-mean assumption.\n\n"
        "The final decision requires all original primary Full and Partial risk/coverage/HIGH gates, overlay validity, and the fixed historical Ambiguous diagnostic. False-adjacency orientation is reported as a safety metric. Robustness FGES is reported separately. No scientific method is selected from the robustness result. If all pass, the disposition is PASS_SUPPLEMENTAL_CONFIRMATION and a separate validation authorization must follow; otherwise STOP_SUPPLEMENTAL_NEGATIVE_OR_INCONCLUSIVE. No inspection before the one registered look.\n\n"
        "Exactly 80 new deterministic IDs/seeds and strata are frozen in a separate namespace. Source, identity, and output SHA-256 values are recorded in the audit. Expected workload: 16,480 statistical identities and 960 Full/Partial Mini-medium logical calls, subject to pair-pool and provider preflight. Scaling the last recorded 480-call provider usage gives approximately 1,390,998 total study tokens (618,528 input and 772,470 output, of which 536,086 were reasoning). This is a planning estimate; provider usage in the future run is authoritative. No scene, story, fit, API call, new Oracle read, validation data, or holdout data was touched.\n\n"
        "Method basis: [time-uniform confidence sequences](https://arxiv.org/abs/1810.08240) and [safe anytime-valid inference](https://ir.cwi.nl/pub/33561/).\n"
    ).encode("utf-8")
    artifacts={ROOT/out[k]:v for k,v in body.items()}
    artifacts[ROOT/out["audit"]]=cb(audit)
    artifacts[ROOT/out["report"]]=report
    return artifacts,audit


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args()
    artifacts,audit=build()
    for path,content in artifacts.items():
        if args.check:
            must(path.is_file() and path.read_bytes()==content, f"byte-for-byte replay drift: {path}")
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            must(not path.exists() or path.read_bytes()==content, f"existing artifact drift: {path}")
            if not path.exists():path.write_bytes(content)
    power=load(ROOT/"data/manifests/p1_v4_partial_high_supplemental80_power.json")
    central=next(row for row in power["high_gate"]["grid"] if row["high_scene_rate"] == 53/440 and row["high_scene_error_rate"] == 0)
    print(json.dumps({"status":audit["status"],"identity_count":80,"central_high_gate_power":central["probability_combined_high_guardrail_pass"],"replay":args.check,"semantic_api_calls":0,"new_oracle_access":0}))


if __name__=="__main__":
    main()
