# Comparative Analysis of Retrieval Strategies for Retrieval-Augmented Generation

## Sparse, Dense, Entity-Graph, Hybrid, and LLM-Reranked Retrieval on Indian Government-Scheme Documents

**Amulya Gupta — 2024AB05200**<br>
M.Tech Artificial Intelligence and Machine Learning<br>
Birla Institute of Technology & Science, Pilani — WILP<br>
Dissertation submission draft — July 2026

> Submission note: this is a technically complete draft grounded in the frozen Phase 1–7 pilot. Institutional front matter, declaration, certificate, acknowledgements, final bibliography formatting, and supervisor-specific edits remain to be inserted before submission.

## Abstract

Retrieval-augmented generation depends on retrieving evidence that is relevant, complete, and usable by a downstream generator. This dissertation compares five retrieval configurations on a shared corpus of Indian government-scheme documents: BM25 lexical retrieval, FAISS dense retrieval, entity-co-occurrence graph retrieval, BM25–graph Reciprocal Rank Fusion, and an LLM-based reranker operating over a frozen BM25 candidate set. A controlled pilot benchmark contains 22 documents, 140 chunks, and 34 questions across exact lookup, terminology, paraphrase, entity relation, multi-hop, and synthesis categories. Relevance assessment uses 755 pooled query–chunk pairs with human-owner grading, deterministic regrading, and disagreement adjudication.

Prompt-RAG produced the highest pilot MRR@10 (0.9779) and graded nDCG@10 (0.8907), while Hybrid RRF achieved the highest Recall@10 (0.8449). BM25 remained a strong baseline with MRR@10 of 0.9412. FAISS and entity-graph retrieval did not satisfy the preregistered pilot superiority hypotheses. A separate generation study produced 170 answers from each system's top-three evidence chunks. Twenty-six blinded answers were scored by the human owner and 144 received disclosed offline AI-assisted labels. Retrieval MRR had almost no monotonic association with generation faithfulness (Spearman rho = -0.0333), while Complete Evidence Recall showed a modest positive association with answer completeness (rho = 0.3395).

An exploratory Phase 8 R4 scaling study expanded the corpus to 130 documents and 954 chunks and evaluated 100 inherited questions, with 20 synthesis questions held out as automated candidates. On the locked 40-question test split, Prompt-RAG achieved the highest Recall@10 (0.8750), BM25 the highest MRR@10 (0.6071) and nDCG@10 (0.6412), and Prompt-RAG nearly matched BM25 nDCG@10 (0.6408). All 100 generated-answer quality labels in R4 were AI-assigned and the expanded gold crosswalks remain pending human review. R4 therefore demonstrates engineering scalability and supplies exploratory evidence; it does not supersede the human-validated pilot. Results support evaluating retrieval and generation as separate layers.

**Keywords:** retrieval-augmented generation, BM25, FAISS, entity graph, reciprocal rank fusion, reranking, relevance judgment, government schemes

# Chapter 1 — Introduction

## 1.1 Background

Retrieval-augmented generation combines information retrieval with language-model generation. Instead of relying only on model parameters, the system retrieves passages from an external corpus and supplies them as evidence. This architecture can improve factual grounding, updateability, and source traceability. Yet retrieval quality is not a single property. Lexical systems reward exact term overlap; dense systems reward semantic similarity; graph systems exploit entity connections; fusion systems combine ranked evidence; and LLM rerankers apply task-specific relevance reasoning to a candidate set.

Government-scheme information provides a demanding evaluation domain. Questions may ask for exact benefit values, acronym expansions, relationships between ministries and schemes, comparisons across programmes, or synthesis of several policy components. Documents contain overlapping terminology, repeated administrative language, and uneven detail. A system that performs well on exact facts may fail on paraphrases or multi-part questions.

## 1.2 Problem statement

The dissertation asks how different retrieval paradigms behave when corpus, chunking, questions, relevance judgments, and evaluation metrics are held constant. It also asks whether stronger retrieval rankings necessarily translate into better generated answers. Prior comparisons often change several variables simultaneously or report only aggregate metrics. This study instead preserves category slices, contradictory metrics, failure cases, and audit evidence.

