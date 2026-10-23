"""Authorized cumulative Oracle scoring for P1V4 calibration look 160."""
import argparse,hashlib,json,sys
from collections import defaultdict
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts'),str(ROOT)]
import replay_p1_v4_independent_calibration_look120_overlay_oracle as base
from fourgraph.p1_generation import scene_scm_record
from fourgraph.partial_graph import PartialGraph
from materialize_p1_v4_stage3 import build_blueprint
CFG=ROOT/'configs/p1_v4_look160_cumulative_oracle_scoring_execution.yaml'
def cb(x):return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sh(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def lines(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def write(p,b):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists() and p.read_bytes()!=b:raise RuntimeError(f'drift {p}')
 if not p.exists():p.write_bytes(b)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');ap.add_argument('--check',action='store_true');a=ap.parse_args()
 if a.execute==a.check:raise SystemExit('choose --execute or --check')
 c=yaml.safe_load(CFG.read_text())
 if sh(ROOT/c['authorization']['path'])!=c['authorization']['sha256'] or sh(ROOT/c['authorization']['audit_path'])!=c['authorization']['audit_sha256']:raise RuntimeError('authorization hash drift')
 auth=json.loads((ROOT/c['authorization']['path']).read_text());
 if auth.get('status')!='AUTHORIZED_CALIBRATION_LOOK160_ORACLE_SCORING' or not auth.get('explicit_user_authorization'):raise RuntimeError('not authorized')
 for n,s in c['inputs'].items():
  if sh(ROOT/s['path'])!=s['sha256']:raise RuntimeError(f'input hash drift: {n}')
 cp=json.loads((ROOT/c['inputs']['checkpoint']['path']).read_text());ids=auth['scope']['exact_scene_ids'];old_ids=set(cp['look120_scene_ids']);new_ids=set(cp['incremental_scene_ids'])
 if ids!=cp['exact_scene_ids'] or len(ids)!=160 or len(old_ids)!=120 or len(new_ids)!=40:raise RuntimeError('scene scope drift')
 parents={}
 for item in cp['parent_graph_inventory']:
  p=ROOT/item['path']
  if sh(p)!=item['sha256']:raise RuntimeError('parent hash drift')
  parents[(item['scene_id'],item['condition'])]=json.loads(p.read_text())['graph']
 if len(parents)!=320:raise RuntimeError('parent scope drift')
 op=json.loads((ROOT/c['inputs']['look120_plan']['path']).read_text());np=json.loads((ROOT/c['inputs']['increment_plan']['path']).read_text());pools={}
 for plan in (op,np):
  for sid,row in plan['pair_pools'].items():pools[sid]={x['pair_id']:(x['node_a_canonical'],x['node_b_canonical']) for x in row['pairs']}
 groups={(x['scene_id'],x['variant'],x['pair_id']):x for x in lines(ROOT/c['inputs']['look120_groups']['path'])+lines(ROOT/c['inputs']['increment_groups']['path'])}
 if len(groups)!=3022:raise RuntimeError('group scope drift')
 generation=yaml.safe_load((ROOT/c['inputs']['generation_config']['path']).read_text())['generation'];identity={x['study_id']:x for x in lines(ROOT/c['inputs']['exact_identities']['path'])};mats={}
 for key in ('look120_materialization','increment_materialization'):
  mats.update({x['study_id']:x for x in json.loads((ROOT/c['inputs'][key]['path']).read_text())['records']})
 oracles={};commitments={}
 for sid in ids:
  bp=build_blueprint(identity[sid],generation);commit=hashlib.sha256(cb(scene_scm_record(bp))).hexdigest().upper();md=json.loads((ROOT/mats[sid]['metadata_path']).read_text())
  if commit!=md.get('scm_commitment_sha256') or commit!=mats[sid]['scm_commitment_sha256']:raise RuntimeError(f'Oracle commitment mismatch {sid}')
  oracles[sid]=set(bp.dag.directed);commitments[sid]=commit
 records=[];overlays=[];automatic=set(c['scope']['automatic_agreements'])
 for condition in c['scope']['parent_conditions']:
  for sid in ids:
   g=parents[(sid,condition)];parent=PartialGraph.build(g['nodes'],[tuple(x) for x in g['directed']],[tuple(x) for x in g['undirected']])
   variants=['full','partial']+(['ambiguous'] if sid in old_ids else [])
   for variant in variants:
    gs={pid:groups[(sid,variant,pid)] for pid in pools[sid]};rr,oo=base.scene_output(parent,pools[sid],gs,oracles[sid],scene_id=sid,condition=condition,variant=variant,automatic=automatic);records.extend(rr);overlays.append(oo)
 gates=c['sequential_gates'];results={};curves={}
 for condition in c['scope']['parent_conditions']:
  cr=[x for x in records if x['condition']==condition];vr={}
  for variant in c['scope']['certification_variants']:
   rows=[x for x in cr if x['variant']==variant];outs=[x for x in overlays if x['condition']==condition and x['variant']==variant];scene_cov=[];loss=[];highloss=[]
   for sid in ids:
    sr=[x for x in rows if x['scene_id']==sid];pub=[x for x in sr if x['published']];scene_cov.append(len(pub)/len(sr))
    if pub:loss.append(sum(not bool(x['oracle_match']) for x in pub)/len(pub))
    hi=[x for x in pub if x['agreement']==c['scope']['high_agreement']]
    if hi:highloss.append(sum(not bool(x['oracle_match']) for x in hi)/len(hi))
   pr=base.risk(loss,gates['risk']['error_ceiling'],gates['risk']['alternatives'],gates['risk']['alpha_per_policy']);cov=base.coverage(scene_cov,gates['coverage']['floor'],gates['coverage']['alternatives'],gates['coverage']['alpha_per_policy']);hi=base.risk(highloss,gates['high_guardrail']['error_ceiling'],gates['high_guardrail']['alternatives'],gates['high_guardrail']['alpha']);hp=hi['contributing_scenes']>=gates['high_guardrail']['minimum_contributing_scenes'] and hi['crosses'];pp=pr['contributing_scenes']>=gates['risk']['minimum_contributing_scenes'] and pr['crosses'];valid=len(outs)==160
   vr[variant]={'certified_compelled':base.summary(rows,'certified_compelled'),'semantic_selected':base.summary(rows,'semantic_selected'),'combined_published':base.summary(rows),'coverage':cov,'abstention_rate_scene_mean':1-cov['mean_coverage'],'precision_confidence_sequence':{**pr,'precision_floor':0.95,'pass':pp},'High_guardrail':{**hi,'pass':hp},'overlay_validity':{'valid_after_fail_closed':len(outs),'total':160,'pass':valid,'pre_suppression_conflicts':sum(not x['semantic_overlay_valid'] for x in outs)},'false_positive_adjacency_orientations':sum(x['oracle_relationship']=='FALSE_ADJACENCY' for x in rows if x['published']),'registered_gate_pass':pp and cov['crosses'] and hp and valid};curves[f'{condition}/{variant}']={'scene_coverage':scene_cov,'scene_error_on_contributing':loss,'high_scene_error':highloss,'precision':pr,'coverage':cov,'High':hi}
  ar=[x for x in cr if x['variant']=='ambiguous' and x['source']=='semantic_selected'];flags=[float(any(x['published'] for x in ar if x['scene_id']==sid)) for sid in sorted(old_ids)];amb=base.risk(flags,gates['ambiguous']['error_ceiling'],gates['ambiguous']['alternatives'],gates['ambiguous']['alpha']);results[condition]={'variants':vr,'ambiguous_abstention_diagnostic':{'scenes':120,'eligible_parent_undirected_records':len(ar),'automatic_direction_scenes':int(sum(flags)),'risk':amb,'pass':amb['crosses']}}
 primary=c['scope']['primary_parent'];remaining=c['scope']['maximum_calibration_scenes']-160;futility={}
 for variant in c['scope']['certification_variants']:
  x=curves[f'{primary}/{variant}'];bp=base.risk(x['scene_error_on_contributing']+[0.0]*remaining,gates['risk']['error_ceiling'],gates['risk']['alternatives'],gates['risk']['alpha_per_policy']);bc=base.coverage(x['scene_coverage']+[1.0]*remaining,gates['coverage']['floor'],gates['coverage']['alternatives'],gates['coverage']['alpha_per_policy']);bh=base.risk(x['high_scene_error']+[0.0]*remaining,gates['high_guardrail']['error_ceiling'],gates['high_guardrail']['alternatives'],gates['high_guardrail']['alpha']);futility[variant]={'best_case_by_440':{'precision':bp,'coverage':bc,'High':bh},'futile':not(bp['crosses'] and bc['crosses'] and bh['crosses'])}
 pp=results[primary];early=all(x['registered_gate_pass'] for x in pp['variants'].values()) and pp['ambiguous_abstention_diagnostic']['pass'];status='PASS_EARLY_CERTIFICATION' if early else 'STOP_FOR_FUTILITY' if any(x['futile'] for x in futility.values()) else 'CONTINUE_TO_REGISTERED_LOOK_200'
 dataset=b''.join(cb(x) for x in records);ob=b''.join(cb(x) for x in overlays);res={'schema_version':'fourgraph.p1_v4_look160_cumulative_overlay_oracle_results.v1','task':c['task'],'status':status,'registered_look':160,'primary_condition':primary,'conditions':results,'futility':futility,'selection_performed':False,'oracle_scope':'P1V4 calibration 160 only','metric_dataset_sha256':hashlib.sha256(dataset).hexdigest().upper(),'overlay_outputs_sha256':hashlib.sha256(ob).hexdigest().upper(),'semantic_api_calls':0,'statistical_reruns':0,'meek_closure':0,'holdout_access':0};audit={'schema_version':'fourgraph.p1_v4_look160_cumulative_overlay_oracle_audit.v1','task':c['task'],'status':'PASS_ORACLE_SCORING','authorization_sha256':sh(ROOT/c['authorization']['path']),'oracle_scenes_accessed':160,'oracle_commitments_verified':len(commitments),'metric_records':len(records),'overlay_outputs':len(overlays),'parent_cpdag_mutations':0,'semantic_api_calls':0,'statistical_reruns':0,'meek_closure':0,'holdout_access':0,'metric_dataset_sha256':hashlib.sha256(dataset).hexdigest().upper(),'overlay_outputs_sha256':hashlib.sha256(ob).hexdigest().upper()};report=f"# P1V4 cumulative calibration look 160 Oracle scoring\n\nStatus: **{status}**. Exactly 160 calibration Oracle commitments were reconstructed and verified. No API, statistical rerun, closure, validation or holdout access occurred.\n".encode();arts={ROOT/c['outputs']['metric_dataset']:dataset,ROOT/c['outputs']['overlay_outputs']:ob,ROOT/c['outputs']['results']:cb(res),ROOT/c['outputs']['risk_coverage']:cb(curves),ROOT/c['outputs']['audit']:cb(audit),ROOT/c['outputs']['report']:report}
 if a.check:
  for p,b in arts.items():
   if not p.is_file() or p.read_bytes()!=b:raise RuntimeError(f'replay drift {p}')
 else:
  for p,b in arts.items():write(p,b)
 print(json.dumps({'status':status,'audit':audit,'primary':results[primary]},indent=2))
if __name__=='__main__':main()
