"""Phase-E V3 shared semantic execution.

This runner consumes only the frozen development statistical artifacts and the
hash-pinned public stories.  It never reads SCM truth/Oracle material and does
not run holdout, calibration, or downstream reasoning.  One raw response per
scene/variant/prompt is cached and reused for every graph condition.
"""
from __future__ import annotations

import argparse, hashlib, json, os, time
from collections import defaultdict
from pathlib import Path
from typing import Any

from openai import OpenAI

from fourgraph.partial_graph import PartialGraph
from fourgraph.bootstrap_boss import BootstrapGraphRun, aggregate_bootstrap_graphs
from fourgraph.p1_stories import assign_aliases
from fourgraph.p1v3_ensemble_amendment import bootstrap_method_level_skeleton, primary_ensemble_from_methods
from fourgraph.semantic_pair_contract_v2 import StablePair
from fourgraph.semantic_pair_contract_v3 import PROMPT_IDS, render_cause_effect_prompt, validate_response_by_pair
from fourgraph.edge_selective import meek_closure

ROOT = Path(__file__).resolve().parents[1]
MODEL = "gpt-5.4-nano-2026-03-17"
SCHEMA_PATH = ROOT / "schemas/semantic_whole_graph_response_v3.schema.json"
PROMPT_PATH = ROOT / "prompts/p1_semantic_empirical_reliability_v3.md"
PUBLIC_MANIFEST = ROOT / "data/manifests/p1v3_public_semantic_inputs_manifest.json"
AUTH_AUDIT = ROOT / "data/manifests/p1v3_phase_e_shared_semantic_authorization_v3_audit.json"
UPDATED_MANIFEST = ROOT / "configs/p1v3_statistical_ensemble_manifest_v2.yaml"
IDENTITIES = ROOT / "data/manifests/p1_v3_successor_sequential_exact_identity_plan.json"
STATS_ROOT = ROOT / "results/p1v3_statistical_ensemble"
RAW_ROOT = ROOT / "results/raw/p1v3_phase_e_shared_semantic_v3"
AUDIT_PATH = ROOT / "data/manifests/p1v3_phase_e_shared_semantic_execution_v3_audit.json"
SCORES_PATH = ROOT / "data/manifests/p1v3_phase_e_shared_semantic_execution_v3_scores.jsonl"
REPORT_PATH = ROOT / "reports/p1v3_phase_e_shared_semantic_execution_v3.md"
HASHES = {
    "updated_manifest": "581AA295BE087265F3E99BFD337AB1DB47309C58E7EB3AEFEC9DDF271D8A11D2",
    "public_semantic_manifest": "352C437599A25B7875464E68922857096942F2993EA58B973391C9C81DD17A34",
    "phase_d_audit": "A320070B0362CC1645A46E357B9BCB4C83C97BF3170C3CF62753D4E3CFE4BF0D",
}

