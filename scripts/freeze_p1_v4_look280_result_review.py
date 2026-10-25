"""Freeze the registered look-280 decision; do not authorize look 320."""
import argparse,hashlib,json
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];CFG=ROOT/'configs/p1_v4_look280_result_review_and_look320_go_no_go.yaml'
def cb(x):return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sh(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def build():
 c=yaml.safe_load(CFG.read_text());checks={}
 for n,s in c['inputs'].items():checks[f'input_{n}']=(ROOT/s['path']).is_file() and sh(ROOT/s['path'])==s['sha256']
 r=json.loads((ROOT/c['inputs']['results']['path']).read_text());a=json.loads((ROOT/c['inputs']['audit']['path']).read_text());p=r['conditions'][r['primary_condition']];full=p['variants']['full'];partial=p['variants']['partial'];checks.update({'oracle_audit_pass':a.get('status')=='PASS_ORACLE_SCORING','oracle_exact_280':a.get('oracle_scenes_accessed')==280,'registered_status':r.get('status')==c['registered']['expected_status'],'full_gate_pass':full['registered_gate_pass'] is True,'partial_precision_pass':partial['precision_confidence_sequence']['pass'] is True,'partial_coverage_pass':partial['coverage']['crosses'] is True,'partial_high_pending':partial['High_guardrail']['pass'] is False and partial['High_guardrail']['contributing_scenes']<c['registered']['minimum_high_contributing_scenes'],'ambiguous_pass':p['ambiguous_abstention_diagnostic']['pass'] is True,'not_futile':not any(x['futile'] for x in r['futility'].values()),'no_false_adjacency_orientation':full['false_positive_adjacency_orientations']==0 and partial['false_positive_adjacency_orientations']==0,'boundaries_locked':not any(c['boundaries'].values())});ok=all(checks.values());review={'schema_version':'fourgraph.p1_v4_look280_result_review.v1','status':'PASS' if ok else 'FAIL','decision':'CONTINUE_TO_REGISTERED_LOOK_320' if ok else 'STOP_REVIEW_FAILED','reason':f"Full passes all gates. Partial passes precision and coverage but has {partial['High_guardrail']['contributing_scenes']} HIGH-contributing scenes versus the registered minimum of {c['registered']['minimum_high_contributing_scenes']}; futility is false.",'primary_condition':r['primary_condition'],'primary_summary':p,'futility':r['futility'],'policy_change':False,'look320_execution_authorized':False,'validation_authorized':False,'holdout_authorized':False};rb=cb(review);audit={'status':'PASS' if ok else 'FAIL','checks':checks,'review_sha256':hashlib.sha256(rb).hexdigest().upper(),'semantic_api_calls':0,'statistical_reruns':0,'oracle_reads':0,'validation_access':0,'holdout_access':0};report=(f"# P1V4 calibration look 280 review\n\nDecision: **{review['decision']}**. Full passes all registered gates. Partial retains perfect observed publication precision and passes coverage, but only {partial['High_guardrail']['contributing_scenes']} scenes contribute HIGH directions versus the required 60. Futility is false. Look 320 is not authorized by this checkpoint.\n").encode();return audit,{ROOT/c['outputs']['review']:rb,ROOT/c['outputs']['audit']:cb(audit),ROOT/c['outputs']['report']:report}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');x=ap.parse_args();a,arts=build()
 for p,b in arts.items():
  if x.check:
   if not p.is_file() or p.read_bytes()!=b:raise RuntimeError(f'replay drift: {p}')
  else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 print(json.dumps(a,indent=2));raise SystemExit(0 if a['status']=='PASS' else 1)
if __name__=='__main__':main()
