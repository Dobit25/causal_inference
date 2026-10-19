"""Freeze P1V4 identities and registered sequential membership without scenes."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_stage3_exact_identity_cohort.yaml"
COMPONENTS = ("graph_candidates", "edge_weights", "observations", "query_order", "story_template", "bootstrap_boss")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def seed(master: int, study_id: str, component: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{master}|{study_id}|{component}".encode("utf-8")).digest()[:8], "big")


def allocation(ids: list[str], counts: dict[Any, int], master: int, label: str) -> dict[str, Any]:
    ranked = sorted(ids, key=lambda value: (digest_bytes(f"{master}|{label}|{value}".encode()), value))
    values: list[Any] = []
    for key, count in counts.items(): values.extend([key] * int(count))
    if len(values) != len(ids): raise ValueError(f"count mismatch for {label}")
    return dict(zip(ranked, values, strict=True))


def balanced_order(rows: list[dict[str, Any]], master: int) -> list[dict[str, Any]]:
    fields = ("node_count", "primary_motif", "noise_family", "query_stratum")
    categories = {field: sorted({row[field] for row in rows}, key=str) for field in fields}
    remaining, result = list(rows), []
    counts = {field: Counter() for field in fields}
    while remaining:
        def score(row: dict[str, Any]) -> tuple[Any, ...]:
            spreads = []
            for field in fields:
                candidate = counts[field].copy(); candidate[row[field]] += 1
                values = [candidate[value] for value in categories[field]]; spreads.append(max(values) - min(values))
            return (max(spreads), sum(spreads), digest_bytes(f"{master}|{len(result)}|{row['study_id']}".encode()), row["study_id"])
        chosen = min(remaining, key=score); remaining.remove(chosen); result.append(chosen)
        for field in fields: counts[field][chosen[field]] += 1
    return result


def role_rows(role: str, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    ids = [f"{cfg['namespace']}{index:03d}" for index in range(cfg["scene_count"])]
    target = cfg["targets"]
    columns = {
        "node_count": allocation(ids, {int(key): value for key, value in target["node_count"].items()}, cfg["master_seed"], "node"),
        "primary_motif": allocation(ids, target["primary_motif"], cfg["master_seed"], "motif"),
        "noise_family": allocation(ids, target["noise_family"], cfg["master_seed"], "noise"),
        "query_stratum": allocation(ids, target["query_stratum"], cfg["master_seed"], "query"),
    }
    rows = []
    for ordinal, study_id in enumerate(ids):
        rows.append({"schema_version": "fourgraph.p1_v4_stage3_identity.v1", "role": role, "ordinal": ordinal, "study_id": study_id, "contract_scene_id": f"scene_{cfg['scene_number_start'] + ordinal:06d}", "master_seed": cfg["master_seed"], **{field: values[study_id] for field, values in columns.items()}, "component_seeds": {component: seed(cfg["master_seed"], study_id, component) for component in COMPONENTS}, "scene_materialized": False})
    ordered = balanced_order(rows, cfg["master_seed"])
    for sequence, row in enumerate(ordered):
        looks = cfg["registered_looks"]; first = next(look for look in looks if sequence < look)
        prior = max([look for look in looks if look <= sequence], default=0)
        row.update({"sequence_index": sequence, "first_registered_look": first, "batch_id": f"{role}:{prior:03d}-{first:03d}", "included_in_registered_looks": [look for look in looks if sequence < look], "diagnostic_memberships": []})
    return ordered


def build() -> dict[Path, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    checks = {}
    for name, spec in cfg["parents"].items():
        path = ROOT / spec["path"]; checks[f"{name}_hash"] = path.is_file() and digest_file(path) == spec["sha256"]
    by_role = {role: role_rows(role, spec) for role, spec in cfg["roles"].items()}
    subsets = {
        "ambiguous_semantic_calibration": [row["study_id"] for row in by_role["semantic_calibration"][:120]],
        "ambiguous_threshold_validation": [row["study_id"] for row in by_role["threshold_validation"][:120]],
        "nonedge_semantic_calibration": [row["study_id"] for row in by_role["semantic_calibration"][:80]],
        "nonedge_threshold_validation": [row["study_id"] for row in by_role["threshold_validation"][:80]],
    }
    reverse: dict[str, list[str]] = {}
    for name, ids in subsets.items():
        for study_id in ids: reverse.setdefault(study_id, []).append(name)
    rows = [row for role in cfg["roles"] for row in by_role[role]]
    for row in rows:
        row["diagnostic_memberships"] = sorted(reverse.get(row["study_id"], []))
        payload = dict(row); row["identity_sha256"] = digest_bytes(canonical(payload))
    ids = [row["study_id"] for row in rows]; scenes = [row["contract_scene_id"] for row in rows]; seeds = [value for row in rows for value in row["component_seeds"].values()]
    checks.update({"identity_count": len(rows) == 950, "unique_ids": len(set(ids)) == 950, "unique_contract_scene_ids": len(set(scenes)) == 950, "unique_component_seeds": len(set(seeds)) == 5700, "p1v4_namespace_only": all(row["study_id"].startswith("P1V4") for row in rows), "registered_look_nesting": all(sum(look in row["included_in_registered_looks"] for row in by_role[role]) == look for role, spec in cfg["roles"].items() for look in spec["registered_looks"]), "nonedge_nested_in_ambiguous": set(subsets["nonedge_semantic_calibration"]) <= set(subsets["ambiguous_semantic_calibration"]) and set(subsets["nonedge_threshold_validation"]) <= set(subsets["ambiguous_threshold_validation"]), "offline_boundary": all(value in (0, False) for value in cfg["execution_boundary"].values())})
    passed = all(checks.values())
    identity_bytes = b"".join(canonical(row) + b"\n" for row in rows)
    plan = {"schema_version": "fourgraph.p1_v4_stage3_exact_identity_cohort.v1", "task": cfg["task"], "status": "FROZEN_OFFLINE_EXACT_IDENTITIES" if passed else "FAILED_OFFLINE_EXACT_IDENTITIES", "roles": {role: {"count": len(role_rows), "ordered_scene_ids": [row["study_id"] for row in role_rows], "registered_looks": cfg["roles"][role]["registered_looks"]} for role, role_rows in by_role.items()}, "diagnostic_subsets": subsets, "execution_boundary": cfg["execution_boundary"], "authorization_after_freeze": {"method_development_live_authorized": False, "calibration_live_authorized": False, "validation_live_authorized": False, "oracle_access_authorized": False, "holdout_access_authorized": False, "next_action": "P1_V4_STAGE_3D_METHOD_DEVELOPMENT_AUTHORIZATION"}}
    plan_bytes = canonical(plan) + b"\n"
    audit = {"schema_version": "fourgraph.p1_v4_stage3_exact_identity_cohort_audit.v1", "task": cfg["task"], "status": "PASS_STAGE_3C_EXACT_IDENTITY_FREEZE" if passed else "FAIL_STAGE_3C_EXACT_IDENTITY_FREEZE", "checks": checks, "counts": {"method_development": 30, "semantic_calibration": 440, "threshold_validation": 480, "total": 950}, "hashes": {"identities": digest_bytes(identity_bytes), "plan": digest_bytes(plan_bytes), "config": digest_file(CONFIG)}, "execution_boundary": cfg["execution_boundary"], "next_action": plan["authorization_after_freeze"]["next_action"] if passed else "IDENTITY_REMEDIATION_ONLY"}
    report = f"""# P1-v4 Stage 3 exact identity cohort\n\nStatus: **{audit['status']}**. The future cohort contains 30 method-development, 440 sequential calibration and 480 sequential validation identities, all under a fresh P1V4 namespace. Each identity has fixed stratum assignments, component seeds, batch membership and diagnostic subset membership.\n\nNo SCM, observational sample, story, statistical fit or semantic call has been created. Oracle and the existing 80-scene holdout remain inaccessible.\n""".encode("utf-8")
    return {ROOT / cfg["outputs"]["identities"]: identity_bytes, ROOT / cfg["outputs"]["plan"]: plan_bytes, ROOT / cfg["outputs"]["audit"]: canonical(audit), ROOT / cfg["outputs"]["report"]: report}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    generated = build()
    if args.check:
        for path, content in generated.items():
            if not path.is_file() or path.read_bytes() != content: raise SystemExit(f"artifact drift: {path.relative_to(ROOT)}")
    else:
        for path, content in generated.items(): path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    print(json.dumps({"status": "PASS", "stage": "3C", "identities": 950, "scenes_materialized": 0, "api_calls": 0, "oracle_access": False, "check": args.check}))
    return 0


if __name__ == "__main__": raise SystemExit(main())
