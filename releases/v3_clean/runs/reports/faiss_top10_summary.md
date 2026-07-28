# Experiment Report: `faiss_top10`

## Configuration
```json
{
  "retriever": "faiss",
  "top_k": 10,
  "model_name": "sentence-transformers/all-MiniLM-L6-v2",
  "model_revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
  "similarity_metric": "l2",
  "normalize_embeddings": false,
  "query_prefix": "",
  "passage_prefix": "",
  "split": "all"
}
```

## Aggregate Metrics

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| faiss | 100 | 0.4648 | 0.3700 | 0.4350 | 0.4555 | 0.4648 | 0.2650 | 0.4250 | 0.5200 | 0.6000 | 0.3700 | 0.3909 | 0.4328 | 0.4604 |

### Category: `entity_relation`

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| faiss | 20 | 0.5972 | 0.5000 | 0.5917 | 0.5917 | 0.5972 | 0.2500 | 0.4750 | 0.5250 | 0.5750 | 0.5000 | 0.4686 | 0.4923 | 0.5125 |

### Category: `exact_match`

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| faiss | 20 | 0.6079 | 0.5000 | 0.5667 | 0.6017 | 0.6079 | 0.5000 | 0.6500 | 0.8000 | 0.8500 | 0.5000 | 0.5881 | 0.6505 | 0.6663 |

### Category: `multi_hop`

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| faiss | 20 | 0.6767 | 0.5500 | 0.6417 | 0.6767 | 0.6767 | 0.2750 | 0.5000 | 0.6250 | 0.6750 | 0.5500 | 0.4912 | 0.5546 | 0.5740 |

### Category: `paraphrase`

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| faiss | 20 | 0.2472 | 0.1500 | 0.2083 | 0.2208 | 0.2472 | 0.1500 | 0.3000 | 0.3500 | 0.5500 | 0.1500 | 0.2315 | 0.2531 | 0.3175 |

### Category: `terminology_heavy`

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| faiss | 20 | 0.1950 | 0.1500 | 0.1667 | 0.1867 | 0.1950 | 0.1500 | 0.2000 | 0.3000 | 0.3500 | 0.1500 | 0.1750 | 0.2137 | 0.2315 |

## Latency (ms, avg per query)

| Retriever | Avg Latency (ms) |
| --- | --- |
| faiss | 18.90 |
