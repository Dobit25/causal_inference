"""Freeze public-story non-edge pairs for calibration look 120.

This amendment deliberately reads only the frozen public full stories and the
registered diagnostic scene IDs.  It never reads SCM, Oracle, or statistical
parent artifacts.  The resulting pair manifest is an input-selection artifact,
not a scientific score.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "data/manifests/p1_v3_successor_sequential_exact_identity_plan.json"
STORY_ROOT = ROOT / "data/generated/p1_v3_nano_medium_calibration_look120_stories"
STORY_MANIFEST = ROOT / "data/manifests/p1_v3_nano_medium_calibration_public_story_manifest.jsonl"
CONFIG = ROOT / "configs/p1_v3_nano_medium_calibration_look120_nonedge_amendment.yaml"
PAIR_MANIFEST = ROOT / "data/manifests/p1_v3_nano_medium_calibration_nonedge_pair_manifest.json"
AUDIT = ROOT / "data/manifests/p1_v3_nano_medium_calibration_nonedge_amendment_audit.json"
REPORT = ROOT / "reports/p1_v3_nano_medium_calibration_nonedge_amendment.md"

EXPECTED_COUNT = 80
MAX_PAIRS_PER_SCENE = 3
PREFIX = "P1V3SC"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def file_sha(path: Path) -> str:
    return sha(path.read_bytes())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def identities() -> list[str]:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    ids = list(plan["diagnostic_subsets"]["nonedge_semantic_calibration"])
    if len(ids) != EXPECTED_COUNT or len(set(ids)) != EXPECTED_COUNT:
        raise RuntimeError("non-edge diagnostic subset is not exactly 80 unique IDs")
    if any(not str(x).startswith(PREFIX) for x in ids):
        raise RuntimeError("non-edge IDs have unexpected namespace")
    return ids


def story(scene_id: str) -> tuple[str, list[str], str]:
    path = STORY_ROOT / scene_id / "story_full.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("study_id") != scene_id or obj.get("evidence_variant") != "full":
        raise RuntimeError(f"story provenance drift: {scene_id}")
    text = obj.get("builder_input", {}).get("story")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError(f"empty story: {scene_id}")
    first, *_ = text.split(".", 1)
    marker = "This synthetic process contains the following measured quantities: "
    if not first.startswith(marker):
        raise RuntimeError(f"alias header drift: {scene_id}")
    aliases = [x.strip() for x in first[len(marker):].split(",")]
    if not 5 <= len(aliases) <= 7 or len(set(aliases)) != len(aliases):
        raise RuntimeError(f"invalid alias universe: {scene_id}")
    return text, aliases, file_sha(path)


def direct_pairs(text: str, aliases: list[str]) -> set[tuple[int, int]]:
    """Extract only pair mentions in direct-connection statements.

    The full story is the public source of truth for this diagnostic.  The
    sentence saying that unlisted pairs have no direct connection contains no
    alias pair and therefore contributes nothing here.
    """
    sentences = [s.strip() for s in text.split(".")[1:] if s.strip()]
    out: set[tuple[int, int]] = set()
    for sentence in sentences:
        for i, j in itertools.combinations(range(len(aliases)), 2):
            if aliases[i] in sentence and aliases[j] in sentence:
                out.add((i, j))
    return out


def build() -> dict[str, Any]:
    registered = set(identities())
    story_records = {
        r["scene_id"]: r
        for r in read_jsonl(STORY_MANIFEST)
        if r.get("variant") == "full"
    }
    records: list[dict[str, Any]] = []
    per_scene: list[dict[str, Any]] = []
    for scene_id in identities():
        text, aliases, story_hash = story(scene_id)
        manifest_row = story_records.get(scene_id)
        if not manifest_row or manifest_row.get("variant") != "full":
            raise RuntimeError(f"missing frozen full-story manifest row: {scene_id}")
        if manifest_row.get("content_sha256") != story_hash:
            raise RuntimeError(f"story hash mismatch: {scene_id}")
        all_pairs = list(itertools.combinations(range(len(aliases)), 2))
        direct = direct_pairs(text, aliases)
        absent = [pair for pair in all_pairs if pair not in direct]
        if len(absent) < MAX_PAIRS_PER_SCENE:
            raise RuntimeError(f"public story has fewer than 3 unlisted pairs: {scene_id}")
        ranked = sorted(
            absent,
            key=lambda pair: sha(canonical([scene_id, "public_story_nonedge_v1", f"X{pair[0]:03d}", f"X{pair[1]:03d}"])),
        )
        selected = ranked[:MAX_PAIRS_PER_SCENE]
        pair_rows = []
        for index, (i, j) in enumerate(selected, start=1):
            pair = {
                "pair_id": f"pair_{index:02d}",
                "node_a_id": f"X{i:03d}",
                "node_b_id": f"X{j:03d}",
                "node_a_alias": aliases[i],
                "node_b_alias": aliases[j],
                "selection_basis": "public_story_explicit_unlisted_pair",
                "direct_pair_in_public_story": False,
            }
            pair_rows.append(pair)
            records.append({"scene_id": scene_id, "variant": "full", **pair})
        per_scene.append(
            {
                "scene_id": scene_id,
                "story_path": str((STORY_ROOT / scene_id / "story_full.json").relative_to(ROOT)).replace("\\", "/"),
                "story_sha256": story_hash,
                "alias_count": len(aliases),
                "public_story_direct_pair_count": len(direct),
                "public_story_unlisted_pair_count": len(absent),
                "pairs": pair_rows,
            }
        )
    if set(x["scene_id"] for x in per_scene) != registered or len(records) != EXPECTED_COUNT * MAX_PAIRS_PER_SCENE:
        raise RuntimeError("pair manifest cardinality drift")
    return {
        "schema_version": "fourgraph.p1_v3_public_story_nonedge_pair_manifest.v1",
        "purpose": "public-story non-edge diagnostic; not a parent-graph candidate set",
        "selection_protocol": {
            "source": "frozen public full story only",
            "direct_pair_extraction": "alias pair co-occurrence within one direct-connection sentence",
            "candidate_rule": "all unordered alias pairs not mentioned in a direct-connection sentence",
            "ordering": "SHA256(scene_id, public_story_nonedge_v1, canonical node IDs)",
            "pairs_per_scene": MAX_PAIRS_PER_SCENE,
            "oracle_or_statistical_inputs": False,
            "holdout_inputs": False,
        },
        "scene_count": EXPECTED_COUNT,
        "pair_count": len(records),
        "scenes": per_scene,
    }


def config(manifest_hash: str) -> str:
    return f"""schema_version: fourgraph.p1_v3_nano_medium_calibration_nonedge_amendment.v1
