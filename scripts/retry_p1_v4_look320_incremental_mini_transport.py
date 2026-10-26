"""Execute the separately authorized one-time retry for look-320."""
from __future__ import annotations
import hashlib,json,sys,time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import yaml
from openai import OpenAI
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from fourgraph.semantic_sentence_id_contract import validate_response_by_pair
from scripts.run_p1_v4_independent_calibration_look120_mini_semantic import build_jobs,canonical,load_key,sha_file,sha_text,window_start
CFG=ROOT/'configs/p1_v4_look320_incremental_mini_transport_retry.yaml'
def lines(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def once(p,v):
 b=canonical(v);p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists() and p.read_bytes()!=b:raise RuntimeError(f'artifact drift: {p}')
 if not p.exists():p.write_bytes(b)
def append(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.open('ab').write(canonical(v))
def main():
 c=yaml.safe_load(CFG.read_text());rawp=ROOT/c['parent_raw_response_cache']['path'];audp=ROOT/c['parent_execution_audit']['path'];target=c['retry_policy']['exact_logical_id']
 if sha_file(rawp)!=c['parent_raw_response_cache']['sha256'] or sha_file(audp)!=c['parent_execution_audit']['sha256']:raise RuntimeError('parent hash drift')
 raw=lines(rawp);errors=[x for x in raw if x.get('status')=='provider_error']
 if len(raw)!=480 or len(errors)!=1 or errors[0].get('logical_id')!=target:raise RuntimeError('incident identity drift')
 e=errors[0]
 if e.get('error_type')!=c['retry_policy']['eligible_error_type'] or e.get('request_id') is not None or e.get('total_tokens') is not None:raise RuntimeError('incident ineligible')
 out=ROOT/c['outputs']['retry_response']
 if out.exists() and out.read_text().strip():raise RuntimeError('retry already exists')
 disp={'status':'PASS_DISPOSITIONED_FOR_EXACTLY_ONE_RETRY','logical_id':target,'prior_error_type':e['error_type'],'no_response_or_usage':True,'raw_parent_sha256':sha_file(rawp),'oracle_access':0,'holdout_access':0};once(ROOT/c['outputs']['disposition'],disp)
 auth={'status':'PASS_LIVE_AUTHORIZED','explicit_user_live_authorization':True,'logical_id':target,'max_new_attempts':1,'config_sha256':sha_file(CFG),'disposition_sha256':sha_file(ROOT/c['outputs']['disposition']),'boundary':c['boundary']};once(ROOT/c['outputs']['authorization'],auth)
 jobs={j['logical_id']:j for j in build_jobs({'parents':{'execution_plan':c['execution_plan']},'scope':{'logical_calls':480},'semantic_contract':c['semantic_contract']})};job=jobs[target];schema=json.loads((ROOT/c['semantic_contract']['schema']).read_text());client=OpenAI(api_key=load_key(),max_retries=0,timeout=float(c['retry_policy']['timeout_seconds']));started=time.perf_counter()
 try:
  response=client.responses.create(model=job['model'],input=job['prompt'],reasoning={'effort':job['reasoning_effort']},max_output_tokens=8192,service_tier='default',store=False,text={'format':{'type':'json_schema','name':'semantic_sentence_id_response_v1','schema':schema,'strict':True}},metadata={'task':c['task'],'logical_id':target,'study_execution':'true','retry_attempt':'1'})
  u=response.usage;total=getattr(u,'total_tokens',None)
  if not isinstance(total,int):raise RuntimeError('missing provider usage')
  text=response.output_text or '';v=validate_response_by_pair(json.loads(text),job['pairs'],job['story']);status='completed_valid' if v['response_valid'] else 'completed_pair_invalid';row={'logical_id':target,'attempt':2,'retry_of_status':'provider_error','status':status,'scene_id':job['study_id'],'variant':job['variant'],'prompt_id':job['prompt_id'],'model':response.model,'reasoning_effort':job['reasoning_effort'],'request_id':getattr(response,'_request_id',None),'input_tokens':int(u.input_tokens),'output_tokens':int(u.output_tokens),'reasoning_tokens':int(getattr(getattr(u,'output_tokens_details',None),'reasoning_tokens',0) or 0),'total_tokens':total,'latency_ms':round((time.perf_counter()-started)*1000),'response_sha256':sha_text(text),'story_content_sha256':job['story_content_sha256'],'pair_pool_sha256':job['pair_pool_sha256'],'prompt_render_sha256':job['prompt_render_sha256'],'raw_text':text,'response_valid':v['response_valid'],'valid_pair_count':sum(x.get('pair_valid') is True for x in v['pairs']),'invalid_pair_count':sum(x.get('pair_valid') is False for x in v['pairs'])}
  ledger=rawp.parent/'token_ledger.jsonl';append(ledger,{'window_start':window_start(datetime.now(tz=ZoneInfo('Asia/Ho_Chi_Minh'))).isoformat(),'logical_id':target,'attempt':2,'record_type':'authorized_transport_retry','input_tokens':row['input_tokens'],'output_tokens':row['output_tokens'],'reasoning_tokens':row['reasoning_tokens'],'total_tokens':row['total_tokens'],'cost_usd':None})
 except Exception as exc:row={'logical_id':target,'attempt':2,'retry_of_status':'provider_error','status':'provider_error','scene_id':job['study_id'],'variant':job['variant'],'prompt_id':job['prompt_id'],'model':job['model'],'reasoning_effort':job['reasoning_effort'],'error_type':type(exc).__name__,'error_message':str(exc)[:1000],'latency_ms':round((time.perf_counter()-started)*1000),'story_content_sha256':job['story_content_sha256'],'pair_pool_sha256':job['pair_pool_sha256'],'prompt_render_sha256':job['prompt_render_sha256']}
 append(out,row);audit={'status':'PASS_RESPONSE_RECEIVED' if row['status']!='provider_error' else 'FAIL_PROVIDER_RETRY','logical_id':target,'recorded_retries':1,'retry_status':row['status'],'retry_response_sha256':sha_file(out),'semantic_api_calls':1,'oracle_access':0,'holdout_access':0};once(ROOT/c['outputs']['audit'],audit);print(json.dumps(audit,indent=2));raise SystemExit(0 if audit['status']=='PASS_RESPONSE_RECEIVED' else 1)
if __name__=='__main__':main()
