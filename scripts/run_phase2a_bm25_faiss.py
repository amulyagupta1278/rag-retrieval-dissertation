#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,math,os,platform,statistics,sys,time,tracemalloc
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.utils.atomic_io import write_json,write_jsonl
from src.utils.hashing import sha256_file

MODEL='sentence-transformers/all-MiniLM-L6-v2'; REVISION='1110a243fdf4706b3f48f1d95db1a4f5529b4d41'
METRICS=('mrr_at_5','mrr_at_10','recall_at_5','recall_at_10','hit_rate_at_5','hit_rate_at_10','precision_at_5','precision_at_10','binary_ndcg_at_10','graded_ndcg_at_10','complete_evidence_recall_at_5','complete_evidence_recall_at_10')

def tokenize(s):
 import re
 return re.findall(r"\b\w+\b",s.casefold(),flags=re.UNICODE)

def query_metrics(ranked,gains):
 rel={x for x,v in gains.items() if v>0}
 def mrr(k): return next((1/i for i,x in enumerate(ranked[:k],1) if x in rel),0.0)
 def recall(k): return len(set(ranked[:k])&rel)/len(rel)
 def hit(k): return float(bool(set(ranked[:k])&rel))
 def precision(k): return sum(x in rel for x in ranked[:k])/k
 def ndcg(k,graded):
  vals=[(gains.get(x,0) if graded else int(x in rel)) for x in ranked[:k]]
  dcg=sum(v/math.log2(i+2) for i,v in enumerate(vals)); ideal=sorted((gains[x] if graded else 1 for x in rel),reverse=True)[:k]
  idcg=sum(v/math.log2(i+2) for i,v in enumerate(ideal)); return dcg/idcg if idcg else 0.0
 def complete(k): return float(rel.issubset(set(ranked[:k])))
 return {'mrr_at_5':mrr(5),'mrr_at_10':mrr(10),'recall_at_5':recall(5),'recall_at_10':recall(10),'hit_rate_at_5':hit(5),'hit_rate_at_10':hit(10),'precision_at_5':precision(5),'precision_at_10':precision(10),'binary_ndcg_at_10':ndcg(10,False),'graded_ndcg_at_10':ndcg(10,True),'complete_evidence_recall_at_5':complete(5),'complete_evidence_recall_at_10':complete(10)}

def aggregate(rows): return {m:sum(x['metrics'][m] for x in rows)/len(rows) for m in METRICS}
def percentile(values,p): return float(np.percentile(np.asarray(values,dtype=float),p))
def bootstrap(a,b,seed=20260724,n=2000):
 rng=np.random.default_rng(seed); out={}
 for m in METRICS:
  d=np.array([x['metrics'][m]-y['metrics'][m] for x,y in zip(a,b)],dtype=float); means=np.empty(n)
  for i in range(n): means[i]=d[rng.integers(0,len(d),len(d))].mean()
  out[m]={'effect_bm25_minus_faiss':float(d.mean()),'ci95':[percentile(means,2.5),percentile(means,97.5)],'method':'paired query bootstrap','replicates':n,'inference':'exploratory pilot'}
 return out

def bootstrap_panel(a,b):
 categories=sorted({x['category'] for x in a})
 return {'aggregate':bootstrap(a,b),'per_category':{c:{'query_n':sum(x['category']==c for x in a),'intervals':bootstrap([x for x in a if x['category']==c],[x for x in b if x['category']==c],seed=20260724+sum(map(ord,c)))} for c in categories}}

