# Dissertation Diagrams - Complete Index

Quick access guide to all Mermaid diagrams for your dissertation.

---

## 📊 All Diagrams at a Glance

| # | Diagram | Type | Focus | Status |
|---|---------|------|-------|--------|
| 1 | [fig1_overall_architecture.md](fig1_overall_architecture.md) | System | Corpus → Results pipeline | ✅ Enhanced |
| 2 | [fig2_faiss_pipeline.md](fig2_faiss_pipeline.md) | Method | Dense vector retrieval | ✅ Enhanced |
| 3 | [fig3_bm25_pipeline.md](fig3_bm25_pipeline.md) | Method | Lexical retrieval | ✅ Enhanced |
| 4 | [fig4_graphrag_pipeline.md](fig4_graphrag_pipeline.md) | Method | Entity-aware retrieval | ✅ Enhanced |
| 5 | [fig5_evaluation_framework.md](fig5_evaluation_framework.md) | Evaluation | Metrics & analysis | ✅ Enhanced |
| 6 | [fig6_retriever_comparison.md](fig6_retriever_comparison.md) | Comparison | Side-by-side all 3 methods | ✨ NEW |
| 7 | [fig7_complete_system_details.md](fig7_complete_system_details.md) | Architecture | Full end-to-end with details | ✨ NEW |

---

## 🎯 By Use Case

### For Chapter 5 Writing

**Section 5.1 - Results:**
- [Figure 1](fig1_overall_architecture.md) - System overview
- [Figure 6](fig6_retriever_comparison.md) - Performance comparison

**Section 5.2 - Category-Specific Analysis:**
- [Figure 5](fig5_evaluation_framework.md) - Query categories
- [Figure 6](fig6_retriever_comparison.md) - Per-category breakdown

**Section 5.3 - Methodology:**
- [Figure 2](fig2_faiss_pipeline.md) - FAISS implementation
- [Figure 3](fig3_bm25_pipeline.md) - BM25 implementation
- [Figure 4](fig4_graphrag_pipeline.md) - GraphRAG implementation
- [Figure 5](fig5_evaluation_framework.md) - Evaluation methodology
- [Figure 7](fig7_complete_system_details.md) - Complete system flow

**Section 5.4 - Discussion:**
- [Figure 6](fig6_retriever_comparison.md) - Trade-offs & strategic recommendations

**Section 5.5 - Limitations & Appendix:**
- [Figure 7](fig7_complete_system_details.md) - Parameter specifications

### For Presentations

- **Overview:** [Figure 1](fig1_overall_architecture.md) or [Figure 7](fig7_complete_system_details.md)
- **Methods:** [Figures 2, 3, 4](fig2_faiss_pipeline.md)
- **Comparison:** [Figure 6](fig6_retriever_comparison.md)
- **Evaluation:** [Figure 5](fig5_evaluation_framework.md)

### For Code Documentation

- **System Architecture:** [Figure 7](fig7_complete_system_details.md)
- **Implementation Details:** [Figures 2, 3, 4](fig2_faiss_pipeline.md)
- **Evaluation Pipeline:** [Figure 5](fig5_evaluation_framework.md)

---

## 📚 Reference Guide

**Comprehensive guide:** [DIAGRAM_GUIDE.md](DIAGRAM_GUIDE.md)
- Detailed description of each diagram
- How to use for dissertation writing
- Subgraph organization patterns
- Key parameters at a glance

---

## 🔑 Key Findings Illustrated

### BM25 (Lexical Retrieval)
- **Best Overall:** MRR@5 = 0.8304 ⭐
- **Fastest:** 0.06 ms/query (1500× faster than FAISS)
- **Perfect Recall:** 100% at k=10
- **See in:** [Figure 3](fig3_bm25_pipeline.md), [Figure 6](fig6_retriever_comparison.md)

### FAISS (Dense Vector Retrieval)
- **Semantic Strength:** Handles paraphrase, entities (both 1.0)
- **Accuracy:** MRR@5 = 0.7958 (2nd place)
- **Trade-off:** Slower but more semantic
- **See in:** [Figure 2](fig2_faiss_pipeline.md), [Figure 6](fig6_retriever_comparison.md)

### GraphRAG (Entity-Aware Retrieval)
- **Entity Focus:** 12 entity types (6 standard + 6 domain)
- **Performance:** MRR@5 = 0.6095 (3rd place)
- **Issue:** Underperforms, needs large corpus
- **See in:** [Figure 4](fig4_graphrag_pipeline.md), [Figure 6](fig6_retriever_comparison.md)

---

## 📊 Subgraph Summary

### Figure 1 (Overall Architecture)
3 independent subgraphs showing key parameters for each retriever

### Figure 2 (FAISS)
1 comprehensive subgraph with 5 sections:
- Model Architecture
- Index Settings
- Search Behavior
- Performance Metrics
- Strengths & Limitations

