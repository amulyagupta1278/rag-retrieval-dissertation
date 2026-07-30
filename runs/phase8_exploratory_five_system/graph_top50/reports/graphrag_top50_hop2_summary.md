# Experiment Report: `graphrag_top50_hop2`

## Configuration
```json
{
  "retriever": "graphrag",
  "human_name": "Entity-Co-occurrence Graph Retrieval",
  "top_k": 50,
  "max_hop": 2,
  "entity_model": "en_core_web_sm",
  "relation_window": 2,
  "min_entity_freq": 2,
  "split": "all",
  "seed_filtering": false,
  "use_aliases": false,
  "hub_penalty": false,
  "dual_entity_coverage": false,
  "lexical_fallback": false,
  "max_seeds": 5,
  "hop_decay": 0.5
}
```

## Aggregate Metrics

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Entity-Co-occurrence Graph Retrieval | 100 | 0.1612 | 0.0500 | 0.1200 | 0.1385 | 0.1537 | 0.0450 | 0.1500 | 0.2150 | 0.3050 | 0.0500 | 0.1149 | 0.1442 | 0.1756 |

### Category: `entity_relation`

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Entity-Co-occurrence Graph Retrieval | 20 | 0.1636 | 0.0000 | 0.1083 | 0.1333 | 0.1535 | 0.0000 | 0.1250 | 0.1750 | 0.2750 | 0.0000 | 0.0887 | 0.1151 | 0.1538 |

### Category: `exact_match`

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Entity-Co-occurrence Graph Retrieval | 20 | 0.1801 | 0.1000 | 0.1500 | 0.1725 | 0.1725 | 0.1000 | 0.2000 | 0.3000 | 0.3000 | 0.1000 | 0.1631 | 0.2040 | 0.2040 |

### Category: `multi_hop`

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Entity-Co-occurrence Graph Retrieval | 20 | 0.2194 | 0.0500 | 0.1750 | 0.1975 | 0.2142 | 0.0250 | 0.1750 | 0.2500 | 0.3000 | 0.0500 | 0.1347 | 0.1729 | 0.1948 |

### Category: `paraphrase`

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Entity-Co-occurrence Graph Retrieval | 20 | 0.0682 | 0.0000 | 0.0250 | 0.0375 | 0.0592 | 0.0000 | 0.0500 | 0.1000 | 0.2500 | 0.0000 | 0.0315 | 0.0531 | 0.1033 |

### Category: `terminology_heavy`

| Retriever | N | MRR | MRR@1 | MRR@3 | MRR@5 | MRR@10 | R@1 | R@3 | R@5 | R@10 | nDCG@1 | nDCG@3 | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Entity-Co-occurrence Graph Retrieval | 20 | 0.1746 | 0.1000 | 0.1417 | 0.1517 | 0.1694 | 0.1000 | 0.2000 | 0.2500 | 0.4000 | 0.1000 | 0.1565 | 0.1759 | 0.2221 |

## Latency (ms, avg per query)

| Retriever | Avg Latency (ms) |
| --- | --- |
| Entity-Co-occurrence Graph Retrieval | 51.34 |
