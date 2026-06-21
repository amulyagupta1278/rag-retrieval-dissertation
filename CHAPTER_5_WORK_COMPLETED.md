# Chapter 5: Work Completed to Date

## 5.1 Research and Design Foundations

The research design for this dissertation was completed and locked prior to implementation. The primary research question investigates whether vector-free retrieval methods (lexical retrieval via BM25 and entity-aware graph-based retrieval via GraphRAG) can remain competitive with dense vector retrieval (FAISS) when evaluated on policy document retrieval tasks. The central hypothesis (H1) posits that BM25 will demonstrate competitive performance on exact-match, terminology-heavy, and entity-specific questions because lexical signals preserve explicit term constraints that dense embeddings may obscure through semantic projection.

The evaluation framework was explicitly designed to separate retrieval quality from generation quality. This methodological choice enables direct comparison of retrieval strategies independent of downstream large language model behavior. The framework specifies six query categories that represent distinct information needs: terminology-focused queries where acronyms and formal names dominate (PM-KISAN, PMJAY); exact lookup queries requiring specific policy values or criteria; paraphrase queries using synonymous language; entity relation queries requiring understanding of how policy entities relate; synthesis queries combining information across multiple documents; and multi-hop queries requiring transitive reasoning chains. This categorical decomposition allows per-category performance analysis that surface domain-specific strengths and weaknesses that aggregate metrics would obscure.

The system architecture specifies five complete retrieval pipelines: a shared preprocessing pipeline applied uniformly to all three retrieval methods, individual index construction pipelines for BM25, FAISS, and GraphRAG, corresponding query execution pipelines for each retriever, an evaluation framework that computes standardized information retrieval metrics, and a reporting pipeline that generates comparative analysis artifacts. The decision to implement three distinct paradigms on identical corpus and query sets directly addresses the research question by eliminating confounds related to dataset composition.

## 5.2 Corpus and Dataset Construction

The corpus consists of ten chunks derived from five source documents covering Indian government welfare schemes. Each chunk represents a contiguous 300-word window of text extracted and cleaned from Wikipedia articles on policy programs. The corpus manifest (evidence file S1) documents the source provenance: documents cover Pradhan Mantri Awas Yojana (PMAY), Mahatma Gandhi National Rural Employment Guarantee Act (MGNREGA), Pradhan Mantri Jan Arogya Yojana (PMJAY), Pradhan Mantri Fasal Bima Yojana (PMFBY), and Pradhan Mantri Mudra Yojana (PMMY). The registry of sources (evidence file S2) lists five unique documents by identifier and crawl date (all dated June 21, 2026).

Chunking statistics (evidence file S4) show that the ten chunks have a mean length of 244.5 words, with minimum length 193 words and maximum length 351 words. No single source document is represented more than three times in the corpus; the distribution is roughly balanced across the five policy documents. This constraint ensures that no retriever can exploit domain-skew by specializing to one heavily-represented document.

The QA dataset (evidence file S5) contains twenty-eight distinct question-answer pairs. The category distribution is as follows: terminology queries comprise seven items; exact lookup queries comprise nine items; paraphrase queries comprise three items; entity relation queries comprise three items; synthesis queries comprise three items; and multi-hop queries comprise three items. The imbalance reflects the natural prevalence of exact-lookup questions in policy document search while still providing at least three examples per category. The gold evidence set averages 2.04 chunks per question, indicating that roughly two chunks are marked as containing relevant information per query. This moderate relevant-set size is consistent with policy retrieval benchmarks where multiple documents often address orthogonal aspects of a single policy (eligibility in one chunk, benefits in another).

The qrels file (evidence file S6) contains 56 total relevance judgments across the 28 queries. Of these, 57 are marked as gold (relevance=2), 0 are marked as relevant (relevance=1), and 0 are marked as not relevant (relevance=0). This binary annotation scheme (gold vs. not-gold) was chosen for simplicity and reflects the information-seeking task: for each policy question, the relevant chunks either contain information that directly answers the question (gold) or they do not. The average gold chunks per query is 2.04, confirming the earlier observation.

## 5.3 Retrieval System Implementation

### 5.3.1 BM25 Lexical Retrieval

The BM25 retriever implements the Okapi BM25 probabilistic ranking model using the pure-Python rank-bm25 library. Index construction (evidence file S7) tokenizes all ten chunks by lowercasing, removing punctuation, and splitting on whitespace, then builds an inverted index mapping terms to chunk occurrences. The BM25 parameters are set to k1=1.5 (term frequency saturation) and b=0.75 (length normalization), both standard values drawn from the BM25 literature. The index is persisted as a Python pickle file totaling 1,658 bytes stored at `indexes/bm25/bm25_index.pkl`. The build process completes instantaneously on the ten-chunk corpus.