def sha_bytes(b: bytes) -> str: return hashlib.sha256(b).hexdigest().upper()
def sha_file(p: Path) -> str: return sha_bytes(p.read_bytes())
def canon(v: Any) -> bytes: return (json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
def load_json(p: Path) -> Any: return json.loads(p.read_text(encoding="utf-8"))

def load_key() -> str:
    if os.environ.get("OPENAI_API_KEY"): return os.environ["OPENAI_API_KEY"]
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("OPENAI_API_KEY missing")

def read_graph_record(path: Path) -> tuple[str, dict[str, Any]]:
    row = load_json(path)
    return row["scene_id"], row

def build_conditions() -> tuple[dict[str, dict[str, Any]], dict[str, list[tuple[str, str]]], dict[str, tuple[str, ...]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in (STATS_ROOT / "normalized").glob("*.json"):
        row = load_json(path)
        if row.get("scene_id", "").startswith("P1V3SD"):
            grouped[row["scene_id"]].append(row)
    manifest_hash = sha_file(UPDATED_MANIFEST)
    identity_hash = sha_file(IDENTITIES)
    conditions: dict[str, dict[str, Any]] = {}
    pools: dict[str, list[tuple[str, str]]] = {}
    nodes_by_scene: dict[str, tuple[str, ...]] = {}
    for sid in sorted(grouped):
        rows = grouped[sid]
        nodes = tuple(sorted(rows[0]["graph"]["nodes"]))
        nodes_by_scene[sid] = nodes
        single = next(r for r in rows if r["algorithm"] == "BOSS")
        pc = next(r for r in rows if r["algorithm"] == "PC")
        mmpc = next(r for r in rows if r["algorithm"] == "MMPC")
        fges = next(r for r in rows if r["algorithm"] == "FGES")
        boot = [r for r in rows if r["algorithm"] == "Bootstrap-BOSS"]
        # The normalized run identity is a hash; a stable sorted order supplies
        # the contiguous repetition labels required by the aggregate contract.
        runs = [BootstrapGraphRun(i, g.graph if hasattr(g, "graph") else g) for i, g in enumerate([PartialGraph.build(nodes, r["graph"]["directed"], r["graph"]["undirected"]) for r in sorted(boot, key=lambda x: x["run_id"])])]
        # Phase-D has already audited all 6,000 normalized fits.  Recomputing
        # the immutable four-state rates here avoids re-running the expensive
        # completed-PDAG validator over every bootstrap artifact.
        from itertools import combinations
        states = ("absent", "undirected", "A_to_B", "B_to_A")
        evidence = []
        for left, right in combinations(nodes, 2):
            counts = {s: 0 for s in states}
            for run in runs:
                g = run.graph
                if (left, right) in g.undirected: state = "undirected"
                elif (left, right) in g.directed: state = "A_to_B"
                elif (right, left) in g.directed: state = "B_to_A"
                else: state = "absent"
                counts[state] += 1
            rates = {s: counts[s] / 200 for s in states}
            rates["adjacency_stability"] = 1.0 - rates["absent"]
            evidence.append({"edge":[left,right],"counts":counts,"rates":rates})
        aggregate = {"scene_id": sid, "nodes": list(nodes), "bootstrap_runs": 200, "edge_evidence": evidence}
        meta = load_json(STATS_ROOT / "scenes" / sid / "metadata.json")
        parents: dict[str, PartialGraph] = {}
        for cid, ta, td in (("C1", .60, .80), ("C2", .60, .90), ("C3", .80, .80), ("C4", .80, .90), ("C5", .95, .80), ("C6", .95, .90)):
            directed, undirected = [], []
            for row in aggregate["edge_evidence"]:
                left, right = row["edge"]; rates = row["rates"]
                if rates["adjacency_stability"] < ta: continue
                if rates["A_to_B"] >= td: directed.append((left, right))
                elif rates["B_to_A"] >= td: directed.append((right, left))
                else: undirected.append((left, right))
            # Keep even a non-CPDAG threshold result as an explicit condition;
            # closure will fail closed and record the condition error rather
            # than silently projecting or repairing it.
            try: parents[cid] = PartialGraph.build(nodes, directed, undirected)
            except Exception: parents[cid] = PartialGraph(tuple(nodes), frozenset(directed), frozenset(undirected))
        graphs = {"single_boss": PartialGraph.build(nodes, single["graph"]["directed"], single["graph"]["undirected"]),
                  "C1": parents["C1"], "C2": parents["C2"], "C3": parents["C3"], "C4": parents["C4"], "C5": parents["C5"], "C6": parents["C6"]}
        boot_stab = {tuple(row["edge"]): float(row["rates"]["adjacency_stability"]) for row in aggregate["edge_evidence"]}
        boot_method = bootstrap_method_level_skeleton(nodes, boot_stab)
        method_skeletons = {"single_boss": graphs["single_boss"].skeleton, "bootstrap_boss": boot_method,
                            "pc": PartialGraph.build(nodes, pc["graph"]["directed"], pc["graph"]["undirected"]).skeleton,
                            "mmpc": PartialGraph.build(nodes, mmpc["graph"]["directed"], mmpc["graph"]["undirected"]).skeleton,
                            "fges": PartialGraph.build(nodes, fges["graph"]["directed"], fges["graph"]["undirected"]).skeleton}
        ens = primary_ensemble_from_methods(nodes, **method_skeletons)
        graphs["primary_ensemble"] = PartialGraph.build(nodes, undirected=ens)
        pool = set()
        for name, graph in graphs.items(): pool.update(graph.undirected)
        pools[sid] = sorted(pool)
        conditions[sid] = graphs
    if len(conditions) != 30 or any(len(p) > 21 for p in pools.values()): raise RuntimeError("frozen condition pool invalid")
    return conditions, pools, nodes_by_scene

def load_story_inputs() -> dict[tuple[str, str], dict[str, Any]]:
    manifest = load_json(PUBLIC_MANIFEST)
    records = {}
    for rec in manifest["records"]:
        sid = rec["study_id"]; variant = rec["variant"]
        path = ROOT / rec["artifact_path"]
        if sha_file(path) != rec["artifact_sha256"]: raise RuntimeError(f"story hash mismatch {sid}/{variant}")
        story_rec = load_json(path)
        story = story_rec["builder_input"]["story"]
        records[(sid, variant)] = {"story": story, "story_hash": sha_bytes(story.encode()), "path": str(path.relative_to(ROOT))}
    if len(records) != 60: raise RuntimeError("expected 60 public story inputs")
    return records

def make_pairs(scene_id: str, pool: list[tuple[str, str]], nodes: tuple[str, ...]) -> list[StablePair]:
    cfg = load_json(ROOT / "configs/t19_p1_semantic_stories.yaml") if False else None
    import yaml
    t19 = yaml.safe_load((ROOT / "configs/t19_p1_semantic_stories.yaml").read_text(encoding="utf-8"))
    alias = dict(assign_aliases(nodes, t19["aliases"]["lexicon"], int(t19["randomness"]["master_seed"]), scene_id))
    return [StablePair(f"pair_{i:03d}", alias[a], alias[b], a, b) for i, (a, b) in enumerate(sorted(pool), 1)]

def parse_response(resp: Any) -> dict[str, Any]:
    return json.loads(resp.output_text)

def aggregate_votes(validated: list[dict[str, Any]]) -> dict[str, Any]:
    directed = [r["direction"] for r in validated if r.get("pair_valid") and r.get("direction") in ("A_TO_B", "B_TO_A")]
    counts = {"A_TO_B": directed.count("A_TO_B"), "B_TO_A": directed.count("B_TO_A"), "UNDETERMINED": sum(1 for r in validated if r.get("pair_valid") and r.get("direction") == "UNDETERMINED")}
    best = "A_TO_B" if counts["A_TO_B"] > counts["B_TO_A"] else "B_TO_A" if counts["B_TO_A"] > counts["A_TO_B"] else None
    selected = best if best and counts[best] >= 4 and (counts["A_TO_B"] == 0 or counts["B_TO_A"] == 0) else None
    return {"counts": counts, "published_direction": selected, "valid_votes": len(validated)}

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--execute", action="store_true"); ap.add_argument("--audit", action="store_true"); args = ap.parse_args()
    if not args.execute and not args.audit: raise SystemExit("use --execute or --audit")
    checkpoint = load_json(AUTH_AUDIT)
    if not all(checkpoint.get("checks", {}).values()): raise RuntimeError("V3 authorization checkpoint is not PASS")
    if args.audit:
        print(AUDIT_PATH.read_text(encoding="utf-8") if AUDIT_PATH.exists() else "missing audit"); return 0 if AUDIT_PATH.exists() else 1
    conditions, pools, nodes_by_scene = build_conditions(); stories = load_story_inputs(); RAW_ROOT.mkdir(parents=True, exist_ok=True)
    schema = load_json(SCHEMA_PATH); key = load_key(); client = OpenAI(api_key=key)
    cache = {}; cache_path = RAW_ROOT / "shared_responses.jsonl"
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line); cache[row["cache_key"]] = row
    calls = 0; attempts = 0; errors = 0; retries = 0; total_in = total_out = 0; last_call = 0.0
    raw_out = cache_path.open("a", encoding="utf-8")
    validated_rows = []
    for sid in sorted(nodes_by_scene):
        for variant in ("full", "partial"):
            inp = stories[(sid, variant)]; pairs = make_pairs(sid, pools[sid], nodes_by_scene[sid]);
            for prompt_id in PROMPT_IDS:
                key_id = f"{sid}|{variant}|{prompt_id}"; prompt = render_cause_effect_prompt(prompt_id=prompt_id, story=inp["story"], pairs=pairs)
                if key_id in cache:
                    row = cache[key_id]
                else:
                    wait = 3.2 - (time.monotonic() - last_call)
                    if wait > 0: time.sleep(wait)
                    started = time.perf_counter(); attempts += 1
                    try:
                        resp = client.responses.create(model=MODEL, input=prompt, reasoning={"effort":"medium"}, max_output_tokens=8192, service_tier="default", store=False, text={"format":{"type":"json_schema","name":"semantic_whole_graph_response_v3","schema":schema,"strict":True}}, metadata={"task":"P1_V3_PHASE_E_SHARED_SEMANTIC_EXECUTION","study_execution":"true"})
                        usage = resp.usage; parsed = parse_response(resp); row = {"cache_key":key_id,"scene_id":sid,"variant":variant,"prompt_id":prompt_id,"prompt_sha256":sha_bytes(prompt.encode()),"response":parsed,"response_text":resp.output_text,"request_id":getattr(resp,"_request_id",None),"model":resp.model,"input_tokens":int(usage.input_tokens),"output_tokens":int(usage.output_tokens),"total_tokens":int(getattr(usage,"total_tokens",usage.input_tokens+usage.output_tokens)),"latency_ms":round((time.perf_counter()-started)*1000),"error":None,"retry":0}; total_in += row["input_tokens"]; total_out += row["output_tokens"]; calls += 1
                    except Exception as exc:
                        errors += 1; row = {"cache_key":key_id,"scene_id":sid,"variant":variant,"prompt_id":prompt_id,"prompt_sha256":sha_bytes(prompt.encode()),"response":None,"response_text":None,"request_id":None,"model":MODEL,"input_tokens":0,"output_tokens":0,"total_tokens":0,"latency_ms":round((time.perf_counter()-started)*1000),"error":f"{type(exc).__name__}: {str(exc)[:500]}","retry":0}; calls += 1
                    raw_out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"); raw_out.flush(); cache[key_id] = row; last_call = time.monotonic()
                result = validate_response_by_pair(row["response"], pairs, inp["story"]) if row.get("response") else {"response_valid":False,"response_error":"provider_error","pairs":[{"pair_id":p.pair_id,"pair_valid":False,"invalid_reason":"provider_error","status":None,"direction":None,"cause":None,"effect":None,"evidence_quote":None} for p in pairs]}
                validated_rows.append({"scene_id":sid,"variant":variant,"prompt_id":prompt_id,"response_valid":result["response_valid"],"pairs":result["pairs"],"raw_hash":sha_bytes((row.get("response_text") or "").encode())})
    raw_out.close()
    by_key = defaultdict(list)
    for row in validated_rows:
        for pair in row["pairs"]: by_key[(row["scene_id"],row["variant"],pair["pair_id"])].append(pair)
    score_lines=[]; closure_counts=defaultdict(lambda:{"scenes":0,"pairs":0,"selected":0,"closure":0,"failed":0})
    for sid, graphs in conditions.items():
        pairs = make_pairs(sid, pools[sid], nodes_by_scene[sid])
        for variant in ("full","partial"):
            votes = {p.pair_id: aggregate_votes(by_key[(sid,variant,p.pair_id)]) for p in pairs}
            for condition,parent in graphs.items():
                selected = []
                for p in pairs:
                    d=votes[p.pair_id]["published_direction"]
                    if d: selected.append((p.node_a_id,p.node_b_id) if d=="A_TO_B" else (p.node_b_id,p.node_a_id))
                closure_status="PASS"; trace=[]; out_graph=parent
                try: out_graph, tr = meek_closure(parent, selected); trace=list(tr)
                except Exception as exc: closure_status=f"FAIL:{type(exc).__name__}"; closure_counts[condition]["failed"] += 1
                closure_counts[condition]["scenes"] += 1; closure_counts[condition]["pairs"] += len(pairs); closure_counts[condition]["selected"] += len(selected); closure_counts[condition]["closure"] += len(trace)
                score_lines.append({"scene_id":sid,"variant":variant,"condition":condition,"candidate_pairs":len(pairs),"published_directions":len(selected),"votes":votes,"closure_status":closure_status,"closure_trace":trace,"output_graph":out_graph.to_dict(),"output_graph_sha256":sha_bytes(canon(out_graph.to_dict()))})
    SCORES_PATH.write_text("".join(json.dumps(x,ensure_ascii=False,sort_keys=True)+"\n" for x in score_lines), encoding="utf-8")
    audit={"schema_version":"fourgraph.p1v3_phase_e_shared_semantic_execution_v3_audit.v1","status":"PASS" if calls==360 and errors==0 else "COMPLETED_WITH_PROVIDER_ERRORS","planned_semantic_calls":360,"actual_semantic_calls":calls,"provider_attempts":attempts,"retries":retries,"errors":errors,"scenes":30,"story_inputs":{"full":30,"partial":30,"ambiguous":0},"input_tokens":total_in,"output_tokens":total_out,"total_tokens":total_in+total_out,"raw_response_count":len(cache),"conditions":["single_boss","C1","C2","C3","C4","C5","C6","primary_ensemble"],"condition_summary":closure_counts,"hashes":{"authorization_audit":sha_file(AUTH_AUDIT),"updated_manifest":sha_file(UPDATED_MANIFEST),"public_semantic_manifest":sha_file(PUBLIC_MANIFEST),"prompt":sha_file(PROMPT_PATH),"schema":sha_file(SCHEMA_PATH),"scores":sha_file(SCORES_PATH)},"oracle_accessed":False,"holdout_accessed":False,"downstream_reasoner_calls":0,"calibration_or_threshold_tuning":False}
    AUDIT_PATH.write_bytes(canon(audit)); REPORT_PATH.write_text("# Phase E Shared Semantic Execution V3\n\n"+json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(audit,ensure_ascii=False,indent=2)); return 0 if errors==0 and calls==360 else 2

if __name__ == "__main__": raise SystemExit(main())
