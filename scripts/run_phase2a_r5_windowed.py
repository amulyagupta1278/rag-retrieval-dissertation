#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,platform,random,resource,statistics,subprocess,sys,time,tracemalloc
from collections import defaultdict
from importlib import metadata
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.utils.atomic_io import write_json,write_jsonl
from src.utils.hashing import sha256_file
from scripts.run_phase2a_bm25_faiss import MODEL,REVISION,METRICS,query_metrics,tokenize,percentile
from scripts.correct_phase2a_validity import bootstrap
WINDOW=254; OVERLAP=32; STEP=222; REPS=20; WARMUPS=5
CANONICAL_CHUNKS=ROOT/'data/v2/pilot/chunks/chunks.jsonl'
CANONICAL_QA=ROOT/'data/v2/pilot/qa/pilot-qa-v2-owner-approved-20260724-r5.jsonl'
CANONICAL_QRELS=ROOT/'data/v2/pilot/qrels/pilot-qa-v2-owner-approved-20260724-r5.jsonl'
CANONICAL_OUTPUT=ROOT/'runs/v2/phase2a_r5_windowed'
FROZEN_HASHES={
 'chunks':'70c1e3b8b0380809adea000654333a5921132ab7608ff328a9fa7934e8f43aa6',
 'qa':'0abd328ff639a05e80559202a018df0bd50aaf875f8d6b7753af925cc8a89c4b',
 'qrels':'d335e034b517a4fe8810c8d09584991f2553dd985a3140524d99d20bcdc3faf4',
}
EXPECTED_QUERY_IDS=[f'v2q-{i:03d}' for i in range(1,35)]

def validate_frozen_inputs(chunks_path,qa_path,qrels_path,output_path):
 """Reject any path, byte, count, ID, label, or qrel drift before retrieval."""
 paths={'chunks':Path(chunks_path).resolve(),'qa':Path(qa_path).resolve(),'qrels':Path(qrels_path).resolve()}
 expected={'chunks':CANONICAL_CHUNKS.resolve(),'qa':CANONICAL_QA.resolve(),'qrels':CANONICAL_QRELS.resolve()}
 if paths!=expected: raise ValueError('Phase 2A R5 inputs must use exact canonical paths')
 if Path(output_path).resolve()!=CANONICAL_OUTPUT.resolve(): raise ValueError('invalid output')
 for name,path in paths.items():
  if sha256_file(path)!=FROZEN_HASHES[name]: raise ValueError(f'frozen {name} SHA-256 mismatch')
 chunks=[json.loads(x) for x in paths['chunks'].read_text().splitlines() if x.strip()]
 qa=[json.loads(x) for x in paths['qa'].read_text().splitlines() if x.strip()]
 qrels=[json.loads(x) for x in paths['qrels'].read_text().splitlines() if x.strip()]
 chunk_ids=[x.get('chunk_id') for x in chunks]; query_ids=[x.get('question_id') for x in qa]
 if len(chunk_ids)!=140 or len(set(chunk_ids))!=140: raise ValueError('frozen corpus requires 140 unique chunks')
 if query_ids!=EXPECTED_QUERY_IDS or len(set(query_ids))!=34: raise ValueError('R5 requires exact ordered v2q-001..034')
 if any(x.get('benchmark_version')!='pilot-qa-v2-owner-approved-20260724-r5' for x in qa+qrels): raise ValueError('R5 benchmark version mismatch')
 if any(x.get('review_status')!='ai_assisted_owner_authorized' or x.get('owner_approval_status')!='authorized_for_pilot_development' for x in qa+qrels): raise ValueError('R5 approval labels mismatch')
 pairs=[(x.get('query_id'),x.get('chunk_id')) for x in qrels]
 if len(qrels)!=48 or len(set(pairs))!=48 or any(x.get('relevance')!=2 for x in qrels): raise ValueError('R5 requires 48 unique grade-2 qrels')
 if any(q not in set(query_ids) or c not in set(chunk_ids) for q,c in pairs): raise ValueError('R5 qrel does not resolve')
 by_query=defaultdict(set)
 for q,c in pairs: by_query[q].add(c)
 for row in qa:
  if set(row.get('gold_evidence_ids',[]))!=by_query[row['question_id']]: raise ValueError('R5 QA gold IDs and qrels differ')
 return chunks,qa,qrels

def collapse_window_scores(scored_windows):
 """Select score-max window per chunk; equal scores use ascending window ID."""
 best={}
 for score,window in scored_windows:
  candidate=(float(score),str(window['window_id']),window)
  previous=best.get(window['chunk_id'])
  if previous is None or candidate[0]>previous[0] or (candidate[0]==previous[0] and candidate[1]<previous[1]):
   best[window['chunk_id']]=candidate
 return best
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
 chunks,qa,qr=validate_frozen_inputs(a.chunks,a.qa,a.qrels,a.output); qa=sorted(qa,key=lambda x:x['question_id']); ids=[x['chunk_id'] for x in chunks]
 start_git={'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=ROOT,text=True).strip(),'status_porcelain':subprocess.check_output(['git','status','--porcelain=v1','-uall'],cwd=ROOT,text=True).splitlines()}
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
  best=collapse_window_scores((float(s),windows[int(wi)]) for wi,s in zip(idx[0],scores[0]))
  ordered=sorted(best.items(),key=lambda x:(-x[1][0],x[0]))[:50]
  return [{'chunk_id':cid,'rank':r,'score':v[0],'winning_window_id':v[2]['window_id'],'winning_window_start_token':v[2]['start_token'],'winning_window_end_token':v[2]['end_token'],'winning_window_start_char':v[2]['start_char'],'winning_window_end_char':v[2]['end_char']} for r,(cid,v) in enumerate(ordered,1)]
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
 provenance={'command':[sys.executable,*sys.argv],'git':start_git,'python':{'version':sys.version,'platform':platform.platform()},'packages':{name:metadata.version(name) for name in ('faiss-cpu','numpy','rank-bm25','sentence-transformers')},'input_hashes':FROZEN_HASHES,'config':{'bm25_k1':1.5,'bm25_b':0.75,'faiss_model':MODEL,'faiss_revision':REVISION,'window':WINDOW,'overlap':OVERLAP,'pooling':'maximum score; equal-score winning window uses ascending window_id'},'counts':{'chunks':140,'queries':34,'qrels':48,'grade_2_qrels':48},'benchmark_version':'pilot-qa-v2-owner-approved-20260724-r5'}; write_json(out/'provenance.json',provenance,overwrite=a.overwrite)
 files=[x for x in out.rglob('*') if x.is_file() and x.name!='hashes.json']; write_json(out/'hashes.json',{str(x.relative_to(ROOT)):sha256_file(x) for x in sorted(files)},overwrite=a.overwrite); print(json.dumps({'metrics':metrics,'windows':len(windows),'pool':len(reviewer),'h1':h1},sort_keys=True))
if __name__=='__main__': main()
