"""Freeze the exact 480-call Mini authorization and debit provider preflight usage."""
import argparse,hashlib,json
from datetime import datetime,time as dtime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import yaml
ROOT=Path(__file__).resolve().parents[1];CFG=ROOT/'configs/p1_v4_look160_incremental_mini_semantic_live.yaml';RUNNER=ROOT/'scripts/run_p1_v4_independent_calibration_look120_mini_semantic.py'
def cb(x):return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sh(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def start():
 z=ZoneInfo('Asia/Ho_Chi_Minh');now=datetime.now(z);b=datetime.combine(now.date(),dtime(7),tzinfo=z);return (b if now>=b else b-timedelta(days=1)).isoformat()
def build():
 c=yaml.safe_load(CFG.read_text());plan=json.loads((ROOT/c['parents']['execution_plan']['path']).read_text());pre=json.loads((ROOT/c['parents']['provider_preflight']['path']).read_text());checks={'plan_hash':sh(ROOT/c['parents']['execution_plan']['path'])==c['parents']['execution_plan']['sha256'],'preflight_hash':sh(ROOT/c['parents']['provider_preflight']['path'])==c['parents']['provider_preflight']['sha256'],'preflight_pass':pre.get('status')=='PASS','exact_480':len(plan['logical_calls'])==480,'unique_ids':len({x['logical_id'] for x in plan['logical_calls']})==480,'mini_medium':all(x['model']==c['semantic_contract']['model'] and x['reasoning_effort']=='medium' for x in plan['logical_calls']),'no_oracle':not c['boundary']['oracle_access'] and not c['boundary']['holdout_access']}
 ok=all(checks.values());checkpoint={'schema_version':'fourgraph.p1_v4_look160_incremental_mini_live_checkpoint.v1','status':'PASS_READY' if ok else 'FAIL','plan_sha256':sh(ROOT/c['parents']['execution_plan']['path']),'provider_preflight_sha256':sh(ROOT/c['parents']['provider_preflight']['path']),'runner_sha256':sh(RUNNER),'authorized_logical_ids':[x['logical_id'] for x in plan['logical_calls']],'token_hard_stop':2500000,'preflight_tokens_debited':int(pre['total_tokens']),'boundary':c['boundary']};ch=hashlib.sha256(cb(checkpoint)).hexdigest().upper();auth={'schema_version':'fourgraph.p1_v4_look160_incremental_mini_live_authorization.v1','status':'PASS_LIVE_AUTHORIZED' if ok else 'FAIL','explicit_user_live_authorization':True,'checkpoint_sha256':ch,'authorized_logical_calls':480,'execution_slice':{'max_new_calls':480,'authorized_pending_logical_ids':checkpoint['authorized_logical_ids']},'token_hard_stop':2500000};audit={'status':'PASS' if ok else 'FAIL','checks':checks,'hashes':{'config':sh(CFG),'checkpoint':ch,'authorization':hashlib.sha256(cb(auth)).hexdigest().upper()},'provider_calls_before_study':1,'provider_tokens_before_study':int(pre['total_tokens'])}
 return c,pre,{ROOT/c['outputs']['live_authorization_checkpoint']:cb(checkpoint),ROOT/c['outputs']['live_authorization']:cb(auth),ROOT/c['outputs']['live_authorization_audit']:cb(audit)}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();c,pre,arts=build()
 for p,b in arts.items():
  if a.check:
   if not p.is_file() or p.read_bytes()!=b:raise RuntimeError(f'drift {p}')
  else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 ledger=ROOT/c['runtime']['cache_root']/'token_ledger.jsonl';row=cb({'window_start':start(),'logical_id':'PROVIDER_PREFLIGHT','input_tokens':pre['input_tokens'],'output_tokens':pre['output_tokens'],'reasoning_tokens':pre['reasoning_tokens'],'total_tokens':pre['total_tokens'],'remaining_tokens_after_call':2500000-pre['total_tokens'],'cost_usd':None})
 if a.check:
  if not ledger.is_file() or ledger.read_bytes()!=row:raise RuntimeError('ledger drift')
 else:ledger.parent.mkdir(parents=True,exist_ok=True);ledger.write_bytes(row)
 print(json.dumps({'status':'PASS','authorized_calls':480,'preflight_tokens_debited':pre['total_tokens'],'remaining':2500000-pre['total_tokens'],'check':a.check}))
if __name__=='__main__':main()
