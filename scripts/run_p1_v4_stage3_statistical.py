"""P1V4 Stage-3D statistical-only runner with conservative resume semantics."""
from __future__ import annotations

import argparse, hashlib, json, sys, time
from pathlib import Path
from typing import Any

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from adapters.common import canonical_json, sha256_file
from adapters.mmpc_adapter import MMPCAdapter
from adapters.tetrad_adapter import TetradAdapter
from fourgraph.bootstrap_boss import BootstrapGraphRun, aggregate_bootstrap_graphs, iter_bootstrap_indices, standardize_bootstrap_sample
from fourgraph.causalds_scd import SceneData
from fourgraph.p1_generation import standardize
from materialize_p1_v4_stage3 import load_development_identities, materialize


def sha_bytes(value: bytes) -> str: return hashlib.sha256(value).hexdigest().upper()
def rows(path: Path) -> list[dict[str, Any]]: return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
def cfg(path: Path) -> dict[str, Any]: return yaml.safe_load(path.read_text(encoding="utf-8"))


def bundle(config: dict[str, Any], config_path: Path) -> dict[str, str]:
    paths = [config_path, ROOT / config["authorization_checkpoint"], ROOT / config["preflight"], ROOT / config["identity_manifest"], Path(__file__), ROOT / "scripts/materialize_p1_v4_stage3.py"]
    return {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in paths}


def run_id(job: dict[str, Any]) -> str: return sha_bytes(canonical_json(job))


def base_jobs(config: dict[str, Any], config_path: Path) -> list[dict[str, Any]]:
    identities = load_development_identities(ROOT / config["identity_manifest"]); hashes = bundle(config, config_path); h = sha_bytes(canonical_json(hashes)); jobs=[]
    methods = [("Single-BOSS", 1), ("Bootstrap-BOSS", int(config["parameters"]["bootstrap"]["repetitions"])), ("PC", 1), ("MMPC", 1), ("FGES", 1)]
    for identity in identities:
        for algorithm, repetitions in methods:
            for repetition in range(repetitions):
                item={"scene_id":identity["study_id"],"contract_scene_id":identity["contract_scene_id"],"algorithm":algorithm,"repetition":repetition,"config_hash":h,"dependency_hashes":hashes,"seed":int.from_bytes(hashlib.sha256(f"P1V4|{h}|{identity['study_id']}|{algorithm}|{repetition}".encode()).digest()[:8],"big")}; item["run_id"]=run_id(item); jobs.append(item)
    if len(jobs)!=6120 or len({job['run_id'] for job in jobs})!=6120: raise RuntimeError("base job-plan mismatch")
    return jobs


def constrained_jobs(config: dict[str, Any], config_path: Path) -> list[dict[str, Any]]:
    identities=load_development_identities(ROOT/config["identity_manifest"]); hashes=bundle(config,config_path); h=sha_bytes(canonical_json(hashes)); jobs=[]
    for identity in identities:
        for algorithm in ("Constrained-BOSS","Constrained-FGES"):
            item={"scene_id":identity["study_id"],"contract_scene_id":identity["contract_scene_id"],"algorithm":algorithm,"repetition":0,"config_hash":h,"dependency_hashes":hashes,"seed":int.from_bytes(hashlib.sha256(f"P1V4|{h}|{identity['study_id']}|{algorithm}|0".encode()).digest()[:8],"big")}; item["run_id"]=run_id(item); jobs.append(item)
    return jobs


def complete(config: dict[str, Any], job: dict[str, Any]) -> bool:
    raw=ROOT/config["runtime"]["raw_root"]/f"{job['run_id']}.json"; norm=ROOT/config["runtime"]["normalized_root"]/f"{job['run_id']}.json"; return raw.is_file() and norm.is_file()


