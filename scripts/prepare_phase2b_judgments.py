#!/usr/bin/env python3
"""Prepare leak-free owner relevance judgment package for Phase 2B."""
from __future__ import annotations
import argparse,csv,io,json,random,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.utils.atomic_io import _atomic_write,write_json
from src.utils.hashing import sha256_file
FORBIDDEN={'system','systems','rank','score','current_gold','gold','relevance','predicted_relevance','contributions','contributing_systems'}
def main():
 p=argparse.ArgumentParser(); p.add_argument('--pool',type=Path,required=True); p.add_argument('--sealed',type=Path,required=True); p.add_argument('--qa',type=Path,required=True); p.add_argument('--chunks',type=Path,required=True); p.add_argument('--documents',type=Path,required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--overwrite',action='store_true'); a=p.parse_args(); out=a.output.resolve()
 a.pool=a.pool.resolve(); a.sealed=a.sealed.resolve(); a.qa=a.qa.resolve(); a.chunks=a.chunks.resolve(); a.documents=a.documents.resolve()
 if out!=(ROOT/'audits/phase2b').resolve(): raise ValueError('output must be audits/phase2b')
 blind=[json.loads(x) for x in a.pool.read_text().splitlines()]; sealed=[json.loads(x) for x in a.sealed.read_text().splitlines()]; qa={x['question_id']:x for x in map(json.loads,a.qa.read_text().splitlines())}; chunks={x['chunk_id']:x for x in map(json.loads,a.chunks.read_text().splitlines())}; docs={x['document_id']:x for x in map(json.loads,a.documents.read_text().splitlines())}
 if len(blind)!=504 or len(sealed)!=504: raise ValueError('pool count mismatch')
 bmap={x['display_id']:x for x in blind}; smap={x['display_id']:x for x in sealed}
 if len(bmap)!=504 or set(bmap)!=set(smap): raise ValueError('display IDs duplicate or misaligned')
 leaks=[]
 for row in blind:
  keys=set(row)
  if keys&FORBIDDEN: leaks.append({'display_id':row['display_id'],'keys':sorted(keys&FORBIDDEN)})
  if row['query_id'] not in qa or row['chunk_id'] not in chunks: raise ValueError('unknown blind reference')
 for display,row in smap.items():
  if row['query_id']!=bmap[display]['query_id'] or row['chunk_id']!=bmap[display]['chunk_id']: raise ValueError('sealed mapping mismatch')
 if leaks: raise ValueError(f'blind leakage: {leaks[:3]}')
 fields=['display_id','query_id','question','reference_answer','chunk_id','source_document_title','candidate_chunk','owner_grade_2_1_0_U','owner_rationale']
 buf=io.StringIO(newline=''); writer=csv.DictWriter(buf,fieldnames=fields,lineterminator='\n'); writer.writeheader()
 for display in sorted(bmap):
  row=bmap[display]; chunk=chunks[row['chunk_id']]; writer.writerow({'display_id':display,'query_id':row['query_id'],'question':qa[row['query_id']]['question'],'reference_answer':qa[row['query_id']]['reference_answer'],'chunk_id':row['chunk_id'],'source_document_title':docs[chunk['document_id']]['title'],'candidate_chunk':row['chunk_text'],'owner_grade_2_1_0_U':'','owner_rationale':''})
 _atomic_write(out/'owner_judgments.csv',buf.getvalue(),overwrite=a.overwrite)
 rubric='''# Phase 2B Relevance Rubric

Grade each query/chunk pair without viewing system provenance.

- `2`: Directly supports reference answer.
- `1`: Useful context, but insufficient alone.
- `0`: Irrelevant or misleading.
- `U`: Unclear; requires adjudication.

Rules:

- Do not infer relevance from same document or scheme.
- Judge chunk text against question and reference answer.
- Ignore expected system performance.
- Add rationale for `U` and any difficult boundary decision.
- Leave no row blank before submission.

Current qrels are non-exhaustive direct-gold judgments. This package remains provisional until Graph candidates are added and judged.
'''
 _atomic_write(out/'relevance_rubric.md',rubric,overwrite=a.overwrite)
 rng=random.Random(42); selected=sorted(rng.sample(sorted(bmap),round(len(bmap)*.15)))
 write_json(out/'qc_rejudge_selection_sealed.json',{'seed':42,'population':504,'sample_size':len(selected),'percentage':100*len(selected)/504,'display_ids':selected,'status':'sealed until initial judgments complete'},overwrite=a.overwrite)
 config={'status':'frozen_before_pool_judgments','benchmark':'pilot-qa-v2-owner-approved-20260724-r5','seed':42,'metric_definitions':'frozen Phase 2A balanced panel','bm25':{'tokenizer':'unicode_word_casefold_v1','k1':1.5,'b':.75,'tie_break':'score descending then chunk ID ascending'},'faiss_windowed_max':{'model':'sentence-transformers/all-MiniLM-L6-v2','revision':'1110a243fdf4706b3f48f1d95db1a4f5529b4d41','window_content_tokens':254,'overlap_tokens':32,'normalized':True,'index':'IndexFlatIP','similarity':'cosine','chunk_pooling':'maximum window score','tie_break':'score descending then chunk ID ascending'},'no_post_judgment_tuning':True,'inputs':{str(x.relative_to(ROOT)):sha256_file(x) for x in (a.pool,a.sealed,a.qa,a.chunks,a.documents)}}
 write_json(out/'frozen_configuration.json',config,overwrite=a.overwrite)
 validation={'blind_rows':len(blind),'sealed_rows':len(sealed),'display_id_alignment':True,'forbidden_field_leaks':0,'unknown_query_references':0,'unknown_chunk_references':0,'reviewer_package_fields':fields,'hidden_from_reviewer':sorted(FORBIDDEN),'sealed_file_not_for_reviewer':str(a.sealed.relative_to(ROOT)),'qc_rejudge_sample_size':len(selected),'owner_judgments_completed':False}
 write_json(out/'blind_pool_validation.json',validation,overwrite=a.overwrite)
 paths=[out/'owner_judgments.csv',out/'relevance_rubric.md',out/'qc_rejudge_selection_sealed.json',out/'frozen_configuration.json',out/'blind_pool_validation.json']
 write_json(out/'hashes.json',{str(x.relative_to(ROOT)):sha256_file(x) for x in paths},overwrite=a.overwrite)
 print(json.dumps(validation,sort_keys=True))
if __name__=='__main__': main()
