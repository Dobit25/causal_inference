"""Generate the frozen calibration public stories without any API calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v3_nano_medium_calibration_public_story_generation_amendment.yaml"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fourgraph.p1_stories import build_story_bundle, public_builder_view, validate_story_bundle  # noqa: E402
from materialize_p1_v3_nano_calibration_look120 import materialize as materialize_scenes  # noqa: E402


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_cfg() -> dict[str, Any]:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def verify_parent_hashes(cfg: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in cfg["parents"].values():
        path = ROOT / item["path"]
        if not path.is_file():
            raise RuntimeError(f"missing parent: {item['path']}")
        digest = sha256_file(path)
        if digest != item["sha256"].upper():
            raise RuntimeError(f"parent hash drift: {item['path']}")
        out[item["path"]] = digest
    return out


def load_ids() -> list[dict[str, Any]]:
    path = ROOT / "data/manifests/p1_v3_successor_sequential_exact_identities.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if r.get("role") == "semantic_calibration" and int(r.get("sequence_index", -1)) < 120]
    rows.sort(key=lambda r: int(r["sequence_index"]))
    if len(rows) != 120 or len({r["study_id"] for r in rows}) != 120:
        raise RuntimeError("exact calibration cohort is not 120 unique rows")
    if any(not r["study_id"].startswith("P1V3SC") for r in rows):
        raise RuntimeError("calibration namespace guard failed")
    return rows


def preflight() -> dict[str, Any]:
    cfg = load_cfg()
    hashes = verify_parent_hashes(cfg)
    rows = load_ids()
    t19_cfg = yaml.safe_load((ROOT / cfg["parents"]["t19_story_config"]["path"]).read_text(encoding="utf-8"))
    if int(t19_cfg["randomness"]["master_seed"]) != int(cfg["generator"]["master_seed"]):
        raise RuntimeError("T19 story seed drift")
    return {
        "status": "PASS_AMENDMENT_OFFLINE_PREFLIGHT",
        "exact_scene_count": len(rows),
        "parent_hashes": hashes,
        "story_variants": cfg["variants"]["public_story_variants"],
        "expected_public_stories": int(cfg["outputs"]["expected_story_count"]),
        "semantic_api_calls": 0,
        "oracle_scoring": 0,
        "holdout_stories": 0,
    }


def build_public_payloads(cfg: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[dict[str, bytes], list[dict[str, Any]], list[dict[str, Any]]]:
    t19_cfg = yaml.safe_load((ROOT / cfg["parents"]["t19_story_config"]["path"]).read_text(encoding="utf-8"))
    payloads: dict[str, bytes] = {}
    manifest: list[dict[str, Any]] = []
    validation: list[dict[str, Any]] = []
    for row in rows:
        scm_path = ROOT / cfg["materialization"]["scene_root"] / row["study_id"] / "scm_internal.json"
        if not scm_path.is_file():
            raise RuntimeError(f"missing materialized SCM: {scm_path}")
        scm = json.loads(scm_path.read_text(encoding="utf-8"))
        bundle = build_story_bundle(scm, t19_cfg)
        counts = validate_story_bundle(bundle, t19_cfg)
        validation.append({"study_id": row["study_id"], "counts": counts})
        for record in bundle.public_records:
            variant = str(record["evidence_variant"])
            if variant not in cfg["variants"]["public_story_variants"]:
                raise RuntimeError(f"unexpected story variant {variant}")
            public = public_builder_view(record)
            story = public["story"]
            if any(token in story for token in ("X000", "X001", "oracle", "Oracle", "CPDAG", "DAG", "seed=")):
                raise RuntimeError(f"possible leakage in {record['artifact_id']}")
            out_record = dict(record)
            out_record["builder_input"] = public
            data = canonical(out_record)
            rel = f"{row['study_id']}/story_{variant}.json"
            payloads[rel] = data
            manifest.append({
                "scene_id": row["study_id"],
                "variant": variant,
                "path": f"{cfg['outputs']['story_root']}/{rel}",
                "content_sha256": sha256_bytes(data),
                "source_identity_sha256": row["identity_sha256"],
                "source_scm_commitment_sha256": sha256_file(scm_path),
                "public_model_view": True,
            })
    if len(payloads) != 360 or len(manifest) != 360:
        raise RuntimeError("expected exactly 120 scenes x 3 public story variants")
    return payloads, manifest, validation


def execute() -> dict[str, Any]:
    cfg = load_cfg()
    pre = preflight()
    rows = load_ids()
    # Materialize observations/SCM first, using the already-frozen adapter.
    materialization_cfg = ROOT / "configs/p1_v3_nano_medium_calibration_look120_production_runner.yaml"
    materialization_result = materialize_scenes(materialization_cfg, execute=True)
    payloads, manifest, validation = build_public_payloads(cfg, rows)
    # Deterministic replay is done in memory before any story artifact write.
    payloads_replay, manifest_replay, validation_replay = build_public_payloads(cfg, rows)
    if payloads != payloads_replay or manifest != manifest_replay or validation != validation_replay:
        raise RuntimeError("story generation replay is not byte-for-byte deterministic")
    story_root = ROOT / cfg["outputs"]["story_root"]
    for rel, data in payloads.items():
        path = story_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    manifest_path = ROOT / cfg["outputs"]["story_manifest"]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(b"".join(canonical(row) + b"\n" for row in manifest))
    input_manifest = {
        "schema_version": "fourgraph.p1_v3_nano_medium_calibration_public_input_manifest.v1",
        "scene_count": 120,
        "story_count": 360,
        "records": manifest,
        "diagnostic_nonedge_is_pair_subset_not_story_variant": True,
    }
    input_manifest_path = ROOT / cfg["outputs"]["input_manifest"]
    input_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    input_manifest_path.write_bytes(canonical(input_manifest))
    audit = {
        "schema_version": "fourgraph.p1_v3_nano_medium_calibration_public_story_generation_audit.v1",
        "status": "PASS_CALIBRATION_PUBLIC_STORIES_FROZEN",
        "preflight": pre,
        "materialization": materialization_result,
        "scene_count": 120,
        "story_count": 360,
        "variants": {variant: 120 for variant in cfg["variants"]["public_story_variants"]},
        "validation": validation,
        "replay": "PASS_BYTE_FOR_BYTE",
        "story_manifest_sha256": sha256_file(manifest_path),
        "input_manifest_sha256": sha256_file(input_manifest_path),
        "semantic_api_calls": 0,
        "oracle_scoring": 0,
        "holdout_access": 0,
        "leakage_audit": "PASS",
        "next_action": "REQUEST_SEPARATE_LIVE_EXECUTION_AUTHORIZATION",
    }
    audit_path = ROOT / cfg["outputs"]["audit"]
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_bytes(canonical(audit))
    return audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    result = execute() if args.execute else preflight()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
