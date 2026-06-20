# Graph RAG Retriever

An entity-aware dense retriever that builds a knowledge graph of extracted entities and their co-occurrence patterns, enabling intelligent query resolution through graph traversal.

## Overview

The Graph RAG retriever combines:
- **Named Entity Recognition (NER)** using spaCy (`en_core_web_sm`)
- **Domain-specific entity patterns** via regex (welfare scheme entities)
- **Knowledge graph** stored in NetworkX DiGraph
- **Query-time graph traversal** (2-hop neighborhood search)

```
Chunks
    ↓ (extract entities)
Entities: (PERSON, ORG, GPE, MONEY, DATE, LAW, SCHEME_NAME, AMOUNT, BENEFICIARY, ...)
    ↓ (co-occurrence)
Knowledge Graph:
    • Entity nodes (with chunk_ids)
    • Chunk nodes
    • MENTIONED_IN edges (entity → chunk)
    • CO_OCCURS_WITH edges (entity → entity)
    ↓ (save to JSON)
indexes/graphrag/
  ├── graph.json           (all nodes and edges)
  └── chunk_lookup.json    (chunk metadata)
    ↓ (at query time)
Query → Entity Extraction → Seed Nodes → 2-Hop Traversal → Ranked Chunks
```

## Setup

### Install Dependencies

```bash
pip install -r requirements-graphrag.txt
python -m spacy download en_core_web_sm
```

or manually:

```bash
pip install spacy>=3.5.0 networkx>=2.6.0 numpy>=1.21.0
python -m spacy download en_core_web_sm
```

### Build Graph

Build the knowledge graph from your corpus:

```bash
python scripts/build_graph.py
```

**Output:**
- `indexes/graphrag/graph.json` — Complete graph (nodes + edges)
- `indexes/graphrag/chunk_lookup.json` — Chunk metadata for retrieval

**Time:** ~1 second for 3 chunks (spaCy model already loaded)

**Statistics Example:**
```
Graph Statistics:
  Total nodes: 45
    • Entity nodes: 42
    • Chunk nodes: 3
  Total edges: 699
  Graph density: 0.7061

Entity Nodes by Type:
  • AMOUNT        :  4
  • BENEFICIARY   :  5
  • DATE          :  4
  • DOCUMENT      :  1
  • ELIGIBILITY   :  1
  • GPE           :  2
  • ORG           : 13
  • PERSON        :  3
  • SCHEME_NAME   :  9
```

### Run Retrieval

Retrieve top-k results for queries:

```bash
python scripts/run_graphrag.py
```

**Input:** `data/queries/qa_dataset_v1.jsonl` (or `qa_dataset.jsonl`)

**Output:**
- `runs/retrieval/graphrag_run.tsv` — TREC format
- `runs/retrieval/graphrag_run.jsonl` — Detailed runs

**Time:** ~2ms per query (spaCy model cached)

## Usage

### Direct Python API

```python
from src.retrievers.graph_retriever import GraphRAGRetriever

# Initialize and load graph
retriever = GraphRAGRetriever(
    graph_dir="indexes/graphrag",
    chunks_path="data/chunks/chunks_v1.jsonl",
    model_name="en_core_web_sm",
)
retriever.load_graph()

# Retrieve for a single query
results = retriever.retrieve("What is PM-KISAN?", top_k=5)

for result in results:
    print(f"Rank {result.rank}: {result.chunk_id} (score={result.score:.4f})")
    print(f"  Seed entities matched: {result.extra.get('num_seed_matches')}")
```

### Building a Custom Graph

```python
import json

# Load chunks
chunks = []
with open("data/chunks/chunks_v1.jsonl") as f:
    for line in f:
        chunks.append(json.loads(line))

# Build graph from scratch
retriever = GraphRAGRetriever(
    graph_dir="indexes/custom_graph",
    chunks_path="data/chunks/chunks_v1.jsonl",
)
retriever.build_graph()

# Run queries
results = retriever.retrieve("your query", top_k=10)
```

## Entity Extraction

### Standard Entities (spaCy NER)

Extracted automatically via spaCy `en_core_web_sm`:

| Type | Examples |
|------|----------|
| **PERSON** | Names, individuals |
| **ORG** | Government departments, organizations (e.g., "Ministry of Agriculture") |
| **GPE** | Locations, states (e.g., "Punjab", "Delhi") |
| **MONEY** | Numeric values (e.g., "$50", "€100") |
| **DATE** | Temporal expressions (e.g., "2024", "August") |
| **LAW** | Legal documents (e.g., "Constitution") |

### Domain-Specific Entities (Regex Patterns)

Extracted using hand-crafted patterns for welfare schemes:

| Type | Pattern Examples | Domain Examples |
|------|------------------|-----------------|
| **SCHEME_NAME** | `Yojana`, `Scheme`, `Mission` | PM-KISAN, PMJAY, MGNREGA |
| **AMOUNT** | `Rs. X`, `INR X`, `X lakh` | "Rs. 6000", "5 lakhs" |
| **BENEFICIARY** | `farmer`, `women`, `BPL`, `SC/ST` | "small and marginal farmers" |
| **ELIGIBILITY** | `eligible`, `age limit`, `income limit` | "Must be above 18 years" |
| **DOCUMENT** | `Aadhaar`, `PAN`, `Ration Card` | Required documents |

## Query Resolution

### Step 1: Seed Node Identification

Extract entities from query using same pipeline (spaCy + domain patterns):

