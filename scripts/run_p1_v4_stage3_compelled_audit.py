"""Frozen Mini-medium compelled-direction audit for P1V4 development only."""
from __future__ import annotations
import argparse, hashlib, json, os, sys, time
from collections import defaultdict
from pathlib import Path
from typing import Any
import openai, yaml
from openai import OpenAI

ROOT=Path(__file__).resolve().parents[1]; sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from fourgraph.p1_stories import assign_aliases
from fourgraph.semantic_pair_contract_v2 import StablePair
from fourgraph.semantic_sentence_id_contract import render_sentence_id_prompt, validate_response_by_pair, aggregate_six_votes
from fourgraph.p1_generation import scene_scm_record
from materialize_p1_v4_stage3 import build_blueprint
from run_p1_v4_stage3_shared_semantic_cau import load_key
C=ROOT/'configs/p1_v4_stage3_compelled_semantic_audit.yaml'; PREFLIGHT=ROOT/'configs/p1_v4_stage3_method_development_preflight.yaml'; IDENTITIES=ROOT/'data/manifests/p1_v4_stage3_exact_identities.jsonl'
def can(x): return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def shab(b): return hashlib.sha256(b).hexdigest().upper()
def load(p):
 t=p.read_text(encoding='utf-8'); return yaml.safe_load(t) if p.suffix in ('.yaml','.yml') else json.loads(t)
def rows(p): return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def write(p,x): p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(can(x))
def append(p,x): p.parent.mkdir(parents=True,exist_ok=True); open(p,'ab').write(can(x))
def cfg(): return load(C)
def allowed(): return {f'P1V4SD{i:03d}' for i in range(30)}

def freeze():
 c=cfg()
 for k in ('parent_manifest','public_stories','mini_preflight'):
  p=ROOT/c['parents'][k]; expected=c['parents'][f'{k}_sha256'];
  if sha(p)!=expected: raise RuntimeError(f'parent hash drift: {k}')
 pre=load(ROOT/c['parents']['mini_preflight'])
 if pre.get('status')!='PASS' or pre.get('model')!=c['scope']['model_snapshot'] or pre.get('reasoning_effort')!=c['scope']['reasoning_effort'] or pre.get('truncation')!='disabled' or pre.get('worst_case_pairs',0)<21: raise RuntimeError('mini preflight cannot cover this contract')
 parent=load(ROOT/c['parents']['parent_manifest'])['conditions']; stories=load(ROOT/c['parents']['public_stories'])['records']; story={(r['study_id'],r['variant']):r for r in stories}; t19=load(ROOT/c['parents']['t19_config']); ids=allowed(); pools=[]; calls=[]
 for sid in sorted(ids):
  graphs=[parent[x][sid]['graph'] for x in c['scope']['conditions']]
  nodes=graphs[0]['nodes']; alias=dict(assign_aliases(nodes,t19['aliases']['lexicon'],int(t19['randomness']['master_seed']),sid))
  edges=sorted({tuple(sorted(e)) for g in graphs for e in g['directed']})
  pair_rows=[{'pair_id':f'compelled_pair_{i:03d}','node_a_id':a,'node_a_alias':alias[a],'node_b_id':b,'node_b_alias':alias[b]} for i,(a,b) in enumerate(edges,1)]
  proposed={condition:[list(e) for e in parent[condition][sid]['graph']['directed']] for condition in c['scope']['conditions']}
  pools.append({'scene_id':sid,'pairs':pair_rows,'proposed_directions':proposed,'alias_map_sha256':shab(can(alias))})
  for variant in c['scope']['variants']:
   s=story.get((sid,variant));
   if not s: raise RuntimeError('public story missing')
   for pid in (c['scope']['prompt_variants'] if pair_rows else ()):
    calls.append({'logical_id':f'{sid}/{variant}/{pid}','study_id':sid,'variant':variant,'prompt_id':pid,'pair_ids':[x['pair_id'] for x in pair_rows],'story_path':s['artifact_path'],'story_content_sha256':s['content_sha256'],'pair_pool_sha256':shab(can(pair_rows)),'model_snapshot':c['scope']['model_snapshot'],'reasoning_effort':c['scope']['reasoning_effort']})
 if len({x['logical_id'] for x in calls})!=len(calls): raise RuntimeError('duplicate logical calls')
 write(ROOT/c['outputs']['pool'],{'schema_version':'fourgraph.p1_v4_compelled_audit_pair_pool.v1','records':pools})
 write(ROOT/c['outputs']['plan'],{'schema_version':'fourgraph.p1_v4_compelled_audit_plan.v1','status':'FROZEN','logical_calls':calls,'planned_logical_calls':len(calls),'structural_no_query_scenes':[x['scene_id'] for x in pools if not x['pairs']],'max_pairs_per_scene':max(len(x['pairs']) for x in pools),'contract':c['contract']})
 audit={'task':c['task'],'status':'PASS_FROZEN_READY_FOR_LIVE_AUTHORIZATION','scenes':30,'queryable_scenes':sum(bool(x['pairs']) for x in pools),'structural_no_query_scenes':[x['scene_id'] for x in pools if not x['pairs']],'logical_calls':len(calls),'structural_no_query_logical_slots':360-len(calls),'pair_pool_sha256':sha(ROOT/c['outputs']['pool']),'plan_sha256':sha(ROOT/c['outputs']['plan']),'oracle_access':0,'holdout_access':0,'semantic_api_calls':0}
 write(ROOT/c['outputs']['freeze_audit'],audit); print(json.dumps(audit,indent=2)); return audit

