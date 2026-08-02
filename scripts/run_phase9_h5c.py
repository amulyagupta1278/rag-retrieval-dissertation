#!/usr/bin/env python3
"""Run frozen H5c payloads once after explicit cost-cap approval."""
from __future__ import annotations
import copy, hashlib, json, sys, time
from pathlib import Path
import anthropic
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.generation.phase7_v2_freeze import SDK_VERSION, observed_cost_usd
from src.generation.phase8_r4_v2_validation import validate_provider_response
from src.utils.atomic_io import write_json
FR=ROOT/'runs/phase9_h5c/freeze'; OUT=ROOT/'runs/phase9_h5c/generation'; APPROVAL=ROOT/'audits/phase9_h5c/cost_approval.json'
def obj(p): return json.loads(p.read_text())
def rows(p): return [json.loads(x) for x in p.read_text().splitlines() if x]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 cfg=obj(FR/'execution_config.json'); ap=obj(APPROVAL)
 if ap.get('status')!='owner_approved' or ap.get('hard_cap_usd')!=cfg['generation_hard_cap_usd'] or ap.get('manifest_sha256')!=sha(FR/'manifest.json'): raise RuntimeError('explicit H5c cost approval missing or differs')
 manifest=obj(FR/'manifest.json')
 for group in ('inputs','artifacts'):
  for rel,h in manifest[group].items():
   if sha(ROOT/rel)!=h: raise RuntimeError(f'frozen hash differs: {rel}')
 if OUT.exists() and any(OUT.rglob('*')): raise RuntimeError('H5c output exists; refuse rerun')
 plans={x['blinded_request_id']:x for x in rows(FR/'request_plan.jsonl')}; payloads={x['blinded_request_id']:x for x in rows(FR/'request_payloads.jsonl')}
 env=dotenv_values(ROOT/'.env'); key=env.get('ANTHROPIC_API_KEY')
 if not key or anthropic.__version__!=SDK_VERSION: raise RuntimeError('credential or Anthropic SDK differs')
 client=anthropic.Anthropic(api_key=key,max_retries=0,timeout=120.0); ledger={'status':'ready','attempt_n':0,'completed':[],'input_tokens':0,'output_tokens':0,'observed_cost_usd':0.0,'retry_n':0}; write_json(OUT/'ledger.json',ledger,overwrite=False)
 ordered=sorted(plans)
 for blind in ordered:
  rem=[x for x in ordered if x not in ledger['completed']]; projected=observed_cost_usd(ledger['input_tokens'],ledger['output_tokens'])+cfg['ambiguous_dispatch_reserve_usd']+sum(plans[x]['planned_input_token_envelope'] for x in rem)/1e6+len(rem)*cfg['max_output_tokens']*5/1e6
  if projected>cfg['generation_hard_cap_usd']+1e-12: raise RuntimeError('projected cost exceeds frozen cap')
  ledger.update(status='attempt_counted_before_dispatch',attempt_n=ledger['attempt_n']+1,active=blind); write_json(OUT/'ledger.json',ledger,overwrite=True); started=time.perf_counter()
  try: raw=client.messages.create(**copy.deepcopy(payloads[blind]['request'])).model_dump(mode='json',by_alias=True,exclude_none=True)
  except Exception as exc: ledger.update(status='failed_ambiguous_dispatch',failure={'type':type(exc).__name__}); write_json(OUT/'ledger.json',ledger,overwrite=True); return 76
  write_json(OUT/'raw'/f'{blind}.json',raw,overwrite=False); valid=validate_provider_response(raw,available_evidence_ids=list(plans[blind]['evidence_id_to_chunk_id'])); write_json(OUT/'validated'/f'{blind}.json',{'blinded_request_id':blind,'latency_seconds':round(time.perf_counter()-started,6),**valid},overwrite=False)
  ledger['completed'].append(blind); ledger['input_tokens']+=valid['usage']['input_tokens']; ledger['output_tokens']+=valid['usage']['output_tokens']; ledger['observed_cost_usd']=round(observed_cost_usd(ledger['input_tokens'],ledger['output_tokens']),6); ledger.update(status='running',active=None); write_json(OUT/'ledger.json',ledger,overwrite=True)
 ledger['status']='complete'; write_json(OUT/'ledger.json',ledger,overwrite=True); print(json.dumps(ledger,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
