"""Freeze and independently re-score the 480-response look-160 increment."""
import argparse,hashlib,json,sys
from collections import Counter,defaultdict
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from fourgraph.semantic_sentence_id_contract import aggregate_six_votes,validate_response_by_pair
from fourgraph.semantic_sentence_id_contract_reference import reference_aggregate,reference_validate
from scripts.run_p1_v4_independent_calibration_look120_mini_semantic import build_jobs
CFG=ROOT/'configs/p1_v4_look160_incremental_response_freeze_rescore.yaml'
def cb(x):return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sh(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def lines(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def build():
 c=yaml.safe_load(CFG.read_text());
 for n,s in c['parents'].items():
  p=ROOT/s['path']
  if not p.is_file() or sh(p)!=s['sha256']:raise RuntimeError(f'parent hash drift: {n}')
 audit=json.loads((ROOT/c['parents']['execution_audit']['path']).read_text());raw=lines(ROOT/c['parents']['raw_responses']['path'])
 if audit.get('status')!='PASS' or audit.get('recorded_logical_calls')!=480 or len(raw)!=480 or len({x['logical_id'] for x in raw})!=480:raise RuntimeError('execution not complete/unique')
 if any(x.get('status')=='provider_error' for x in raw):raise RuntimeError('unresolved provider incident')
 cfg={'parents':{'execution_plan':c['parents']['execution_plan']},'scope':{'logical_calls':480},'semantic_contract':c['semantic_contract']};jobs=build_jobs(cfg);by={x['logical_id']:x for x in raw}
 if set(by)!={x['logical_id'] for x in jobs}:raise RuntimeError('logical identity drift')
 freeze={'schema_version':'fourgraph.p1_v4_look160_incremental_response_freeze.v1','task':c['task'],'status':'PASS_FROZEN','config_sha256':sh(CFG),'execution_plan_sha256':sh(ROOT/c['parents']['execution_plan']['path']),'raw_response_sha256':sh(ROOT/c['parents']['raw_responses']['path']),'token_ledger_sha256':sh(ROOT/c['parents']['token_ledger']['path']),'effective_logical_responses':480,'provider_errors':0,'frozen_before':['oracle_scoring','precision_metrics','coverage_metrics','closure','threshold_selection'],'oracle_access':0,'holdout_access':0,'semantic_api_calls':0}
 pairs=[];groups=defaultdict(list);dis=0
 for job in jobs:
  rr=by[job['logical_id']]
  try:response=json.loads(str(rr.get('raw_text','')))
  except json.JSONDecodeError:response=object()
  prod_all=validate_response_by_pair(response,job['pairs'],job['story']);judgments={r.get('pair_id'):r for r in response.get('judgments',[])} if isinstance(response,dict) and isinstance(response.get('judgments'),list) else {}
  for pair,prod in zip(job['pairs'],prod_all['pairs']):
   ref=reference_validate(judgments.get(pair.pair_id),{'pair_id':pair.pair_id,'A':pair.node_a_alias,'B':pair.node_b_alias},job['story'])
   if any(prod.get(k)!=ref.get(k) for k in ('pair_valid','validator_status','direction')):dis+=1
   rec={'schema_version':'fourgraph.p1_v4_look160_incremental_pair_rescore.v1','logical_id':job['logical_id'],'scene_id':job['study_id'],'variant':job['variant'],'prompt_id':job['prompt_id'],'pair_id':pair.pair_id,'node_a_alias':pair.node_a_alias,'node_b_alias':pair.node_b_alias,'model_status':prod.get('model_status'),'validator_status':prod.get('validator_status'),'pair_valid':prod.get('pair_valid'),'direction':prod.get('direction'),'evidence_sentence_ids':prod.get('evidence_sentence_ids'),'response_sha256':rr.get('response_sha256'),'raw_status':rr.get('status'),'effective_source':'primary_raw'};pairs.append(rec);groups[(job['study_id'],job['variant'],pair.pair_id)].append(rec)
 out=[]
 for (sid,var,pid),votes in sorted(groups.items()):
  votes=sorted(votes,key=lambda x:x['prompt_id']);prod=aggregate_six_votes(votes,balanced=True);ref=reference_aggregate(votes,balanced=True)
  if any(prod.get(k)!=ref.get(k) for k in ('valid_votes','completeness','agreement','automatic_candidate','review_candidate','candidate_direction')):dis+=1
  out.append({'schema_version':'fourgraph.p1_v4_look160_incremental_six_vote_group.v1','scene_id':sid,'variant':var,'pair_id':pid,'prompt_ids':[x['prompt_id'] for x in votes],'valid_votes':prod['valid_votes'],'invalid_votes':prod['invalid_votes'],'completeness':prod['completeness'],'agreement':prod['agreement'],'vote_counts':prod['vote_counts'],'automatic_candidate':prod['automatic_candidate'],'review_candidate':prod['review_candidate'],'candidate_direction':prod['candidate_direction'],'automatically_published':False})
 if len(pairs)!=3408 or len(out)!=568:raise RuntimeError('pair/group cardinality drift')
 artifacts={ROOT/c['outputs']['response_freeze']:cb(freeze),ROOT/c['outputs']['pair_records']:b''.join(cb(x) for x in pairs),ROOT/c['outputs']['six_vote_groups']:b''.join(cb(x) for x in out)}
 audit={'schema_version':'fourgraph.p1_v4_look160_incremental_response_freeze_rescore_audit.v1','task':c['task'],'status':'PASS' if dis==0 else 'FAIL_VALIDATOR_DISAGREEMENT','response_freeze_sha256':hashlib.sha256(artifacts[ROOT/c['outputs']['response_freeze']]).hexdigest().upper(),'pair_records_sha256':hashlib.sha256(artifacts[ROOT/c['outputs']['pair_records']]).hexdigest().upper(),'six_vote_groups_sha256':hashlib.sha256(artifacts[ROOT/c['outputs']['six_vote_groups']]).hexdigest().upper(),'effective_logical_responses':480,'pair_records':len(pairs),'six_vote_groups':len(out),'production_reference_disagreements':dis,'valid_pair_records':sum(x['pair_valid'] is True for x in pairs),'invalid_pair_records':sum(x['pair_valid'] is False for x in pairs),'validator_status_counts':dict(sorted(Counter(str(x['validator_status']) for x in pairs).items())),'agreement_counts':dict(sorted(Counter(str(x['agreement']) for x in out).items())),'completeness_counts':dict(sorted(Counter(str(x['completeness']) for x in out).items())),'automatic_candidate_groups':sum(x['automatic_candidate'] is True for x in out),'review_candidate_groups':sum(x['review_candidate'] is True for x in out),'oracle_access':0,'holdout_access':0,'semantic_api_calls':0,'precision_metrics':0,'coverage_metrics':0,'closure':0}
 artifacts[ROOT/c['outputs']['audit']]=cb(audit);report=f"# P1V4 look-160 incremental response freeze\n\nStatus: **{audit['status']}**. Exactly 480 frozen Mini-medium responses were replayed into 3,408 pair records and 568 balanced six-vote groups. No API, Oracle, holdout, precision/coverage metric, threshold selection, or closure occurred.\n".encode();artifacts[ROOT/c['outputs']['report']]=report
 return artifacts,audit
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();arts,audit=build()
 for p,b in arts.items():
  if a.check:
   if not p.is_file() or p.read_bytes()!=b:raise RuntimeError(f'byte replay mismatch: {p}')
  else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 print(json.dumps(audit,indent=2));raise SystemExit(0 if audit['status']=='PASS' else 1)
if __name__=='__main__':main()
