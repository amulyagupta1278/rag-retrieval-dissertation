# Experiment Protocol V2

Status: preregistration draft approved for Phase 0. No V2 comparative result has been inspected.

## Research-integrity boundary

The rebuild exists because later evidence is incomplete or compromised, not because any result contradicts a hypothesis. Negative results remain valid. Historical files and results remain unchanged and are classified separately from V2 evidence.

## Canonical hypotheses

- **H1:** BM25 performs competitively with FAISS on exact-match and terminology-sensitive queries.
- **H2:** FAISS outperforms BM25 on paraphrased/semantic queries where query vocabulary differs from source text.
- **H3:** Entity-Co-occurrence Graph Retrieval outperforms BM25 and FAISS on entity-relation and multi-hop queries.
- **H4:** Hybrid BM25 + Entity-Co-occurrence Graph retrieval (via RRF) achieves the highest aggregate MRR across mixed query types, at the cost of higher latency.
- **H5:** Retrieval quality (MRR) does not translate monotonically into generation faithfulness; retrieval and generation require separate evaluation.

H4 always means BM25 plus Entity-Co-occurrence Graph RRF. Hypotheses may be supported, partially supported, not supported, or inconclusive.

## Frozen balanced evaluation design

No single global metric determines best system. Metrics are not averaged into a composite score. Conclusions identify category-specific and metric-specific strengths, weaknesses, and Pareto trade-offs. Contradictory metrics are reported explicitly.

Every retrieval system reports:

- MRR@5 and MRR@10.
- Recall@5 and Recall@10.
- Hit Rate@5 and Hit Rate@10.
- Precision@5 and Precision@10.
- Binary nDCG@10 for historical continuity.
- Graded nDCG@10 using qrel grades.
- Complete Evidence Recall@5 and Complete Evidence Recall@10.

Every retrieval metric is shown aggregate and per category, with query count and paired uncertainty where applicable. No hidden weighting, composite score, or universal winner is permitted.

Efficiency reporting includes mean, median, and p95 latency; index-build time; index size; peak memory where measurable; and API tokens, cost, and retry rate for Prompt-RAG.

Generation is evaluated separately using correctness, faithfulness, completeness, citation/evidence accuracy, abstention quality, and unsupported-claim rate.

- Positive relevance: qrel value greater than zero.
- Query aggregation: unweighted macro mean.
- Stochastic seed: 42 for every local stochastic operation.
- Bootstrap: paired whole-query bootstrap, 10,000 resamples, seed 42, percentile 95% interval.
- Directional superiority: paired randomization test.
- Confirmatory multiplicity: Holm correction across preregistered confirmatory comparisons.
- Category sample size must accompany every category result. Small-category analyses remain exploratory.

## H1 equivalence rule

Define paired query effect as:

`BM25 MRR@10 - FAISS MRR@10`

H1 is supported only when its paired 95% bootstrap confidence interval lies completely inside `[-0.05, +0.05]`. An interval touching or crossing either boundary is inconclusive. This is a two-sided equivalence rule; one-sided noninferiority is not a substitute.

The `±0.05` margin is a preregistered dissertation design choice, not a literature-established universal threshold. Report a sensitivity display using `±0.03`; never replace the primary `±0.05` decision after observing results.

## Other hypothesis rules

- H1 uses exact-lookup and terminology slices. Inspect MRR, Recall, binary and graded nDCG, Precision, and Hit Rate. The MRR@10 equivalence rule remains one explicit decision test; disagreement from other metrics must be disclosed.
- H2 uses paraphrase/semantic queries and the full retrieval panel.
- H3 reports entity-relation and multi-hop separately. Emphasize Complete Evidence Recall, Recall, graded nDCG, and MRR without hiding contradictory measures.
- H4’s canonical wording specifically names highest aggregate MRR, making aggregate MRR its stated endpoint. Report latency and every other quality metric; never reinterpret H4 as universal superiority. Compare frozen BM25+Graph RRF against its strongest frozen constituent and other frozen systems.
- H5 compares retrieval metrics with correctness, faithfulness, and completeness at query level. Aggregate system-level correlation alone is insufficient.
- H2–H4 directional superiority requires positive paired effect, confidence interval excluding zero in the predicted direction, and Holm-corrected paired-randomization result.

Exact minimum meaningful effects and final H2–H5 decision details must be frozen before their corresponding benchmark phase. Holdout labels remain sealed until corpus, systems, metrics, failure taxonomy, and decision rules are frozen.

## Artifact contract

Every V2 run records Git SHA, command, platform, Python/package/model versions, input hashes, configuration, seed, raw per-query ranking, errors, metrics, and output hashes. Ordering and tie-breaking must be deterministic. Retrieval timing excludes index construction, records warm-up/cache/batching policy, and separates external API time from local retrieval.

## Phase distinction

- Phase 0: forensic historical recomputation; not inferential evidence.
- Pilot: mechanical validation on 20–25 manually auditable documents; not final evidence.
- Expansion stages: development evidence, approved independently of hypothesis outcomes.
- Final holdout: single sealed evaluation after configuration freeze.