## 1.3 Objectives

1. Build a reproducible government-scheme retrieval benchmark.
2. Compare sparse, dense, graph-based, fused, and LLM-reranked retrieval under one protocol.
3. Measure rank quality, coverage, evidence completeness, and operational cost separately.
4. Test preregistered hypotheses without replacing negative outcomes.
5. Evaluate downstream answer generation using identical prompts and context depth.
6. Preserve hashes, failed attempts, owner approvals, and correction records for auditability.

## 1.4 Research questions

- RQ1: How competitive is BM25 against dense retrieval on exact and terminology-focused questions?
- RQ2: Does dense retrieval outperform BM25 on paraphrased questions?
- RQ3: Does entity-co-occurrence graph retrieval improve entity-relation and multi-hop retrieval?
- RQ4: Does BM25–graph fusion achieve the strongest aggregate retrieval performance?
- RQ5: Does retrieval rank quality translate monotonically into generated-answer faithfulness?

## 1.5 Scope

Confirmatory claims apply to the frozen V2 pilot: 22 documents, 140 chunks, 34 questions, and five retrieval systems. Phase 8 R4 is reported separately as an exploratory scaling study with 130 documents, 954 chunks, 100 primary questions, and 20 automated synthesis candidates. Its inherited gold mappings and generated-answer labels are not human-validated, so R4 is not used to inflate pilot claims. Prompt-RAG is a reranker rather than the downstream answer generator. In the pilot it reranks BM25's top 50; in R4 it reranks a deterministic BM25-top-25 plus unseen-FAISS-top-25 union. The graph systems are entity-co-occurrence retrievers, not Microsoft GraphRAG.

# Chapter 2 — Related Work

## 2.1 Sparse lexical retrieval

BM25 scores documents using term frequency, inverse document frequency, and document-length normalization. It remains a difficult baseline to beat when queries contain domain terms, identifiers, acronyms, or exact phrases. Its strengths include deterministic ranking, low operational complexity, and interpretability. Its main weakness is vocabulary mismatch when users paraphrase source language.

## 2.2 Dense retrieval

Dense retrieval embeds queries and text into a vector space and ranks by similarity. It can recover semantically related passages without exact term overlap. Performance depends on embedding model, chunk boundaries, truncation, pooling, and index configuration. This study uses windowed maximum scoring so long chunks are represented through token-aware windows rather than a single truncated embedding.

## 2.3 Graph retrieval

Graph retrieval represents entities and their relationships or co-occurrence. It may help when a question requires connecting evidence across entities or chunks. Benefits depend on reliable entity extraction and query-to-entity matching. The implemented system uses corpus-backed normalized aliases, chunk/entity co-occurrence edges, and bounded traversal. It does not generate community summaries.

## 2.4 Fusion and reranking

Reciprocal Rank Fusion combines rank positions without requiring score calibration. This makes it useful when component systems produce incomparable score scales. LLM reranking can apply richer relevance reasoning but introduces provider dependence, cost, latency, and candidate-set ceilings. In this study, Prompt-RAG cannot retrieve outside BM25's frozen top-50 pool.

## 2.5 Evaluation

MRR measures rank of the first relevant result. Recall measures coverage of judged relevant chunks. nDCG rewards graded relevance near the top. Complete Evidence Recall asks whether all judged positive evidence is present within a cutoff. No single metric captures every desired property; therefore metrics remain separate. Generation evaluation similarly separates correctness, faithfulness, completeness, citation accuracy, unsupported-claim severity, and abstention quality.

# Chapter 3 — Dataset and Experimental Design

## 3.1 Corpus

The pilot corpus contains 22 Indian government-scheme documents represented by 140 deterministic chunks. Documents cover banking, insurance, pensions, housing, employment, agriculture, skills, energy access, and tribal welfare. Two documents contribute 65 of 140 chunks, creating a known concentration risk. Every frozen chunk has a stable identifier and provenance metadata.

