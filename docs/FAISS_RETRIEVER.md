# FAISS Dense Retriever

A production-ready dense retrieval system for the RAG dissertation using FAISS (exact L2-based search) and SentenceTransformer embeddings.

## Overview

The FAISS retriever provides exact semantic search over a corpus of document chunks using:
- **SentenceTransformer embeddings** (`all-MiniLM-L6-v2`) for dense representation
- **FAISS IndexFlatL2** for exact L2-distance similarity search (no approximation)
- **Disk-persistent index** for efficient replay experiments

## Architecture

```
chunks_v1.jsonl
    ↓ (load)
chunks: [{"chunk_id", "doc_id", "text", ...}, ...]
    ↓ (encode with SentenceTransformer)
embeddings: (N, 384) float32 array
    ↓ (build index)
FAISS IndexFlatL2(dim=384)
    ↓ (save to disk)
indexes/faiss/
  ├── faiss.index       (binary index)
  ├── chunk_ids.json    (chunk_id list for index lookups)
  └── config.json       (metadata: model_name, dim, num_chunks)
```

## Setup

### Install Dependencies

```bash
pip install -r requirements-faiss.txt
```

or manually:

```bash
pip install faiss-cpu>=1.7.4 sentence-transformers>=2.2.0 numpy>=1.21.0
```

### Build Index

Build the FAISS index from your corpus:

```bash
python scripts/build_faiss_index.py
```

**Output:**
- `indexes/faiss/faiss.index` — Binary index file
- `indexes/faiss/chunk_ids.json` — List of chunk IDs (indexed by position)
- `indexes/faiss/config.json` — Index configuration

**Time:** ~15s for 3 chunks (model download + embedding + indexing)

### Run Retrieval

Retrieve top-k results for a query file:

```bash
python scripts/run_faiss.py
```

**Input:** `data/queries/qa_dataset_v1.jsonl` (or `qa_dataset.jsonl`)

**Output:**
- `runs/retrieval/faiss_run.tsv` — TREC format (one result per line)
- `runs/retrieval/faiss_run.jsonl` — Detailed runs (RetrievalRun JSONL format)

**Time:** ~2.3s for 5 queries

## Usage

### Direct Python API

```python
from src.retrievers.faiss_retriever import FAISSRetriever
import json

# Initialize retriever
retriever = FAISSRetriever(
    index_dir="indexes/faiss",
    chunks_path="data/chunks/chunks_v1.jsonl",
    model_name="all-MiniLM-L6-v2",
)

# Load a pre-built index from disk
retriever.load_index()

# Retrieve for a single query
results = retriever.retrieve("What is PM-KISAN?", top_k=5)

for result in results:
    print(f"Rank {result.rank}: {result.chunk_id} (score={result.score:.4f})")
    print(f"  Doc: {result.doc_id}")
    print(f"  Text: {result.text[:100]}...")
```

### Building a Custom Index

```python
# Load chunks from JSONL
chunks = []
with open("data/chunks/chunks_v1.jsonl") as f:
    for line in f:
        chunks.append(json.loads(line))

# Build index from scratch
retriever = FAISSRetriever(
    index_dir="indexes/custom",
    chunks_path="data/chunks/chunks_v1.jsonl",
)
retriever.build_index(chunks)

# Now retriever is ready for queries
results = retriever.retrieve("your query", top_k=10)
```

### Batch Retrieval (Benchmark)

```python
# Load queries
qa_items = [
    {"question_id": "q1", "question": "What is BM25?"},
    {"question_id": "q2", "question": "What is FAISS?"},
]

# Run benchmark
runs = retriever.run_benchmark(qa_items, top_k=5)

for run in runs:
    print(f"Query: {run.query_text}")
    print(f"  Results: {len(run.results)}")
    print(f"  Latency: {run.total_latency_ms:.2f}ms")
```

## Output Formats

### TREC Run File (`faiss_run.tsv`)

Tab-separated format, one result per line:

