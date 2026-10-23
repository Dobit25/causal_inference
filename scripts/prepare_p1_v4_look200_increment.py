"""Prepare/materialize/freeze the registered 40-scene look-200 increment."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
from run_p1_v4_independent_calibration_look120_materialization import construct_scene  # noqa: E402

CFG = ROOT / "configs/p1_v4_look200_increment.yaml"


def cb(x: Any) -> bytes:
    return (json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != body:
            raise RuntimeError(f"artifact drift: {path.relative_to(ROOT)}")
        return
    tmp = path.with_name(path.name + ".partial")
    tmp.write_bytes(body)
    tmp.replace(path)


def selected(cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    plan = load(ROOT / cfg["parents"]["identity_plan"])
    all_rows = rows(ROOT / cfg["parents"]["identities"])
    ids = plan["exact_scene_ids_in_execution_order"][cfg["scope"]["index_start"]:cfg["scope"]["index_end"]]
    by_id = {row["study_id"]: row for row in all_rows}
    chosen = [by_id[x] for x in ids]
    if len(chosen) != 40 or len(set(ids)) != 40:
        raise RuntimeError("look-200 exact identity slice drift")
    if any(row["batch_id"] != cfg["scope"]["batch_id"] for row in chosen):
        raise RuntimeError("look-200 batch identity drift")
    return chosen, ids


def freeze_review_and_identities(cfg: dict[str, Any]) -> None:
    results = load(ROOT / cfg["parents"]["look160_results"])
    audit = load(ROOT / cfg["parents"]["look160_audit"])
    if results["status"] != "CONTINUE_TO_REGISTERED_LOOK_200" or audit["status"] != "PASS_ORACLE_SCORING":
        raise RuntimeError("look-160 does not authorize registered look-200 planning")
    primary = results["conditions"]["Constrained-BOSS"]["variants"]
    checks = {
        "look160_oracle_exact": audit["oracle_scenes_accessed"] == 160,
        "full_precision_cs_pass": primary["full"]["precision_confidence_sequence"]["pass"] is True,
        "partial_precision_cs_pass": primary["partial"]["precision_confidence_sequence"]["pass"] is True,
        "full_coverage_pass": primary["full"]["coverage"]["crosses"] is True,
        "partial_coverage_pass": primary["partial"]["coverage"]["crosses"] is True,
        "full_high_guardrail_pending": primary["full"]["High_guardrail"]["pass"] is False,
        "partial_high_guardrail_pending": primary["partial"]["High_guardrail"]["pass"] is False,
        "not_futile": not results["futility"]["full"]["futile"] and not results["futility"]["partial"]["futile"],
        "no_holdout_api_statistical_or_closure": all(audit[k] == 0 for k in ("holdout_access", "semantic_api_calls", "statistical_reruns", "meek_closure")),
    }
    if not all(checks.values()):
        raise RuntimeError(f"look-160 review failed: {[k for k,v in checks.items() if not v]}")
    chosen, ids = selected(cfg)
    identity_body = b"".join(cb(row) for row in chosen)
    review = {
        "schema_version": "fourgraph.p1_v4_look160_review_look200_go_no_go.v1",
        "status": "PASS_CONTINUE_TO_REGISTERED_LOOK_200",
        "decision": "CONTINUE_TO_REGISTERED_LOOK_200",
        "checks": checks,
        "policy_changes": 0,
        "api_calls": 0,
        "oracle_access": 0,
        "holdout_access": 0,
    }
    identity_plan = {
        "schema_version": "fourgraph.p1_v4_look200_incremental_identity_plan.v1",
        "status": "PASS_FROZEN_EXACT_40_IDENTITIES",
        "previous_look": 160,
        "next_look": 200,
        "batch_id": cfg["scope"]["batch_id"],
        "incremental_scene_ids_in_execution_order": ids,
        "cumulative_scene_ids_in_execution_order": load(ROOT / cfg["parents"]["identity_plan"])["exact_scene_ids_in_execution_order"][:200],
        "incremental_identity_sha256": hashlib.sha256(identity_body).hexdigest().upper(),
        "component_seeds_by_scene": {row["study_id"]: row["component_seeds"] for row in chosen},
        "materialization_authorized_by_user": True,
        "statistical_and_semantic_execution_authorized_by_user": True,
    }
    write(ROOT / "data/manifests/p1_v4_look160_result_review_and_look200_go_no_go.json", cb(review))
    write(ROOT / "data/manifests/p1_v4_look200_incremental_exact_identities.jsonl", identity_body)
    write(ROOT / "data/manifests/p1_v4_look200_incremental_exact_identity_plan.json", cb(identity_plan))


def materialize(cfg: dict[str, Any]) -> None:
    chosen, ids = selected(cfg)
    generation = yaml.safe_load((ROOT / cfg["parents"]["generation_contract"]).read_text(encoding="utf-8"))["generation"]
    story_cfg = yaml.safe_load((ROOT / cfg["parents"]["story_protocol"]).read_text(encoding="utf-8"))
    scene_root = ROOT / cfg["roots"]["generated"]
    public_root = ROOT / cfg["roots"]["public"]
    scene_records, story_records = [], []
    for identity in chosen:
        contents, metadata, records = construct_scene(identity, generation, story_cfg)
        sid = identity["study_id"]
        for name in ("observations.npy", "metadata.json", "alias_map.json"):
            write(scene_root / sid / name, contents[name])
        for record in records:
            path = public_root / sid / f"story_{record['variant']}.json"
            write(path, contents[f"story_{record['variant']}.json"])
            record["artifact_path"] = path.relative_to(ROOT).as_posix()
        scene_records.append({
            "study_id": sid,
            "scene_id": identity["contract_scene_id"],
            "observation_path": (scene_root / sid / "observations.npy").relative_to(ROOT).as_posix(),
            "metadata_path": (scene_root / sid / "metadata.json").relative_to(ROOT).as_posix(),
            "alias_map_path": (scene_root / sid / "alias_map.json").relative_to(ROOT).as_posix(),
            "observation_sha256": metadata["observation_sha256"],
            "scm_commitment_sha256": metadata["scm_commitment_sha256"],
        })
        story_records.extend(records)
    manifest = {"schema_version": "fourgraph.p1_v4_look200_materialization.v1", "records": scene_records}
    public = {"schema_version": "fourgraph.p1_v4_look200_public_inputs.v1", "records": story_records}
    write(ROOT / "data/manifests/p1_v4_look200_incremental_materialization.json", cb(manifest))
    write(ROOT / "data/manifests/p1_v4_look200_incremental_public_inputs.json", cb(public))
    audit = {
        "status": "PASS_MATERIALIZATION",
        "scenes": len(scene_records), "stories": len(story_records),
        "variant_counts": {v: sum(r["variant"] == v for r in story_records) for v in ("full", "partial", "ambiguous")},
        "exact_ids": [r["study_id"] for r in scene_records] == ids,
        "semantic_api_calls": 0, "oracle_access": 0, "holdout_access": 0,
    }
    if not (audit["scenes"] == 40 and audit["stories"] == 120 and audit["exact_ids"] and all(x == 40 for x in audit["variant_counts"].values())):
        raise RuntimeError("look-200 materialization audit failed")
    write(ROOT / "data/manifests/p1_v4_look200_incremental_materialization_audit.json", cb(audit))


def statistical_plan(cfg: dict[str, Any]) -> None:
    mat = load(ROOT / "data/manifests/p1_v4_look200_incremental_materialization.json")
    ids = [r["study_id"] for r in mat["records"]]
    jobs = []
    for sid in ids:
        for alg, reps in (("Single-BOSS",1),("Bootstrap-BOSS",200),("PC",1),("MMPC",1),("FGES",1),("Constrained-BOSS",1),("Constrained-FGES",1)):
            for rep in range(reps):
                base = {"scene_id":sid,"algorithm":alg,"repetition":rep,"seed":int.from_bytes(hashlib.sha256(f"P1V4CAL|{sid}|{alg}|{rep}".encode()).digest()[:8],"big")}
                base["execution_id"] = hashlib.sha256(cb(base)).hexdigest().upper(); jobs.append(base)
    plan = {"schema_version":"fourgraph.p1_v4_look200_statistical_plan.v1","status":"FROZEN_AUTHORIZED","scene_ids":ids,"parameters":yaml.safe_load((ROOT/"configs/p1_v4_look160_incremental_statistical_execution.yaml").read_text())["parameters"],"jobs":jobs}
    auth = {"status":"PASS_LIVE_STATISTICAL_AUTHORIZATION","plan_sha256":hashlib.sha256(cb(plan)).hexdigest().upper(),"exact_fits":8240,"concurrency":1,"semantic_api_calls":0,"oracle_access":0,"holdout_access":0}
    if len(jobs) != 8240 or len({j["execution_id"] for j in jobs}) != 8240:
        raise RuntimeError("statistical plan count drift")
    write(ROOT/"data/manifests/p1_v4_look200_incremental_statistical_plan.json",cb(plan))
    write(ROOT/"data/manifests/p1_v4_look200_incremental_statistical_live_authorization.json",cb(auth))
    write(ROOT/"data/manifests/p1_v4_look200_incremental_statistical_preflight_audit.json",cb({"status":"PASS","planned_fits":8240,"actual_fits":0,"unique":True,"api_calls":0,"oracle_access":0,"holdout_access":0}))


def semantic_plan(cfg: dict[str, Any]) -> None:
    stat_audit = load(ROOT/"data/manifests/p1_v4_look200_incremental_statistical_execution_audit.json")
    if stat_audit.get("status") != "PASS_STATISTICAL_EXECUTION" or stat_audit.get("complete_terminal_records") != 8240:
        raise RuntimeError("look-200 statistical execution incomplete")
    pub = load(ROOT/"data/manifests/p1_v4_look200_incremental_public_inputs.json")["records"]
    by_story = {(r["study_id"],r["variant"]):r for r in pub}
    ids = sorted({r["study_id"] for r in pub})
    norm = ROOT/cfg["roots"]["statistical"]/"normalized"
    graphs = {}
    for p in norm.glob("*.json"):
        r=load(p); j=r["job"]
        if j["algorithm"] in {"Constrained-BOSS","Constrained-FGES"}:
            if r.get("status") != "VALID": raise RuntimeError(f"invalid constrained parent: {j}")
            graphs[(j["scene_id"],j["algorithm"])]=r["graph"]
    pools,calls={},[]
    for sid in ids:
        pairs=set()
        for alg in ("Constrained-BOSS","Constrained-FGES"):
            g=graphs[(sid,alg)]; pairs |= {tuple(sorted(e)) for e in g.get("directed",[])+g.get("undirected",[])}
        aliases=load(ROOT/cfg["roots"]["generated"]/sid/"alias_map.json")["alias_map"]
        pr=[{"pair_id":f"pair_{i:03d}","node_a_canonical":a,"node_b_canonical":b,"node_a_alias":aliases[a],"node_b_alias":aliases[b]} for i,(a,b) in enumerate(sorted(pairs),1)]
        ph=hashlib.sha256(cb(pr)).hexdigest().upper();pools[sid]={"pairs":pr,"pair_pool_sha256":ph,"source":"union_all_constrained_parent_adjacencies"}
        for variant in ("full","partial"):
            story=by_story[(sid,variant)]
            for prompt in ("P1","P2","P3","P4","P5","P6"):
                calls.append({"logical_id":f"{sid}/{variant}/{prompt}","study_id":sid,"variant":variant,"prompt_id":prompt,"model":cfg["semantic"]["model"],"reasoning_effort":"medium","story_artifact_path":story["artifact_path"],"story_content_sha256":story["content_sha256"],"pair_count":len(pr),"pair_ids":[x["pair_id"] for x in pr],"pair_pool_sha256":ph,"conditions":["constrained_boss","constrained_fges"]})
    plan={"schema_version":"fourgraph.p1_v4_look200_mini_semantic_plan.v1","status":"FROZEN","model":cfg["semantic"]["model"],"reasoning_effort":"medium","logical_calls":calls,"pair_pools":pools,"story_variants":["full","partial"],"ambiguous_increment":"excluded_by_fixed_diagnostic_subset","nonedge":"excluded","primary_meek_closure":"forbidden"}
    counts=[len(x["pairs"]) for x in pools.values()]
    if len(calls)!=480 or len(pools)!=40 or min(counts)<1 or max(counts)>21: raise RuntimeError("semantic plan drift")
    write(ROOT/"data/manifests/p1_v4_look200_incremental_mini_semantic_plan.json",cb(plan))
    write(ROOT/"data/manifests/p1_v4_look200_incremental_mini_semantic_plan_audit.json",cb({"status":"PASS","scenes":40,"logical_calls":480,"scene_pair_records":sum(counts),"min_pairs":min(counts),"max_pairs":max(counts),"api_calls":0,"oracle_access":0,"holdout_access":0}))


def main() -> int:
    ap=argparse.ArgumentParser();ap.add_argument("stage",choices=("freeze","materialize","stat-plan","semantic-plan","all-offline"));a=ap.parse_args()
    cfg=yaml.safe_load(CFG.read_text(encoding="utf-8"))
    stages=("freeze","materialize","stat-plan") if a.stage=="all-offline" else (a.stage,)
    for stage in stages:
        {"freeze":freeze_review_and_identities,"materialize":materialize,"stat-plan":statistical_plan,"semantic-plan":semantic_plan}[stage](cfg)
    print(json.dumps({"status":"PASS","stage":a.stage}))
    return 0

if __name__=="__main__": raise SystemExit(main())
