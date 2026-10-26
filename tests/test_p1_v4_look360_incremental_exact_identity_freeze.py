import json,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def load(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))

def test_look360_increment_is_exact_unique_and_unexecuted():
 plan=load('data/manifests/p1_v4_look360_incremental_exact_identity_plan.json');audit=load('data/manifests/p1_v4_look360_incremental_exact_identity_audit.json');master=load('data/manifests/p1_v4_independent_calibration_exact_identity_plan.json');ids=plan['incremental_scene_ids_in_execution_order']
 assert plan['status']=='PASS_FROZEN_EXACT_40_IDENTITIES_OFFLINE'
 assert ids==master['exact_scene_ids_in_execution_order'][320:360]
 assert len(ids)==len(set(ids))==40
 assert set(ids).isdisjoint(plan['cumulative_scene_ids_in_execution_order'][:320])
 assert plan['previous_registered_look']==320 and plan['next_registered_look']==360
 assert len(plan['cumulative_scene_ids_in_execution_order'])==360
 assert plan['authorization']['identity_freeze_complete'] is True
 assert all(v is False for k,v in plan['authorization'].items() if k!='identity_freeze_complete')
 assert audit['status']=='PASS'
 assert all(audit['counts'][k]==0 for k in ('scenes_materialized','stories_generated','statistical_fits','semantic_api_calls','oracle_reads'))
 assert audit['validation_access']==audit['holdout_access']==0

def test_look360_freeze_byte_for_byte_replay():
 r=subprocess.run([sys.executable,'scripts/freeze_p1_v4_look360_incremental_exact_identities.py','--check'],cwd=ROOT,capture_output=True,text=True,check=False)
 assert r.returncode==0,r.stdout+r.stderr
