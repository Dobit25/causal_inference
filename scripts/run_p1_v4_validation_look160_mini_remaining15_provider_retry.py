"""Run one watchdog-protected retry for each of the 15 authorized IDs."""
from __future__ import annotations
import hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import run_p1_v4_independent_calibration_look120_mini_semantic as base
import yaml
CONFIG=ROOT/os.environ.get('P1_RETRY_CONFIG','configs/p1_v4_validation_look160_mini_remaining15_provider_retry.yaml')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def load(p): return yaml.safe_load(p.read_text(encoding='utf-8')) if p.suffix in {'.yaml','.yml'} else json.loads(p.read_text(encoding='utf-8'))
def rows(p): return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def canon(v): return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def append(p,v): p.parent.mkdir(parents=True,exist_ok=True);p.open('ab').write(canon(v))
def write(p,v): p.parent.mkdir(parents=True,exist_ok=True);b=canon(v);p.write_bytes(b);return sha(p)
def main():
    cfg=load(CONFIG); auth=load(ROOT/cfg['outputs']['authorization']);ids=cfg['retry_scope']['logical_ids']
    if auth.get('status')!='PASS_LIVE_AUTHORIZED' or auth.get('logical_ids')!=ids: raise RuntimeError('authorization mismatch')
    planp=ROOT/cfg['parents']['execution_plan']['path'];rawp=ROOT/cfg['parents']['raw_responses']['path'];
    if sha(planp)!=cfg['parents']['execution_plan']['sha256'] or sha(rawp)!=cfg['parents']['raw_responses']['sha256']: raise RuntimeError('parent hash drift')
    ov=ROOT/cfg['runtime']['retry_overlay'];at=ROOT/cfg['runtime']['retry_attempts'];led=ROOT/cfg['runtime']['retry_token_ledger']
    if any(p.exists() for p in (ov,at,led)): raise RuntimeError('retry artifacts already exist')
    raw={r['logical_id']:r for r in rows(rawp)};jobs={j['logical_id']:j for j in base.build_jobs(cfg)};schema=json.loads((ROOT/cfg['semantic_contract']['schema']).read_text(encoding='utf-8'));used=base.current_window_tokens(ROOT/cfg['runtime']['cache_root']/'token_ledger.jsonl');limit=cfg['token_control']['hard_stop_tokens'];attempted=[]
    for i in ids:
        if raw[i].get('status')!='provider_error': raise RuntimeError(f'not provider error: {i}')
        job=jobs[i];started=time.perf_counter()
        try:
            res=base.watchdog_response(job,schema,cfg['runtime']['external_watchdog']);text=res['raw_text'];val=base.validate_response_by_pair(json.loads(text),job['pairs'],job['story']);status='completed_valid' if val['response_valid'] else 'completed_pair_invalid';rec={'logical_id':i,'status':status,'scene_id':job['study_id'],'variant':job['variant'],'prompt_id':job['prompt_id'],'model':res['model'],'reasoning_effort':job['reasoning_effort'],'request_id':res['request_id'],'input_tokens':res['input_tokens'],'output_tokens':res['output_tokens'],'reasoning_tokens':res['reasoning_tokens'],'total_tokens':res['total_tokens'],'latency_ms':round((time.perf_counter()-started)*1000),'response_sha256':base.sha_text(text),'story_content_sha256':job['story_content_sha256'],'pair_pool_sha256':job['pair_pool_sha256'],'prompt_render_sha256':job['prompt_render_sha256'],'raw_text':text,'response_valid':val['response_valid'],'valid_pair_count':sum(x.get('pair_valid') is True for x in val.get('pairs',[])),'invalid_pair_count':sum(x.get('pair_valid') is False for x in val.get('pairs',[])),'retry_of_status':'provider_error','retry_attempt_number':1,'external_watchdog':True}
            append(ov,rec);used+=rec['total_tokens'];append(led,{'window_start':base.window_start(base.datetime.now(tz=base.ZoneInfo('Asia/Ho_Chi_Minh'))).isoformat(),'logical_id':i,'input_tokens':rec['input_tokens'],'output_tokens':rec['output_tokens'],'reasoning_tokens':rec['reasoning_tokens'],'total_tokens':rec['total_tokens'],'remaining_tokens_after_call':max(0,limit-used),'cost_usd':None,'retry_of_status':'provider_error'})
        except Exception as e: rec={'logical_id':i,'status':'provider_error','scene_id':job['study_id'],'variant':job['variant'],'prompt_id':job['prompt_id'],'model':job['model'],'reasoning_effort':job['reasoning_effort'],'error_type':type(e).__name__,'error_message':str(e)[:1000],'latency_ms':round((time.perf_counter()-started)*1000),'retry_of_status':'provider_error','retry_attempt_number':1,'external_watchdog':True}
        append(at,rec);attempted.append(rec)
    ok=[r for r in attempted if r['status']!='provider_error'];fail=[r for r in attempted if r['status']=='provider_error'];audit={'schema_version':'fourgraph.p1_v4_validation_look160_mini_remaining15_provider_retry_execution_audit.v1','status':'PASS_ALL_15_RETRIES' if len(ok)==15 else 'INCOMPLETE_15_RETRY','authorized_ids':ids,'attempted_ids':[r['logical_id'] for r in attempted],'succeeded':len(ok),'failed':len(fail),'failed_ids':[r['logical_id'] for r in fail],'provider_usage_successes':{k:sum(int(r.get(k,0) or 0) for r in ok) for k in ('input_tokens','output_tokens','reasoning_tokens','total_tokens')},'retry_overlay_sha256':sha(ov) if ov.exists() else None,'retry_attempts_sha256':sha(at),'retry_token_ledger_sha256':sha(led) if led.exists() else None,'api_calls':len(attempted),'oracle_access':0,'holdout_access':0,'metrics_calculated':False};write(ROOT/cfg['outputs']['execution_audit'],audit);report=f"# P1V4 look-160 Mini — remaining 15 provider retry\n\nStatus: **{audit['status']}**. One retry was attempted for each of 15 authorized provider-error logical IDs. Succeeded: {len(ok)}; failed: {len(fail)}. Raw errors remain immutable; retry output is append-only. No Oracle, holdout, closure or metrics.\n";rp=ROOT/cfg['outputs']['report'];rp.parent.mkdir(parents=True,exist_ok=True);rp.write_text(report,encoding='utf-8');print(json.dumps(audit,indent=2))
if __name__=='__main__': main()
