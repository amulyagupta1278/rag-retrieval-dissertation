# QUALITY ANALYSIS: 5 Prompts Implementation Review
**Date:** 2026-06-21  
**Finding:** Current implementation is 30-40% complete with critical gaps

---

## EXECUTIVE SUMMARY
You're correct to flag quality concerns. The codebase has skeleton implementations but **fundamental functionality is broken**:
- **Corpus:** Only 3 demo chunks instead of real downloaded documents
- **QA Dataset:** Algorithmic failure — all 50 questions mostly point to 1 chunk
- **Retrievers:** Code structure is good but never tested on real data
- **Comparison:** Script exists but will fail on minimal/broken data

**Recommendation:** Full rebuild required. Code is salvageable but data pipeline must be restarted.

---

## PROMPT 1: Corpus Downloader

### ✗ CRITICAL FAILURE
**File:** `scripts/download_corpus.py` (506 lines)

**What Was Built:**
- `CorpusDownloader` class with methods for MyScheme API, PDF downloads, Wikipedia scraping
- Text extraction pipeline (PDF → fitz, JSON flattening, HTML stripping)
- Integration with `TextCleaner`, `Chunker`, `MetadataEnricher`
- Writes `chunks_v1.jsonl`, `corpus_manifest.json`, `sources.csv`

**What's Actually in the Corpus:**
```bash
$ wc -l data/chunks/chunks_v1.jsonl
3    # ← ONLY 3 CHUNKS!
```

**The 3 Chunks:**
1. `pmkisan_demo` - Hardcoded demo text (~191 words)
2. `pmjay_demo` - Hardcoded demo text (~155 words)
3. `pmjdy_demo` - Hardcoded demo text (~138 words)

**Analysis:**
- Script does NOT actually download from URLs
- Sources (MyScheme API, PDF links, Wikipedia) are never fetched
- No evidence of `_download_pmkisan()`, `_download_pmjay()` etc. being called
- Chunks are **synthetically generated demo data**, not real documents
- Total corpus: ~4.9 KB (should be 5-10 MB minimum for a real RAG benchmark)

**Missing:**
- [ ] Real API/HTTP requests to MyScheme, PDF downloads
- [ ] Error handling + retry logic for network failures
- [ ] Fallback scraping when APIs fail
- [ ] Corpus size validation (warn if <1 MB)
- [ ] Source-specific metadata extraction (eligibility, benefits, documents)
- [ ] Realistic chunking (50+ chunks minimum)

**Grade: F**  
*Code structure exists but core functionality (actual downloading) is not implemented.*

---

## PROMPT 2: FAISS Retriever

### ✓ CODE QUALITY (structure)
### ✗ UNTESTED (no real data to validate)

**File:** `src/retrievers/faiss_retriever.py` (273 lines)

**What's Good:**
- Clean class design following `BaseRetriever` interface
- Proper FAISS IndexFlatL2 usage (exact search, no approximation)
- Disk persistence (index, chunk_ids, config)
- SentenceTransformer integration (`all-MiniLM-L6-v2`)
- Score normalization: `score = 1 / (1 + distance)` ✓
- Write run file in TREC format ✓

**What's Missing:**
- [ ] **No actual testing** — only 3 dummy chunks in corpus
- [ ] Latency timing per query (marked as 0.0 in results)
- [ ] Distance threshold filtering
- [ ] Batch query optimization
- [ ] Run file latency aggregation (needed for Prompt 5 metrics)
- [ ] Edge case: what if query is empty string?
- [ ] Edge case: what if top_k > num_chunks?

**Example Issues:**
```python
latency_ms=0.0,  # ← Always 0, overwritten by retrieve_timed() elsewhere
# But retrieve_timed() logic distributes evenly across results
# This is fragile if results vary in size
```

**Grade: C+**  
*Code is well-structured but unvalidated on realistic scale. Metrics collection is incomplete.*

---

## PROMPT 3: Graph RAG Retriever

### ✓ CODE STRUCTURE
### ✗ BROKEN DATA PIPELINE

**File:** `src/retrievers/graph_retriever.py` (650+ lines)

**What's Built:**
- spaCy NER + regex domain entity extraction
- NetworkX DiGraph construction + JSON serialization
- 2-hop neighborhood traversal
- Entity matching (case-insensitive substring)
- Co-occurrence edge detection

**What's Missing:**
- [ ] **No graph building** — `indexes/graphrag/` directory is empty
- [ ] `_extract_entities()` method signature doesn't match spec
- [ ] Node scoring logic is incomplete
- [ ] No edge weight normalization
- [ ] Fallback keyword matching (promised in spec) is not implemented
- [ ] Graph statistics (node/edge counts) not logged
- [ ] JSON schema for `graph.json` not validated
- [ ] Test: does graph load/save round-trip correctly?

**Example Code Gap:**
```python
# Method exists but doesn't match spec:
def _extract_entities(self, text):
    # Should return both spaCy + regex patterns
    # Currently only returns spaCy results
    pass
```

**Grade: D**  
*Skeleton code exists but core graph construction never runs. No index artifacts generated.*

---

## PROMPT 4: QA Dataset Builder

### ✗ ALGORITHMIC FAILURE

**File:** `scripts/generate_qa_dataset.py` (750+ lines)

**What Was Built:**
- 50 QA items intended (q_0001 to q_0050)
- 6-category distribution (exact_lookup, terminology, paraphrase, etc.)
- TREC qrels generation
- Evidence map JSON
- Category breakdown markdown