```
query_id    Q0    chunk_id           rank    score         system_name
q_0001      Q0    chunk_aa4e34cd     1       0.390125      faiss
q_0001      Q0    chunk_b97b59fc     2       0.370375      faiss
q_0002      Q0    chunk_6084a763     1       0.362619      faiss
```

**Columns:**
- `query_id`: Query identifier
- `Q0`: Placeholder (TREC standard)
- `chunk_id`: Retrieved chunk ID
- `rank`: 1-based rank
- `score`: Similarity score in (0, 1]
- `system_name`: Retriever name (`faiss`)

### RetrievalRun JSONL (`faiss_run.jsonl`)

One JSON object per line, one object per query:

```json
{
  "query_id": "q_0001",
  "query_text": "What is BM25?",
  "retriever": "faiss",
  "top_k": 5,
  "results": [
    {
      "chunk_id": "chunk_aa4e34cd",
      "doc_id": "pmkisan_demo",
      "text": "...",
      "score": 0.390125,
      "rank": 1,
      "latency_ms": 512.48,
      "retriever": "faiss",
      "extra": {"distance": 1.563}
    },
    ...
  ],
  "total_latency_ms": 512.48,
  "config_snapshot": {...}
}
```

## Configuration

Edit constants in `FAISSRetriever.__init__()` or `scripts/build_faiss_index.py`:

```python
model_name = "all-MiniLM-L6-v2"        # Embedding model
index_dir = "indexes/faiss"             # Where to save index
chunks_path = "data/chunks/chunks_v1.jsonl"
```

## Index Details

### Model

- **Name:** `all-MiniLM-L6-v2`
- **Dimensions:** 384
- **Speed:** ~0.1s per query (including encoding)
- **Size:** ~90 MB (downloaded once, cached locally)

### Index Type

- **Type:** `IndexFlatL2`
- **Search:** Exact L2-distance (no approximation)
- **Scalability:** Best for < 1M chunks (dissertation scale: ~1k chunks)
- **Scoring:** `score = 1 / (1 + distance)` → range [0, 1]

### Score Interpretation

Lower L2 distance = higher similarity score:
- Distance 0.0 → score 1.0 (identical embedding)
- Distance 1.0 → score 0.5 (moderately similar)
- Distance 3.0 → score 0.25 (weakly similar)

## Reproduction

To rebuild the index from scratch:

```bash
rm -rf indexes/faiss/
python scripts/build_faiss_index.py
python scripts/run_faiss.py
```

All randomness is eliminated (no GPU, no approximate search), so results are perfectly reproducible.

## Performance

| Metric | Value |
|--------|-------|
| **Index Build Time** | 15.6s (3 chunks) |
| **Query Latency** | 0.5–1.0s per query |
| **Memory Usage** | ~50 MB (model + embeddings) |
| **Disk Usage** | ~4.5 KB index + 90 MB model |

*(Times measured on Apple Silicon with `all-MiniLM-L6-v2`)*

## Comparison with Other Approaches

| Method | Pros | Cons |
|--------|------|------|
| **FAISS (this)** | Exact, reproducible, fast | Only semantic similarity |
| **BM25** | Lexical matching, no embedding training | Misses paraphrases |
| **GraphRAG** | Structured knowledge, entity-aware | Complex, harder to tune |

## Troubleshooting

### Index not found

```
FileNotFoundError: Index file not found: indexes/faiss/faiss.index
```

**Solution:** Run `python scripts/build_faiss_index.py` first.

### Query results are all low scores

**Possible causes:**
- Query is semantically distant from corpus
- Corpus is too small to contain relevant chunks
- Try increasing `top_k` parameter

### Memory error during build

For large corpora (> 100k chunks), reduce batch size in `build_index()`:

```python
embeddings = model.encode(
    texts,
    batch_size=32,  # Reduce from 64
    show_progress_bar=True,
)
```

## Further Reading

- FAISS documentation: https://faiss.ai/
- SentenceTransformer: https://www.sbert.net/
- MinLM paper: https://arxiv.org/abs/2106.07851
