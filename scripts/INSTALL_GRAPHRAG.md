# GraphRAG Installation & Quick Start

## Installation

```bash
# Install dependencies
pip install spacy networkx

# Download spaCy NER model
python -m spacy download en_core_web_sm
```

Or use the requirements file:
```bash
pip install -r requirements-graphrag.txt
python -m spacy download en_core_web_sm
```

## Quick Start

### 1. Build Knowledge Graph (One-Time)

```bash
python scripts/build_graph.py
```

**Output:**
- `indexes/graphrag/graph.json` — Knowledge graph (45 nodes, 699 edges for sample)
- `indexes/graphrag/chunk_lookup.json` — Chunk metadata

### 2. Run Retrieval

```bash
python scripts/run_graphrag.py
```

**Output:**
- `runs/retrieval/graphrag_run.tsv` — TREC format run file
- `runs/retrieval/graphrag_run.jsonl` — Detailed runs with metadata

## What's Included

### Core Implementation: `src/retrievers/graph_retriever.py`

**Class: `GraphRAGRetriever`** (subclasses `BaseRetriever`)

Methods:
- `build_index(chunks: list[dict])` — Build knowledge graph offline
- `load_graph()` — Load pre-built graph from disk
- `retrieve(query: str, top_k: int)` — Query-time retrieval with 2-hop traversal
- `write_run_file(queries, top_k, output_path)` — Write TREC-format output

Features:
- **Entity Extraction:** spaCy NER (PERSON, ORG, GPE, MONEY, DATE, LAW) + domain patterns
- **Graph Construction:** NetworkX DiGraph with entity nodes, chunk nodes, and two types of edges
- **Query Resolution:** Entity matching + 2-hop neighbourhood traversal
- **Fallback:** Keyword overlap if no entities match

### Scripts

**`scripts/build_graph.py`**
- Loads chunks, extracts entities, builds graph
- Outputs: Graph statistics by entity type, total edges, density

**`scripts/run_graphrag.py`**
- Loads pre-built graph and queries
- Runs retrieval on all queries
- Outputs: TREC + JSONL run files, per-query statistics

## Entity Types Extracted

### Standard (spaCy)
- PERSON, ORG, GPE, MONEY, DATE, LAW

### Domain-Specific (Regex)
- **SCHEME_NAME**: PM-KISAN, PMJAY, MGNREGA, etc.
- **AMOUNT**: Rs. 6000, 5 lakhs, INR X, etc.
- **BENEFICIARY**: farmers, women, BPL, SC/ST, etc.
- **ELIGIBILITY**: age limit, income limit, conditions, etc.
- **DOCUMENT**: Aadhaar, PAN, Ration Card, etc.

## Graph Structure

### Nodes
- **Entity nodes**: Text representation + entity type + list of chunk_ids
- **Chunk nodes**: Full chunk text + doc_id

### Edges
- **MENTIONED_IN**: Entity → Chunk (entity appears in chunk)
- **CO_OCCURS_WITH**: Entity → Entity (both in same chunk)

### Human-Inspectable JSON
```json
{
  "nodes": [
    {"id": "entity_0", "text": "PM-KISAN", "type": "SCHEME_NAME", "chunk_ids": ["chunk_001", "chunk_003"]},
    ...
  ],
  "edges": [
    {"source": "entity_0", "target": "chunk_001", "relation": "MENTIONED_IN"},
    {"source": "entity_0", "target": "entity_5", "relation": "CO_OCCURS_WITH"},
    ...
  ]
}
```

## Retrieval Pipeline

```
Query: "What is the eligibility for PM-KISAN?"
  ↓
Extract entities: [("PM-KISAN", "SCHEME_NAME"), ("eligibility", "ELIGIBILITY")]
  ↓
Find seed nodes in graph: [entity_42, entity_89]
  ↓
Traverse 2-hop neighbourhood
  ├─ Direct: Chunks mentioning entities (score +1.0)
  └─ 2-hop: Chunks mentioning co-occurring entities (score +0.5)
  ↓
Rank & return top-k chunks
```

## Performance

| Metric | Value |
|--------|-------|
| Graph build time | 1.0s (3 chunks) |
| Query latency | 2–11ms per query |
| Memory footprint | 50 MB (spaCy + graph) |
| Disk footprint | 106 KB graph + 3.5 KB metadata |

## Documentation

See `docs/GRAPHRAG_RETRIEVER.md` for:
- Detailed entity extraction documentation
- Query resolution algorithm
- Advanced usage (graph inspection, custom patterns)
- Comparison with FAISS and BM25
- Troubleshooting

## Comparison: Graph RAG vs FAISS vs BM25

| Feature | Graph RAG | FAISS | BM25 |
|---------|-----------|-------|------|
| Entity aware | ✓ | ✗ | ✗ |
| Paraphrase robust | ~ (co-occurrence) | ✓ | ✗ |
| Terminology matching | ✓ | ✗ | ✓ |
| Query speed | ✓✓ (2-11ms) | ✓ (500ms) | ✓✓ (1-5ms) |
| Interpretable | ✓ (graph JSON) | ✗ (embeddings) | ✓ (term frequency) |
| Cold start | ~100ms | ~100ms | Fast |
| Scalability | Good (<100k) | Excellent | Excellent |

## Example Usage

```python
from src.retrievers.graph_retriever import GraphRAGRetriever

# Initialize
retriever = GraphRAGRetriever(
    graph_dir="indexes/graphrag",
    chunks_path="data/chunks/chunks_v1.jsonl",
)

# Load pre-built graph
retriever.load_graph()

# Retrieve
results = retriever.retrieve("What is PM-KISAN eligibility?", top_k=5)

# Print results
for result in results:
    print(f"{result.rank}. {result.chunk_id} (score={result.score:.3f})")
    print(f"   Entities matched: {result.extra['num_seed_matches']}")
    print()
```

## Troubleshooting

### spaCy model not found
```bash
python -m spacy download en_core_web_sm
```

### Graph file not found
```bash
python scripts/build_graph.py  # Build first
```

### No retrieval results
- Check if graph was built correctly
- Verify chunk files exist
- Enable debug logging: `logging.basicConfig(level=logging.DEBUG)`

## Files Created

```
src/retrievers/
  └── graph_retriever.py          ← Main implementation

scripts/
  ├── build_graph.py              ← Graph construction
  ├── run_graphrag.py             ← Query runner
  └── INSTALL_GRAPHRAG.md         ← This file

indexes/graphrag/
  ├── graph.json                  ← Knowledge graph
  └── chunk_lookup.json           ← Chunk metadata

runs/retrieval/
  ├── graphrag_run.tsv            ← TREC format
  └── graphrag_run.jsonl          ← Detailed runs

docs/
  └── GRAPHRAG_RETRIEVER.md       ← Full documentation

requirements-graphrag.txt         ← Dependencies
```

## Next Steps

1. **Build graph once**: `python scripts/build_graph.py`
2. **Run queries**: `python scripts/run_graphrag.py`
3. **Inspect results**: Open `runs/retrieval/graphrag_run.tsv` or `graphrag_run.jsonl`
4. **Compare with FAISS**: `python scripts/run_faiss.py` for side-by-side evaluation

Enjoy entity-aware retrieval! 🎉
