"""Record explicit authorization for exactly 160 calibration Oracle commitments."""
import argparse,hashlib,json
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];CFG=ROOT/'configs/p1_v4_look160_cumulative_oracle_scoring_live_authorization.yaml'
def cb(x):return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sh(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def build():
 c=yaml.safe_load(CFG.read_text());checks={n:(ROOT/s['path']).is_file() and sh(ROOT/s['path'])==s['sha256'] for n,s in c['parents'].items()};cp=json.loads((ROOT/c['parents']['checkpoint']['path']).read_text());checks.update({'checkpoint_ready':cp.get('status')=='PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION','exact_160':len(cp.get('exact_scene_ids',[]))==160 and c['authorization']['exact_calibration_scenes']==160,'explicit':c['authorization']['explicit_user_authorization'] is True,'boundary':c['authorization']['semantic_api_calls']==0 and c['authorization']['statistical_reruns']==0 and not c['authorization']['holdout_access'] and c['authorization']['closure']=='forbidden'});ok=all(checks.values());auth={'schema_version':'fourgraph.p1_v4_look160_cumulative_oracle_scoring_live_authorization.v1','task':c['task'],'status':'AUTHORIZED_CALIBRATION_LOOK160_ORACLE_SCORING' if ok else 'FAIL','explicit_user_authorization':True,'checkpoint_sha256':sh(ROOT/c['parents']['checkpoint']['path']),'scope':{'exact_scene_ids':cp['exact_scene_ids'],'parent_conditions':['Constrained-BOSS','Constrained-FGES'],'certification_variants':['full','partial'],'ambiguous_diagnostic_scope':'first_120_only'},'permitted':['reconstruct_160_registered_oracle_commitments','calculate_registered_cumulative_metrics'],'forbidden':['semantic_api','statistical_rerun','validation_or_holdout','closure','threshold_tuning']};audit={'status':'PASS' if ok else 'FAIL','checks':checks,'authorization_sha256':hashlib.sha256(cb(auth)).hexdigest().upper(),'oracle_access_before_execution':0,'holdout_access':0,'semantic_api_calls':0}
 return c,{ROOT/c['outputs']['authorization']:cb(auth),ROOT/c['outputs']['audit']:cb(audit)}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();c,arts=build()
 for p,b in arts.items():
  if a.check:
   if not p.is_file() or p.read_bytes()!=b:raise RuntimeError(f'drift {p}')
  else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 print(json.dumps(json.loads(arts[ROOT/c['outputs']['audit']]),indent=2))
if __name__=='__main__':main()
