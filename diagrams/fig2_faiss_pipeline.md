# Figure 2: FAISS Dense Retrieval Pipeline

```mermaid
graph LR
    A["Document Chunks<br/>(text)"] -->|SentenceTransformer<br/>all-MiniLM-L6-v2| B["Embeddings<br/>(384-dim vectors)"]
    
    B -->|Build Index| C["FAISS IndexFlatL2"]
    
    C -->|Store| D["Index Files<br/>(faiss.index<br/>chunk_ids.json<br/>config.json)"]
    
    D -->|Retrieve| E["Query<br/>(text)"]
    
    E -->|SentenceTransformer| F["Query Embedding<br/>(384-dim vector)"]
    
    F -->|L2 Distance| C
    
    C -->|Top-k nearest<br/>neighbors| G["Retrieved Chunks<br/>(ranked by distance)"]
    
    G -->|Convert distance<br/>to score| H["Scored Results<br/>(score = 1 / 1+distance)"]
```

**Key Parameters:**
- Model: all-MiniLM-L6-v2 (384 dimensions)
- Index type: IndexFlatL2 (exact, no approximation)
- Similarity metric: L2 distance
- Query latency: ~500ms

