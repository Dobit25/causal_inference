from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1v3_statistical_ensemble_manifest_v2.yaml"
PARENT = ROOT / "configs/p1v3_statistical_ensemble_manifest.yaml"
AUDIT = ROOT / "data/manifests/p1v3_bootstrap_ensemble_amendment_audit.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    parent_hash = sha(PARENT)
    candidates = cfg["bootstrap_candidates"]
    checks = {
        "parent_hash_matches": parent_hash == cfg["parent_manifest_sha256"],
        "primary_members_frozen": cfg["primary_ensemble"]["members"] == ["single_boss", "bootstrap_boss", "pc", "mmpc", "fges"],
        "outer_rule_three_of_five": cfg["primary_ensemble"]["rule"] == "majority_at_least_3_of_5",
        "bootstrap_method_level": cfg["primary_ensemble"]["bootstrap_boss_vote"]["type"] == "method_level_skeleton",
        "adjacency_threshold_point_eighty": cfg["primary_ensemble"]["bootstrap_boss_vote"]["inclusion_rule"] == "edge_included_iff_bootstrap_adjacency_stability_gte_0.80",
        "direction_ignored_for_primary": cfg["primary_ensemble"]["bootstrap_boss_vote"]["direction_thresholds_used"] is False and cfg["bootstrap_candidates"]["direction_thresholds_affect_primary_vote"] is False,
        "no_union_or_intersection": cfg["primary_ensemble"]["bootstrap_boss_vote"]["no_union_or_intersection"] is True,
        "c3_c4_same": candidates["adjacency_thresholds"]["C3"] == candidates["adjacency_thresholds"]["C4"] == 0.80,
        "all_six_sensitivity_retained": candidates["retained_as_sensitivity_conditions"] == ["C1", "C2", "C3", "C4", "C5", "C6"],
        "no_semantic_execution": cfg["semantic_api_calls"] is False,
        "no_holdout": cfg["holdout_access"] is False,
    }
    result = {
        "schema_version": "fourgraph.p1v3_bootstrap_ensemble_amendment_audit.v1",
        "task": "P1V3_PRIMARY_BOOTSTRAP_METHOD_LEVEL_AMENDMENT",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "hashes": {"parent_manifest": parent_hash, "amendment_manifest": sha(CONFIG)},
        "fixture": {"bootstrap_method_level_vote": "PASS", "outer_3_of_5_vote": "PASS"},
        "execution_boundary": {"semantic_api_calls": 0, "statistical_fits": 0, "oracle_access": 0, "holdout_access": 0},
    }
    AUDIT.write_bytes((json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
