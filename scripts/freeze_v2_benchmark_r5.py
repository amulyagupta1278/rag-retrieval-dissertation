#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.utils.atomic_io import write_json,write_jsonl
from src.utils.hashing import sha256_file
OLD='pilot-qa-v2-owner-approved-20260724-r4'; CAND='pilot-qa-v2-ai-reviewed-20260724-r4-candidate'; R5='pilot-qa-v2-owner-approved-20260724-r5'
def main():
 p=argparse.ArgumentParser(); p.add_argument('--pilot-root',type=Path,required=True); p.add_argument('--audit',type=Path,required=True); p.add_argument('--overwrite',action='store_true'); a=p.parse_args(); root=a.pilot_root.resolve(); audit=a.audit.resolve()
 oldq=root/'qa'/f'{OLD}.jsonl'; oldr=root/'qrels'/f'{OLD}.jsonl'; qa=[json.loads(x) for x in oldq.read_text().splitlines()]; qr=[json.loads(x) for x in oldr.read_text().splitlines()]
 for x in qa: x.update(benchmark_version=CAND,review_status='ai_reviewed_owner_pending',owner_approval_status='pending_owner_review',owner_approval_timestamp=None)
 for x in qr: x.update(benchmark_version=CAND,review_status='ai_reviewed_owner_pending',owner_approval_status='pending_owner_review',owner_approval_timestamp=None)
 cq=root/'qa'/f'{CAND}.jsonl'; cr=root/'qrels'/f'{CAND}.jsonl'; write_jsonl(cq,qa,key='question_id',overwrite=a.overwrite); write_jsonl(cr,qr,key='judgment_id',overwrite=a.overwrite)
 ts=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'); r5q=[]; r5r=[]
 for x in qa: y=dict(x); y.update(benchmark_version=R5,review_status='ai_assisted_owner_authorized',owner_approval_status='authorized_for_pilot_development',owner_approval_timestamp=ts); r5q.append(y)
 for x in qr: y=dict(x); y.update(benchmark_version=R5,review_status='ai_assisted_owner_authorized',owner_approval_status='authorized_for_pilot_development',owner_approval_timestamp=ts); r5r.append(y)
 qp=root/'qa'/f'{R5}.jsonl'; rp=root/'qrels'/f'{R5}.jsonl'; write_jsonl(qp,r5q,key='question_id',overwrite=a.overwrite); write_jsonl(rp,r5r,key='judgment_id',overwrite=a.overwrite)
 allowed={'benchmark_version','review_status','owner_approval_status','owner_approval_timestamp'}
 for before,after in zip(qa,r5q):
  if {k for k in set(before)|set(after) if before.get(k)!=after.get(k)}!=allowed: raise RuntimeError('R5 QA content drift')
 for before,after in zip(qr,r5r):
  if {k for k in set(before)|set(after) if before.get(k)!=after.get(k)}!=allowed: raise RuntimeError('R5 qrels drift')
 manifest={'benchmark_version':R5,'source_candidate':CAND,'status':'ai_assisted_owner_authorized_for_pilot_development','approval_timestamp':ts,'not_independently_human_annotated':True,'qrels_exhaustive':False,'final_dissertation_evidence':False,'qa_path':str(qp.relative_to(ROOT)),'qrels_path':str(rp.relative_to(ROOT)),'qa_sha256':sha256_file(qp),'qrels_sha256':sha256_file(rp)}
 write_json(audit/'r4_candidate_manifest.json',{'benchmark_version':CAND,'status':'ai_reviewed_owner_pending','qa_path':str(cq.relative_to(ROOT)),'qrels_path':str(cr.relative_to(ROOT)),'qa_sha256':sha256_file(cq),'qrels_sha256':sha256_file(cr)},overwrite=a.overwrite)
 write_json(audit/'r5_freeze_manifest.json',manifest,overwrite=a.overwrite); print(json.dumps(manifest,sort_keys=True))
if __name__=='__main__': main()
