# Figure 5: Evaluation Framework

```mermaid
graph TD
    A["Run Files<br/>(FAISS, BM25, GraphRAG)<br/>JSONL format"] -->|Load| B["RetrievalEvaluator"]
    
    C["Qrels<br/>(TREC format)<br/>query_id, chunk_id, relevance"] -->|Load| B
    
    D["QA Dataset<br/>(question_id, category)<br/>JSONL"] -->|Load| B
    
    B -->|For each retriever:| E["Compute Metrics"]
    
    E -->|Per-Query Metrics| F["MRR<br/>Recall@5, @10<br/>nDCG@5, @10<br/>Latency"]
    
    E -->|Aggregate (all queries)| G["Overall Metrics<br/>(mean, std)"]
    
    E -->|Per-Category| H["Category Breakdown<br/>(exact_lookup,<br/>terminology,<br/>paraphrase,<br/>entity_relation,<br/>multi_hop,<br/>synthesis)"]
    
    G -->|Output CSV| I["comparison_summary.csv"]
    
    H -->|Output CSV| J["per_category.csv"]
    
    F -->|Generate Analysis| K["Findings<br/>(strengths, weaknesses,<br/>failure modes)"]
    
    I -->|Generate| L["comparison_report.md<br/>(Markdown report<br/>with tables & findings)"]
    J -->|Generate| L
    K -->|Generate| L
```

**Metrics Computed:**

1. **MRR (Mean Reciprocal Rank):**
   - MRR = (1/n) × Σ(1 / rank of first gold chunk)
   - Range: [0, 1], higher is better
   - Suited for: exact lookup queries

2. **Recall@k:**
   - Recall@k = (# gold chunks in top-k) / (# total gold chunks)
   - Range: [0, 1], higher is better
   - Suited for: multi-hop, synthesis (need coverage)

3. **nDCG@k (Normalized Discounted Cumulative Gain):**
   - Accounts for rank and relevance
   - DCG@k = Σ (2^rel_i - 1) / log2(i+1)
   - nDCG@k = DCG@k / IDCG@k
   - Range: [0, 1], higher is better
   - Suited for: all query types

4. **Precision@k:**
   - Precision@k = (# gold chunks in top-k) / k
   - Range: [0, 1], higher is better
   - Suited for: ranking quality

**Output Files:**
- `comparison_summary.csv`: One row per retriever, metrics as columns
- `per_category.csv`: One row per (retriever, category) pair
- `comparison_report.md`: Markdown table + findings + failure analysis

