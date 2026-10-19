"""Freeze a no-fit job plan for P1V4 calibration look-120 statistical parents."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Any
import yaml
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'configs/p1_v4_independent_calibration_look120_statistical_parent_preflight.yaml'
def canon(x:Any)->bytes:return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def build():
 c=yaml.safe_load(CONFIG.read_text()); checks={}; deps=[]
 for n,s in c['parents'].items():
  p=ROOT/s['path']; h=sha(p) if p.is_file() else None; checks[n+'_hash']=h==s['sha256']; deps.append({'name':n,'path':s['path'],'sha256':h})
 manifest=json.loads((ROOT/c['parents']['materialization_manifest']['path']).read_text()); ids=[r['study_id'] for r in manifest['records']]
 params=c['parameters']; jobs=[]
 for sid in ids:
  for alg,reps in [('Single-BOSS',1),('Bootstrap-BOSS',params['bootstrap']['repetitions']),('PC',1),('MMPC',1),('FGES',1),('Constrained-BOSS',1),('Constrained-FGES',1)]:
   for rep in range(int(reps)):
    base={'scene_id':sid,'algorithm':alg,'repetition':rep,'seed':int.from_bytes(hashlib.sha256(f'P1V4CAL|{sid}|{alg}|{rep}'.encode()).digest()[:8],'big')}; base['execution_id']=hashlib.sha256(canon(base)).hexdigest().upper(); jobs.append(base)
 checks.update({'exact_120_materialized_inputs':len(ids)==120 and len(set(ids))==120,'plan_arithmetic':len(jobs)==24720,'unique_execution_identities':len({j['execution_id'] for j in jobs})==len(jobs),'bootstrap_arithmetic':sum(j['algorithm']=='Bootstrap-BOSS' for j in jobs)==24000,'base_ensemble_arithmetic':sum(j['algorithm'] in {'Single-BOSS','PC','MMPC','FGES'} for j in jobs)==480,'constrained_arithmetic':sum(j['algorithm'].startswith('Constrained-') for j in jobs)==240,'output_root_absent':not (ROOT/c['runtime']['output_root']).exists(),'aggregation_root_absent':not (ROOT/c['runtime']['aggregation_root']).exists(),'offline_boundary':all(v in (0,False) for v in c['boundary'].values())})
 passed=all(checks.values()); plan={'schema_version':'fourgraph.p1_v4_calibration_look120_statistical_parent_plan.v1','task':c['task'],'status':'FROZEN_NO_FIT_PLAN' if passed else 'FAIL','scene_ids':ids,'parameters':params,'jobs':jobs,'execution_order':['base_ensemble_methods','bootstrap_aggregation_and_3_of_5_mask','constrained_boss_primary','constrained_fges_robustness'],'boundary':c['boundary']}; pb=canon(plan)
 pre={'schema_version':'fourgraph.p1_v4_calibration_look120_statistical_parent_preflight.v1','task':c['task'],'status':'PASS_FROZEN_OFFLINE_STATISTICAL_PARENT_PREFLIGHT' if passed else 'FAIL','dependencies':deps,'plan_sha256':hashlib.sha256(pb).hexdigest().upper(),'counts':{'scenes':len(ids),'single_boss':120,'bootstrap_boss':24000,'pc':120,'mmpc':120,'fges':120,'constrained_boss':120,'constrained_fges':120,'total_fits':24720},'parameters':params,'boundary':c['boundary'],'next_action':'P1_V4_INDEPENDENT_CALIBRATION_LOOK120_STATISTICAL_PARENT_LIVE_AUTHORIZATION_CHECKPOINT'}
 audit={'schema_version':'fourgraph.p1_v4_calibration_look120_statistical_parent_preflight_audit.v1','task':c['task'],'status':'PASS' if passed else 'FAIL','checks':checks,'hashes':{'config':sha(CONFIG),'plan':hashlib.sha256(pb).hexdigest().upper(),'preflight':hashlib.sha256(canon(pre)).hexdigest().upper()},'boundary':c['boundary'],'next_action':pre['next_action'] if passed else 'PREFLIGHT_REMEDIATION_ONLY'}
 report=f"# P1V4 calibration look-120 statistical-parent preflight\n\nStatus: **{audit['status']}**. Exactly 120 materialized calibration scenes are bound to 24,720 planned fits: 120 Single-BOSS, 24,000 Bootstrap-BOSS, 120 each PC/MMPC/FGES, and 120 each constrained-BOSS/constrained-FGES. The ensemble 3/5 mask is constructed only after its five method-level skeletons exist; constrained BOSS is primary and constrained FGES robustness. No fit or API call occurred.\n".encode()
 return {ROOT/c['outputs']['plan']:pb,ROOT/c['outputs']['preflight']:canon(pre),ROOT/c['outputs']['audit']:canon(audit),ROOT/c['outputs']['report']:report}
def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args();arts=build()
 if a.check:
  for path,b in arts.items():
   if not path.is_file() or path.read_bytes()!=b:raise SystemExit(f'artifact drift: {path.relative_to(ROOT)}')
 else:
  for path,b in arts.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b)
 audit=json.loads(arts[ROOT/yaml.safe_load(CONFIG.read_text())['outputs']['audit']]);print(json.dumps({'status':audit['status'],'planned_fits':24720,'executed_fits':0,'api_calls':0,'check':a.check}));
 if audit['status']!='PASS':raise SystemExit('preflight failed')
if __name__=='__main__':main()
