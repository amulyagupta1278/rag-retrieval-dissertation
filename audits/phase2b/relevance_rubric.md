# Phase 2B Relevance Rubric

Grade each query/chunk pair without viewing system provenance.

- `2`: Directly supports reference answer.
- `1`: Useful context, but insufficient alone.
- `0`: Irrelevant or misleading.
- `U`: Unclear; requires adjudication.

Rules:

- Do not infer relevance from same document or scheme.
- Judge chunk text against question and reference answer.
- Ignore expected system performance.
- Add rationale for `U` and any difficult boundary decision.
- Leave no row blank before submission.

Current qrels are non-exhaustive direct-gold judgments. This package remains provisional until Graph candidates are added and judged.
