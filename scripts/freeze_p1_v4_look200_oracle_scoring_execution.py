"""Freeze the look-200 Oracle scorer without opening Oracle commitments."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/p1_v4_look200_cumulative_oracle_scoring_execution_freeze.yaml"


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def build() -> tuple[dict, dict[Path, bytes]]:
    config = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    for name, spec in config["inputs"].items():
        path = ROOT / spec["path"]
        checks[f"input_{name}"] = path.is_file() and sha256(path) == spec["sha256"]
    scorer = ROOT / config["implementation"]["scorer"]
    checks["scorer_hash"] = scorer.is_file() and sha256(scorer) == config["implementation"]["scorer_sha256"]

    checkpoint = json.loads((ROOT / config["inputs"]["checkpoint"]["path"]).read_text(encoding="utf-8"))
    checkpoint_audit = json.loads((ROOT / config["inputs"]["checkpoint_audit"]["path"]).read_text(encoding="utf-8"))
    freeze_path = ROOT / config["execution_freeze"]["path"]
    if freeze_path.is_file():
        # Replay preserves the historical fact recorded by the original freeze;
        # a later, separately authorized artifact must not invalidate that freeze.
        authorization_absent_at_freeze = json.loads(freeze_path.read_text(encoding="utf-8")).get(
            "oracle_scoring_authorized"
        ) is False
    else:
        authorization_absent_at_freeze = not (ROOT / config["authorization"]["path"]).exists() and not (
            ROOT / config["authorization"]["audit_path"]
        ).exists()
    checks.update(
        {
            "checkpoint_ready": checkpoint.get("status") == "PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION",
            "checkpoint_audit_ready": checkpoint_audit.get("status") == "PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION",
            "exact_200_scenes": len(checkpoint.get("exact_scene_ids", [])) == 200,
            "exact_400_parents": len(checkpoint.get("parent_graph_inventory", [])) == 400,
            "exact_3554_groups": checkpoint.get("scope", {}).get("six_vote_groups") == 3554,
            "registered_formula": config["scope"]["registered_look"] == 200
            and config["sequential_gates"]["risk"]["error_ceiling"] == 0.05
            and config["sequential_gates"]["coverage"]["floor"] == 0.20
            and config["sequential_gates"]["high_guardrail"]["error_ceiling"] == 0.10,
            "output_paths_unique": len(set(config["outputs"].values())) == len(config["outputs"]),
            "output_paths_look200": all("look200" in path for path in config["outputs"].values()),
            "dry_run_boundary": all(value == 0 for value in config["boundaries"].values()),
            "authorization_absent_at_freeze": authorization_absent_at_freeze,
        }
    )
    passed = all(checks.values())
    freeze = {
        "schema_version": "fourgraph.p1_v4_look200_oracle_scoring_execution_freeze.v1",
        "task": "P1_V4_LOOK200_ORACLE_SCORING_EXECUTION_FREEZE",
        "status": "PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION" if passed else "FAIL",
        "config_sha256": sha256(CFG),
        "implementation": config["implementation"],
        "checkpoint_sha256": config["inputs"]["checkpoint"]["sha256"],
        "exact_scene_ids": checkpoint["exact_scene_ids"],
        "scope": config["scope"],
        "sequential_gates": config["sequential_gates"],
        "decision_rule": config["decision_rule"],
        "frozen_inputs": config["inputs"],
        "frozen_outputs": config["outputs"],
        "boundary": config["boundaries"],
        "oracle_scoring_authorized": False,
        "automatic_execution": False,
    }
    freeze_bytes = canonical_bytes(freeze)
    audit = {
        "schema_version": "fourgraph.p1_v4_look200_oracle_scoring_execution_freeze_audit.v1",
        "task": freeze["task"],
        "status": "PASS" if passed else "FAIL",
        "checks": checks,
        "execution_freeze_sha256": hashlib.sha256(freeze_bytes).hexdigest().upper(),
        "oracle_access": 0,
        "semantic_api_calls": 0,
        "statistical_reruns": 0,
        "validation_access": 0,
        "holdout_access": 0,
    }
    report = (
        "# P1V4 look 200 Oracle-scoring execution freeze\n\n"
        f"Status: **{freeze['status']}**. The scorer, exactly 200 calibration scene IDs, 400 parent graphs, "
        "3,554 six-vote groups, sequential formulas, decision rule and output paths are hash-frozen. "
        "This checkpoint opened zero Oracle commitments.\n"
    ).encode()
    artifacts = {
        ROOT / config["execution_freeze"]["path"]: freeze_bytes,
        ROOT / config["execution_freeze"]["audit_path"]: canonical_bytes(audit),
        ROOT / "reports/p1_v4_look200_oracle_scoring_execution_freeze.md": report,
    }
    return audit, artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    audit, artifacts = build()
    for path, payload in artifacts.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != payload:
                raise RuntimeError(f"freeze replay drift: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    print(json.dumps(audit, indent=2))
    return 0 if audit["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