def authorized(config: dict[str, Any]) -> None:
    checkpoint=ROOT/config["authorization_checkpoint"]
    if sha256_file(checkpoint)!=config["authorization_checkpoint_sha256"]: raise RuntimeError("authorization checkpoint hash drift")
    value=json.loads(checkpoint.read_text(encoding="utf-8"))
    if value["status"]!="PASS_SCOPED_LIVE_AUTHORIZATION" or not value["authorization"]["materialization_authorized"] or not value["authorization"]["statistical_execution_authorized"]: raise RuntimeError("Stage 3D statistical authorization unavailable")
    if value["authorization"]["semantic_api_calls_authorized"] or value["authorization"]["oracle_access_authorized"] or value["authorization"]["holdout_access_authorized"]: raise RuntimeError("authorization scope drift")
    if int(config["runtime"]["concurrency"])!=1 or config["runtime"]["oracle_access"] or config["runtime"]["holdout_access"] or config["runtime"]["semantic_api_calls"]!=0: raise RuntimeError("statistical execution boundary drift")


def graph_of(normalized: Path) -> dict[str, Any]: return json.loads(normalized.read_text(encoding="utf-8"))["graph"]


def ensemble_allowed(config: dict[str, Any], scene_id: str, jobs: list[dict[str, Any]]) -> tuple[set[tuple[str,str]], dict[str, Any]]:
    by={(job["algorithm"],job["repetition"]):job for job in jobs if job["scene_id"]==scene_id}
    required=["Single-BOSS","PC","MMPC","FGES"]
    if any(not complete(config,by[(name,0)]) for name in required): raise RuntimeError(f"base graph missing: {scene_id}")
    bootstrap=[]
    for repetition in range(200):
        job=by[("Bootstrap-BOSS",repetition)]
        if not complete(config,job): raise RuntimeError(f"bootstrap graph missing: {scene_id}/{repetition}")
        g=graph_of(ROOT/config["runtime"]["normalized_root"]/f"{job['run_id']}.json")
        from fourgraph.partial_graph import PartialGraph
        bootstrap.append(BootstrapGraphRun(repetition,PartialGraph.build(g["nodes"],g["directed"],g["undirected"])))
    first=graph_of(ROOT/config["runtime"]["normalized_root"]/f"{by[('Single-BOSS',0)]['run_id']}.json")
    aggregate=aggregate_bootstrap_graphs(scene_id, first["nodes"], bootstrap)
    threshold=float(config["parameters"]["bootstrap"]["adjacency_stability_method_vote"])
    boot={tuple(row["edge"]) for row in aggregate["edge_evidence"] if float(row["rates"]["adjacency_stability"])>=threshold}
    votes=[boot]
    for name in required:
        graph=graph_of(ROOT/config["runtime"]["normalized_root"]/f"{by[(name,0)]['run_id']}.json")
        votes.append({tuple(sorted(edge)) for edge in graph["directed"]+graph["undirected"]})
    universe=set().union(*votes); allowed={edge for edge in universe if sum(edge in vote for vote in votes)>=3}
    return allowed,{"schema_version":"fourgraph.p1_v4_ensemble_mask.v1","scene_id":scene_id,"bootstrap_adjacency_threshold":threshold,"method_votes":{"Bootstrap-BOSS":sorted(map(list,boot)), **{name:sorted(map(list,votes[index+1])) for index,name in enumerate(required)}},"allowed_edges":sorted(map(list,allowed)),"majority":3,"of":5,"bootstrap_aggregate":aggregate}


