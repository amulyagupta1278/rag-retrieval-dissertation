# Phase 8 Final Hypothesis Verdicts

Status: `canonical_phase8_verdicts_complete`

## Evidence boundary

Canonical independent holdout contains 12 owner-reviewed questions, 21 relevance judgments,
and two questions in each of six retrieval categories. BM25, FAISS cosine, Entity Graph v4,
and Hybrid R4 completed frozen evaluation. Intervals use 10,000 paired whole-query bootstrap
samples with seed 42.

Prompt-RAG completed only 1/12 requests under the frozen zero-retry contract. A later 12/12
execution repeated an ambiguously dispatched request and is excluded from canonical inference.
Its results may be disclosed only as exploratory sensitivity evidence.

## Aggregate holdout results

| System | MRR@10 | Recall@10 | Precision@10 | nDCG@10 | Hit@10 |
|---|---:|---:|---:|---:|---:|
| BM25 | **0.6667** | **0.8611** | **0.1500** | **0.6938** | **0.9167** |
| FAISS cosine | 0.5444 | 0.7500 | 0.1167 | 0.5685 | 0.8333 |
| Entity Graph v4 | 0.5162 | 0.6528 | 0.1083 | 0.4907 | 0.7500 |
| Hybrid R4 | 0.6597 | **0.8611** | **0.1500** | 0.6855 | **0.9167** |

All main paired MRR confidence intervals cross zero. Results therefore support descriptive
directional claims, not decisive superiority claims.

## Final verdicts

### H1 — BM25 is competitive with FAISS for exact-match and terminology-heavy queries

**Verdict: partial support; formal equivalence inconclusive.**

Exact-match MRR is tied at 1.000 for BM25 and FAISS. Terminology-heavy MRR does not favor
BM25: BM25 0.250, FAISS 0.417, Graph 0.556. Frozen equivalence requires the paired confidence
interval to lie wholly inside ±0.05. Only four combined exact/terminology questions exist, so
that criterion is not established.

Defensible claim: BM25 remains highly effective for exact-match retrieval. Evidence does not
show BM25 as best across the broader terminology-heavy slice.

### H2 — FAISS outperforms BM25 for paraphrase queries

**Verdict: not supported by current holdout; construct validity limited.**

Paraphrase MRR favors BM25, 0.667 versus FAISS 0.500. Several questions retain exact document
terminology, weakening the intended lexical-mismatch test. This limitation prevents a clean
general rejection of semantic retrieval, but current data cannot support H2.

Defensible claim: H2 was not supported in this benchmark. A separately preregistered,
paraphrase-only follow-up is required before reconsidering it.

### H3 — Graph retrieval outperforms BM25 and FAISS for entity-relation and multi-hop queries

**Verdict: strongest directional support; not statistically confirmed.**

Graph leads entity-relation MRR at 1.000 versus BM25 0.500 and FAISS 0.750. Graph also leads
multi-hop MRR at 0.667 versus BM25 0.583 and FAISS 0.250. Each category contains only two
questions, preventing reliable confirmatory inference.

Defensible claim: H3 received strongest preliminary support among five hypotheses. Phrase as
point-estimate evidence, not proof.

### H4 — Hybrid retrieval achieves highest aggregate MRR with increased latency

**Verdict: not supported.**

BM25 aggregate MRR is 0.6667, exceeding Hybrid R4 at 0.6597. BM25 also exceeds Hybrid nDCG,
0.6938 versus 0.6855. Recall, precision, and hit rate tie. Earlier locked R4 results show same
MRR direction: BM25 0.6071 versus Hybrid 0.5938. Holdout Hybrid also includes FAISS, whereas
canonical H4 originally specified BM25 plus Graph, creating an implementation mismatch.

Defensible claim: fusion maintained BM25-level recall but did not deliver highest aggregate MRR.

### H5 — Retrieval quality is not monotonically associated with answer faithfulness

**Verdict: inconclusive and not estimable for primary outcome.**

Human faithfulness labels are constant at 2, producing zero variance. MRR–faithfulness
correlation therefore cannot be estimated. Exploratory MRR–correctness correlation is
Spearman rho −0.1888 with 95% CI [−0.4009, 0.0698]; nDCG–correctness is −0.1659 with
95% CI [−0.3956, 0.0880]. These weak intervals cross zero and do not establish H5.

Defensible claim: available evidence shows no measurable monotonic pattern, but score-range
restriction makes H5 unresolved. A preregistered evaluation with varied blinded faithfulness
scores is required.

## Dissertation conclusion

No hypothesis reaches full confirmatory status under frozen statistical rules. H3 has strongest
positive point-estimate support. H1 receives partial exact-match support. H2 and H4 are not
supported by current benchmark. H5 remains inconclusive because primary outcome has no variance.

This conclusion must not be rewritten as “three hypotheses proved and two failed.” Such wording
would exceed sample size, confidence intervals, and evaluation validity.

## Canonical evidence

- `runs/phase8_option_b_holdout/retrieval/metrics.json`
- `runs/phase8_option_b_holdout/retrieval/per_query.jsonl`
- `runs/phase8_option_b_holdout/analysis/descriptive_statistics.json`
- `runs/phase8_option_b_holdout/freeze/freeze_manifest.json`
- `docs/PHASE8_R4_HUMAN_VALIDATION_FINAL_REPORT.md`
- `audits/phase8_option_b_holdout/prompt_rag_12of12_validity_audit.json`
