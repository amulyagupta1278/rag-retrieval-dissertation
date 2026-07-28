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

Demonstrate whether FAISS (dense), BM25 (sparse), and Entity-Co-occurrence Graph Retrieval retrieve relevant evidence differently on the same benchmark dataset — and under which query categories each paradigm leads.

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
├── indexes/               # Persisted BM25, FAISS, entity-graph indexes
├── runs/
│   ├── retrieval/         # Per-retriever JSONL run files
│   ├── metrics/           # metrics.csv (MRR, Recall@k, nDCG@k, latency)
│   └── reports/           # Markdown + JSON experiment summaries
├── src/
│   ├── ingestion/         # DocumentLoader, TextCleaner, Chunker, MetadataEnricher, CorpusVersioner
│   ├── benchmark/         # QAGenerator, QRelsBuilder, QueryCategorizer
│   ├── retrievers/        # BM25, FAISS, entity-co-occurrence, structured-graph, and gated fusion code
│   ├── evaluation/        # metrics.py, RetrievalEvaluator, ReportGenerator
│   └── utils/             # logging, I/O helpers
├── releases/              # Immutable, checksummed v2/v3 experiment releases
├── experiments/           # Runnable experiment scripts
│   ├── build_dataset.py   # Ingest → clean → chunk (corpus stage only)
│   ├── run_faiss.py       # FAISS dense retrieval experiment
│   ├── run_bm25.py        # BM25 sparse retrieval experiment
│   ├── run_graphrag.py    # Entity-Co-occurrence Graph Retrieval (legacy filename)
│   ├── run_structured_graph.py  # Gated P3 structured-metadata graph experiment
│   └── compare_retrievers.py  # Cross-retriever comparison + reports
├── tests/                 # Isolated unit/integration tests (pytest)
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

# 2. Acquire the frozen authoritative source snapshot (only if absent)
python scripts/download_corpus.py

# 3. Build, independently reproduce, verify, then atomically publish v3_clean
make release-v3-clean

# 4. Verify immutable releases without rebuilding
python scripts/release_manifest.py \
  --base-dir releases/v3_clean \
  --include-root releases/v3_clean/data \
  --include-root releases/v3_clean/indexes \
  --include-root releases/v3_clean/runs \
  --include-root releases/v3_clean/configs \
  --include-root releases/v3_clean/manifests \
  --manifest releases/v3_clean/manifests/release_manifest.jsonl \
  --sums releases/v3_clean/manifests/SHA256SUMS --verify
make verify-v2-baseline
```

Or use the Makefile:

```bash
make install        # pip install
make spacy-model    # download en_core_web_sm
make all                    # alias for the gated v3 release
make release-corpus         # staged corpus only
make release-indexes        # staged corpus + build-only indexes
make release-benchmark      # add graph-backed 60+40 benchmark
make release-evaluate       # evaluate only staged immutable paths
make release-statistics     # add corpus/graph statistics
make release-verify         # deterministic rebuild, checksums, atomic publish
make test                   # complete test suite
```

---

## Query Categories (Benchmark Stratification)

| Category | Description | Hypothesis |
|---|---|---|
| `exact_match` | Exact fact lookup | BM25 leads (H1) |
| `terminology_heavy` | Acronym / technical term | BM25 leads (H1) |
| `paraphrase` | Semantically paraphrased | FAISS leads (H2) |
| `entity_relation` | Entity relationship questions | Entity graph leads (H3) |
| `multi_hop` | Requires evidence from ≥2 chunks | Entity graph leads (H3) |

---

## Evaluation Metrics

- **MRR** — Mean Reciprocal Rank
- **Recall@k** — k ∈ {1, 3, 5, 10}
- **nDCG@k** — Normalised Discounted Cumulative Gain
- **Precision@k**
- **Latency (ms)** — avg per query

All metrics are computed per-retriever **and** per-query-category for sliced analysis.

---

## Artifact lineage

The source registry and frozen raw snapshot retain their historical `v2` filenames. Corpus
release labels describe processed content and must not be inferred from those source filenames.

| Release | Purpose | Documents | Chunks | Queries | Qrels | Status |
|---|---|---:|---:|---:|---:|---|
| `v2_serialized` | Historical serialized-JSON/noisy baseline | 120 | 1,074 | 100 | 140 | Immutable archive; missing historical config fields are explicitly marked unknown |
| `v3_clean` | Canonical deterministic human-text baseline | 130 | 856 | 100 | 140 | Released and canonical |

`releases/CURRENT` points to `v3_clean`. Each release contains matching data, indexes, runs,
reports, configuration evidence, a release record, and a complete SHA-256 manifest. Canonical
compatibility paths are updated only after every staging gate succeeds. The v3 build uses the
established 512-word chunks with 64-word overlap and a pinned MiniLM revision. It rejects corpus
or benchmark publication on count, provenance, leakage, qrel, index-cardinality, or chunk-ID
alignment failures.

The corpus builder does not generate QA or run retrieval. Index builders support `--build-only`;
the benchmark builder consumes the staged graph; the evaluator receives explicit released paths.
The full pipeline performs a second independent build and byte-compares deterministic artifacts
before atomic publication.

## Benchmark-review gate

The 100-query benchmark is exploratory until its manual P1 audit is completed. The audit packet
is generated under `audits/v3_clean/` and contains 60 selected question rows plus the deduplicated
top-3 pool from all three baselines. Automatic evidence/ID checks currently pass, but the files
remain explicitly `pending_human_review`; this is not represented as completed annotation.

```bash
python scripts/finalize_question_audit.py \
  --reviewed-questions audits/v3_clean/question_audit_60.csv \
  --output audits/v3_clean/question_audit_completion.json

python scripts/finalize_qrels_audit.py \
  --original-qrels releases/v3_clean/data/qrels/qrels_v3_clean.tsv \
  --reviewed-pool audits/v3_clean/pooled_top3_judgments.csv \
  --output-dir audits/v3_clean/completed
```

Development model selection, structured-graph ablations, RRF, reranking, and routing all fail
closed until the audit completion records exist. Model selection accepts only `split=dev`.
Holdout execution additionally requires a pre-visibility source/config hash lock. No P2–P5
experiment has been run as part of the baseline release.

Current audit outputs:

- `data/metadata/acquisition_audit_v2.jsonl`
- `data/metadata/deduplication_report_v3_clean.jsonl`
- `data/metadata/qa_validation_stats_v3_clean.json`
- `data/metadata/cross_scheme_audit_v3_clean.jsonl`
- `data/metadata/corpus_statistics_v3_clean.json`
- `releases/v3_clean/manifests/release_manifest.jsonl`

## Graph-system terminology

The implemented graph baseline is **Entity-Co-occurrence Graph Retrieval**: spaCy entity
extraction, entity/chunk co-occurrence edges, and bounded graph traversal. Legacy Python class,
config, and artifact keys retain `graphrag` only for compatibility. This system is not Microsoft
GraphRAG: it has no LLM relationship extraction, community detection, community summaries, or
global/local GraphRAG query modes.

---

## Working Hypotheses

- **H1** BM25 competitive on exact-match and terminology-heavy queries
- **H2** FAISS strong on paraphrased / semantic queries
- **H3** Entity-Co-occurrence Graph Retrieval outperforms flat retrieval on entity-relation and multi-hop queries
