# Phase 0 Retrieval Benchmark

## Table 5.3 — Aggregate

| System | MRR@5 | MRR@10 | Recall@5 | Recall@10 | nDCG@10 | Avg latency (ms) |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 0.5703 | 0.5813 | 0.6800 | 0.7750 | 0.6017 | 1.04 |
| FAISS | 0.4555 | 0.4662 | 0.5200 | 0.6100 | 0.4637 | 22.23 |
| Entity-Co-occurrence Graph Retrieval | 0.1385 | 0.1537 | 0.2150 | 0.3050 | 0.1756 | 51.22 |

## Table 5.4 — Per category

| System | Category | MRR@5 | MRR@10 | Recall@5 | Recall@10 | nDCG@10 | Avg latency (ms) |
|---|---|---:|---:|---:|---:|---:|---:|
| BM25 | exact_match | 0.7850 | 0.7921 | 0.9500 | 1.0000 | 0.8437 | 0.77 |
| BM25 | terminology_heavy | 0.2792 | 0.3101 | 0.5500 | 0.7500 | 0.4163 | 0.39 |
| BM25 | paraphrase | 0.2750 | 0.2833 | 0.4000 | 0.4500 | 0.3244 | 0.99 |
| BM25 | entity_relation | 0.6917 | 0.7000 | 0.6500 | 0.7750 | 0.6436 | 1.51 |
| BM25 | multi_hop | 0.8208 | 0.8208 | 0.8500 | 0.9000 | 0.7805 | 1.54 |
| FAISS | exact_match | 0.6017 | 0.6151 | 0.8000 | 0.9000 | 0.6829 | 64.48 |
| FAISS | terminology_heavy | 0.1867 | 0.1950 | 0.3000 | 0.3500 | 0.2315 | 7.24 |
| FAISS | paraphrase | 0.2208 | 0.2472 | 0.3500 | 0.5500 | 0.3175 | 9.66 |
| FAISS | entity_relation | 0.5917 | 0.5972 | 0.5250 | 0.5750 | 0.5125 | 15.63 |
| FAISS | multi_hop | 0.6767 | 0.6767 | 0.6250 | 0.6750 | 0.5740 | 14.12 |
| Entity-Co-occurrence Graph Retrieval | exact_match | 0.1725 | 0.1725 | 0.3000 | 0.3000 | 0.2040 | 143.58 |
| Entity-Co-occurrence Graph Retrieval | terminology_heavy | 0.1517 | 0.1694 | 0.2500 | 0.4000 | 0.2221 | 21.70 |
| Entity-Co-occurrence Graph Retrieval | paraphrase | 0.0375 | 0.0592 | 0.1000 | 0.2500 | 0.1033 | 40.78 |
| Entity-Co-occurrence Graph Retrieval | entity_relation | 0.1333 | 0.1535 | 0.1750 | 0.2750 | 0.1538 | 23.28 |
| Entity-Co-occurrence Graph Retrieval | multi_hop | 0.1975 | 0.2142 | 0.2500 | 0.3000 | 0.1948 | 26.75 |

## Sanity flags

- None
