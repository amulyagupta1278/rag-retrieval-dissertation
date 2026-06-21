# Figure 1: Overall System Architecture

```mermaid
graph TD
    A["Raw Corpus<br/>(PDF, DOCX, JSON)"] -->|Extract, Clean, Chunk| B["chunks_v1.jsonl<br/>(300-word windows)"]
    B -->|Preprocess| C["Shared Ingestion Layer<br/>(Text cleaning, metadata enrichment)"]
    
    C -->|Index| FAISS["FAISS Dense Retrieval<br/>(SentenceTransformer → IndexFlatL2)"]
    C -->|Index| BM25["BM25 Lexical Retrieval<br/>(Okapi BM25 formula)"]
    C -->|Index| GraphRAG["GraphRAG Entity-Aware<br/>(spaCy NER + NetworkX)"]
    
    D["QA Dataset<br/>(50 queries, 6 categories)"] -->|Load| FAISS
    D -->|Load| BM25
    D -->|Load| GraphRAG
    
    FAISS -->|Retrieve top-k| E["Run Files<br/>(JSONL format)"]
    BM25 -->|Retrieve top-k| E
    GraphRAG -->|Retrieve top-k| E
    
    E -->|Evaluate| F["Evaluation Framework<br/>(MRR, Recall@k, nDCG@k)"]
    
    G["Qrels<br/>(TREC format)"] -->|Load| F
    
    F -->|Generate reports| H["Results<br/>(CSV metrics, Markdown analysis)"]
    
    subgraph FAISS_Params["⚙️ FAISS Key Parameters & Details"]
        F1["Model: all-MiniLM-L6-v2"]
        F2["Embedding Dim: 384"]
        F3["Index Type: IndexFlatL2"]
        F4["Similarity: L2 Distance"]
        F5["Latency: ~92 ms/query"]
        F6["Accuracy: MRR@5 = 0.7958"]
        F7["Advantage: Semantic matching"]
        F8["Limitation: Slow inference"]
    end
    
    subgraph BM25_Params["⚙️ BM25 Key Parameters & Details"]
        B1["Algorithm: Okapi BM25"]
        B2["k1 Parameter: 1.5"]
        B3["b Parameter: 0.75"]
        B4["Index: Inverted Index"]
        B5["Latency: ~0.06 ms/query"]
        B6["Accuracy: MRR@5 = 0.8304"]
        B7["Advantage: Fast & Exact Match"]
        B8["Limitation: No Semantics"]
    end
    
    subgraph GraphRAG_Params["⚙️ GraphRAG Key Parameters & Details"]
        G1["NER Tool: spaCy"]
        G2["Entity Types: 12 total"]
        G3["Graph Type: DiGraph NetworkX"]
        G4["Traversal: 2-hop"]
        G5["Latency: ~3.29 ms/query"]
        G6["Accuracy: MRR@5 = 0.6095"]
        G7["Advantage: Entity Relations"]
        G8["Limitation: Small corpus needs tuning"]
    end
```

