import argparse,hashlib,json
from pathlib import Path
import yaml
R=Path(__file__).resolve().parents[1];C=R/'configs/p1_v4_independent_calibration_look120_statistical_execution_authorization.yaml'
def b(x):return(json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def build():
 c=yaml.safe_load(C.read_text());ch={};deps=[]
 for n,s in c['parents'].items():
  p=R/s['path'];v=h(p) if p.is_file() else None;ch[n+'_hash']=v==s['sha256'];deps.append({'name':n,'path':s['path'],'sha256':v})
 plan=json.loads((R/c['parents']['plan']['path']).read_text());a=c['authorization'];ch.update({'explicit':a['explicit_user_live_statistical_authorization_recorded'] is True,'exact_plan':len(plan['jobs'])==a['exact_fits']==24720,'no_api_or_oracle':not any(a[k] for k in ('semantic_api_calls_authorized','oracle_access_authorized','holdout_access_authorized'))});ok=all(ch.values());o={'task':c['task'],'status':'PASS_LIVE_STATISTICAL_AUTHORIZATION' if ok else 'FAIL','dependencies':deps,'authorization':a,'next_action':'RUN_24720_STATISTICAL_FITS_ONLY' if ok else 'REMEDIATION'};ob=b(o);au={'task':c['task'],'status':'PASS' if ok else 'FAIL','checks':ch,'hashes':{'config':h(C),'authorization':hashlib.sha256(ob).hexdigest().upper()},'boundary':{'semantic_api_calls':0,'oracle_access':False,'holdout_access':False}};return{R/c['outputs']['authorization']:ob,R/c['outputs']['audit']:b(au)}
def main():
 x=argparse.ArgumentParser();x.add_argument('--check',action='store_true');a=x.parse_args();d=build()
 if a.check:
  for p,v in d.items():
   if not p.is_file() or p.read_bytes()!=v:raise SystemExit('drift')
 else:
  for p,v in d.items():p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v)
 au=json.loads(d[R/yaml.safe_load(C.read_text())['outputs']['audit']]);print(json.dumps({'status':au['status'],'fits':24720,'api':0}));
 if au['status']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
