# Comparative RAG System: Three Retrievers

Your dissertation system now includes three complementary retrieval approaches. This document shows how they compare and how to use them together.

## System Overview

```
Chunked Corpus (chunks_v1.jsonl)
    ↓
    ├─→ [BM25 Retriever]        (Lexical: term frequency-based)
    ├─→ [FAISS Retriever]       (Dense: semantic embeddings)
    └─→ [Graph RAG Retriever]   (Entity-aware: knowledge graph)
         ↓
         → Runs saved to runs/retrieval/
         → Comparable in same benchmark
```

## Three Retrieval Approaches

### 1. BM25 Retriever (Sparse Lexical)

**What it does:** Ranks chunks by term frequency using BM25 formula.

**Best for:**
- Exact terminology matching
- Queries with clear keywords
- When corpus is small or domain-specific

**Strengths:**
- ✅ Extremely fast (<1ms per query)
- ✅ Deterministic (no randomness)
- ✅ Completely interpretable (term weights)
- ✅ No model dependencies

**Weaknesses:**
- ❌ Misses paraphrased queries
- ❌ No semantic understanding
- ❌ OOV (out-of-vocabulary) terms

**Example:**
```
Query: "government schemes for farmers"
  → Matches chunks containing: government, schemes, farmers
  → Ranks by term frequency
```

### 2. FAISS Retriever (Dense Semantic)

**What it does:** Embeds queries and chunks using SentenceTransformer, finds nearest neighbours via exact L2 distance.

**Best for:**
- Paraphrased or semantically similar queries
- When exact terminology varies
- Semantic retrieval without structured knowledge

**Strengths:**
- ✅ Handles paraphrasing ("PM-KISAN" vs "farmer income support")
- ✅ Semantic understanding via embeddings
- ✅ One-size-fits-all (no tuning needed)
- ✅ Consistent with modern dense retrieval

**Weaknesses:**
- ❌ Slower (~500ms per query)
- ❌ Requires embedding model (~90 MB)
- ❌ Black-box (hard to debug)
- ❌ May miss explicit terminology

**Example:**
```
Query: "farming financial assistance"
  → Embed query → (384-dim vector)
  → Find nearest chunk embeddings
  → Matches semantically similar chunks (PM-KISAN, subsidy, etc.)
```

### 3. Graph RAG Retriever (Entity-Aware)

**What it does:** Extracts entities from query, traverses knowledge graph to find related chunks.

**Best for:**
- Structured domain (entities, relations matter)
- Queries about entities and their attributes
- When you need explainability

**Strengths:**
- ✅ Entity-aware matching
- ✅ Handles terminology variation via co-occurrence
- ✅ Human-readable (graph JSON)
- ✅ Very fast query time (~5ms)
- ✅ Explicit reasoning (seed nodes → traversal)

**Weaknesses:**
- ❌ Depends on entity extraction quality
- ❌ Sparse graph limits coverage
- ❌ Limited to 2-hop scope
- ❌ Requires domain pattern engineering

**Example:**
```
Query: "What schemes benefit small farmers?"
  → Extract entities: [("scheme", SCHEME_NAME), ("small farmer", BENEFICIARY)]
  → Find matching nodes in graph
  → Traverse 2-hop neighbourhood
  → Return chunks mentioning these entities
```

## Comparison Table

| Aspect | BM25 | FAISS | Graph RAG |
|--------|------|-------|-----------|
| **Approach** | Lexical (TF-IDF) | Dense (semantic) | Entity (graph) |
| **Query type** | Keywords | Semantic | Entity-based |
| **Paraphrase handling** | ❌ Poor | ✅ Excellent | ✅ Good |
| **Exact match** | ✅ Excellent | ❌ Poor | ✅ Good |
| **Query latency** | ⚡ 1-5ms | 🐢 500ms | ⚡⚡ 2-11ms |
| **Memory footprint** | 🤏 Minimal | 📦 50 MB | 📦 50 MB |
| **Model dependencies** | None | SentenceTransformer | spaCy |
| **Interpretability** | 🔓 Clear (terms) | 🔒 Hidden (embeddings) | 🔓 Clear (entities) |
| **Scalability** | ✅ Excellent | ✅ Good | ~ Fair |
| **Setup complexity** | 🟢 Easy | 🟡 Medium | 🟡 Medium |

## When to Use Each

### Use BM25 when:
- Queries have strong keyword signals
- You need raw speed (<5ms)
- You have minimal dependencies
- Exact terminology matters
- **Example queries:** "PM-KISAN payment", "Aadhaar requirement"

### Use FAISS when:
- Queries are paraphrased or semantic
- You want modern semantic matching
- Dataset is large (>10k docs)
- Speed is secondary to quality
- **Example queries:** "schemes for farming families", "government aid for poor"

### Use Graph RAG when:
- Entities and relations are important
- You want explainable results
- Query speed is critical
- You need fast answer construction
- **Example queries:** "eligibility for PM-KISAN", "what documents needed?"

## Running All Three

### Individual Runs

```bash
# Build indexes (one-time each)
python scripts/build_bm25_index.py
python scripts/build_faiss_index.py
python scripts/build_graph.py

# Run retrieval independently
python scripts/run_bm25.py           # → runs/retrieval/bm25_run.tsv
python scripts/run_faiss.py          # → runs/retrieval/faiss_run.tsv
python scripts/run_graphrag.py       # → runs/retrieval/graphrag_run.tsv
```

