"""Freeze cumulative look-200 inputs without opening Oracle commitments."""
import argparse,hashlib,json
from collections import Counter
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/'configs/p1_v4_look200_cumulative_oracle_scoring_authorization_checkpoint.yaml'
NORMALIZED={
 'look120':ROOT/'results/raw/p1_v4_independent_calibration/look120/statistical/normalized',
 'look160':ROOT/'results/raw/p1_v4_independent_calibration/look160_increment/statistical/normalized',
 'look200':ROOT/'results/raw/p1_v4_independent_calibration/look200_increment/statistical/normalized',
}
def cb(x):return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sh(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def lines(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]

def build():
 c=yaml.safe_load(CFG.read_text(encoding='utf-8'));checks={}
 for name,spec in c['parents'].items():checks[name+'_hash']=(ROOT/spec['path']).is_file() and sh(ROOT/spec['path'])==spec['sha256']
 audits={look:json.loads((ROOT/c['parents'][f'{look}_statistical_audit']['path']).read_text()) for look in ('look120','look160','look200')}
 resc={look:json.loads((ROOT/c['parents'][f'{look}_rescore_audit']['path']).read_text()) for look in ('look120','look160','look200')}
 plans={look:json.loads((ROOT/c['parents'][f'{look}_statistical_plan']['path']).read_text()) for look in ('look120','look160','look200')}
 scene_sets={look:set(plan['scene_ids']) for look,plan in plans.items()};all_ids=sorted(set().union(*scene_sets.values()))
 parents=[]
 for look,plan in plans.items():
  for job in plan['jobs']:
   if job['algorithm'] not in c['scope']['parent_conditions']:continue
   p=NORMALIZED[look]/(job['execution_id']+'.json')
   if not p.is_file():raise RuntimeError(f'missing parent: {job["execution_id"]}')
   row=json.loads(p.read_text())
   if row.get('status')!='VALID' or row.get('job')!=job:raise RuntimeError(f'invalid parent: {job["execution_id"]}')
   parents.append({'scene_id':job['scene_id'],'condition':job['algorithm'],'execution_id':job['execution_id'],'path':p.relative_to(ROOT).as_posix(),'sha256':sh(p)})
 pair_sets={look:lines(ROOT/c['parents'][f'{look}_pair_records']['path']) for look in ('look120','look160','look200')}
 group_sets={look:lines(ROOT/c['parents'][f'{look}_six_vote_groups']['path']) for look in ('look120','look160','look200')}
 all_pairs=sum(pair_sets.values(),[]);all_groups=sum(group_sets.values(),[]);variants=Counter(x['variant'] for x in all_groups)
 checks.update({
  'statistical_pass':audits['look120'].get('status')=='PASS_STATISTICAL_EXECUTION' and audits['look120'].get('complete_fits')==24720 and audits['look160'].get('status')=='PASS' and audits['look160'].get('complete_terminal_records')==8240 and audits['look200'].get('status')=='PASS_STATISTICAL_EXECUTION' and audits['look200'].get('complete_terminal_records')==8240,
  'rescore_pass':all(x.get('status')=='PASS' for x in resc.values()),
  'scene_partition':len(scene_sets['look120'])==120 and len(scene_sets['look160'])==40 and len(scene_sets['look200'])==40 and not(scene_sets['look120']&scene_sets['look160']) and not(scene_sets['look120']&scene_sets['look200']) and not(scene_sets['look160']&scene_sets['look200']) and len(all_ids)==200,
  'parents_400':len(parents)==400,
  'pair_records_21324':len(all_pairs)==21324,
  'groups_3554':len(all_groups)==3554,
  'variant_counts':variants==Counter({'full':1368,'partial':1368,'ambiguous':818}),
  'prompt_ids':all(x['prompt_ids']==['P1','P2','P3','P4','P5','P6'] for x in all_groups),
  'boundary_zero':all(v in (0,False) for v in c['boundary'].values()),
 })
 passed=all(checks.values())
 checkpoint={'schema_version':'fourgraph.p1_v4_look200_cumulative_oracle_scoring_checkpoint.v1','task':c['task'],'status':'PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION' if passed else 'FAIL','config_sha256':sh(CFG),'exact_scene_ids':all_ids,'scene_ids_by_stage':{k:sorted(v) for k,v in scene_sets.items()},'parent_graph_inventory':parents,'frozen_inputs':c['parents'],'scope':c['scope'],'semantic_policy':c['semantic_policy'],'registered_metrics_after_explicit_authorization':c['registered_metrics_after_explicit_authorization'],'boundary':c['boundary'],'oracle_scoring_authorized':False,'automatic_execution':False}
 audit={'schema_version':'fourgraph.p1_v4_look200_cumulative_oracle_scoring_checkpoint_audit.v1','task':c['task'],'status':checkpoint['status'],'checks':checks,'checkpoint_sha256':hashlib.sha256(cb(checkpoint)).hexdigest().upper(),'exact_scenes':len(all_ids),'parent_graphs':len(parents),'pair_records':len(all_pairs),'six_vote_groups':len(all_groups),'groups_by_variant':dict(sorted(variants.items())),'oracle_access':0,'holdout_access':0,'semantic_api_calls':0,'metrics_calculated':0}
 report=f"# P1V4 cumulative look-200 Oracle-scoring authorization checkpoint\n\nStatus: **{checkpoint['status']}**. The exact 200 calibration scenes, 400 constrained parent graphs, 21,324 pair records and 3,554 six-vote groups are hash-pinned. Ambiguous remains the fixed first-120 diagnostic subset (818 groups); Full and Partial contain 1,368 groups each. No Oracle, holdout, API, statistical rerun, or metric calculation occurred. Explicit authorization is required before Oracle scoring.\n".encode()
 return {ROOT/c['outputs']['checkpoint']:cb(checkpoint),ROOT/c['outputs']['audit']:cb(audit),ROOT/c['outputs']['report']:report},audit

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args();artifacts,audit=build()
 for path,body in artifacts.items():
  if args.check:
   if not path.is_file() or path.read_bytes()!=body:raise RuntimeError(f'byte replay mismatch: {path}')
  else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
 print(json.dumps(audit,indent=2));raise SystemExit(0 if audit['status'].startswith('PASS') else 1)
if __name__=='__main__':main()
