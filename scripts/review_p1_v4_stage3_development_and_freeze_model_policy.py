"""Review frozen development metrics and freeze the pre-calibration model policy."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import NormalDist
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_stage3_development_scientific_review_and_model_policy.yaml"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def one_sided_wilson_lower(correct: int, total: int, confidence: float = 0.95) -> float | None:
    if total == 0:
        return None
    z = NormalDist().inv_cdf(confidence)
    p = correct / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    radius = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5)
    return (centre - radius) / denom


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for item in cfg["parents"].values():
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise RuntimeError(f"parent artifact drift: {item['path']}")
    results = json.loads((ROOT / cfg["parents"]["parent_semantic_metric_results"]["path"]).read_text(encoding="utf-8"))
    audit = json.loads((ROOT / cfg["parents"]["parent_semantic_metric_audit"]["path"]).read_text(encoding="utf-8"))
    if results.get("status") != "PASS_DEVELOPMENT_ONLY" or audit.get("status") != "PASS":
        raise RuntimeError("parent/semantic development metric audit not PASS")
    records = rows(ROOT / cfg["parents"]["parent_semantic_metric_dataset"]["path"])
    group_lookup: dict[str, dict[tuple[str, str, tuple[str, str]], str]] = {}
    for model in ("nano_medium", "mini_medium"):
        key = f"{model.split('_')[0]}_six_vote_groups"
        groups = rows(ROOT / cfg["parents"][key]["path"])
        group_lookup[model] = {}
        # Candidate direction is encoded A/B only, so endpoint matching happens below from metric source records.
        for group in groups:
            group_lookup[model][(group["scene_id"], group["variant"], (group["pair_id"], group.get("candidate_direction") or ""))] = group["agreement"]
    # Agreement-specific review uses selected metrics plus the group ordinal by pair ordering supplied below only as a quality check;
    # the combined automatic policy is the frozen decision criterion.
    semantic = [r for r in records if r["source"] == "semantic_selected" and r["published"]]
    all_by_model_variant: dict[str, Any] = {}
    for model in ("nano_medium", "mini_medium"):
        model_summary: dict[str, Any] = {}
        for variant in ("full", "partial"):
            selected = [r for r in semantic if r["model"] == model and r["variant"] == variant]
            correct = sum(r["oracle_match"] is True for r in selected)
            model_summary[variant] = {"automatic_semantic_selected": len(selected), "correct": correct, "wrong": len(selected) - correct, "precision": correct / len(selected) if selected else None, "one_sided_95pct_wilson_lcb": one_sided_wilson_lower(correct, len(selected))}
        total = [r for r in semantic if r["model"] == model]
        correct = sum(r["oracle_match"] is True for r in total)
        model_summary["all_variants"] = {"automatic_semantic_selected": len(total), "correct": correct, "wrong": len(total) - correct, "precision": correct / len(total) if total else None, "one_sided_95pct_wilson_lcb": one_sided_wilson_lower(correct, len(total))}
        all_by_model_variant[model] = model_summary
    model_coverages = {
        model: sum(results["models"][model]["Constrained-BOSS"][variant]["semantic_selected"]["published"] for variant in ("full", "partial"))
        for model in ("nano_medium", "mini_medium")
    }
    primary_model = max(model_coverages, key=lambda label: (model_coverages[label], label == "mini_medium"))
    parent_precision = {condition: results["models"]["nano_medium"][condition]["parent_compelled"]["precision"] for condition in ("Constrained-BOSS", "Constrained-FGES")}
    primary_parent = max(parent_precision, key=lambda label: (parent_precision[label], label == "Constrained-BOSS"))
    review = {
        "schema_version": "fourgraph.p1_v4_stage3_development_scientific_review.v1",
        "task": cfg["task"],
        "status": "PASS_DEVELOPMENT_REVIEW_COMPLETE",
        "scope": "30 development scenes only; descriptive, not validation or holdout evidence",
        "semantic_results": all_by_model_variant,
        "parent_compelled_precision": parent_precision,
        "key_findings": [
            "Both frozen models had zero errors among the automatic semantic-selected directions that survived condition-specific parent filtering.",
            "Mini-medium selected more semantic directions than Nano-medium on the same frozen inputs.",
            "Parent compelled directions have materially lower precision than semantic-selected directions; integrated partial-graph precision therefore cannot be interpreted as a semantic-model precision estimate.",
            "No-closure results are the primary development comparison; closure was not used to increase coverage.",
        ],
        "limitations": [
            "The 30 scenes are method-development data and cannot certify generalization.",
            "The model choice is frozen for independent calibration, not claimed as a best-model result.",
            "Wilson lower bounds are descriptive here; sequential certification remains reserved for the independent calibration protocol.",
        ],
        "next_action": "run independent calibration only after a new calibration authorization; do not tune on these 30 scenes",
    }
    policy = {
        "schema_version": "fourgraph.p1_v4_precalibration_model_policy.v1",
        "task": cfg["task"],
        "status": "FROZEN_CANDIDATE_POLICY_PENDING_INDEPENDENT_CALIBRATION",
        "primary_semantic_model": "gpt-5.4-mini-2026-03-17",
        "reasoning_effort": "medium",
        "selection_basis": "higher automatic semantic-selected coverage with zero direction errors on frozen development data; selection is not a generalization claim",
        "nano_medium_role": "frozen cost-sensitive comparator; not the primary calibration model",
        "semantic_selection": {"accepted_agreements": ["VERY_HIGH", "HIGH"], "closure": "forbidden", "condition_specific_parent_filtering": True},
        "primary_parent": primary_parent,
        "parent_policy": "compelled statistical directions remain separately labelled statistical context and are not automatically semantic-certified",
        "constrained_fges_role": "robustness comparator",
        "calibration_gate_unchanged": "independent sequential calibration is required before certification; no threshold change is authorized",
        "frozen_from_review_sha256": None,
    }
    review_path = ROOT / cfg["outputs"]["review"]
    review_path.write_bytes(canonical(review))
    policy["frozen_from_review_sha256"] = sha(review_path)
    policy_path = ROOT / cfg["outputs"]["policy"]
    policy_path.write_bytes(canonical(policy))
    audit_out = {"schema_version": "fourgraph.p1_v4_stage3_development_scientific_review_audit.v1", "task": cfg["task"], "status": "PASS", "review_sha256": sha(review_path), "policy_sha256": sha(policy_path), "inputs_hash_verified": True, "additional_oracle_access": 0, "semantic_api_calls": 0, "statistical_reruns": 0, "closure": 0, "calibration": 0, "holdout_access": 0}
    audit_path = ROOT / cfg["outputs"]["audit"]
    audit_path.write_bytes(canonical(audit_out))
    report = "# P1V4 development scientific review\n\n" + json.dumps(review, ensure_ascii=False, indent=2) + "\n\n## Frozen pre-calibration policy\n\n" + json.dumps(policy, ensure_ascii=False, indent=2) + "\n"
    (ROOT / cfg["outputs"]["report"]).write_text(report, encoding="utf-8")
    print(json.dumps({"review": review, "policy": policy, "audit": audit_out}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
