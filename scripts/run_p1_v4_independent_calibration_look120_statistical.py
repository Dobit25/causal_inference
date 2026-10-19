"""Authorized sequential statistical execution for P1V4 calibration look 120."""
import argparse,hashlib,json,os,sys,time
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'scripts')]
from adapters.tetrad_adapter import TetradAdapter
from adapters.mmpc_adapter import MMPCAdapter
from fourgraph.causalds_scd import SceneData
from fourgraph.p1_generation import standardize
from fourgraph.bootstrap_boss import BootstrapGraphRun,aggregate_bootstrap_graphs,iter_bootstrap_indices,standardize_bootstrap_sample
from fourgraph.partial_graph import PartialGraph,validate_cpdag
from fourgraph.p1_v4_adaptive_ensemble import METHODS, decide_valid_method_ensemble
AUTH=R/'data/manifests/p1_v4_independent_calibration_look120_statistical_execution_authorization.json'; PLAN=R/'data/manifests/p1_v4_independent_calibration_look120_statistical_parent_plan.json'; OUT=R/'results/raw/p1_v4_independent_calibration/look120/statistical'; JAR=R/'data/raw/t05/py-tetrad/pytetrad/resources/tetrad-current.jar';JH='5A3BA56ADECE35DA8A209B39DB8B8BF29D4037FB79ED56C4B63F8D3B4C1A7051'
RESUME_AUTH=R/'data/manifests/p1_v4_independent_calibration_look120_valid_method_ensemble_resume_live_authorization.json'; RESUME_AUDIT=R/'data/manifests/p1_v4_independent_calibration_look120_valid_method_ensemble_resume_dry_run_audit.json'
def cb(x):return(json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sh(x):return hashlib.sha256(x).hexdigest().upper()
def write(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():
  if p.read_bytes()!=x:raise RuntimeError(f'drift {p}')
  return False
 q=p.with_suffix(p.suffix+'.part');q.write_bytes(x);q.replace(p);return True
def main():
 a=argparse.ArgumentParser();a.add_argument('--dry-run',action='store_true');a.add_argument('--execute',action='store_true');a.add_argument('--audit',action='store_true');args=a.parse_args()
 if sum((args.dry_run,args.execute,args.audit))!=1:raise SystemExit('choose one mode')
 au=json.loads(AUTH.read_text());plan=json.loads(PLAN.read_text());
 if au['status']!='PASS_LIVE_STATISTICAL_AUTHORIZATION' or len(plan['jobs'])!=24720:raise SystemExit('authorization/plan invalid')
 raw=OUT/'raw';norm=OUT/'normalized';err=OUT/'errors';agg=OUT/'aggregates'
 ids={j['execution_id'] for j in plan['jobs']}; raw_ids={p.stem for p in raw.glob('*.json')}; norm_ids={p.stem for p in norm.glob('*.json')}
 if args.dry_run: print(json.dumps({'status':'PASS_DRY_RUN','planned_fits':24720,'already_terminal_records':len(raw_ids&norm_ids),'executed_fits':0,'api_calls':0}));return
 if args.audit:
  audit={'task':'P1_V4_INDEPENDENT_CALIBRATION_LOOK120_VALID_METHOD_ENSEMBLE_RESUME_DRY_RUN','status':'PASS' if raw_ids==norm_ids and raw_ids.issubset(ids) and len(raw_ids)==2037 and len(list(err.glob('*.json')))==1 else 'FAIL','planned_execution_identities':24720,'terminal_raw_normalized_pairs':len(raw_ids),'raw_normalized_id_sets_equal':raw_ids==norm_ids,'unknown_execution_identities':len(raw_ids-ids),'existing_error_artifacts':len(list(err.glob('*.json'))),'statistical_fits_executed':0,'semantic_api_calls':0,'oracle_access':0,'holdout_access':0}
  write(RESUME_AUDIT,cb(audit));print(json.dumps(audit));return
 if not RESUME_AUTH.is_file():raise SystemExit('valid-method resume live authorization missing')
 rau=json.loads(RESUME_AUTH.read_text())
 if rau.get('status')!='PASS_VALID_METHOD_ENSEMBLE_RESUME_AUTHORIZATION':raise SystemExit('valid-method resume is not authorized')
 os.environ['JAVA_HOME']=str(Path(sys.prefix)/'Library/lib/jvm');os.environ['PATH']=str(Path(sys.prefix)/'Library/bin')+os.pathsep+os.environ['PATH']
 tet=TetradAdapter(JAR,JH);mmpc=MMPCAdapter('D:/Coding/R44/R-4.4.3/bin/Rscript.exe',Path('D:/Coding/R44/library'),'5.3-20260901')
 mats=json.loads((R/'data/manifests/p1_v4_independent_calibration_look120_materialization.json').read_text())['records'];meta={x['study_id']:x for x in mats};jobs=plan['jobs'];raw=OUT/'raw';norm=OUT/'normalized';err=OUT/'errors';agg=OUT/'aggregates'
 def done(j):return(raw/(j['execution_id']+'.json')).is_file() and (norm/(j['execution_id']+'.json')).is_file()
 def recorded(j):
  value=json.loads((norm/(j['execution_id']+'.json')).read_text())
  return value.get('status','VALID'),value.get('graph')
 def one(j,allowed=None):
  if done(j):return recorded(j)[0]
  t=time.perf_counter();ep=err/(j['execution_id']+'.json')
  try:
   rec=meta[j['scene_id']];d=R/rec['metadata_path'];md=json.loads(d.read_text());v=np.load(R/rec['observation_path'],allow_pickle=False);nodes=md['nodes'];s=SceneData(j['scene_id'],tuple(nodes),(False,)*len(nodes),standardize(v));alg=j['algorithm']
   if alg=='Bootstrap-BOSS':
    idx=idx_cache[j['scene_id']][j['repetition']];g,sec=tet.run(SceneData(j['scene_id'],tuple(nodes),(False,)*len(nodes),standardize_bootstrap_sample(v,idx)),'BOSS',{'penalty_discount':1.0,'truncation_limit':3})
   elif alg=='Single-BOSS':g,sec=tet.run(s,'BOSS',{'penalty_discount':1.0,'truncation_limit':3})
   elif alg=='PC':g,sec=tet.run(s,'PC',{'alpha':.01,'depth':-1,'stable_fas':True})
   elif alg=='MMPC':g,sec=mmpc.run(nodes,v,{'test':'zf','alpha':.01,'max_sx':None,'undirected':True})
   elif alg=='FGES':g,sec=tet.run(s,'FGES',{'penalty_discount':1.0,'max_degree':-1,'symmetric_first_step':False,'faithfulness_assumed':False})
   elif alg=='Constrained-BOSS':g,sec=tet.run_constrained(s,'BOSS',{'penalty_discount':1.0,'truncation_limit':3},allowed)
   else:g,sec=tet.run_constrained(s,'FGES',{'penalty_discount':1.0,'max_degree':-1,'symmetric_first_step':False,'faithfulness_assumed':False},allowed)
   body={'job':j,'graph':g,'adapter_seconds':sec,'prevalidation_capture':True};bb=cb(body);write(raw/(j['execution_id']+'.json'),bb)
   try:
    if alg!='MMPC':validate_cpdag(PartialGraph.build(g['nodes'],g['directed'],g['undirected']))
   except ValueError as e:
    write(norm/(j['execution_id']+'.json'),cb({'job':j,'graph':g,'status':'INVALID_NO_VOTE','validation_error':str(e),'raw_sha256':sh(bb),'runtime_seconds':time.perf_counter()-t,'input_sha256':md['observation_sha256']}));return 'INVALID_NO_VOTE'
   write(norm/(j['execution_id']+'.json'),cb({'job':j,'graph':g,'status':'VALID','raw_sha256':sh(bb),'runtime_seconds':time.perf_counter()-t,'input_sha256':md['observation_sha256']}));return 'VALID'
  except Exception as e:write(ep,cb({'job':j,'error_type':type(e).__name__,'error':str(e)}));raise
 def terminal(j,reason):
  if done(j):return
  body={'job':j,'status':'FAIL_CLOSED_INSUFFICIENT_VALID_METHODS','reason':reason,'prevalidation_capture':False};bb=cb(body);write(raw/(j['execution_id']+'.json'),bb);write(norm/(j['execution_id']+'.json'),cb({'job':j,'status':'FAIL_CLOSED_INSUFFICIENT_VALID_METHODS','reason':reason,'raw_sha256':sh(bb)}))
 idx_cache={sid:dict(iter_bootstrap_indices(sid)) for sid in meta}
 base=[j for j in jobs if not j['algorithm'].startswith('Constrained-')]
 for j in base:one(j)
 for sid in [x['study_id'] for x in mats]:
  ss=[j for j in jobs if j['scene_id']==sid];by={(j['algorithm'],j['repetition']):j for j in ss};bs=[]
  bootstrap_rows=[recorded(by[('Bootstrap-BOSS',i)]) for i in range(200)]
  bootstrap_valid=all(status=='VALID' for status,_ in bootstrap_rows)
  if bootstrap_valid:
   for i,(_,g) in enumerate(bootstrap_rows):bs.append(BootstrapGraphRun(i,PartialGraph.build(g['nodes'],g['directed'],g['undirected'])))
   first=recorded(by[('Single-BOSS',0)])[1];ba=aggregate_bootstrap_graphs(sid,first['nodes'],bs);boot={tuple(x['edge']) for x in ba['edge_evidence'] if x['rates']['adjacency_stability']>=.8}
  else: ba=None;boot=None
  votes={'Bootstrap-BOSS':boot}
  for alg in ('Single-BOSS','PC','MMPC','FGES'):
   status,g=recorded(by[(alg,0)]);votes[alg]=None if status!='VALID' else {tuple(sorted(x)) for x in g['directed']+g['undirected']}
  decision=decide_valid_method_ensemble(votes)
  write(agg/(sid+'.json'),cb({'scene_id':sid,'bootstrap':ba,'valid_methods':list(decision.valid_methods),'invalid_methods':list(decision.invalid_methods),'ensemble_status':decision.status,'allowed_edges':sorted(map(list,decision.allowed_edges)),'majority':f'{decision.threshold}/{decision.denominator}' if decision.threshold else None}))
  if decision.status.startswith('VALID'):
   one(by[('Constrained-BOSS',0)],set(decision.allowed_edges));one(by[('Constrained-FGES',0)],set(decision.allowed_edges))
  else:
   terminal(by[('Constrained-BOSS',0)],decision.status);terminal(by[('Constrained-FGES',0)],decision.status)
 complete=sum(done(j) for j in jobs);errors=len(list(err.glob('*.json')));audit={'status':'PASS' if complete==24720 else 'INCOMPLETE','planned_fits':24720,'complete_terminal_records':complete,'unexpected_error_artifacts':errors,'by_algorithm':{x:sum(done(j) and j['algorithm']==x for j in jobs) for x in ('Single-BOSS','Bootstrap-BOSS','PC','MMPC','FGES','Constrained-BOSS','Constrained-FGES')},'boundary':{'semantic_api_calls':0,'oracle_access':False,'holdout_access':False}};write(OUT/'audit.json',cb(audit));print(json.dumps(audit))
if __name__=='__main__':main()