def authorize():
 c=cfg(); plan=ROOT/c['outputs']['plan']; audit=load(ROOT/c['outputs']['freeze_audit'])
 if audit.get('status')!='PASS_FROZEN_READY_FOR_LIVE_AUTHORIZATION': raise RuntimeError('freeze audit not ready')
 out={'task':c['task'],'status':'PASS_LIVE_AUTHORIZED','explicit_user_authorization':True,'plan_sha256':sha(plan),'freeze_audit_sha256':sha(ROOT/c['outputs']['freeze_audit']),'authorized_logical_calls':load(plan)['planned_logical_calls'],'oracle_access':False,'holdout_access':False,'closure':False}
 write(ROOT/c['outputs']['authorization'],out); print(json.dumps(out,indent=2)); return out

def jobs():
 c=cfg(); plan=load(ROOT/c['outputs']['plan']); auth=load(ROOT/c['outputs']['authorization'])
 if auth.get('status')!='PASS_LIVE_AUTHORIZED' or auth.get('plan_sha256')!=sha(ROOT/c['outputs']['plan']) or auth.get('authorized_logical_calls')!=len(plan['logical_calls']): raise RuntimeError('live authorization drift')
 pool={x['scene_id']:x for x in load(ROOT/c['outputs']['pool'])['records']}; ans=[]
 for x in plan['logical_calls']:
  artifact=load(ROOT/x['story_path']); story=artifact['builder_input']['story']
  if shab(story.encode())!=x['story_content_sha256']: raise RuntimeError('story drift')
  p=tuple(StablePair(**r) for r in pool[x['study_id']]['pairs'])
  if shab(can([r for r in pool[x['study_id']]['pairs']]))!=x['pair_pool_sha256']: raise RuntimeError('pool drift')
  prompt=render_sentence_id_prompt(prompt_id=x['prompt_id'],story=story,pairs=p)
  ans.append({**x,'story':story,'pairs':p,'prompt':prompt,'prompt_render_sha256':shab(prompt.encode())})
 return ans
def cache(path):
 d={}
 if path.exists():
  for n,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
   if line:
    x=json.loads(line); k=x.get('logical_id')
    if not k or k in d: raise RuntimeError(f'duplicate/malformed cache line {n}')
    d[k]=x
 return d
