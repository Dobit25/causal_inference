"""Freeze and independently re-score the 480-response look-200 increment."""
from __future__ import annotations
import argparse,hashlib,json,sys
from collections import Counter,defaultdict
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from fourgraph.semantic_sentence_id_contract import aggregate_six_votes,validate_response_by_pair
from fourgraph.semantic_sentence_id_contract_reference import reference_aggregate,reference_validate
from scripts.run_p1_v4_independent_calibration_look120_mini_semantic import build_jobs

CFG=ROOT/'configs/p1_v4_look200_incremental_response_freeze_rescore.yaml'
def cb(x):return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sh(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def lines(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]

def build():
 c=yaml.safe_load(CFG.read_text(encoding='utf-8'))
 for name,spec in c['parents'].items():
  p=ROOT/spec['path']
  if not p.is_file() or sh(p)!=spec['sha256']:raise RuntimeError(f'parent hash drift: {name}')
 audit=json.loads((ROOT/c['parents']['execution_audit']['path']).read_text());raw=lines(ROOT/c['parents']['raw_responses']['path']);metadata=lines(ROOT/c['parents']['request_metadata']['path'])
 if audit.get('status')!='PASS' or audit.get('recorded_logical_calls')!=480 or len(raw)!=480 or len({x['logical_id'] for x in raw})!=480:raise RuntimeError('execution not complete/unique')
 if len(metadata)!=480 or len({x['logical_id'] for x in metadata})!=480:raise RuntimeError('request metadata not complete/unique')
 if any(x.get('status')=='provider_error' for x in raw):raise RuntimeError('unresolved provider incident')
 disposition=json.loads((ROOT/c['parents']['retry_disposition']['path']).read_text())
 if disposition.get('status')!='PASS_DISPOSITIONED_AND_EXECUTION_COMPLETE' or disposition.get('retry_attempts_used')!=1:raise RuntimeError('transport incident not properly dispositioned')
 job_cfg={'parents':{'execution_plan':c['parents']['execution_plan']},'scope':{'logical_calls':480},'semantic_contract':c['semantic_contract']}
 jobs=build_jobs(job_cfg);by={x['logical_id']:x for x in raw}
 if set(by)!={x['logical_id'] for x in jobs}:raise RuntimeError('logical identity drift')
 freeze={'schema_version':'fourgraph.p1_v4_look200_incremental_response_freeze.v1','task':c['task'],'status':'PASS_FROZEN','config_sha256':sh(CFG),'execution_plan_sha256':sh(ROOT/c['parents']['execution_plan']['path']),'raw_response_sha256':sh(ROOT/c['parents']['raw_responses']['path']),'request_metadata_sha256':sh(ROOT/c['parents']['request_metadata']['path']),'token_ledger_sha256':sh(ROOT/c['parents']['token_ledger']['path']),'transport_incident_sha256':sh(ROOT/c['parents']['transport_incident']['path']),'retry_disposition_sha256':sh(ROOT/c['parents']['retry_disposition']['path']),'effective_logical_responses':480,'provider_errors':0,'transport_retries':1,'frozen_before':['oracle_scoring','precision_metrics','coverage_metrics','closure','threshold_selection'],'oracle_access':0,'holdout_access':0,'semantic_api_calls':0}
 pair_records=[];grouped=defaultdict(list);disagreements=0
 for job in jobs:
  raw_row=by[job['logical_id']]
  try:response=json.loads(str(raw_row.get('raw_text','')))
  except json.JSONDecodeError:response=object()
  prod_all=validate_response_by_pair(response,job['pairs'],job['story'])
  judgments={r.get('pair_id'):r for r in response.get('judgments',[])} if isinstance(response,dict) and isinstance(response.get('judgments'),list) else {}
  for pair,prod in zip(job['pairs'],prod_all['pairs']):
   ref=reference_validate(judgments.get(pair.pair_id),{'pair_id':pair.pair_id,'A':pair.node_a_alias,'B':pair.node_b_alias},job['story'])
   if any(prod.get(k)!=ref.get(k) for k in ('pair_valid','validator_status','direction')):disagreements+=1
   rec={'schema_version':'fourgraph.p1_v4_look200_incremental_pair_rescore.v1','logical_id':job['logical_id'],'scene_id':job['study_id'],'variant':job['variant'],'prompt_id':job['prompt_id'],'pair_id':pair.pair_id,'node_a_alias':pair.node_a_alias,'node_b_alias':pair.node_b_alias,'model_status':prod.get('model_status'),'validator_status':prod.get('validator_status'),'pair_valid':prod.get('pair_valid'),'direction':prod.get('direction'),'evidence_sentence_ids':prod.get('evidence_sentence_ids'),'response_sha256':raw_row.get('response_sha256'),'raw_status':raw_row.get('status'),'effective_source':'primary_raw'}
   pair_records.append(rec);grouped[(job['study_id'],job['variant'],pair.pair_id)].append(rec)
 six_groups=[]
 for (sid,variant,pair_id),votes in sorted(grouped.items()):
  votes=sorted(votes,key=lambda x:x['prompt_id']);prod=aggregate_six_votes(votes,balanced=True);ref=reference_aggregate(votes,balanced=True)
  if any(prod.get(k)!=ref.get(k) for k in ('valid_votes','completeness','agreement','automatic_candidate','review_candidate','candidate_direction')):disagreements+=1
  six_groups.append({'schema_version':'fourgraph.p1_v4_look200_incremental_six_vote_group.v1','scene_id':sid,'variant':variant,'pair_id':pair_id,'prompt_ids':[x['prompt_id'] for x in votes],'valid_votes':prod['valid_votes'],'invalid_votes':prod['invalid_votes'],'completeness':prod['completeness'],'agreement':prod['agreement'],'vote_counts':prod['vote_counts'],'automatic_candidate':prod['automatic_candidate'],'review_candidate':prod['review_candidate'],'candidate_direction':prod['candidate_direction'],'automatically_published':False})
 if len(pair_records)!=c['scope']['expected_pair_records'] or len(six_groups)!=c['scope']['expected_six_vote_groups']:raise RuntimeError(f"pair/group cardinality drift: {len(pair_records)}/{len(six_groups)}")
 artifacts={ROOT/c['outputs']['response_freeze']:cb(freeze),ROOT/c['outputs']['pair_records']:b''.join(cb(x) for x in pair_records),ROOT/c['outputs']['six_vote_groups']:b''.join(cb(x) for x in six_groups)}
 result={'schema_version':'fourgraph.p1_v4_look200_incremental_response_freeze_rescore_audit.v1','task':c['task'],'status':'PASS' if disagreements==0 else 'FAIL_VALIDATOR_DISAGREEMENT','response_freeze_sha256':hashlib.sha256(artifacts[ROOT/c['outputs']['response_freeze']]).hexdigest().upper(),'pair_records_sha256':hashlib.sha256(artifacts[ROOT/c['outputs']['pair_records']]).hexdigest().upper(),'six_vote_groups_sha256':hashlib.sha256(artifacts[ROOT/c['outputs']['six_vote_groups']]).hexdigest().upper(),'effective_logical_responses':480,'pair_records':len(pair_records),'six_vote_groups':len(six_groups),'production_reference_disagreements':disagreements,'valid_pair_records':sum(x['pair_valid'] is True for x in pair_records),'invalid_pair_records':sum(x['pair_valid'] is False for x in pair_records),'validator_status_counts':dict(sorted(Counter(str(x['validator_status']) for x in pair_records).items())),'agreement_counts':dict(sorted(Counter(str(x['agreement']) for x in six_groups).items())),'completeness_counts':dict(sorted(Counter(str(x['completeness']) for x in six_groups).items())),'automatic_candidate_groups':sum(x['automatic_candidate'] is True for x in six_groups),'review_candidate_groups':sum(x['review_candidate'] is True for x in six_groups),'transport_retry_count':1,'oracle_access':0,'holdout_access':0,'semantic_api_calls':0,'precision_metrics':0,'coverage_metrics':0,'closure':0}
 artifacts[ROOT/c['outputs']['audit']]=cb(result)
 artifacts[ROOT/c['outputs']['report']]=(f"# P1V4 look-200 incremental response freeze\n\nStatus: **{result['status']}**. Exactly 480 frozen Mini-medium responses were replayed into {len(pair_records):,} pair records and {len(six_groups):,} balanced six-vote groups. The single authorized transport retry is hash-pinned. No API, Oracle, holdout, precision/coverage metric, threshold selection, or closure occurred.\n").encode()
 return artifacts,result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args();artifacts,audit=build()
 for path,body in artifacts.items():
  if args.check:
   if not path.is_file() or path.read_bytes()!=body:raise RuntimeError(f'byte replay mismatch: {path}')
  else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
 print(json.dumps(audit,indent=2));raise SystemExit(0 if audit['status']=='PASS' else 1)
if __name__=='__main__':main()
