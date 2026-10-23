"""Freeze the exact 8,240-fit incremental look-160 statistical plan."""
import argparse, hashlib, json
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/'configs/p1_v4_look160_incremental_statistical_execution.yaml'
def cb(x): return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sh(p): return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def build():
 c=yaml.safe_load(CFG.read_text()); checks={}
 for name,spec in c['parents'].items(): checks[name+'_hash']=sh(ROOT/spec['path'])==spec['sha256']
 m=json.loads((ROOT/c['parents']['materialization_manifest']['path']).read_text()); ids=[r['study_id'] for r in m['records']]
 jobs=[]
 for sid in ids:
  for alg,reps in [('Single-BOSS',1),('Bootstrap-BOSS',200),('PC',1),('MMPC',1),('FGES',1),('Constrained-BOSS',1),('Constrained-FGES',1)]:
   for rep in range(reps):
    b={'scene_id':sid,'algorithm':alg,'repetition':rep,'seed':int.from_bytes(hashlib.sha256(f'P1V4CAL|{sid}|{alg}|{rep}'.encode()).digest()[:8],'big')};b['execution_id']=hashlib.sha256(cb(b)).hexdigest().upper();jobs.append(b)
 checks.update({'exact_40':len(ids)==40 and len(set(ids))==40,'exact_8240':len(jobs)==8240,'unique_jobs':len({j['execution_id'] for j in jobs})==8240,'bootstrap_8000':sum(j['algorithm']=='Bootstrap-BOSS' for j in jobs)==8000,'authorization_exact':c['authorization']['explicit_user_live_authorization'] and c['authorization']['exact_fits']==8240,'no_semantic_or_oracle':c['authorization']['semantic_api_calls']==0 and not c['authorization']['oracle_access'] and not c['authorization']['holdout_access']})
 ok=all(checks.values()); plan={'schema_version':'fourgraph.p1_v4_look160_incremental_statistical_plan.v1','status':'FROZEN_AUTHORIZED' if ok else 'FAIL','scene_ids':ids,'parameters':c['parameters'],'jobs':jobs}
 auth={'schema_version':'fourgraph.p1_v4_look160_incremental_statistical_authorization.v1','status':'PASS_LIVE_STATISTICAL_AUTHORIZATION' if ok else 'FAIL','plan_sha256':hashlib.sha256(cb(plan)).hexdigest().upper(),'exact_fits':8240,'concurrency':1,'semantic_api_calls':0,'oracle_access':0,'holdout_access':0}
 audit={'status':'PASS' if ok else 'FAIL','checks':checks,'hashes':{'config':sh(CFG),'plan':hashlib.sha256(cb(plan)).hexdigest().upper(),'authorization':hashlib.sha256(cb(auth)).hexdigest().upper()},'executed_fits':0}
 return c,{ROOT/c['outputs']['plan']:cb(plan),ROOT/c['outputs']['authorization']:cb(auth),ROOT/c['outputs']['preflight_audit']:cb(audit)}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();c,arts=build()
 for p,b in arts.items():
  if a.check:
   if not p.is_file() or p.read_bytes()!=b: raise SystemExit(f'drift: {p}')
  else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 print(json.dumps({'status':json.loads(next(b for p,b in arts.items() if p.name.endswith('preflight_audit.json')))['status'],'planned_fits':8240,'check':a.check}))
if __name__=='__main__':main()
