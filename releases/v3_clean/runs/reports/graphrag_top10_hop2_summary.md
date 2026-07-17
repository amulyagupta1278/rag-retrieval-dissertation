# Experiment Report: `graphrag_top10_hop2`

## Configuration
```json
{
  "retriever": "graphrag",
  "human_name": "Entity-Co-occurrence Graph Retrieval",
  "top_k": 10,
  "max_hop": 2,
  "entity_model": "en_core_web_sm",
  "relation_window": 2,
  "min_entity_freq": 2,
  "split": "all"
}
```

## Aggregate Metrics

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Entity-Co-occurrence Graph Retrieval | 100 | 0.1712 | 0.0700 | 0.1383 | 0.1553 | 0.1712 | 0.0600 | 0.1550 | 0.2050 | 0.2950 | 0.0700 | 0.1273 | 0.1513 | 0.1832 |

### Category: `entity_relation`

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Entity-Co-occurrence Graph Retrieval | 20 | 0.1847 | 0.0000 | 0.1250 | 0.1625 | 0.1847 | 0.0000 | 0.1250 | 0.2250 | 0.3250 | 0.0000 | 0.0967 | 0.1495 | 0.1895 |

### Category: `exact_match`

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Entity-Co-occurrence Graph Retrieval | 20 | 0.1500 | 0.1000 | 0.1500 | 0.1500 | 0.1500 | 0.1000 | 0.2000 | 0.2000 | 0.2000 | 0.1000 | 0.1631 | 0.1631 | 0.1631 |

### Category: `multi_hop`

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Entity-Co-occurrence Graph Retrieval | 20 | 0.2405 | 0.1000 | 0.2000 | 0.2250 | 0.2405 | 0.0500 | 0.1500 | 0.2000 | 0.2500 | 0.1000 | 0.1387 | 0.1651 | 0.1862 |

### Category: `paraphrase`

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Entity-Co-occurrence Graph Retrieval | 20 | 0.1113 | 0.0500 | 0.0750 | 0.0875 | 0.1113 | 0.0500 | 0.1000 | 0.1500 | 0.3000 | 0.0500 | 0.0815 | 0.1031 | 0.1554 |

### Category: `terminology_heavy`

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Entity-Co-occurrence Graph Retrieval | 20 | 0.1694 | 0.1000 | 0.1417 | 0.1517 | 0.1694 | 0.1000 | 0.2000 | 0.2500 | 0.4000 | 0.1000 | 0.1565 | 0.1759 | 0.2221 |

## Latency (ms, avg per query)

| Retriever | Avg Latency (ms) |
| --- | --- |
| Entity-Co-occurrence Graph Retrieval | 18.22 |