### Figure 3 (BM25)
1 comprehensive subgraph with 6 sections:
- Algorithm Specification
- Core Parameters (k1, b)
- Indexing Details
- Performance Metrics
- Category Performance
- Strengths & Limitations
- Complete BM25 formula

### Figure 4 (GraphRAG)
1 comprehensive subgraph with 6 sections:
- NER & Entity Extraction (12 types)
- Graph Structure
- Retrieval Algorithm (6-step process)
- Performance Metrics
- Category Performance
- Strengths & Limitations

### Figure 5 (Evaluation Framework)
3 independent subgraphs:
- Metrics Specification (MRR, Recall@k, nDCG@k)
- Query Categories (6 types defined)
- Output Files (4 file formats)

### Figure 6 (Comprehensive Comparison)
4 major subgraphs:
- BM25 System (10 sections)
- FAISS System (10 sections)
- GraphRAG System (10 sections)
- Comparison Matrix (8 dimensions)

### Figure 7 (Complete System Details)
6 sections with detailed information:
- Input Layer
- Shared Preprocessing
- 3 Parallel Indexing Pipelines
- 3 Parallel Query Execution Pipelines
- Evaluation Layer
- Results Output

---

## 🎨 How These Diagrams Are Structured

**Pattern:** Main Flow + Parameter Subgraphs (No Connections)

```
Input ──→ Processing ──→ Output
                          ↓
                 ┌─────────────────┐
                 │ Subgraph Config │  ← Details (isolated)
                 │ ├─ Parameter 1  │    - Easy to read
                 │ ├─ Parameter 2  │    - No visual clutter
                 │ └─ Parameter 3  │    - Quick reference
                 └─────────────────┘
```

**Benefits:**
- Main flow stays clean and readable
- Parameters easy to find and understand
- Can be copy-pasted to dissertation
- Suitable for presentations

---

## 📝 File Sizes & Complexity

| Diagram | File | Size | Nodes | Complexity |
|---------|------|------|-------|-----------|
| Fig 1 | 2.5 KB | 25 | Low-Med |
| Fig 2 | 3.2 KB | 30 | Medium |
| Fig 3 | 4.8 KB | 40 | Medium-High |
| Fig 4 | 4.2 KB | 35 | Medium-High |
| Fig 5 | 4.5 KB | 35 | Medium |
| Fig 6 | 12+ KB | 100+ | High (comprehensive) |
| Fig 7 | 15+ KB | 120+ | High (detailed) |

---

## 🔄 Rendering

All diagrams use **Mermaid** syntax and can be rendered by:

1. **GitHub** - Automatic rendering in Markdown
2. **VS Code** - With Mermaid extension
3. **mermaid.live** - Online editor (mermaid.live)
4. **Various tools** - Any Mermaid-compatible tool

**Recommended:** View directly on GitHub for best results

---

## ✨ What's New vs. Original

### Original Version (5 diagrams)
- Basic flow diagrams
- Minimal parameter detail
- Limited to core concepts

### Enhanced Version (7 diagrams + guide)
- **All 5 diagrams enhanced** with detailed subgraphs
- **2 new comprehensive diagrams** (Fig 6 & 7)
- **Complete reference guide** (DIAGRAM_GUIDE.md)
- **All key parameters visible**
- **No main flow clutter**
- **Ready for dissertation**
- **Better for presentations**

---

## 🚀 Quick Start

1. **Start here:** [DIAGRAM_GUIDE.md](DIAGRAM_GUIDE.md) for complete reference
2. **For Chapter 5:** Use [Figure 6](fig6_retriever_comparison.md) for overview
3. **For Methods:** Use [Figures 2, 3, 4](fig2_faiss_pipeline.md) for details
4. **For Complete Flow:** Use [Figure 7](fig7_complete_system_details.md) for end-to-end
5. **For Evaluation:** Use [Figure 5](fig5_evaluation_framework.md) for metrics

---

## 📌 Key Parameters at a Glance

**BM25:**
- k1 = 1.5 | b = 0.75
- Latency: 0.06 ms
- MRR@5: 0.8304 ⭐

**FAISS:**
- all-MiniLM-L6-v2 | 384-dim
- Latency: 92 ms
- MRR@5: 0.7958

**GraphRAG:**
- 12 entity types | 2-hop traversal
- Latency: 3.29 ms
- MRR@5: 0.6095

---

## 📞 For Questions

Refer to [DIAGRAM_GUIDE.md](DIAGRAM_GUIDE.md) for:
- Detailed explanations of each diagram
- When to use each one
- How to integrate into dissertation
- Subgraph organization patterns

---

**Last Updated:** 2026-06-21  
**Version:** 1.0  
**Status:** Complete ✅  
**Ready for Chapter 5:** Yes ✅
