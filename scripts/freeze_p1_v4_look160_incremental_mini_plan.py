"""Freeze shared Mini-medium inputs for the 40-scene calibration increment."""
import argparse,hashlib,json
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/'data/manifests/p1_v4_independent_calibration_look160_incremental_public_inputs.json'
STAT=ROOT/'results/raw/p1_v4_independent_calibration/look160_increment/statistical/normalized'
STAT_AUD=ROOT/'data/manifests/p1_v4_look160_incremental_statistical_execution_audit.json'
PLAN=ROOT/'data/manifests/p1_v4_look160_incremental_mini_semantic_plan.json'
AUD=ROOT/'data/manifests/p1_v4_look160_incremental_mini_semantic_plan_audit.json'
def cb(x):return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def sh(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def build():
 sa=json.loads(STAT_AUD.read_text());
 if sa.get('status') not in {'PASS','PASS_STATISTICAL_EXECUTION'} or sa.get('complete_terminal_records')!=8240:raise RuntimeError('statistical audit not PASS')
 pub=json.loads(PUBLIC.read_text())['records'];by={(r['study_id'],r['variant']):r for r in pub};ids=sorted({r['study_id'] for r in pub});graphs={}
 for p in STAT.glob('*.json'):
  r=json.loads(p.read_text());j=r['job']
  if j['algorithm'] in {'Constrained-BOSS','Constrained-FGES'}:
   if r.get('status')!='VALID':raise RuntimeError(f'invalid constrained parent {j}')
   graphs[(j['scene_id'],j['algorithm'])]=r['graph']
 if len(ids)!=40 or len(graphs)!=80:raise RuntimeError('input/graph count drift')
 pools={};calls=[]
 for sid in ids:
  pairs=set()
  for alg in ('Constrained-BOSS','Constrained-FGES'):
   g=graphs[(sid,alg)];pairs|={tuple(sorted(e)) for e in g.get('directed',[])+g.get('undirected',[])}
  aliases=json.loads((ROOT/f'data/generated/p1_v4_independent_calibration/look160_increment/{sid}/alias_map.json').read_text())['alias_map']
  rows=[{'pair_id':f'pair_{i:03d}','node_a_canonical':a,'node_b_canonical':b,'node_a_alias':aliases[a],'node_b_alias':aliases[b]} for i,(a,b) in enumerate(sorted(pairs),1)];ph=hashlib.sha256(cb(rows)).hexdigest().upper();pools[sid]={'pairs':rows,'pair_pool_sha256':ph,'source':'union_all_constrained_parent_adjacencies'}
  # Ambiguous remains a fixed first-120 diagnostic subset; the registered increment certifies Full/Partial only.
  for variant in ('full','partial'):
   story=by[(sid,variant)]
   for prompt_id in ('P1','P2','P3','P4','P5','P6'):
    calls.append({'logical_id':f'{sid}/{variant}/{prompt_id}','study_id':sid,'variant':variant,'prompt_id':prompt_id,'model':'gpt-5.4-mini-2026-03-17','reasoning_effort':'medium','story_artifact_path':story['artifact_path'],'story_content_sha256':story['content_sha256'],'pair_count':len(rows),'pair_ids':[x['pair_id'] for x in rows],'pair_pool_sha256':ph,'conditions':['constrained_boss','constrained_fges']})
 counts=[len(x['pairs']) for x in pools.values()];plan={'schema_version':'fourgraph.p1_v4_look160_incremental_mini_semantic_plan.v1','status':'FROZEN','model':'gpt-5.4-mini-2026-03-17','reasoning_effort':'medium','logical_calls':calls,'pair_pools':pools,'story_variants':['full','partial'],'ambiguous_increment':'excluded_by_fixed_diagnostic_subset','nonedge':'excluded','primary_meek_closure':'forbidden'}
 checks={'scenes_40':len(ids)==40,'calls_480':len(calls)==480,'twelve_calls_per_scene':all(sum(c['study_id']==sid for c in calls)==12 for sid in ids),'pair_pool_positive':min(counts)>0,'pair_pool_max_21':max(counts)<=21,'all_parents_valid':len(graphs)==80}
 audit={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'counts':{'scenes':40,'public_story_artifacts_available':len(pub),'used_story_inputs':80,'logical_calls':len(calls),'scene_pair_records':sum(counts),'min_pairs':min(counts),'max_pairs':max(counts)},'hashes':{'public_inputs':sh(PUBLIC),'statistical_audit':sh(STAT_AUD),'plan':hashlib.sha256(cb(plan)).hexdigest().upper()},'boundary':{'provider_calls':0,'oracle_access':0,'holdout_access':0}}
 return {PLAN:cb(plan),AUD:cb(audit)}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();arts=build()
 for p,b in arts.items():
  if a.check:
   if not p.is_file() or p.read_bytes()!=b:raise RuntimeError(f'drift {p}')
  else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 print(json.dumps(json.loads(arts[AUD])))
if __name__=='__main__':main()
