# Dissertation Diagrams - Complete Reference Guide

## Overview

This directory contains 7 comprehensive Mermaid diagrams that visualize every aspect of the RAG retrieval dissertation system. Each diagram includes detailed subgraphs showing key parameters, configurations, and performance characteristics without cluttering the main data flow.

---

## Diagram Listing

### Figure 1: Overall System Architecture
**File:** `fig1_overall_architecture.md`

**Purpose:** High-level view of the entire system pipeline from raw corpus to final results.

**Key Components:**
- Raw corpus ingestion and preprocessing
- Three retrieval pathways (BM25, FAISS, GraphRAG)
- Query loading and execution
- Evaluation framework
- Output generation

**New Addition:** Three independent subgraphs showing parameters for each retriever without connections to the main flow:
- ⚙️ FAISS Key Parameters & Details (8 nodes)
- ⚙️ BM25 Key Parameters & Details (8 nodes)
- ⚙️ GraphRAG Key Parameters & Details (8 nodes)

**When to Use:**
- Chapter 5 introduction/methodology section
- System overview slides
- Architecture documentation

---

### Figure 2: FAISS Dense Retrieval Pipeline
**File:** `fig2_faiss_pipeline.md`

**Purpose:** Detailed walkthrough of FAISS dense vector retrieval process.

**Key Components:**
- Document chunking and embedding
- FAISS index building
- Query embedding and similarity search
- Score conversion and ranking

**New Addition:** Comprehensive subgraph with 5 major sections:
- Model Architecture (384-dim, MiniLM-L6-v2, 22.7M params)
- Index Settings (IndexFlatL2, L2 distance, exact search)
- Search Behavior (Brute force, O(d×n) complexity)
- Performance Metrics (0.79 MRR@5, 0.8571 Recall@10)
- Strengths & Limitations (Semantic matching vs. slow speed)

**Parameters Displayed:**
- Embedding dimension: 384
- Model: all-MiniLM-L6-v2
- Latency: ~92 ms/query
- MRR@5: 0.7958 (2nd place)

**When to Use:**
- Chapter 3.2 Methodology (FAISS implementation)
- Dense retrieval explanation
- Embedding model details

---

### Figure 3: BM25 Lexical Retrieval Pipeline
**File:** `fig3_bm25_pipeline.md`

**Purpose:** Detailed walkthrough of BM25 sparse lexical retrieval process.

**Key Components:**
- Document tokenization and inverted index building
- Index storage (pickle format)
- Query tokenization
- BM25 score computation
- Ranking and result return

**New Addition:** Comprehensive subgraph with 6 major sections:
- Algorithm Specification (Okapi BM25, pure Python, rank-bm25 library)
- Core Parameters (k1=1.5, b=0.75 with detailed explanations)
- Indexing Details (Inverted index, pickle storage, 2KB size)
- Performance Metrics (0.06 ms latency ⭐, 0.8304 MRR@5 BEST)
- Category Performance (Excellent on 2 categories, Fair on 1, Weak on 1)
- Strengths & Limitations (Fast, interpretable vs. no semantics)

**BM25 Formula Included:**
```
BM25(q, d) = Σ IDF(q_i) × (f(q_i,d) × (k1+1)) / 
             (f(q_i,d) + k1 × (1-b + b × |d|/avgdl))
```

**Parameters Displayed:**
- k1: 1.5 (tunable)
- b: 0.75 (tunable)
- Latency: ~0.06 ms/query (1500× faster than FAISS)
- MRR@5: 0.8304 (⭐ WINNER)

**When to Use:**
- Chapter 3.1 Methodology (BM25 implementation)
- Baseline retrieval comparison
- Algorithm parameter tuning discussion

---

### Figure 4: GraphRAG Entity-Aware Retrieval Pipeline
**File:** `fig4_graphrag_pipeline.md`

**Purpose:** Detailed walkthrough of GraphRAG entity-based retrieval with knowledge graphs.

**Key Components:**
- Entity extraction (standard NER + domain-specific regex)
- Knowledge graph construction (NetworkX)
- Graph persistence
- Query entity extraction
- 2-hop graph traversal
- Chunk scoring and ranking

**New Addition:** Comprehensive subgraph with 6 major sections:
- NER & Entity Extraction (12 entity types detailed)
- Graph Structure (DiGraph, node types, edge types)
- Retrieval Algorithm (6-step process from extraction to scoring)
- Performance Metrics (3.29ms latency, 0.6095 MRR@5)
- Category Performance Analysis (Good, Fair, and Weak categories)
- Strengths & Limitations (Entity relationships vs. small corpus issues)

