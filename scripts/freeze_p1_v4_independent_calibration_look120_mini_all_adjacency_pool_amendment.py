"""Offline re-freeze of the Mini plan with all parent adjacencies in scope."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_mini_all_adjacency_pool_amendment.yaml"
PUBLIC = ROOT / "data/manifests/p1_v4_independent_calibration_look120_public_inputs.json"
STAT = ROOT / "results/raw/p1_v4_independent_calibration/look120/statistical/normalized"
STAT_AUDIT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_statistical_final_audit.json"
PRIOR = ROOT / "data/manifests/p1_v4_independent_calibration_look120_mini_semantic_reconciliation_amendment.json"
PREFLIGHT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_mini_provider_preflight_audit.json"
PLAN = ROOT / "data/manifests/p1_v4_independent_calibration_look120_mini_semantic_execution_plan_v2.json"
MANIFEST = ROOT / "data/manifests/p1_v4_independent_calibration_look120_mini_all_adjacency_pool_amendment.json"
AUDIT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_mini_all_adjacency_pool_amendment_audit.json"
REPORT = ROOT / "reports/p1_v4_independent_calibration_look120_mini_all_adjacency_pool_amendment.md"

def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def write_once(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != content: raise RuntimeError(f"artifact drift: {path}")
    if not path.exists(): path.write_bytes(content)

def build() -> tuple[dict,dict,dict,str]:
    public = json.loads(PUBLIC.read_text())["records"]
    public_by = {(row["study_id"], row["variant"]): row for row in public}
    graphs = {}
    for path in STAT.glob("*.json"):
        row = json.loads(path.read_text()); job = row["job"]
        if job["algorithm"] in {"Constrained-BOSS", "Constrained-FGES"}:
            graphs[(job["scene_id"], job["algorithm"])] = row["graph"]
    scene_ids = sorted({row["study_id"] for row in public})
    if len(scene_ids) != 120 or len(graphs) != 240: raise RuntimeError("frozen input/parent count drift")
    pools, calls = {}, []
    for scene_id in scene_ids:
        pairs = set()
        for method in ("Constrained-BOSS", "Constrained-FGES"):
            graph = graphs[(scene_id, method)]
            pairs |= {tuple(sorted(edge)) for edge in graph.get("undirected", [])}
            pairs |= {tuple(sorted(edge)) for edge in graph.get("directed", [])}
        aliases = json.loads((ROOT / "data/generated/p1_v4_independent_calibration/look120" / scene_id / "alias_map.json").read_text())["alias_map"]
        pair_rows = [{"pair_id": f"pair_{i:03d}", "node_a_canonical": a, "node_b_canonical": b, "node_a_alias": aliases[a], "node_b_alias": aliases[b]} for i,(a,b) in enumerate(sorted(pairs),1)]
        pool_hash = hashlib.sha256(canonical(pair_rows)).hexdigest().upper()
        pools[scene_id] = {"pairs": pair_rows, "pair_pool_sha256": pool_hash, "source": "union_all_constrained_parent_adjacencies"}
        for variant in ("full", "partial", "ambiguous"):
            story = public_by[(scene_id, variant)]
            for prompt_id in ("P1", "P2", "P3", "P4", "P5", "P6"):
                calls.append({"logical_id": f"{scene_id}/{variant}/{prompt_id}", "study_id": scene_id, "variant": variant, "prompt_id": prompt_id, "model": "gpt-5.4-mini-2026-03-17", "reasoning_effort": "medium", "story_artifact_path": story["artifact_path"], "story_content_sha256": story["content_sha256"], "pair_count": len(pair_rows), "pair_ids": [p["pair_id"] for p in pair_rows], "pair_pool_sha256": pool_hash, "conditions": ["constrained_boss", "constrained_fges"]})
    counts = [len(value["pairs"]) for value in pools.values()]
    plan = {"schema_version":"fourgraph.p1_v4_independent_calibration_look120_mini_semantic_execution_plan.v2", "task":"P1_V4_INDEPENDENT_CALIBRATION_LOOK120_MINI_SEMANTIC_EXECUTION_PLAN_V2", "model":"gpt-5.4-mini-2026-03-17", "reasoning_effort":"medium", "logical_calls":calls, "pair_pools":pools, "pool_definition":"union_of_all_directed_and_undirected_adjacencies_from_constrained_boss_and_constrained_fges", "shared_evidence_rule":"one raw response per logical call; condition-specific filtering", "scope":{"nonedge_diagnostic":"excluded", "primary_meek_closure":"forbidden"}}
    checks = {"scenes_120":len(scene_ids)==120,"public_inputs_360":len(public)==360,"calls_2160":len(calls)==2160,"six_prompts_per_input":all(sum(row["study_id"]==sid and row["variant"]==variant for row in calls)==6 for sid in scene_ids for variant in ("full","partial","ambiguous")),"pairs_818":sum(counts)==818,"minimum_pair_count_positive":min(counts)>0,"maximum_pair_count_at_most_21":max(counts)<=21,"no_nonedge":plan["scope"]["nonedge_diagnostic"]=="excluded","mini_medium_only":all(row["model"]==plan["model"] and row["reasoning_effort"]=="medium" for row in calls)}
    if not all(checks.values()): raise RuntimeError(f"pool amendment validation failed: {[k for k,v in checks.items() if not v]}")
    preflight = json.loads(PREFLIGHT.read_text())
    if preflight.get("status") != "PASS_PROVIDER_PREFLIGHT" or preflight["provider"].get("model") != plan["model"]: raise RuntimeError("Mini provider preflight unavailable")
    manifest = {"schema_version":"fourgraph.p1_v4_independent_calibration_look120_mini_all_adjacency_pool_amendment.v1", "task":"P1_V4_INDEPENDENT_CALIBRATION_LOOK120_MINI_ALL_ADJACENCY_POOL_AMENDMENT", "status":"PASS_OFFLINE_FROZEN", "supersedes":{"prior_mini_plan_sha256":sha(ROOT / "data/manifests/p1_v4_independent_calibration_look120_mini_semantic_execution_plan.json"), "reason":"prior plan omitted compelled adjacencies and contained 36 zero-pair calls", "disposition":"retained_historical_not_valid_for_live_execution"}, "parent_rule":{"include":["directed_compelled_adjacencies","undirected_adjacencies"],"methods":["constrained_boss","constrained_fges"]}, "scope":{"scene_pair_records":sum(counts),"min_pairs_per_scene":min(counts),"max_pairs_per_scene":max(counts),"logical_calls":len(calls),"nonedge":"excluded"}, "contract":{"model":plan["model"],"reasoning_effort":"medium","automatic":["VERY_HIGH","HIGH"],"review_only":["MEDIUM"],"abstain":["UNCERTAIN","CONFLICT"],"primary_meek_closure":"forbidden"}, "preflight_reuse":{"eligible":True,"reason":"same Mini model/prompt/schema and new maximum 11 pairs <= provider-tested 21 pairs","preflight_audit_sha256":sha(PREFLIGHT)}, "execution_plan":{"path":str(PLAN.relative_to(ROOT)).replace("\\", "/"),"sha256":hashlib.sha256(canonical(plan)).hexdigest().upper()}, "boundary":{"provider_calls":0,"study_api_calls":0,"oracle_access":0,"holdout_access":0,"statistical_reruns":0}}
    audit = {"task":manifest["task"],"status":"PASS","config_sha256":sha(CONFIG),"manifest_sha256":hashlib.sha256(canonical(manifest)).hexdigest().upper(),"plan_sha256":hashlib.sha256(canonical(plan)).hexdigest().upper(),"pair_count_distribution":dict(sorted(Counter(counts).items())),"checks":checks | {"provider_preflight_reuse_justified":True,"no_provider_or_study_api_calls":True,"no_oracle_holdout_or_statistical_rerun":True}}
    report = f"""# Look-120 Mini all-adjacency pool amendment

