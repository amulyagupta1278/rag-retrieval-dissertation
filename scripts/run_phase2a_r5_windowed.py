#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,platform,random,resource,statistics,sys,time,tracemalloc
from collections import defaultdict
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.utils.atomic_io import write_json,write_jsonl
from src.utils.hashing import sha256_file
from scripts.run_phase2a_bm25_faiss import MODEL,REVISION,METRICS,query_metrics,tokenize,percentile
from scripts.correct_phase2a_validity import bootstrap
WINDOW=254; OVERLAP=32; STEP=222; REPS=20; WARMUPS=5
def make_windows(text,tokenizer,chunk_id):
 encoded=tokenizer(text,add_special_tokens=False,return_offsets_mapping=True,truncation=False); ids=encoded['input_ids']; offsets=encoded['offset_mapping']; out=[]
 for i,start in enumerate(range(0,len(ids),STEP)):
  end=min(start+WINDOW,len(ids)); cs=offsets[start][0]; ce=offsets[end-1][1]; out.append({'window_id':f'{chunk_id}:w{i:03d}','chunk_id':chunk_id,'window_index':i,'start_token':start,'end_token':end,'start_char':cs,'end_char':ce,'token_count':end-start,'text':text[cs:ce]})
  if end==len(ids): break
 return out
