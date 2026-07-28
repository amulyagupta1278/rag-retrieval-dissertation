# Phase 8 R4 Improvement Status

Status: offline experimental branch; R3 baseline preserved; human validation incomplete.

## Implemented

- Audited 130 documents and 856 R3 chunks: zero exact duplicate documents, one near-duplicate pair, and ten noisy-chunk candidates. No review-sensitive document was silently deleted.
- Rebuilt corpus as 954 balanced, section-aware chunks using 450-word windows and 60-word overlap. Titles and section headings remain in retrieval text.
- Mapped all 140 R3 gold judgments to R4 chunks. Minimum frozen-reference-answer coverage is 0.5111; every mapping remains automatic and pending human validation.
- Created 20 deterministic cross-document synthesis candidates with two source programmes and at least two evidence chunks each.
- Created category-stratified 60-query development and 40-query locked test split. Retrieval parameters use development queries only.
- Tuned BM25 on development split and evaluated once on locked test split.
- Built normalized-cosine FAISS using pinned `all-MiniLM-L6-v2` revision.
- Rebuilt Graph index from all 954 R4 chunks: 3,781 nodes and 26,430 edges; reran all 120 questions with aliases, seed filtering, hub penalty, dual-entity coverage, and lexical fallback.
- Rebuilt equal BM25–Graph Hybrid and dev-selected weighted BM25–FAISS–Graph Hybrid using only matching R4 rankings.
- Built deterministic BM25-top-25 plus FAISS-top-25 union plans for later Prompt-RAG reranking. No LLM calls occurred.

## Locked-test retrieval results

| System/variant | MRR@10 | Recall@10 | nDCG@10 |
|---|---:|---:|---:|
| R3 BM25 baseline | 0.5655 | 0.7625 | 0.5942 |
| R4 section-aware BM25 | **0.6071** | **0.8500** | **0.6412** |
| R3 FAISS baseline | 0.4341 | 0.6250 | 0.4427 |
| R4 normalized-cosine FAISS | 0.4113 | 0.6625 | 0.4413 |
| R4 fresh Graph v4 | 0.4579 | 0.6625 | 0.4628 |
| R4 equal BM25–Graph Hybrid | 0.5350 | 0.7750 | 0.5576 |
| R4 weighted BM25–FAISS–Graph Hybrid | 0.5938 | **0.8500** | 0.6245 |

R4 section-aware BM25 improves locked-test BM25 by +0.0416 MRR@10, +0.0875 Recall@10, and +0.0470 nDCG@10. Fresh Graph greatly improves over R3 Graph but remains below BM25. Equal BM25–Graph fusion dilutes BM25. Weighted three-system fusion matches BM25 recall but remains below BM25 MRR and nDCG; R4 BM25 remains strongest locked-test system.

BM25–FAISS candidate-union recall rises from 0.825 at depth 10 to 0.880 at depth 25. This supports, but does not yet execute, a larger mixed Prompt-RAG candidate pool.

## Synthesis candidate result

R4 BM25 reaches MRR@10 0.6392, Recall@10 0.5000, and nDCG@10 0.4499 on 20 automatically composed synthesis candidates. These figures are diagnostic only: questions and crosswalk qrels lack human validation.

## Remaining gates

1. Review one near-duplicate pair, ten noisy chunks, 140 qrel crosswalk rows, and 20 synthesis questions.
2. Freeze cost for mixed top-25 Prompt-RAG trace before any paid call.
3. Run statistical comparison only after validation and final configuration freeze.
4. Keep R3 Phase 8 results as canonical baseline until all R4 gates pass.

No claim that Phase 8 is human validated, final-scale confirmed, or hypothesis-proving is authorized.
