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
```

**BM25 Formula:**
```
BM25(q, d) = Σ IDF(q_i) × (f(q_i,d) × (k1+1)) / 
             (f(q_i,d) + k1 × (1-b + b × |d|/avgdl))
```

**Key Parameters:**
- k1 = 1.2 (tunable, controls term frequency saturation)
- b = 0.75 (tunable, controls length normalization)
- Query latency: ~1-5ms (pure CPU)

