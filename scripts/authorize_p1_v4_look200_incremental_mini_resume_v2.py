"""Authorize exactly one transport retry followed by the remaining cached resume."""
from __future__ import annotations
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'data/manifests/p1_v4_look200_incremental_mini_semantic_plan.json'
RAW=ROOT/'results/raw/p1_v4_independent_calibration/look200_increment/mini_semantic/raw_responses.jsonl'
CHECKPOINT=ROOT/'data/manifests/p1_v4_look200_incremental_mini_resume_v2_authorization_checkpoint.json'
AUTH=ROOT/'data/manifests/p1_v4_look200_incremental_mini_resume_v2_authorization.json'
AUDIT=ROOT/'data/manifests/p1_v4_look200_incremental_mini_resume_v2_authorization_audit.json'
RETRY='P1V4SC097/full/P4'

def cb(x):return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def write(p,b):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists() and p.read_bytes()!=b:raise RuntimeError(f'artifact drift: {p}')
 if not p.exists():p.write_bytes(b)

plan=json.loads(PLAN.read_text());cached=[json.loads(x) for x in RAW.read_text().splitlines() if x.strip()]
seen={x['logical_id'] for x in cached};pending=[x['logical_id'] for x in plan['logical_calls'] if x['logical_id'] not in seen]
checks={'cached_exact_87':len(cached)==87,'pending_exact_393':len(pending)==393,'retry_is_first_pending':pending[0]==RETRY,'no_duplicate_cache':len(seen)==len(cached),'no_record_or_usage_for_hung_call':RETRY not in seen}
if not all(checks.values()):raise RuntimeError(f'resume authorization failed: {checks}')
checkpoint={'schema_version':'fourgraph.p1_v4_look200_mini_resume_checkpoint.v2','status':'PASS_READY','plan_sha256':sha(PLAN),'cache_sha256':sha(RAW),'cached_logical_calls':87,'authorized_pending_logical_ids':pending,'transport_retry':{'logical_id':RETRY,'maximum_additional_attempts':1,'eligibility':'prior_hang_without_response_request_id_or_usage'},'remaining_after_retry':392,'token_hard_stop':2500000,'oracle_access':0,'holdout_access':0,'metric_calculation':0}
body=cb(checkpoint);ch=hashlib.sha256(body).hexdigest().upper()
auth={'schema_version':'fourgraph.p1_v4_look200_mini_resume_authorization.v2','status':'PASS_LIVE_AUTHORIZED','explicit_user_live_authorization':True,'checkpoint_sha256':ch,'authorized_logical_calls':480,'execution_slice':{'max_new_calls':393,'authorized_pending_logical_ids':pending},'transport_retry_logical_id':RETRY,'transport_retry_attempt_ceiling':1,'token_hard_stop':2500000}
audit={'status':'PASS','checks':checks,'hashes':{'checkpoint':ch,'authorization':hashlib.sha256(cb(auth)).hexdigest().upper(),'cache':sha(RAW)},'api_calls_at_checkpoint':0,'oracle_access':0,'holdout_access':0}
write(CHECKPOINT,body);write(AUTH,cb(auth));write(AUDIT,cb(audit));print(json.dumps({'status':'PASS','cached':87,'authorized_pending':393,'retry':RETRY}))
