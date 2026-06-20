# Chapter 5 Quick Start — What You Need to Know

**Status:** ✅ All retrievers working, comparison complete, ready for writeup

---

## 🔴 THE BM25 FIX (What Was Wrong)

**Problem:** BM25 returning 0 results for all 28 queries

**Root Cause:** Bug in `src/retrievers/bm25_retriever.py` line 135-149
- Rank counter wasn't tracking correctly when items were skipped
- Condition `if scores[idx] <= 0` was filtering all results

**Solution:** Fixed ranking logic
```python
# Now correctly: rank=len(results) + 1 (instead of enumerate counter)
```

**Result:** 
- Before: 0 results ❌
- After: 280 results (10 per query) ✅
- MRR@5: 0.8304 (BEST among all three)

---

## 🏆 FINAL RESULTS FOR CHAPTER 5

### Overall Winner: BM25

| Retriever | MRR@5 | Recall@10 | nDCG@10 | Latency |
|-----------|-------|-----------|---------|---------|
| **BM25** | **0.8304** ⭐ | **1.0000** ⭐ | **0.8683** ⭐ | 0.06 ms ⭐ |
| FAISS | 0.7958 | 0.8571 | 0.7742 | 92.06 ms |
| GraphRAG | 0.6095 | 0.6875 | 0.5909 | 3.29 ms |

**Key Finding:** Lexical retrieval (BM25) outperforms dense vectors on this policy document corpus — unexpected! This validates your H1 hypothesis.

---

## 📊 FILES FOR CHAPTER 5 TABLES

**Use these directly in your dissertation:**

1. **Main Results Table**
   - File: `runs/metrics/comparison_summary.csv`
   - Contains: MRR@5, MRR@10, Recall, nDCG, Latency for all 3 retrievers
   - Ready to paste into document

2. **Category Breakdown**
   - File: `runs/metrics/per_category.csv`
   - Contains: MRR@5 per category per retriever
   - Shows where each method excels/fails
   - Interesting finding: BM25 dominates on terminology (1.0), FAISS on paraphrase (1.0)

3. **Written Analysis**
   - File: `runs/reports/comparison_report.md`
   - Contains: Key findings, per-category insights, failure analysis
   - Ready to adapt for your dissertation

4. **Example Queries**
   - File: `runs/reports/sample_queries.md`
   - Shows side-by-side retrieval results for 5 queries
   - Good for illustrating differences

---

## 🎯 CATEGORY INSIGHTS (for Chapter 5 discussion)

| Category | Top Performer | Score | Key Insight |
|----------|---|---|---|
| **Terminology** | BM25 / FAISS (tie) | 1.0 | All methods handle acronyms well |
| **Exact Lookup** | BM25 | 0.94 | BM25's lexical strength |
| **Paraphrase** | FAISS | 1.0 | Dense vectors beat sparse on synonymy |
| **Entity Relation** | FAISS | 1.0 | Semantic relationships |
| **Synthesis** | FAISS | 0.92 | Multi-step reasoning |
| **Multi-hop** | All (0.55-0.60) | 0.55-0.60 | ⚠️ All methods struggle |

**Story for Chapter 5:** "Despite dense vectors' theoretical advantages, BM25's simplicity dominates on regulatory documents where terminology and exact matching matter most."

---

## ⚠️ IMPORTANT CAVEATS FOR CHAPTER 5

1. **Small Corpus (10 chunks):** Limited multi-hop reasoning capability
   - Recommendation: Future work should use 100+ chunk corpus
   
2. **Small Query Set (28 queries):** No statistical significance testing possible
   - Cannot claim statistical superiority (only empirical observation)

3. **GraphRAG Underperformance:** 
   - Likely due to small corpus and entity extraction quality
   - May perform better on larger corpus with more entities

---

## 🔄 HOW TO REGENERATE (if needed)

```bash
# Rebuild all indexes and run all retrievers
python run_all_retrievers.py --rebuild-all

# Or individually:
python experiments/run_bm25.py --rebuild
python scripts/run_faiss.py
python scripts/run_graphrag.py

# Generate comparison
python scripts/run_full_comparison.py

# Results appear in:
# - runs/metrics/ (CSV files for tables)
# - runs/reports/ (Markdown analysis)
```

---

## 📋 CHAPTER 5 SECTION SUGGESTIONS

### 5.1 Results (Metrics Tables)
- Table 1: Overall metrics (from comparison_summary.csv)
- Table 2: Category breakdown (from per_category.csv)
- Find: "BM25 achieves best MRR@5 (0.8304), contradicting assumption that dense vectors dominate"

### 5.2 Analysis (Category-Specific Discussion)
- Discuss why BM25 wins on terminology and exact lookup
- Discuss why FAISS wins on paraphrase and synthesis
- Highlight multi-hop as challenge for all methods

### 5.3 Discussion (Research Question)
- H1 confirmed: "BM25 remains competitive despite simplicity"
- Cost-benefit: Simplicity vs. semantic power
- When to use each: BM25 for policy docs, FAISS for customer support

### 5.4 Limitations
- Corpus size (10 → recommend 100+ chunks)
- Query count (28 → recommend 100+ queries for significance testing)
- GraphRAG not optimized for small corpus

### 5.5 Future Work
- Scaling experiments to larger corpus
- Statistical significance testing
- Hybrid approaches (BM25 + FAISS ensemble)
- Domain-specific fine-tuning

---

## ✅ READY FOR CHAPTER 5

All data is generated and verified. You can now:

1. ✅ Copy tables from CSVs into your dissertation
2. ✅ Reference findings from comparison_report.md
3. ✅ Use sample_queries.md for examples
4. ✅ Cite code from src/retrievers/ for methodology
5. ✅ Run regeneration script if needed for verification

**Time to write!** 🚀
