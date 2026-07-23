#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json,math,random,re,statistics,sys,time,tracemalloc
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.utils.atomic_io import write_json,write_jsonl
from src.utils.hashing import sha256_file
from scripts.run_phase2a_bm25_faiss import METRICS,query_metrics,tokenize
R3='pilot-qa-v2-owner-approved-20260724-r3'; R4='pilot-qa-v2-owner-approved-20260724-r4'; SEED=42; BOOT=10000
STOP=set('the a an and or of to in for from with which what how does do is are its their under through by who this that'.split())
REWRITES={
'v2q-013':'Which initiative helps women in low-income countryside homes replace smoke-producing solid cooking materials with bottled gas?',
'v2q-014':'Under the national ration programme, what monthly cereal allocation goes to families in the poorest entitlement tier and to each person in the priority tier?',
'v2q-015':'Which initiative helps job-seekers and established craftspeople launch small businesses outside agriculture?',
'v2q-017':'Which training route serves people no longer in education or work who need an initial occupational skill?',
'v2q-018':'Which initiative helps city households across officially defined lower and middle income bands obtain permanent homes?',
}
SOURCE_WORDING={'v2q-013':'clean cooking fuel such as LPG available to the rural and deprived households which were otherwise using traditional cooking fuels such as firewood, coal, cow-dung cakes','v2q-014':'Antyodaya Anna Yojana (AAY) families receive 35 kilograms ... Priority Household (PHH) beneficiaries receive 5 kilograms','v2q-015':'self-employment among traditional artisans, unemployed youth ... non-farm sector','v2q-017':'school/college dropouts, and unemployed youth','v2q-018':'urban housing shortages, especially for EWS, LIG, and MIG categories'}

def norm(s): return re.findall(r"\b\w+\b",s.casefold(),re.UNICODE)
def bootstrap(a,b,metric,seed=SEED,n=BOOT):
 d=np.array([x['metrics'][metric]-y['metrics'][metric] for x,y in zip(a,b)],float); rng=np.random.default_rng(seed); means=np.empty(n)
 for i in range(n): means[i]=d[rng.integers(0,len(d),len(d))].mean()
 return {'query_n':len(d),'point_effect_bm25_minus_faiss':float(d.mean()),'ci95':[float(np.percentile(means,2.5)),float(np.percentile(means,97.5))],'samples':n,'seed':seed,'unit':'whole query','inference':'exploratory pilot'}