def execute(config: dict[str, Any], config_path: Path) -> None:
    authorized(config); identities=load_development_identities(ROOT/config["identity_manifest"])
    generation=json.loads((ROOT/config["preflight"]).read_text(encoding="utf-8"))["generation"]
    scene_root=ROOT/config["runtime"]["scene_root"]; scene_records=materialize(identities,generation,scene_root)
    (scene_root/"manifest.json").write_bytes(canonical_json({"schema_version":"fourgraph.p1_v4_materialized_scene_manifest.v1","records":scene_records}))
    tetrad=TetradAdapter(ROOT/config["environment"]["tetrad_jar"],config["environment"]["tetrad_jar_sha256"]);mmpc=MMPCAdapter(config["environment"]["rscript"],Path(config["environment"]["r_library"]),config["environment"]["bnlearn"])
    raw_root=ROOT/config["runtime"]["raw_root"]; norm_root=ROOT/config["runtime"]["normalized_root"]; error_root=ROOT/config["runtime"]["error_root"]
    for root in (raw_root,norm_root,error_root,ROOT/config["runtime"]["aggregation_root"]): root.mkdir(parents=True,exist_ok=True)
    all_base=base_jobs(config,config_path); by_scene={row["study_id"]:row for row in identities}
    def one(job:dict[str,Any],allowed:set[tuple[str,str]]|None=None)->None:
        if complete(config,job): return
        started=time.perf_counter(); raw=raw_root/f"{job['run_id']}.json"; norm=norm_root/f"{job['run_id']}.json"; err=error_root/f"{job['run_id']}.json"
        try:
            directory=scene_root/job["scene_id"]; metadata=json.loads((directory/"metadata.json").read_text()); values=np.load(directory/"observations.npy",allow_pickle=False)
            if sha256_file(directory/"observations.npy")!=metadata["observation_sha256"]: raise RuntimeError("input hash drift")
            nodes=metadata["nodes"]; scene=SceneData(job["contract_scene_id"],tuple(nodes),tuple(False for _ in nodes),standardize(values)); alg=job["algorithm"]
            if alg=="Bootstrap-BOSS":
                _,idx=next(x for x in iter_bootstrap_indices(job["contract_scene_id"],row_count=2000,sample_size=2000,repetitions=200) if x[0]==job["repetition"]); fit=SceneData(job["contract_scene_id"],tuple(nodes),tuple(False for _ in nodes),standardize_bootstrap_sample(values,idx)); graph,sec=tetrad.run(fit,"BOSS",config["parameters"]["boss"])
            elif alg=="MMPC": graph,sec=mmpc.run(nodes,values,config["parameters"]["mmpc"])
            elif alg=="Single-BOSS": graph,sec=tetrad.run(scene,"BOSS",config["parameters"]["boss"])
            elif alg=="PC": graph,sec=tetrad.run(scene,"PC",config["parameters"]["pc"])
            elif alg=="FGES": graph,sec=tetrad.run(scene,"FGES",config["parameters"]["fges"])
            elif alg=="Constrained-BOSS": graph,sec=tetrad.run_constrained(scene,"BOSS",config["parameters"]["boss"],allowed or set())
            elif alg=="Constrained-FGES": graph,sec=tetrad.run_constrained(scene,"FGES",config["parameters"]["fges"],allowed or set())
            else: raise RuntimeError("unknown algorithm")
            body={"schema_version":"fourgraph.p1_v4_raw_statistical_fit.v1","job":job,"adapter_seconds":sec,"graph":graph}; data=canonical_json(body);raw.write_bytes(data)
            norm.write_bytes(canonical_json({"schema_version":"fourgraph.p1_v4_normalized_statistical_fit.v1","run_id":job["run_id"],"scene_id":job["scene_id"],"algorithm":alg,"input_sha256":metadata["observation_sha256"],"raw_output_sha256":sha_bytes(data),"runtime_seconds":time.perf_counter()-started,"graph":graph,"config_hash":job["config_hash"],"dependency_hashes":job["dependency_hashes"]}))
        except Exception as exc: err.write_bytes(canonical_json({"schema_version":"fourgraph.p1_v4_fit_error.v1","run_id":job["run_id"],"error_type":type(exc).__name__,"error":str(exc),"runtime_seconds":time.perf_counter()-started}))
    for job in all_base: one(job)
    for scene_id in sorted(by_scene):
        allowed,aggregate=ensemble_allowed(config,scene_id,all_base); (ROOT/config["runtime"]["aggregation_root"]/f"{scene_id}.json").write_bytes(canonical_json(aggregate))
        for job in [job for job in constrained_jobs(config,config_path) if job["scene_id"]==scene_id]: one(job,allowed)


