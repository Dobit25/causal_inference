"""Run exactly one retry for P1V4SV064/full/P2."""
from __future__ import annotations
import hashlib, json, sys, time
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import run_p1_v4_independent_calibration_look120_mini_semantic as base
CONFIG=ROOT/'configs/p1_v4_validation_look160_mini_single_retry_sv064.yaml'
ID='P1V4SV064/full/P2'
def canonical(value): return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))+"\n").encode()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest().upper()
def load(path):
    value=yaml.safe_load(path.read_text(encoding='utf-8')) if path.suffix in {'.yaml','.yml'} else json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value,dict): raise RuntimeError(f'mapping expected: {path}')
    return value
def jsonl(path): return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
def append(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('ab') as h: h.write(canonical(value))
def write_new(path,value):
    body=canonical(value); path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.read_bytes()!=body: raise RuntimeError(f'artifact drift: {path}')
    if not path.exists(): path.write_bytes(body)
    return hashlib.sha256(body).hexdigest().upper()
def main():
    cfg=load(CONFIG); auth=load(ROOT/cfg['outputs']['authorization'])
    if auth.get('status')!='PASS_LIVE_AUTHORIZED' or auth.get('logical_ids')!=[ID] or auth.get('maximum_attempts_per_logical_id')!=1: raise RuntimeError('single retry authorization mismatch')
    plan_path=ROOT/cfg['parents']['execution_plan']['path']; raw_path=ROOT/cfg['parents']['raw_responses']['path']
    if sha(plan_path)!=cfg['parents']['execution_plan']['sha256'] or sha(raw_path)!=cfg['parents']['raw_responses']['sha256']: raise RuntimeError('parent hash drift')
    overlay=ROOT/cfg['runtime']['retry_overlay']; attempts=ROOT/cfg['runtime']['retry_attempts']; ledger=ROOT/cfg['runtime']['retry_token_ledger']
    if any(p.exists() for p in (overlay,attempts,ledger)): raise RuntimeError('single retry artifacts already exist')
    raw=jsonl(raw_path); row={r['logical_id']:r for r in raw}.get(ID)
    if not row or row.get('status')!='provider_error': raise RuntimeError('target is no longer exact provider error')
    jobs={j['logical_id']:j for j in base.build_jobs(cfg)}; job=jobs[ID]; schema=json.loads((ROOT/cfg['semantic_contract']['schema']).read_text(encoding='utf-8'))
    used=base.current_window_tokens(ROOT/cfg['runtime']['cache_root']/'token_ledger.jsonl'); limit=int(cfg['token_control']['hard_stop_tokens']); started=time.perf_counter()
    try:
        result=base.watchdog_response(job,schema,cfg['runtime']['external_watchdog']); raw_text=result['raw_text']
        try:
            validation=base.validate_response_by_pair(json.loads(raw_text),job['pairs'],job['story']); status='completed_valid' if validation['response_valid'] else 'completed_pair_invalid'
        except Exception as exc:
            validation={'response_valid':False,'pairs':[],'validation_exception':f'{type(exc).__name__}: {exc}'}; status='completed_schema_invalid'
        record={'logical_id':ID,'status':status,'scene_id':job['study_id'],'variant':job['variant'],'prompt_id':job['prompt_id'],'model':result['model'],'reasoning_effort':job['reasoning_effort'],'request_id':result['request_id'],'input_tokens':result['input_tokens'],'output_tokens':result['output_tokens'],'reasoning_tokens':result['reasoning_tokens'],'total_tokens':result['total_tokens'],'latency_ms':round((time.perf_counter()-started)*1000),'response_sha256':base.sha_text(raw_text),'story_content_sha256':job['story_content_sha256'],'pair_pool_sha256':job['pair_pool_sha256'],'prompt_render_sha256':job['prompt_render_sha256'],'raw_text':raw_text,'response_valid':validation['response_valid'],'valid_pair_count':sum(r.get('pair_valid') is True for r in validation.get('pairs',[])),'invalid_pair_count':sum(r.get('pair_valid') is False for r in validation.get('pairs',[])),'retry_of_status':'provider_error','retry_attempt_number':1,'external_watchdog':True}
        append(overlay,record); used+=record['total_tokens']; append(ledger,{'window_start':base.window_start(base.datetime.now(tz=base.ZoneInfo('Asia/Ho_Chi_Minh'))).isoformat(),'logical_id':ID,'input_tokens':record['input_tokens'],'output_tokens':record['output_tokens'],'reasoning_tokens':record['reasoning_tokens'],'total_tokens':record['total_tokens'],'remaining_tokens_after_call':max(0,limit-used),'cost_usd':None,'retry_of_status':'provider_error'})
    except Exception as exc:
        record={'logical_id':ID,'status':'provider_error','scene_id':job['study_id'],'variant':job['variant'],'prompt_id':job['prompt_id'],'model':job['model'],'reasoning_effort':job['reasoning_effort'],'error_type':type(exc).__name__,'error_message':str(exc)[:1000],'latency_ms':round((time.perf_counter()-started)*1000),'retry_of_status':'provider_error','retry_attempt_number':1,'external_watchdog':True}; append(attempts,record)
    else: append(attempts,record)
    success=record.get('status')!='provider_error'; audit={'schema_version':'fourgraph.p1_v4_validation_look160_mini_sv064_retry_execution_audit.v1','status':'PASS_SINGLE_RETRY_SUCCESS' if success else 'INCOMPLETE_SINGLE_RETRY','authorized_id':ID,'attempted_id':ID,'succeeded':int(success),'failed':int(not success),'failed_id':None if success else ID,'retry_overlay_sha256':sha(overlay) if overlay.exists() else None,'retry_attempts_sha256':sha(attempts),'retry_token_ledger_sha256':sha(ledger) if ledger.exists() else None,'provider_usage':{k:int(record.get(k,0) or 0) for k in ('input_tokens','output_tokens','reasoning_tokens','total_tokens')},'api_calls':1,'oracle_access':0,'holdout_access':0,'metrics_calculated':False}
    write_new(ROOT/cfg['outputs']['execution_audit'],audit); report=f"# P1V4 validation look-160 — SV064 single retry\n\nStatus: **{audit['status']}**. Exactly one retry was attempted for `{ID}`. The original provider-error record remains immutable; any response is stored only in the separate overlay. No Oracle, holdout, closure or metric calculation occurred.\n"; rp=ROOT/cfg['outputs']['report']; rp.parent.mkdir(parents=True,exist_ok=True); rp.write_text(report,encoding='utf-8')
    print(json.dumps(audit,indent=2))
if __name__=='__main__': main()