task: P1_V3_NANO_MEDIUM_CALIBRATION_PUBLIC_STORY_NONEDGE_AMENDMENT_FREEZE
status: offline_frozen_requires_successor_live_authorization

parent_live_authorization:
  path: configs/p1_v3_nano_medium_calibration_look120_live_authorization_v2.yaml
  sha256: {file_sha(ROOT / 'configs/p1_v3_nano_medium_calibration_look120_live_authorization_v2.yaml')}
pair_manifest:
  path: data/manifests/p1_v3_nano_medium_calibration_nonedge_pair_manifest.json
  sha256: {manifest_hash}
  scene_count: 80
  pairs_per_scene: 3
  total_pairs: 240

definition:
  label: public-story non-edge diagnostic
  input_story_variant: full
  source: frozen public story text only
  selection: unlisted alias pairs in direct-connection sentences' complement
  statistical_parent_filter: forbidden
  oracle_filter: forbidden
  hidden_scm_filter: forbidden
  holdout_access: forbidden
  model_view: public aliases only; pair IDs are internal request metadata

workload:
  nonedge_diagnostic_calls: 480
  formula: 80 scenes x 6 prompt variants
  previous_authorization_workload: 2640
  successor_authorization_required: true

replay:
  deterministic: true
  source_story_hashes: pinned_in_pair_manifest
  no_api_calls: true
  no_statistical_rerun: true
"""


def write_or_check(check: bool) -> dict[str, Any]:
    obj = build()
    manifest_bytes = canonical(obj) + b"\n"
    manifest_hash = sha(manifest_bytes)
    cfg_bytes = config(manifest_hash).encode()
    audit = {
        "schema_version": "fourgraph.p1_v3_nano_medium_calibration_nonedge_amendment_audit.v1",
        "status": "PASS_PUBLIC_STORY_NONEDGE_PAIR_FREEZE",
        "scene_count": obj["scene_count"],
        "pair_count": obj["pair_count"],
        "pairs_per_scene": MAX_PAIRS_PER_SCENE,
        "exact_scene_ids": identities(),
        "manifest_sha256": manifest_hash,
        "config_sha256": sha(cfg_bytes),
        "source_story_manifest_sha256": file_sha(STORY_MANIFEST),
        "selection_inputs": {"public_stories": True, "statistical_graphs": False, "oracle": False, "holdout": False},
        "leakage_audit": "PASS",
        "mapping_audit": "PASS",
        "replay": "PASS_BYTE_FOR_BYTE" if PAIR_MANIFEST.exists() and canonical(json.loads(PAIR_MANIFEST.read_bytes())) + b"\n" == manifest_bytes else "PENDING_INITIAL_WRITE",
        "api_calls": 0,
    }
    if check:
        if not PAIR_MANIFEST.exists() or PAIR_MANIFEST.read_bytes() != manifest_bytes:
            raise SystemExit("pair manifest replay mismatch")
        if not CONFIG.exists() or CONFIG.read_bytes() != cfg_bytes:
            raise SystemExit("amendment config replay mismatch")
        existing = json.loads(AUDIT.read_text(encoding="utf-8"))
        if existing.get("manifest_sha256") != manifest_hash or existing.get("config_sha256") != sha(cfg_bytes):
            raise SystemExit("amendment audit hash mismatch")
        existing["replay"] = "PASS_BYTE_FOR_BYTE"
        AUDIT.write_bytes(canonical(existing) + b"\n")
        return existing
    PAIR_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    PAIR_MANIFEST.write_bytes(manifest_bytes)
    CONFIG.write_bytes(cfg_bytes)
    AUDIT.write_bytes(canonical(audit) + b"\n")
    REPORT.write_text(
        "# Public-story non-edge diagnostic amendment\n\n"
        "This offline amendment freezes exactly 80 registered calibration scenes and "
        "three non-edge pairs per scene (240 pairs). Pairs are selected only from "
        "the complement of direct pair mentions in each frozen public full story. "
        "No SCM, Oracle, statistical parent graph, holdout data, or API response is "
        "read or used. The diagnostic is not part of the statistical parent graph and "
        "requires a successor live authorization.\n\n"
        f"Manifest SHA-256: `{manifest_hash}`\n\n"
        f"Config SHA-256: `{sha(cfg_bytes)}`\n\n"
        "Audit: `PASS_PUBLIC_STORY_NONEDGE_PAIR_FREEZE`; API calls: 0; Oracle/holdout: 0.\n",
        encoding="utf-8",
    )
    return audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = write_or_check(args.check)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
