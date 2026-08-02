# Phase 8 Option B Independent Holdout Preregistration Draft

Status: `owner_reviewed_frozen_four_local_systems_complete_prompt_rag_pending`

## Decision and purpose

Option B is selected for the next Phase 8 step: retain the existing pilot and R4 runs as development evidence, then evaluate once on a separately frozen, owner-reviewed holdout. The holdout is intended to strengthen independence, not to convert exploratory R4 work into preregistered evidence retroactively.

## Frozen-after-review design

- Corpus: existing Phase 8 R4 section-aware corpus; no document, chunk, or index changes after holdout freeze.
- Holdout size: 12 questions, exactly two in each category: exact match, terminology-heavy, paraphrase, entity relation, multi-hop, and synthesis.
- Source selection: documents unused as gold-source documents in the 100-question R4 benchmark at candidate-construction time.
- Human gate: every question, reference answer, source-document mapping, and gold-evidence mapping requires explicit owner approval.
- Leakage control: holdout questions and labels must not be used for retriever tuning, prompt changes, index changes, or error-driven system modification.
- Systems: frozen BM25, normalized-cosine FAISS, Entity Graph v4, Hybrid RRF R4, and Prompt-RAG Claude configurations already used in Phase 8 R4.
- Primary retrieval depth: top 10.
- Primary metrics: MRR@10, Recall@10, Precision@10, nDCG@10, and Hit@10.
- Reporting: per-system aggregate and per-query results; holdout reported separately from pilot and exploratory R4 results.
- Statistical scope: descriptive estimates and paired uncertainty intervals. Any hypothesis test must be specified before execution and corrected for multiplicity.

## Owner review gate

Review workbook:

`submission/human_review/phase8_option_b_holdout/phase8_option_b_holdout_review_12.xlsx`

For each candidate, owner must complete:

1. question validity;
2. reference-answer validity;
3. evidence completeness;
4. leakage/duplication check;
5. overall decision: accept, revise, or reject;
6. revised question or answer where needed;
7. notes where judgment needs explanation.

Freeze is allowed only when all 12 rows are decided, no row remains uncertain, accepted/revised rows retain exactly two questions per category, and protected source/evidence fields remain unchanged unless a documented correction is approved.

## Execution stop rule

No retrieval, generation, scoring, or statistical comparison may run from this draft. Next authorized action after completed owner review is deterministic validation, export of accepted rows, SHA-256 manifest creation, and freeze. System execution requires a separate post-freeze action.

## Claim boundary

Before owner freeze, these rows are design candidates only. After freeze and one untouched execution, results may be described as independent holdout evidence. They must not be merged silently with pilot or exploratory R4 metrics.
