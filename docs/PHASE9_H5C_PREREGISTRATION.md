# Phase 9 H5c Confirmatory Follow-up — Frozen Protocol

Status: **confirmatory design; freeze before provider execution and outcome review**.

## Rationale and hypothesis

Original H5 was not estimable because claim faithfulness had a severe ceiling. H5c tests a
related, behaviorally identifiable construct without replacing or relabeling original H5.

> H5c: Reducing supplied evidence sufficiency lowers grounded-answer success, operationalized as
> production of a non-abstaining answer with adjudicated claim faithfulness >= 0.90.

## Panel

- Twelve frozen test questions: 3 exact-match, 3 terminology-heavy, 2 paraphrase, 2 multi-hop,
  and 2 entity-relation.
- Five within-question evidence conditions, yielding 60 responses.
- Frozen seed: 51025. Model: `claude-haiku-4-5-20251001`; temperature 0; zero retries.
- Conditions: `complete_top3`, `best_only`, `truncated_best`, `distractor_heavy`, `irrelevant`.
- Complete contexts use Prompt-RAG top three. Distractors come from different source documents.
  Truncation is deterministic at 25% of best-chunk words. No synthetic facts or contradictions.

## Outcomes and analysis

Primary endpoint: grounded-answer success = non-abstention and adjudicated faithfulness >= 0.90.
Primary contrast: paired `complete_top3` versus `irrelevant`, exact two-sided McNemar test.
Effect: paired success-rate difference with 10,000 question-cluster bootstrap draws (seed 51025).
H5c support requires: complete success rate > irrelevant success rate, difference >= 0.30,
two-sided p < 0.05, and bootstrap 95% CI lower bound > 0.

Secondary ordered-condition trend and abstention analyses are descriptive. Claim faithfulness
among claim-bearing answers is reported but is not sole H5c endpoint. No result-dependent
exclusions, replacements, retries, prompt changes, or condition changes permitted.

## Review and stopping

Two reviewers independently score every factual claim against supplied evidence while condition
labels remain hidden. Disagreements in total claims or faithfulness > 0.10 require adjudication.
No confirmatory conclusion may be produced before 60/60 generation, dual review, adjudication,
mapping unseal, and validation. Human scoring cannot be replaced by generated agreement.

This follow-up may support H5c only. Original H5 remains `not_estimable` and must be reported.
