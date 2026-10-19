"""Create a non-executing live-authorization readiness checkpoint."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]; CONFIG=ROOT/'configs/p1_v4_independent_calibration_look120_statistical_parent_live_authorization.yaml'
def canon(x):return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def build():
 c=yaml.safe_load(CONFIG.read_text());checks={};deps=[]
 for n,s in c['parents'].items():
  p=ROOT/s['path'];h=sha(p) if p.is_file() else None;checks[n+'_hash']=h==s['sha256'];deps.append({'name':n,'path':s['path'],'sha256':h})
 pre=json.loads((ROOT/c['parents']['preflight']['path']).read_text()); aud=json.loads((ROOT/c['parents']['preflight_audit']['path']).read_text());plan=json.loads((ROOT/c['parents']['job_plan']['path']).read_text());a=c['authorization']
 checks.update({'preflight_pass':pre['status']=='PASS_FROZEN_OFFLINE_STATISTICAL_PARENT_PREFLIGHT' and aud['status']=='PASS','exact_24720_jobs':len(plan['jobs'])==24720,'statistical_only_scope':not any(a[k] for k in ('statistical_execution_authorized','semantic_api_calls_authorized','oracle_access_authorized','holdout_access_authorized','downstream_reasoner_authorized')),'no_implicit_user_authorization':a['explicit_user_live_statistical_authorization_recorded'] is False})
 ok=all(checks.values());out={'schema_version':'fourgraph.p1_v4_calibration_look120_statistical_parent_live_authorization.v1','task':c['task'],'status':'PASS_READY_FOR_EXPLICIT_LIVE_STATISTICAL_AUTHORIZATION' if ok else 'FAIL','dependencies':deps,'planned_fits':24720,'authorization':a,'execution_boundary':{'statistical_fits':0,'semantic_api_calls':0,'oracle_access':False,'holdout_access':False},'next_action':'EXPLICIT_USER_LIVE_STATISTICAL_AUTHORIZATION_REQUIRED' if ok else 'REMEDIATION_ONLY'};ob=canon(out);audit={'task':c['task'],'status':'PASS' if ok else 'FAIL','checks':checks,'hashes':{'config':sha(CONFIG),'checkpoint':hashlib.sha256(ob).hexdigest().upper()},'execution_boundary':out['execution_boundary'],'next_action':out['next_action']};rep=f"# P1V4 look-120 statistical-parent authorization checkpoint\n\nStatus: **{audit['status']}**. It binds the 24,720-fit plan and materialized input hashes. It does not itself authorize execution; BOSS/Bootstrap-BOSS/PC/MMPC/FGES and constrained fits remain at zero pending explicit user authorization. Semantic API, Oracle, holdout and reasoner remain locked.\n".encode();return {ROOT/c['outputs']['checkpoint']:ob,ROOT/c['outputs']['audit']:canon(audit),ROOT/c['outputs']['report']:rep}
def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');x=p.parse_args();arts=build()
 if x.check:
  for path,b in arts.items():
   if not path.is_file() or path.read_bytes()!=b:raise SystemExit(f'drift: {path.relative_to(ROOT)}')
 else:
  for path,b in arts.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b)
 audit=json.loads(arts[ROOT/yaml.safe_load(CONFIG.read_text())['outputs']['audit']]);print(json.dumps({'status':audit['status'],'planned_fits':24720,'executed_fits':0,'api_calls':0,'check':x.check}));
 if audit['status']!='PASS':raise SystemExit('checkpoint fail')
if __name__=='__main__':main()
