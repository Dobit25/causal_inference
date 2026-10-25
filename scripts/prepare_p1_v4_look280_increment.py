"""Materialize and plan the authorized P1V4 calibration look-280 increment."""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from run_p1_v4_independent_calibration_look120_materialization import construct_scene
CFG=ROOT/'configs/p1_v4_look280_increment.yaml'
def cb(x):return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def rows(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x]
def write(p,b):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists() and p.read_bytes()!=b:raise RuntimeError(f'artifact drift: {p.relative_to(ROOT)}')
 if not p.exists():p.write_bytes(b)
def selected(c):
 plan=load(ROOT/c['parents']['identity_plan']);rs=rows(ROOT/c['parents']['identities']);ids=plan['incremental_scene_ids_in_execution_order']
 if plan['status']!='PASS_FROZEN_EXACT_40_IDENTITIES_OFFLINE' or len(ids)!=40:raise RuntimeError('identity freeze not eligible')
 if load(ROOT/c['parents']['review']).get('decision')!='CONTINUE_TO_REGISTERED_LOOK_280':raise RuntimeError('look-240 review not eligible')
 if [r['study_id'] for r in rs]!=ids:raise RuntimeError('identity order drift')
 return rs,ids
def preflight(c):
 rs,ids=selected(c);checks={'exact_40':len(rs)==40,'unique':len(set(ids))==40,'batch':all(r['batch_id']==c['scope']['batch_id'] for r in rs),'unmaterialized':all(r['scene_materialized'] is False for r in rs),'authorized':c['authorization']['materialization'] is True,'validation_locked':not c['boundaries']['validation_access'],'holdout_locked':not c['boundaries']['holdout_access']};out={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'scene_ids':ids,'scenes_materialized':0,'api_calls':0,'oracle_access':0,'validation_access':0,'holdout_access':0};write(ROOT/'data/manifests/p1_v4_look280_incremental_materialization_preflight.json',cb(out));return out
def materialize(c):
 if preflight(c)['status']!='PASS':raise RuntimeError('preflight failed')
 rs,ids=selected(c);generation=yaml.safe_load((ROOT/c['parents']['generation_contract']).read_text())['generation'];story_cfg=yaml.safe_load((ROOT/c['parents']['story_protocol']).read_text());sr=[];pr=[];scene_root=ROOT/c['roots']['generated'];public_root=ROOT/c['roots']['public']
 for identity in rs:
  contents,meta,recs=construct_scene(identity,generation,story_cfg);sid=identity['study_id']
  for n in ('observations.npy','metadata.json','alias_map.json'):write(scene_root/sid/n,contents[n])
  for rec in recs:
   p=public_root/sid/f"story_{rec['variant']}.json";write(p,contents[f"story_{rec['variant']}.json"]);rec['artifact_path']=p.relative_to(ROOT).as_posix()
  sr.append({'study_id':sid,'scene_id':identity['contract_scene_id'],'observation_path':(scene_root/sid/'observations.npy').relative_to(ROOT).as_posix(),'metadata_path':(scene_root/sid/'metadata.json').relative_to(ROOT).as_posix(),'alias_map_path':(scene_root/sid/'alias_map.json').relative_to(ROOT).as_posix(),'observation_sha256':meta['observation_sha256'],'scm_commitment_sha256':meta['scm_commitment_sha256']});pr.extend(recs)
 counts={v:sum(x['variant']==v for x in pr) for v in ('full','partial','ambiguous')};audit={'status':'PASS_MATERIALIZATION','scenes':len(sr),'stories':len(pr),'variant_counts':counts,'exact_ids':[x['study_id'] for x in sr]==ids,'semantic_api_calls':0,'oracle_access':0,'validation_access':0,'holdout_access':0}
 if not(audit['scenes']==40 and audit['stories']==120 and all(v==40 for v in counts.values()) and audit['exact_ids']):raise RuntimeError('materialization audit failed')
 write(ROOT/'data/manifests/p1_v4_look280_incremental_materialization.json',cb({'schema_version':'fourgraph.p1_v4_look280_materialization.v1','records':sr}));write(ROOT/'data/manifests/p1_v4_look280_incremental_public_inputs.json',cb({'schema_version':'fourgraph.p1_v4_look280_public_inputs.v1','records':pr}));write(ROOT/'data/manifests/p1_v4_look280_incremental_materialization_audit.json',cb(audit));return audit