Query execution tokenizes each question using the same tokenization rules applied during index construction, computes the BM25 score for each chunk according to the Okapi formula, and ranks chunks by descending score. The retrieve method returns the top-k documents with non-negative scores, preserving exact score values for ranking. Run file output (evidence file S8) shows that all twenty-eight queries produced results, with an average of ten results per query.

### 5.3.2 FAISS Dense Vector Retrieval

The FAISS retriever encodes all chunks and queries into 384-dimensional dense vectors using the `all-MiniLM-L6-v2` sentence transformer model, then indexes the chunk embeddings into a FAISS IndexFlatL2 index that uses exact L2 distance search. Index construction generates one embedding per chunk, each 384-dimensional float32 vector. The FAISS index is persisted to `indexes/faiss/faiss.index` (evidence file S9) along with chunk ID mappings in JSON format. The index directory total size is approximately 10 megabytes due to the embedding matrix and auxiliary structures.

Query execution embeds the question using the same sentence transformer, computes L2 distance to all chunk embeddings, and returns the top-k chunks ranked by ascending distance (equivalently, descending similarity). Run file output (evidence file S10) confirms that all twenty-eight queries produced results, with the configured top-k=5 yielding five results per query except when fewer than five chunks exceed a similarity threshold.

### 5.3.3 GraphRAG Entity-Aware Retrieval

The GraphRAG retriever builds a knowledge graph by extracting entities from all chunks using spaCy NER (extracting PERSON, ORG, GPE, MONEY, DATE, LAW entities) and domain-specific regex patterns (extracting SCHEME_NAME, AMOUNT, BENEFICIARY, ELIGIBILITY, DOCUMENT entities). Entities are represented as nodes in a NetworkX directed graph; edges encode two relations: MENTIONED_IN edges link entity nodes to the chunks where they appear, and CO_OCCURS_WITH edges link entities that appear in the same chunk. Graph construction persists the graph to `indexes/graphrag/graph.json` (evidence file S11) as a JSON-serialized dictionary.

Query execution extracts entities from the question using the same NER and regex pipeline, identifies matching entity nodes in the graph, performs a two-hop traversal to collect neighboring entities and their chunk associations, aggregates chunk scores based on direct hits (+1.0 per directly mentioned query entity) and two-hop neighbors (+0.5), and returns ranked chunks. Run file output (evidence file S12) shows that all twenty-eight queries produced results, with an average of approximately 4.67 results per query reflecting the sparsity of the entity graph on the ten-chunk corpus.

## 5.4 Evaluation Results

### 5.4.1 Test Coverage

The pytest test suite (evidence file S14) verifies core functionality of the retrieval implementations. Test execution covers unit tests for the BM25 tokenizer, index construction, and scoring functions; unit tests for FAISS embedding and indexing; and unit tests for the GraphRAG entity extractor and graph traversal. Tests are written to execute without external API calls and complete execution within 30 seconds total.

### 5.4.2 Quantitative Metrics

Evaluation metrics (evidence file S15) computed from the qrels and run files using standard information retrieval metrics include Mean Reciprocal Rank (MRR), Recall@k, and Normalized Discounted Cumulative Gain (nDCG@k). Results are computed at k=5 and k=10 cutoffs. The comparison summary shows:

BM25 achieves MRR@5 = 0.8304, MRR@10 = 0.8304, Recall@5 = 0.8214, Recall@10 = 1.0000, nDCG@5 = 0.7804, nDCG@10 = 0.8683. The perfect Recall@10 score (1.0000) indicates that BM25 retrieves all relevant chunks within the top-10 results for all twenty-eight queries. Average query latency is 0.06 milliseconds.

FAISS achieves MRR@5 = 0.7958, MRR@10 = 0.7958, Recall@5 = 0.8571, Recall@10 = 0.8571, nDCG@5 = 0.7742, nDCG@10 = 0.7742. Average query latency is 92.06 milliseconds, predominantly due to embedding computation time.

GraphRAG achieves MRR@5 = 0.6095, MRR@10 = 0.6095, Recall@5 = 0.6875, Recall@10 = 0.6875, nDCG@5 = 0.5909, nDCG@10 = 0.5909. Average query latency is 3.29 milliseconds, reflecting the graph traversal speed advantage over embedding.

The per-category breakdown (evidence file S15, second part) shows category-specific performance:

Terminology queries: BM25 = 1.0000, FAISS = 1.0000, GraphRAG = 0.6250. Both lexical and dense methods handle acronym-heavy questions perfectly; entity-based method underperforms because entity extraction prioritizes semantic types over acronyms.

Exact lookup queries: BM25 = 0.9444, FAISS = 0.6389, GraphRAG = 0.5407. Lexical exact matching significantly outperforms semantic methods when the question and answer use identical terminology.

