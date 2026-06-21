# Figure 3: BM25 Lexical Retrieval Pipeline

```mermaid
graph LR
    A["Document Chunks"] -->|Tokenize<br/>Remove Stopwords| B["Tokens<br/>(preserved: acronyms)"]
    
    B -->|Build Inverted Index<br/>term → [chunks]| C["Inverted Index"]
    
    C -->|Store| D["Index Files<br/>(bm25_index.pkl)"]
    
    D -->|Retrieve| E["Query<br/>(text)"]
    
    E -->|Tokenize<br/>Remove Stopwords| F["Query Tokens"]
    
    F -->|Okapi BM25<br/>formula| C
    
    C -->|Score each chunk<br/>BM25(q, d)| G["Scored Results<br/>(ranked by BM25)"]
    
    subgraph BM25_Config["⚙️ BM25 Configuration & Details"]
        BC1["Algorithm Specification"]
        BC1a["├─ Variant: Okapi BM25"]
        BC1b["├─ Library: rank-bm25"]
        BC1c["├─ Implementation: Pure Python"]
        BC1d["└─ No Dependencies: No CUDA/GPU needed"]
        
        BC2["Core Parameters"]
        BC2a["├─ k1 = 1.5 (term saturation)"]
        BC2b["│  ├─ Controls impact of term frequency"]
        BC2c["│  └─ Range: 0.0 (frequency ignored) to ∞"]
        BC2d["├─ b = 0.75 (length normalization)"]
        BC2e["│  ├─ Controls length bias"]
        BC2f["│  └─ Range: 0.0 (no normalization) to 1.0 (full)"]
        BC2g["└─ IDF Variant: Lucene-style"]
        
        BC3["Indexing Details"]
        BC3a["├─ Index Type: Inverted Index"]
        BC3b["├─ Storage Format: Python pickle"]
        BC3c["├─ Index Size: ~2KB (10 chunks)"]
        BC3d["└─ Persistence: bm25_index.pkl"]
        
        BC4["Performance Metrics"]
        BC4a["├─ Latency: ~0.06 ms/query"]
        BC4b["├─ MRR@5: 0.8304 ⭐ BEST"]
        BC4c["├─ Recall@10: 1.0000 (perfect)"]
        BC4d["└─ nDCG@10: 0.8683"]
        
        BC5["Category Performance"]
        BC5a["✓ Excellent (1.0): Terminology, Exact Lookup"]
        BC5b["✓ Good (0.94): Entity Relations"]
        BC5c["✓ Fair (0.55): Multi-hop"]
        BC5d["✗ Weak: Paraphrase (no semantics)"]
        
        BC6["Strengths & Limitations"]
        BC6a["✓ Blazing Fast: ~0.06ms (1500× faster than FAISS)"]
        BC6b["✓ Exact Matching: Preserves acronyms & terminology"]
        BC6c["✓ Interpretable: Which terms matched is clear"]
        BC6d["✗ Limitation: No semantic understanding"]
        BC6e["✗ Limitation: Vocabulary mismatch fails"]
    end
```

**BM25 Formula:**
```
BM25(q, d) = Σ IDF(q_i) × (f(q_i,d) × (k1+1)) / 
             (f(q_i,d) + k1 × (1-b + b × |d|/avgdl))

where:
  q_i = query term i
  f(q_i, d) = frequency of q_i in document d
  |d| = document length
  avgdl = average document length
  k1, b = tunable parameters
  IDF(q_i) = log((N - n(q_i) + 0.5) / (n(q_i) + 0.5))
```

**Key Parameters:**
- k1 = 1.5 (tunable, controls term frequency saturation)
- b = 0.75 (tunable, controls length normalization)
- Query latency: ~0.06ms (pure CPU, 1500× faster than embeddings)

