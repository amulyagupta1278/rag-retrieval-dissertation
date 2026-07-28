# Phase 7 Final Status — Disclosed AI Evaluation

Status: complete as an exploratory, AI-evaluated pilot.

## Scope

- 170 generated answers: 34 questions × 5 retrieval systems.
- 170/170 generation records mechanically valid.
- 26 blinded records scored by the human owner across six frozen dimensions.
- 144 remaining records scored offline using pinned `all-MiniLM-L6-v2` revision
  `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` and a five-nearest-neighbor
  classifier trained on the 26 owner records.
- Human-owner scores override automated predictions for all 26 audited records.
- No additional provider/API calls were made.

These results must not be described as 170 human-reviewed answers. Accurate wording:
"170 answers received disclosed automated quality evaluation, with a frozen 26-answer
blinded human-owner audit."

## Audit agreement

Leave-one-owner-row-out exact agreement was 88.46% for correctness, 96.15% for
faithfulness, 96.15% for completeness, 92.31% for citation accuracy, 92.31% for
unsupported-claim severity, and 88.46% for abstention quality. Correctness kappa was
0.7011, completeness kappa 0.9065, and abstention-quality kappa 0.6929. Kappa was zero
for three highly imbalanced dimensions because automated predictions contained only
the majority class; high raw agreement must not be interpreted as strong reliability
for those dimensions.

## H5

Whole-query bootstrap used 10,000 resamples, seed 42, preserving each five-system
query panel. Main exploratory associations:

| Retrieval measure | Generation measure | Spearman rho | 95% bootstrap interval |
|---|---|---:|---:|
| MRR@10 | Faithfulness | -0.0333 | [-0.0672, -0.0256] |
| MRR@10 | Correctness | 0.1753 | [0.0255, 0.3396] |
| Graded nDCG@10 | Correctness | 0.2700 | [0.1362, 0.3848] |
| Complete Evidence Recall@10 | Completeness | 0.3395 | [0.1581, 0.5067] |

MRR had almost no monotonic relationship with faithfulness, while evidence-coverage
measures had modest positive relationships with correctness and completeness. This is
consistent with treating retrieval and generation as separate evaluation layers, but
H5 receives no confirmatory supported/not-supported verdict because the frozen protocol
did not define a minimum effect or decision threshold.

## Limits

- Automated labels dominate the panel (144/170).
- Human audit contains 26 records and is not independent inter-rater evaluation.
- Faithfulness, citation accuracy, and unsupported-claim labels are strongly imbalanced.
- Only 6,387/10,000 MRR–faithfulness bootstrap samples produced defined correlations;
  remaining samples had constant faithfulness values.
- Results remain exploratory pilot evidence; no causal or universal-winner claim follows.
- No quality dimensions were combined into a composite score.

Canonical artifacts:

- `runs/v2/phase7_generation_claude_top3_v2/evaluation_v2_ai/final_quality_labels_170.jsonl`
- `runs/v2/phase7_generation_claude_top3_v2/evaluation_v2_ai/ai_owner_agreement.json`
- `runs/v2/phase7_generation_claude_top3_v2/evaluation_v2_ai/h5_results.json`
- `audits/phase7_generation/v2/evaluation_v2_ai/freeze_manifest.json`

The earlier `evaluation_v1` H5 gate remains preserved as truthful historical evidence of
the state before explicit owner authorization for disclosed AI evaluation.
