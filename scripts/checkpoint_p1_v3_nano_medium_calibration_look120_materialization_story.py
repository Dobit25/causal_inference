"""Fail-closed materialization/story checkpoint for Nano look 120.

The current T19 story amendment is explicitly scoped to P1V3SD method
development scenes.  This checkpoint therefore refuses to relabel/copy those
stories to P1V3SC calibration.  A calibration story-generation amendment must
be frozen before any scene write or live semantic authorization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v3_nano_medium_calibration_look120_materialization_story_checkpoint.yaml"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_cfg() -> dict[str, Any]:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def exact_ids() -> list[dict[str, Any]]:
    path = ROOT / "data/manifests/p1_v3_successor_sequential_exact_identities.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if r.get("role") == "semantic_calibration" and int(r.get("sequence_index", -1)) < 120]
    rows.sort(key=lambda r: int(r["sequence_index"]))
    if len(rows) != 120 or len({r["study_id"] for r in rows}) != 120:
        raise RuntimeError("exact calibration prefix is not 120 unique identities")
    if any(not r["study_id"].startswith("P1V3SC") for r in rows):
        raise RuntimeError("calibration namespace guard failed")
    return rows


def verify_parent_hashes(cfg: dict[str, Any]) -> dict[str, str]:
    actual: dict[str, str] = {}
    for record in cfg["parents"].values():
        path = ROOT / record["path"]
        if not path.is_file():
            raise RuntimeError(f"missing parent: {record['path']}")
        digest = sha256_file(path)
        if digest != record["sha256"].upper():
            raise RuntimeError(f"parent hash drift: {record['path']}")
        actual[record["path"]] = digest
    return actual


def inspect_existing_inputs(cfg: dict[str, Any], ids: list[dict[str, Any]]) -> dict[str, Any]:
    scene_root = ROOT / cfg["materialization"]["scene_root"]
    story_root = ROOT / cfg["materialization"]["public_story_root"]
    scene_manifest = scene_root / "manifest.json"
    scene_ready = scene_manifest.is_file()
    story_ready = story_root.is_dir()
    scene_count = 0
    story_count = 0
    leakage_errors: list[str] = []
    if scene_ready:
        payload = json.loads(scene_manifest.read_text(encoding="utf-8"))
        records = payload.get("records", [])
        scene_count = len(records)
        if {r.get("study_id") for r in records} != {r["study_id"] for r in ids}:
            leakage_errors.append("scene manifest does not equal exact 120 IDs")
    if story_ready:
        for row in ids:
            for variant in cfg["public_stories"]["certification_variants"]:
                path = story_root / row["study_id"] / f"story_{variant}.json"
                if not path.is_file():
                    leakage_errors.append(f"missing story: {path.relative_to(ROOT)}")
                    continue
                story_count += 1
                data = json.loads(path.read_text(encoding="utf-8"))
                # Only the public builder view may reach the model.
                public = data.get("builder_input", {})
                if set(public) != {"story"} or not isinstance(public.get("story"), str):
                    leakage_errors.append(f"non-public fields or invalid story: {path.relative_to(ROOT)}")
                text = public.get("story", "")
                if any(token in text for token in ("oracle", "cpdag", "dag", "seed=", "X000", "X001", "->")):
                    leakage_errors.append(f"possible leakage in: {path.relative_to(ROOT)}")
    # T19 is not a calibration story contract; this is intentionally a hard
    # blocker, even if development stories happen to be present elsewhere.
    story_protocol_ready = False
    return {
        "scene_root_exists": scene_root.is_dir(),
        "scene_manifest_exists": scene_ready,
        "scene_count": scene_count,
        "story_root_exists": story_ready,
        "story_count_full_partial": story_count,
        "story_protocol_ready": story_protocol_ready,
        "leakage_errors": leakage_errors,
        "scene_root": str(scene_root.relative_to(ROOT)),
        "story_root": str(story_root.relative_to(ROOT)),
    }


def run() -> dict[str, Any]:
    cfg = load_cfg()
    hashes = verify_parent_hashes(cfg)
    ids = exact_ids()
    inputs = inspect_existing_inputs(cfg, ids)
    status = "PASS_READY_FOR_STORY_AMENDMENT" if inputs["story_protocol_ready"] and not inputs["leakage_errors"] else "BLOCKED_CALIBRATION_STORY_PROTOCOL"
    return {
        "schema_version": "fourgraph.p1_v3_nano_medium_calibration_look120_materialization_story_audit.v1",
        "status": status,
        "exact_scene_count": len(ids),
        "exact_scene_ids_hash": hashlib.sha256(canonical([r["study_id"] for r in ids])).hexdigest().upper(),
        "parent_hashes": hashes,
        "inputs": inputs,
        "scene_materialization_writes": 0,
        "semantic_api_calls": 0,
        "single_boss_fits": 0,
        "bootstrap_boss_fits": 0,
        "oracle_access": False,
        "validation_access": False,
        "holdout_access": False,
        "live_execution_enabled": False,
        "disposition": "Do not relabel/copy P1V3SD T19 stories; freeze a calibration story-generation amendment first.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--materialize", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "data/manifests/p1_v3_nano_medium_calibration_look120_materialization_story_checkpoint_audit.json")
    args = parser.parse_args()
    if args.materialize:
        raise SystemExit("FAIL_CLOSED: calibration public-story amendment is not frozen; no scene writes allowed")
    audit = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(audit))
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
