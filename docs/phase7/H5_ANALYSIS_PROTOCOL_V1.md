# Phase 7 H5 Analysis Protocol

Status: frozen before generation results; analysis not executed.

H5 examines associations between retrieval evidence quality and downstream answer
quality. It does not establish causality.

## Outcomes

- retrieval relevance versus answer correctness;
- Complete Evidence Recall versus answer completeness;
- retrieval quality versus faithfulness;
- citation accuracy by retrieval system;
- unsupported claims by system;
- abstention quality by system.

## Analysis

- Pair systems at query level; preserve all 34 questions and category summaries.
- Use 10,000 paired whole-query bootstrap resamples with seed 42.
- Use paired randomization for frozen directional comparisons where applicable.
- Apply Holm correction across frozen confirmatory comparisons.
- Report point effects, 95% intervals, raw p-values, Holm-adjusted p-values, query N,
  missing-output N, and category N.
- Primary missing-output display retains failures as missing/failed generation.
- Sensitivity displays use conservative worst-quality assignment and complete-case
  results; neither replaces primary reporting.
- Do not average metrics into a composite score.
- Do not make causal or universal-winner claims.

Analysis begins only after generation completion, quality-evaluation freeze,
approved judging, and finalized labels.
