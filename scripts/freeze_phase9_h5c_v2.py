#!/usr/bin/env python3
"""Freeze fresh H5c-v2 panel from v1 contexts with 1,024-token limit."""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.generation.phase7_v2_freeze import conservative_input_token_envelope, request_sha256
from src.utils.atomic_io import stable_json
SRC=ROOT/'runs/phase9_h5c/freeze'; OUT=ROOT/'runs/phase9_h5c_v2/freeze'; AMEND=ROOT/'docs/PHASE9_H5C_V2_RECOVERY_AMENDMENT.md'; CAP=.597256; MAXTOK=1024
def rows(p): return [json.loads(x) for x in p.read_text().splitlines() if x]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(stable_json(v)+'\n')
def main():
 if OUT.exists() and any(OUT.iterdir()): raise RuntimeError('H5c-v2 freeze exists; refuse overwrite')
 oldplans={x['blinded_request_id']:x for x in rows(SRC/'request_plan.jsonl')}; oldpayloads={x['blinded_request_id']:x for x in rows(SRC/'request_payloads.jsonl')}; oldmap={x['blinded_request_id']:x for x in rows(SRC/'sealed_mapping.jsonl')}
 plans=[]; payloads=[]; mapping=[]
 for old in sorted(oldplans):
  m=oldmap[old]; req=oldpayloads[old]['request']; req['max_tokens']=MAXTOK; logical=f"{m['query_id']}:{m['condition']}"; blind='H5C2'+hashlib.sha256(('h5c-v2:'+logical).encode()).hexdigest()[:13]
  plan={**oldplans[old],'blinded_request_id':blind,'planned_input_token_envelope':conservative_input_token_envelope(req),'request_sha256':request_sha256(req)}
  plans.append(plan); payloads.append({'blinded_request_id':blind,'request_sha256':plan['request_sha256'],'request':req}); mapping.append({**m,'blinded_request_id':blind})
 plans.sort(key=lambda x:x['blinded_request_id']); payloads.sort(key=lambda x:x['blinded_request_id']); mapping.sort(key=lambda x:x['blinded_request_id'])
 inp=sum(x['planned_input_token_envelope'] for x in plans); worst=inp/1e6+len(plans)*MAXTOK*5/1e6; maxinp=max(x['planned_input_token_envelope'] for x in plans); reserve=maxinp/1e6+MAXTOK*5/1e6; required=round(worst+reserve,6)
 if required>CAP: raise RuntimeError(f'required cap {required} exceeds approved {CAP}')
 OUT.mkdir(parents=True); (OUT/'request_plan.jsonl').write_text(''.join(stable_json(x)+'\n' for x in plans)); (OUT/'request_payloads.jsonl').write_text(''.join(stable_json(x)+'\n' for x in payloads)); (OUT/'sealed_mapping.jsonl').write_text(''.join(stable_json(x)+'\n' for x in mapping)); (OUT/'response_schema.json').write_bytes((SRC/'response_schema.json').read_bytes())
 cfg={'status':'frozen_owner_approved','hypothesis':'H5c-v2','authorization':'User approved Anthropic payload egress and corrected $0.597256 H5c-v2 cap.','question_n':12,'request_n':60,'model':'claude-haiku-4-5-20251001','temperature':0,'max_output_tokens':MAXTOK,'zero_retries':True,'seed':51025,'input_token_envelope':inp,'generation_worst_case_usd':round(worst,6),'ambiguous_dispatch_reserve_usd':round(reserve,6),'minimum_required_cap_usd':required,'generation_hard_cap_usd':CAP}
 dump(OUT/'execution_config.json',cfg); inputs={str(p.relative_to(ROOT)):sha(p) for p in [SRC/'manifest.json',SRC/'request_plan.jsonl',SRC/'request_payloads.jsonl',SRC/'sealed_mapping.jsonl',AMEND]}; arts={str(p.relative_to(ROOT)):sha(p) for p in sorted(OUT.glob('*')) if p.name!='manifest.json'}; dump(OUT/'manifest.json',{'inputs':inputs,'artifacts':arts}); print(json.dumps(cfg,indent=2))
if __name__=='__main__': main()
