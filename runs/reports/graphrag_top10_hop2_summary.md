# Experiment Report: `graphrag_top10_hop2`
_Generated: 2026-07-17T07:40:08.631165+00:00_

## Configuration
```json
{
  "retriever": "graphrag",
  "top_k": 10,
  "max_hop": 2,
  "entity_model": "en_core_web_sm",
  "relation_window": 2,
  "min_entity_freq": 2
}
```

## Aggregate Metrics

| Retriever | N | MRR | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| graphrag | 100 | 0.1152 | 0.0350 | 0.1300 | 0.1950 | 0.2350 | 0.0400 | 0.0969 | 0.1243 | 0.1382 |

### Category: `entity_relation`

| Retriever | N | MRR | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| graphrag | 20 | 0.0725 | 0.0000 | 0.0500 | 0.1000 | 0.1000 | 0.0000 | 0.0387 | 0.0637 | 0.0637 |

### Category: `exact_match`

| Retriever | N | MRR | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| graphrag | 20 | 0.1167 | 0.0500 | 0.2000 | 0.2000 | 0.2000 | 0.0500 | 0.1381 | 0.1381 | 0.1381 |

### Category: `multi_hop`

| Retriever | N | MRR | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| graphrag | 20 | 0.0883 | 0.0250 | 0.0500 | 0.0750 | 0.1250 | 0.0500 | 0.0500 | 0.0632 | 0.0830 |

### Category: `paraphrase`

| Retriever | N | MRR | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| graphrag | 20 | 0.0100 | 0.0000 | 0.0000 | 0.0500 | 0.0500 | 0.0000 | 0.0000 | 0.0193 | 0.0193 |

### Category: `terminology_heavy`

| Retriever | N | MRR | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| graphrag | 20 | 0.2885 | 0.1000 | 0.3500 | 0.5500 | 0.7000 | 0.1000 | 0.2577 | 0.3373 | 0.3868 |

## Latency (ms, avg per query)

| Retriever | Avg Latency (ms) |
| --- | --- |
| graphrag | 25.37 |
