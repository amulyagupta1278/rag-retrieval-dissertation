# Phase 9 H5 Final Report

Status: `complete_not_estimable_range_restriction`

## Validated panel

- Frozen answers: 150 across 30 questions and five retrieval systems.
- Reviewer A complete: 150/150.
- Reviewer B complete: 150/150.
- Reviewer claim-count agreement: 150/150 exact.
- Adjudication: 150 rows marked `NOT_REQUIRED`; final counts pass through identical reviews.
- Claim-bearing answers: 81.
- Abstentions with no verifiable claim: 69.
- Formula errors: 0.

Workbook SHA-256:
`3e77d5551779fd0a3a523bc3bde37f30a339b55806afd418527260df56163458`.

## Claim-level faithfulness

| Outcome | Count |
|---|---:|
| Total verifiable claims | 301 |
| Fully supported | 300 |
| Partially supported | 1 |
| Unsupported | 0 |
| Contradicted | 0 |

Claim-weighted faithfulness is `0.9983388704`. Row-level faithfulness has only two distinct values
and sample standard deviation `0.0111111111`.

## Primary H5 analysis

- Spearman MRR@10–faithfulness rho: `0.1487392237`.
- Whole-question bootstrap samples: 10,000, seed 42.
- Valid non-constant bootstrap samples: 6,471.
- 95% percentile interval: `[0.1188680510, 0.2562974692]`.
- Claim-bearing questions: 21/30.

## Preregistered decision

**H5 verdict: `not_estimable`.**

Preregistration requires faithfulness standard deviation of at least 0.10 and at least three
distinct values before testing the weak/non-monotonic association rule. Observed standard
deviation is 0.0111 with two values. Therefore, H5 cannot receive confirmatory support or a clean
rejection from this panel. Statistical non-significance is not used as evidence for H5.

## Sensitivity results

- Treating partially supported claims as zero credit increases SD only to `0.0222222222`; rho
  remains `0.1487392237`. Range criterion still fails.
- Legacy V1/V2 contract: 30 claim-bearing answers, SD `0.0182574186`, rho `0.2435351402`.
- V3 semantic contract: 51 claim-bearing answers, faithfulness constant at 1.0; rho not estimable.
- Two prompt-contract strata exist: 50 legacy answer records and 100 V3 answer records. This
  mismatch is disclosed and prevents an identical-prompt claim across all 150 answers.

## Interpretation

Generated non-abstaining answers are almost perfectly grounded in supplied evidence. Main
observed failure mode is over-cautious abstention, not hallucination: 69/150 outputs contain no
verifiable claim, while zero of 301 scored claims are unsupported or contradicted.

## Exploratory H5b: Retrieval Quality and Answer Coverage

Post-hoc H5b tested whether retrieval quality predicts answer production rather than
faithfulness. This analysis is exploratory because hypothesis was formulated after observing
H5 faithfulness ceiling; it cannot provide confirmatory evidence.

No retrieval association was statistically clear. All whole-query bootstrap 95% confidence
intervals crossed zero:

- MRR versus answered: Spearman rho = -0.091, 95% CI [-0.330, 0.166].
- nDCG versus answered: Spearman rho = 0.062, 95% CI [-0.198, 0.323].
- Recall versus answered: Spearman rho = 0.139, 95% CI [-0.140, 0.431].

Strong descriptive pattern was question-category dependence. Abstention rates were 90.0% for
entity-relation, 83.3% for multi-hop, 43.3% for terminology, and 6.7% for both exact-match and
paraphrase questions. Therefore H5b is exploratory and inconclusive, not strongly supported.

Defensible dissertation wording:

> H5 remained not estimable because generation faithfulness exhibited severe ceiling effects and
> insufficient variance. The follow-up nevertheless showed that hallucination was not the main
> failure mode: 300 of 301 claims were fully supported, one was partially supported, and none was
> unsupported or contradicted. Sixty-nine outputs abstained, indicating that answer coverage was a
> larger practical limitation than faithfulness.

## Canonical artifacts

- `runs/phase9_h5_followup/analysis/h5_final_results.json`
- `runs/phase9_h5_followup/analysis/h5b_abstention_results.json`
- `runs/phase9_h5_followup/analysis_freeze/sealed_mapping_150.jsonl`
- `runs/phase9_h5_followup/analysis_freeze/manifest.json`
- `docs/PHASE9_H5_CONFIRMATORY_PREREGISTRATION.md`