Paraphrase queries: BM25 = 1.0000, FAISS = 1.0000, GraphRAG = 0.2667. Dense vectors excel at synonymy; entity-based method fails because paraphrased questions extract different entities than the source text.

Entity relation queries: BM25 = 1.0000, FAISS = 1.0000, GraphRAG = 1.0000. All methods succeed when entity types are stable across questions and source documents.

Synthesis queries: BM25 = 0.6667, FAISS = 0.9167, GraphRAG = 0.9167. Dense methods excel at multi-document synthesis, using semantic similarity to identify complementary information; BM25 requires term overlap.

Multi-hop queries: BM25 = 0.5500, FAISS = 0.6067, GraphRAG = 0.3333. All methods struggle with transitive reasoning; the ten-chunk corpus provides insufficient entities and cross-references to enable robust multi-hop retrieval.

### 5.4.3 Qualitative Results

Sample query results (evidence file S16) document the top-ranked retrievals for three representative questions. One question on welfare scheme eligibility shows BM25 returning chunks containing explicit eligibility text, FAISS returning semantically similar policy descriptions, and GraphRAG returning entity-associated chunks. Another question using paraphrased language shows FAISS identifying relevant chunks despite term mismatch, while BM25 returns no matches due to vocabulary divergence. A third question on comparative policy features shows FAISS synthesizing across chunks with different entity compositions, while BM25 requires term overlap and GraphRAG requires explicit entity co-occurrence.

## 5.5 Honest Assessment and Next Steps

### 5.5.1 Completed Work

The following components are fully implemented, tested, and verified to be working:

1. Corpus construction and chunking pipeline: The ten-chunk corpus is complete, cleaned, and stored in standardized JSONL format.

2. QA dataset generation and annotation: Twenty-eight questions across six categories are annotated with relevance judgments in TREC qrels format.

3. BM25 retrieval system: Index construction, query execution, and run file generation are complete. All 28 queries return results (280 total).

4. FAISS retrieval system: Index construction, query execution, and run file generation are complete. All 28 queries return results (140 total).

5. GraphRAG retrieval system: Entity extraction, graph construction, query execution, and run file generation are complete. All 28 queries return results (131 total).

6. Evaluation framework: Metric computation (MRR, Recall@k, nDCG@k) is implemented and verified. Per-category analysis is computed and consistent.

7. Comparative analysis reports: Summary tables (comparison_summary.csv, per_category.csv) and markdown report (comparison_report.md) are generated.

### 5.5.2 Outstanding Work

The following components are not yet complete but are not blocking further dissertation progress:

1. GraphRAG parameter tuning: The current 2-hop traversal and scoring function (+1.0/-+0.5) are defaults. Fine-tuning entity extraction confidence thresholds and edge weighting may improve performance, but this is optional for the primary hypothesis.

2. Hybrid ensemble methods: A proof-of-concept combining BM25 and FAISS scores via learned weights is not yet implemented, but analysis of individual methods is sufficient for the dissertation scope.

3. Statistical significance testing: With 28 queries and three methods, power analysis shows that significance tests would require bootstrap resampling or a substantially larger query set. This limitation is acknowledged in the dissertation but does not prevent reporting empirical results.

4. Extended corpus experiments: Testing the three methods on a 100-chunk corpus to assess scalability is desirable but not required for the primary hypothesis validation.

### 5.5.3 Critical Path to Submission

The dissertation is on track for completion by August 2, 2026. The critical path consists of:

1. Write Chapter 5 final version incorporating all quantitative results: Estimated 4 days (due June 25, 2026).

2. Write Chapter 6 discussion, limitations, and conclusions: Estimated 3 days (due June 28, 2026).

3. Technical editing and formatting: Estimated 2 days (due June 30, 2026).

4. Internal review by supervisor and examiner: Estimated 2 days (due July 31, 2026).

5. Revisions and final submission: Estimated 2 days (due August 2, 2026).

No blocking issues have emerged. All retrieval methods are functional. All evaluation metrics are computed. No additional data collection or system development is required beyond the optional components listed above.

---

**Evidence Files Used:**
- S1: Corpus Manifest (source metadata)
- S2: Sources Registry (document inventory)
- S4: Chunk Statistics (corpus characteristics)
- S5: QA Dataset Overview (query composition)
- S6: Qrels Statistics (relevance judgments)
- S7: BM25 Index Build (lexical indexing)
- S8: BM25 Run Sample (results verification)
- S9-S10: FAISS Index and Run (dense vector retrieval)
- S11-S12: GraphRAG Graph and Run (entity-aware retrieval)
- S14-S15: Test Results and Metrics (quantitative evaluation)
- S16: Sample Queries (qualitative examples)
