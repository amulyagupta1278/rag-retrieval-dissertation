#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,platform,resource,statistics,sys,time,tracemalloc
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.utils.atomic_io import write_json,write_jsonl
from scripts.run_phase2a_bm25_faiss import MODEL,REVISION,tokenize,percentile
WARMUPS=5; REPETITIONS=20
def summary(v): return {'n':len(v),'mean_ms':statistics.mean(v),'median_ms':statistics.median(v),'p95_ms':percentile(v,95),'stddev_ms':statistics.pstdev(v)}
def main():
 p=argparse.ArgumentParser(); p.add_argument('--chunks',type=Path,required=True); p.add_argument('--qa',type=Path,required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--overwrite',action='store_true'); a=p.parse_args(); out=a.output.resolve()
 if out!=(ROOT/'runs/v2/phase2a_v2/latency').resolve(): raise ValueError('invalid output')
 chunks=[json.loads(x) for x in a.chunks.read_text().splitlines()]; qa=sorted([json.loads(x) for x in a.qa.read_text().splitlines()],key=lambda x:x['question_id']); ids=[x['chunk_id'] for x in chunks]
 import faiss
 from rank_bm25 import BM25Okapi
 from sentence_transformers import SentenceTransformer
 tracemalloc.start(); build={}
 t=time.perf_counter(); tokenized=[tokenize(x['text']) for x in chunks]; build['bm25_tokenization_seconds']=time.perf_counter()-t
 t=time.perf_counter(); bm=BM25Okapi(tokenized,k1=1.5,b=.75); build['bm25_index_construction_seconds']=time.perf_counter()-t
 t=time.perf_counter(); json.dumps({'ids':ids,'tokens':tokenized,'idf':bm.idf},sort_keys=True); build['bm25_serialization_seconds']=time.perf_counter()-t; build['bm25_total_seconds']=sum(build[k] for k in list(build))
 t=time.perf_counter(); model=SentenceTransformer(MODEL,revision=REVISION,local_files_only=True); build['faiss_model_loading_seconds']=time.perf_counter()-t
 t=time.perf_counter(); emb=np.asarray(model.encode([x['text'] for x in chunks],normalize_embeddings=True,show_progress_bar=False),dtype='float32'); build['faiss_document_encoding_seconds']=time.perf_counter()-t
 t=time.perf_counter(); index=faiss.IndexFlatIP(emb.shape[1]); index.add(emb); build['faiss_index_construction_seconds']=time.perf_counter()-t
 t=time.perf_counter(); faiss.serialize_index(index); build['faiss_serialization_seconds']=time.perf_counter()-t; build['faiss_total_seconds']=sum(build[k] for k in list(build) if k.startswith('faiss_') and k!='faiss_total_seconds')
 def bm_run(q):
  t=time.perf_counter(); toks=tokenize(q); a=(time.perf_counter()-t)*1000
  t=time.perf_counter(); scores=bm.get_scores(toks); b=(time.perf_counter()-t)*1000
  t=time.perf_counter(); sorted(range(len(chunks)),key=lambda i:(-float(scores[i]),ids[i]))[:50]; c=(time.perf_counter()-t)*1000
  return {'tokenization_ms':a,'scoring_ms':b,'sorting_ms':c,'total_ms':a+b+c}
 def faiss_run(q):
  t=time.perf_counter(); qe=np.asarray(model.encode([q],normalize_embeddings=True,show_progress_bar=False),dtype='float32'); a=(time.perf_counter()-t)*1000
  t=time.perf_counter(); index.search(qe,50); b=(time.perf_counter()-t)*1000
  return {'encoding_ms':a,'search_ms':b,'total_ms':a+b}
 for q in qa[:WARMUPS]: bm_run(q['question']); faiss_run(q['question'])
 rows=[]
 for rep in range(REPETITIONS):
  for q in qa:
   rows.append({'sample_id':f"bm25:{rep:02d}:{q['question_id']}",'system':'bm25','repetition':rep,'query_id':q['question_id'],**bm_run(q['question'])})
  for q in qa:
   rows.append({'sample_id':f"faiss:{rep:02d}:{q['question_id']}",'system':'faiss','repetition':rep,'query_id':q['question_id'],**faiss_run(q['question'])})
 py_peak=tracemalloc.get_traced_memory()[1]; tracemalloc.stop(); rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss; rss_bytes=int(rss*(1024 if sys.platform!='darwin' else 1))
 stages={}
 for system in ('bm25','faiss'):
  sr=[x for x in rows if x['system']==system]; keys=['tokenization_ms','scoring_ms','sorting_ms','total_ms'] if system=='bm25' else ['encoding_ms','search_ms','total_ms']; stages[system]={k:summary([x[k] for x in sr]) for k in keys}
 protocol={'warmup_queries_per_system':WARMUPS,'timed_repetitions_per_query':REPETITIONS,'query_count':len(qa),'samples_per_system':len(qa)*REPETITIONS,'query_order':'question_id ascending; identical for both systems','cache_policy':'warm model/index; no OS cache flush; five excluded warm-up queries','batch_size':1,'thread_count':{'faiss':faiss.omp_get_max_threads(),'OMP_NUM_THREADS':os.getenv('OMP_NUM_THREADS'),'MKL_NUM_THREADS':os.getenv('MKL_NUM_THREADS')},'cpu_platform':platform.platform(),'build_time_decomposition':build,'timing_summary':stages,'memory':{'python_tracemalloc_peak_bytes':py_peak,'process_peak_rss_bytes':rss_bytes,'warning':'tracemalloc is Python-only; process RSS includes wider process state; native FAISS allocations may escape Python tracing. Scopes are not directly comparable.'},'validity_notice':'Timing characterizes current truncated MiniLM implementation; model correction awaits owner approval.'}
 write_jsonl(out/'raw_samples.jsonl',rows,key='sample_id',overwrite=a.overwrite); write_json(out/'protocol_and_summary.json',protocol,overwrite=a.overwrite); print(json.dumps(protocol,sort_keys=True))
if __name__=='__main__': main()
