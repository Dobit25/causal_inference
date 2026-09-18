from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/t21_v3e_terminal_decision.yaml"
AUDIT = ROOT / "data/manifests/t21_v3e_terminal_audit.json"
REPORT = ROOT / "reports/t21_v3e_terminal_decision.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def frozen_paths() -> list[Path]:
    patterns = (
        "configs/t21_v2*.yaml",
        "configs/t21_v3[abcd]*.yaml",
        "configs/p1_edge_selective_v2.yaml",
        "prompts/p1_semantic_preferences_v2.md",
        "reports/t21_v2*.md",
        "reports/t21_v3[abcd]*.md",
        "schemas/edge_selective_*.json",
        "schemas/p1_edge_selective_*.json",
        "data/manifests/t21_v2*",
        "data/manifests/t21_v3[abcd]*",
        "scripts/*t21_v2*.py",
        "scripts/*t21_v3[abcd]*.py",
        "scripts/seed_t21_v2_full_cache.py",
        "scripts/recover_t21_v2_development_cache.py",
        "src/fourgraph/edge_selective.py",
        "src/fourgraph/edge_selective_reference.py",
        "src/fourgraph/p1_validation_generation.py",
        "tests/test_t21_v2*.py",
        "tests/test_t21_v3[abcd]*.py",
        "tests/test_edge_selective.py",
    )
    paths: set[Path] = set()
    for pattern in patterns:
        paths.update(path for path in ROOT.glob(pattern) if path.is_file())
    return sorted(paths, key=lambda path: path.relative_to(ROOT).as_posix())


def build() -> tuple[bytes, bytes]:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    v3d_path = ROOT / config["terminal_evidence"]["validation_audit"]
    v3d = json.loads(v3d_path.read_text(encoding="utf-8"))

    if v3d["verdict"]["validation_gate_passed"] is not False:
        raise RuntimeError("T21 v3-D is not a failed validation gate")
    if v3d["selected_threshold"] is not None:
        raise RuntimeError("T21 v3-D unexpectedly selected a threshold")
    if v3d["evidence_boundary"]["final_holdout_accessed"] is not False:
        raise RuntimeError("Final holdout boundary was violated")
    if v3d["best_candidate_by_precision_then_coverage"]["orientation_precision"] != config["terminal_evidence"]["observed_best_orientation_precision"]:
        raise RuntimeError("Frozen terminal precision does not match T21 v3-D")

    grid_path = ROOT / "data/manifests/t21_v3d_validation_threshold_grid.jsonl"
    grid = [json.loads(line) for line in grid_path.read_text(encoding="utf-8").splitlines()]
    if len(grid) != 20 or any(row["eligible"] for row in grid):
        raise RuntimeError("Expected exactly 20 ineligible threshold candidates")
    selected_path = ROOT / "data/manifests/t21_v3d_validation_selected_graphs.jsonl"
    if selected_path.read_bytes() != b"":
        raise RuntimeError("Selected graph manifest must remain empty")

    frozen = [
        {
            "bytes": path.stat().st_size,
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256(path),
        }
        for path in frozen_paths()
    ]
    audit = {
        "schema_version": "fourgraph.t21_v3e_terminal_audit.v1",
        "task": "T21 Amendment v3-E",
        "decision": config["decision"],
        "decision_config": {
            "path": CONFIG.relative_to(ROOT).as_posix(),
            "sha256": sha256(CONFIG),
        },
        "implementation": {
            "path": "scripts/finalize_t21_v3e.py",
            "sha256": sha256(Path(__file__)),
        },
        "terminal_result": {
            "validation_scenes": v3d["counts"]["validation_scenes"],
            "threshold_candidates": v3d["counts"]["threshold_candidates"],
            "selected_threshold": None,
            "best_orientation_correct": v3d["best_candidate_by_precision_then_coverage"]["orientation_correct"],
            "best_answered_edges": v3d["best_candidate_by_precision_then_coverage"]["answered_edges"],
            "best_orientation_precision": v3d["best_candidate_by_precision_then_coverage"]["orientation_precision"],
            "best_orientation_coverage": v3d["best_candidate_by_precision_then_coverage"]["orientation_coverage"],
            "oriented_false_adjacencies": v3d["best_candidate_by_precision_then_coverage"]["oriented_false_adjacencies"],
            "required_orientation_precision": config["terminal_evidence"]["required_orientation_precision"],
        },
        "freeze": {
            "artifact_count": len(frozen),
            "artifacts": frozen,
            "t21_v2_v3_mutation_authorized": False,
        },
        "evidence_boundary": {
            "api_calls": 0,
            "downstream_tasks_or_answers_accessed": False,
            "final_holdout_accessed": False,
            "final_holdout_method_results_created": False,
            "selected_graph_manifest_empty": True,
        },
        "successor_boundary": config["successor_boundary"],
        "verdict": {
            "t21_v3e_complete": True,
            "p1_v2_terminal": True,
            "threshold_selected": False,
            "t22_authorized": False,
            "final_holdout_execution_authorized": False,
            "p1_v3_protocol_design_authorized": True,
            "p1_v3_execution_authorized": False,
        },
    }

    report = f"""# T21 v3-E — Terminal stop/freeze decision

T21 v3-E closes P1-v2 without opening the final holdout. The preregistered validation gate failed: the best candidate correctly oriented {audit['terminal_result']['best_orientation_correct']}/{audit['terminal_result']['best_answered_edges']} answered edges (`{audit['terminal_result']['best_orientation_precision']:.4f}` precision) at `{audit['terminal_result']['best_orientation_coverage']:.4f}` coverage, below the required `{audit['terminal_result']['required_orientation_precision']:.2f}` precision.

No threshold was selected. The selected-graph manifest remains empty, T22 is unauthorized, and the existing 80-scene final holdout remains sealed. The validation result is retained as a negative result; its gate will not be lowered and the same validation cohort will not be retuned.

This closure made zero API calls and accessed no downstream task answer or final-holdout method result. It hash-pins {len(frozen)} versioned T21 v2/v3 artifacts without modifying them.

The only authorized successor action is design-only work for `P1-v3 Evidence-Selective Hybrid`. The user-frozen starting decisions are GPT-5.4 Nano, whole-graph semantic calls, Bootstrap-BOSS as the primary statistical method, and deferral of the multi-algorithm ensemble to a later robustness study. Bootstrap execution, semantic API calls, new cohort generation and final-holdout access remain unauthorized until that successor protocol is independently frozen.
""".encode("utf-8")
    return canonical_json(audit), report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    audit, report = build()
    outputs = ((AUDIT, audit), (REPORT, report))
    if args.check:
        for path, expected in outputs:
            if not path.exists() or path.read_bytes() != expected:
                raise SystemExit(f"Mismatch: {path.relative_to(ROOT)}")
        print("T21 v3-E terminal artifacts reproduce byte-for-byte")
        return 0
    for path, content in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    print("T21 v3-E terminal stop/freeze recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