**Entity Types (12 total):**
- Standard (6): PERSON, ORG, GPE, MONEY, DATE, LAW
- Domain (5): SCHEME_NAME, AMOUNT, BENEFICIARY, ELIGIBILITY, DOCUMENT

**Parameters Displayed:**
- NER Tool: spaCy
- Entity types: 12 total
- Traversal depth: 2-hop
- Latency: ~3.29 ms/query
- MRR@5: 0.6095 (3rd place)

**When to Use:**
- Chapter 3.3 Methodology (GraphRAG implementation)
- Entity extraction and knowledge graphs
- Graph-based retrieval explanation

---

### Figure 5: Evaluation Framework
**File:** `fig5_evaluation_framework.md`

**Purpose:** Complete evaluation pipeline from run files to final reports.

**Key Components:**
- Loading run files, qrels, and QA dataset
- Metric computation (per-query, aggregate, per-category)
- Output file generation (CSV and Markdown)
- Analysis and report generation

**New Additions:** Three independent subgraphs:

1. **📊 Evaluation Metrics Specification** (4 metrics detailed)
   - MRR: Formula, range, interpretation, use case
   - Recall@k: Formula, range, interpretation, use case
   - nDCG@k: Formula breakdown, range, interpretation, use case
   - Latency: Unit, meaning, baseline values

2. **🏷️ Query Categories (6 types)** (6 detailed categories)
   - Exact Lookup: Definition, example, best performer
   - Terminology: Definition, example, best performer
   - Paraphrase: Definition, example, best performer
   - Entity Relation: Definition, example, best performer
   - Synthesis: Definition, example, best performer
   - Multi-hop: Definition, example, best performer (all struggle)

3. **📁 Output Files & Formats** (4 output files)
   - comparison_summary.csv: Format, rows, columns, use
   - per_category.csv: Format, rows, columns, use
   - comparison_report.md: Format, sections, purpose, use
   - sample_queries.md: Format, content, purpose, use

**When to Use:**
- Chapter 5.3 Evaluation Methodology
- Metrics definition section
- Query category explanation

---

### Figure 6: Comprehensive Retriever Comparison (NEW)
**File:** `fig6_retriever_comparison.md`

**Purpose:** Side-by-side detailed comparison of all three retrieval systems.

**Key Features:**
- Three major subgraphs: BM25, FAISS, GraphRAG
- Each subgraph contains 10 detailed sections
- One subgraph for comparison matrix

**BM25 Subgraph (10 sections):**
- Algorithm, Index Construction, Query Processing
- Parameters, Performance, Metrics
- Strengths, Weaknesses, Best For Categories, Use Cases

**FAISS Subgraph (10 sections):**
- Algorithm, Index Construction, Query Processing
- Parameters, Performance, Metrics
- Strengths, Weaknesses, Best For Categories, Use Cases

**GraphRAG Subgraph (10 sections):**
- Algorithm, Index Construction, Query Processing
- Parameters, Performance, Metrics
- Strengths, Weaknesses, Best For Categories, Use Cases

**Comparison Matrix (8 dimensions):**
- Speed (Winner: BM25, 1500× faster)
- Accuracy MRR@5 (Winner: BM25, 0.8304)
- Semantic Quality (Winner: FAISS, handles paraphrase)
- Interpretability (Winner: BM25, see exact matches)
- Resource Efficiency (Winner: BM25, no GPU)
- Multi-hop Reasoning (Tied: All struggle, max 0.61)
- Entity Relationships (Winner: FAISS, 0.6067-1.0000)
- Scalability (Winner: FAISS, handles large corpus)

**Strategic Recommendations:**
- For policy/regulatory documents: BM25
- For semantic/customer search: FAISS
- For entity-centric apps: Hybrid (BM25 + FAISS)
- Current dataset (10 chunks): BM25 is optimal
- Scaled dataset (100+ chunks): FAISS becomes attractive

**When to Use:**
- Chapter 5.2 Comparative Analysis
- Retrievers side-by-side comparison
- Strategic decision-making discussion

---

### Figure 7: Complete System Details (NEW)
**File:** `fig7_complete_system_details.md`

**Purpose:** Comprehensive end-to-end system with all detailed parameters and configurations.

**Key Sections:**
1. Input Layer: Corpus (10 chunks) + Queries (28 QA pairs)

2. Shared Preprocessing (4 steps)
   - Text extraction
   - Text cleaning
   - Chunking (300-word windows)
   - Metadata enrichment

