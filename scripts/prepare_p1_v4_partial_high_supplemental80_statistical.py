"""Freeze exact statistical jobs and scoped authorization after materialization."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/'configs/p1_v4_partial_high_supplemental80_statistical_execution.yaml'

def canonical(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))

def write_once(path, body, check=False):
    if check:
        if not path.is_file() or path.read_bytes()!=body: raise RuntimeError(f'byte replay drift: {path}')
    else:
        if path.exists() and path.read_bytes()!=body: raise RuntimeError(f'existing artifact drift: {path}')
        if not path.exists():
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(body)

def build():
    c=yaml.safe_load(CFG.read_text(encoding='utf-8'))
    for name,spec in c['parents'].items():
        path=ROOT/spec['path']
        if not path.is_file() or sha(path)!=spec['sha256']:raise RuntimeError(f'parent hash drift: {name}')
    parent=yaml.safe_load((ROOT/c['parents']['frozen_statistical_config']['path']).read_text(encoding='utf-8'))
    frozen=load(ROOT/c['parents']['protocol']['path'])
    identities=[json.loads(x) for x in (ROOT/c['parents']['exact_identities']['path']).read_text(encoding='utf-8').splitlines() if x]
    planned=load(ROOT/c['parents']['exact_plan']['path'])
    materialized=load(ROOT/c['parents']['materialization_manifest']['path'])['records']
    public=load(ROOT/c['parents']['public_input_manifest']['path'])['records']
    ids=planned['exact_scene_ids_in_execution_order']
    if frozen['status']!='PASS_FROZEN_OFFLINE_DESIGN' or [r['study_id'] for r in identities]!=ids or [r['study_id'] for r in materialized]!=ids or len(ids)!=80 or len(set(ids))!=80:raise RuntimeError('scene scope/order drift')
    if len(public)!=240 or {(r['study_id'],r['variant']) for r in public}!={(sid,v) for sid in ids for v in ('full','partial','ambiguous')}:raise RuntimeError('public story completeness drift')
    if any(any(r['leakage_check'].values()) for r in public):raise RuntimeError('public story leakage')
    for r in materialized:
        if sha(ROOT/r['observation_path'])!=r['observation_sha256']:raise RuntimeError(f'observation hash drift: {r["study_id"]}')
    for r in public:
        if sha(ROOT/r['artifact_path'])!=r['artifact_sha256']:raise RuntimeError(f'public story hash drift: {r["study_id"]}/{r["variant"]}')
    params=parent['parameters']
    if params['bootstrap']['repetitions']!=c['scope']['bootstrap_repetitions'] or params['ensemble']['members']!=['Single-BOSS','Bootstrap-BOSS','PC','MMPC','FGES'] or params['ensemble']['normal_rule']!='3_of_5' or params['ensemble']['one_invalid_rule']!='3_of_4':raise RuntimeError('frozen algorithm parameters drift')
    jobs=[]
    for sid in ids:
        for algorithm in c['scope']['algorithms_in_order']:
            repetitions=c['scope']['bootstrap_repetitions'] if algorithm=='Bootstrap-BOSS' else 1
            for repetition in range(repetitions):
                seed=int.from_bytes(hashlib.sha256(f'P1V4CAL|{sid}|{algorithm}|{repetition}'.encode()).digest()[:8],'big')
                job={'scene_id':sid,'algorithm':algorithm,'repetition':repetition,'seed':seed}
                job['execution_id']=hashlib.sha256(canonical(job)).hexdigest().upper()
                jobs.append(job)
    counts={name:sum(j['algorithm']==name for j in jobs) for name in c['scope']['algorithms_in_order']}
    if counts!=c['scope']['by_algorithm'] or len(jobs)!=c['scope']['exact_fits']==16480 or len({j['execution_id'] for j in jobs})!=16480:raise RuntimeError('statistical plan cardinality/identity drift')
    plan={'schema_version':'fourgraph.p1_v4_partial_high_supplemental80_statistical_plan.v1','status':'FROZEN_AUTHORIZED','scene_ids':ids,'parameters':params,'jobs':jobs}
    body=canonical(plan)
    plan_hash=hashlib.sha256(body).hexdigest().upper()
    auth={'schema_version':'fourgraph.p1_v4_partial_high_supplemental80_statistical_live_authorization.v1','status':'PASS_LIVE_STATISTICAL_AUTHORIZATION','explicit_user_authorization':True,'plan_sha256':plan_hash,'config_sha256':sha(CFG),'exact_fits':16480,'concurrency':1,'semantic_api_calls':0,'oracle_access':0,'holdout_access':0}
    audit={'status':'PASS_STATISTICAL_PREFLIGHT','planned_fits':16480,'actual_fits':0,'scene_count':80,'by_algorithm':counts,'unique_execution_identities':True,'plan_sha256':plan_hash,'config_sha256':sha(CFG),'authorization_sha256':hashlib.sha256(canonical(auth)).hexdigest().upper(),'semantic_api_calls':0,'oracle_access':0,'validation_access':0,'holdout_access':0}
    return c,{ROOT/c['scope']['plan']:body,ROOT/c['scope']['authorization']:canonical(auth),ROOT/c['scope']['preflight_audit']:canonical(audit)},audit

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
    c,artifacts,audit=build()
    for path,body in artifacts.items():write_once(path,body,args.check)
    print(json.dumps({'status':audit['status'],'planned':audit['planned_fits'],'actual':0,'check':args.check}))

if __name__=='__main__':main()
