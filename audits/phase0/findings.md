# Phase 0 historical metric recomputation

- Status: numerically recomputable from committed inputs.
- Scope: forensic 28-query benchmark; not final inferential evidence.
- Relevance: binary; every qrel value greater than zero is relevant.
- Supplementary analysis: graded nDCG@10 uses positive qrel values as gains.
- Aggregation: unweighted macro mean across queries.
- nDCG root cause: historical qrels contain grades 1 and 2, but historical code converted all positive grades to a set of chunk IDs. Published nDCG therefore uses binary relevance. A graded-relevance recomputation answers a different metric and must not be compared as if it were the same definition. Published binary nDCG reproduction remains unchanged; graded nDCG is supplementary.