```
Query: "What schemes are available for farmers in Punjab?"
  ↓
Entities: [("farmer", "BENEFICIARY"), ("Punjab", "GPE"), ("scheme", "SCHEME_NAME")]
  ↓
Seed nodes: [entity_23, entity_42, entity_15] (matched from graph)
```

**Fallback:** If no entities match, use keyword overlap scoring.

### Step 2: 2-Hop Graph Traversal

From each seed node, traverse neighbors within 2 hops:

```
Seed node (entity_23: "farmer")
  ↓ MENTIONED_IN
Chunks directly mentioning entity: [chunk_001, chunk_003]
  ↓ CO_OCCURS_WITH
Neighbours of entity_23: [entity_25, entity_30, entity_42]
  ↓ MENTIONED_IN (from neighbours)
Chunks via 2-hop: [chunk_002, chunk_004]
```

**Scoring:**
- Chunks mentioned by seed nodes: **+1.0** per seed node
- Chunks mentioned by 2-hop neighbours: **+0.5** per neighbour

### Step 3: Ranking and Return

Sort chunks by cumulative score, return top-k.

## Output Formats

### TREC Run File (`graphrag_run.tsv`)

```
query_id    Q0    chunk_id          rank    score       system_name
q_0001      Q0    chunk_aa4e34cd    1       0.500000    graphrag
q_0001      Q0    chunk_b97b59fc    2       0.350000    graphrag
q_0002      Q0    chunk_6084a763    1       0.400000    graphrag
```

### Graph JSON Structure

**Nodes:**
```json
{
  "id": "entity_0",
  "text": "Pradhan Mantri",
  "type": "ORG",
  "chunk_ids": ["chunk_aa4e34cd", "chunk_b97b59fc"]
}
```

**Edges:**
```json
{
  "source": "entity_0",
  "target": "chunk_aa4e34cd",
  "relation": "MENTIONED_IN",
  "chunk_id": ""
}
```

## Configuration

Edit constants in `GraphRAGRetriever.__init__()`:

```python
model_name = "en_core_web_sm"        # spaCy NER model
graph_dir = "indexes/graphrag"       # Where to save graph
chunks_path = "data/chunks/chunks_v1.jsonl"
```

## Graph Statistics

| Metric | Value |
|--------|-------|
| **Build Time** | 1.0s (3 chunks) |
| **Query Latency** | 2-11ms per query |
| **Memory Usage** | ~50 MB (spaCy model + graph) |
| **Disk Usage** | ~106 KB graph + 3.5 KB metadata |

## Performance Characteristics

### Strengths

✅ **Terminology variation handling**: "PM-KISAN" ↔ "Kisan Samman Nidhi"
✅ **Implicit relevance**: Finds docs with related entities
✅ **Transparent**: Human-readable graph JSON
✅ **Deterministic**: No randomness, perfectly reproducible
✅ **Fast query time**: ~2-11ms per query

### Weaknesses

❌ **Sparsity**: Depends on NER quality
❌ **No learning**: Fixed patterns, cannot adapt
❌ **Limited scope**: 2-hop traversal may miss distant relevance
❌ **Cold start**: First query slower (model loading)

## Troubleshooting

### "Model not found: en_core_web_sm"

```
OSError: Can't find model 'en_core_web_sm'
```

**Solution:**
```bash
python -m spacy download en_core_web_sm
```

### No entities extracted from query

**Possible causes:**
- Query contains no standard NER entities (PERSON, ORG, etc.)
- Domain pattern doesn't match query text

**Fallback:** System uses keyword overlap scoring automatically.

### Graph file too large

For large corpora (> 100k chunks), consider:
- Storing graph in NetworkX binary format (pickle) instead of JSON
- Implementing incremental graph building

## Comparison with FAISS

| Aspect | Graph RAG | FAISS |
|--------|-----------|-------|
| **Entity awareness** | ✓ Explicit | ✗ Implicit |
| **Paraphrase handling** | ✓ Co-occurrence | ✓ Embeddings |
| **Terminology variation** | ✓ Pattern matching | ✗ Embedding similarity |
| **Cold start time** | ~100ms (first entity extract) | ~100ms (model load) |
| **Query latency** | ~5ms | ~500ms |
| **Interpretability** | ✓ Human-readable graph | ✗ Black-box embeddings |

## Advanced Usage

### Inspecting the Graph

```python
import networkx as nx

# Load and inspect
G = retriever.graph

# Entity nodes
entity_nodes = [n for n, d in G.nodes(data=True) if d['type'] != 'CHUNK']
print(f"Total entities: {len(entity_nodes)}")

# Edges by relation type
mentioned_in = [(u, v) for u, v, d in G.edges(data=True) if d['relation'] == 'MENTIONED_IN']
co_occurs = [(u, v) for u, v, d in G.edges(data=True) if d['relation'] == 'CO_OCCURS_WITH']
print(f"MENTIONED_IN: {len(mentioned_in)}, CO_OCCURS_WITH: {len(co_occurs)}")

# Most connected entities
degrees = dict(G.degree())
top_entities = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:10]
for node, degree in top_entities:
    node_data = G.nodes[node]
    print(f"{node_data['text']}: {degree} connections")
```

### Custom Entity Patterns

Extend `_DOMAIN_PATTERNS` in `graph_retriever.py`:

```python
_DOMAIN_PATTERNS["CUSTOM_TYPE"] = [
    r"pattern1",
    r"pattern2",
]
```

## Further Reading

- spaCy documentation: https://spacy.io/
- NetworkX documentation: https://networkx.org/
- Knowledge graphs in NLP: https://aclanthology.org/D19-1139/