## 3.2 Benchmark

The benchmark contains 34 owner-approved questions: six each for exact lookup, terminology, paraphrase, entity relation, and multi-hop, plus four synthesis questions. Reference answers define expected facts. Category sizes are reported with every slice because N=4 or N=6 cannot support broad population claims.

## 3.3 Relevance judgments

Five systems contributed candidate chunks to a blinded pool. After deduplication, the pool contained 755 unique query–chunk pairs. Grades use 0 for nonrelevant, 1 for contextual or partially useful, and 2 for directly relevant evidence. A deterministic seed-42 sample of 114 rows received a second human-owner pass. Exact agreement was 87.72%, Cohen's kappa 0.7421, and quadratic-weighted kappa 0.8841. Fourteen disagreements were owner-adjudicated. Final distribution was 572 grade-0, 89 grade-1, and 94 grade-2 labels.

## 3.4 Systems

### BM25

BM25 uses `k1=1.5`, `b=0.75`, Unicode word tokenization, and deterministic chunk-ID tie-breaking.

### FAISS-windowed-max

FAISS uses normalized `all-MiniLM-L6-v2` embeddings, 254-content-token windows, 32-token overlap, exact inner-product search, and maximum-window collapse to chunk scores.

### Entity Graph v3.2

Entity Graph uses exact normalized alias matching, corpus-backed entities, at most two graph hops, no lexical fallback, and deterministic ranking.

### Hybrid RRF

Hybrid combines BM25 and Entity Graph ranks with equal weights and RRF constant 60.

### Prompt-RAG Claude

Prompt-RAG sends each BM25 top-50 candidate set to `claude-haiku-4-5-20251001`. Every candidate receives an integer 0–3 relevance score. Ranking uses descending score then ascending chunk ID. No retry, fallback, or output replacement is allowed.

## 3.5 Metrics and statistics

Primary retrieval metrics are MRR@10, Recall@10, graded nDCG@10, and Complete Evidence Recall@10. MRR@5, Recall@5, precision, binary nDCG, hit rate, category slices, latency, and per-query values are retained. Statistical analysis uses 10,000 paired whole-query bootstrap samples with seed 42, exact paired randomization where defined, and Holm correction across frozen directional comparisons.

## 3.6 Phase 8 R4 scaling design

R4 expands the corpus from 22 to 130 documents and from 140 to 954 section-aware chunks. It retains 100 inherited primary questions across exact lookup, terminology, paraphrase, entity relation, and multi-hop categories. Sixty questions form a development split and 40 form a locked test split. Twenty deterministic synthesis questions remain outside primary metrics as `automated_candidate_pending_human_validation`.

All five retrieval systems were rebuilt against the R4 corpus: BM25, normalized-cosine FAISS, Entity Graph v4, matching Hybrid RRF, and Prompt-RAG. Prompt-RAG used a deterministic union of BM25 top 25 followed by unseen FAISS top 25 candidates. Live calls used a frozen model, prompt, schema, temperature, output ceiling, request hashes, pre-dispatch accounting, and zero-retry/no-fallback policy. Failed V1 and V2 attempts were preserved; V3 recovery changed only the disclosed semantic instruction needed to satisfy the frozen claim-to-evidence contract.

R4 relevance mappings are automatic crosswalks from inherited benchmark records to new chunks. They have not received the Phase 6-style human pooling, regrade, and adjudication process. Statistical comparisons are therefore explicitly exploratory.

# Chapter 4 — Retrieval Results

## 4.1 Aggregate results

| System | MRR@10 | Recall@10 | Graded nDCG@10 | Complete Evidence Recall@10 |
|---|---:|---:|---:|---:|
| BM25 | 0.9412 | 0.8008 | 0.8235 | 0.4118 |
| FAISS-windowed-max | 0.8279 | 0.7001 | 0.6883 | 0.2941 |
| Entity Graph v3.2 | 0.6765 | 0.6103 | 0.6214 | 0.4118 |
| Hybrid RRF | 0.9559 | **0.8449** | 0.8783 | 0.5000 |
| Prompt-RAG Claude | **0.9779** | 0.8355 | **0.8907** | **0.5882** |