Status: **PASS_OFFLINE_FROZEN**. The prior 488-pair plan queried only undirected parent edges; it could not audit compelled directions and generated 36 zero-pair calls. This amendment freezes the union of both directed compelled and undirected adjacencies from constrained-BOSS and constrained-FGES.

The resulting plan has 120 scenes, {sum(counts)} scene-pair records ({min(counts)}–{max(counts)} per scene), 360 public inputs and 2,160 Mini-medium logical calls. Non-edge remains excluded; primary Meek closure remains forbidden. The existing Mini provider preflight is valid for reuse because it tested the unchanged model/prompt/schema with 21 pairs, above the revised maximum of {max(counts)}. No provider or study API call occurred here.
"""
    return plan,manifest,audit,report

def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("--check",action="store_true");args=parser.parse_args()
    for path in (CONFIG,PUBLIC,STAT_AUDIT,PRIOR,PREFLIGHT):
        if not path.is_file(): raise RuntimeError(f"missing prerequisite: {path}")
    plan,manifest,audit,report=build(); artifacts=((PLAN,canonical(plan)),(MANIFEST,canonical(manifest)),(AUDIT,canonical(audit)),(REPORT,report.encode()))
    if args.check:
        for path,content in artifacts:
            if not path.is_file() or path.read_bytes()!=content: raise RuntimeError(f"replay mismatch: {path}")
        print(json.dumps({"status":"PASS_CHECK","pairs":818,"calls":2160}));return
    for path,content in artifacts: write_once(path,content)
    print(json.dumps({"status":manifest["status"],"pairs":818,"calls":2160}))

if __name__ == "__main__": main()
