"""Freeze the registered look-360 calibration decision without policy changes."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/'configs/p1_v4_look360_overlay_result_review_and_look400_go_no_go.yaml'
def cb(x): return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sh(p): return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def build():
    c=yaml.safe_load(CFG.read_text(encoding='utf-8'))
    for name,s in c['inputs'].items():
        p=ROOT/s['path']
        if not p.is_file() or sh(p)!=s['sha256']: raise RuntimeError(f'input drift: {name}')
    r=json.loads((ROOT/c['inputs']['oracle_results']['path']).read_text()); a=json.loads((ROOT/c['inputs']['oracle_audit']['path']).read_text()); rr=json.loads((ROOT/c['inputs']['response_rescore_audit']['path']).read_text())
    if a.get('status')!='PASS_ORACLE_SCORING' or a.get('oracle_scenes_accessed')!=360 or rr.get('status')!='PASS': raise RuntimeError('upstream audit failed')
    if r.get('status') not in set(c['registered_logic'].values()): raise RuntimeError('unregistered decision')
    p=r['conditions']['Constrained-BOSS']; full=p['variants']['full']; partial=p['variants']['partial']; decision=r['status']
    if decision=='CONTINUE_TO_LOOK_400' and (r['futility']['full']['futile'] or r['futility']['partial']['futile']): raise RuntimeError('continue/futility contradiction')
    cp={'schema_version':'fourgraph.p1_v4_look360_result_review_checkpoint.v1','status':'PASS_REVIEWED','decision':decision,'registered_look':360,'next_registered_look':400 if decision=='CONTINUE_TO_LOOK_400' else None,'primary_parent':'Constrained-BOSS','gates':{'full':{'registered_gate_pass':full['registered_gate_pass'],'precision_cs_pass':full['precision_confidence_sequence']['pass'],'coverage_pass':full['coverage']['crosses'],'high_guardrail_pass':full['High_guardrail']['pass'],'high_contributing_scenes':full['High_guardrail']['contributing_scenes']},'partial':{'registered_gate_pass':partial['registered_gate_pass'],'precision_cs_pass':partial['precision_confidence_sequence']['pass'],'coverage_pass':partial['coverage']['crosses'],'high_guardrail_pass':partial['High_guardrail']['pass'],'high_contributing_scenes':partial['High_guardrail']['contributing_scenes']},'ambiguous_pass':p['ambiguous_abstention_diagnostic']['pass'],'futility':r['futility']},'policy_changes':0,'validation_access':0,'holdout_access':0,'semantic_api_calls':0}
    audit={'schema_version':'fourgraph.p1_v4_look360_result_review_audit.v1','status':'PASS','decision':decision,'oracle_result_sha256':sh(ROOT/c['inputs']['oracle_results']['path']),'checkpoint_sha256':hashlib.sha256(cb(cp)).hexdigest().upper(),'registered_decision_applied':True,'tuning_performed':False,'validation_access':0,'holdout_access':0,'semantic_api_calls':0}
    report=f"# P1V4 calibration look 360 review\n\nDecision: **{decision}**. Full passes all registered gates. Partial passes precision and coverage but its High guardrail has {partial['High_guardrail']['contributing_scenes']} contributing scenes, below the registered minimum 60 and has not crossed its confidence sequence. Futility is false, so the next registered look is 400. No policy tuning, validation, or holdout access occurred.\n"
    return {ROOT/c['outputs']['checkpoint']:cb(cp),ROOT/c['outputs']['audit']:cb(audit),ROOT/c['outputs']['report']:report.encode()},audit
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--check',action='store_true'); x=ap.parse_args(); arts,a=build()
    for p,b in arts.items():
        if x.check:
            if not p.is_file() or p.read_bytes()!=b: raise RuntimeError(f'byte replay mismatch: {p}')
        else: p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b)
    print(json.dumps(a,indent=2))
if __name__=='__main__': main()
