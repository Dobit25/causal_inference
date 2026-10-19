"""Create the P1V4/cau semantic-live authorization checkpoint, without API use."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_stage3_shared_semantic_live_authorization_cau.yaml"


def line(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load(path: Path) -> dict[str, Any]:
    if path.suffix in {".yaml", ".yml"}:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"mapping required: {path}")
    return value


def verify_pins(cfg: dict[str, Any]) -> None:
    for name, item in cfg["parents"].items():
        path = ROOT / str(item["path"])
        if not path.is_file():
            raise RuntimeError(f"missing dependency {name}")
        expected = item.get("sha256")
        if expected and sha_file(path) != expected:
            raise RuntimeError(f"dependency hash drift: {name}")
    for field in ("prompt", "schema"):
        path = ROOT / str(cfg["semantic_contract"][field])
        expected = str(cfg["semantic_contract"][f"{field}_sha256"])
        if sha_file(path) != expected:
            raise RuntimeError(f"semantic {field} hash drift")


def run() -> dict[str, Any]:
    cfg = load(CONFIG)
    verify_pins(cfg)
    public_manifest = load(ROOT / str(cfg["parents"]["public_story_manifest"]["path"]))
    pool_manifest = load(ROOT / str(cfg["parents"]["condition_pair_pools"]["path"]))
    input_audit = load(ROOT / str(cfg["parents"]["public_input_audit"]["path"]))
    preflight = load(ROOT / str(cfg["parents"]["provider_preflight"]["path"]))
    preflight_audit = load(ROOT / str(cfg["parents"]["provider_preflight_audit"]["path"]))
    statistical_audit = load(ROOT / str(cfg["parents"]["statistical_execution_audit"]["path"]))
    protocol = load(ROOT / str(cfg["parents"]["semantic_protocol"]["path"]))
    if input_audit.get("status") != "PASS" or preflight.get("status") != "PASS" or preflight_audit.get("status") != "PASS_PROVIDER_PREFLIGHT":
        raise RuntimeError("input or provider preflight audit is not PASS")
    if statistical_audit.get("status") != "PASS_STATISTICAL_EXECUTION" or statistical_audit.get("complete_jobs") != 6180:
        raise RuntimeError("statistical parent audit is not complete")
    if protocol["semantic_contract"]["model_snapshot"] != cfg["semantic_contract"]["model_snapshot"] or protocol["semantic_contract"]["reasoning_effort"] != cfg["semantic_contract"]["reasoning_effort"]:
        raise RuntimeError("model or reasoning effort differs from frozen protocol")
    if preflight.get("model") != cfg["semantic_contract"]["model_snapshot"] or preflight.get("reasoning_effort") != cfg["semantic_contract"]["reasoning_effort"]:
        raise RuntimeError("provider preflight differs from semantic contract")
    if preflight.get("truncation") != "disabled" or preflight.get("context_limit_check") != "provider_completed_without_truncation":
        raise RuntimeError("provider preflight did not clear context gate")
    expected_scenes = [f"P1V4SD{i:03d}" for i in range(30)]
    story_by_key = {(r["study_id"], r["variant"]): r for r in public_manifest["records"]}
    pool_by_scene = {r["study_id"]: r for r in pool_manifest["records"]}
    if len(story_by_key) != 60 or len(pool_by_scene) != 30:
        raise RuntimeError("public story/pool cardinality mismatch")
    plan_items: list[dict[str, Any]] = []
    for scene in expected_scenes:
        pool = pool_by_scene.get(scene)
        if pool is None:
            raise RuntimeError(f"missing pair pool {scene}")
        pairs = pool.get("shared_union_pairs")
        if not isinstance(pairs, list) or not pairs or len(pairs) > int(cfg["scope"]["max_pairs_per_scene"]):
            raise RuntimeError(f"invalid pair pool {scene}")
        pair_ids = [pair.get("pair_id") for pair in pairs]
        if len(pair_ids) != len(set(pair_ids)) or any(not item for item in pair_ids):
            raise RuntimeError(f"pair identity mismatch {scene}")
        pool_sha = hashlib.sha256(line(pool)).hexdigest().upper()
        for variant in cfg["scope"]["story_variants"]:
            story = story_by_key.get((scene, variant))
            if story is None:
                raise RuntimeError(f"missing public story {scene}/{variant}")
            for prompt_id in cfg["semantic_contract"]["prompt_variants"]:
                plan_items.append({
                    "logical_id": f"{scene}/{variant}/{prompt_id}", "study_id": scene, "variant": variant,
                    "prompt_id": prompt_id, "story_artifact_path": story["artifact_path"],
                    "story_content_sha256": story["content_sha256"], "pair_pool_sha256": pool_sha,
                    "pair_ids": pair_ids, "pair_count": len(pair_ids),
                    "model_snapshot": cfg["semantic_contract"]["model_snapshot"], "reasoning_effort": cfg["semantic_contract"]["reasoning_effort"],
                })
    if len(plan_items) != int(cfg["scope"]["expected_logical_calls"]):
        raise RuntimeError("logical semantic workload mismatch")
    cache_root = ROOT / str(cfg["runtime"]["cache_root"])
    cache_existing = sorted(str(item.relative_to(ROOT)).replace("\\", "/") for item in cache_root.rglob("*") if item.is_file()) if cache_root.exists() else []
    if cache_existing:
        raise RuntimeError("semantic cache already exists before authorization")
    plan = {"schema_version": "fourgraph.p1_v4_shared_semantic_execution_plan.v1", "task": cfg["task"], "logical_calls": plan_items,
            "shared_evidence_rule": "one raw response per logical call; reuse only via condition-specific post-response filtering",
            "conditions": cfg["scope"]["conditions_reusing_shared_raw_evidence"]}
    outputs = cfg["outputs"]
    plan_path, checkpoint_path, audit_path, report_path = (ROOT / str(outputs[key]) for key in ("execution_plan", "checkpoint", "audit", "report"))
    for path in (plan_path, checkpoint_path, audit_path, report_path): path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_bytes(line(plan))
    checks = {"exact_30_scenes": sorted(pool_by_scene) == expected_scenes, "sixty_public_inputs": len(story_by_key) == 60,
              "full_partial_only": set(variant for _, variant in story_by_key) == {"full", "partial"},
              "pair_pools_nonempty": all(item["pair_count"] > 0 for item in plan_items),
              "pair_pool_cap": max(item["pair_count"] for item in plan_items) <= 21,
              "exact_360_logical_calls": len(plan_items) == 360,
              "provider_preflight_pass": True, "statistical_execution_frozen": True,
              "no_pre_authorization_semantic_cache": not cache_existing, "oracle_access": False, "holdout_access": False}
    checkpoint = {"schema_version": "fourgraph.p1_v4_shared_semantic_live_authorization_checkpoint.v1", "task": cfg["task"],
                  "status": "PASS_READY_FOR_EXPLICIT_LIVE_AUTHORIZATION" if all(value for key, value in checks.items() if key not in {"oracle_access", "holdout_access"}) else "FAIL",
                  "live_execution_authorized": False, "required_next_action": "explicit_user_live_authorization_for_exact_360_logical_calls",
                  "execution_plan_sha256": sha_file(plan_path), "checks": checks,
                  "frozen_contract": {"model": cfg["semantic_contract"]["model_snapshot"], "reasoning_effort": cfg["semantic_contract"]["reasoning_effort"],
                                      "prompt_sha256": cfg["semantic_contract"]["prompt_sha256"], "schema_sha256": cfg["semantic_contract"]["schema_sha256"],
                                      "truncation": "disabled", "automatic_chunking": "forbidden"},
                  "execution_boundary": {"semantic_api_calls": 0, "oracle_access": 0, "holdout_access": 0, "downstream_reasoner": 0}}
    checkpoint_path.write_bytes(line(checkpoint))
    audit = {"schema_version": "fourgraph.p1_v4_shared_semantic_live_authorization_audit.v1", "task": cfg["task"],
             "status": checkpoint["status"], "checkpoint_sha256": sha_file(checkpoint_path), "execution_plan_sha256": sha_file(plan_path),
             "logical_calls": len(plan_items), "scene_count": 30, "story_inputs": 60, "shared_pair_total": sum(len(pool_by_scene[s]["shared_union_pairs"]) for s in expected_scenes),
             "max_pairs_per_scene": max(len(pool_by_scene[s]["shared_union_pairs"]) for s in expected_scenes), "checks": checks,
             "execution_boundary": checkpoint["execution_boundary"]}
    audit_path.write_bytes(line(audit))
    report_path.write_text(
        "# P1V4 shared semantic live-authorization checkpoint (cau)\n\n"
        f"## Verdict\n\n{checkpoint['status']}. This checkpoint prepares exactly **360** logical study calls; it does **not** itself authorize or execute them.\n\n"
        "## Frozen scope\n\n- 30 P1V4 method-development scenes; Full and Partial public stories only.\n"
        "- One shared raw semantic response for each scene/variant/prompt; outputs are later filtered independently for constrained-BOSS and constrained-FGES.\n"
        "- Nano snapshot, medium reasoning, prompt/schema hashes, disabled truncation, and forbidden automatic chunking are pinned.\n\n"
        "## Boundary\n\nNo semantic study request, Oracle access, holdout access, or downstream reasoner execution occurred.\n",
        encoding="utf-8", newline="\n")
    return audit


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS_READY_FOR_EXPLICIT_LIVE_AUTHORIZATION" else 1)