def main():
 p=argparse.ArgumentParser(); p.add_argument('--chunks',type=Path,required=True); p.add_argument('--qa',type=Path,required=True); p.add_argument('--qrels',type=Path,required=True); p.add_argument('--output-dir',type=Path,required=True); p.add_argument('--overwrite',action='store_true'); a=p.parse_args()
 a.chunks=a.chunks.resolve(); a.qa=a.qa.resolve(); a.qrels=a.qrels.resolve()
 out=a.output_dir.resolve()
 if out!=(ROOT/'runs/v2/phase2a').resolve(): raise ValueError('output-dir must be runs/v2/phase2a')
 chunks=[json.loads(x) for x in a.chunks.read_text().splitlines()]; qa=[json.loads(x) for x in a.qa.read_text().splitlines()]; qr=[json.loads(x) for x in a.qrels.read_text().splitlines()]
 if len(chunks)!=140 or len(qa)!=34: raise ValueError('frozen input counts differ')
 ids=[x['chunk_id'] for x in chunks]
 if len(ids)!=len(set(ids)): raise ValueError('duplicate chunks')
 qg=defaultdict(dict)
 for x in qr:
  if x['chunk_id'] not in set(ids): raise ValueError('unknown qrel chunk')
  qg[x['query_id']][x['chunk_id']]=x['relevance']
 if set(qg)!={x['question_id'] for x in qa}: raise ValueError('query/qrels mismatch')
 out.mkdir(parents=True,exist_ok=True)
 inputs={str(x.relative_to(ROOT)):sha256_file(x) for x in (a.chunks,a.qa,a.qrels)}
 tracemalloc.start(); peak={}; build={}; sizes={}; rankings={}; traces={}
 # BM25
 from rank_bm25 import BM25Okapi
 tokenized=[tokenize(x['text']) for x in chunks]; t=time.perf_counter(); bm=BM25Okapi(tokenized,k1=1.5,b=0.75); build['bm25_seconds']=time.perf_counter()-t
 bmprov={'system':'bm25','library':'rank_bm25','k1':1.5,'b':0.75,'tokenizer':'unicode_word_casefold_v1','tie_break':'score_desc_then_chunk_id_asc','chunk_ids':ids,'input_hashes':inputs}
 write_json(out/'indexes/bm25/provenance.json',bmprov,overwrite=a.overwrite); sizes['bm25_bytes']=(out/'indexes/bm25/provenance.json').stat().st_size
 write_json(out/'indexes/bm25/state.json',{'chunk_ids':ids,'tokenized_corpus':tokenized,'document_lengths':list(map(int,bm.doc_len)),'average_document_length':float(bm.avgdl),'idf':{k:float(v) for k,v in sorted(bm.idf.items())}},overwrite=a.overwrite)
 sizes['bm25_bytes']=sum(x.stat().st_size for x in (out/'indexes/bm25').iterdir())
 bmrows=[]; bmt=[]
 for q in qa:
  t=time.perf_counter(); scores=bm.get_scores(tokenize(q['question'])); order=sorted(range(len(chunks)),key=lambda i:(-float(scores[i]),ids[i]))[:50]; latency=(time.perf_counter()-t)*1000; bmt.append(latency)
  bmrows.append({'query_id':q['question_id'],'category':q['category'],'latency_ms':latency,'ranking':[{'chunk_id':ids[i],'rank':r,'score':float(scores[i])} for r,i in enumerate(order,1)]})
 rankings['bm25']=bmrows; peak['bm25_python_peak_bytes']=tracemalloc.get_traced_memory()[1]
 # FAISS cosine
 import faiss
 from sentence_transformers import SentenceTransformer
 t=time.perf_counter(); model=SentenceTransformer(MODEL,revision=REVISION,local_files_only=True); emb=np.asarray(model.encode([x['text'] for x in chunks],normalize_embeddings=True,show_progress_bar=False),dtype='float32'); index=faiss.IndexFlatIP(emb.shape[1]); index.add(emb); build['faiss_seconds']=time.perf_counter()-t
 (out/'indexes/faiss').mkdir(parents=True,exist_ok=True); faiss.write_index(index,str(out/'indexes/faiss/faiss.index'))
 write_json(out/'indexes/faiss/chunk_ids.json',ids,overwrite=a.overwrite)
 fprov={'system':'faiss','model':MODEL,'revision':REVISION,'normalize_embeddings':True,'index_type':'IndexFlatIP','similarity':'cosine','dimension':int(emb.shape[1]),'chunk_count':len(ids),'input_hashes':inputs}
 write_json(out/'indexes/faiss/provenance.json',fprov,overwrite=a.overwrite); sizes['faiss_bytes']=sum(x.stat().st_size for x in (out/'indexes/faiss').iterdir())
 frows=[]; ft=[]
 for q in qa:
  t=time.perf_counter(); qe=np.asarray(model.encode([q['question']],normalize_embeddings=True,show_progress_bar=False),dtype='float32'); scores,idx=index.search(qe,50); latency=(time.perf_counter()-t)*1000; ft.append(latency)
  pairs=sorted(zip(idx[0],scores[0]),key=lambda z:(-float(z[1]),ids[int(z[0])]))
  frows.append({'query_id':q['question_id'],'category':q['category'],'latency_ms':latency,'ranking':[{'chunk_id':ids[int(i)],'rank':r,'score':float(s)} for r,(i,s) in enumerate(pairs,1)]})
 rankings['faiss']=frows; peak['faiss_python_peak_bytes']=tracemalloc.get_traced_memory()[1]; tracemalloc.stop()
 for system,rows in rankings.items(): write_jsonl(out/f'rankings/{system}_top50.jsonl',rows,key='query_id',overwrite=a.overwrite)
 evaluated={}
 for system,rows in rankings.items():
  er=[]
  for row in rows:
   ranked=[x['chunk_id'] for x in row['ranking']]; er.append({'query_id':row['query_id'],'category':row['category'],'metrics':query_metrics(ranked,qg[row['query_id']]),'gold_ids':sorted(qg[row['query_id']]),'top10':row['ranking'][:10],'latency_ms':row['latency_ms']})
  evaluated[system]=er; write_jsonl(out/f'traces/{system}_per_query.jsonl',er,key='query_id',overwrite=a.overwrite)
 metrics={}
 for system,rows in evaluated.items():
  cats={c:[x for x in rows if x['category']==c] for c in sorted({x['category'] for x in rows})}
  metrics[system]={'aggregate':aggregate(rows),'query_n':len(rows),'per_category':{c:{'query_n':len(v),'metrics':aggregate(v)} for c,v in cats.items()}}
 lat={s:{'mean_ms':statistics.mean(v),'median_ms':statistics.median(v),'p95_ms':percentile(v,95)} for s,v in [('bm25',bmt),('faiss',ft)]}
 write_json(out/'metrics/balanced_metrics.json',metrics,overwrite=a.overwrite); write_json(out/'metrics/paired_bootstrap.json',bootstrap_panel(evaluated['bm25'],evaluated['faiss']),overwrite=a.overwrite)
 write_json(out/'efficiency.json',{'latency':lat,'build_time_seconds':build,'index_size_bytes':sizes,'peak_memory':peak,'peak_memory_method':'Python tracemalloc; native FAISS allocations may be excluded'},overwrite=a.overwrite)
 failures=[]
 for s,rows in evaluated.items():
  for x in rows:
   label='success' if x['metrics']['complete_evidence_recall_at_10']==1 else ('partial_multi_evidence' if x['metrics']['recall_at_10']>0 else 'no_gold_top10')
   failures.append({'failure_id':f"{s}:{x['query_id']}",'system':s,'query_id':x['query_id'],'category':x['category'],'taxonomy':label,'recall_at_10':x['metrics']['recall_at_10']})
 write_jsonl(out/'failure_taxonomy.jsonl',failures,key='failure_id',overwrite=a.overwrite)
 pool=[]
 for q in qa:
  union={x['chunk_id'] for s in rankings for row in rankings[s] if row['query_id']==q['question_id'] for x in row['ranking']}
  for cid in sorted(union): pool.append({'pool_id':f"{q['question_id']}:{cid}",'query_id':q['question_id'],'chunk_id':cid,'systems':[s for s in rankings if cid in {x['chunk_id'] for row in rankings[s] if row['query_id']==q['question_id'] for x in row['ranking']}],'judgment':'unjudged','relevance':None})
 write_jsonl(out/'pool/top50_union_unjudged.jsonl',pool,key='pool_id',overwrite=a.overwrite)
 manifest={'status':'exploratory_pilot_not_final_dissertation_evidence','systems':['bm25','faiss'],'query_count':34,'chunk_count':140,'top_k_saved':50,'inputs':inputs,'model':fprov,'qrels_exhaustive':False,'unjudged_policy':'Metrics credit only explicit positive qrels; absent judgments remain unjudged and are not factual nonrelevance claims.','outputs':{}}
 for pth in sorted(x for x in out.rglob('*') if x.is_file() and x.name not in {'manifest.json','hashes.json'}): manifest['outputs'][str(pth.relative_to(ROOT))]=sha256_file(pth)
 write_json(out/'manifest.json',manifest,overwrite=a.overwrite)
 write_json(out/'hashes.json',{'manifest_sha256':sha256_file(out/'manifest.json'),'files':manifest['outputs']},overwrite=a.overwrite)
 print(json.dumps({'metrics':metrics,'efficiency':{'latency':lat,'build':build,'sizes':sizes},'pool_rows':len(pool)},sort_keys=True))
if __name__=='__main__': main()
