# Phase 8 Option B Independent Holdout Execution Status

Status: `four_local_systems_complete_prompt_rag_ambiguous_dispatch_stop`

Date: 2026-08-01

## Freeze

- Owner-reviewed questions: 12/12.
- Categories: two each for exact match, terminology-heavy, paraphrase, entity relation, multi-hop, and synthesis.
- Gold qrels: 21.
- Freeze status: `owner_approved_frozen_ready_for_single_execution`.
- Review corrections: SUMAN expansion completed; NPS-Traders eligibility evidence added; distractor-only exposure resolved under the preregistered unused-gold-source rule; completion formula strengthened.

## Holdout retrieval results

| System | MRR@10 | Recall@10 | Precision@10 | nDCG@10 | Hit@10 |
|---|---:|---:|---:|---:|---:|
| BM25 | 0.6667 | 0.8611 | 0.1500 | 0.6938 | 0.9167 |
| FAISS normalized-cosine | 0.5444 | 0.7500 | 0.1167 | 0.5685 | 0.8333 |
| Entity Graph v4 | 0.5162 | 0.6528 | 0.1083 | 0.4907 | 0.7500 |
| Hybrid RRF R4 | 0.6597 | 0.8611 | 0.1500 | 0.6855 | 0.9167 |

BM25, FAISS, Graph v4, and Hybrid used frozen R4 configurations. No parameter selection or error-driven modification used holdout results. FAISS query embedding and index search ran in isolated processes to avoid incompatible native OpenMP runtimes; model, revision, normalization, index, and ranking contract remained unchanged.

## Descriptive uncertainty

Ten-thousand whole-query bootstrap samples used seed 42. Selected 95% percentile intervals are:

| System | MRR@10 interval | nDCG@10 interval | Recall@10 interval |
|---|---:|---:|---:|
| BM25 | [0.4583, 0.8750] | [0.5060, 0.8597] | [0.6667, 1.0000] |
| FAISS normalized-cosine | [0.3389, 0.7500] | [0.3790, 0.7515] | [0.5278, 0.9444] |
| Entity Graph v4 | [0.2731, 0.7569] | [0.2854, 0.6924] | [0.4028, 0.8750] |
| Hybrid RRF R4 | [0.4514, 0.8542] | [0.4970, 0.8503] | [0.6667, 1.0000] |

Intervals overlap substantially. Point estimates favor BM25 narrowly over Hybrid, with both above FAISS and Graph v4, but 12-query uncertainty prevents decisive superiority claims. Category slices contain only two questions each and are diagnostic.

## Prompt-RAG execution checkpoint

Owner explicitly authorized Anthropic payload egress. Exact token counting froze a USD 0.355854 hard cap. `holdout_001` completed successfully with its gold chunk ranked first. Known observed usage is 22,946 input tokens and 604 output tokens, costing USD 0.025966 at frozen list prices.

The process terminated after counting the second attempt (`holdout_008`) but before persisting a provider response or terminal exception. Dispatch and incremental billing for that request are ambiguous. Zero-retry policy forbids rerunning it and requires stopping remaining requests. Prompt-RAG coverage is therefore 1/12 and no aggregate Prompt-RAG metric is reported.

## Claim boundary

Current results support a four-local-system independent holdout comparison. Five-system holdout claims are unavailable because Prompt-RAG stopped at an ambiguous dispatch checkpoint. With only 12 questions, results are descriptive and uncertainty is large; they must not be presented as decisive hypothesis proof.
