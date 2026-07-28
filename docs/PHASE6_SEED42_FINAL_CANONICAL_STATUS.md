# Corrected Phase 6 Canonical Status

Status date: 2026-07-28

Scope: pilot/development evidence only

Phase 7 dependency gate: OPEN

Phase 7 generation execution: NOT AUTHORIZED

## Canonical human inputs

- Completed seed-42 second pass: 114 rows, SHA-256
  `e12c4c427ddf7b5ea58063c19e3063ddfcf223b2762ee2089e8434b26dc9bc00`.
- Final owner adjudication: 14 rows, SHA-256
  `9fd10b3267fbcd339c3ce65b2c5796a99b17672f69c32d4a39cbdc9055fa4aa7`.
- Both repository copies are byte-identical to owner-supplied originals.
- No AI-selected final grades.

## Agreement and labels

- Exact agreement: 100/114 = 87.7193%.
- Disagreements: 14; unresolved: 0; U: 0.
- Cohen's kappa: 0.7421.
- Quadratic-weighted kappa: 0.8841.
- Final labels: grade 0 = 572, grade 1 = 89, grade 2 = 94.
- Provenance: 641 first-pass unsampled, 100 seed-42 agreements, 14 owner
  adjudications.
- Final-label SHA-256:
  `ee5f4c6731117001ff92be01489e859b43ab14a6bda6bcfc8b0bce16ca94f77c`.
- Final-qrels SHA-256:
  `c167689e5f0a1e7412d17baab56c6789e1612bb08121255fc0c153fecd1e077f`.
- Corrected qrels differ from invalid seed-123 qrels on 11 pairs. Change report
  records IDs, old/new grades, provenance, and owner rationale where applicable.

## Retrieval results

Known-gold metrics and final-pooled metrics remain separate.

| System | Known MRR@10 | Final MRR@10 | Final Recall@10 | Final graded nDCG@10 | Final CE Recall@10 |
|---|---:|---:|---:|---:|---:|
| BM25 | 0.8480 | 0.9412 | 0.8008 | 0.8235 | 0.4118 |
| FAISS-windowed-max | 0.6578 | 0.8279 | 0.7001 | 0.6883 | 0.2941 |
| Graph v3.2 | 0.6422 | 0.6765 | 0.6103 | 0.6214 | 0.4118 |
| Hybrid RRF | 0.8824 | 0.9559 | **0.8449** | 0.8783 | 0.5000 |
| Prompt-RAG Claude | **0.9632** | **0.9779** | 0.8355 | **0.8907** | **0.5882** |

No composite score or universal-winner claim is made. Prompt-RAG candidate recall
ceiling from frozen BM25 top-50 is 0.9490 macro mean.

## Preregistered exploratory H1-H4

- H1: BM25 minus FAISS MRR@10 on exact lookup + terminology, N=12, effect
  0.0667, 95% bootstrap CI `[-0.0833, 0.2417]`. CI is not wholly inside
  ±0.05 or ±0.03. Verdict: inconclusive.
- H2: FAISS minus BM25 on paraphrase, N=6. Zero of 12 balanced-metric tests met
  positive-effect, positive-CI, and Holm-adjusted exact-randomization criteria.
  MRR@10 effect -0.4250, CI `[-0.7667, 0.0000]`, exact p=0.96875,
  Holm-adjusted p=1.0. Verdict: not supported.
- H3: Graph versus BM25 and FAISS, entity relation and multi-hop separately.
  Zero of 16 emphasized metric tests met all criteria. Verdict: not supported.
- H4: Hybrid aggregate MRR@10 passed only Graph comparison (effect 0.2794,
  CI `[0.1471, 0.4265]`, exact p=0.0004883, Holm p=0.015625). Hybrid did not
  pass BM25, FAISS, or Prompt-RAG comparisons. Verdict: not supported.
- H5: not evaluated; Phase 7 only.

All conclusions are exploratory pilot evidence. Directional family contains 32
frozen metric-specific tests, uses exact paired sign-randomization p-values, and
Holm correction. Effect intervals use 10,000 paired whole-query bootstraps, seed 42.

## Phase 7 boundary

Dependency manifest verifies completed human review, agreement, labels, qrels,
metrics, statistics, and all five ranking hashes. Dependency gate is open only for
Phase 7 generation/H5 preregistration. Provider, model, prompt, context depth,
evaluation rubric, cost controls, and owner execution approval remain unresolved.
No Phase 7 API or generation work occurred.
