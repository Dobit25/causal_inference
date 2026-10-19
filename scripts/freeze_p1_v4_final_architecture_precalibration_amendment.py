"""Freeze the two-source, no-closure architecture before independent calibration."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any
import yaml

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'configs/p1_v4_final_architecture_precalibration_amendment.yaml'
def sha(path:Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()
def canonical(value:Any)->bytes: return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def main()->int:
 c=yaml.safe_load(CONFIG.read_text(encoding='utf-8'))
 for item in c['parents'].values():
  if sha(ROOT/item['path'])!=item['sha256']: raise RuntimeError(f"parent hash drift: {item['path']}")
 policy=json.loads((ROOT/c['parents']['precalibration_model_policy']['path']).read_text(encoding='utf-8'))
 results=json.loads((ROOT/c['parents']['compelled_audit_results']['path']).read_text(encoding='utf-8'))
 if policy.get('primary_semantic_model')!=c['semantic_contract']['model_snapshot'] or policy.get('reasoning_effort')!=c['semantic_contract']['reasoning_effort']: raise RuntimeError('model policy mismatch')
 if results.get('status')!='PASS_DEVELOPMENT_ONLY' or results.get('closure')!=0 or results.get('holdout_access')!=0: raise RuntimeError('compelled diagnostic is not a valid parent')
 checks={
  'primary_is_constrained_boss':c['architecture']['primary_parent']=='Constrained-BOSS',
  'robustness_is_constrained_fges':c['architecture']['robustness_parent']=='Constrained-FGES',
  'model_blind_to_parent_direction':c['architecture']['model_sees_statistical_parent_direction'] is False,
  'confirmed_compelled_rule':c['architecture']['rules']['compelled']['publish_if']=='automatic_semantic_direction_matches_parent_direction',
  'undirected_rule':c['architecture']['rules']['undirected']['publish_if']=='automatic_semantic_direction',
  'closure_forbidden':c['architecture']['closure']=='forbidden',
  'no_live_work':all(c['boundaries'][k] for k in ('no_calibration_scene_materialization','no_statistical_execution','no_semantic_api_calls','no_oracle_access','no_holdout_access')),
  'full_partial_separate':c['calibration']['full_partial_certification_separate'] is True,
  'registered_looks':c['calibration']['sequential_looks']==[120,160,200,240,280,320,360,400,440],
 }
 passed=all(checks.values())
 amendment={'schema_version':'fourgraph.p1_v4_final_architecture_precalibration_amendment.v1','task':c['task'],'status':'PASS_FROZEN_READY_FOR_INDEPENDENT_CALIBRATION_PREFLIGHT' if passed else 'FAIL','config_sha256':sha(CONFIG),'parents':c['parents'],'semantic_contract':c['semantic_contract'],'architecture':c['architecture'],'calibration':c['calibration'],'boundaries':c['boundaries']}
 ap=ROOT/c['outputs']['amendment']; ap.write_bytes(canonical(amendment))
 audit={'schema_version':'fourgraph.p1_v4_final_architecture_precalibration_amendment_audit.v1','task':c['task'],'status':'PASS' if passed else 'FAIL','amendment_sha256':sha(ap),'checks':checks,'calibration_scenes_materialized':0,'statistical_fits':0,'semantic_api_calls':0,'oracle_access':0,'holdout_access':0}
 au=ROOT/c['outputs']['audit']; au.write_bytes(canonical(audit))
 report='# P1V4 final architecture before independent calibration\n\n'+json.dumps({'architecture':c['architecture'],'calibration':c['calibration'],'development_only_caveat':'The cited 30-scene results chose a candidate architecture; they are not calibration evidence.'},ensure_ascii=False,indent=2)+'\n'
 (ROOT/c['outputs']['report']).write_text(report,encoding='utf-8')
 print(json.dumps(audit,ensure_ascii=False,indent=2)); return 0 if passed else 1
if __name__=='__main__': raise SystemExit(main())
