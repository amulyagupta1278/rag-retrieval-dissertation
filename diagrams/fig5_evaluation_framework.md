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
    
    subgraph Metrics_Details["📊 Evaluation Metrics Specification"]
        MD1["MRR (Mean Reciprocal Rank)"]
        MD1a["├─ Formula: (1/n) × Σ(1 / rank_i)"]
        MD1b["├─ Range: [0, 1] (higher better)"]
        MD1c["├─ Interpretation: Avg position of 1st gold chunk"]
        MD1d["└─ Best For: Exact lookup, entity-specific queries"]
        
        MD2["Recall@k"]
        MD2a["├─ Formula: (# gold chunks in top-k) / (# total gold)"]
        MD2b["├─ Range: [0, 1] (higher better)"]
        MD2c["├─ Interpretation: Coverage of relevant chunks"]
        MD2d["└─ Best For: Multi-hop, synthesis, recall-critical"]
        
        MD3["nDCG@k (Normalized Discounted Cumulative Gain)"]
        MD3a["├─ DCG@k = Σ (2^rel_i - 1) / log2(i+1)"]
        MD3b["├─ nDCG@k = DCG@k / IDCG@k"]
        MD3c["├─ Range: [0, 1] (higher better)"]
        MD3d["└─ Best For: Ranking quality (all query types)"]
        
        MD4["Latency"]
        MD4a["├─ Unit: milliseconds (ms)"]
        MD4b["├─ Meaning: Query processing time"]
        MD4c["├─ Baseline: FAISS ~92ms, BM25 ~0.06ms, GraphRAG ~3.29ms"]
        MD4d["└─ Best For: Production efficiency analysis"]
    end
    
    subgraph Query_Categories["🏷️ Query Categories (6 types)"]
        QC1["Category: Exact Lookup"]
        QC1a["├─ Definition: Question requires specific entity/value"]
        QC1b["├─ Example: 'What is PM-KISAN eligibility?'"]
        QC1c["└─ Best Performer: BM25 (0.9444)"]
        
        QC2["Category: Terminology"]
        QC2a["├─ Definition: Heavy use of acronyms/technical terms"]
        QC2b["├─ Example: 'Explain PMJAY benefits'"]
        QC2c["└─ Best Performer: BM25/FAISS (1.0)"]
        
        QC3["Category: Paraphrase"]
        QC3a["├─ Definition: Synonymous terms, different wording"]
        QC3b["├─ Example: 'Housing assistance vs. Awas'"]
        QC3c["└─ Best Performer: FAISS (1.0)"]
        
        QC4["Category: Entity Relation"]
        QC4a["├─ Definition: Relationship between entities"]
        QC4b["├─ Example: 'How do benefits link to eligibility?'"]
        QC4c["└─ Best Performer: FAISS (1.0)"]
        
        QC5["Category: Synthesis"]
        QC5a["├─ Definition: Combine info from multiple sources"]
        QC5b["├─ Example: 'Compare scheme A vs scheme B'"]
        QC5c["└─ Best Performer: FAISS (0.9167)"]
        
        QC6["Category: Multi-hop"]
        QC6a["├─ Definition: Requires chaining multiple facts"]
        QC6b["├─ Example: 'Who is eligible and what's the process?'"]
        QC6c["└─ Best Performer: FAISS (0.6067) - ALL STRUGGLE"]
    end
    
    subgraph Output_Files["📁 Output Files & Formats"]
        OF1["comparison_summary.csv"]
        OF1a["├─ Format: CSV (comma-separated)"]
        OF1b["├─ Rows: 3 (one per retriever)"]
        OF1c["├─ Columns: Retriever, MRR@5, MRR@10, Recall@5, ...]
        OF1d["└─ Use: Main results table for paper"]
        
        OF2["per_category.csv"]
        OF2a["├─ Format: CSV"]
        OF2b["├─ Rows: 6 (one per category)"]
        OF2c["├─ Columns: Category, BM25, FAISS, GraphRAG"]
        OF2d["└─ Use: Category breakdown analysis"]
        
        OF3["comparison_report.md"]
        OF3a["├─ Format: Markdown"]
        OF3b["├─ Sections: Tables, Key Findings, Failure Analysis"]
        OF3c["├─ Purpose: Human-readable report"]
        OF3d["└─ Use: Dissertation Chapter 5"]
        
        OF4["sample_queries.md"]
        OF4a["├─ Format: Markdown"]
        OF4b["├─ Content: 5 example queries with results"]
        OF4c["├─ Purpose: Qualitative examples"]
        OF4d["└─ Use: Qualitative discussion section"]
    end
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

