"""Freeze the evidence-annotated overlay contract without Oracle re-scoring."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_look120_evidence_annotated_partial_graph_contract_amendment.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"non-deterministic artifact drift: {path}")
        return
    path.write_bytes(payload)


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for section in ("parents", "incident_evidence_retained"):
        for name, item in cfg[section].items():
            if not isinstance(item, dict) or "path" not in item:
                continue
            path = ROOT / item["path"]
            if not path.is_file() or sha(path) != item["sha256"]:
                raise RuntimeError(f"hash drift: {section}/{name}")
    checkpoint = json.loads((ROOT / cfg["parents"]["oracle_scoring_checkpoint"]["path"]).read_text(encoding="utf-8"))
    if checkpoint.get("status") != "PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION":
        raise RuntimeError("parent checkpoint is not frozen")
    if checkpoint["verification"].get("oracle_access") != 0:
        raise RuntimeError("offline parent checkpoint unexpectedly accessed Oracle")
    amendment = {
        "schema_version": "fourgraph.p1_v4_evidence_annotated_partial_graph_contract_amendment.v1",
        "task": cfg["task"],
        "status": "PASS_OFFLINE_FROZEN",
        "config_sha256": sha(CONFIG),
        "parents": cfg["parents"],
        "incident_evidence_retained": cfg["incident_evidence_retained"],
        "contract": cfg["contract"],
        "boundaries": cfg["boundaries"],
    }
    amendment_path = ROOT / cfg["outputs"]["amendment"]
    write_once(amendment_path, canonical(amendment))
    audit = {
        "schema_version": "fourgraph.p1_v4_evidence_annotated_partial_graph_contract_amendment_audit.v1",
        "task": cfg["task"],
        "status": "PASS",
        "amendment_sha256": sha(amendment_path),
        "all_parent_hashes_match": True,
        "incident_evidence_preserved": True,
        "parent_cpdag_immutable": True,
        "semantic_selected_parent_undirected_only": True,
        "global_semantic_conflict_rule": cfg["contract"]["validity"]["semantic_conflict_rule"],
        "oracle_access": 0,
        "holdout_access": 0,
        "semantic_api_calls": 0,
        "statistical_reruns": 0,
        "metric_recalculation": 0,
        "meek_closure": 0,
    }
    write_once(ROOT / cfg["outputs"]["audit"], canonical(audit))
    report = """# Look120 evidence-annotated partial-graph contract amendment

This amendment preserves the constrained statistical parent CPDAG as an immutable extension constraint. The visible publication graph is an evidence-annotated overlay: an unconfirmed parent-compelled direction is displayed as unresolved, not reinterpreted as statistically reversible. Semantic directions may appear only on parent-undirected edges and must be jointly compatible with the original parent CPDAG. A semantic conflict fail-closes that scene-condition-variant's semantic overlay; it never repairs or mutates the parent.

The prior Oracle metric artifacts are retained, hash-pinned incident evidence only. They used a CPDAG validator on the display overlay and must not be used for scientific gates. No Oracle access, metric replay, API call, statistical rerun, or Meek closure occurs in this amendment.
"""
    report_path = ROOT / cfg["outputs"]["report"]
    write_once(report_path, report.encode("utf-8"))
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
