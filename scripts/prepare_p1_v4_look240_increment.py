"""Freeze, materialize, and plan the registered look-240 increment."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
from typing import Any
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from run_p1_v4_independent_calibration_look120_materialization import construct_scene

CFG=ROOT/'configs/p1_v4_look240_increment.yaml'
def cb(x:Any)->bytes:return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def load(p:Path)->dict:return json.loads(p.read_text(encoding='utf-8'))
def rows(p:Path)->list[dict]:return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x]
def write(p:Path,b:bytes)->None:
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():
  if p.read_bytes()!=b:raise RuntimeError(f'artifact drift: {p.relative_to(ROOT)}')
  return
 q=p.with_name(p.name+'.partial');q.write_bytes(b);q.replace(p)

def chosen(c:dict)->tuple[list[dict],list[str]]:
 plan=load(ROOT/c['parents']['identity_plan']);all_rows=rows(ROOT/c['parents']['identities'])
 ids=plan['exact_scene_ids_in_execution_order'][c['scope']['index_start']:c['scope']['index_end']]
 by={r['study_id']:r for r in all_rows};out=[by[x] for x in ids]
 if len(out)!=40 or len(set(ids))!=40 or any(r['batch_id']!=c['scope']['batch_id'] for r in out):raise RuntimeError('look-240 exact identity slice drift')
 if set(ids)&set(plan['exact_scene_ids_in_execution_order'][:200]):raise RuntimeError('look-240 overlap with prior looks')
 return out,ids

def freeze(c:dict)->None:
 result=load(ROOT/c['parents']['look200_results']);audit=load(ROOT/c['parents']['look200_audit']);review=load(ROOT/c['parents']['look200_review'])
 checks={'look200_decision':result.get('status')=='CONTINUE_TO_LOOK_240','audit_pass':audit.get('status')=='PASS_ORACLE_SCORING','review_go':review.get('decision')=='CONTINUE_TO_REGISTERED_LOOK_240','oracle_exact_200':audit.get('oracle_scenes_accessed')==200,'no_holdout':audit.get('holdout_access')==0}
 if not all(checks.values()):raise RuntimeError(f'look-200 parent gate failed: {checks}')
 rs,ids=chosen(c);body=b''.join(cb(r) for r in rs);master=load(ROOT/c['parents']['identity_plan'])
 plan={'schema_version':'fourgraph.p1_v4_look240_incremental_identity_plan.v1','status':'PASS_FROZEN_EXACT_40_IDENTITIES','previous_look':200,'next_look':240,'batch_id':c['scope']['batch_id'],'incremental_scene_ids_in_execution_order':ids,'cumulative_scene_ids_in_execution_order':master['exact_scene_ids_in_execution_order'][:240],'incremental_identity_sha256':hashlib.sha256(body).hexdigest().upper(),'component_seeds_by_scene':{r['study_id']:r['component_seeds'] for r in rs},'spend_attestation':c['spend_attestation'],'explicit_user_authorization':c['authorization'],'validation_locked':True,'holdout_locked':True}
 aud={'status':'PASS','checks':checks,'incremental_scenes':40,'cumulative_scenes':240,'unique':len(set(plan['cumulative_scene_ids_in_execution_order']))==240,'api_calls':0,'oracle_access':0,'validation_access':0,'holdout_access':0}
 write(ROOT/'data/manifests/p1_v4_look240_incremental_exact_identities.jsonl',body);write(ROOT/'data/manifests/p1_v4_look240_incremental_exact_identity_plan.json',cb(plan));write(ROOT/'data/manifests/p1_v4_look240_incremental_exact_identity_audit.json',cb(aud))

def materialize(c:dict)->None:
 rs,ids=chosen(c);generation=yaml.safe_load((ROOT/c['parents']['generation_contract']).read_text())['generation'];story_cfg=yaml.safe_load((ROOT/c['parents']['story_protocol']).read_text())
 sr,pr=[],[];scene_root=ROOT/c['roots']['generated'];public_root=ROOT/c['roots']['public']
 for identity in rs:
  contents,meta,recs=construct_scene(identity,generation,story_cfg);sid=identity['study_id']
  for n in ('observations.npy','metadata.json','alias_map.json'):write(scene_root/sid/n,contents[n])
  for rec in recs:
   p=public_root/sid/f"story_{rec['variant']}.json";write(p,contents[f"story_{rec['variant']}.json"]);rec['artifact_path']=p.relative_to(ROOT).as_posix()
  sr.append({'study_id':sid,'scene_id':identity['contract_scene_id'],'observation_path':(scene_root/sid/'observations.npy').relative_to(ROOT).as_posix(),'metadata_path':(scene_root/sid/'metadata.json').relative_to(ROOT).as_posix(),'alias_map_path':(scene_root/sid/'alias_map.json').relative_to(ROOT).as_posix(),'observation_sha256':meta['observation_sha256'],'scm_commitment_sha256':meta['scm_commitment_sha256']});pr.extend(recs)
 out={'schema_version':'fourgraph.p1_v4_look240_materialization.v1','records':sr};pub={'schema_version':'fourgraph.p1_v4_look240_public_inputs.v1','records':pr};counts={v:sum(x['variant']==v for x in pr) for v in ('full','partial','ambiguous')};aud={'status':'PASS_MATERIALIZATION','scenes':len(sr),'stories':len(pr),'variant_counts':counts,'exact_ids':[x['study_id'] for x in sr]==ids,'semantic_api_calls':0,'oracle_access':0,'validation_access':0,'holdout_access':0}
 if not(aud['scenes']==40 and aud['stories']==120 and all(v==40 for v in counts.values()) and aud['exact_ids']):raise RuntimeError('materialization audit failed')
 write(ROOT/'data/manifests/p1_v4_look240_incremental_materialization.json',cb(out));write(ROOT/'data/manifests/p1_v4_look240_incremental_public_inputs.json',cb(pub));write(ROOT/'data/manifests/p1_v4_look240_incremental_materialization_audit.json',cb(aud))

def stat_plan(c:dict)->None:
 ids=[r['study_id'] for r in load(ROOT/'data/manifests/p1_v4_look240_incremental_materialization.json')['records']];jobs=[]
 for sid in ids:
  for alg,reps in (('Single-BOSS',1),('Bootstrap-BOSS',200),('PC',1),('MMPC',1),('FGES',1),('Constrained-BOSS',1),('Constrained-FGES',1)):
   for rep in range(reps):
    x={'scene_id':sid,'algorithm':alg,'repetition':rep,'seed':int.from_bytes(hashlib.sha256(f'P1V4CAL|{sid}|{alg}|{rep}'.encode()).digest()[:8],'big')};x['execution_id']=hashlib.sha256(cb(x)).hexdigest().upper();jobs.append(x)
 plan={'schema_version':'fourgraph.p1_v4_look240_statistical_plan.v1','status':'FROZEN_AUTHORIZED','scene_ids':ids,'parameters':yaml.safe_load((ROOT/'configs/p1_v4_look160_incremental_statistical_execution.yaml').read_text())['parameters'],'jobs':jobs};auth={'status':'PASS_LIVE_STATISTICAL_AUTHORIZATION','plan_sha256':hashlib.sha256(cb(plan)).hexdigest().upper(),'exact_fits':8240,'concurrency':1,'semantic_api_calls':0,'oracle_access':0,'holdout_access':0}
 if len(jobs)!=8240 or len({j['execution_id'] for j in jobs})!=8240:raise RuntimeError('statistical plan drift')
 write(ROOT/'data/manifests/p1_v4_look240_incremental_statistical_plan.json',cb(plan));write(ROOT/'data/manifests/p1_v4_look240_incremental_statistical_live_authorization.json',cb(auth));write(ROOT/'data/manifests/p1_v4_look240_incremental_statistical_preflight_audit.json',cb({'status':'PASS','planned_fits':8240,'actual_fits':0,'unique':True,'semantic_api_calls':0,'oracle_access':0,'holdout_access':0}))

def semantic_plan(c:dict)->None:
 sa=load(ROOT/'data/manifests/p1_v4_look240_incremental_statistical_execution_audit.json')
 if sa.get('status')!='PASS_STATISTICAL_EXECUTION' or sa.get('complete_terminal_records')!=8240:raise RuntimeError('statistical execution incomplete')
 pub=load(ROOT/'data/manifests/p1_v4_look240_incremental_public_inputs.json')['records'];by_story={(x['study_id'],x['variant']):x for x in pub};ids=sorted({x['study_id'] for x in pub});graphs={}
 for p in (ROOT/c['roots']['statistical']/'normalized').glob('*.json'):
  r=load(p);j=r['job']
  if j['algorithm'] in {'Constrained-BOSS','Constrained-FGES'}:
   if r.get('status')!='VALID':raise RuntimeError(f'invalid constrained parent: {j}')
   graphs[(j['scene_id'],j['algorithm'])]=r['graph']
 pools,calls={},[]
 for sid in ids:
  pairs=set()
  for alg in ('Constrained-BOSS','Constrained-FGES'):
   g=graphs[(sid,alg)];pairs|={tuple(sorted(e)) for e in g.get('directed',[])+g.get('undirected',[])}
  aliases=load(ROOT/c['roots']['generated']/sid/'alias_map.json')['alias_map'];prs=[{'pair_id':f'pair_{i:03d}','node_a_canonical':a,'node_b_canonical':b,'node_a_alias':aliases[a],'node_b_alias':aliases[b]} for i,(a,b) in enumerate(sorted(pairs),1)];ph=hashlib.sha256(cb(prs)).hexdigest().upper();pools[sid]={'pairs':prs,'pair_pool_sha256':ph,'source':'union_all_constrained_parent_adjacencies'}
  for variant in ('full','partial'):
   story=by_story[(sid,variant)]
   for prompt in ('P1','P2','P3','P4','P5','P6'):calls.append({'logical_id':f'{sid}/{variant}/{prompt}','study_id':sid,'variant':variant,'prompt_id':prompt,'model':c['semantic']['model'],'reasoning_effort':'medium','story_artifact_path':story['artifact_path'],'story_content_sha256':story['content_sha256'],'pair_count':len(prs),'pair_ids':[x['pair_id'] for x in prs],'pair_pool_sha256':ph,'conditions':['constrained_boss','constrained_fges']})
 counts=[len(x['pairs']) for x in pools.values()];plan={'schema_version':'fourgraph.p1_v4_look240_mini_semantic_plan.v1','status':'FROZEN','model':c['semantic']['model'],'reasoning_effort':'medium','logical_calls':calls,'pair_pools':pools,'story_variants':['full','partial'],'ambiguous_increment':'excluded_by_fixed_diagnostic_subset','nonedge':'excluded','primary_meek_closure':'forbidden'}
 if len(calls)!=480 or len(pools)!=40 or min(counts)<1 or max(counts)>21:raise RuntimeError('semantic plan drift')
 write(ROOT/'data/manifests/p1_v4_look240_incremental_mini_semantic_plan.json',cb(plan));write(ROOT/'data/manifests/p1_v4_look240_incremental_mini_semantic_plan_audit.json',cb({'status':'PASS','scenes':40,'logical_calls':480,'scene_pair_records':sum(counts),'min_pairs':min(counts),'max_pairs':max(counts),'api_calls':0,'oracle_access':0,'holdout_access':0}))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=('freeze','materialize','stat-plan','semantic-plan','all-offline'));a=ap.parse_args();c=yaml.safe_load(CFG.read_text());stages=('freeze','materialize','stat-plan') if a.stage=='all-offline' else (a.stage,)
 for stage in stages:{'freeze':freeze,'materialize':materialize,'stat-plan':stat_plan,'semantic-plan':semantic_plan}[stage](c)
 print(json.dumps({'status':'PASS','stage':a.stage}))
if __name__=='__main__':main()
