"""Freeze the confirmed P1V4 policy and audit the sealed validation look 160.

Offline only: reads previously frozen manifests, never materializes scenes or
opens validation Oracle commitments.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_post_supplemental_policy_validation_freeze.yaml"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def build() -> tuple[dict, dict, str]:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    checks = {}
    for name, source in config["sources"].items():
        path = ROOT / source["path"]
        checks[f"hash_{name}"] = path.is_file() and digest(path) == source["sha256"]
    if not all(checks.values()):
        raise RuntimeError(f"Source hash mismatch: {[k for k, ok in checks.items() if not ok]}")

    results = json.loads((ROOT / config["sources"]["supplemental_results"]["path"]).read_text(encoding="utf-8"))
    scoring_audit = json.loads((ROOT / config["sources"]["supplemental_audit"]["path"]).read_text(encoding="utf-8"))
    response_audit = json.loads((ROOT / config["sources"]["supplemental_response_audit"]["path"]).read_text(encoding="utf-8"))
    old_review = json.loads((ROOT / config["sources"]["original_look440_review"]["path"]).read_text(encoding="utf-8"))
    primary = results["combined_520"]["Constrained-BOSS"]
    checks.update({
        "supplemental_pass": results["status"] == scoring_audit["decision"] == "PASS_SUPPLEMENTAL_CONFIRMATION",
        "original_stop_preserved": old_review["decision"] == results["historical_look440_decision_unchanged"] == "STOP_FOR_FUTILITY",
        "response_freeze_pass": response_audit["status"] == "PASS" and response_audit["oracle_access"] == 0,
        "supplemental_oracle_scope": scoring_audit["oracle_scenes_accessed"] == 80 and scoring_audit["holdout_access"] == 0,
        "primary_full_pass": primary["variants"]["full"]["registered_gate_pass"],
        "primary_partial_pass": primary["variants"]["partial"]["registered_gate_pass"],
        "primary_ambiguous_pass": primary["ambiguous_abstention_diagnostic"]["pass"],
        "partial_high_count": primary["variants"]["partial"]["High_guardrail"]["contributing_scenes"] >= 60,
        "robustness_not_certified": not results["combined_520"]["Constrained-FGES"]["variants"]["partial"]["registered_gate_pass"],
        "no_validation_access": results["validation_access"] == 0,
    })

    identities = [json.loads(line) for line in (ROOT / config["sources"]["identities"]["path"]).read_text(encoding="utf-8").splitlines() if line]
    validation = [x for x in identities if x["role"] == "threshold_validation"]
    first = sorted((x for x in validation if x["sequence_index"] < 160), key=lambda x: x["sequence_index"])
    first_ids = {x["study_id"] for x in first}
    other_ids = {x["study_id"] for x in identities if x["role"] != "threshold_validation"}
    ambiguous = [x["study_id"] for x in first if "ambiguous_threshold_validation" in x["diagnostic_memberships"]]
    checks.update({
        "total_frozen_identities": len(identities) == 950,
        "validation_identity_count": len(validation) == 480,
        "first_look_exact_count": len(first) == len(first_ids) == 160,
        "first_look_prefix": [x["sequence_index"] for x in first] == list(range(160)),
        "first_look_registered": all(x["first_registered_look"] == 160 for x in first),
        "cohort_disjoint": not (first_ids & other_ids),
        "first_look_ambiguous_subset": len(ambiguous) == 120,
        "validation_not_materialized": all(not x["scene_materialized"] for x in first),
    })
    if not all(checks.values()):
        raise RuntimeError(f"Freeze gate failed: {[k for k, ok in checks.items() if not ok]}")

    identity_bytes = b"".join(canonical_json(row) for row in first)
    identity_plan = {
        "schema_version": "fourgraph.p1_v4_validation_look160_exact_identity_plan.v1",
        "status": "PASS_EXACT_IDENTITY_FREEZE",
        "role": "threshold_validation",
        "registered_look": 160,
        "scene_count": 160,
        "scene_ids_in_execution_order": [x["study_id"] for x in first],
        "ambiguous_scene_ids": ambiguous,
        "exact_identities_sha256": hashlib.sha256(identity_bytes).hexdigest().upper(),
        "source_identity_manifest_sha256": config["sources"]["identities"]["sha256"],
        "scenes_materialized": 0,
        "oracle_access": 0,
        "holdout_access": 0,
    }
    policy = {
        "schema_version": "fourgraph.p1_v4_post_supplemental_policy_validation_freeze.v1",
        "status": "PASS_OFFLINE_POLICY_FREEZE",
        "config_sha256": digest(CONFIG),
        "historical_look440_decision": "STOP_FOR_FUTILITY",
        "supplemental_decision": "PASS_SUPPLEMENTAL_CONFIRMATION",
        "policy": config["policy"],
        "gates": config["gates"],
        "validation": config["validation"],
        "first_look_identity_sha256": identity_plan["exact_identities_sha256"],
        "first_look_scene_ids": [x["study_id"] for x in first],
        "first_look_ambiguous_scene_ids": ambiguous,
        "source_sha256": {name: source["sha256"] for name, source in config["sources"].items()},
        "live_execution_authorized_by_this_artifact": False,
        "validation_oracle_access": 0,
        "holdout_access": 0,
    }
    audit = {
        "schema_version": "fourgraph.p1_v4_post_supplemental_policy_validation_freeze_audit.v1",
        "status": "PASS_OFFLINE_FREEZE_LIVE_PENDING",
        "checks": checks,
        "policy_sha256": hashlib.sha256(canonical_json(policy)).hexdigest().upper(),
        "first_look_scenes": 160,
        "first_look_ambiguous_scenes": 120,
        "first_look_statistical_fits_estimate": 160 * 206,
        "first_look_semantic_calls_estimate": 160 * 2 * 6 + 120 * 6,
        "live_blocker": "fresh_project_spend_limit_hard_limit_reset_attestation_and_provider_preflight_not_yet_frozen",
        "validation_oracle_access": 0,
        "holdout_access": 0,
    }
    report = (
        "# P1V4 post-supplemental policy and validation look 160 freeze\n\n"
        "The original 440-scene STOP_FOR_FUTILITY remains unchanged. The separately registered 80-scene supplemental extension reached PASS_SUPPLEMENTAL_CONFIRMATION for primary Constrained-BOSS, but is not independent validation. Constrained-FGES remains a robustness comparator and did not independently meet the Partial HIGH minimum.\n\n"
        "The frozen publication policy is Mini-medium, six sentence-ID prompts, VERY_HIGH/HIGH automatic, MEDIUM review-only, UNCERTAIN/CONFLICT abstain, compelled confirmation and undirected semantic selection, no primary Meek closure. Parent CPDAGs remain immutable; the published graph is an evidence-annotated overlay. No model, prompt, schema, threshold, parent or e-process component is reselected.\n\n"
        "The independent P1V4SV cohort was pre-registered before the supplemental result. Its first look has exactly 160 scenes, including a fixed 120-scene Ambiguous diagnostic subset; Full and Partial are run on all 160. Expected workload is 32,960 statistical fits and 2,640 Mini-medium logical calls (1,920 Full/Partial plus 720 Ambiguous). Non-edge is excluded under the P1V4 execution policy. Later looks are 200 through 480 in steps of 40.\n\n"
        "At the observed combined Partial HIGH frequency 64/520, 480 fresh validation scenes would yield approximately 59 HIGH-contributing scenes on average. Under an illustrative independent constant-rate binomial model, reaching the minimum 60 by look 480 has probability about 47%; this is planning arithmetic, not observed validation performance or a registered power guarantee. The 960-call supplemental execution used 1,409,160 provider total tokens; a simple linear extrapolation to the first 2,640 calls is about 3.88 million tokens, above the previously requested 3-million-token daily ceiling. Actual calls must be batched across reset windows and governed by provider-reported usage.\n\n"
        "Offline identity/hash audit PASS. No scene was materialized, no fit or API call was run, and no validation Oracle or holdout was opened by this checkpoint. The user's execution consent is recorded in the conversation, but a distinct live checkpoint still requires fresh project spend/limit/hard-limit/reset attestation, a provider preflight, an execution/token budget and exact runner plan. This artifact is not live authorization.\n"
    )
    return policy, audit, report, identity_bytes, identity_plan


def main() -> None:
    policy, audit, report, identity_bytes, identity_plan = build()
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for key, value in (("policy", canonical_json(policy)), ("audit", canonical_json(audit)), ("report", report.encode("utf-8"))):
        path = ROOT / config["outputs"][key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    exact = ROOT / config["outputs"]["exact_identities"]
    exact.parent.mkdir(parents=True, exist_ok=True)
    exact.write_bytes(identity_bytes)
    (ROOT / config["outputs"]["exact_identity_plan"]).write_bytes(canonical_json(identity_plan))
    print(audit["status"], audit["policy_sha256"], audit["first_look_semantic_calls_estimate"])


if __name__ == "__main__":
    main()
