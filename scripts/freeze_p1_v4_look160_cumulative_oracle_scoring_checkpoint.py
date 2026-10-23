"""Freeze cumulative look-160 inputs without opening Oracle commitments."""
import argparse,hashlib,json
from collections import Counter
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];CFG=ROOT/'configs/p1_v4_look160_cumulative_oracle_scoring_authorization_checkpoint.yaml'
OLD_NORM=ROOT/'results/raw/p1_v4_independent_calibration/look120/statistical/normalized';NEW_NORM=ROOT/'results/raw/p1_v4_independent_calibration/look160_increment/statistical/normalized'
def cb(x):return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sh(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def lines(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def build():
 c=yaml.safe_load(CFG.read_text());checks={}
 for n,s in c['parents'].items():checks[n+'_hash']=(ROOT/s['path']).is_file() and sh(ROOT/s['path'])==s['sha256']
 oa=json.loads((ROOT/c['parents']['look120_statistical_audit']['path']).read_text());na=json.loads((ROOT/c['parents']['increment_statistical_audit']['path']).read_text());orx=json.loads((ROOT/c['parents']['look120_rescore_audit']['path']).read_text());nrx=json.loads((ROOT/c['parents']['increment_rescore_audit']['path']).read_text());op=json.loads((ROOT/c['parents']['look120_statistical_plan']['path']).read_text());np=json.loads((ROOT/c['parents']['increment_statistical_plan']['path']).read_text())
 old_ids=set(op['scene_ids']);new_ids=set(np['scene_ids']);ids=sorted(old_ids|new_ids)
 parents=[]
 for plan,root in ((op,OLD_NORM),(np,NEW_NORM)):
  for j in plan['jobs']:
   if j['algorithm'] not in c['scope']['parent_conditions']:continue
   p=root/(j['execution_id']+'.json')
   if not p.is_file():raise RuntimeError(f'missing parent: {j["execution_id"]}')
   r=json.loads(p.read_text())
   if r.get('status')!='VALID' or r.get('job')!=j:raise RuntimeError(f'invalid parent: {j["execution_id"]}')
   parents.append({'scene_id':j['scene_id'],'condition':j['algorithm'],'execution_id':j['execution_id'],'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':sh(p)})
 oldpairs=lines(ROOT/c['parents']['look120_pair_records']['path']);newpairs=lines(ROOT/c['parents']['increment_pair_records']['path']);oldg=lines(ROOT/c['parents']['look120_six_vote_groups']['path']);newg=lines(ROOT/c['parents']['increment_six_vote_groups']['path']);allg=oldg+newg;vc=Counter(x['variant'] for x in allg)
 checks.update({'statistical_pass':oa.get('status')=='PASS_STATISTICAL_EXECUTION' and oa.get('complete_fits')==24720 and na.get('status')=='PASS' and na.get('complete_terminal_records')==8240,'rescore_pass':orx.get('status')=='PASS' and nrx.get('status')=='PASS','scene_partition':len(old_ids)==120 and len(new_ids)==40 and not(old_ids&new_ids) and len(ids)==160,'parents_320':len(parents)==320,'pair_records_18132':len(oldpairs)+len(newpairs)==18132,'groups_3022':len(allg)==3022,'variant_counts':vc==Counter({'full':1102,'partial':1102,'ambiguous':818}),'prompt_ids':all(x['prompt_ids']==['P1','P2','P3','P4','P5','P6'] for x in allg),'boundary_zero':all(v in (0,False) for v in c['boundary'].values())})
 ok=all(checks.values());checkpoint={'schema_version':'fourgraph.p1_v4_look160_cumulative_oracle_scoring_checkpoint.v1','task':c['task'],'status':'PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION' if ok else 'FAIL','config_sha256':sh(CFG),'exact_scene_ids':ids,'look120_scene_ids':sorted(old_ids),'incremental_scene_ids':sorted(new_ids),'parent_graph_inventory':parents,'frozen_inputs':{n:s for n,s in c['parents'].items()},'scope':c['scope'],'semantic_policy':c['semantic_policy'],'registered_metrics_after_explicit_authorization':c['registered_metrics_after_explicit_authorization'],'boundary':c['boundary']}
 audit={'schema_version':'fourgraph.p1_v4_look160_cumulative_oracle_scoring_checkpoint_audit.v1','task':c['task'],'status':checkpoint['status'],'checks':checks,'checkpoint_sha256':hashlib.sha256(cb(checkpoint)).hexdigest().upper(),'exact_scenes':len(ids),'parent_graphs':len(parents),'pair_records':len(oldpairs)+len(newpairs),'six_vote_groups':len(allg),'groups_by_variant':dict(sorted(vc.items())),'oracle_access':0,'holdout_access':0,'semantic_api_calls':0,'metrics_calculated':0}
 report=f"# P1V4 cumulative look-160 Oracle-scoring authorization checkpoint\n\nStatus: **{checkpoint['status']}**. The exact 160 calibration scenes, 320 constrained parent graphs, 18,132 pair records and 3,022 six-vote groups are hash-pinned. Ambiguous remains a fixed first-120 diagnostic subset (818 groups); Full and Partial contain 1,102 groups each. No Oracle, holdout, API, statistical rerun, or metric calculation occurred. Explicit authorization is required before Oracle scoring.\n".encode()
 return {ROOT/c['outputs']['checkpoint']:cb(checkpoint),ROOT/c['outputs']['audit']:cb(audit),ROOT/c['outputs']['report']:report},audit
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();arts,audit=build()
 for p,b in arts.items():
  if a.check:
   if not p.is_file() or p.read_bytes()!=b:raise RuntimeError(f'byte replay mismatch: {p}')
  else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 print(json.dumps(audit,indent=2));raise SystemExit(0 if audit['status'].startswith('PASS') else 1)
if __name__=='__main__':main()
