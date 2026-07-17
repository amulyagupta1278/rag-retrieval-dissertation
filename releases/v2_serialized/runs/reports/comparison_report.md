# Retrieval Comparison Report

**Generated:** 2026-06-21 02:41:59

**QA Dataset Size:** 28 queries

## Overall Metrics

| Retriever | MRR@5 | MRR@10 | Recall@5 | Recall@10 | nDCG@5 | nDCG@10 | Latency (ms) |
|-----------|-------|--------|----------|-----------|--------|---------|-------------|
| BM25 | 0.8304 | 0.8304 | 0.8214 | 1.0000 | 0.7804 | 0.8683 | 0.06 |
| FAISS | 0.7958 | 0.7958 | 0.8571 | 0.8571 | 0.7742 | 0.7742 | 92.06 |
| GRAPHRAG | 0.6095 | 0.6095 | 0.6875 | 0.6875 | 0.5909 | 0.5909 | 3.29 |

## Per-Category Breakdown (MRR@5)

| Category | bm25 | faiss | graphrag |
|----------|---|---|---|
| entity_relation | 1.0000 | 1.0000 | 1.0000 |
| exact_lookup | 0.9444 | 0.6389 | 0.5407 |
| multi_hop | 0.5500 | 0.6067 | 0.3333 |
| paraphrase | 1.0000 | 1.0000 | 0.2667 |
| synthesis | 0.6667 | 0.9167 | 0.9167 |
| terminology | 1.0000 | 1.0000 | 0.6250 |

## Key Findings

- **Best overall (MRR@5):** BM25 (0.8304)
- **Lowest overall (MRR@5):** GRAPHRAG (0.6095)
- **Best per category:**
  - entity_relation: FAISS (1.0000)
  - exact_lookup: BM25 (0.9444)
  - multi_hop: FAISS (0.6067)
  - paraphrase: FAISS (1.0000)
  - synthesis: FAISS (0.9167)
  - terminology: FAISS (1.0000)

## Failure Analysis

**Lowest MRR@5 category per retriever:**
- BM25: multi_hop (0.5500)
- FAISS: multi_hop (0.6067)
- GRAPHRAG: paraphrase (0.2667)