def stat_plan(c):
 ids=[r['study_id'] for r in load(ROOT/'data/manifests/p1_v4_look280_incremental_materialization.json')['records']];jobs=[]
 for sid in ids:
  for alg,reps in (('Single-BOSS',1),('Bootstrap-BOSS',200),('PC',1),('MMPC',1),('FGES',1),('Constrained-BOSS',1),('Constrained-FGES',1)):
   for rep in range(reps):
    x={'scene_id':sid,'algorithm':alg,'repetition':rep,'seed':int.from_bytes(hashlib.sha256(f'P1V4CAL|{sid}|{alg}|{rep}'.encode()).digest()[:8],'big')};x['execution_id']=hashlib.sha256(cb(x)).hexdigest().upper();jobs.append(x)
 plan={'schema_version':'fourgraph.p1_v4_look280_statistical_plan.v1','status':'FROZEN_AUTHORIZED','scene_ids':ids,'parameters':yaml.safe_load((ROOT/'configs/p1_v4_look160_incremental_statistical_execution.yaml').read_text())['parameters'],'jobs':jobs};body=cb(plan);auth={'status':'PASS_LIVE_STATISTICAL_AUTHORIZATION','explicit_user_authorization':True,'plan_sha256':hashlib.sha256(body).hexdigest().upper(),'exact_fits':8240,'concurrency':1,'semantic_api_calls':0,'oracle_access':0,'holdout_access':0}
 if len(jobs)!=8240 or len({j['execution_id'] for j in jobs})!=8240:raise RuntimeError('statistical plan drift')
 write(ROOT/'data/manifests/p1_v4_look280_incremental_statistical_plan.json',body);write(ROOT/'data/manifests/p1_v4_look280_incremental_statistical_live_authorization.json',cb(auth));write(ROOT/'data/manifests/p1_v4_look280_incremental_statistical_preflight_audit.json',cb({'status':'PASS','planned_fits':8240,'actual_fits':0,'unique':True,'semantic_api_calls':0,'oracle_access':0,'holdout_access':0}));return auth
def semantic_plan(c):
 sa=load(ROOT/'data/manifests/p1_v4_look280_incremental_statistical_execution_audit.json')
 if sa.get('status')!='PASS_STATISTICAL_EXECUTION' or sa.get('complete_terminal_records')!=8240:raise RuntimeError('statistical execution incomplete')
 pub=load(ROOT/'data/manifests/p1_v4_look280_incremental_public_inputs.json')['records'];by_story={(x['study_id'],x['variant']):x for x in pub};ids=[x['study_id'] for x in load(ROOT/'data/manifests/p1_v4_look280_incremental_materialization.json')['records']];graphs={}
 for p in (ROOT/c['roots']['statistical']/'normalized').glob('*.json'):
  r=load(p);j=r['job']
  if j['algorithm'] in {'Constrained-BOSS','Constrained-FGES'}:
   if r.get('status')!='VALID':raise RuntimeError(f'invalid constrained parent: {j}')
   graphs[(j['scene_id'],j['algorithm'])]=r['graph']
 pools={};calls=[]
 for sid in ids:
  pairs=set()
  for alg in ('Constrained-BOSS','Constrained-FGES'):
   g=graphs[(sid,alg)];pairs|={tuple(sorted(e)) for e in g.get('directed',[])+g.get('undirected',[])}
  aliases=load(ROOT/c['roots']['generated']/sid/'alias_map.json')['alias_map'];prs=[{'pair_id':f'pair_{i:03d}','node_a_canonical':a,'node_b_canonical':b,'node_a_alias':aliases[a],'node_b_alias':aliases[b]} for i,(a,b) in enumerate(sorted(pairs),1)];ph=hashlib.sha256(cb(prs)).hexdigest().upper();pools[sid]={'pairs':prs,'pair_pool_sha256':ph,'source':'union_all_constrained_parent_adjacencies'}
  for variant in ('full','partial'):
   story=by_story[(sid,variant)]
   for prompt in ('P1','P2','P3','P4','P5','P6'):calls.append({'logical_id':f'{sid}/{variant}/{prompt}','study_id':sid,'variant':variant,'prompt_id':prompt,'model':c['semantic']['model'],'reasoning_effort':'medium','story_artifact_path':story['artifact_path'],'story_content_sha256':story['content_sha256'],'pair_count':len(prs),'pair_ids':[x['pair_id'] for x in prs],'pair_pool_sha256':ph,'conditions':['constrained_boss','constrained_fges']})
 counts=[len(x['pairs']) for x in pools.values()];plan={'schema_version':'fourgraph.p1_v4_look280_mini_semantic_plan.v1','status':'FROZEN','model':c['semantic']['model'],'reasoning_effort':'medium','logical_calls':calls,'pair_pools':pools,'story_variants':['full','partial'],'ambiguous_increment':'excluded_by_fixed_diagnostic_subset','nonedge':'excluded','primary_meek_closure':'forbidden'}
 if len(calls)!=480 or len(pools)!=40 or min(counts)<1 or max(counts)>21:raise RuntimeError('semantic plan drift')
 body=cb(plan);write(ROOT/'data/manifests/p1_v4_look280_incremental_mini_semantic_plan.json',body);write(ROOT/'data/manifests/p1_v4_look280_incremental_mini_semantic_plan_audit.json',cb({'status':'PASS','scenes':40,'logical_calls':480,'scene_pair_records':sum(counts),'expected_pair_records':sum(counts)*12,'expected_six_vote_groups':sum(counts)*2,'min_pairs':min(counts),'max_pairs':max(counts),'plan_sha256':hashlib.sha256(body).hexdigest().upper(),'api_calls':0,'oracle_access':0,'holdout_access':0}));return plan
def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=('preflight','materialize','stat-plan','semantic-plan'));a=ap.parse_args();c=yaml.safe_load(CFG.read_text());result={'preflight':preflight,'materialize':materialize,'stat-plan':stat_plan,'semantic-plan':semantic_plan}[a.stage](c);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
