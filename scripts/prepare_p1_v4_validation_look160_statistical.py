"""Freeze the exact 32,960-job validation statistical plan and authorization."""
import hashlib, json
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]; CFG=ROOT/'configs/p1_v4_validation_look160_statistical_execution.yaml'
def cb(x):return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
 c=yaml.safe_load(CFG.read_text(encoding='utf-8'))
 for name,spec in c['parents'].items():
  p=ROOT/spec['path']
  if not p.is_file() or sha(p)!=spec['sha256']:raise RuntimeError(f'parent hash drift: {name}')
 source=yaml.safe_load((ROOT/c['parents']['frozen_statistical_config']['path']).read_text(encoding='utf-8'))
 identities=[json.loads(x) for x in (ROOT/c['parents']['exact_identities']['path']).read_text(encoding='utf-8').splitlines() if x]
 exact=load(ROOT/c['parents']['exact_plan']['path']); mats=load(ROOT/c['parents']['materialization_manifest']['path'])['records']; public=load(ROOT/c['parents']['public_input_manifest']['path'])['records']
 ids=exact['scene_ids_in_execution_order']
 if len(ids)!=160 or [x['study_id'] for x in identities]!=ids or [x['study_id'] for x in mats]!=ids:raise RuntimeError('scene scope/order drift')
 if len(public)!=480 or {(x['study_id'],x['variant']) for x in public}!={(sid,v) for sid in ids for v in ('full','partial','ambiguous')}:raise RuntimeError('public input completeness drift')
 if any(any(x['leakage_check'].values()) for x in public):raise RuntimeError('public input leakage')
 for x in mats:
  if sha(ROOT/x['observation_path'])!=x['observation_sha256']:raise RuntimeError(f'observation drift: {x["study_id"]}')
 params=source['parameters']; algorithms=['Single-BOSS','Bootstrap-BOSS','PC','MMPC','FGES','Constrained-BOSS','Constrained-FGES']
 if params['bootstrap']['repetitions']!=200 or params['ensemble']['normal_rule']!='3_of_5' or params['ensemble']['one_invalid_rule']!='3_of_4':raise RuntimeError('algorithm parameter drift')
 jobs=[]
 for sid in ids:
  for alg in algorithms:
   for rep in range(200 if alg=='Bootstrap-BOSS' else 1):
    seed=int.from_bytes(hashlib.sha256(f'P1V4CAL|{sid}|{alg}|{rep}'.encode()).digest()[:8],'big')
    job={'scene_id':sid,'algorithm':alg,'repetition':rep,'seed':seed};job['execution_id']=hashlib.sha256(cb(job)).hexdigest().upper();jobs.append(job)
 counts={a:sum(x['algorithm']==a for x in jobs) for a in algorithms}
 if len(jobs)!=c['scope']['exact_fits']==32960 or counts!=c['scope']['by_algorithm'] or len({x['execution_id'] for x in jobs})!=32960:raise RuntimeError('job plan cardinality drift')
 plan={'schema_version':'fourgraph.p1_v4_validation_look160_statistical_plan.v1','status':'FROZEN_AUTHORIZED','scene_ids':ids,'parameters':params,'jobs':jobs};body=cb(plan);ph=hashlib.sha256(body).hexdigest().upper()
 auth={'schema_version':'fourgraph.p1_v4_validation_look160_statistical_live_authorization.v1','status':'PASS_LIVE_STATISTICAL_AUTHORIZATION','explicit_user_authorization':True,'plan_sha256':ph,'config_sha256':sha(CFG),'exact_fits':32960,'concurrency':1,'semantic_api_calls':0,'oracle_access':0,'holdout_access':0}
 audit={'status':'PASS_STATISTICAL_PREFLIGHT','planned_fits':32960,'actual_fits':0,'scene_count':160,'by_algorithm':counts,'unique_execution_identities':True,'plan_sha256':ph,'authorization_sha256':hashlib.sha256(cb(auth)).hexdigest().upper(),'semantic_api_calls':0,'oracle_access':0,'holdout_access':0}
 for path,obj in ((ROOT/c['scope']['plan'],plan),(ROOT/c['scope']['authorization'],auth),(ROOT/c['scope']['preflight_audit'],audit)):
  path.parent.mkdir(parents=True,exist_ok=True);data=cb(obj)
  if path.exists() and path.read_bytes()!=data:raise RuntimeError(f'artifact drift: {path}')
  path.write_bytes(data)
 print(json.dumps({'status':audit['status'],'planned':32960,'actual':0}))
if __name__=='__main__':main()
