# RAG Retrieval Dissertation

**Comparative Analysis of Vector-Free Retrieval Strategies for RAG: Hybrid Search and Graph-Based Approaches**

| | |
|---|---|
| **Student** | Amulya Gupta |
| **BITS ID** | 2024AB05200 |
| **Program** | M.Tech. Artificial Intelligence and Machine Learning |
| **Course** | AIMLC ZG628T — Dissertation |
| **Organisation** | HCLTech, Noida |

---

## Research Goal

Demonstrate whether FAISS (dense), BM25 (sparse), and GraphRAG (graph-based) retrieval paradigms retrieve relevant evidence differently on the same benchmark dataset — and under which query categories each paradigm leads.

---

## Repository Structure

```
.
├── configs/               # Reproducible YAML configs for corpus, chunking, retrieval, evaluation
├── data/
│   ├── raw/               # Place your corpus documents here (PDF/DOCX/TXT/HTML/JSON)
│   ├── processed/         # Cleaned document JSONL (auto-generated)
│   ├── chunks/            # Chunk-level JSONL (auto-generated)
│   ├── queries/           # qa_dataset.jsonl + query_categories.json
│   └── qrels/             # qrels.tsv (TREC format) + evidence_map.json
├── indexes/               # Persisted BM25, FAISS, GraphRAG indexes
├── runs/
│   ├── retrieval/         # Per-retriever JSONL run files
│   ├── metrics/           # metrics.csv (MRR, Recall@k, nDCG@k, latency)
│   └── reports/           # Markdown + JSON experiment summaries
├── src/
│   ├── ingestion/         # DocumentLoader, TextCleaner, Chunker, MetadataEnricher, CorpusVersioner
│   ├── benchmark/         # QAGenerator, QRelsBuilder, QueryCategorizer
│   ├── retrievers/        # BaseRetriever, FAISSRetriever, BM25Retriever, GraphRAGRetriever
│   ├── evaluation/        # metrics.py, RetrievalEvaluator, ReportGenerator
│   └── utils/             # logging, I/O helpers
├── experiments/           # Runnable experiment scripts
│   ├── build_dataset.py   # Ingest → clean → chunk → QA benchmark
│   ├── run_faiss.py       # FAISS dense retrieval experiment
│   ├── run_bm25.py        # BM25 sparse retrieval experiment
│   ├── run_graphrag.py    # GraphRAG entity-graph retrieval experiment
│   └── compare_retrievers.py  # Cross-retriever comparison + reports
├── tests/                 # 31 unit tests (pytest)
├── requirements.txt
├── pyproject.toml
└── Makefile
```

---

## Quickstart

```bash
# 1. Install dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# 2. Acquire reviewed authoritative v2 sources
python scripts/download_corpus.py

# 3. Build corpus + benchmark
python experiments/build_dataset.py

# 4. Run retrievers
python experiments/run_faiss.py    --top-k 10 --rebuild
python experiments/run_bm25.py     --top-k 10 --rebuild
python experiments/run_graphrag.py --top-k 10 --rebuild

# 5. Compare all retrievers
python experiments/compare_retrievers.py
python scripts/generate_corpus_statistics.py
# → runs/reports/experiment_summary.md
# → runs/metrics/metrics.csv
# → runs/reports/retrieval_results.json
```

Or use the Makefile:

```bash
make install        # pip install
make spacy-model    # download en_core_web_sm
make all            # dataset + faiss + bm25 + graphrag + compare
make all-v2         # acquire v2 + full rebuild + statistics + comparison
make test           # 31 unit tests
```

---

## Query Categories (Benchmark Stratification)

| Category | Description | Hypothesis |
|---|---|---|
| `exact_match` | Exact fact lookup | BM25 leads (H1) |
| `terminology_heavy` | Acronym / technical term | BM25 leads (H1) |
| `paraphrase` | Semantically paraphrased | FAISS leads (H2) |
| `entity_relation` | Entity relationship questions | GraphRAG leads (H3) |
| `multi_hop` | Requires evidence from ≥2 chunks | GraphRAG leads (H3) |

---

## Evaluation Metrics

- **MRR** — Mean Reciprocal Rank
- **Recall@k** — k ∈ {1, 3, 5, 10}
- **nDCG@k** — Normalised Discounted Cumulative Gain
- **Precision@k**
- **Latency (ms)** — avg per query

All metrics are computed per-retriever **and** per-query-category for sliced analysis.

---

## Authoritative Corpus v2

`data/sources/source_catalog_v2.jsonl` is the reviewed source registry. Acquisition stores
official myScheme scheme content, FAQs, and document metadata with checksums in
`data/raw/snapshot_v2/`. Canonical ingestion remains `experiments/build_dataset.py` and keeps
the established 512-word chunks with 64-word overlap. Builds fail closed when document/chunk
bounds, provenance, ministry diversity, document-type coverage, deduplication, or qrels lineage
checks fail. Versioned v1 artifacts remain untouched.

Audit outputs:

- `data/metadata/acquisition_audit_v2.jsonl`
- `data/metadata/deduplication_report_v2.jsonl`
- `data/metadata/corpus_statistics_v2.json`
- `data/metadata/corpus_statistics_v2.md`

---

## Working Hypotheses

- **H1** BM25 competitive on exact-match and terminology-heavy queries
- **H2** FAISS strong on paraphrased / semantic queries
- **H3** GraphRAG outperforms flat retrieval on entity-relation and multi-hop queries
