"""Run the authorized 40-scene incremental statistical layer, resumably."""
import argparse,hashlib,json,os,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from adapters.tetrad_adapter import TetradAdapter
from adapters.mmpc_adapter import MMPCAdapter
from fourgraph.causalds_scd import SceneData
from fourgraph.p1_generation import standardize
from fourgraph.bootstrap_boss import BootstrapGraphRun,aggregate_bootstrap_graphs,iter_bootstrap_indices,standardize_bootstrap_sample
from fourgraph.partial_graph import PartialGraph,validate_cpdag
from fourgraph.p1_v4_adaptive_ensemble import decide_valid_method_ensemble
PLAN=ROOT/'data/manifests/p1_v4_look160_incremental_statistical_plan.json';AUTH=ROOT/'data/manifests/p1_v4_look160_incremental_statistical_live_authorization.json';MAT=ROOT/'data/manifests/p1_v4_independent_calibration_look160_incremental_materialization.json';OUT=ROOT/'results/raw/p1_v4_independent_calibration/look160_increment/statistical';AUD=ROOT/'data/manifests/p1_v4_look160_incremental_statistical_execution_audit.json';JAR=ROOT/'data/raw/t05/py-tetrad/pytetrad/resources/tetrad-current.jar';JH='5A3BA56ADECE35DA8A209B39DB8B8BF29D4037FB79ED56C4B63F8D3B4C1A7051'
def cb(x):return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sh(x):return hashlib.sha256(x).hexdigest().upper()
def write(p,b):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():
  if p.read_bytes()!=b:raise RuntimeError(f'drift {p}')
  return
 q=p.with_suffix(p.suffix+'.part');q.write_bytes(b);q.replace(p)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--dry-run',action='store_true');ap.add_argument('--execute',action='store_true');ap.add_argument('--audit',action='store_true');a=ap.parse_args()
 if sum((a.dry_run,a.execute,a.audit))!=1:raise SystemExit('choose one mode')
 plan=json.loads(PLAN.read_text());auth=json.loads(AUTH.read_text());jobs=plan['jobs']
 if auth['status']!='PASS_LIVE_STATISTICAL_AUTHORIZATION' or len(jobs)!=8240 or auth['plan_sha256']!=sh(cb(plan)):raise SystemExit('authorization drift')
 raw,norm,err,agg=[OUT/x for x in ('raw','normalized','errors','aggregates')]
 def done(j):return (raw/(j['execution_id']+'.json')).is_file() and (norm/(j['execution_id']+'.json')).is_file()
 if a.dry_run:print(json.dumps({'status':'PASS','planned':8240,'complete':sum(done(j) for j in jobs),'fits_executed':0}));return
 mats=json.loads(MAT.read_text())['records'];meta={x['study_id']:x for x in mats}
 if a.audit:
  complete=sum(done(j) for j in jobs);out={'status':'PASS_STATISTICAL_EXECUTION' if complete==8240 else 'INCOMPLETE','planned_fits':8240,'complete_terminal_records':complete,'error_artifacts':len(list(err.glob('*.json'))),'semantic_api_calls':0,'oracle_access':0,'holdout_access':0};print(json.dumps(out));return
 os.environ['JAVA_HOME']=str(Path(sys.prefix)/'Library/lib/jvm');os.environ['PATH']=str(Path(sys.prefix)/'Library/bin')+os.pathsep+os.environ['PATH']
 tet=TetradAdapter(JAR,JH);mmpc=MMPCAdapter('D:/Coding/R44/R-4.4.3/bin/Rscript.exe',Path('D:/Coding/R44/library'),'5.3-20260901');idx_cache={sid:dict(iter_bootstrap_indices(sid)) for sid in meta}
 def recorded(j):
  x=json.loads((norm/(j['execution_id']+'.json')).read_text());return x.get('status','VALID'),x.get('graph')
 def one(j,allowed=None):
  if done(j):return recorded(j)[0]
  t=time.perf_counter();rec=meta[j['scene_id']];md=json.loads((ROOT/rec['metadata_path']).read_text());v=np.load(ROOT/rec['observation_path'],allow_pickle=False);nodes=md['nodes'];s=SceneData(j['scene_id'],tuple(nodes),(False,)*len(nodes),standardize(v));alg=j['algorithm']
  try:
   if alg=='Bootstrap-BOSS':g,sec=tet.run(SceneData(j['scene_id'],tuple(nodes),(False,)*len(nodes),standardize_bootstrap_sample(v,idx_cache[j['scene_id']][j['repetition']])),'BOSS',{'penalty_discount':1.0,'truncation_limit':3})
   elif alg=='Single-BOSS':g,sec=tet.run(s,'BOSS',{'penalty_discount':1.0,'truncation_limit':3})
   elif alg=='PC':g,sec=tet.run(s,'PC',{'alpha':.01,'depth':-1,'stable_fas':True})
   elif alg=='MMPC':g,sec=mmpc.run(nodes,v,{'test':'zf','alpha':.01,'max_sx':None,'undirected':True})
   elif alg=='FGES':g,sec=tet.run(s,'FGES',{'penalty_discount':1.0,'max_degree':-1,'symmetric_first_step':False,'faithfulness_assumed':False})
   elif alg=='Constrained-BOSS':g,sec=tet.run_constrained(s,'BOSS',{'penalty_discount':1.0,'truncation_limit':3},allowed)
   else:g,sec=tet.run_constrained(s,'FGES',{'penalty_discount':1.0,'max_degree':-1,'symmetric_first_step':False,'faithfulness_assumed':False},allowed)
   body={'job':j,'graph':g,'adapter_seconds':sec,'prevalidation_capture':True};bb=cb(body);write(raw/(j['execution_id']+'.json'),bb)
   try:
    if alg!='MMPC':validate_cpdag(PartialGraph.build(g['nodes'],g['directed'],g['undirected']))
   except ValueError as e:write(norm/(j['execution_id']+'.json'),cb({'job':j,'graph':g,'status':'INVALID_NO_VOTE','validation_error':str(e),'raw_sha256':sh(bb),'input_sha256':md['observation_sha256']}));return 'INVALID_NO_VOTE'
   write(norm/(j['execution_id']+'.json'),cb({'job':j,'graph':g,'status':'VALID','raw_sha256':sh(bb),'input_sha256':md['observation_sha256']}));return 'VALID'
  except Exception as e:write(err/(j['execution_id']+'.json'),cb({'job':j,'error_type':type(e).__name__,'error':str(e)}));raise
 def terminal(j,reason):
  if done(j):return
  b=cb({'job':j,'status':'FAIL_CLOSED_INSUFFICIENT_VALID_METHODS','reason':reason});write(raw/(j['execution_id']+'.json'),b);write(norm/(j['execution_id']+'.json'),cb({'job':j,'status':'FAIL_CLOSED_INSUFFICIENT_VALID_METHODS','reason':reason,'raw_sha256':sh(b)}))
 for j in [x for x in jobs if not x['algorithm'].startswith('Constrained-')]:one(j)
 for sid in [x['study_id'] for x in mats]:
  ss=[j for j in jobs if j['scene_id']==sid];by={(j['algorithm'],j['repetition']):j for j in ss};br=[recorded(by[('Bootstrap-BOSS',i)]) for i in range(200)]
  if all(s=='VALID' for s,_ in br):
   runs=[BootstrapGraphRun(i,PartialGraph.build(g['nodes'],g['directed'],g['undirected'])) for i,(s,g) in enumerate(br)];first=recorded(by[('Single-BOSS',0)])[1];ba=aggregate_bootstrap_graphs(sid,first['nodes'],runs);boot={tuple(x['edge']) for x in ba['edge_evidence'] if x['rates']['adjacency_stability']>=.8}
  else:ba=None;boot=None
  votes={'Bootstrap-BOSS':boot}
  for alg in ('Single-BOSS','PC','MMPC','FGES'):
   s,g=recorded(by[(alg,0)]);votes[alg]=None if s!='VALID' else {tuple(sorted(x)) for x in g['directed']+g['undirected']}
  d=decide_valid_method_ensemble(votes);write(agg/(sid+'.json'),cb({'scene_id':sid,'bootstrap':ba,'valid_methods':list(d.valid_methods),'invalid_methods':list(d.invalid_methods),'ensemble_status':d.status,'allowed_edges':sorted(map(list,d.allowed_edges)),'majority':f'{d.threshold}/{d.denominator}' if d.threshold else None}))
  if d.status.startswith('VALID'):one(by[('Constrained-BOSS',0)],set(d.allowed_edges));one(by[('Constrained-FGES',0)],set(d.allowed_edges))
  else:terminal(by[('Constrained-BOSS',0)],d.status);terminal(by[('Constrained-FGES',0)],d.status)
 complete=sum(done(j) for j in jobs);audit={'status':'PASS_STATISTICAL_EXECUTION' if complete==8240 else 'INCOMPLETE','planned_fits':8240,'complete_terminal_records':complete,'by_algorithm':{x:sum(done(j) and j['algorithm']==x for j in jobs) for x in ('Single-BOSS','Bootstrap-BOSS','PC','MMPC','FGES','Constrained-BOSS','Constrained-FGES')},'invalid_no_vote':sum(json.loads(p.read_text()).get('status')=='INVALID_NO_VOTE' for p in norm.glob('*.json')),'error_artifacts':len(list(err.glob('*.json'))),'execution_boundary':{'semantic_api_calls':0,'oracle_access':False,'holdout_access':False},'semantic_api_calls':0,'oracle_access':0,'holdout_access':0};write(AUD,cb(audit));print(json.dumps(audit))
if __name__=='__main__':main()
