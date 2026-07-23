import json
from pathlib import Path
def test_r5_only_approval_fields_change():
 root=Path(__file__).parents[1]/'data/v2/pilot'; c=[json.loads(x) for x in (root/'qa/pilot-qa-v2-ai-reviewed-20260724-r4-candidate.jsonl').read_text().splitlines()]; r=[json.loads(x) for x in (root/'qa/pilot-qa-v2-owner-approved-20260724-r5.jsonl').read_text().splitlines()]; allowed={'benchmark_version','review_status','owner_approval_status','owner_approval_timestamp'}
 assert len(c)==len(r)==34
 for a,b in zip(c,r): assert {k for k in set(a)|set(b) if a.get(k)!=b.get(k)}==allowed
