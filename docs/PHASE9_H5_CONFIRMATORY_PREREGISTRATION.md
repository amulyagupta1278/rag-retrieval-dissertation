# Phase 9 H5 Confirmatory Follow-up Preregistration

Status: `draft_blocked_on_50_additional_generations_and_owner_freeze`

## Research question

Does retrieval rank quality exhibit a monotonic association with answer faithfulness when
faithfulness is measured at claim level and has sufficient observed variation?

## Hypothesis

H5: retrieval MRR@10 does not reliably predict claim-level generation faithfulness across
retrieval systems and questions.

This follow-up does not alter the Phase 8 verdict. Phase 8 H5 remains inconclusive because all
100 owner faithfulness labels equal 2.0.

## Frozen target panel

- 30 locked-test questions selected without using new faithfulness outcomes.
- Five systems per question: BM25, FAISS cosine, Entity Graph v4, Hybrid R4, Prompt-RAG.
- 150 answers total.
- Existing supply: 100 answers covering 20 questions × five systems.
- Missing gate: 50 answers covering ten additional locked-test questions × five systems.
- Identical answer model, prompt, context depth, temperature, and output contract across systems.
- System identity hidden from reviewers.

Human scoring must not begin until all 150 protected answer/evidence records exist, hashes are
frozen, and reviewer assignment is recorded.

## Primary outcome

For each answer, reviewers identify every externally verifiable claim and classify it as:

- fully supported by supplied evidence;
- partially supported;
- unsupported;
- contradicted by supplied evidence.

Primary faithfulness score:

`(fully_supported + 0.5 × partially_supported) / total_verifiable_claims`

Abstentions with no factual claim are recorded separately and excluded from primary correlation;
their exclusion count must be reported. Unsupported and contradicted claims are never treated as
missing.

## Review process

- Two independent reviewers score all 150 answers.
- Reviewers receive question, reference answer, evidence, generated answer, citations, and
  abstention fields; they do not receive system ID or retrieval metrics.
- Reviewer sheets use identical protected fields and separate editable scoring fields.
- Disagreement occurs when total claim count differs or primary score differs by more than 0.10.
- Disagreements require adjudication without revealing system identity.
- Final analysis uses adjudicated claim counts, not average ordinal labels.

## Primary analysis

- Unit: answer, clustered by whole question.
- Association: Spearman correlation between MRR@10 and adjudicated claim-level faithfulness.
- Uncertainty: 10,000 whole-question bootstrap samples, seed 42, preserving five-system panels.
- Report rho, 95% percentile interval, answer N, question N, abstention exclusions, and missing N.

## Decision rule

H5 receives confirmatory support only if all conditions hold:

1. At least 30 questions and 150 answers pass validation.
2. At least 80% of answers contain one or more verifiable claims.
3. Faithfulness has at least 0.10 observed standard deviation and at least three distinct values.
4. Absolute Spearman rho is below 0.20.
5. Entire 95% bootstrap interval lies inside [-0.30, 0.30].
6. Sensitivity analyses do not reverse the conclusion.

If conditions 1–3 fail, verdict is `not_estimable`. If conditions 4–6 fail, H5 is `not_supported`.
Statistical non-significance alone does not support H5.

## Sensitivity analyses

- Reviewer A and Reviewer B scores before adjudication.
- Complete-case analysis.
- Conservative scoring where partial support receives zero credit.
- Exclusion of abstentions.
- System-stratified and category-stratified descriptive correlations; no additional confirmatory
  claims.

## Integrity rules

- No question, answer, evidence, score, threshold, or exclusion rule may change after freeze.
- No reviewer may access sealed system mapping before adjudication completion.
- Phase 8 results remain unchanged regardless of follow-up outcome.
- Follow-up may support, reject, or leave H5 not estimable; data must not be selected to force a
  preferred verdict.
