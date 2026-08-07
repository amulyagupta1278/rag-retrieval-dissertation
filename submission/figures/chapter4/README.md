# Chapter 4 figure set

Seven editable SVG figures generated from implemented R4 and Phase 9 pipelines.
All figures use a 1400 × 850 viewBox, Arial-compatible typography, white
background, colour-plus-label encoding, and embedded accessibility metadata.

| Figure | File | Primary implementation evidence |
|---|---|---|
| 4.1 | `figure-4-1-end-to-end-architecture.svg` | R4 corpus/retrieval paths, holdout runner, Phase 9 analysis |
| 4.2 | `figure-4-2-ingestion-and-chunking.svg` | `scripts/build_phase8_r4_improvements.py` |
| 4.3 | `figure-4-3-entity-graph-v4.svg` | `src/retrievers/graphrag_retriever.py`, `scripts/run_phase8_r4_graph_hybrid.py` |
| 4.4 | `figure-4-4-fusion-and-reranking.svg` | `scripts/run_phase8_r4_graph_hybrid.py`, `src/retrievers/prompt_rag_phase8_r4_v2.py` |
| 4.5 | `figure-4-5-evaluation-harness.svg` | `scripts/run_phase8_option_b_holdout.py`, frozen run manifests |
| 4.6 | `figure-4-6-generation-and-h5.svg` | `scripts/freeze_phase9_h5_generation_50.py`, `scripts/analyze_phase9_h5_followup.py` |
| 4.7 | `figure-4-7-deployment-view.svg` | index artefacts, retriever modules, Anthropic client paths |

Canonical values shown in figures:

- 130 documents and 954 section-aware chunks; 450-word windows with 60-word overlap.
- BM25 `k1=1.2`, `b=0.75`.
- FAISS `IndexFlatIP` over L2-normalised 384-dimensional MiniLM embeddings.
- Entity Graph v4: 3,781 nodes, 26,430 edges, two-hop traversal and lexical fallback.
- Weighted hybrid: `k=10`, weights 1.00/0.25/0.10, graph-only factor 0.0.
- Prompt-RAG: deduplicated BM25 top-25 and FAISS top-25 union; 1,024 output tokens.
- Evaluation: 60 development, 40 locked-test, 12 canonical holdout questions.
- H5: 150 outputs, 81 claim-bearing answers, 69 abstentions and 301 claims.

Regenerate with:

```bash
python scripts/generate_chapter4_svgs.py
```