Prompt-RAG led MRR, graded nDCG, and evidence completeness. Hybrid led recall. BM25 remained close to the strongest systems on first-relevant rank. Dense and graph systems performed below BM25 in aggregate. These observations do not establish a universal winner.

## 4.2 Hypothesis outcomes

H1 tested BM25–FAISS MRR equivalence on exact lookup and terminology questions. Difference was +0.0667, but the 95% interval [-0.0833, 0.2417] was not contained within the ±0.05 margin; H1 was inconclusive. H2 predicted FAISS superiority on paraphrases. Observed FAISS–BM25 MRR difference was -0.4250; H2 was not supported. H3 predicted graph superiority for entity-relation and multi-hop questions; none of 16 frozen comparisons passed all criteria. H4 required Hybrid to outperform every comparator in aggregate MRR. It passed only the Graph comparison and was not supported.

## 4.3 Interpretation

Strong BM25 performance indicates extensive lexical anchoring in government-scheme questions and documents. Dense retrieval's semantic flexibility did not compensate for lost exact-term precision in this pilot. Entity graph retrieval suffered from sparse or ambiguous query entity matches and could not rely on lexical fallback. Hybrid recovered much of BM25's strength while adding graph results, improving recall. Prompt-RAG gained top-rank precision by reasoning over candidate relevance but remained constrained by BM25 candidate recall.

## 4.4 Exploratory Phase 8 R4 results

Locked-test results on 40 questions were:

| System | MRR@10 | Recall@10 | Precision@10 | nDCG@10 |
|---|---:|---:|---:|---:|
| BM25 | **0.6071** | 0.8500 | 0.1200 | **0.6412** |
| FAISS-windowed-max | 0.4113 | 0.6625 | 0.0975 | 0.4413 |
| Entity Graph v4 | 0.4579 | 0.6625 | 0.0950 | 0.4628 |
| Hybrid RRF | 0.5938 | 0.8500 | 0.1200 | 0.6245 |
| Prompt-RAG Claude | 0.5842 | **0.8750** | **0.1225** | 0.6408 |

Expansion changed the ordering seen in the pilot. BM25 led R4 locked-test MRR and nDCG, Prompt-RAG led recall and precision, and Hybrid remained close to BM25. Prompt-RAG mean latency was 16.82 seconds (median 15.80; p95 24.25). Comparable latency was unavailable for the other systems and was not encoded as zero.

Exploratory paired nDCG@10 tests used 10,000 sign-flip randomizations, paired bootstrap intervals, seed 42, and Holm correction. BM25, Hybrid, and Prompt-RAG each outperformed FAISS after correction (adjusted p-values 0.0036, 0.0020, and 0.0056 respectively). Other adjusted comparisons were not below 0.05. These tests do not prove preregistered hypotheses because R4 was not the confirmatory benchmark and its gold crosswalks await human review.

# Chapter 5 — Generation Experiment

## 5.1 Design

Each retrieval system supplied its top-three chunks for each of 34 questions, producing 170 requests. One frozen prompt, response schema, model, temperature, and citation contract were used. The final V2 run produced 170 valid answers with no retries or generation failures. Cumulative Phase 7 provider cost was USD 0.525320.

## 5.2 Evaluation

Mechanical checks verified schema, citation IDs, citation coverage, latency, usage, and cost. The owner scored a frozen blinded sample of 26 answers across six dimensions. Remaining 144 answers received explicitly disclosed offline AI labels using pinned MiniLM embeddings and a five-nearest-neighbor classifier trained on owner scores. Owner scores override automated predictions. This is not equivalent to 170 human-reviewed answers.

Leave-one-owner-row-out agreement was 88.46% for correctness, 96.15% for faithfulness, 96.15% for completeness, 92.31% for citation accuracy, 92.31% for unsupported-claim severity, and 88.46% for abstention quality. Class imbalance produced kappa of zero for three dimensions despite high raw agreement, limiting reliability claims.

