# Phase 8 R4 Human-Validation Final Report

## Status

Owner validation is complete for all 260 review rows. R4 now provides human-owner-validated
exploratory scaling evidence. V2 pilot remains canonical confirmatory evidential base because R4
design and statistical comparisons were not preregistered.

## Frozen owner inputs

- Gold-mapping review: 140/140 complete; decisions `valid=140`; grades `2=139`, `0=1`.
- Generation review: 100/100 complete across six dimensions.
- Synthesis review: 20/20 complete; `accept=12`, `revise=4`, `reject=4`.
- Protected-column mismatches: 0.
- Approved ZIP SHA-256: `cd757251a7fb60370ba08795d7fdc6529f5d7b962760eeee55ec2e6c3f4f9ac1`.

Single grade-0 mapping is intentional. Mapping correctly preserves old chunk content, but chunk does
not support claimed reference fact. This is treated as inherited qrel error, not R4 remapping error.

## Owner-validated locked-test retrieval metrics

| System | MRR@10 | Recall@10 | Precision@10 | nDCG@10 | Hit@10 |
|---|---:|---:|---:|---:|---:|
| BM25 | 0.6071 | 0.8625 | 0.1200 | 0.6460 | 0.9000 |
| FAISS normalized-cosine | 0.4113 | 0.6750 | 0.0975 | 0.4451 | 0.7500 |
| Entity Graph v4 | 0.4579 | 0.6750 | 0.0950 | 0.4724 | 0.7500 |
| Hybrid RRF | 0.5938 | 0.8625 | 0.1200 | 0.6306 | 0.9000 |
| Prompt-RAG Claude | 0.5842 | **0.8875** | **0.1225** | **0.6469** | **0.9250** |

MRR is unchanged because intentional grade-0 chunk was not first relevant result. Recall and nDCG
increase slightly because denominator/ideal ranking now exclude one unsupported positive.

## Owner generation evaluation

| System | Correctness | Faithfulness | Completeness | Citation accuracy | Unsupported severity | Abstention quality |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 1.3 | 2.0 | 1.0 | 2.0 | 0.0 | 1.3 |
| FAISS normalized-cosine | 1.6 | 2.0 | 1.1 | 2.0 | 0.0 | 1.6 |
| Entity Graph v4 | **1.8** | 2.0 | 1.1 | 2.0 | 0.0 | **1.8** |
| Hybrid RRF | 1.4 | 2.0 | 1.0 | 2.0 | 0.0 | 1.4 |
| Prompt-RAG Claude | 1.5 | 2.0 | **1.2** | 2.0 | 0.0 | 1.5 |

Faithfulness and citation accuracy are constant at 2.0; unsupported-claim severity is constant at
0.0. Those dimensions cannot support between-system inference.

## H5

- MRR–faithfulness: not estimable because faithfulness is constant.
- MRR–correctness: rho `-0.1888`, 95% bootstrap interval `[-0.4009, 0.0698]`.
- nDCG–correctness: rho `-0.1659`, interval `[-0.3956, 0.0880]`.
- Recall–completeness: rho `0.0651`, interval `[-0.2746, 0.4232]`.

H5 remains exploratory descriptive analysis. Owner labels remove automated-label limitation but do
not create preregistered effect thresholds or causal evidence.

## Synthesis

Twelve candidates are accepted. Four require revision and four are rejected. Eight IDs remain
outside primary metrics and require content work: `r4_syn_006`, `r4_syn_008`, `r4_syn_009`,
`r4_syn_012`, `r4_syn_014`, `r4_syn_017`, `r4_syn_019`, and `r4_syn_020`.

## Integrity

- API calls: 0.
- Automated R4 artifacts modified: 0.
- Owner inputs preserved byte-identically.
- Synthesis rows merged into primary metrics: 0.
- Canonical status: `audits/phase8_r4_human_validated/canonical_status.json`.
- Manifest: `audits/phase8_r4_human_validated/manifest.json`.
