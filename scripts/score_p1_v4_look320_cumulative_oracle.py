"""Freeze authorization and score the registered cumulative P1V4 look 320."""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts'),str(ROOT)]
import replay_p1_v4_independent_calibration_look120_overlay_oracle as base
from fourgraph.p1_generation import scene_scm_record
from fourgraph.partial_graph import PartialGraph
from materialize_p1_v4_stage3 import build_blueprint
SCRIPT=Path(__file__).resolve();PREFIX='p1_v4_look320_cumulative'
STAGES={
 'look120':{'plan':'p1_v4_independent_calibration_look120_statistical_parent_plan.json','audit':'p1_v4_independent_calibration_look120_statistical_final_audit.json','groups':'p1_v4_independent_calibration_look120_six_vote_groups.jsonl','pairs':'p1_v4_independent_calibration_look120_pair_rescore.jsonl','semantic':'p1_v4_independent_calibration_look120_mini_semantic_execution_plan_v2.json','materialization':'p1_v4_independent_calibration_look120_materialization.json','root':'results/raw/p1_v4_independent_calibration/look120/statistical/normalized'},
 'look160':{'plan':'p1_v4_look160_incremental_statistical_plan.json','audit':'p1_v4_look160_incremental_statistical_execution_audit.json','groups':'p1_v4_look160_incremental_six_vote_groups.jsonl','pairs':'p1_v4_look160_incremental_pair_rescore.jsonl','semantic':'p1_v4_look160_incremental_mini_semantic_plan.json','materialization':'p1_v4_independent_calibration_look160_incremental_materialization.json','root':'results/raw/p1_v4_independent_calibration/look160_increment/statistical/normalized'},
 'look200':{'plan':'p1_v4_look200_incremental_statistical_plan.json','audit':'p1_v4_look200_incremental_statistical_execution_audit.json','groups':'p1_v4_look200_incremental_six_vote_groups.jsonl','pairs':'p1_v4_look200_incremental_pair_rescore.jsonl','semantic':'p1_v4_look200_incremental_mini_semantic_plan.json','materialization':'p1_v4_look200_incremental_materialization.json','root':'results/raw/p1_v4_independent_calibration/look200_increment/statistical/normalized'},
 'look240':{'plan':'p1_v4_look240_incremental_statistical_plan.json','audit':'p1_v4_look240_incremental_statistical_execution_audit.json','groups':'p1_v4_look240_incremental_six_vote_groups.jsonl','pairs':'p1_v4_look240_incremental_pair_records.jsonl','semantic':'p1_v4_look240_incremental_mini_semantic_plan.json','materialization':'p1_v4_look240_incremental_materialization.json','root':'results/raw/p1_v4_independent_calibration/look240_increment/statistical/normalized'},
 'look280':{'plan':'p1_v4_look280_incremental_statistical_plan.json','audit':'p1_v4_look280_incremental_statistical_execution_audit.json','groups':'p1_v4_look280_incremental_six_vote_groups.jsonl','pairs':'p1_v4_look280_incremental_pair_records.jsonl','semantic':'p1_v4_look280_incremental_mini_semantic_plan.json','materialization':'p1_v4_look280_incremental_materialization.json','root':'results/raw/p1_v4_independent_calibration/look280_increment/statistical/normalized'},
 'look320':{'plan':'p1_v4_look320_incremental_statistical_plan.json','audit':'p1_v4_look320_incremental_statistical_execution_audit.json','groups':'p1_v4_look320_incremental_six_vote_groups.jsonl','pairs':'p1_v4_look320_incremental_pair_records.jsonl','semantic':'p1_v4_look320_incremental_mini_semantic_plan.json','materialization':'p1_v4_look320_incremental_materialization.json','root':'results/raw/p1_v4_independent_calibration/look320_increment/statistical/normalized'},
}
def cb(x):return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sh(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def lines(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def mpath(stage,key):
 v=STAGES[stage][key];return ROOT/v if key=='root' else ROOT/'data/manifests'/v
def write(p,b):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists() and p.read_bytes()!=b:raise RuntimeError(f'artifact drift: {p}')
 if not p.exists():p.write_bytes(b)
def spec(p):return {'path':p.relative_to(ROOT).as_posix(),'sha256':sh(p)}
def inventory():
 ids=[]
 for s in STAGES:ids.extend(load(mpath(s,'plan'))['scene_ids'])
 if len(ids)!=320 or len(set(ids))!=320:raise RuntimeError('scene partition drift')
 parents=[]
 for s in STAGES:
  if load(mpath(s,'audit')).get('status') not in {'PASS','PASS_STATISTICAL_EXECUTION'}:raise RuntimeError(f'statistical audit failed: {s}')
  for job in load(mpath(s,'plan'))['jobs']:
   if job['algorithm'] not in ('Constrained-BOSS','Constrained-FGES'):continue
   p=mpath(s,'root')/(job['execution_id']+'.json');r=load(p)
   if r.get('status')!='VALID':raise RuntimeError(f'invalid constrained parent {job}')
   parents.append({'scene_id':job['scene_id'],'condition':job['algorithm'],'execution_id':job['execution_id'],'path':p.relative_to(ROOT).as_posix(),'sha256':sh(p)})
 groups=sum((lines(mpath(s,'groups')) for s in STAGES),[]);pairs=sum((lines(mpath(s,'pairs')) for s in STAGES),[])
 if len(parents)!=640 or len({(x['scene_id'],x['condition']) for x in parents})!=640:raise RuntimeError('parent inventory drift')
 return ids,parents,groups,pairs
def freeze():
 ids,parents,groups,pairs=inventory();inputs={'exact_identities':spec(ROOT/'data/manifests/p1_v4_independent_calibration_exact_identities.jsonl'),'generation_config':spec(ROOT/'configs/p1_v4_stage3_method_development_preflight.yaml'),'overlay_amendment':spec(ROOT/'data/manifests/p1_v4_look120_evidence_annotated_partial_graph_contract_amendment.json')}
 for s in STAGES:
  for key in ('groups','pairs','semantic','materialization','plan','audit'):inputs[f'{s}_{key}']=spec(mpath(s,key))
 gates=yaml.safe_load((ROOT/'configs/p1_v4_look240_cumulative_oracle_scoring_execution_freeze.yaml').read_text())['sequential_gates'];checkpoint={'schema_version':'fourgraph.p1_v4_look320_oracle_checkpoint.v1','status':'PASS_READY','exact_scene_ids':ids,'scene_ids_by_stage':{s:load(mpath(s,'plan'))['scene_ids'] for s in STAGES},'parent_graph_inventory':parents,'scope':{'scenes':320,'parents':640,'pair_records':len(pairs),'six_vote_groups':len(groups)},'oracle_access':0,'validation_access':0,'holdout_access':0};cp=ROOT/f'data/manifests/{PREFIX}_oracle_scoring_checkpoint.json';write(cp,cb(checkpoint));inputs['checkpoint']=spec(cp)
 config={'schema_version':'fourgraph.p1_v4_look320_oracle_execution.v1','status':'FROZEN_AUTHORIZED','implementation':spec(SCRIPT),'inputs':inputs,'scope':{'registered_look':320,'maximum_calibration_scenes':440,'next_registered_look':360,'parent_conditions':['Constrained-BOSS','Constrained-FGES'],'primary_parent':'Constrained-BOSS','certification_variants':['full','partial'],'automatic_agreements':['VERY_HIGH','HIGH'],'high_agreement':'HIGH'},'sequential_gates':gates,'authorization':{'explicit_user_authorization':True,'exact_oracle_scenes':320},'outputs':{'dataset':f'data/manifests/{PREFIX}_overlay_oracle_metric_dataset.jsonl','overlays':f'data/manifests/{PREFIX}_overlay_outputs.jsonl','results':f'data/manifests/{PREFIX}_overlay_oracle_metric_results.json','curves':f'data/manifests/{PREFIX}_overlay_oracle_risk_coverage.json','audit':f'data/manifests/{PREFIX}_overlay_oracle_metric_audit.json','report':f'reports/{PREFIX}_overlay_oracle_metric_results.md'},'boundaries':{'semantic_api_calls':0,'statistical_reruns':0,'meek_closure':0,'validation_access':0,'holdout_access':0}}
 cfg=ROOT/'configs/p1_v4_look320_cumulative_oracle_scoring.yaml';write(cfg,cb(config));auth={'status':'AUTHORIZED_CALIBRATION_LOOK320_ORACLE_SCORING','explicit_user_authorization':True,'config_sha256':sh(cfg),'exact_scene_ids':ids,'forbidden':['semantic_api','statistical_rerun','validation','holdout','meek_closure','tuning']};ap=ROOT/f'data/manifests/{PREFIX}_oracle_scoring_live_authorization.json';write(ap,cb(auth));audit={'status':'PASS','checkpoint_sha256':sh(cp),'config_sha256':sh(cfg),'authorization_sha256':sh(ap),'scenes':320,'parents':640,'groups':len(groups),'oracle_access_before_execution':0,'validation_access':0,'holdout_access':0};write(ROOT/f'data/manifests/{PREFIX}_oracle_scoring_authorization_audit.json',cb(audit));return audit
def execute():
 cfgp=ROOT/'configs/p1_v4_look320_cumulative_oracle_scoring.yaml';c=load(cfgp)
 if c['implementation']['sha256']!=sh(SCRIPT):raise RuntimeError('scorer hash drift')
 for name,x in c['inputs'].items():
  p=ROOT/x['path']
  if not p.is_file() or sh(p)!=x['sha256']:raise RuntimeError(f'input hash drift: {name}')
 auth=load(ROOT/f'data/manifests/{PREFIX}_oracle_scoring_live_authorization.json')
 if auth.get('status')!='AUTHORIZED_CALIBRATION_LOOK320_ORACLE_SCORING' or auth.get('config_sha256')!=sh(cfgp):raise RuntimeError('authorization drift')
 ids,parent_items,groups_list,_=inventory();old_ids=set(load(mpath('look120','plan'))['scene_ids']);parents={(x['scene_id'],x['condition']):load(ROOT/x['path'])['graph'] for x in parent_items};pools={}
 for s in STAGES:
  for sid,row in load(mpath(s,'semantic'))['pair_pools'].items():pools[sid]={p['pair_id']:(p['node_a_canonical'],p['node_b_canonical']) for p in row['pairs']}
 groups={(r['scene_id'],r['variant'],r['pair_id']):r for r in groups_list};identities={r['study_id']:r for r in lines(ROOT/'data/manifests/p1_v4_independent_calibration_exact_identities.jsonl')};materialized={}
 for s in STAGES:materialized.update({r['study_id']:r for r in load(mpath(s,'materialization'))['records']})
 generation=yaml.safe_load((ROOT/'configs/p1_v4_stage3_method_development_preflight.yaml').read_text())['generation'];oracles={};commitments={}
 for sid in ids:
  blueprint=build_blueprint(identities[sid],generation);commit=hashlib.sha256(cb(scene_scm_record(blueprint))).hexdigest().upper();md=load(ROOT/materialized[sid]['metadata_path'])
  if commit!=md['scm_commitment_sha256'] or commit!=materialized[sid]['scm_commitment_sha256']:raise RuntimeError(f'Oracle commitment mismatch: {sid}')
  oracles[sid]=set(blueprint.dag.directed);commitments[sid]=commit
 records=[];overlays=[];automatic=set(c['scope']['automatic_agreements'])
 for condition in c['scope']['parent_conditions']:
  for sid in ids:
   g=parents[(sid,condition)];parent=PartialGraph.build(g['nodes'],[tuple(e) for e in g['directed']],[tuple(e) for e in g['undirected']])
   for variant in ['full','partial']+(['ambiguous'] if sid in old_ids else []):
    sg={pid:groups[(sid,variant,pid)] for pid in pools[sid]};rs,ov=base.scene_output(parent,pools[sid],sg,oracles[sid],scene_id=sid,condition=condition,variant=variant,automatic=automatic);records.extend(rs);overlays.append(ov)
 gates=c['sequential_gates'];results={};curves={}
 for condition in c['scope']['parent_conditions']:
  cr=[r for r in records if r['condition']==condition];vr={}
  for variant in ('full','partial'):
   rowsv=[r for r in cr if r['variant']==variant];ovs=[r for r in overlays if r['condition']==condition and r['variant']==variant];scov=[];sloss=[];hloss=[]
   for sid in ids:
    sr=[r for r in rowsv if r['scene_id']==sid];pub=[r for r in sr if r['published']];scov.append(len(pub)/len(sr))
    if pub:sloss.append(sum(not bool(r['oracle_match']) for r in pub)/len(pub))
    high=[r for r in pub if r['agreement']=='HIGH']
    if high:hloss.append(sum(not bool(r['oracle_match']) for r in high)/len(high))
   precision=base.risk(sloss,gates['risk']['error_ceiling'],gates['risk']['alternatives'],gates['risk']['alpha_per_policy']);coverage=base.coverage(scov,gates['coverage']['floor'],gates['coverage']['alternatives'],gates['coverage']['alpha_per_policy']);high=base.risk(hloss,gates['high_guardrail']['error_ceiling'],gates['high_guardrail']['alternatives'],gates['high_guardrail']['alpha']);pp=precision['contributing_scenes']>=gates['risk']['minimum_contributing_scenes'] and precision['crosses'];hp=high['contributing_scenes']>=gates['high_guardrail']['minimum_contributing_scenes'] and high['crosses'];valid=len(ovs)==320
   vr[variant]={'certified_compelled':base.summary(rowsv,'certified_compelled'),'semantic_selected':base.summary(rowsv,'semantic_selected'),'combined_published':base.summary(rowsv),'coverage':coverage,'abstention_rate_scene_mean':1-coverage['mean_coverage'],'precision_confidence_sequence':{**precision,'precision_floor':.95,'pass':pp},'High_guardrail':{**high,'pass':hp},'overlay_validity':{'valid_after_fail_closed':len(ovs),'total':320,'pass':valid,'pre_suppression_conflicts':sum(not x['semantic_overlay_valid'] for x in ovs)},'false_positive_adjacency_orientations':sum(r['oracle_relationship']=='FALSE_ADJACENCY' for r in rowsv if r['published']),'registered_gate_pass':pp and coverage['crosses'] and hp and valid};curves[f'{condition}/{variant}']={'scene_coverage':scov,'scene_error_on_contributing':sloss,'high_scene_error':hloss,'precision':precision,'coverage':coverage,'High':high}
  amb=[r for r in cr if r['variant']=='ambiguous' and r['source']=='semantic_selected'];flags=[float(any(r['published'] for r in amb if r['scene_id']==sid)) for sid in sorted(old_ids)];ar=base.risk(flags,gates['ambiguous']['error_ceiling'],gates['ambiguous']['alternatives'],gates['ambiguous']['alpha']);results[condition]={'variants':vr,'ambiguous_abstention_diagnostic':{'scenes':120,'eligible_parent_undirected_records':len(amb),'automatic_direction_scenes':int(sum(flags)),'risk':ar,'pass':ar['crosses']}}
 primary=c['scope']['primary_parent'];remaining=440-320;futility={}
 for variant in ('full','partial'):
  x=curves[f'{primary}/{variant}'];bp=base.risk(x['scene_error_on_contributing']+[0.0]*remaining,gates['risk']['error_ceiling'],gates['risk']['alternatives'],gates['risk']['alpha_per_policy']);bc=base.coverage(x['scene_coverage']+[1.0]*remaining,gates['coverage']['floor'],gates['coverage']['alternatives'],gates['coverage']['alpha_per_policy']);bh=base.risk(x['high_scene_error']+[0.0]*remaining,gates['high_guardrail']['error_ceiling'],gates['high_guardrail']['alternatives'],gates['high_guardrail']['alpha']);futility[variant]={'best_case_by_440':{'precision':bp,'coverage':bc,'High':bh},'futile':not(bp['crosses'] and bc['crosses'] and bh['crosses'])}
 early=all(x['registered_gate_pass'] for x in results[primary]['variants'].values()) and results[primary]['ambiguous_abstention_diagnostic']['pass'];status='PASS_EARLY_CERTIFICATION' if early else 'STOP_FOR_FUTILITY' if any(x['futile'] for x in futility.values()) else 'CONTINUE_TO_LOOK_360';db=b''.join(cb(r) for r in records);ob=b''.join(cb(r) for r in overlays);result={'schema_version':'fourgraph.p1_v4_look320_cumulative_overlay_oracle_results.v1','status':status,'registered_look':320,'primary_condition':primary,'conditions':results,'futility':futility,'selection_performed':False,'oracle_scope':'P1V4 calibration 320 only','metric_dataset_sha256':hashlib.sha256(db).hexdigest().upper(),'overlay_outputs_sha256':hashlib.sha256(ob).hexdigest().upper(),'semantic_api_calls':0,'statistical_reruns':0,'meek_closure':0,'validation_access':0,'holdout_access':0};audit={'status':'PASS_ORACLE_SCORING','oracle_scenes_accessed':320,'oracle_commitments_verified':len(commitments),'metric_records':len(records),'overlay_outputs':len(overlays),'parent_cpdag_mutations':0,'semantic_api_calls':0,'statistical_reruns':0,'meek_closure':0,'validation_access':0,'holdout_access':0,'metric_dataset_sha256':result['metric_dataset_sha256'],'overlay_outputs_sha256':result['overlay_outputs_sha256']};outs=c['outputs'];arts={ROOT/outs['dataset']:db,ROOT/outs['overlays']:ob,ROOT/outs['results']:cb(result),ROOT/outs['curves']:cb(curves),ROOT/outs['audit']:cb(audit),ROOT/outs['report']:(f'# P1V4 cumulative calibration look 320\n\nStatus: **{status}**. Exactly 320 calibration Oracle commitments were verified. No API, statistical rerun, closure, validation, or holdout.\n').encode()}
 for p,b in arts.items():write(p,b)
 return {'status':status,'audit':audit,'primary':results[primary],'robustness':results['Constrained-FGES'],'futility':futility}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=('freeze','execute'));a=ap.parse_args();r=freeze() if a.stage=='freeze' else execute();print(json.dumps(r,indent=2))
if __name__=='__main__':main()
