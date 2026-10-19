"""Adopt the already-frozen, unmaterialized P1V4SC identities for independent calibration."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Any
import yaml

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'configs/p1_v4_independent_calibration_exact_identity_plan.yaml'
GEN_ROOT=ROOT/'data/generated/p1_v4_stage3_method_development_cau'
def sha(path:Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()
def canonical(x:Any)->bytes: return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def rows(path:Path): return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x]
def build():
 c=yaml.safe_load(CONFIG.read_text(encoding='utf-8'))
 for item in c['parents'].values():
  if sha(ROOT/item['path'])!=item['sha256']: raise RuntimeError(f"parent hash drift: {item['path']}")
 amendment=json.loads((ROOT/c['parents']['final_architecture_amendment']['path']).read_text(encoding='utf-8'))
 audit=json.loads((ROOT/c['parents']['final_architecture_audit']['path']).read_text(encoding='utf-8'))
 if amendment.get('status')!='PASS_FROZEN_READY_FOR_INDEPENDENT_CALIBRATION_PREFLIGHT' or audit.get('status')!='PASS': raise RuntimeError('final architecture not frozen')
 all_rows=rows(ROOT/c['parents']['source_exact_identities']['path']); identities=[x for x in all_rows if x['role']==c['adoption']['source_role']]
 ids=[x['study_id'] for x in identities]; looks=c['adoption']['registered_looks']
 ambiguous=[x['study_id'] for x in identities if 'ambiguous_semantic_calibration' in x['diagnostic_memberships']]
 nonedge=[x['study_id'] for x in identities if 'nonedge_semantic_calibration' in x['diagnostic_memberships']]
 checks={
  'exact_440_identities':len(identities)==c['adoption']['exact_scene_count'],
  'namespace':all(x.startswith(c['adoption']['required_namespace']) for x in ids),
  'unique_ids':len(set(ids))==len(ids),
  'none_materialized':not any(x.get('scene_materialized') for x in identities) and not any((GEN_ROOT/x).exists() for x in ids),
  'no_development_overlap':not set(ids)&{x['study_id'] for x in all_rows if x['study_id'].startswith(c['adoption']['independent_from_development_prefix'])},
  'registered_look_membership':all(sum(look in x['included_in_registered_looks'] for x in identities)==look for look in looks),
  'ambiguous_subset_exact':len(ambiguous)==c['adoption']['diagnostics']['ambiguous_subset'],
  'nonedge_subset_exact':len(nonedge)==c['adoption']['diagnostics']['nonedge_subset'],
  'nonedge_nested':set(nonedge)<=set(ambiguous),
  'boundary_all_zero':all(v in (0,False) for v in c['boundaries'].values()),
 }
 passed=all(checks.values()); body=b''.join(canonical(x) for x in identities)
 plan={'schema_version':'fourgraph.p1_v4_independent_calibration_exact_identity_plan.v1','task':c['task'],'status':'PASS_FROZEN_UNMATERIALIZED_CALIBRATION_IDENTITIES' if passed else 'FAIL','source_identity_sha256':sha(ROOT/c['parents']['source_exact_identities']['path']),'exact_scene_ids_in_execution_order':ids,'registered_looks':looks,'diagnostic_subsets':{'ambiguous':ambiguous,'nonedge':nonedge},'boundaries':c['boundaries'],'next_action':'P1_V4_INDEPENDENT_CALIBRATION_GENERATOR_AND_MATERIALIZATION_PREFLIGHT'}
 audit={'schema_version':'fourgraph.p1_v4_independent_calibration_exact_identity_plan_audit.v1','task':c['task'],'status':'PASS' if passed else 'FAIL','checks':checks,'identities_sha256':hashlib.sha256(body).hexdigest().upper(),'plan_sha256':hashlib.sha256(canonical(plan)).hexdigest().upper(),'execution_counts':c['boundaries']}
 report=f"# P1V4 independent calibration exact identity plan\n\nThis checkpoint adopts exactly **440**, still-unmaterialized `P1V4SC` identities in their pre-frozen order. The 120-scene first look, 120-scene Ambiguous subset, and nested 80-scene non-edge subset are fixed before materialization. It creates no scientific scene, data, story, graph, response, Oracle read, or holdout access.\n"
 return c,{ROOT/c['outputs']['identities']:body,ROOT/c['outputs']['plan']:canonical(plan),ROOT/c['outputs']['audit']:canonical(audit),ROOT/c['outputs']['report']:report.encode()}
def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args(); c,arts=build()
 if a.check:
  for path,content in arts.items():
   if not path.is_file() or path.read_bytes()!=content: raise RuntimeError(f'artifact drift: {path.relative_to(ROOT)}')
 else:
  for path,content in arts.items(): path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
 audit=json.loads(arts[ROOT/c['outputs']['audit']]); print(json.dumps({'status':audit['status'],'identities':440,'materialized':0,'semantic_api_calls':0,'oracle_access':False,'check':a.check}))
if __name__=='__main__': main()