3. Three Parallel Indexing Pipelines
   - **BM25:** Tokenize → Build inverted index → Store pickle
   - **FAISS:** Embed → Build FAISS index → Store binary
   - **GraphRAG:** Extract entities → Build graph → Store JSON

4. Three Parallel Query Execution Pipelines
   - **BM25:** Tokenize → Compute scores → Rank (280 results)
   - **FAISS:** Embed → Distance calculation → Rank (140 results)
   - **GraphRAG:** Extract entities → Find nodes → 2-hop traverse → Score (131 results)

5. Evaluation Layer
   - Load qrels (ground truth)
   - Compute per-query metrics
   - Aggregate metrics
   - Per-category analysis
   - Generate reports

6. Results Output
   - comparison_summary.csv
   - per_category.csv
   - comparison_report.md
   - sample_queries.md

**Details Included:**
- File names and sizes (all index files)
- Processing steps and algorithms
- Performance metrics (latency, accuracy)
- Configuration parameters
- Data formats and structures

**Performance Table:**
| Retriever | Avg Latency | Total (28q) | Bottleneck |
|-----------|------------|-----------|-----------|
| BM25 | 0.06 ms | 1.7 ms | None |
| FAISS | 92 ms | 2.6 sec | Embedding |
| GraphRAG | 3.29 ms | 92 ms | NER |

**When to Use:**
- Complete system overview
- Detailed methodology section
- Architecture documentation
- Appendix for full system specification

---

## How to Use These Diagrams

### For Chapter 5 Writing

**Section 5.1 - Results:**
- Use Figure 6 (Comparison) for overview
- Use Figure 5 (Evaluation Framework) for metrics explanation

**Section 5.2 - Category-Specific Analysis:**
- Use Figure 6 (Comparison) for per-category performance
- Use Figure 5 (Query Categories subgraph) for category definitions

**Section 5.3 - Methodology:**
- Use Figures 2, 3, 4 for individual retriever descriptions
- Use Figure 7 for complete system flow
- Use Figure 5 (Evaluation Framework) for evaluation methodology

**Section 5.4 - Discussion:**
- Use Figure 6 (Comparison Matrix) for trade-offs
- Use Figure 1 for system overview

**Section 5.5 - Limitations:**
- Reference parameter details from Figures 2, 3, 4, 7

### For Presentations

- **System Overview:** Use Figure 1 or Figure 7
- **Individual Methods:** Use Figures 2, 3, 4
- **Comparison:** Use Figure 6
- **Evaluation:** Use Figure 5

### For Code Documentation

- Use Figures 2, 3, 4, 7 to explain implementation details
- Reference parameter values from relevant subgraphs

---

## Subgraph Organization

All diagrams follow a consistent pattern:

```
Main Flow → Processing Steps → Outputs
    ↓
Subgraph 1: Configuration Details (no connections)
Subgraph 2: Performance Details (no connections)
Subgraph 3: Analysis Details (no connections)
```

**Subgraph Types:**
- ⚙️ Configuration/Parameters
- 📊 Metrics/Performance
- 🏷️ Categories/Types
- 📁 Output Files
- ✓/✗ Strengths/Weaknesses

---

## Key Parameters at a Glance

### BM25
- k1 = 1.5 (term saturation)
- b = 0.75 (length normalization)
- Latency: 0.06 ms
- MRR@5: 0.8304 ⭐
- Best on: Terminology, Exact Lookup

### FAISS
- Model: all-MiniLM-L6-v2
- Dimensions: 384
- Index: IndexFlatL2 (exact)
- Latency: 92 ms
- MRR@5: 0.7958
- Best on: Paraphrase, Entity Relations

### GraphRAG
- NER: spaCy + domain regex
- Entity Types: 12 total
- Traversal: 2-hop
- Latency: 3.29 ms
- MRR@5: 0.6095
- Best on: Entity Relations

---

## Quick Rendering Tips

All diagrams are written in Mermaid syntax and can be rendered using:
- GitHub (inline in .md files)
- VS Code (with Mermaid extension)
- mermaid.live (online editor)
- Various documentation tools

Recommended viewing approach:
1. View raw Markdown on GitHub (auto-renders)
2. Or use mermaid.live for editing/exporting

---

## Future Enhancements

Potential additions for future iterations:
- Interactive version with clickable nodes
- Performance benchmarks as graphs
- Failure case examples
- Real query traces through system
- Comparison with other RAG systems

---

**Last Updated:** 2026-06-21
**Version:** 1.0
**Status:** Complete with comprehensive subgraphs for all parameters
