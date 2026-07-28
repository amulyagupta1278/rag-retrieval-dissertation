# Experiment Report: `faiss_top10`
_Generated: 2026-07-17T07:39:58.139086+00:00_

## Configuration
```json
{
  "retriever": "faiss",
  "top_k": 10,
  "model_name": "sentence-transformers/all-MiniLM-L6-v2",
  "index_type": "IndexFlatIP",
  "batch_size": 64,
  "normalize_embeddings": true,
  "index_path": "indexes/faiss/faiss.index",
  "meta_path": "indexes/faiss/faiss_meta.jsonl"
}
```

## Aggregate Metrics

| Retriever | N | MRR | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| faiss | 100 | 0.1570 | 0.0750 | 0.1300 | 0.1650 | 0.2600 | 0.0900 | 0.1144 | 0.1292 | 0.1633 |

### Category: `entity_relation`

| Retriever | N | MRR | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| faiss | 20 | 0.1894 | 0.0250 | 0.1250 | 0.2000 | 0.2750 | 0.0500 | 0.1040 | 0.1396 | 0.1679 |

### Category: `exact_match`

| Retriever | N | MRR | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| faiss | 20 | 0.3489 | 0.3000 | 0.3500 | 0.4000 | 0.5500 | 0.3000 | 0.3250 | 0.3443 | 0.3950 |

### Category: `multi_hop`

| Retriever | N | MRR | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| faiss | 20 | 0.2001 | 0.0500 | 0.1250 | 0.1250 | 0.2750 | 0.1000 | 0.1113 | 0.1113 | 0.1718 |

### Category: `paraphrase`

| Retriever | N | MRR | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| faiss | 20 | 0.0368 | 0.0000 | 0.0500 | 0.0500 | 0.1500 | 0.0000 | 0.0315 | 0.0315 | 0.0624 |

### Category: `terminology_heavy`

| Retriever | N | MRR | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| faiss | 20 | 0.0100 | 0.0000 | 0.0000 | 0.0500 | 0.0500 | 0.0000 | 0.0000 | 0.0193 | 0.0193 |

## Latency (ms, avg per query)

| Retriever | Avg Latency (ms) |
| --- | --- |
| faiss | 32.42 |