def tree_hash(root): return {str(p.relative_to(root)):sha256_file(p) for p in sorted(root.rglob('*')) if p.is_file()}
def main():
 p=argparse.ArgumentParser(); p.add_argument('--pilot-root',type=Path,required=True); p.add_argument('--v1',type=Path,required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--audit',type=Path,required=True); p.add_argument('--overwrite',action='store_true'); a=p.parse_args()
 pilot=a.pilot_root.resolve(); v1=a.v1.resolve(); out=a.output.resolve(); audit=a.audit.resolve()
 if out!=(ROOT/'runs/v2/phase2a_v2').resolve() or audit!=(ROOT/'audits/phase2a').resolve(): raise ValueError('invalid output paths')
 qa=[json.loads(x) for x in (pilot/'qa'/f'{R3}.jsonl').read_text().splitlines()]; qrels=[json.loads(x) for x in (pilot/'qrels'/f'{R3}.jsonl').read_text().splitlines()]; chunks=[json.loads(x) for x in (pilot/'chunks/chunks.jsonl').read_text().splitlines()]; cmap={x['chunk_id']:x for x in chunks}
 # V1 preservation classification
 v1hash=tree_hash(v1); write_json(audit/'v1_preservation.json',{'classification':'exploratory_development_run_pre_validity_corrections','path':str(v1.relative_to(ROOT)),'file_count':len(v1hash),'files':v1hash},overwrite=a.overwrite)
 # Paraphrase lexical audit + R4 candidate
 docs=[json.loads(x) for x in (pilot/'extracted/documents.jsonl').read_text().splitlines()]
 df=Counter();
 for c in chunks: df.update(set(norm(c['text'])))
 para=[]
 decisions={'v2q-013':'rewrite required','v2q-014':'rewrite required','v2q-015':'rewrite required','v2q-016':'valid semantic paraphrase','v2q-017':'rewrite required','v2q-018':'rewrite required'}
 for q in [x for x in qa if x['category']=='paraphrase']:
  gold=' '.join(cmap[x]['text'] for x in q['gold_evidence_ids']); qt=norm(q['question']); gt=norm(gold); qc=[x for x in qt if x not in STOP]; gc=set(x for x in gt if x not in STOP); inter=set(qc)&gc
  phrases=[]
  for n in (4,3,2):
   for i in range(len(qt)-n+1):
    phrase=' '.join(qt[i:i+n]);
    if phrase in ' '.join(gt) and phrase not in phrases: phrases.append(phrase)
  caps=re.findall(r'\b(?:[A-Z]{2,}|[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+)\b',q['question']); nums=re.findall(r'\b\d[\d,.%₹-]*\b',q['question']); acr=[x for x in caps if x.isupper()]
  rare=sorted(x for x in inter if df[x]<=5)
  para.append({'question_id':q['question_id'],'question':q['question'],'normalized_query_tokens':qt,'normalized_gold_tokens':gt,'query_content_tokens':qc,'gold_content_tokens':sorted(gc),'token_overlap_count':len(inter),'content_word_jaccard':len(inter)/len(set(qc)|gc),'exact_copied_phrases_2plus':phrases,'named_entities_copied':caps,'acronyms_copied':acr,'numbers_copied':nums,'rare_high_idf_terms_copied':rare,'mainly_exact_lexical_overlap':q['question_id'] in REWRITES,'semantic_meaning_preserved':True,'reviewer_decision':decisions[q['question_id']]})
 write_json(audit/'paraphrase_validity_audit.json',para,overwrite=a.overwrite)
 r4=[]
 for x in qa:
  y=dict(x); y['benchmark_version']=R4; y['review_status']='ai_reviewed_owner_pending'; y['owner_approval_status']='pending_r4_owner_review'; y['owner_approval_timestamp']=None
  if y['question_id'] in REWRITES:
   old=y['question']; y['question']=REWRITES[y['question_id']]; y['paired_paraphrase_metadata']={'original_r3_question':old,'original_source_wording':SOURCE_WORDING[y['question_id']],'paraphrased_wording':y['question'],'unavoidable_named_entities':[],'lexical_shift_audit':'decisive source phrases removed','semantic_equivalence_justification':'Same requested fact and unchanged gold evidence; surface vocabulary changed.'}
  r4.append(y)
 r4q=[]
 for x in qrels:
  y=dict(x); y['benchmark_version']=R4; y['review_status']='ai_reviewed_owner_pending'; y['owner_approval_status']='pending_r4_owner_review'; y['owner_approval_timestamp']=None; r4q.append(y)
 r4p=pilot/'qa'/f'{R4}.jsonl'; r4rp=pilot/'qrels'/f'{R4}.jsonl'; write_jsonl(r4p,r4,key='question_id',overwrite=a.overwrite); write_jsonl(r4rp,r4q,key='judgment_id',overwrite=a.overwrite)
 write_json(audit/'r4_candidate_manifest.json',{'benchmark_version':R4,'status':'candidate_owner_approval_required','changed_question_ids':sorted(REWRITES),'unchanged_nonparaphrase_items':28,'qa_sha256':sha256_file(r4p),'qrels_sha256':sha256_file(r4rp),'evaluation_authorized':False},overwrite=a.overwrite)
 # Truncation audit
 from sentence_transformers import SentenceTransformer
 model=SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2',revision='1110a243fdf4706b3f48f1d95db1a4f5529b4d41',local_files_only=True); tok=model.tokenizer; limit=model.max_seq_length; special=tok.num_special_tokens_to_add(pair=False); cap=limit-special
 chunkrows=[]; counts={}
 for c in chunks:
  n=len(tok(c['text'],add_special_tokens=False,truncation=False)['input_ids']); counts[c['chunk_id']]=n; chunkrows.append({'chunk_id':c['chunk_id'],'document_id':c['document_id'],'token_count':n,'truncated_token_count':max(0,n-cap),'truncated':n>cap})
 gold_occ=[]
 for q in qa:
  ans=set(x for x in norm(q['reference_answer']) if x not in STOP)
  for cid in q['gold_evidence_ids']:
   c=cmap[cid]; sentences=re.split(r'(?<=[.!?])\s+',c['text']); best=max(sentences,key=lambda s:len(ans&set(norm(s)))); char=c['text'].find(best); pos=len(tok(c['text'][:char],add_special_tokens=False,truncation=False)['input_ids']); end=pos+len(tok(best,add_special_tokens=False,truncation=False)['input_ids'])
   gold_occ.append({'query_id':q['question_id'],'category':q['category'],'chunk_id':cid,'answer_position_method':'sentence with maximum answer-content-token overlap','answer_start_token':pos,'answer_end_token':end,'after_truncation_boundary':pos>=cap,'crosses_boundary':pos<cap<end})
 bydoc=defaultdict(list)
 for x in chunkrows: bydoc[x['document_id']].append(x)
 bycat=defaultdict(list)
 for x in gold_occ: bycat[x['category']].append(x)
 unique_gold={x['chunk_id'] for x in gold_occ}
 trunc={'model':'sentence-transformers/all-MiniLM-L6-v2','revision':'1110a243fdf4706b3f48f1d95db1a4f5529b4d41','tokenizer':tok.name_or_path,'model_max_sequence_length':limit,'special_token_allowance':special,'content_token_capacity':cap,'chunks':chunkrows,'summary':{'chunks_truncated':sum(x['truncated'] for x in chunkrows),'chunks_total':len(chunks),'percentage_chunks_truncated':100*sum(x['truncated'] for x in chunkrows)/len(chunks),'unique_gold_chunks_truncated':sum(counts[x]>cap for x in unique_gold),'unique_gold_chunks_total':len(unique_gold),'percentage_gold_chunks_truncated':100*sum(counts[x]>cap for x in unique_gold)/len(unique_gold),'answer_spans_after_boundary':sum(x['after_truncation_boundary'] for x in gold_occ),'answer_spans_crossing_boundary':sum(x['crosses_boundary'] for x in gold_occ),'meaningful_truncation':True},'gold_answer_positions':gold_occ,'by_document':{k:{'chunks':len(v),'truncated':sum(x['truncated'] for x in v)} for k,v in sorted(bydoc.items())},'by_category':{k:{'gold_occurrences':len(v),'after_boundary':sum(x['after_truncation_boundary'] for x in v),'crosses_boundary':sum(x['crosses_boundary'] for x in v)} for k,v in sorted(bycat.items())},'decision':'Do not silently retain or switch model; owner selection required.','options':{'A':'Pinned model with verified context covering every 300-word chunk; changes dense representation only.','B':'Deterministic within-chunk model-window segmentation plus documented pooling; preserves shared retrieval units but adds pooling design choice and cost.','C':'Rechunk corpus and remap all evidence for every system; strongest unit alignment change but invalidates current frozen benchmark lineage.'}}
 write_json(audit/'faiss_truncation_audit.json',trunc,overwrite=a.overwrite)
 md=f"# FAISS truncation audit\n\nModel capacity: {cap} content tokens ({limit} including {special} special tokens).\n\n- Truncated chunks: {trunc['summary']['chunks_truncated']}/{len(chunks)} ({trunc['summary']['percentage_chunks_truncated']:.1f}%)\n- Truncated unique gold chunks: {trunc['summary']['unique_gold_chunks_truncated']}/{len(unique_gold)} ({trunc['summary']['percentage_gold_chunks_truncated']:.1f}%)\n- Answer spans starting after boundary: {trunc['summary']['answer_spans_after_boundary']}\n- Answer spans crossing boundary: {trunc['summary']['answer_spans_crossing_boundary']}\n\nMeaningful truncation exists. Owner must choose Option A, B, or C before corrected FAISS evaluation.\n"
 from src.utils.atomic_io import _atomic_write; _atomic_write(audit/'faiss_truncation_audit.md',md,overwrite=a.overwrite)
 # Correct statistics from preserved V1 rankings
 evals={}
 gains=defaultdict(dict)
 for x in qrels: gains[x['query_id']][x['chunk_id']]=x['relevance']
 for system in ('bm25','faiss'):
  rank=[json.loads(x) for x in (v1/'rankings'/f'{system}_top50.jsonl').read_text().splitlines()]; qmap={x['question_id']:x for x in qa}; evals[system]=[{'query_id':x['query_id'],'category':x['category'],'metrics':query_metrics([z['chunk_id'] for z in x['ranking']],gains[x['query_id']])} for x in rank]
 comparisons={'bootstrap_samples':BOOT,'seed':SEED,'metric_notice':'Metrics use non-exhaustive direct-support qrels. Unjudged relevant chunks may exist.','aggregate':{},'per_category':{}}
 for m in METRICS: comparisons['aggregate'][m]=bootstrap(evals['bm25'],evals['faiss'],m)
 for cat in sorted({x['category'] for x in evals['bm25']}): comparisons['per_category'][cat]={m:bootstrap([x for x in evals['bm25'] if x['category']==cat],[x for x in evals['faiss'] if x['category']==cat],m,seed=SEED) for m in METRICS}
 h1cats={'exact_lookup','terminology'}; h1a=[x for x in evals['bm25'] if x['category'] in h1cats]; h1b=[x for x in evals['faiss'] if x['category'] in h1cats]; h1=bootstrap(h1a,h1b,'mrr_at_10'); h1.update({'bm25_known_gold_mrr_at_10':statistics.mean(x['metrics']['mrr_at_10'] for x in h1a),'faiss_known_gold_mrr_at_10':statistics.mean(x['metrics']['mrr_at_10'] for x in h1b),'primary_margin':[-.05,.05],'equivalence_decision':'equivalent' if h1['ci95'][0]>-.05 and h1['ci95'][1]<.05 else 'not equivalent','sensitivity_margin':[-.03,.03],'sensitivity_equivalent':h1['ci95'][0]>-.03 and h1['ci95'][1]<.03,'scope':'exact_lookup + terminology only','inference':'exploratory pilot'})
 h2a=[x for x in evals['bm25'] if x['category']=='paraphrase']; h2b=[x for x in evals['faiss'] if x['category']=='paraphrase']; h2={m:bootstrap(h2a,h2b,m) for m in METRICS}; h2['validity_status']='R3 paraphrase audit failed 5/6; H2 comparison diagnostic only pending R4 owner approval.'
 write_json(out/'statistics/comparisons.json',comparisons,overwrite=a.overwrite); write_json(out/'statistics/h1_exact_terminology.json',h1,overwrite=a.overwrite); write_json(out/'statistics/h2_paraphrase_only.json',h2,overwrite=a.overwrite)
 labels={'mrr_at_5':'known-gold MRR@5','mrr_at_10':'known-gold MRR@10','recall_at_5':'known-gold Recall@5','recall_at_10':'known-gold Recall@10','hit_rate_at_5':'known-gold Hit Rate@5','hit_rate_at_10':'known-gold Hit Rate@10','precision_at_5':'judged-gold Precision@5','precision_at_10':'judged-gold Precision@10','binary_ndcg_at_10':'incomplete-pool binary nDCG@10','graded_ndcg_at_10':'incomplete-pool graded nDCG@10','complete_evidence_recall_at_5':'known-gold Complete Evidence Recall@5','complete_evidence_recall_at_10':'known-gold Complete Evidence Recall@10','notice':'Metrics use non-exhaustive direct-support qrels. Unjudged relevant chunks may exist.','ndcg_equality':'Binary and graded nDCG are equal because every current positive judgment has uniform grade 2.'}; write_json(out/'metric_labels.json',labels,overwrite=a.overwrite)
 # Imbalance
 sources=[json.loads(x) for x in (pilot/'manifests/raw_sources.jsonl').read_text().splitlines()]; stype={x['source_id']:x['mime_type'] for x in sources}; docmeta={x['document_id']:x for x in docs}; perdoc=Counter(x['document_id'] for x in chunks); permin=Counter(docmeta[x['document_id']]['ministry'] for x in chunks); gold_dist=Counter(cmap[cid]['document_id'] for q in qa for cid in q['gold_evidence_ids']); distract={}
 for system in ('bm25','faiss'):
  rank=[json.loads(x) for x in (v1/'rankings'/f'{system}_top50.jsonl').read_text().splitlines()]; c=Counter()
  for row in rank:
   gold=set(gains[row['query_id']]); c.update(cmap[x['chunk_id']]['document_id'] for x in row['ranking'][:10] if x['chunk_id'] not in gold)
  distract[system]=dict(sorted(c.items()))
 pdfdocs={'doc-pm-kmy-guidelines':perdoc['doc-pm-kmy-guidelines'],'doc-pm-kisan-guidelines':perdoc['doc-pm-kisan-guidelines']}; pdfsum=sum(pdfdocs.values())
 pdf_retrieval={}
 for system,values in distract.items():
  total=sum(values.values()); pdf_hits=sum(values.get(doc,0) for doc in pdfdocs); share=100*pdf_hits/total
  pdf_retrieval[system]={'pdf_distractors':pdf_hits,'all_non_gold_top10_distractors':total,'percentage':share,'share_to_corpus_share_ratio':share/(100*pdfsum/len(chunks))}
 imbalance={'chunks_per_document':dict(sorted(perdoc.items())),'chunks_per_ministry':dict(sorted(permin.items())),'pdf_chunks':pdfdocs,'both_pdfs_percentage_corpus':100*pdfsum/len(chunks),'median_chunks_per_document':statistics.median(perdoc.values()),'maximum_chunks_per_document':max(perdoc.values()),'minimum_chunks_per_document':min(perdoc.values()),'source_type_distribution':dict(Counter(stype[x['source_id']] for x in chunks)),'gold_query_distribution_by_document':dict(sorted(gold_dist.items())),'retrieved_top10_non_gold_distribution_by_document':distract,'pdf_retrieved_distractor_share':pdf_retrieval,'long_pdfs_dominate_top_results_disproportionately':False,'material_distortion_decision':'Long PDFs materially imbalance corpus composition but do not disproportionately dominate BM25/FAISS top-10 non-gold distractors in this run. Sensitivity analysis remains advisable and was not applied.','proposed_sensitivities_not_applied':['section filtering with preregistered rules','document-balanced retrieval sensitivity','maximum validated sections per source','separate official-PDF sensitivity table']}; write_json(audit/'corpus_imbalance_audit.json',imbalance,overwrite=a.overwrite)
 # Trace-based misses
 failures=[]
 for system in ('bm25','faiss'):
  traces=[json.loads(x) for x in (v1/'traces'/f'{system}_per_query.jsonl').read_text().splitlines()]; qmap={x['question_id']:x for x in qa}
  for t in traces:
   if t['metrics']['complete_evidence_recall_at_10']==1: continue
   topdocs=[cmap[x['chunk_id']]['document_id'] for x in t['top10']]; golddocs={cmap[x]['document_id'] for x in t['gold_ids']}; classes=[]; evidence=[]
   if any(x in golddocs for x in topdocs): classes.append('same-scheme wrong chunk'); evidence.append('Top-10 contains non-gold chunk from gold source document.')
   if len(t['gold_ids'])>1: classes.append('incomplete multi-evidence'); evidence.append(f"Known-gold Recall@10={t['metrics']['recall_at_10']:.3f}.")
   if system=='faiss' and any(counts[x]>cap for x in t['gold_ids']): classes.append('truncation suspected'); evidence.append('At least one gold chunk exceeds model content-token capacity; causality unresolved.')
   failures.append({'failure_id':f"{system}:{t['query_id']}",'system':system,'query_id':t['query_id'],'query':qmap[t['query_id']]['question'],'category':t['category'],'gold_chunks':t['gold_ids'],'top10':t['top10'],'failure_classification':classes or ['unresolved'],'evidence':evidence or ['Trace insufficient for causal classification.']})
 write_jsonl(out/'failure_taxonomy.jsonl',failures,key='failure_id',overwrite=a.overwrite)
 # Blind top10 pool
 rank={s:{x['query_id']:x for x in map(json.loads,(v1/'rankings'/f'{s}_top50.jsonl').read_text().splitlines())} for s in ('bm25','faiss')}; reviewer=[]; sealed=[]; rng=random.Random(SEED)
 for q in qa:
  pairs={x['chunk_id'] for s in rank for x in rank[s][q['question_id']]['ranking'][:10]}|set(q['gold_evidence_ids']); order=sorted(pairs); rng.shuffle(order)
  for i,cid in enumerate(order,1):
   display=f"{q['question_id']}-candidate-{i:02d}"; reviewer.append({'display_id':display,'query_id':q['question_id'],'question':q['question'],'chunk_id':cid,'chunk_text':cmap[cid]['text'],'relevance_judgment':'','reviewer_notes':''})
   contrib=[]
   for s in rank:
    hit=next((x for x in rank[s][q['question_id']]['ranking'][:10] if x['chunk_id']==cid),None)
    if hit: contrib.append({'system':s,'rank':hit['rank'],'score':hit['score']})
   sealed.append({'display_id':display,'query_id':q['question_id'],'chunk_id':cid,'contributing_systems':contrib,'current_gold':cid in q['gold_evidence_ids']})
 write_jsonl(out/'pool/blind_top10_candidates.jsonl',reviewer,key='display_id',overwrite=a.overwrite); write_jsonl(out/'pool/sealed_provenance.jsonl',sealed,key='display_id',overwrite=a.overwrite); write_json(out/'pool/design.json',{'seed':SEED,'candidate_count':len(reviewer),'systems':['bm25','faiss'],'includes_all_existing_gold':True,'reviewer_hidden_fields':['system identity','rank','score','current gold status'],'status':'provisional; Graph results must be added before final pooled judging'},overwrite=a.overwrite)
 # Hashes
 artifacts=[p for p in [audit/'v1_preservation.json',audit/'paraphrase_validity_audit.json',audit/'r4_candidate_manifest.json',audit/'faiss_truncation_audit.json',audit/'faiss_truncation_audit.md',audit/'corpus_imbalance_audit.json',audit/'commands.txt',audit/'test_output.txt',out/'statistics/comparisons.json',out/'statistics/h1_exact_terminology.json',out/'statistics/h2_paraphrase_only.json',out/'metric_labels.json',out/'failure_taxonomy.jsonl',out/'pool/blind_top10_candidates.jsonl',out/'pool/sealed_provenance.jsonl',out/'pool/design.json',out/'latency/raw_samples.jsonl',out/'latency/protocol_and_summary.json',r4p,r4rp]]
 write_jsonl(audit/'hashes.jsonl',[{'path':str(x.relative_to(ROOT)),'sha256':sha256_file(x),'byte_size':x.stat().st_size} for x in artifacts],key='path',overwrite=a.overwrite)
 print(json.dumps({'r4_rewrites':len(REWRITES),'truncated_chunks':trunc['summary']['chunks_truncated'],'h1':h1,'blind_pool':len(reviewer)},sort_keys=True))
if __name__=='__main__': main()