def execute(live):
 c=cfg(); js=jobs(); root=ROOT/c['runtime']['cache_root']; raw=root/'raw_responses.jsonl'; cached=cache(raw); pending=[x for x in js if x['logical_id'] not in cached]
 if not live: print(json.dumps({'status':'PASS_DRY_RUN','planned':len(js),'cached':len(cached),'pending':len(pending),'semantic_api_calls':0},indent=2)); return
 if sys.version.split()[0]!='3.10.21' or openai.__version__!='3.6.0': raise RuntimeError('canonical cau runtime drift')
 schema=load(ROOT/c['contract']['schema']); client=OpenAI(api_key=load_key(),max_retries=0,timeout=120); last=0.0
 for ordinal,x in enumerate(pending,1):
  wait=60/c['runtime']['calls_per_minute']-(time.perf_counter()-last)
  if wait>0: time.sleep(wait)
  began=time.perf_counter(); last=began
  try:
   r=client.responses.create(model=x['model_snapshot'],input=x['prompt'],reasoning={'effort':x['reasoning_effort']},max_output_tokens=c['contract']['max_output_tokens'],service_tier='default',store=False,text={'format':{'type':'json_schema','name':'semantic_sentence_id_response_v1','schema':schema,'strict':True}},metadata={'task':c['task'],'logical_id':x['logical_id']})
   text=r.output_text or ''; u=r.usage
   try: v=validate_response_by_pair(json.loads(text),x['pairs'],x['story']); status='completed_valid' if v['response_valid'] else 'completed_pair_invalid'
   except Exception as e: v={'response_valid':False,'validation_exception':f'{type(e).__name__}: {e}','pairs':[]}; status='completed_schema_invalid'
   rec={'logical_id':x['logical_id'],'ordinal':ordinal,'status':status,'scene_id':x['study_id'],'variant':x['variant'],'prompt_id':x['prompt_id'],'model_snapshot':r.model,'reasoning_effort':x['reasoning_effort'],'request_id':getattr(r,'_request_id',None),'input_tokens':int(u.input_tokens),'output_tokens':int(u.output_tokens),'reasoning_tokens':int(getattr(getattr(u,'output_tokens_details',None),'reasoning_tokens',0) or 0),'total_tokens':int(getattr(u,'total_tokens',u.input_tokens+u.output_tokens)),'latency_ms':round((time.perf_counter()-began)*1000),'story_content_sha256':x['story_content_sha256'],'pair_pool_sha256':x['pair_pool_sha256'],'prompt_render_sha256':x['prompt_render_sha256'],'response_sha256':shab(text.encode()),'raw_text':text}
  except Exception as e:
   rec={'logical_id':x['logical_id'],'ordinal':ordinal,'status':'provider_error','scene_id':x['study_id'],'variant':x['variant'],'prompt_id':x['prompt_id'],'model_snapshot':x['model_snapshot'],'reasoning_effort':x['reasoning_effort'],'error_type':type(e).__name__,'error_message':str(e)[:1000],'latency_ms':round((time.perf_counter()-began)*1000),'story_content_sha256':x['story_content_sha256'],'pair_pool_sha256':x['pair_pool_sha256'],'prompt_render_sha256':x['prompt_render_sha256']}
  append(raw,rec); cached[rec['logical_id']]=rec
  if ordinal%20==0: print(json.dumps({'progress':f'{ordinal}/{len(pending)}','cached':len(cached)}),flush=True)
 counts={s:sum(x['status']==s for x in cached.values()) for s in ('completed_valid','completed_pair_invalid','completed_schema_invalid','provider_error')}
 audit={'task':c['task'],'status':'PASS' if len(cached)==len(js) and not counts['provider_error'] else 'INCOMPLETE_OR_PROVIDER_INCIDENT','planned':len(js),'recorded':len(cached),'counts':counts,'provider_usage':{k:sum(int(x.get(k,0) or 0) for x in cached.values()) for k in ('input_tokens','output_tokens','reasoning_tokens','total_tokens')},'raw_sha256':sha(raw),'oracle_access':0,'holdout_access':0,'closure':0}
 write(ROOT/c['outputs']['response_freeze'],audit); print(json.dumps(audit,indent=2))

def oracle_dags():
 gen=load(PREFLIGHT)['generation']; result={}
 for i in rows(IDENTITIES):
  if i.get('study_id') in allowed():
   b=build_blueprint(i,gen); result[i['study_id']]=set(b.dag.directed)
 return result
