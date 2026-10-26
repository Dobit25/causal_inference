"""Freeze the terminal registered calibration decision at maximum look 440."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/'configs/p1_v4_look440_final_calibration_review.yaml'
def cb(x): return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sh(p): return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def build():
    c=yaml.safe_load(CFG.read_text(encoding='utf-8'))
    for name,s in c['inputs'].items():
        p=ROOT/s['path']
        if not p.is_file() or sh(p)!=s['sha256']: raise RuntimeError(f'input drift: {name}')
    r=json.loads((ROOT/c['inputs']['oracle_results']['path']).read_text()); a=json.loads((ROOT/c['inputs']['oracle_audit']['path']).read_text()); rr=json.loads((ROOT/c['inputs']['response_rescore_audit']['path']).read_text())
    if a.get('status')!='PASS_ORACLE_SCORING' or a.get('oracle_scenes_accessed')!=440 or rr.get('status')!='PASS': raise RuntimeError('upstream audit failed')
    if r.get('status') not in (c['registered_logic']['pass'],c['registered_logic']['stop']): raise RuntimeError('unregistered terminal decision')
    p=r['conditions']['Constrained-BOSS']; full=p['variants']['full']; partial=p['variants']['partial']; decision=r['status']
    all_pass=bool(full['registered_gate_pass'] and partial['registered_gate_pass'] and p['ambiguous_abstention_diagnostic']['pass'])
    if (decision==c['registered_logic']['pass']) != all_pass: raise RuntimeError('terminal decision/gate contradiction')
    if decision==c['registered_logic']['stop'] and partial['High_guardrail']['contributing_scenes']>=c['registered_logic']['high_minimum_contributing_scenes']: raise RuntimeError('registered stop reason not present')
    outcome='CERTIFIED_READY_FOR_VALIDATION' if all_pass else 'NEGATIVE_OR_INCONCLUSIVE_CALIBRATION_STOP'
    cp={'schema_version':'fourgraph.p1_v4_look440_final_calibration_review.v1','status':'PASS_REVIEWED','decision':decision,'calibration_outcome':outcome,'registered_look':440,'maximum_registered_look':440,'next_calibration_look':None,'validation_authorized':False,'primary_parent':'Constrained-BOSS','gates':{'full':{'registered_gate_pass':full['registered_gate_pass'],'precision_cs_pass':full['precision_confidence_sequence']['pass'],'coverage_pass':full['coverage']['crosses'],'high_guardrail_pass':full['High_guardrail']['pass'],'high_contributing_scenes':full['High_guardrail']['contributing_scenes']},'partial':{'registered_gate_pass':partial['registered_gate_pass'],'precision_cs_pass':partial['precision_confidence_sequence']['pass'],'coverage_pass':partial['coverage']['crosses'],'high_guardrail_pass':partial['High_guardrail']['pass'],'high_contributing_scenes':partial['High_guardrail']['contributing_scenes'],'registered_minimum_high_scenes':c['registered_logic']['high_minimum_contributing_scenes']},'ambiguous_pass':p['ambiguous_abstention_diagnostic']['pass']},'disposition':{'additional_calibration_scenes':False,'lower_gate':False,'retune_same_cohort':False,'open_validation':all_pass,'open_holdout':False},'validation_access':0,'holdout_access':0,'semantic_api_calls':0}
    audit={'schema_version':'fourgraph.p1_v4_look440_final_calibration_review_audit.v1','status':'PASS','decision':decision,'calibration_outcome':outcome,'oracle_result_sha256':sh(ROOT/c['inputs']['oracle_results']['path']),'checkpoint_sha256':hashlib.sha256(cb(cp)).hexdigest().upper(),'registered_terminal_logic_applied':True,'tuning_performed':False,'validation_access':0,'holdout_access':0,'semantic_api_calls':0}
    if all_pass:
        text='All registered Full/Partial and Ambiguous gates passed. Calibration policy may be frozen, but validation still requires a separate checkpoint and authorization.'
    else:
        text=f"Full passed all gates. Partial precision and coverage passed, but only {partial['High_guardrail']['contributing_scenes']} scenes contributed HIGH evidence versus the registered minimum {c['registered_logic']['high_minimum_contributing_scenes']}. At the maximum look 440 this is a negative/inconclusive calibration stop; no more scenes, gate reduction, retuning, or validation is authorized."
    report=f"# P1V4 final calibration review at look 440\n\nDecision: **{decision}**.\n\nOutcome: **{outcome}**.\n\n{text}\n"
    return {ROOT/c['outputs']['checkpoint']:cb(cp),ROOT/c['outputs']['audit']:cb(audit),ROOT/c['outputs']['report']:report.encode()},audit
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--check',action='store_true'); x=ap.parse_args(); arts,a=build()
    for p,b in arts.items():
        if x.check:
            if not p.is_file() or p.read_bytes()!=b: raise RuntimeError(f'byte replay mismatch: {p}')
        else: p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b)
    print(json.dumps(a,indent=2))
if __name__=='__main__': main()
