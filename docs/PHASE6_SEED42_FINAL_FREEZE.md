# Phase 6 Seed-42 Final Freeze

Status: frozen pilot evidence, 2026-07-28. This additive correction supersedes the
seed-123/AI-graded run for use. Invalid historical artifacts remain preserved and
must not be cited as confirmatory evidence.

## Human judgment lineage

- Blind first pass: 755 owner-graded pooled query/chunk pairs.
- Protocol-conformant regrade: 114 pairs selected by blind simple random sampling,
  seed 42.
- Owner final adjudication: 14 disagreements, source SHA-256
  `9fd10b3267fbcd339c3ce65b2c5796a99b17672f69c32d4a39cbdc9055fa4aa7`.
- Agreement: 100/114 = 87.7193%; Cohen's kappa 0.7421; quadratic-weighted kappa
  0.8841.
- Final label distribution: grade 0 = 572, grade 1 = 89, grade 2 = 94.
- Label sources: 641 owner first-pass unsampled, 100 owner regrade agreements,
  14 owner adjudications.
- Five labels changed from first pass. No aggregate metric moved by 0.01 or more.

Final labels:
`data/v2/pilot/labels/phase6_final_human_labels_seed42.csv`

Final pooled qrels:
`data/v2/pilot/qrels/pilot-qa-v2-final-pooled-phase6-seed42-owner-adjudicated.tsv`

Qrels contain complete judgments for the frozen 755-pair, five-system top-10 union
pool. They are not exhaustive judgments over every query/chunk pair in the
140-chunk corpus.

## Metric definitions

- Relevance means qrel grade greater than zero.
- MRR@k uses reciprocal rank of first relevant result within top k; otherwise zero.
- Recall@k divides retrieved relevant chunks by all relevant pooled chunks.
- Precision@k divides relevant results in top k by k, including systems returning
  fewer than k results.
- Binary nDCG@10 maps every positive grade to gain 1.
- Graded nDCG@10 uses raw gains 0, 1, and 2.
- Complete Evidence Recall@k is 1 only when every positive pooled qrel is present in
  top k; otherwise 0.
- Query aggregation is unweighted macro mean. No composite score exists.

## Aggregate balanced results

| System | MRR@10 | Recall@10 | Hit@10 | Precision@10 | Binary nDCG@10 | Graded nDCG@10 | CE Recall@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| BM25 | 0.9412 | 0.8008 | 0.9706 | 0.4176 | 0.8012 | 0.8235 | 0.4118 |
| FAISS-windowed-max | 0.8279 | 0.7001 | 1.0000 | 0.3588 | 0.6673 | 0.6883 | 0.2941 |
| Graph v3.2 | 0.6765 | 0.6103 | 0.7059 | 0.2882 | 0.6185 | 0.6214 | 0.4118 |
| Hybrid RRF | 0.9559 | **0.8449** | 0.9706 | **0.4382** | 0.8651 | 0.8783 | 0.5000 |
| Prompt-RAG Claude | **0.9779** | 0.8355 | **1.0000** | 0.4324 | **0.8747** | **0.8907** | **0.5882** |

Full @5/@10 aggregate and six-category panels, query counts, paired uncertainty,
per-query traces, failure taxonomy, and efficiency provenance live under
`runs/v2/phase6_seed42_metrics/`.

## Hypothesis-aligned pilot results

- H1: BM25 minus FAISS MRR@10 on exact lookup + terminology = 0.0667; paired
  bootstrap 95% CI `[-0.0833, 0.2417]`. CI is not wholly inside either primary
  `[-0.05, 0.05]` or sensitivity `[-0.03, 0.03]` margin. Verdict: inconclusive.
- H2: zero of 12 paraphrase metric tests met positive-effect, positive-CI, and
  Holm-adjusted paired-randomization criteria. Pilot result does not support H2.
- H3: zero of eight tests met criteria for entity relation; zero of eight for
  multi-hop. Pilot result does not support H3.
- H4: Hybrid met rule against one of four comparators and had lower aggregate
  MRR@10 than Prompt-RAG. Pilot result does not support H4.
- H5: not evaluated. Generation remains separate.

Bootstrap and paired-randomization settings: 10,000 samples, seed 42. Holm
correction covers the 32 H2-H4 directional tests. Results remain pilot evidence;
they are not final holdout dissertation verdicts.

## Rebuild commands

```bash
python scripts/finalize_phase6_seed42.py \
  --first-pass runs/v2/phase6_blind_judging_package/owner_judging_package.csv \
  --sample runs/v2/phase6_regrade_package_seed42/regrade_package_seed42.csv \
  --sealed-provenance runs/v2/phase6_regrade_package_seed42/regrade_provenance_sealed_seed42.json \
  --sample-manifest runs/v2/phase6_regrade_package_seed42/regrade_manifest_seed42.json \
  --owner-adjudication outputs/019f9e9c-e14b-7b51-87af-e2cfca5b2a6e/phase6_adjudication_final/phase6_owner_adjudication_14_FINAL.csv \
  --owner-approval audits/phase6_seed42/owner_adjudication_approval.json \
  --labels-output data/v2/pilot/labels/phase6_final_human_labels_seed42.csv \
  --qrels-output data/v2/pilot/qrels/pilot-qa-v2-final-pooled-phase6-seed42-owner-adjudicated.tsv \
  --audit-dir audits/phase6_seed42/freeze \
  --owner-input-copy audits/phase6_seed42/inputs/phase6_owner_adjudication_14_FINAL.csv \
  --overwrite

python scripts/evaluate_phase6_seed42.py \
  --chunks data/v2/pilot/chunks/chunks.jsonl \
  --qa data/v2/pilot/qa/pilot-qa-v2-owner-approved-20260724-r5.jsonl \
  --qrels data/v2/pilot/qrels/pilot-qa-v2-final-pooled-phase6-seed42-owner-adjudicated.tsv \
  --first-pass-qrels data/v2/pilot/qrels/phase6_pooled_qrels.tsv \
  --bm25-ranking runs/v2/phase2a_r5_windowed/rankings/bm25_top50.jsonl \
  --faiss-ranking runs/v2/phase2a_r5_windowed/rankings/faiss_windowed_max_top50.jsonl \
  --graph-ranking runs/v2/phase3_graph_v3_2/rankings/graph_v3_2_top50.jsonl \
  --hybrid-ranking runs/v2/phase4_hybrid/rankings/hybrid_top50.jsonl \
  --prompt-ranking runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/complete_primary_rankings.jsonl \
  --phase2a-efficiency runs/v2/phase2a_r5_windowed/latency/protocol_summary.json \
  --graph-manifest runs/v2/phase3_graph_v3_2/evaluation_manifest.json \
  --hybrid-latency runs/v2/phase4_hybrid/latency/live_summary.json \
  --prompt-trace-operational runs/v2/phase5d_prompt_rag_claude_v2/trace/operational_summary.json \
  --prompt-full-operational runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/operational_summary.json \
  --bm25-index-dir runs/v2/phase2a/indexes/bm25 \
  --faiss-index-dir runs/v2/phase2a_r5_windowed/indexes/faiss_windowed \
  --output-dir runs/v2/phase6_seed42_metrics \
  --overwrite
```

No API call, retrieval run, answer generation, or new owner label assignment occurs
in either command. Both consume frozen artifacts only.
