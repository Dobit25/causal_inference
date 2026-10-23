"""Freeze and explicitly authorize cumulative look-240 Oracle scoring."""
from __future__ import annotations
import argparse,hashlib,json
from collections import Counter
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
SCORER=ROOT/'scripts/score_p1_v4_look240_cumulative_oracle.py'
CFG=ROOT/'configs/p1_v4_look240_cumulative_oracle_scoring_execution_freeze.yaml'
def cb(x):return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sh(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def lines(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def write(p,b):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists() and p.read_bytes()!=b:raise RuntimeError(f'artifact drift: {p}')
 if not p.exists():p.write_bytes(b)
def spec(path):return {'path':path.relative_to(ROOT).as_posix(),'sha256':sh(path)}
def build():
 stages={
  'look120':{'plan':ROOT/'data/manifests/p1_v4_independent_calibration_look120_statistical_parent_plan.json','audit':ROOT/'data/manifests/p1_v4_independent_calibration_look120_statistical_final_audit.json','groups':ROOT/'data/manifests/p1_v4_independent_calibration_look120_six_vote_groups.jsonl','pairs':ROOT/'data/manifests/p1_v4_independent_calibration_look120_pair_rescore.jsonl','semantic':ROOT/'data/manifests/p1_v4_independent_calibration_look120_mini_semantic_execution_plan_v2.json','materialization':ROOT/'data/manifests/p1_v4_independent_calibration_look120_materialization.json','rescore':ROOT/'data/manifests/p1_v4_independent_calibration_look120_response_freeze_rescore_audit.json','root':ROOT/'results/raw/p1_v4_independent_calibration/look120/statistical/normalized'},
  'look160':{'plan':ROOT/'data/manifests/p1_v4_look160_incremental_statistical_plan.json','audit':ROOT/'data/manifests/p1_v4_look160_incremental_statistical_execution_audit.json','groups':ROOT/'data/manifests/p1_v4_look160_incremental_six_vote_groups.jsonl','pairs':ROOT/'data/manifests/p1_v4_look160_incremental_pair_rescore.jsonl','semantic':ROOT/'data/manifests/p1_v4_look160_incremental_mini_semantic_plan.json','materialization':ROOT/'data/manifests/p1_v4_independent_calibration_look160_incremental_materialization.json','rescore':ROOT/'data/manifests/p1_v4_look160_incremental_response_freeze_rescore_audit.json','root':ROOT/'results/raw/p1_v4_independent_calibration/look160_increment/statistical/normalized'},
  'look200':{'plan':ROOT/'data/manifests/p1_v4_look200_incremental_statistical_plan.json','audit':ROOT/'data/manifests/p1_v4_look200_incremental_statistical_execution_audit.json','groups':ROOT/'data/manifests/p1_v4_look200_incremental_six_vote_groups.jsonl','pairs':ROOT/'data/manifests/p1_v4_look200_incremental_pair_rescore.jsonl','semantic':ROOT/'data/manifests/p1_v4_look200_incremental_mini_semantic_plan.json','materialization':ROOT/'data/manifests/p1_v4_look200_incremental_materialization.json','rescore':ROOT/'data/manifests/p1_v4_look200_incremental_response_freeze_rescore_audit.json','root':ROOT/'results/raw/p1_v4_independent_calibration/look200_increment/statistical/normalized'},
  'look240':{'plan':ROOT/'data/manifests/p1_v4_look240_incremental_statistical_plan.json','audit':ROOT/'data/manifests/p1_v4_look240_incremental_statistical_execution_audit.json','groups':ROOT/'data/manifests/p1_v4_look240_incremental_six_vote_groups.jsonl','pairs':ROOT/'data/manifests/p1_v4_look240_incremental_pair_records.jsonl','semantic':ROOT/'data/manifests/p1_v4_look240_incremental_mini_semantic_plan.json','materialization':ROOT/'data/manifests/p1_v4_look240_incremental_materialization.json','rescore':ROOT/'data/manifests/p1_v4_look240_incremental_response_freeze_rescore_audit.json','root':ROOT/'results/raw/p1_v4_independent_calibration/look240_increment/statistical/normalized'},
 }
 for s,x in stages.items():
  for k,p in x.items():
   if k!='root' and not p.is_file():raise RuntimeError(f'missing {s}/{k}: {p}')
 scene_sets={s:set(load(x['plan'])['scene_ids']) for s,x in stages.items()};ids=sorted(set().union(*scene_sets.values()))
 if len(ids)!=240 or sum(map(len,scene_sets.values()))!=240:raise RuntimeError('scene partition drift')
 parents=[]
 for s,x in stages.items():
  for job in load(x['plan'])['jobs']:
   if job['algorithm'] not in ('Constrained-BOSS','Constrained-FGES'):continue
   p=x['root']/(job['execution_id']+'.json');r=load(p)
   if r.get('status')!='VALID' or r.get('job')!=job:raise RuntimeError(f'invalid parent {job}')
   parents.append({'scene_id':job['scene_id'],'condition':job['algorithm'],'execution_id':job['execution_id'],'path':p.relative_to(ROOT).as_posix(),'sha256':sh(p)})
 groups=sum((lines(x['groups']) for x in stages.values()),[]);pairs=sum((lines(x['pairs']) for x in stages.values()),[]);variants=Counter(x['variant'] for x in groups)
 if len(parents)!=480 or len({(x['scene_id'],x['condition']) for x in parents})!=480:raise RuntimeError('parent inventory drift')
 if any(load(x['rescore']).get('status')!='PASS' for x in stages.values()):raise RuntimeError('rescore audit failed')
 checkpoint={'schema_version':'fourgraph.p1_v4_look240_cumulative_oracle_scoring_checkpoint.v1','task':'P1_V4_LOOK240_CUMULATIVE_ORACLE_SCORING','status':'PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION','exact_scene_ids':ids,'scene_ids_by_stage':{s:sorted(v) for s,v in scene_sets.items()},'parent_graph_inventory':parents,'scope':{'scenes':240,'parent_graphs':480,'pair_records':len(pairs),'six_vote_groups':len(groups),'groups_by_variant':dict(sorted(variants.items()))},'oracle_scoring_authorized':False,'validation_access':0,'holdout_access':0}
 cp=ROOT/'data/manifests/p1_v4_look240_cumulative_oracle_scoring_authorization_checkpoint.json';cpa=ROOT/'data/manifests/p1_v4_look240_cumulative_oracle_scoring_authorization_checkpoint_audit.json';cpb=cb(checkpoint);write(cp,cpb);write(cpa,cb({'status':'PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION','checkpoint_sha256':hashlib.sha256(cpb).hexdigest().upper(),'exact_scenes':240,'parent_graphs':480,'pair_records':len(pairs),'six_vote_groups':len(groups),'oracle_access':0,'validation_access':0,'holdout_access':0}))
 inputs={'checkpoint':spec(cp),'checkpoint_audit':spec(cpa),'overlay_amendment':spec(ROOT/'data/manifests/p1_v4_look120_evidence_annotated_partial_graph_contract_amendment.json'),'exact_identities':spec(ROOT/'data/manifests/p1_v4_independent_calibration_exact_identities.jsonl'),'generation_config':spec(ROOT/'configs/p1_v4_stage3_method_development_preflight.yaml'),'blueprint_builder':spec(ROOT/'scripts/materialize_p1_v4_stage3.py')}
 for s,x in stages.items():inputs[f'{s}_groups']=spec(x['groups']);inputs[f'{s}_semantic_plan']=spec(x['semantic']);inputs[f'{s}_materialization']=spec(x['materialization'])
 gates=yaml.safe_load((ROOT/'configs/p1_v4_look200_cumulative_oracle_scoring_execution_freeze.yaml').read_text())['sequential_gates']
 outputs={'metric_dataset':'data/manifests/p1_v4_look240_cumulative_overlay_oracle_metric_dataset.jsonl','overlay_outputs':'data/manifests/p1_v4_look240_cumulative_overlay_outputs.jsonl','results':'data/manifests/p1_v4_look240_cumulative_overlay_oracle_metric_results.json','risk_coverage':'data/manifests/p1_v4_look240_cumulative_overlay_oracle_risk_coverage.json','audit':'data/manifests/p1_v4_look240_cumulative_overlay_oracle_metric_audit.json','report':'reports/p1_v4_look240_cumulative_overlay_oracle_metric_results.md'}
 cfg={'schema_version':'fourgraph.p1_v4_look240_cumulative_oracle_scoring_execution_freeze_config.v1','task':'P1_V4_LOOK240_ORACLE_SCORING_EXECUTION','implementation':{'scorer':SCORER.relative_to(ROOT).as_posix(),'scorer_sha256':sh(SCORER)},'execution_freeze':{'path':'data/manifests/p1_v4_look240_oracle_scoring_execution_freeze.json','audit_path':'data/manifests/p1_v4_look240_oracle_scoring_execution_freeze_audit.json'},'authorization':{'path':'data/manifests/p1_v4_look240_cumulative_oracle_scoring_live_authorization.json','audit_path':'data/manifests/p1_v4_look240_cumulative_oracle_scoring_live_authorization_audit.json'},'inputs':inputs,'scope':{'registered_look':240,'maximum_calibration_scenes':440,'next_registered_look':280,'exact_scenes':240,'exact_parent_graphs':480,'exact_six_vote_groups':len(groups),'parent_conditions':['Constrained-BOSS','Constrained-FGES'],'primary_parent':'Constrained-BOSS','certification_variants':['full','partial'],'diagnostic_variant':'ambiguous','ambiguous_scope':'first_120_only','automatic_agreements':['VERY_HIGH','HIGH'],'high_agreement':'HIGH'},'sequential_gates':gates,'decision_rule':{'pass':'PASS_EARLY_CERTIFICATION','continue':'CONTINUE_TO_LOOK_280','futility':'STOP_FOR_FUTILITY'},'boundaries':{'oracle_access_during_freeze':0,'semantic_api_calls':0,'statistical_reruns':0,'validation_access':0,'holdout_access':0,'meek_closure':0},'outputs':outputs}
 cfgb=cb(cfg)
 if CFG.exists() and CFG.read_bytes()!=cfgb:raise RuntimeError('execution config drift')
 if not CFG.exists():CFG.write_bytes(cfgb)
 freeze={'schema_version':'fourgraph.p1_v4_look240_oracle_scoring_execution_freeze.v1','status':'PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION','config_sha256':sh(CFG),'implementation':cfg['implementation'],'checkpoint_sha256':inputs['checkpoint']['sha256'],'exact_scene_ids':ids,'scope':cfg['scope'],'sequential_gates':gates,'decision_rule':cfg['decision_rule'],'frozen_inputs':inputs,'frozen_outputs':outputs,'boundary':cfg['boundaries'],'oracle_scoring_authorized':False}
 fp=ROOT/cfg['execution_freeze']['path'];fa=ROOT/cfg['execution_freeze']['audit_path'];fb=cb(freeze);write(fp,fb);write(fa,cb({'status':'PASS','execution_freeze_sha256':hashlib.sha256(fb).hexdigest().upper(),'oracle_access':0,'validation_access':0,'holdout_access':0}))
 auth={'schema_version':'fourgraph.p1_v4_look240_cumulative_oracle_scoring_live_authorization.v1','status':'AUTHORIZED_CALIBRATION_LOOK240_ORACLE_SCORING','explicit_user_authorization':True,'execution_freeze_sha256':sh(fp),'scope':{'exact_scene_ids':ids,'parent_conditions':['Constrained-BOSS','Constrained-FGES'],'certification_variants':['full','partial'],'ambiguous_diagnostic_scope':'first_120_only'},'permitted':['reconstruct_240_registered_calibration_oracle_commitments','calculate_registered_cumulative_look240_metrics','apply_registered_sequential_decision_rule'],'forbidden':['semantic_api','statistical_rerun','validation_or_holdout','meek_closure','threshold_or_policy_tuning']}
 ap=ROOT/cfg['authorization']['path'];aa=ROOT/cfg['authorization']['audit_path'];ab=cb(auth);write(ap,ab);write(aa,cb({'status':'PASS','authorization_sha256':hashlib.sha256(ab).hexdigest().upper(),'oracle_access_before_execution':0,'semantic_api_calls':0,'statistical_reruns':0,'validation_access':0,'holdout_access':0}))
 return {'status':'PASS','exact_scenes':240,'parents':480,'pair_records':len(pairs),'six_vote_groups':len(groups),'groups_by_variant':dict(variants),'execution_config_sha256':sh(CFG),'execution_freeze_sha256':sh(fp),'authorization_sha256':sh(ap)}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();result=build();print(json.dumps(result,indent=2))
if __name__=='__main__':main()
