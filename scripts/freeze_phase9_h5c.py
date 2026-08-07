#!/usr/bin/env python3
"""Freeze controlled 60-response H5c panel; performs no provider calls."""
from __future__ import annotations
import hashlib, json, random, sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.generation.phase7_freeze import response_schema
from src.generation.phase7_v2_freeze import MODEL,TEMPERATURE,build_request,conservative_input_token_envelope,request_sha256
from src.utils.atomic_io import stable_json

BASE=ROOT/'runs/phase8_r4_improvements'; OUT=ROOT/'runs/phase9_h5c/freeze'
QA=BASE/'benchmark/qa_dev_test.jsonl'; CH=BASE/'corpus/chunks_section_aware_450w.jsonl'
RUN=BASE/'prompt_rag_r4_v2_full/prompt_rag_run.jsonl'; PROMPT=ROOT/'prompts/phase8_r4_answer_generation_v3.txt'
QIDS=['q_0001','q_0003','q_0013','q_0021','q_0024','q_0039','q_0043','q_0047','q_0083','q_0094','q_0064','q_0071']
CONDS=['complete_top3','best_only','truncated_best','distractor_heavy','irrelevant']; SEED=51025; MAXTOK=512
def load(p): return [json.loads(x) for x in p.read_text().splitlines() if x]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(stable_json(v)+'\n')
def cost(inp,n): return inp/1e6+n*MAXTOK*5/1e6
def serialize(question,use,texts):
 evidence=[]; mapping={}
 for i,cid in enumerate(use,1):
  eid=f'E{i:02d}'; mapping[eid]=cid; evidence.append({'evidence_id':eid,'text':texts[cid]})
 return json.dumps({'question':question,'evidence':evidence},ensure_ascii=False,sort_keys=True,separators=(',',':')),mapping
def main():
 if OUT.exists() and any(OUT.iterdir()): raise RuntimeError('H5c freeze exists; refuse overwrite')
 qa={x['question_id']:x for x in load(QA)}; chunks={x['chunk_id']:x for x in load(CH)}
 runs={x['query_id']:x for x in load(RUN)}; rng=random.Random(SEED); ids=sorted(chunks)
 plans=[]; payloads=[]; mapping=[]; prompt=PROMPT.read_text(); schema=response_schema()
 for qid in QIDS:
  top=[x['chunk_id'] for x in runs[qid]['results'][:3]]; forbidden={chunks[x]['doc_id'] for x in top}
  pool=[x for x in ids if chunks[x]['doc_id'] not in forbidden]
  dist=rng.sample(pool,4)
  for cond in CONDS:
   if cond=='complete_top3': use=top; texts={x:chunks[x]['text'] for x in use}
   elif cond=='best_only': use=top[:1]; texts={top[0]:chunks[top[0]]['text']}
   elif cond=='truncated_best':
    use=top[:1]; words=chunks[top[0]]['text'].split(); texts={top[0]:' '.join(words[:max(25,len(words)//4)])}
   elif cond=='distractor_heavy': use=[top[0],*dist[:2]]; texts={x:chunks[x]['text'] for x in use}
   else: use=dist[1:4]; texts={x:chunks[x]['text'] for x in use}
   serialized,e_map=serialize(qa[qid]['question'],use,texts)
   req=build_request(prompt=prompt,serialized_context=serialized,schema=schema); req['max_tokens']=MAXTOK
   logical=f'{qid}:{cond}'; blind='H5C'+hashlib.sha256(('h5c:'+logical).encode()).hexdigest()[:14]
   plan={'blinded_request_id':blind,'query_id':qid,'category':qa[qid]['category'],'condition':cond,'context_chunk_ids':use,'evidence_id_to_chunk_id':e_map,'planned_input_token_envelope':conservative_input_token_envelope(req),'request_sha256':request_sha256(req)}
   plans.append(plan); payloads.append({'blinded_request_id':blind,'request_sha256':plan['request_sha256'],'request':req})
   mapping.append({'blinded_request_id':blind,'query_id':qid,'category':qa[qid]['category'],'condition':cond})
 plans.sort(key=lambda x:x['blinded_request_id']); payloads.sort(key=lambda x:x['blinded_request_id']); mapping.sort(key=lambda x:x['blinded_request_id'])
 inp=sum(x['planned_input_token_envelope'] for x in plans); worst=cost(inp,len(plans)); reserve=cost(max(x['planned_input_token_envelope'] for x in plans),1); cap=round(worst+reserve,6)
 OUT.mkdir(parents=True); (OUT/'request_plan.jsonl').write_text(''.join(stable_json(x)+'\n' for x in plans)); (OUT/'request_payloads.jsonl').write_text(''.join(stable_json(x)+'\n' for x in payloads)); (OUT/'sealed_mapping.jsonl').write_text(''.join(stable_json(x)+'\n' for x in mapping)); dump(OUT/'response_schema.json',schema)
 cfg={'status':'frozen_pending_explicit_cost_approval','hypothesis':'H5c','question_n':12,'request_n':60,'condition_counts':dict(Counter(x['condition'] for x in plans)),'model':MODEL,'temperature':TEMPERATURE,'max_output_tokens':MAXTOK,'zero_retries':True,'seed':SEED,'input_token_envelope':inp,'generation_worst_case_usd':round(worst,6),'ambiguous_dispatch_reserve_usd':round(reserve,6),'generation_hard_cap_usd':cap}
 dump(OUT/'execution_config.json',cfg); inputs={str(p.relative_to(ROOT)):sha(p) for p in [QA,CH,RUN,PROMPT,ROOT/'docs/PHASE9_H5C_PREREGISTRATION.md']}; arts={str(p.relative_to(ROOT)):sha(p) for p in sorted(OUT.glob('*')) if p.name!='manifest.json'}; dump(OUT/'manifest.json',{'inputs':inputs,'artifacts':arts}); print(json.dumps(cfg,indent=2))
if __name__=='__main__': main()
