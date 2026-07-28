import json
from pathlib import Path

def test_r3_diff_only_authorized_fields():
 root=Path(__file__).parents[1]; base=root/'data/v2/pilot'
 r2=[json.loads(x) for x in (base/'qa/pilot-qa-v2-reviewed-20260724-r2.jsonl').read_text().splitlines()]
 r3=[json.loads(x) for x in (base/'qa/pilot-qa-v2-owner-approved-20260724-r3.jsonl').read_text().splitlines()]
 allowed={'benchmark_version','review_status','owner_approval_status','owner_approval_timestamp'}
 assert len(r2)==len(r3)==34
 for a,b in zip(r2,r3): assert {k for k in set(a)|set(b) if a.get(k)!=b.get(k)}==allowed
 q2=[json.loads(x) for x in (base/'qrels/pilot-qa-v2-reviewed-20260724-r2.jsonl').read_text().splitlines()]
 q3=[json.loads(x) for x in (base/'qrels/pilot-qa-v2-owner-approved-20260724-r3.jsonl').read_text().splitlines()]
 assert len(q2)==len(q3)==48
 for a,b in zip(q2,q3): assert {k for k in set(a)|set(b) if a.get(k)!=b.get(k)}==allowed
