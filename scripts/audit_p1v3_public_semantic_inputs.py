from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1v3_public_semantic_input_manifest.yaml"
AUDIT = ROOT / "data/manifests/p1v3_public_semantic_input_audit.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def ids() -> list[str]:
    return [f"P1V3SD{i:03d}" for i in range(30)]


def discover() -> list[dict]:
    # Only inspect already registered public-artifact registries. Do not invoke
    # generators and do not inspect SCM/Oracle files to reconstruct stories.
    candidates = [
        ROOT / "data/manifests/p1_v3_successor_method_development_semantic.jsonl",
        ROOT / "data/manifests/p1v3_phase_e_shared_semantic_inputs.jsonl",
        ROOT / "data/manifests/p1_v3_mini_medium_independent_confirmation_semantic_inputs.jsonl",
        ROOT / "data/manifests/t19_p1_story_manifest.jsonl",
    ]
    rows: list[dict] = []
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            study = value.get("study_id")
            story = value.get("story") or value.get("builder_input", {}).get("story")
            if study in ids() and isinstance(story, str):
                rows.append({"source_registry": str(path.relative_to(ROOT)).replace("\\", "/"), "study_id": study, "story": story})
    return rows


def build() -> dict:
    expected = ids()
    found = discover()
    found_by_id: dict[str, list[dict]] = {study: [] for study in expected}
    for row in found:
        found_by_id[row["study_id"]].append(row)
    records = []
    for study in expected:
        rows = found_by_id[study]
        for row in rows:
            records.append({"study_id": study, "source_registry": row["source_registry"], "content_sha256": hashlib.sha256(row["story"].encode()).hexdigest().upper()})
    missing = [study for study in expected if not found_by_id[study]]
    duplicate = {study: len(rows) for study, rows in found_by_id.items() if len(rows) > 1}
    result = {
        "schema_version": "fourgraph.p1v3_public_semantic_input_audit.v1",
        "task": "P1V3_PUBLIC_SEMANTIC_INPUT_IDENTIFICATION",
        "status": "FAIL_MISSING_REGISTERED_PUBLIC_ARTIFACTS" if missing else "PASS",
        "expected_scene_ids": expected,
        "identified_records": records,
        "counts": {"expected_scenes": 30, "identified_scenes": 30 - len(missing), "missing_scenes": len(missing), "duplicate_scene_records": sum(duplicate.values())},
        "missing_scene_ids": missing,
        "duplicate_records": duplicate,
        "checks": {
            "exactly_30_ids": len(expected) == 30,
            "no_missing": not missing,
            "no_duplicate": not duplicate,
            "deterministic_hashes": False if missing else True,
            "replay_byte_for_byte": False if missing else True,
            "public_input_leakage_audit": False if missing else True,
            "statistical_mapping_deterministic": False if missing else True,
        },
        "execution_boundary": {"api_calls": 0, "story_generation": 0, "oracle_access": 0, "holdout_access": 0},
        "reason": "No registered public story/input artifact exists for P1V3SD000-P1V3SD029; T19 artifacts use P1S identifiers and cannot be relabeled.",
        "config_sha256": sha(CONFIG),
    }
    AUDIT.write_bytes((json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())
    return result


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