def summarize(v): return {'n':len(v),'mean_ms':statistics.mean(v),'median_ms':statistics.median(v),'p95_ms':percentile(v,95),'stddev_ms':statistics.pstdev(v)}
def main():
 p=argparse.ArgumentParser(); p.add_argument('--chunks',type=Path,required=True); p.add_argument('--qa',type=Path,required=True); p.add_argument('--qrels',type=Path,required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--overwrite',action='store_true'); a=p.parse_args(); out=a.output.resolve()
 if out!=(ROOT/'runs/v2/phase2a_r5_windowed').resolve(): raise ValueError('invalid output')
 chunks=[json.loads(x) for x in a.chunks.read_text().splitlines()]; qa=sorted([json.loads(x) for x in a.qa.read_text().splitlines()],key=lambda x:x['question_id']); qr=[json.loads(x) for x in a.qrels.read_text().splitlines()]; ids=[x['chunk_id'] for x in chunks]
 gains=defaultdict(dict)
 for x in qr: gains[x['query_id']][x['chunk_id']]=x['relevance']
 import faiss
 from rank_bm25 import BM25Okapi
 from sentence_transformers import SentenceTransformer
 tracemalloc.start(); build={}
 t=time.perf_counter(); bt=[tokenize(x['text']) for x in chunks]; build['bm25_tokenization_seconds']=time.perf_counter()-t
 t=time.perf_counter(); bm=BM25Okapi(bt,k1=1.5,b=.75); build['bm25_index_construction_seconds']=time.perf_counter()-t
 t=time.perf_counter(); json.dumps({'ids':ids,'tokens':bt,'idf':bm.idf},sort_keys=True); build['bm25_serialization_seconds']=time.perf_counter()-t; build['bm25_total_seconds']=sum(build.values())
 t=time.perf_counter(); model=SentenceTransformer(MODEL,revision=REVISION,local_files_only=True); build['faiss_model_loading_seconds']=time.perf_counter()-t
 windows=[w for c in chunks for w in make_windows(c['text'],model.tokenizer,c['chunk_id'])]; write_jsonl(out/'indexes/faiss_windowed/segment_to_chunk.jsonl',[{k:v for k,v in w.items() if k!='text'} for w in windows],key='window_id',overwrite=a.overwrite)
 t=time.perf_counter(); emb=np.asarray(model.encode([x['text'] for x in windows],normalize_embeddings=True,show_progress_bar=False),dtype='float32'); build['faiss_window_encoding_seconds']=time.perf_counter()-t
 t=time.perf_counter(); index=faiss.IndexFlatIP(emb.shape[1]); index.add(emb); build['faiss_index_construction_seconds']=time.perf_counter()-t
 (out/'indexes/faiss_windowed').mkdir(parents=True,exist_ok=True); t=time.perf_counter(); faiss.write_index(index,str(out/'indexes/faiss_windowed/faiss.index')); build['faiss_serialization_seconds']=time.perf_counter()-t; build['faiss_total_seconds']=sum(v for k,v in build.items() if k.startswith('faiss_'))
 prov={'system':'FAISS-windowed-max','model':MODEL,'revision':REVISION,'content_tokens_per_window':WINDOW,'token_overlap':OVERLAP,'step':STEP,'normalized_window_embeddings':True,'index':'IndexFlatIP','similarity':'cosine','scoring':'exact all windows; chunk score=max window score','collapse':'unique chunks','tie_break':'score descending then chunk ID ascending','window_count':len(windows),'chunk_count':len(chunks)}; write_json(out/'indexes/faiss_windowed/provenance.json',prov,overwrite=a.overwrite)
 def bmrun(q):
  toks=tokenize(q); scores=bm.get_scores(toks); order=sorted(range(len(ids)),key=lambda i:(-float(scores[i]),ids[i]))[:50]; return [{'chunk_id':ids[i],'rank':r,'score':float(scores[i])} for r,i in enumerate(order,1)]
 def frun(q):
  qe=np.asarray(model.encode([q],normalize_embeddings=True,show_progress_bar=False),dtype='float32'); scores,idx=index.search(qe,len(windows)); best={}
  for wi,s in zip(idx[0],scores[0]):
   w=windows[int(wi)]; candidate=(float(s),w)
   if w['chunk_id'] not in best or candidate[0]>best[w['chunk_id']][0]: best[w['chunk_id']]=candidate
  ordered=sorted(best.items(),key=lambda x:(-x[1][0],x[0]))[:50]
  return [{'chunk_id':cid,'rank':r,'score':v[0],'winning_window_id':v[1]['window_id'],'winning_window_start_token':v[1]['start_token'],'winning_window_end_token':v[1]['end_token'],'winning_window_start_char':v[1]['start_char'],'winning_window_end_char':v[1]['end_char']} for r,(cid,v) in enumerate(ordered,1)]
 rankings={'bm25':[],'faiss_windowed_max':[]}
 for q in qa:
  rankings['bm25'].append({'query_id':q['question_id'],'category':q['category'],'ranking':bmrun(q['question'])}); rankings['faiss_windowed_max'].append({'query_id':q['question_id'],'category':q['category'],'ranking':frun(q['question'])})
 for s,v in rankings.items(): write_jsonl(out/f'rankings/{s}_top50.jsonl',v,key='query_id',overwrite=a.overwrite)
 evals={}
 for s,rows in rankings.items():
  evals[s]=[{'query_id':x['query_id'],'category':x['category'],'metrics':query_metrics([z['chunk_id'] for z in x['ranking']],gains[x['query_id']]),'gold_ids':sorted(gains[x['query_id']]),'top10':x['ranking'][:10]} for x in rows]; write_jsonl(out/f'traces/{s}_per_query.jsonl',evals[s],key='query_id',overwrite=a.overwrite)
 def panel(rows):
  cats=sorted({x['category'] for x in rows}); return {'query_n':len(rows),'aggregate':{m:statistics.mean(x['metrics'][m] for x in rows) for m in METRICS},'per_category':{c:{'query_n':len(v),'metrics':{m:statistics.mean(x['metrics'][m] for x in v) for m in METRICS}} for c in cats for v in [[x for x in rows if x['category']==c]]}}
 metrics={s:panel(v) for s,v in evals.items()}; write_json(out/'metrics/balanced_metrics.json',{'notice':'Metrics use non-exhaustive direct-support qrels. Unjudged relevant chunks may exist.','labels':'known-gold/ judged-gold/ incomplete-pool per metric_labels.json','systems':metrics},overwrite=a.overwrite)
 slices={'aggregate':(evals['bm25'],evals['faiss_windowed_max']),'h1_exact_terminology':([x for x in evals['bm25'] if x['category'] in {'exact_lookup','terminology'}],[x for x in evals['faiss_windowed_max'] if x['category'] in {'exact_lookup','terminology'}]),'h2_paraphrase':([x for x in evals['bm25'] if x['category']=='paraphrase'],[x for x in evals['faiss_windowed_max'] if x['category']=='paraphrase'])}
 stats={name:{m:bootstrap(left,right,m) for m in METRICS} for name,(left,right) in slices.items()}; h1=stats['h1_exact_terminology']['mrr_at_10']; h1['bm25_mrr_at_10']=statistics.mean(x['metrics']['mrr_at_10'] for x in slices['h1_exact_terminology'][0]); h1['faiss_windowed_max_mrr_at_10']=statistics.mean(x['metrics']['mrr_at_10'] for x in slices['h1_exact_terminology'][1]); h1['equivalent_margin_005']=h1['ci95'][0]>-.05 and h1['ci95'][1]<.05; h1['equivalent_margin_003']=h1['ci95'][0]>-.03 and h1['ci95'][1]<.03; stats['hypothesis_status']={'H1':'exploratory pilot','H2':'exploratory pilot using six approved R5 paraphrases','H3':'untested','H4':'untested','H5':'untested'}; write_json(out/'metrics/paired_bootstrap.json',stats,overwrite=a.overwrite)
 old=json.load(open(ROOT/'runs/v2/phase2a_v1/metrics/balanced_metrics.json'))['faiss']; oldtr=[json.loads(x) for x in (ROOT/'runs/v2/phase2a_v1/traces/faiss_per_query.jsonl').read_text().splitlines()]; rewritten={'v2q-013','v2q-014','v2q-015','v2q-017','v2q-018'}; old29=[x for x in oldtr if x['query_id'] not in rewritten]; new29=[x for x in evals['faiss_windowed_max'] if x['query_id'] not in rewritten]; unchanged={'query_n':29,'truncated':{m:statistics.mean(x['metrics'][m] for x in old29) for m in METRICS},'windowed':{m:statistics.mean(x['metrics'][m] for x in new29) for m in METRICS}}
 write_json(out/'metrics/truncated_vs_windowed_validity.json',{'interpretation':'implementation-validity comparison, not model-selection competition','same_model_revision':True,'full_run_warning':'Full runs use R3 versus R5 and cannot isolate implementation effect.','unchanged_29_query_comparison':unchanged,'truncated_faiss_r3':old,'windowed_faiss_r5':metrics['faiss_windowed_max'],'validity_change':'Windowed implementation covers every token window and removes silent first-window truncation.'},overwrite=a.overwrite)
 # controlled timings
 def timed_bm(q):
  t=time.perf_counter(); toks=tokenize(q); a=(time.perf_counter()-t)*1000; t=time.perf_counter(); sc=bm.get_scores(toks); b=(time.perf_counter()-t)*1000; t=time.perf_counter(); sorted(range(len(ids)),key=lambda i:(-float(sc[i]),ids[i]))[:50]; c=(time.perf_counter()-t)*1000; return {'tokenization_ms':a,'scoring_ms':b,'sorting_ms':c,'total_ms':a+b+c}
 def timed_f(q):
  t=time.perf_counter(); qe=np.asarray(model.encode([q],normalize_embeddings=True,show_progress_bar=False),dtype='float32'); a=(time.perf_counter()-t)*1000; t=time.perf_counter(); scores,idx=index.search(qe,len(windows)); best={};
  for wi,s in zip(idx[0],scores[0]):
   cid=windows[int(wi)]['chunk_id']; best[cid]=max(best.get(cid,-2),float(s))
  sorted(best.items(),key=lambda x:(-x[1],x[0]))[:50]; b=(time.perf_counter()-t)*1000; return {'encoding_ms':a,'search_collapse_sort_ms':b,'total_ms':a+b}
 for q in qa[:WARMUPS]: timed_bm(q['question']); timed_f(q['question'])
 samples=[]
 for rep in range(REPS):
  for q in qa: samples.append({'sample_id':f"bm25:{rep}:{q['question_id']}",'system':'bm25','query_id':q['question_id'],'repetition':rep,**timed_bm(q['question'])})
  for q in qa: samples.append({'sample_id':f"faiss-windowed-max:{rep}:{q['question_id']}",'system':'faiss-windowed-max','query_id':q['question_id'],'repetition':rep,**timed_f(q['question'])})
 write_jsonl(out/'latency/raw_samples.jsonl',samples,key='sample_id',overwrite=a.overwrite); timing={}
 for s in ('bm25','faiss-windowed-max'):
  rows=[x for x in samples if x['system']==s]; keys=[k for k in rows[0] if k.endswith('_ms')]; timing[s]={k:summarize([x[k] for x in rows]) for k in keys}
 rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss; memory={'python_tracemalloc_peak_bytes':tracemalloc.get_traced_memory()[1],'process_peak_rss_bytes':int(rss*(1024 if sys.platform!='darwin' else 1)),'scope_warning':'not directly comparable; native FAISS may escape tracemalloc'}; tracemalloc.stop(); write_json(out/'latency/protocol_summary.json',{'warmups':WARMUPS,'repetitions_per_query':REPS,'samples_per_system':REPS*len(qa),'same_query_order':True,'order':'question_id ascending','batch_size':1,'cache_policy':'warm model/index; no cache flush','threads':{'faiss':faiss.omp_get_max_threads(),'OMP_NUM_THREADS':os.getenv('OMP_NUM_THREADS')},'platform':platform.platform(),'build_decomposition':build,'timing':timing,'memory':memory},overwrite=a.overwrite)
 # provisional blind pool
 rng=random.Random(42); reviewer=[]; sealed=[]
 for q in qa:
  pool={x['chunk_id'] for s in rankings for row in rankings[s] if row['query_id']==q['question_id'] for x in row['ranking'][:10]}|set(q['gold_evidence_ids']); order=sorted(pool); rng.shuffle(order)
  for n,cid in enumerate(order,1):
   did=f"{q['question_id']}-candidate-{n:02d}"; reviewer.append({'display_id':did,'query_id':q['question_id'],'question':q['question'],'chunk_id':cid,'chunk_text':next(x['text'] for x in chunks if x['chunk_id']==cid),'relevance_judgment':'','reviewer_notes':''}); contrib=[]
   for s in rankings:
    hit=next((x for row in rankings[s] if row['query_id']==q['question_id'] for x in row['ranking'][:10] if x['chunk_id']==cid),None)
    if hit: contrib.append({'system':s,'rank':hit['rank'],'score':hit['score']})
   sealed.append({'display_id':did,'query_id':q['question_id'],'chunk_id':cid,'contributions':contrib,'current_gold':cid in q['gold_evidence_ids']})
 write_jsonl(out/'pool/provisional_blind_top10.jsonl',reviewer,key='display_id',overwrite=a.overwrite); write_jsonl(out/'pool/sealed_provenance.jsonl',sealed,key='display_id',overwrite=a.overwrite); write_json(out/'pool/design.json',{'seed':42,'count':len(reviewer),'status':'provisional; Graph candidates required before final judging','hidden':['system','rank','score','gold status']},overwrite=a.overwrite)
 files=[x for x in out.rglob('*') if x.is_file() and x.name!='hashes.json']; write_json(out/'hashes.json',{str(x.relative_to(ROOT)):sha256_file(x) for x in sorted(files)},overwrite=a.overwrite); print(json.dumps({'metrics':metrics,'windows':len(windows),'pool':len(reviewer),'h1':h1},sort_keys=True))
if __name__=='__main__': main()
