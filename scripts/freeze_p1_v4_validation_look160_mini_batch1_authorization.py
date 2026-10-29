"""Authorize exactly the first 480 frozen validation Mini calls; execute none."""
import hashlib,json
from datetime import datetime,time,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import yaml

ROOT=Path(__file__).resolve().parents[1];CFG=ROOT/'configs/p1_v4_validation_look160_mini_semantic_live.yaml';RUNNER=ROOT/'scripts/run_p1_v4_validation_look160_mini_semantic.py'
def cb(x):return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def window_start():
 now=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'));boundary=datetime.combine(now.date(),time(7),tzinfo=now.tzinfo);return (boundary if now>=boundary else boundary-timedelta(days=1)).isoformat()
def write(path,obj):
 body=cb(obj);path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists() and path.read_bytes()!=body:raise RuntimeError(f'artifact drift: {path}')
 if not path.exists():path.write_bytes(body)
 return hashlib.sha256(body).hexdigest().upper()
def main():
 c=yaml.safe_load(CFG.read_text(encoding='utf-8'));plan_path=ROOT/c['parents']['execution_plan']['path'];pre_path=ROOT/c['parents']['provider_preflight']['path']
 if sha(plan_path)!=c['parents']['execution_plan']['sha256'] or sha(pre_path)!=c['parents']['provider_preflight']['sha256']:raise RuntimeError('pinned parent drift')
 plan=load(plan_path);pre=load(pre_path);calls=plan['logical_calls'];ids=[x['logical_id'] for x in calls];authorized=ids[:480];cache=ROOT/c['runtime']['cache_root']
 checks={'preflight_pass':pre.get('status')=='PASS','preflight_one_nonstudy_call':pre.get('provider_calls')==1 and pre.get('study_execution') is False,'preflight_model':pre.get('model')==c['semantic_contract']['model'],'preflight_usage':isinstance(pre.get('total_tokens'),int) and pre['total_tokens']>0,'exact_plan_calls':len(calls)==c['scope']['logical_calls']==2640,'unique_ids':len(set(ids))==2640,'exact_first_slice':len(authorized)==c['scope']['first_authorized_calls']==480,'mini_medium':all(x['model']==c['semantic_contract']['model'] and x['reasoning_effort']=='medium' for x in calls),'hard_spend_stop':c['spend_control']['project_hard_stop_usd']==18.0 and c['spend_control']['hard_limit_enforced'] is True,'daily_token_stop':c['token_control']['daily_window_hard_stop_tokens']==3000000,'batch_size':c['runtime']['batch_size']==480,'no_cache':not (cache/'raw_responses.jsonl').exists(),'no_oracle_holdout':not c['boundary']['oracle_access'] and not c['boundary']['holdout_access'],'no_closure':c['boundary']['closure']=='forbidden'}
 if not all(checks.values()):raise RuntimeError(f'authorization checks failed: {checks}')
 checkpoint={'schema_version':'fourgraph.p1_v4_validation_look160_mini_batch1_checkpoint.v1','status':'PASS_READY_NOT_EXECUTED','checks':checks,'plan_sha256':sha(plan_path),'provider_preflight_sha256':sha(pre_path),'runner_sha256':sha(RUNNER),'batch_id':'look160_batch1_480','authorized_logical_ids':authorized,'project_hard_stop_usd':18.0,'daily_token_hard_stop':3000000,'preflight_tokens_debited':pre['total_tokens'],'study_calls_before_authorization':0,'oracle_access':0,'holdout_access':0};cp=ROOT/c['outputs']['live_authorization_checkpoint'];cph=write(cp,checkpoint)
 auth={'schema_version':'fourgraph.p1_v4_validation_look160_mini_batch1_authorization.v1','status':'PASS_LIVE_AUTHORIZED','explicit_user_live_authorization':True,'checkpoint_sha256':cph,'authorized_logical_calls':2640,'execution_slice':{'batch_id':'look160_batch1_480','max_new_calls':480,'authorized_pending_logical_ids':authorized},'project_hard_stop_usd':18.0,'daily_token_hard_stop':3000000,'study_calls_executed':0};authp=ROOT/c['outputs']['live_authorization'];ah=write(authp,auth)
 audit={'status':'PASS_BATCH1_AUTHORIZATION','checks':checks,'config_sha256':sha(CFG),'checkpoint_sha256':cph,'authorization_sha256':ah,'provider_preflight_calls':1,'provider_preflight_tokens':pre['total_tokens'],'authorized_study_calls':480,'executed_study_calls':0,'oracle_access':0,'holdout_access':0};write(ROOT/c['outputs']['live_authorization_audit'],audit)
 ledger=cache/'token_ledger.jsonl'
 write(ledger,{'window_start':window_start(),'batch_id':'provider_preflight','logical_id':'PROVIDER_PREFLIGHT','input_tokens':pre['input_tokens'],'output_tokens':pre['output_tokens'],'reasoning_tokens':pre['reasoning_tokens'],'total_tokens':pre['total_tokens'],'remaining_tokens_after_call':3000000-pre['total_tokens'],'cost_usd':None})
 print(json.dumps({'status':audit['status'],'authorized_calls':480,'executed_calls':0,'preflight_tokens':pre['total_tokens'],'plan_sha256':sha(plan_path)},indent=2))
if __name__=='__main__':main()