## 5.3 H5 results

| Retrieval variable | Generation variable | Spearman rho | 95% bootstrap interval |
|---|---|---:|---:|
| MRR@10 | Faithfulness | -0.0333 | [-0.0672, -0.0256] |
| MRR@10 | Correctness | 0.1753 | [0.0255, 0.3396] |
| Graded nDCG@10 | Correctness | 0.2700 | [0.1362, 0.3848] |
| Complete Evidence Recall@10 | Completeness | 0.3395 | [0.1581, 0.5067] |

MRR showed almost no monotonic relationship with faithfulness. Evidence coverage had a clearer, though modest, association with completeness. H5 is reported descriptively because the frozen protocol did not specify a minimum effect or confirmatory decision threshold.

## 5.4 Abstention finding

The human audit contained seven literal abstentions. Five were judged incorrect because supplied evidence supported at least part of the answer; two were appropriate. One additional non-abstaining answer mishandled missing evidence, producing six abstention-policy failures. This indicates over-conservative refusal behavior and motivates partial-answer guidance: answer supported components, cite them, and explicitly mark unsupported components.

## 5.5 Phase 8 R4 generation and automated evaluation

R4 generated one answer for each combination of 20 deterministic category-balanced questions and five retrieval systems: 100 answers in total. Every answer used the same model, prompt family, top-three evidence depth, temperature, schema, and citation contract. All 100 final records were valid. Preserved failure checkpoints document truncation and semantic-contract failures before recovery; no failed output was silently replaced.

Prompt-RAG retrieval cost USD 2.430722. Generation, including preserved failed and recovery attempts, cost USD 0.429828. Total R4 API cost was USD 2.860550, leaving USD 0.839450 under the USD 3.70 hard cap.

All R4 answer-quality labels were assigned by a disclosed offline five-nearest-neighbor evaluator using MiniLM features trained on 26 genuine Phase 7 owner-audit labels. No R4 answer overlaps the owner-labelled set, so R4 AI–owner agreement is not estimable. Mean correctness/completeness scores were 1.0 for BM25, 1.1 for FAISS, 1.1 for Graph, 1.0 for Hybrid, and 1.3 for Prompt-RAG on the 0–2 rubric. Literal abstention counts were 10, 9, 9, 10, and 8 respectively. Faithfulness and citation-accuracy predictions were constant at 2.0 and unsupported-claim severity at 0, preventing meaningful inferential claims for those dimensions.

R4 H5 analysis was descriptive. MRR–faithfulness was non-estimable because faithfulness was constant. MRR–correctness had Spearman rho -0.056 with interval [-0.345, 0.254]; nDCG–correctness rho 0.079 [-0.230, 0.387]; and recall–completeness rho 0.078 [-0.256, 0.434]. None supports a strong monotonic relationship between retrieval metrics and automated answer-quality predictions.

# Chapter 6 — Discussion

## 6.1 Retrieval paradigms are complementary

Results reject a simple narrative that dense or graph retrieval automatically replaces lexical retrieval. BM25 was highly competitive, Hybrid improved broad coverage, and Prompt-RAG improved top-rank relevance within a lexical candidate ceiling. System choice should follow query characteristics, latency constraints, cost tolerance, and evidence-completeness requirements.

## 6.2 Retrieval and generation require separate evaluation

A high MRR can coexist with incomplete evidence or poor generation decisions. Conversely, a faithful answer may be produced from modestly ranked but sufficient evidence. Retrieval metrics should therefore be paired with answer correctness, faithfulness, completeness, citation behavior, and abstention analysis.

## 6.3 Negative results matter

H2, H3, and H4 were not supported, while H1 was inconclusive. Preserving these outcomes avoids post-hoc hypothesis replacement. Small category samples and pooled-label limits mean negative outcomes should guide future study design rather than be treated as universal rejection of dense or graph retrieval.

# Chapter 7 — Validity, Ethics, and Reproducibility

## 7.1 Internal validity

