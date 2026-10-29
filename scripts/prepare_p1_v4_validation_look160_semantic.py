"""Freeze validation look-160 constrained parents and the shared Mini pool.

Offline only: no provider, Oracle, or holdout access.
"""
import hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MAN=ROOT/'data/manifests'; GENERATED=ROOT/'data/generated/p1_v4_independent_validation/look160'
NORMALIZED=ROOT/'results/raw/p1_v4_independent_validation/look160/statistical/normalized'
STAT=MAN/'p1_v4_validation_look160_statistical_execution_audit.json'
MAT=MAN/'p1_v4_validation_look160_materialization.json'; PUBLIC=MAN/'p1_v4_validation_look160_public_inputs.json'
PLAN=MAN/'p1_v4_validation_look160_mini_semantic_plan_v2.json'; AUDIT=MAN/'p1_v4_validation_look160_mini_semantic_plan_v2_audit.json'

def cb(x):return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def write(path,obj):
 body=cb(obj)
 if path.exists() and path.read_bytes()!=body:raise RuntimeError(f'artifact drift: {path}')
 if not path.exists():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)

def main():
 stat=load(STAT)
 if stat.get('status')!='PASS_STATISTICAL_EXECUTION' or stat.get('complete_terminal_records')!=32960:raise RuntimeError('statistical execution not complete')
 if any(stat.get(k) for k in ('semantic_api_calls','oracle_access','holdout_access')):raise RuntimeError('statistical boundary violation')
 mats=load(MAT)['records'];ids=[x['study_id'] for x in mats]
 if len(ids)!=160 or len(set(ids))!=160:raise RuntimeError('identity drift')
 public=load(PUBLIC);stories={(x['study_id'],x['variant']):x for x in public['records']}
 if len(stories)!=480:raise RuntimeError('public story inventory drift')
 exact=load(MAN/'p1_v4_validation_look160_exact_identity_plan.json');ambiguous=set(exact['ambiguous_scene_ids'])
 graphs={};invalid=[]
 for path in NORMALIZED.glob('*.json'):
  rec=load(path);job=rec['job'];alg=job['algorithm']
  if alg in ('Constrained-BOSS','Constrained-FGES'):
   if rec.get('status')!='VALID':invalid.append({'scene_id':job['scene_id'],'algorithm':alg,'status':rec.get('status')})
   else:
    key=(job['scene_id'],alg)
    if key in graphs:raise RuntimeError(f'duplicate parent: {key}')
    graphs[key]=rec['graph']
 if invalid:raise RuntimeError(f'invalid constrained parents: {invalid[:5]} total={len(invalid)}')
 if len(graphs)!=320:raise RuntimeError(f'expected 320 parents, got {len(graphs)}')
 pools={};calls=[]
 for sid in ids:
  edges=set()
  for alg in ('Constrained-BOSS','Constrained-FGES'):
   g=graphs[(sid,alg)];edges.update(tuple(sorted(x)) for x in g['directed']+g['undirected'])
  aliases=load(GENERATED/sid/'alias_map.json')['alias_map']
  pairs=[{'pair_id':f'pair_{i:03d}','node_a_canonical':a,'node_b_canonical':b,'node_a_alias':aliases[a],'node_b_alias':aliases[b]} for i,(a,b) in enumerate(sorted(edges),1)]
  if not 1<=len(pairs)<=21:raise RuntimeError(f'pair count out of range: {sid} {len(pairs)}')
  ph=hashlib.sha256(cb(pairs)).hexdigest().upper();pools[sid]={'pairs':pairs,'pair_pool_sha256':ph,'source':'union_all_constrained_parent_adjacencies'}
  variants=['full','partial']+(['ambiguous'] if sid in ambiguous else [])
  for variant in variants:
   story=stories[(sid,variant)];path=ROOT/story['artifact_path']
   if sha(path)!=story['artifact_sha256']:raise RuntimeError(f'story hash drift: {sid}/{variant}')
   story_text=load(path).get('builder_input',{}).get('story')
   if not isinstance(story_text,str) or not story_text:raise RuntimeError(f'missing public story text: {sid}/{variant}')
   story_content_sha256=hashlib.sha256(story_text.encode('utf-8')).hexdigest().upper()
   for prompt in ('P1','P2','P3','P4','P5','P6'):
    calls.append({'logical_id':f'{sid}/{variant}/{prompt}','study_id':sid,'variant':variant,'prompt_id':prompt,'model':'gpt-5.4-mini-2026-03-17','reasoning_effort':'medium','story_artifact_path':story['artifact_path'],'story_artifact_sha256':story['artifact_sha256'],'story_content_sha256':story_content_sha256,'pair_count':len(pairs),'pair_ids':[x['pair_id'] for x in pairs],'pair_pool_sha256':ph,'conditions':['constrained_boss','constrained_fges']})
 if len(calls)!=2640 or len({x['logical_id'] for x in calls})!=2640:raise RuntimeError(f'call count drift: {len(calls)}')
 counts=[len(x['pairs']) for x in pools.values()]
 plan={'schema_version':'fourgraph.p1_v4_validation_look160_mini_semantic_plan.v2','status':'FROZEN_API_NOT_AUTHORIZED','model':'gpt-5.4-mini-2026-03-17','reasoning_effort':'medium','logical_calls':calls,'pair_pools':pools,'certification_variants':['full','partial'],'ambiguous_subset_scenes':120,'nonedge':'excluded','primary_meek_closure':'forbidden','v1_disposition':'superseded_before_api_due_story_content_hash_contract_defect'}
 write(PLAN,plan)
 audit={'status':'PASS_OFFLINE_SEMANTIC_PLAN_FREEZE','scenes':160,'parent_graphs':320,'logical_calls':2640,'full_partial_calls':1920,'ambiguous_calls':720,'scene_pair_records':sum(counts),'min_pairs':min(counts),'max_pairs':max(counts),'plan_sha256':sha(PLAN),'statistical_audit_sha256':sha(STAT),'public_input_manifest_sha256':sha(PUBLIC),'provider_preflight_calls':0,'study_api_calls':0,'oracle_access':0,'holdout_access':0}
 write(AUDIT,audit);print(json.dumps(audit,indent=2))
if __name__=='__main__':main()