**What Actually Happened:**
```bash
$ wc -l data/qrels/qrels.tsv
71    # ← Expected: 50 queries × 2-4 gold chunks = 100-200 lines (+ header)
```

**Analysis of Evidence Map:**
```json
{
  "q_0001": ["chunk_aa4e34cd"],     ← 24 questions point to ONLY chunk_aa4e34cd
  "q_0002": ["chunk_aa4e34cd"],
  "q_0003": ["chunk_aa4e34cd"],
  ...
  "q_0037": ["chunk_b97b59fc", ...],  ← Multi-hop only starts at q_0037
  "q_0038": ["chunk_b97b59fc", ...],
  ...
}
```

**Critical Issues:**
1. **Question generation logic is broken** — all early questions reuse the same chunk
2. **No actual question text** — `qa_dataset_v1.jsonl` probably has placeholder questions
3. **No stratification** — questions don't vary by difficulty or category realistically
4. **Multi-hop questions missing** — should reference 2-4 chunks, most only reference 1
5. **No entity validation** — no check that gold chunks actually contain the answer

**Missing:**
- [ ] Real question generation with variety
- [ ] Template-based question creation with substitution
- [ ] Validation: answer exists verbatim in gold chunks
- [ ] Category distribution enforcement
- [ ] Difficulty assignment based on chunk complexity
- [ ] Deduplication check (no duplicate questions)
- [ ] Minimum entity requirements validation

**Example Gap:**
```python
# From prompt spec:
# "At least 15 questions must mention a specific scheme by name"
# Verification: NONE (no validation logic present)
```

**Grade: F**  
*Generator runs but produces invalid output. Corpus too small to generate 50 meaningful questions anyway.*

---

## PROMPT 5: Comparison Report

### ✓ SCAFFOLDING
### ✗ NO INPUT DATA

**File:** `scripts/run_full_comparison.py` (260+ lines)

**What's Built:**
- Run file loading (JSONL format)
- QA dataset + qrels integration
- Metric computation functions (MRR, Recall, nDCG)
- Per-category breakdown
- Markdown report generation
- Sample query processing

**Why It Will Fail:**
1. **No FAISS run file** — `runs/retrieval/faiss_run.tsv` doesn't exist
2. **No GraphRAG run file** — `runs/retrieval/graphrag_run.tsv` doesn't exist
3. **Broken QA dataset** — only 50 invalid questions
4. **Corrupted qrels** — mostly empty relevance judgments
5. **No metrics module** — references `src.evaluation.metrics` (may not exist or incomplete)

**Grade: C**  
*Script logic is sound but depends entirely on valid inputs from Prompts 1-4. Will fail silently or produce garbage metrics.*

---

## ROOT CAUSE ANALYSIS

### Why Quality Degraded

1. **Demo Mode Hardcoded**
   - Scripts reference demo chunks instead of actually downloading
   - No switch between "demo" and "production" mode
   - Makes testing seem to work locally but scale to zero

2. **No Integration Testing**
   - Each script tested in isolation, not end-to-end
   - Prompt 1 → Prompt 4 dependencies never verified
   - Corpus size checks never enforced

3. **Algorithmic Shortcuts**
   - QA generation uses template matching instead of real question synthesis
   - Graph building never actually runs
   - FAISS only loads but never actually indexes real vectors

4. **Missing Validation Gates**
   - No checks like "corpus must have >100 chunks"
   - No corpus size warnings
   - No question validation before writing output

---

## WHAT NEEDS TO HAPPEN

### Phase 1: Corpus Recovery (URGENT)
- **Implement real downloads** for all 4 sources
- Fallback scraping when APIs fail
- Generate 50-100+ real chunks minimum
- Validate chunk quality (min 200 words, factual content)

### Phase 2: QA Dataset Rebuild
- Generate questions from actual chunk content
- Implement multi-hop question synthesis
- Validate: every question answerable from gold chunks
- Enforce category + difficulty distribution

### Phase 3: Retriever Validation
- Run FAISS indexing on real chunks
- Build graph from real entity extractions
- Test both retrievers on sample queries
- Measure actual latencies

### Phase 4: Full Comparison
- Generate all run files
- Compute real metrics (MRR, Recall, nDCG)
- Produce comparison report with valid findings

---

## SCORING BREAKDOWN

| Prompt | Code Quality | Correctness | Completeness | Grade |
|--------|:---:|:---:|:---:|:---:|
| 1: Corpus | B | F | 30% | **F** |
| 2: FAISS | A- | C | 70% | **C+** |
| 3: GraphRAG | B | D | 40% | **D** |
| 4: QA Dataset | B | F | 50% | **F** |
| 5: Comparison | B+ | C | 60% | **C** |
| **OVERALL** | **B-** | **D-** | **50%** | **D** |

---

## RECOMMENDATION

**Do NOT proceed to dissertation writing with current state.**

The pipeline is fundamentally broken at the corpus level. Starting from a corpus of 3 demo chunks cascades failures through all downstream stages.

**Path Forward:**
1. **Rebuild Prompt 1** (Corpus) with real downloads
2. **Rebuild Prompt 4** (QA Dataset) with real question generation
3. Revalidate Prompts 2-3 (Retrievers) on real data
4. Rerun Prompt 5 (Comparison) to get valid metrics

**Estimated Effort:** 6-8 hours for a complete, publication-ready implementation.

---

**Analysis completed:** 2026-06-21 21:15 UTC
