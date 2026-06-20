# Chapter 5: Results, Analysis & Conclusions — Assets & Deliverables

**Last Updated:** 2026-06-21

---

## 📊 KEY FINDINGS (Summary for Chapter 5)

### Overall Performance Rankings (MRR@5)
1. **BM25: 0.8304** (Best) — Lexical retrieval dominates on this dataset
2. **FAISS: 0.7958** — Dense vectors strong but slower
3. **GraphRAG: 0.6095** — Entity-based approach underperforms

### Category-Specific Insights
| Category | Best Retriever | Score | Insight |
|----------|---|---|---|
| **Terminology** | BM25 / FAISS / GraphRAG | 1.0000 | All methods excel on acronym-heavy queries (PM-KISAN, PMAY, etc.) |
| **Exact Lookup** | BM25 | 0.9444 | Lexical matching superior for explicit entity questions |
| **Entity Relation** | FAISS | 1.0000 | Dense embeddings capture implicit relationships |
| **Paraphrase** | FAISS / BM25 | 1.0000 | Dense vectors handle synonymy; BM25 fails (0.2667 for GraphRAG) |
| **Synthesis** | FAISS | 0.9167 | Multi-step reasoning benefits from semantic similarity |
| **Multi-hop** | FAISS | 0.6067 | All methods struggle; requires explicit linking |

---

## 📁 CHAPTER 5 DATA FILES & OUTPUTS

### A. Primary Results Files (for Chapter 5 tables & figures)

```
runs/metrics/
├── comparison_summary.csv           ← Overall metrics (MRR@5, MRR@10, Recall, nDCG, latency)
└── per_category.csv                 ← Per-category breakdown (MRR@5 by retriever × category)

runs/reports/
├── comparison_report.md             ← Markdown report with key findings
└── sample_queries.md                ← Side-by-side retrieval results for 5 sample queries
```

**Status:** ✅ Generated (2026-06-21 02:41:59)

---

### B. Retriever Output Files (Evidence for analysis)

```
runs/retrieval/
├── bm25_run.jsonl                   ← 28 queries × 10 results (280 total) — NOW FIXED ✅
├── faiss_run.jsonl                  ← 28 queries × 5 results (140 total)
├── faiss_run.tsv                    ← TREC format (optional, for external eval tools)
├── graphrag_run.jsonl               ← 28 queries × 4.67 avg results (131 total)
└── graphrag_run.tsv                 ← TREC format
```

**Status:** ✅ Complete (all three retrievers working)

---

### C. Ground Truth & Dataset Files

```
data/queries/
├── qa_dataset_v1.jsonl              ← 28 questions with category tags (6 categories)
└── query_categories.md              ← Category definitions

data/qrels/
├── qrels.tsv                        ← Relevance judgments (TREC format)
└── evidence_map.json                ← Chunk-to-query relevance mapping (JSON)

data/chunks/
└── chunks_v1.jsonl                  ← 10 policy document chunks (corpus)
```

**Status:** ✅ Complete

---

### D. Indexes (Built & Cached)

```
indexes/
├── faiss/
│   ├── faiss.index                  ← FAISS dense index
│   └── chunk_ids.json               ← Chunk metadata
├── bm25/
│   └── bm25_index.pkl               ← BM25 sparse index (rebuilt 2026-06-21)
└── graphrag/
    └── chunk_lookup.json            ← GraphRAG entity index
```

**Status:** ✅ Complete (BM25 rebuilt & verified)

---

## 🔧 HOW BM25 WAS FIXED

### The Problem
- **Symptom:** BM25 returning empty results for all 28 queries
- **Root Cause:** Two issues in `src/retrievers/bm25_retriever.py:retrieve()`:
  1. **Rank tracking bug:** Used `rank=rank` (enumerate counter) which incremented even when items were skipped
  2. **Score filtering:** Condition `if scores[idx] <= 0: continue` was too strict

### The Fix
```python
# Before (broken):
for rank, idx in enumerate(ranked, start=1):
    if scores[idx] <= 0:
        continue
    results.append(... rank=rank ...)  # ← rank is stale!

# After (fixed):
for actual_rank, idx in enumerate(ranked, start=1):
    score = scores[idx]
    if score < 0:
        continue
    results.append(... rank=len(results) + 1 ...)  # ← correct position
```

**Impact:**
- Before: `28 queries | 0 with results | 0% coverage`
- After: `28 queries | 28 with results | 100% coverage`
- Retrieval Quality: MRR@5 = 0.8304 (BEST among three)

---

## 📋 FILES NEEDED FOR CHAPTER 5 WRITEUP

### 1. Metrics Tables (for Results section)
- ✅ `runs/metrics/comparison_summary.csv` — Main results table
- ✅ `runs/metrics/per_category.csv` — Category breakdown

### 2. Analysis & Findings
- ✅ `runs/reports/comparison_report.md` — Key findings & failure analysis
- ✅ `runs/reports/sample_queries.md` — Qualitative examples

### 3. Methodology Documentation
- ✅ `FINAL_COMPILED_MIDSEM_REPORT.md` — Chapters 1-4 (background)
- ✅ `data/queries/query_categories.md` — Query category definitions
- ✅ `QUALITY_ANALYSIS.md` — Data quality notes