def score():
 c=cfg(); freeze_audit=load(ROOT/c['outputs']['response_freeze'])
 if freeze_audit.get('status')!='PASS': raise RuntimeError('response set incomplete; cannot score')
 js={x['logical_id']:x for x in jobs()}; raw=cache(ROOT/c['runtime']['cache_root']/'raw_responses.jsonl'); pool={x['scene_id']:x for x in load(ROOT/c['outputs']['pool'])['records']}; grouped=defaultdict(list)
 for lid,r in raw.items():
  x=js[lid]; v=validate_response_by_pair(json.loads(r['raw_text']),x['pairs'],x['story']) if r['status']!='provider_error' else {'pairs':[]}
  for pr in v['pairs']: grouped[(x['study_id'],x['variant'],pr['pair_id'])].append({'prompt_id':x['prompt_id'],**pr})
 groups=[]
 for (sid,var,pid),vs in sorted(grouped.items()):
  if len(vs)!=6: raise RuntimeError('not six votes')
  g=aggregate_six_votes(vs,balanced=True); groups.append({'scene_id':sid,'variant':var,'pair_id':pid,**g})
 out=ROOT/c['outputs']['groups']; out.write_bytes(b''.join(can(x) for x in groups))
 oracle=oracle_dags(); parents=load(ROOT/c['parents']['parent_manifest'])['conditions']; lookup={(x['scene_id'],x['variant'],x['pair_id']):x for x in groups}; result={}
 for condition in c['scope']['conditions']:
  for variant in c['scope']['variants']:
   baseline=[]; confirmed=[]; status=defaultdict(int)
   for sid in sorted(allowed()):
    pmap={x['pair_id']:x for x in pool[sid]['pairs']}
    for edge in parents[condition][sid]['graph']['directed']:
     e=tuple(edge); baseline.append(e in oracle[sid]); pair=next(pid for pid,x in pmap.items() if tuple(sorted((x['node_a_id'],x['node_b_id'])))==tuple(sorted(e)))
     g=lookup[(sid,variant,pair)]
     pred=None
     if g['automatic_candidate'] and g['candidate_direction']:
      x=pmap[pair]; pred=(x['node_a_id'],x['node_b_id']) if g['candidate_direction']=='A_TO_B' else (x['node_b_id'],x['node_a_id'])
     if pred==e: confirmed.append(e in oracle[sid]); status['SEMANTIC_CONFIRMED']+=1
     elif pred is not None: status['SEMANTIC_CONFLICT']+=1
     elif g['agreement']=='UNCERTAIN': status['SEMANTIC_UNRESOLVED']+=1
     else: status['SEMANTIC_ABSTAIN']+=1
   result[f'{condition}/{variant}']={'baseline_total':len(baseline),'baseline_correct':sum(baseline),'baseline_precision':sum(baseline)/len(baseline),'confirmed':len(confirmed),'confirmed_correct':sum(confirmed),'confirmed_precision':sum(confirmed)/len(confirmed) if confirmed else None,'retention':len(confirmed)/len(baseline),'statuses':dict(status)}
 res={'task':c['task'],'status':'PASS_DEVELOPMENT_ONLY','retrospective_oracle_metric':True,'results':result,'groups_sha256':sha(out),'raw_sha256':freeze_audit['raw_sha256'],'oracle_scope':'P1V4SD000-P1V4SD029 only','semantic_api_calls':360,'holdout_access':0,'closure':0}
 write(ROOT/c['outputs']['results'],res); audit={'task':c['task'],'status':'PASS','response_freeze_sha256':sha(ROOT/c['outputs']['response_freeze']),'results_sha256':sha(ROOT/c['outputs']['results']),'groups_sha256':sha(out),'oracle_scenes':30,'holdout_access':0,'closure':0,'parent_mutation':0}; write(ROOT/c['outputs']['audit'],audit); (ROOT/c['outputs']['report']).write_text('# P1V4 compelled-direction semantic audit\n\n'+json.dumps(res,indent=2),encoding='utf-8'); print(json.dumps({'results':result,'audit':audit},indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('--freeze',action='store_true'); p.add_argument('--authorize',action='store_true'); p.add_argument('--dry-run',action='store_true'); p.add_argument('--execute',action='store_true'); p.add_argument('--score',action='store_true'); a=p.parse_args()
 if a.freeze: freeze()
 elif a.authorize: authorize()
 elif a.dry_run: execute(False)
 elif a.execute: execute(True)
 elif a.score: score()
 else: p.error('select one action')
