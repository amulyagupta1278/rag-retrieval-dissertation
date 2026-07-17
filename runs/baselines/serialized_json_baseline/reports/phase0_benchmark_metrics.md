# Phase 0 Retrieval Benchmark

## Table 5.3 — Aggregate

| System | MRR@5 | MRR@10 | Recall@5 | Recall@10 | nDCG@10 | Avg latency (ms) |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 0.4107 | 0.4265 | 0.5750 | 0.7200 | 0.4778 | 1.38 |
| FAISS | 0.1383 | 0.1570 | 0.1650 | 0.2600 | 0.1633 | 32.42 |
| GRAPHRAG | 0.1083 | 0.1152 | 0.1950 | 0.2350 | 0.1382 | 25.37 |

## Table 5.4 — Per category

| System | Category | MRR@5 | MRR@10 | Recall@5 | Recall@10 | nDCG@10 | Avg latency (ms) |
|---|---|---:|---:|---:|---:|---:|---:|
| BM25 | exact_match | 0.7333 | 0.7396 | 0.9500 | 1.0000 | 0.8035 | 1.03 |
| BM25 | terminology_heavy | 0.3825 | 0.4042 | 0.7000 | 0.8500 | 0.5113 | 0.47 |
| BM25 | paraphrase | 0.0667 | 0.0972 | 0.2000 | 0.4000 | 0.1681 | 1.33 |
| BM25 | entity_relation | 0.4625 | 0.4830 | 0.5000 | 0.7000 | 0.4836 | 2.03 |
| BM25 | multi_hop | 0.4083 | 0.4083 | 0.5250 | 0.6500 | 0.4225 | 2.02 |
| FAISS | exact_match | 0.3267 | 0.3489 | 0.4000 | 0.5500 | 0.3950 | 80.78 |
| FAISS | terminology_heavy | 0.0100 | 0.0100 | 0.0500 | 0.0500 | 0.0193 | 8.03 |
| FAISS | paraphrase | 0.0250 | 0.0368 | 0.0500 | 0.1500 | 0.0624 | 14.25 |
| FAISS | entity_relation | 0.1717 | 0.1894 | 0.2000 | 0.2750 | 0.1679 | 45.70 |
| FAISS | multi_hop | 0.1583 | 0.2001 | 0.1250 | 0.2750 | 0.1718 | 13.33 |
| GRAPHRAG | exact_match | 0.1167 | 0.1167 | 0.2000 | 0.2000 | 0.1381 | 83.16 |
| GRAPHRAG | terminology_heavy | 0.2675 | 0.2885 | 0.5500 | 0.7000 | 0.3868 | 9.09 |
| GRAPHRAG | paraphrase | 0.0100 | 0.0100 | 0.0500 | 0.0500 | 0.0193 | 10.51 |
| GRAPHRAG | entity_relation | 0.0725 | 0.0725 | 0.1000 | 0.1000 | 0.0637 | 12.08 |
| GRAPHRAG | multi_hop | 0.0750 | 0.0883 | 0.0750 | 0.1250 | 0.0830 | 11.99 |

## Sanity flags

- None