### 4. Configuration & Setup (for reproducibility)
- ✅ `configs/retrieval.yaml` — Retriever hyperparameters
- ✅ `requirements.txt` — Dependencies (rank-bm25, faiss-cpu, etc.)

### 5. Code References (for methodology)
```
src/
├── retrievers/
│   ├── bm25_retriever.py            ← Implementation (line 123-150: retrieve() method)
│   ├── faiss_retriever.py           ← Implementation
│   └── graph_retriever.py           ← Implementation
└── evaluation/
    ├── evaluator.py                 ← Metric computation
    └── metrics.py                   ← MRR, Recall@k, nDCG@k definitions
```

---

## 🎯 SUGGESTED CHAPTER 5 OUTLINE

### 5.1 Results
- Table: Overall metrics (comparison_summary.csv)
- Table: Per-category breakdown (per_category.csv)
- Figure: Category heatmap (can generate from per_category.csv)
- Finding: BM25 outperforms despite simplicity

### 5.2 Analysis
- **Lexical vs. Dense Trade-off:** BM25 (0.83) vs FAISS (0.79)
  - BM25 advantage: terminology, exact lookup, interpretation
  - FAISS advantage: paraphrase, entity relations, synthesis
  
- **Per-Category Insights:**
  - GraphRAG struggles with paraphrase (0.27) despite entity-aware approach
  - FAISS excels at semantic tasks (1.0 on paraphrase, terminology)
  - BM25 dominance on multi-token acronyms (PM-KISAN, PMJAY, etc.)

- **Latency Trade-off:**
  - BM25: 0.06 ms (fastest)
  - GraphRAG: 3.29 ms
  - FAISS: 92.06 ms (slowest, ~1500× slower than BM25)

### 5.3 Failure Analysis
- Multi-hop reasoning (all methods struggle, max MRR=0.60)
  - Cause: Corpus only 10 chunks; multi-document reasoning limited
  
- GraphRAG underperformance (0.61 overall)
  - Hypothesis: Graph construction loses signal on small corpus
  - Recommendation: Test on larger corpus (100+ chunks)

### 5.4 Conclusions
- **H1 (Research Hypothesis):** "BM25 remains competitive" — ✅ CONFIRMED
- **Key Trade-off:** Simplicity (BM25) vs. Semantic Power (FAISS)
- **Practical Recommendation:** Domain-dependent
  - Use BM25 for policy/regulatory documents (terminology-heavy)
  - Use FAISS for customer support / semantic search
  - Hybrid approach for multi-hop reasoning

### 5.5 Future Work & Limitations
- Corpus too small (10 chunks) for reliable multi-hop evaluation
- GraphRAG requires tuning of entity extraction parameters
- No statistical significance testing (due to small dataset)
- Recommend: Repeat on 200+ chunk corpus with 100+ queries

---

## 🚀 HOW TO REGENERATE RESULTS

### Quick Regeneration (all three retrievers)
```bash
# BM25: Rebuild index and run
python run_all_retrievers.py --rebuild-all --top-k 10

# FAISS: (already has latest results)
python scripts/run_faiss.py

# GraphRAG: (already has latest results)
python scripts/run_graphrag.py

# Generate comparison
python scripts/run_full_comparison.py
```

### Or use the individual scripts
```bash
python experiments/run_bm25.py --rebuild --top-k 10
python scripts/run_faiss.py
python scripts/run_graphrag.py
python scripts/run_full_comparison.py
```

---

## 📝 SUMMARY STATISTICS FOR CHAPTER 5

| Metric | BM25 | FAISS | GraphRAG |
|--------|------|-------|----------|
| **Queries** | 28 | 28 | 28 |
| **Avg Results/Query** | 10.0 | 5.0 | 4.68 |
| **MRR@5** | 0.8304 | 0.7958 | 0.6095 |
| **Recall@10** | 1.0000 | 0.8571 | 0.6875 |
| **nDCG@10** | 0.8683 | 0.7742 | 0.5909 |
| **Avg Latency (ms)** | 0.06 | 92.06 | 3.29 |
| **Best Category** | Terminology | Paraphrase | Entity-Relation |
| **Worst Category** | Multi-hop (0.55) | Multi-hop (0.61) | Paraphrase (0.27) |

---

## ✅ VERIFICATION CHECKLIST FOR CHAPTER 5

- [x] All 3 retrievers producing results
- [x] Metrics computed (MRR@5, MRR@10, Recall@k, nDCG@k)
- [x] Per-category breakdown complete
- [x] BM25 fixed and verified (working 100% → 28/28 queries)
- [x] Comparison report generated
- [x] Sample queries documented
- [x] Reproducibility: Scripts and configs available

---

**Ready for Chapter 5 writeup!** 🎉

All data, code, and analysis are in place. Focus on:
1. Tables from CSV files (comparison_summary.csv, per_category.csv)
2. Interpretation of per-category patterns
3. Discussion of BM25's surprising strength
4. Limitations of small corpus (10 chunks, 28 queries)
5. Practical recommendations for practitioners
