# Phase 8 R4 Automated Final Report

Status: automated expansion complete; human validation incomplete.

## Scope

R4 expands the preserved pilot from 22 documents, 140 chunks, and 34 owner-approved questions to 130 documents, 954 section-aware chunks, and 100 inherited questions. Twenty deterministic synthesis questions remain separate automated candidates. Pilot, R3, failed attempts, corrections, and audit lineage remain unchanged.

R4 uses 60 development and 40 locked-test questions across five primary categories. All 140 gold-evidence mappings into new chunks are automatic crosswalks pending human review. Therefore, R4 is exploratory expansion evidence and does not replace the human-validated pilot.

## Locked-test retrieval results

| System | MRR@10 | Recall@10 | Precision@10 | nDCG@10 |
|---|---:|---:|---:|---:|
| BM25 section-aware | **0.6071** | 0.8500 | 0.1200 | **0.6412** |
| FAISS normalized cosine | 0.4113 | 0.6625 | 0.0975 | 0.4413 |
| Graph v4 | 0.4579 | 0.6625 | 0.0950 | 0.4628 |
| Hybrid weighted RRF | 0.5938 | 0.8500 | 0.1200 | 0.6245 |
| Prompt-RAG Claude | 0.5842 | **0.8750** | **0.1225** | 0.6408 |

BM25 has highest locked-test MRR@10 and nDCG@10. Prompt-RAG has highest Recall@10 and Precision@10. Difference between BM25 and Prompt-RAG nDCG@10 is 0.0004. Missing latency is never treated as zero; trustworthy latency is available only for Prompt-RAG (mean 16.82 s, median 15.80 s, p95 24.25 s).

Category slices are frozen in `runs/phase8_r4_improvements/evaluation_r4/metrics.json`. Prompt-RAG leads terminology-heavy nDCG@10 (0.6717), while BM25 leads exact-match nDCG@10 (0.9375). Small category samples and automatic qrels prevent confirmatory conclusions.

## Exploratory statistics

Ten pairwise locked-test nDCG@10 comparisons use 10,000 paired sign-flip randomizations, paired bootstrap intervals, seed 42, and Holm correction. Analysis was explicitly exploratory, not preregistered R4 hypothesis testing.

- BM25 exceeded FAISS: difference +0.1998; Holm-adjusted p=0.0036.
- Hybrid exceeded FAISS: difference +0.1832; Holm-adjusted p=0.0020.
- Prompt-RAG exceeded FAISS: difference +0.1995; Holm-adjusted p=0.0056.
- Other adjusted comparisons did not cross 0.05.
- No result proves preregistered H1-H4 or general superiority.

## Generation

Generation covers 20 deterministic, category-balanced questions across five systems: 100 answers. Every request uses only system-specific top-three evidence. Final coverage is 100/100 after preserving all failed attempts and corrections:

- V1: 10 valid; one 512-token truncation preserved.
- V2: one complete response initially rejected by inherited 512-token validator; revalidated offline under frozen 1024-token contract.
- Corrected V2: 39 valid; one semantic citation-coverage failure preserved.
- V3: 50/50 valid after prompt-only semantic-contract correction.

API cost: Prompt-RAG retrieval $2.430722; generation through failures and recoveries $0.429828; cumulative R4 $2.860550, below $3.70 cap by $0.839450. No retries, fallback, replacement, or concealed failures occurred.

## Disclosed AI evaluation and H5

All 100 R4 quality labels are AI-assigned by an offline 5-nearest-neighbor evaluator using MiniLM features trained on 26 genuine Phase 7 owner-audit labels. R4 has zero owner-labelled overlap, so R4 AI-owner agreement is not estimable. Historical Phase 7 leave-one-owner-row-out calibration is reported only as transfer-model context, not R4 agreement or human reliability.

| System | Correctness | Faithfulness | Completeness | Citation accuracy | Unsupported severity | Abstentions |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 1.00 | 2.00 | 1.00 | 2.00 | 0.00 | 10/20 |
| FAISS | 1.10 | 2.00 | 1.10 | 2.00 | 0.00 | 9/20 |
| Graph v4 | 1.10 | 2.00 | 1.10 | 2.00 | 0.00 | 9/20 |
| Hybrid | 1.00 | 2.00 | 1.00 | 2.00 | 0.00 | 10/20 |
| Prompt-RAG | **1.30** | 2.00 | **1.30** | 2.00 | 0.00 | 8/20 |

Faithfulness is constant at 2.0, making its correlation with MRR non-estimable. Exploratory H5 correlations are weak and uncertain: MRR/correctness rho=-0.056 (95% bootstrap CI -0.345 to 0.254), nDCG/correctness rho=0.079 (-0.230 to 0.387), and Recall/completeness rho=0.078 (-0.256 to 0.434). H5 remains descriptive and does not establish causality or hypothesis support.

## Separate synthesis candidates

Twenty synthesis questions remain `automated_candidate_pending_human_validation`. They are excluded from primary five-category metrics, answer generation, H5, and claims of human-validated six-category performance. Existing diagnostic retrieval results remain separate in Graph/Hybrid metrics.

## Remaining manual work

1. Review 140 automatic gold-evidence crosswalk rows.
2. Review 100 inherited question/reference-answer records against R4 source documents.
3. Review one near-duplicate document pair and ten source-noise candidates.
4. Review 20 synthesis questions and their component evidence.
5. Human-score or audit R4 generated answers if human-validated generation claims are required.
6. Keep pilot as canonical dissertation evidence until these reviews are completed.

## Claim boundary

R4 demonstrates technically successful corpus expansion, five-system reindexing/retrieval, cost-controlled Prompt-RAG, complete generation, and disclosed automated evaluation. It does not prove hypotheses, validate every expanded label, or supersede the human-validated pilot.
