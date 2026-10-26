"""Freeze the registered 40-scene look-360 increment without executing it."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any
import yaml

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'configs/p1_v4_look360_incremental_exact_identity_freeze.yaml'
SCRIPT=Path(__file__).resolve()

def canonical_json(value:Any)->bytes:
 return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')
def canonical_jsonl(rows:list[dict[str,Any]])->bytes:
 return b''.join(canonical_json(row) for row in rows)
def sha256(path:Path)->str:
 return hashlib.sha256(path.read_bytes()).hexdigest().upper()
def load_json(path:Path)->dict[str,Any]:
 return json.loads(path.read_text(encoding='utf-8'))
def load_jsonl(path:Path)->list[dict[str,Any]]:
 return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]

def build()->tuple[dict[str,Any],dict[Path,bytes]]:
 cfg=yaml.safe_load(CONFIG.read_text(encoding='utf-8'))
 if cfg['status']!='offline_identity_freeze_only':raise RuntimeError('checkpoint mode drift')
 parent_paths={};dependencies=[];checks={}
 for name,spec in cfg['parents'].items():
  path=ROOT/spec['path'];observed=sha256(path) if path.is_file() else None
  checks[f'input_{name}']=observed==spec['sha256'];parent_paths[name]=path
  dependencies.append({'name':name,'path':spec['path'],'sha256':observed})
 review=load_json(parent_paths['look320_review']);review_audit=load_json(parent_paths['look320_review_audit']);master_plan=load_json(parent_paths['exact_identity_plan']);master_rows=load_jsonl(parent_paths['exact_identities']);prior_plan=load_json(parent_paths['look320_incremental_plan']);prior_audit=load_json(parent_paths['look320_incremental_audit']);selection=cfg['identity_selection']
 start=int(selection['execution_index_start_inclusive']);stop=int(selection['execution_index_end_exclusive']);ordered_ids=master_plan['exact_scene_ids_in_execution_order'];prior_ids=ordered_ids[:start];incremental_ids=ordered_ids[start:stop];cumulative_ids=ordered_ids[:stop];by_id={row['study_id']:row for row in master_rows};selected=[by_id[sid] for sid in incremental_ids if sid in by_id]
 checks.update({
  'look320_review_pass':review.get('status')=='PASS_REVIEWED',
  'registered_decision_is_look360':review.get('decision')=='CONTINUE_TO_LOOK_360' and review.get('next_registered_look')==360,
  'look320_review_audit_pass':review_audit.get('status')=='PASS' and review_audit.get('decision')=='CONTINUE_TO_LOOK_360',
  'look320_identity_pass':prior_plan.get('status')=='PASS_FROZEN_EXACT_40_IDENTITIES_OFFLINE' and prior_audit.get('status')=='PASS',
  'master_registers_look360':selection['next_registered_look'] in master_plan['registered_looks'],
  'exact_registered_slice':incremental_ids==ordered_ids[320:360],
  'exact_40_increment':len(selected)==selection['incremental_scene_count']==stop-start,
  'exact_360_cumulative':len(cumulative_ids)==selection['cumulative_scene_count']==stop,
  'no_overlap_with_first_320':set(prior_ids).isdisjoint(incremental_ids),
  'unique_incremental_ids':len(set(incremental_ids))==len(incremental_ids),
  'unique_cumulative_ids':len(set(cumulative_ids))==len(cumulative_ids),
  'all_identities_resolve':len(selected)==len(incremental_ids),
  'namespace_locked':all(row['study_id'].startswith(selection['namespace']) for row in selected),
  'role_locked':all(row['role']==selection['allowed_role'] for row in selected),
  'batch_locked':all(row['batch_id']==selection['expected_batch_id'] for row in selected),
  'first_registered_look_locked':all(row['first_registered_look']==360 for row in selected),
  'look360_membership_locked':all(360 in row['included_in_registered_looks'] for row in selected),
  'source_unmaterialized':all(row['scene_materialized'] is False for row in selected),
  'component_seeds_complete':all(set(row['component_seeds'])=={'bootstrap_boss','edge_weights','graph_candidates','observations','query_order','story_template'} for row in selected),
  'no_posthoc_diagnostic_assignment':all(not row['diagnostic_memberships'] for row in selected),
  'policy_frozen':all(cfg['frozen_policy'].values()),
  'offline_boundary_zero':all(value==0 for value in cfg['boundaries'].values()),
 })
 passed=all(checks.values());identities_body=canonical_jsonl(selected);identities_hash=hashlib.sha256(identities_body).hexdigest().upper()
 plan={'schema_version':'fourgraph.p1_v4_look360_incremental_exact_identity_plan.v1','task':cfg['task'],'status':'PASS_FROZEN_EXACT_40_IDENTITIES_OFFLINE' if passed else 'FAIL','previous_registered_look':selection['previous_registered_look'],'next_registered_look':selection['next_registered_look'],'execution_index_range':{'start_inclusive':start,'end_exclusive':stop},'batch_id':selection['expected_batch_id'],'incremental_scene_count':len(selected),'cumulative_scene_count':len(cumulative_ids),'incremental_scene_ids_in_execution_order':incremental_ids,'cumulative_scene_ids_in_execution_order':cumulative_ids,'incremental_identity_sha256_by_scene':{row['study_id']:row['identity_sha256'] for row in selected},'incremental_component_seeds_by_scene':{row['study_id']:row['component_seeds'] for row in selected},'incremental_identities_sha256':identities_hash,'seed_policy':selection['seed_policy'],'diagnostics':{'ambiguous_increment':'none_fixed_120_scene_subset','nonedge_increment':'excluded_from_p1v4_calibration'},'dependencies':dependencies+[{'name':'config','path':CONFIG.relative_to(ROOT).as_posix(),'sha256':sha256(CONFIG)},{'name':'implementation','path':SCRIPT.relative_to(ROOT).as_posix(),'sha256':sha256(SCRIPT)}],'authorization':{'identity_freeze_complete':passed,'materialization_authorized':False,'story_generation_authorized':False,'statistical_execution_authorized':False,'semantic_api_authorized':False,'oracle_access_authorized':False,'validation_or_holdout_authorized':False},'next_action':'P1_V4_LOOK360_INCREMENTAL_MATERIALIZATION_PREFLIGHT_AND_AUTHORIZATION_CHECKPOINT'}
 plan_body=canonical_json(plan)
 audit={'schema_version':'fourgraph.p1_v4_look360_incremental_exact_identity_audit.v1','task':cfg['task'],'status':'PASS' if passed else 'FAIL','checks':checks,'counts':{'previous_scenes':len(prior_ids),'incremental_scenes':len(selected),'cumulative_scenes':len(cumulative_ids),'scenes_materialized':0,'stories_generated':0,'statistical_fits':0,'semantic_api_calls':0,'oracle_reads':0},'hashes':{'config':sha256(CONFIG),'implementation':sha256(SCRIPT),'incremental_identities':identities_hash,'incremental_plan':hashlib.sha256(plan_body).hexdigest().upper(),'master_identity_plan':cfg['parents']['exact_identity_plan']['sha256'],'master_identities':cfg['parents']['exact_identities']['sha256'],'look320_review':cfg['parents']['look320_review']['sha256']},'validation_access':0,'holdout_access':0,'next_action':plan['next_action']}
 report='\n'.join(['# P1V4 look-360 incremental exact identity freeze','',f"Status: **{'PASS' if passed else 'FAIL'}**.",'','The registered look-320 review decision is **CONTINUE_TO_LOOK_360**.','',f"The immutable next increment is execution-order slice 320–359: 40 unique scenes from `{incremental_ids[0]}` through `{incremental_ids[-1]}` in registered order, with no overlap with the first 320 scenes.",'','All component seeds and identity hashes are copied byte-for-byte from the frozen 440-scene master calibration plan. No seed, identity, diagnostic membership, model, prompt, parent method, or threshold was changed.','','This checkpoint materialized no scene or story, ran no statistical fit, made no semantic API call, and performed no Oracle, validation, or holdout access. Look-360 materialization requires a separate checkpoint and authorization.','']).encode('utf-8')
 outputs=cfg['outputs'];artifacts={ROOT/outputs['incremental_identities']:identities_body,ROOT/outputs['incremental_plan']:plan_body,ROOT/outputs['identity_audit']:canonical_json(audit),ROOT/outputs['report']:report};return audit,artifacts

def main()->int:
 parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args();audit,artifacts=build()
 for path,payload in artifacts.items():
  if args.check:
   if not path.is_file() or path.read_bytes()!=payload:raise RuntimeError(f'artifact replay drift: {path.relative_to(ROOT)}')
  else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(payload)
 print(json.dumps(audit,ensure_ascii=False,indent=2));return 0 if audit['status']=='PASS' else 2
if __name__=='__main__':raise SystemExit(main())
