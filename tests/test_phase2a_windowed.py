from pathlib import Path

import pytest

from scripts.run_phase2a_r5_windowed import (
 CANONICAL_CHUNKS,CANONICAL_OUTPUT,CANONICAL_QA,CANONICAL_QRELS,
 WINDOW,OVERLAP,STEP,collapse_window_scores,make_windows,validate_frozen_inputs,
)
class Tok:
 def __call__(self,text,**kw):
  words=text.split(); offsets=[]; p=0
  for w in words: s=text.index(w,p); offsets.append((s,s+len(w))); p=s+len(w)
  return {'input_ids':list(range(len(words))),'offset_mapping':offsets}
def test_fixed_window_contract():
 w=make_windows(' '.join(f'w{i}' for i in range(600)),Tok(),'c')
 assert (WINDOW,OVERLAP,STEP)==(254,32,222)
 assert [(x['start_token'],x['end_token']) for x in w]==[(0,254),(222,476),(444,600)]

def test_equal_score_winning_window_uses_ascending_window_id():
 windows=[
  (0.75,{'chunk_id':'c','window_id':'c:w002'}),
  (0.75,{'chunk_id':'c','window_id':'c:w001'}),
  (0.50,{'chunk_id':'d','window_id':'d:w000'}),
 ]
 best=collapse_window_scores(windows)
 assert best['c'][2]['window_id']=='c:w001'

def test_r5_runner_enforces_exact_paths_hashes_counts_and_labels(tmp_path: Path):
 chunks,qa,qrels=validate_frozen_inputs(CANONICAL_CHUNKS,CANONICAL_QA,CANONICAL_QRELS,CANONICAL_OUTPUT)
 assert len(chunks)==140 and len(qa)==34 and len(qrels)==48
 with pytest.raises(ValueError,match='canonical paths'):
  validate_frozen_inputs(tmp_path/'chunks.jsonl',CANONICAL_QA,CANONICAL_QRELS,CANONICAL_OUTPUT)