def audit(config:dict[str,Any], config_path:Path)->dict[str,Any]:
    base=base_jobs(config,config_path); constrained=constrained_jobs(config,config_path); all_jobs=base+constrained; raw=ROOT/config["runtime"]["raw_root"];norm=ROOT/config["runtime"]["normalized_root"];err=ROOT/config["runtime"]["error_root"]
    complete_jobs=[job for job in all_jobs if (raw/f"{job['run_id']}.json").is_file() and (norm/f"{job['run_id']}.json").is_file()]; errors=[job for job in all_jobs if (err/f"{job['run_id']}.json").is_file()]
    actual={name:sum(job["algorithm"]==name for job in complete_jobs) for name in ("Single-BOSS","Bootstrap-BOSS","PC","MMPC","FGES","Constrained-BOSS","Constrained-FGES")}
    output={
        "schema_version":"fourgraph.p1_v4_stage3_statistical_execution_audit.v1",
        "task":config["task"],
        "status":"PASS_STATISTICAL_EXECUTION" if len(complete_jobs)==6180 and not errors else "FAIL_OR_INCOMPLETE_STATISTICAL_EXECUTION",
        "planned_jobs":6180,
        "complete_jobs":len(complete_jobs),
        "error_jobs":len(errors),
        "jobs_by_algorithm":actual,
        "raw_complete":len([j for j in complete_jobs if (raw / f"{j['run_id']}.json").is_file()]),
        "normalized_complete":len([j for j in complete_jobs if (norm / f"{j['run_id']}.json").is_file()]),
        "aggregation_records":len(list((ROOT/config["runtime"]["aggregation_root"]).glob("P1V4SD*.json"))),
        "execution_boundary":{"semantic_api_calls":0,"oracle_access":False,"holdout_access":False},
        "config_sha256":sha256_file(config_path),
        "execution_binding_sha256":sha256_file(ROOT/config["runtime"]["execution_binding"]) if (ROOT/config["runtime"]["execution_binding"]).is_file() else None,
    }
    (ROOT/config["runtime"]["audit_output"]).write_bytes(canonical_json(output)); return output


def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument("--config",type=Path,default=ROOT/"configs/p1_v4_stage3_statistical_execution.yaml");parser.add_argument("--dry-run",action="store_true");parser.add_argument("--execute",action="store_true");parser.add_argument("--audit",action="store_true");args=parser.parse_args();config=cfg(args.config); base=base_jobs(config,args.config); constrained=constrained_jobs(config,args.config)
    binding={"schema_version":"fourgraph.p1_v4_stage3_statistical_execution_binding.v1","config_sha256":sha256_file(args.config),"runner_sha256":sha256_file(Path(__file__)),"materializer_sha256":sha256_file(ROOT/"scripts/materialize_p1_v4_stage3.py"),"planned_base_jobs":len(base),"planned_constrained_jobs":len(constrained),"planned_total_jobs":len(base)+len(constrained),"oracle_access":False,"holdout_access":False,"semantic_api_calls":0};(ROOT/config["runtime"]["execution_binding"]).parent.mkdir(parents=True,exist_ok=True);(ROOT/config["runtime"]["execution_binding"]).write_bytes(canonical_json(binding));(ROOT/config["runtime"]["plan_output"]).write_bytes(canonical_json({"schema_version":"fourgraph.p1_v4_stage3_statistical_plan.v1","planned_jobs":6180,"base_jobs":base,"constrained_jobs":constrained,"execution_boundary":{"semantic_api_calls":0,"oracle_access":False,"holdout_access":False}}))
    if args.execute: execute(config,args.config)
    result=audit(config,args.config) if args.audit else {"status":"PASS_DRY_RUN","planned_jobs":6180,"materialized_scenes":0,"semantic_api_calls":0,"oracle_access":False,"holdout_access":False}
    print(json.dumps(result,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
