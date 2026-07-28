import json
from pathlib import Path

ALLOWED={'benchmark_version','review_status','owner_approval_status','owner_approval_timestamp'}

def _rows(path):
 return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]

def test_r5_qa_and_qrels_only_approval_fields_change():
 root=Path(__file__).parents[1]/'data/v2/pilot'; c=[json.loads(x) for x in (root/'qa/pilot-qa-v2-ai-reviewed-20260724-r4-candidate.jsonl').read_text().splitlines()]; r=[json.loads(x) for x in (root/'qa/pilot-qa-v2-owner-approved-20260724-r5.jsonl').read_text().splitlines()]; allowed={'benchmark_version','review_status','owner_approval_status','owner_approval_timestamp'}
 assert len(c)==len(r)==34
 for a,b in zip(c,r): assert {k for k in set(a)|set(b) if a.get(k)!=b.get(k)}==allowed
 cq=_rows(root/'qrels/pilot-qa-v2-ai-reviewed-20260724-r4-candidate.jsonl'); rq=_rows(root/'qrels/pilot-qa-v2-owner-approved-20260724-r5.jsonl')
 assert len(cq)==len(rq)==48
 assert [x['judgment_id'] for x in cq]==[x['judgment_id'] for x in rq]
 for a,b in zip(cq,rq): assert {k for k in set(a)|set(b) if a.get(k)!=b.get(k)}==ALLOWED

def test_r5_exact_ids_counts_and_frozen_timestamp():
 root=Path(__file__).parents[1]/'data/v2/pilot'
 qa=_rows(root/'qa/pilot-qa-v2-owner-approved-20260724-r5.jsonl'); qr=_rows(root/'qrels/pilot-qa-v2-owner-approved-20260724-r5.jsonl')
 assert [x['question_id'] for x in qa]==[f'v2q-{i:03d}' for i in range(1,35)]
 assert len({x['judgment_id'] for x in qr})==48
 assert {x['owner_approval_timestamp'] for x in qa+qr}=={'2026-07-23T19:51:15.054027Z'}
 assert {(x['query_id'],x['chunk_id']) for x in qr}=={(q['question_id'],cid) for q in qa for cid in q['gold_evidence_ids']}