### Batch Comparison

```python
from src.retrievers.bm25_retriever import BM25Retriever
from src.retrievers.faiss_retriever import FAISSRetriever
from src.retrievers.graph_retriever import GraphRAGRetriever
import json

# Load queries
with open("data/queries/qa_dataset_v1.jsonl") as f:
    queries = [json.loads(line) for line in f]

# Initialize all three
bm25 = BM25Retriever(
    index_path="indexes/bm25/bm25_index.pkl",
    chunks_path="data/chunks/chunks_v1.jsonl",
)
bm25.load_index()

faiss = FAISSRetriever(
    index_dir="indexes/faiss",
    chunks_path="data/chunks/chunks_v1.jsonl",
)
faiss.load_index()

graphrag = GraphRAGRetriever(
    graph_dir="indexes/graphrag",
    chunks_path="data/chunks/chunks_v1.jsonl",
)
graphrag.load_graph()

# Run a single query with all three
query = queries[0]["question"]
for name, retriever in [("BM25", bm25), ("FAISS", faiss), ("GraphRAG", graphrag)]:
    results = retriever.retrieve(query, top_k=5)
    print(f"\n{name}:")
    for r in results:
        print(f"  {r.rank}. {r.chunk_id} (score={r.score:.3f})")
```

## Expected Behavior

### Query: "What is PM-KISAN?"

| Retriever | Expected Behavior | Latency |
|-----------|-------------------|---------|
| **BM25** | Matches chunks with "PM-KISAN" literally | 1ms |
| **FAISS** | Matches chunks about PM-KISAN (embeddings) | 500ms |
| **Graph RAG** | Finds entity node for "PM-KISAN", returns related chunks | 5ms |

### Query: "What schemes benefit farmers?"

| Retriever | Expected Behavior | Latency |
|-----------|-------------------|---------|
| **BM25** | Matches chunks with "scheme" + "farmer" | 1ms |
| **FAISS** | Finds semantically similar chunks | 500ms |
| **Graph RAG** | Matches SCHEME_NAME + BENEFICIARY entities | 5ms |

### Query: "agricultural financial assistance" (paraphrased PM-KISAN)

| Retriever | Expected Behavior | Latency |
|-----------|-------------------|---------|
| **BM25** | May miss if corpus uses different terms | 1ms |
| **FAISS** | Finds PM-KISAN via semantic similarity | 500ms |
| **Graph RAG** | May miss if pattern doesn't match | 5ms |

## System Integration

### For Your Dissertation

1. **Index Building** (offline, once per corpus):
   ```bash
   python scripts/build_bm25_index.py
   python scripts/build_faiss_index.py
   python scripts/build_graph.py
   ```

2. **Query Evaluation** (compare on same queries):
   ```bash
   python scripts/run_bm25.py
   python scripts/run_faiss.py
   python scripts/run_graphrag.py
   ```

3. **Evaluation Harness** (run_benchmark() in each retriever):
   ```python
   from src.retrievers.base_retriever import RetrievalRun
   
   # All three generate RetrievalRun objects
   # Can be loaded and compared uniformly
   runs_bm25 = RetrievalRun.load_run_file("runs/retrieval/bm25_run.jsonl")
   runs_faiss = RetrievalRun.load_run_file("runs/retrieval/faiss_run.jsonl")
   runs_graphrag = RetrievalRun.load_run_file("runs/retrieval/graphrag_run.jsonl")
   ```

4. **Metrics Calculation**:
   - Compare MRR (Mean Reciprocal Rank)
   - Compare NDCG@5 (Normalized Discounted Cumulative Gain)
   - Compare precision, recall against gold standard
   - Plot latency comparison
   - Analyze per-query-type performance

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Query Set (5 queries)                    │
└───────────────────┬──────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        ↓           ↓           ↓
   ┌─────────┐ ┌──────────┐ ┌────────────┐
   │   BM25  │ │  FAISS   │ │ GraphRAG   │
   ├─────────┤ ├──────────┤ ├────────────┤
   │ 1ms     │ │ 500ms    │ │ 5ms        │
   │ Term    │ │ Semantic │ │ Entity     │
   │ Freq    │ │ Embed    │ │ Graph      │
   └────┬────┘ └────┬─────┘ └─────┬──────┘
        │           │            │
        └───────────┼────────────┘
                    ↓
        ┌───────────────────────┐
        │   Run Files (TREC)    │
        ├───────────────────────┤
        │ bm25_run.tsv          │
        │ faiss_run.tsv         │
        │ graphrag_run.tsv      │
        └───────┬───────────────┘
                ↓
        ┌───────────────────────┐
        │ Evaluation Metrics     │
        ├───────────────────────┤
        │ MRR, NDCG@5           │
        │ Precision, Recall     │
        │ Latency comparison    │
        └───────────────────────┘
```

## Further Reading

- **BM25**: Okapi BM25 (standard IR ranking function)
- **FAISS**: Facebook AI Similarity Search
- **Graph-based RAG**: Entity linking + knowledge graph traversal
- **Comparative evaluation**: TREC evaluation tools, Pyserini

## Next Steps

1. Run all three retrievers on your full corpus
2. Evaluate against gold standard (if available)
3. Plot performance comparison
4. Analyze strengths/weaknesses per query type
5. Document findings in dissertation results section
