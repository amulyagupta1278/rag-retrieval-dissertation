#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.utils.atomic_io import write_json, write_jsonl
from src.utils.hashing import sha256_file
R2="pilot-qa-v2-reviewed-20260724-r2"; R3="pilot-qa-v2-owner-approved-20260724-r3"

def main():
 p=argparse.ArgumentParser(); p.add_argument("--pilot-root",type=Path,required=True); p.add_argument("--audit-root",type=Path,required=True); p.add_argument("--overwrite",action="store_true"); a=p.parse_args()
 pilot=a.pilot_root.resolve(); audit=a.audit_root.resolve()
 if pilot!=(ROOT/'data/v2/pilot').resolve() or audit!=(ROOT/'audits/phase2a/r3_freeze').resolve(): raise ValueError('invalid paths')
 ts=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
 qa=[json.loads(x) for x in (pilot/'qa'/f'{R2}.jsonl').read_text().splitlines()]
 qr=[json.loads(x) for x in (pilot/'qrels'/f'{R2}.jsonl').read_text().splitlines()]
 for x in qa: x.update(benchmark_version=R3,review_status='ai_assisted_owner_authorized',owner_approval_status='authorized_for_pilot_development',owner_approval_timestamp=ts)
 for x in qr: x.update(benchmark_version=R3,review_status='ai_assisted_owner_authorized',owner_approval_status='authorized_for_pilot_development',owner_approval_timestamp=ts)
 qp=pilot/'qa'/f'{R3}.jsonl'; rp=pilot/'qrels'/f'{R3}.jsonl'
 write_jsonl(qp,qa,key='question_id',overwrite=a.overwrite); write_jsonl(rp,qr,key='judgment_id',overwrite=a.overwrite)
 manifest={'benchmark_version':R3,'immutable':True,'status':'ai_assisted_owner_authorized_for_pilot_development','approval_timestamp':ts,'not_independently_human_annotated':True,'qrels_exhaustive':False,'final_dissertation_evidence':False,'qa_path':str(qp.relative_to(ROOT)),'qrels_path':str(rp.relative_to(ROOT)),'qa_sha256':sha256_file(qp),'qrels_sha256':sha256_file(rp),'question_count':34,'qrels_count':48}
 write_json(audit/'freeze_manifest.json',manifest,overwrite=a.overwrite)
 write_json(audit/'hashes.json',{'qa':manifest['qa_sha256'],'qrels':manifest['qrels_sha256'],'manifest':sha256_file(audit/'freeze_manifest.json')},overwrite=a.overwrite)
 print(json.dumps(manifest,sort_keys=True))
if __name__=='__main__': main()