All systems use the same corpus, questions, chunk IDs, relevance labels, and metric definitions. Deterministic tie-breaking reduces accidental variation. Prompt-RAG differs operationally because it uses BM25 candidates and a paid model; this is disclosed rather than treated as a directly symmetric retriever.

## 7.2 Construct validity

Pooled judgments are incomplete: unpooled chunks are not independently verified nonrelevant. Complete Evidence Recall depends on judged positives, not unknowable total corpus evidence. Generation faithfulness labels are strongly imbalanced and mostly automated.

## 7.3 External validity

Twenty-two documents and 34 questions cannot represent every government scheme, language, user population, or information need. R4 materially broadens engineering coverage to 130 documents and 954 chunks, but it reuses inherited questions and automatic gold crosswalks. It therefore reduces corpus-scale uncertainty without establishing population-level validity. Neither study covers multilingual questions, diverse user groups, or independently sampled real-world information needs.

## 7.4 Research integrity

Failed Gemini and Claude attempts, protocol corrections, costs, owner approvals, and invalidated artifacts remain preserved. Secrets are excluded. Frozen outputs are not replaced after seeing results. Human and AI labels are distinguished explicitly.

## 7.5 Reproducibility

Offline rankings, qrels, metrics, generated responses, tests, hashes, and manifests are committed. Live provider responses are protocol-reproducible but not guaranteed byte-identical. Submission-ready pilot freeze is tag `pilot-v2-phase7-final-20260729` at commit `40aad1a`.

# Chapter 8 — Conclusions and Future Work

This dissertation demonstrates that sparse lexical retrieval remains a strong baseline for government-scheme evidence retrieval. Hybrid fusion improves recall, while LLM reranking improves top-rank relevance within a candidate ceiling. Dense and graph retrieval did not achieve their preregistered pilot advantages. Generation evaluation shows that rank quality alone does not determine faithfulness and that evidence completeness deserves separate measurement.

R4 shows that the pipeline can scale from 22 to 130 documents and from 140 to 954 chunks while rebuilding all five systems, enforcing cost and failure controls, and completing retrieval plus generation. Its changed system ordering is itself important: apparent winners depend on benchmark scale and construction. Because R4 gold crosswalks and generation labels are automated, the human-validated pilot remains the canonical evidential basis.

Future work should human-review R4 source mappings and retrieval pools, audit or score R4 answers, validate the 20 held-out synthesis candidates, conduct independent multi-rater judgments, improve graph entity linking, test multilingual questions, and evaluate partial-answer abstention policies. Only after equivalent validation should expanded results replace or be pooled with the pilot.

# Appendix A — Canonical artifacts

- Final qrels: `runs/v2/phase6_seed42_final/qrels/phase6_final_pooled_qrels.tsv`
- Retrieval metrics: `runs/v2/phase6_seed42_final/metrics/balanced_metrics.json`
- H1–H4 statistics: `runs/v2/phase6_seed42_final/statistics/preregistered_h1_h4_results.json`
- Generation checkpoint: `audits/phase7_generation/v2/full_v2_success_checkpoint.json`
- Final quality labels: `runs/v2/phase7_generation_claude_top3_v2/evaluation_v2_ai/final_quality_labels_170.jsonl`
- H5 results: `runs/v2/phase7_generation_claude_top3_v2/evaluation_v2_ai/h5_results.json`
- Phase 7 disclosure: `docs/PHASE7_FINAL_AI_EVALUATED_STATUS.md`
- Phase 8 R4 report: `docs/PHASE8_R4_FINAL_REPORT.md`
- Phase 8 R4 canonical status: `audits/phase8_r4/canonical_status.json`

# Appendix B — Submission completion checklist

- Insert university certificate, declaration, supervisor approval, and acknowledgements.
- Verify every literature citation against original source and apply required citation style.
- Add numbered figures and captions exported from dashboard or analysis scripts.
- Confirm table of contents, page numbering, margins, and institutional template.
- Obtain supervisor review of AI-assisted evaluation disclosure.
- Proofread terminology: Prompt-RAG reranker, Entity-Co-occurrence Graph Retrieval, exploratory pilot.
