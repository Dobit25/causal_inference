"""Disposition and authorize one retry for exactly the 15 new provider errors."""
from __future__ import annotations
import hashlib,json,os
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/os.environ.get('P1_RETRY_CONFIG','configs/p1_v4_validation_look160_mini_remaining15_provider_retry.yaml')
RUNNER=ROOT/'scripts/run_p1_v4_validation_look160_mini_remaining15_provider_retry.py'
OLD={'P1V4SV206/full/P3','P1V4SV200/ambiguous/P4','P1V4SV451/full/P2','P1V4SV081/full/P1','P1V4SV199/partial/P6','P1V4SV079/partial/P6','P1V4SV335/full/P2','P1V4SV064/full/P2','P1V4SV340/ambiguous/P6','P1V4SV373/partial/P3','P1V4SV006/ambiguous/P5','P1V4SV313/partial/P3','P1V4SV268/full/P3'}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def load(p):
    v=yaml.safe_load(p.read_text(encoding='utf-8')) if p.suffix in {'.yaml','.yml'} else json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(v,dict): raise RuntimeError(f'mapping expected: {p}')
    return v
def jsonl(p): return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def write(p,v):
    b=(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode();p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists() and p.read_bytes()!=b: raise RuntimeError(f'artifact drift: {p}')
    if not p.exists(): p.write_bytes(b)
    return sha(p)
def main():
    cfg=load(CONFIG); plan=ROOT/cfg['parents']['execution_plan']['path']; rawp=ROOT/cfg['parents']['raw_responses']['path']; ids=cfg['retry_scope']['logical_ids']; raw=jsonl(rawp); by={r['logical_id']:r for r in raw}
    checks={'plan_hash':sha(plan)==cfg['parents']['execution_plan']['sha256'],'raw_hash':sha(rawp)==cfg['parents']['raw_responses']['sha256'],'exact_scope':len(ids)==15 and len(set(ids))==15,'new_only':not(OLD.intersection(ids)),'raw_provider_errors':all(by.get(i,{}).get('status')=='provider_error' for i in ids),'no_response_usage':all(by[i].get('request_id') is None and by[i].get('response_sha256') is None and by[i].get('total_tokens') is None for i in ids),'one_retry':cfg['retry_scope']['maximum_attempts_per_logical_id']==1,'overwrite_forbidden':cfg['retry_scope']['overwrite_original_error'] is False,'no_api_in_disposition':True,'oracle_holdout_locked':not cfg['boundary']['oracle_access'] and not cfg['boundary']['holdout_access']}
    if not all(checks.values()): raise RuntimeError(f'checks failed: {[k for k,v in checks.items() if not v]}')
    records=[]
    for i in ids:
        r=by[i];msg=r.get('error_message',''); cls='transport_timeout' if 'Timeout' in r.get('error_type','') or 'timed out' in msg.lower() else 'transport_connection'
        records.append({'logical_id':i,'scene_id':r.get('scene_id'),'variant':r.get('variant'),'prompt_id':r.get('prompt_id'),'classification':cls,'disposition':'missing_semantic_response','retry_status':'authorized_one_attempt','raw_record_sha256':sha_bytes(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())})
    disposition={'schema_version':'fourgraph.p1_v4_validation_look160_mini_remaining15_provider_error_disposition.v1','status':'PASS_15_PROVIDER_ERRORS_DISPOSITIONED','scope':'resume413_new_errors_only','checks':checks,'records':records,'boundaries':{'api_calls_during_disposition':0,'oracle_access':0,'holdout_access':0,'metrics':False,'re_score':False}}
    dsha=write(ROOT/cfg['outputs']['disposition'],disposition); asha=write(ROOT/cfg['outputs']['disposition_audit'],{'schema_version':'fourgraph.p1_v4_validation_look160_mini_remaining15_provider_error_disposition_audit.v1','status':'PASS_DISPOSITION_AUDIT','disposition_sha256':dsha,'new_provider_errors':15,'api_calls':0,'oracle_access':0,'holdout_access':0})
    cp={'schema_version':'fourgraph.p1_v4_validation_look160_mini_remaining15_provider_retry_authorization_checkpoint.v1','status':'PASS_READY_NOT_EXECUTED','checks':checks,'config_sha256':sha(CONFIG),'runner_sha256':sha(RUNNER),'plan_sha256':sha(plan),'raw_sha256':sha(rawp),'authorized_ids':ids,'authorized_calls':15,'api_calls_before_execution':0,'oracle_access':0,'holdout_access':0}
    cpsha=write(ROOT/cfg['outputs']['authorization_checkpoint'],cp)
    auth={'schema_version':'fourgraph.p1_v4_validation_look160_mini_remaining15_provider_retry_authorization.v1','status':'PASS_LIVE_AUTHORIZED','explicit_user_live_authorization':True,'user_authorization_scope':'exactly one retry for the 15 new provider errors','checkpoint_sha256':cpsha,'logical_ids':ids,'maximum_attempts_per_logical_id':1,'overwrite_original_error':False,'oracle_access':0,'holdout_access':0}
    authsha=write(ROOT/cfg['outputs']['authorization'],auth); audsha=write(ROOT/cfg['outputs']['authorization_audit'],{'schema_version':'fourgraph.p1_v4_validation_look160_mini_remaining15_provider_retry_authorization_audit.v1','status':'PASS_15_RETRY_AUTHORIZATION','checks':checks,'disposition_sha256':dsha,'disposition_audit_sha256':asha,'checkpoint_sha256':cpsha,'authorization_sha256':authsha,'authorized_calls':15,'executed_calls':0,'oracle_access':0,'holdout_access':0})
    print(json.dumps({'status':'PASS_15_RETRY_AUTHORIZATION','authorized_calls':15,'checkpoint_sha256':cpsha,'authorization_sha256':authsha,'audit_sha256':audsha},indent=2))
def sha_bytes(b): return hashlib.sha256(b).hexdigest().upper()
if __name__=='__main__': main()
