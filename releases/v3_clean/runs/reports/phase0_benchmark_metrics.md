# Phase 0 Retrieval Benchmark

## Table 5.3 — Aggregate

| System | MRR@5 | MRR@10 | Recall@5 | Recall@10 | nDCG@10 | Avg latency (ms) |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 0.5653 | 0.5763 | 0.6800 | 0.7750 | 0.5980 | 1.10 |
| FAISS | 0.4555 | 0.4648 | 0.5200 | 0.6000 | 0.4604 | 18.90 |
| Entity-Co-occurrence Graph Retrieval | 0.1553 | 0.1712 | 0.2050 | 0.2950 | 0.1832 | 18.22 |

## Table 5.4 — Per category

| System | Category | MRR@5 | MRR@10 | Recall@5 | Recall@10 | nDCG@10 | Avg latency (ms) |
|---|---|---:|---:|---:|---:|---:|---:|
| BM25 | exact_match | 0.7600 | 0.7671 | 0.9500 | 1.0000 | 0.8253 | 0.72 |
| BM25 | terminology_heavy | 0.2792 | 0.3101 | 0.5500 | 0.7500 | 0.4163 | 0.40 |
| BM25 | paraphrase | 0.2750 | 0.2833 | 0.4000 | 0.4500 | 0.3244 | 1.14 |
| BM25 | entity_relation | 0.6917 | 0.7000 | 0.6500 | 0.7750 | 0.6436 | 1.72 |
| BM25 | multi_hop | 0.8208 | 0.8208 | 0.8500 | 0.9000 | 0.7805 | 1.50 |
| FAISS | exact_match | 0.6017 | 0.6079 | 0.8000 | 0.8500 | 0.6663 | 38.06 |
| FAISS | terminology_heavy | 0.1867 | 0.1950 | 0.3000 | 0.3500 | 0.2315 | 7.64 |
| FAISS | paraphrase | 0.2208 | 0.2472 | 0.3500 | 0.5500 | 0.3175 | 12.29 |
| FAISS | entity_relation | 0.5917 | 0.5972 | 0.5250 | 0.5750 | 0.5125 | 20.82 |
| FAISS | multi_hop | 0.6767 | 0.6767 | 0.6250 | 0.6750 | 0.5740 | 15.67 |
| Entity-Co-occurrence Graph Retrieval | exact_match | 0.1500 | 0.1500 | 0.2000 | 0.2000 | 0.1631 | 52.97 |
| Entity-Co-occurrence Graph Retrieval | terminology_heavy | 0.1517 | 0.1694 | 0.2500 | 0.4000 | 0.2221 | 7.16 |
| Entity-Co-occurrence Graph Retrieval | paraphrase | 0.0875 | 0.1113 | 0.1500 | 0.3000 | 0.1554 | 10.31 |
| Entity-Co-occurrence Graph Retrieval | entity_relation | 0.1625 | 0.1847 | 0.2250 | 0.3250 | 0.1895 | 10.49 |
| Entity-Co-occurrence Graph Retrieval | multi_hop | 0.2250 | 0.2405 | 0.2000 | 0.2500 | 0.1862 | 10.17 |

## Sanity flags

- None
