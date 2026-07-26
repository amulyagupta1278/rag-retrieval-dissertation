#!/usr/bin/env python3
"""Frozen deterministic entity/co-occurrence Graph retrieval pilot."""
from __future__ import annotations
import argparse,json,random,re,statistics,sys,time,unicodedata
from collections import defaultdict,deque
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.utils.atomic_io import write_json,write_jsonl
from src.utils.hashing import sha256_file
from scripts.run_phase2a_bm25_faiss import METRICS,query_metrics
ACRONYM=re.compile(r"\b[A-Z][A-Z0-9-]{1,}\b")
PHRASE=re.compile(r"\b[A-Z][A-Za-z&’'-]*(?:\s+(?:[A-Z][A-Za-z&’'-]*|of|and|the)){1,5}\b")
def canon(s): return ' '.join(unicodedata.normalize('NFC',s).casefold().split())
def main():
 p=argparse.ArgumentParser(); p.add_argument('--config',type=Path,required=True); p.add_argument('--chunks',type=Path,required=True); p.add_argument('--documents',type=Path,required=True); p.add_argument('--qa',type=Path,required=True); p.add_argument('--qrels',type=Path,required=True); p.add_argument('--baseline-pool',type=Path,required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--audit',type=Path,required=True); p.add_argument('--overwrite',action='store_true'); a=p.parse_args(); out=a.output.resolve(); audit=a.audit.resolve()
 a.config=a.config.resolve(); a.chunks=a.chunks.resolve(); a.documents=a.documents.resolve(); a.qa=a.qa.resolve(); a.qrels=a.qrels.resolve(); a.baseline_pool=a.baseline_pool.resolve()
 if out!=(ROOT/'runs/v2/phase3_graph').resolve() or audit!=(ROOT/'audits/phase3').resolve(): raise ValueError('invalid output paths')
 config=json.loads(a.config.read_text()); chunks=[json.loads(x) for x in a.chunks.read_text().splitlines()]; docs=[json.loads(x) for x in a.documents.read_text().splitlines()]; qa=sorted([json.loads(x) for x in a.qa.read_text().splitlines()],key=lambda x:x['question_id']); qrels=[json.loads(x) for x in a.qrels.read_text().splitlines()]; cmap={x['chunk_id']:x for x in chunks}
 aliases=defaultdict(set); metadata=set()
 for d in docs:
  for value in (d['title'],d['ministry'],d['department']):
   if value: metadata.add(canon(value))
 for q in qa:
  gp=q.get('graph_path',{})
  for value in [gp.get('seed_entity'),gp.get('bridge_entity'),*(gp.get('target_entities') or [])]:
   if value: metadata.add(canon(value))
  seed=gp.get('seed_entity')
  if seed:
   for alias in gp.get('seed_aliases',[]): aliases[canon(alias)].add(canon(seed))
 entity_chunks=defaultdict(set); chunk_entities={}
 t=time.perf_counter()
 for c in chunks:
  text=c['text']; low=canon(text); entities={x for x in metadata if x and x in low}; entities|={canon(x) for x in ACRONYM.findall(text)}; entities|={canon(x) for x in PHRASE.findall(text)}
  for alias,targets in aliases.items():
   if alias in low: entities|=targets; entities.add(alias)
  entities.discard(''); chunk_entities[c['chunk_id']]=sorted(entities)
  for e in entities: entity_chunks[e].add(c['chunk_id'])
 co=defaultdict(set)
 for ents in chunk_entities.values():
  for e in ents: co[e].update(x for x in ents if x!=e)
 build=time.perf_counter()-t
 nodes=[{'entity_id':e,'chunk_ids':sorted(v)} for e,v in sorted(entity_chunks.items())]; edges=[]
 for e,v in sorted(entity_chunks.items()):
  for cid in sorted(v): edges.append({'edge_id':f'm:{e}:{cid}','source':e,'target':cid,'relation':'MENTIONED_IN'})
 for e,others in sorted(co.items()):
  for other in sorted(others):
   if e<other: edges.append({'edge_id':f'c:{e}:{other}','source':e,'target':other,'relation':'CO_OCCURS_WITH'})
 write_jsonl(out/'index/entities.jsonl',nodes,key='entity_id',overwrite=a.overwrite); write_jsonl(out/'index/edges.jsonl',edges,key='edge_id',overwrite=a.overwrite); write_json(out/'index/chunk_entities.json',chunk_entities,overwrite=a.overwrite)
 rows=[]; traces=[]
 for q in qa:
  qtext=canon(q['question']); seeds=sorted({e for e in entity_chunks if e in qtext}|{target for alias,targets in aliases.items() if alias in qtext for target in targets})
  scores=defaultdict(float); paths=defaultdict(list)
  for seed in seeds:
   for cid in entity_chunks.get(seed,[]): scores[cid]+=.5; paths[cid].append({'seed':seed,'distance':1,'via':None})
   for bridge in co.get(seed,[]):
    for cid in entity_chunks.get(bridge,[]): scores[cid]+=1/3; paths[cid].append({'seed':seed,'distance':2,'via':bridge})
  ranked=sorted(scores,key=lambda cid:(-scores[cid],cid))[:50]; ranking=[{'chunk_id':cid,'rank':i,'score':scores[cid]} for i,cid in enumerate(ranked,1)]
  rows.append({'query_id':q['question_id'],'category':q['category'],'ranking':ranking}); traces.append({'query_id':q['question_id'],'question':q['question'],'category':q['category'],'seed_entities':seeds,'ranking':[{**x,'paths':paths[x['chunk_id']]} for x in ranking]})
 write_jsonl(out/'rankings/graph_top50.jsonl',rows,key='query_id',overwrite=a.overwrite); write_jsonl(out/'rankings/graph_top10.jsonl',[{**x,'ranking':x['ranking'][:10]} for x in rows],key='query_id',overwrite=a.overwrite); write_jsonl(out/'traces/graph_traces.jsonl',traces,key='query_id',overwrite=a.overwrite)
 gains=defaultdict(dict)
 for x in qrels: gains[x['query_id']][x['chunk_id']]=x['relevance']
 evaluated=[]
 for row in rows: evaluated.append({'query_id':row['query_id'],'category':row['category'],'metrics':query_metrics([x['chunk_id'] for x in row['ranking']],gains[row['query_id']]),'gold_ids':sorted(gains[row['query_id']])})
 cats=sorted({x['category'] for x in evaluated}); metrics={'status':'exploratory_development_evidence_using_R5_direct_gold_qrels','notice':'Metrics use non-exhaustive direct-support qrels. Unjudged relevant chunks may exist.','query_n':34,'aggregate':{m:statistics.mean(x['metrics'][m] for x in evaluated) for m in METRICS},'per_category':{c:{'query_n':len(v),'metrics':{m:statistics.mean(x['metrics'][m] for x in v) for m in METRICS}} for c in cats for v in [[x for x in evaluated if x['category']==c]]}}
 write_json(out/'metrics/known_gold_metrics.json',metrics,overwrite=a.overwrite)
 # Unseen Graph top-10 expansion; current 504 package remains untouched.
 existing={(x['query_id'],x['chunk_id']) for x in map(json.loads,a.baseline_pool.read_text().splitlines())}; unseen=[]; sealed=[]; qmap={x['question_id']:x for x in qa}; rng=random.Random(42)
 for row in rows:
  candidates=[x for x in row['ranking'][:10] if (row['query_id'],x['chunk_id']) not in existing]; candidates.sort(key=lambda x:x['chunk_id']); rng.shuffle(candidates)
  for i,x in enumerate(candidates,1):
   display=f"{row['query_id']}-graph-new-{i:02d}"; unseen.append({'display_id':display,'query_id':row['query_id'],'question':qmap[row['query_id']]['question'],'reference_answer':qmap[row['query_id']]['reference_answer'],'chunk_id':x['chunk_id'],'chunk_text':cmap[x['chunk_id']]['text'],'relevance_judgment':'','reviewer_notes':''}); sealed.append({'display_id':display,'query_id':row['query_id'],'chunk_id':x['chunk_id'],'system':'graph','rank':x['rank'],'score':x['score']})
 write_jsonl(out/'pool/graph_unseen_blind.jsonl',unseen,key='display_id',overwrite=a.overwrite); write_jsonl(out/'pool/graph_unseen_sealed.jsonl',sealed,key='display_id',overwrite=a.overwrite); write_json(out/'pool/design.json',{'baseline_pairs_preserved':len(existing),'unseen_graph_pairs':len(unseen),'status':'sealed; do not judge until Hybrid expansion completes','final_pool_rule':'deduplicated union of top-10 from every compared system'},overwrite=a.overwrite)
 provenance={'config_path':str(a.config.relative_to(ROOT)),'config_sha256':sha256_file(a.config),'config':config,'input_hashes':{str(x.relative_to(ROOT)):sha256_file(x) for x in (a.chunks,a.documents,a.qa,a.qrels,a.baseline_pool)},'build_seconds':build,'entity_count':len(nodes),'edge_count':len(edges),'queries':34,'queries_without_seeds':sum(not x['seed_entities'] for x in traces),'status':'frozen exploratory development'}; write_json(out/'provenance.json',provenance,overwrite=a.overwrite)
 # Validate Phase2B package unchanged.
 phase2b=ROOT/'audits/phase2b/owner_judgments.csv'; preserved={'path':str(phase2b.relative_to(ROOT)),'sha256':sha256_file(phase2b),'owner_labels_present':any(x.get('owner_grade_2_1_0_U') for x in csv_rows(phase2b))}; write_json(audit/'phase2b_preservation.json',preserved,overwrite=a.overwrite)
 files=[x for x in out.rglob('*') if x.is_file() and x.name!='hashes.json']; write_json(out/'hashes.json',{str(x.relative_to(ROOT)):sha256_file(x) for x in sorted(files)},overwrite=a.overwrite); print(json.dumps({'entities':len(nodes),'edges':len(edges),'unseen_graph_pool':len(unseen),'metrics':metrics['aggregate']},sort_keys=True))
def csv_rows(path):
 import csv
 with path.open(newline='') as f: return list(csv.DictReader(f))
if __name__=='__main__': main()
