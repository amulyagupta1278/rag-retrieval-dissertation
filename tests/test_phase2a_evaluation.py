from scripts.run_phase2a_bm25_faiss import query_metrics
from scripts.correct_phase2a_validity import BOOT, SEED, bootstrap

def test_balanced_metrics_hand_computed():
 m=query_metrics(['x','a','b'],{'a':2,'b':2})
 assert m['mrr_at_5']==.5 and m['recall_at_5']==1 and m['precision_at_5']==.4
 assert m['complete_evidence_recall_at_5']==1 and 0<m['graded_ndcg_at_10']<1

def test_cutoff_and_missing_evidence():
 m=query_metrics(['x']*9+['a'],{'a':2,'b':2})
 assert m['mrr_at_5']==0 and m['mrr_at_10']==.1 and m['recall_at_10']==.5
 assert m['complete_evidence_recall_at_10']==0

def test_frozen_bootstrap_protocol_and_determinism():
 rows=[{'metrics':{'mrr_at_10':x}} for x in (0.0,0.5,1.0)]
 assert (BOOT,SEED)==(10000,42)
 assert bootstrap(rows,list(reversed(rows)),'mrr_at_10')==bootstrap(rows,list(reversed(rows)),'mrr_at_10')

def test_correct_slices_and_non_exhaustive_labels():
 import json
 from pathlib import Path
 root=Path(__file__).parents[1]
 h1=json.loads((root/'runs/v2/phase2a_v2/statistics/h1_exact_terminology.json').read_text())
 h2=json.loads((root/'runs/v2/phase2a_v2/statistics/h2_paraphrase_only.json').read_text())
 labels=json.loads((root/'runs/v2/phase2a_v2/metric_labels.json').read_text())
 assert h1['query_n']==12 and h1['scope']=='exact_lookup + terminology only'
 assert all(v['query_n']==6 for k,v in h2.items() if isinstance(v,dict))
 assert 'non-exhaustive' in labels['notice'] and labels['precision_at_5'].startswith('judged-gold')

def test_blind_pool_and_latency_protocol():
 import json
 from pathlib import Path
 root=Path(__file__).parents[1]
 pool=[json.loads(x) for x in (root/'runs/v2/phase2a_v2/pool/blind_top10_candidates.jsonl').read_text().splitlines()]
 assert not ({'system','rank','score','current_gold'} & set(pool[0]))
 sealed=[json.loads(x) for x in (root/'runs/v2/phase2a_v2/pool/sealed_provenance.jsonl').read_text().splitlines()]
 assert 'contributing_systems' in sealed[0] and 'current_gold' in sealed[0]
 latency=json.loads((root/'runs/v2/phase2a_v2/latency/protocol_and_summary.json').read_text())
 assert latency['warmup_queries_per_system']==5 and latency['timed_repetitions_per_query']>=20
 assert latency['samples_per_system']==34*20

def test_truncation_counts_and_answer_positions():
 import json
 from pathlib import Path
 audit=json.loads((Path(__file__).parents[1]/'audits/phase2a/faiss_truncation_audit.json').read_text())
 assert audit['summary']['chunks_total']==len(audit['chunks'])==140
 assert audit['summary']['chunks_truncated']==sum(x['truncated_token_count']>0 for x in audit['chunks'])
 assert all(x['answer_start_token']>=0 and x['answer_end_token']>=x['answer_start_token'] for x in audit['gold_answer_positions'])

def test_r3_r4_immutability_scope():
 import json
 from pathlib import Path
 root=Path(__file__).parents[1]/'data/v2/pilot/qa'
 r3={x['question_id']:x for x in map(json.loads,(root/'pilot-qa-v2-owner-approved-20260724-r3.jsonl').read_text().splitlines())}
 r4={x['question_id']:x for x in map(json.loads,(root/'pilot-qa-v2-ai-reviewed-20260724-r4-candidate.jsonl').read_text().splitlines())}
 changed={'v2q-013','v2q-014','v2q-015','v2q-017','v2q-018'}
 for qid in r3:
  assert (r3[qid]['question']!=r4[qid]['question'])==(qid in changed)
  for field in ('reference_answer','category','gold_evidence_ids','source_document_ids'):
   assert r3[qid][field]==r4[qid][field]
