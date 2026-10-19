"""Freeze exact look-120 semantic inputs and authorization boundary offline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'configs/p1_v4_independent_calibration_look120_semantic_authorization_checkpoint.yaml'
PUBLIC=ROOT/'data/manifests/p1_v4_independent_calibration_look120_public_inputs.json'
STAT=ROOT/'results/raw/p1_v4_independent_calibration/look120/statistical'
STAT_AUDIT=ROOT/'data/manifests/p1_v4_independent_calibration_look120_statistical_final_audit.json'
PREFLIGHT=ROOT/'data/manifests/p1_v4_independent_calibration_look120_provider_preflight_audit.json'
PLAN=ROOT/'data/manifests/p1_v4_independent_calibration_look120_semantic_execution_plan.json'
CHECKPOINT=ROOT/'data/manifests/p1_v4_independent_calibration_look120_semantic_authorization_checkpoint.json'
AUDIT=ROOT/'data/manifests/p1_v4_independent_calibration_look120_semantic_authorization_audit.json'
REPORT=ROOT/'reports/p1_v4_independent_calibration_look120_semantic_authorization_checkpoint.md'

def canonical(x:object)->bytes:return(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def write_once(p:Path,b:bytes)->None:
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists() and p.read_bytes()!=b:raise RuntimeError(f'artifact drift: {p}')
 if not p.exists():p.write_bytes(b)

def build():
 public=json.loads(PUBLIC.read_text(encoding='utf-8'))['records']; by={(r['study_id'],r['variant']):r for r in public}
 if len(public)!=360 or len({r['study_id'] for r in public})!=120:raise RuntimeError('public input count mismatch')
 norm={}
 for p in (STAT/'normalized').glob('*.json'):
  j=json.loads(p.read_text()); job=j['job'];
  if job['algorithm'] in ('Constrained-BOSS','Constrained-FGES'):norm[(job['scene_id'],job['algorithm'])]=j
 if len(norm)!=240:raise RuntimeError('constrained parent count mismatch')
 records=[]; pools={}
 for sid in sorted({r['study_id'] for r in public}):
  pairs=set()
  for alg in ('Constrained-BOSS','Constrained-FGES'):
   g=norm[(sid,alg)]['graph'];pairs |= {tuple(sorted(e)) for e in g.get('undirected',[])}
  alias=json.loads((ROOT/'data/generated/p1_v4_independent_calibration/look120'/sid/'alias_map.json').read_text())['alias_map']
  pair_rows=[]
  for i,(a,b) in enumerate(sorted(pairs),1):pair_rows.append({'pair_id':f'pair_{i:03d}','node_a_canonical':a,'node_b_canonical':b,'node_a_alias':alias[a],'node_b_alias':alias[b]})
  pool_sha=hashlib.sha256(canonical(pair_rows)).hexdigest().upper();pools[sid]={'pairs':pair_rows,'pair_pool_sha256':pool_sha}
  for variant in ('full','partial','ambiguous'):
   src=by[(sid,variant)]
   for prompt_id in ('P1','P2','P3','P4','P5','P6'):
    records.append({'logical_id':f'{sid}/{variant}/{prompt_id}','study_id':sid,'variant':variant,'prompt_id':prompt_id,'model':'gpt-5.4-nano-2026-03-17','reasoning_effort':'medium','story_artifact_path':src['artifact_path'],'story_content_sha256':src['content_sha256'],'pair_count':len(pair_rows),'pair_ids':[p['pair_id'] for p in pair_rows],'pair_pool_sha256':pool_sha,'conditions':['constrained_boss','constrained_fges']})
 plan={'schema_version':'fourgraph.p1_v4_independent_calibration_look120_semantic_execution_plan.v1','task':'P1_V4_INDEPENDENT_CALIBRATION_LOOK120_SEMANTIC_EXECUTION_PLAN','logical_calls':records,'pair_pools':pools,'shared_evidence_rule':'one raw response per logical call; condition-specific filtering','scope':{'nonedge_diagnostic':'excluded_pending_exact_registered_pair_manifest'}}
 write_once(PLAN,canonical(plan))
 checkpoint={'schema_version':'fourgraph.p1_v4_independent_calibration_look120_semantic_authorization_checkpoint.v1','task':'P1_V4_INDEPENDENT_CALIBRATION_LOOK120_SEMANTIC_LIVE_AUTHORIZATION_CHECKPOINT','status':'PASS_READY_FOR_EXPLICIT_LIVE_AUTHORIZATION','dependencies':{'config_sha256':sha(CONFIG),'statistical_final_audit_sha256':sha(STAT_AUDIT),'public_inputs_sha256':sha(PUBLIC),'provider_preflight_audit_sha256':sha(PREFLIGHT),'execution_plan_sha256':sha(PLAN)},'contract':{'model':'gpt-5.4-nano-2026-03-17','reasoning_effort':'medium','prompt_sha256':sha(ROOT/'prompts/p1_semantic_sentence_ids_v1.md'),'schema_sha256':sha(ROOT/'schemas/semantic_sentence_id_response_v1.schema.json'),'truncation':'disabled','automatic_prompt_chunking':'forbidden'},'scope':{'scenes':120,'public_inputs':360,'logical_calls':2160,'pair_pool_pairs_total':sum(len(v['pairs']) for v in pools.values()),'nonedge_diagnostic':'excluded_pending_exact_registered_pair_manifest'},'boundary':{'study_api_calls_before_authorization':0,'oracle_access':False,'holdout_access':False}}
 audit={'task':checkpoint['task'],'status':'PASS','exact_scenes':120,'exact_public_inputs':360,'exact_logical_calls':2160,'pair_pool_mapping_pass':True,'provider_preflight':'PASS_PROVIDER_PREFLIGHT','statistical_final_audit':'PASS_STATISTICAL_EXECUTION','api_calls_before_authorization':0,'oracle_access':0,'holdout_access':0,'checkpoint_sha256':hashlib.sha256(canonical(checkpoint)).hexdigest().upper()}
 report=f"""# Look-120 semantic authorization checkpoint\n\nStatus: **PASS_READY_FOR_EXPLICIT_LIVE_AUTHORIZATION**. The frozen plan contains 120 scenes, 360 public Full/Partial/Ambiguous inputs, and {len(records)} logical calls (six prompt variants per input). The shared pair pool is the union of undirected edges from official constrained-BOSS and constrained-FGES parents; its total scene-level pair count is {sum(len(v['pairs']) for v in pools.values())}.\n\nNon-edge diagnostic is explicitly excluded from this checkpoint because no exact registered non-edge pair manifest exists for this look; no pair is inferred or invented. No study API call, Oracle access, holdout access, metric calculation or downstream reasoner is authorized by this checkpoint.\n"""
 return plan,checkpoint,audit,report

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
 for p in (CONFIG,PUBLIC,STAT_AUDIT,PREFLIGHT):
  if not p.is_file():raise SystemExit(f'missing {p}')
 plan,checkpoint,audit,report=build()
 if args.check:
  for p,b in ((PLAN,canonical(plan)),(CHECKPOINT,canonical(checkpoint)),(AUDIT,canonical(audit)),(REPORT,report.encode())):
   if not p.is_file() or p.read_bytes()!=b:raise SystemExit('checkpoint replay mismatch')
  print(json.dumps({'status':'PASS_CHECK','logical_calls':len(plan['logical_calls'])}));return
 write_once(CHECKPOINT,canonical(checkpoint));write_once(AUDIT,canonical(audit));write_once(REPORT,report.encode());print(json.dumps({'status':checkpoint['status'],'logical_calls':len(plan['logical_calls'])}))
if __name__=='__main__':main()
