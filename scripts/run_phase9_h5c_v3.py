#!/usr/bin/env python3
"""Run H5c-v3 with frozen deterministic citation normalization."""
from __future__ import annotations
import copy,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'scripts'))
import run_phase9_h5c as runner
from src.generation.phase8_r4_v2_validation import validate_provider_response as base_validate
PATTERN=re.compile(r'\[((?:E\d{2})(?:\s*,\s*E\d{2})+)\]')
def normalize(text):
 def repl(m): return ''.join(f'[{x.strip()}]' for x in m.group(1).split(','))
 return PATTERN.sub(repl,text)
def validate(raw,*,available_evidence_ids):
 normalized=copy.deepcopy(raw); payload=json.loads(normalized['content'][0]['text']); payload['answer']=normalize(payload['answer']); normalized['content'][0]['text']=json.dumps(payload,ensure_ascii=False,separators=(',',':')); return base_validate(normalized,available_evidence_ids=available_evidence_ids)
runner.FR=ROOT/'runs/phase9_h5c_v3/freeze_final'; runner.OUT=ROOT/'runs/phase9_h5c_v3/generation'; runner.APPROVAL=ROOT/'audits/phase9_h5c_v3/cost_approval.json'; runner.validate_provider_response=validate
if __name__=='__main__': raise SystemExit(runner.main())
