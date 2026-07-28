# Phase 8 Exploratory Automated Expansion Status

Status: `exploratory_automated_only_pending_human_validation`

## Outcome

Existing `v3_clean` release already exceeds historical 45/70-document targets:

- 130 accepted documents;
- 856 chunks;
- 100 generated questions;
- 140 generated qrels;
- BM25, FAISS, and entity-co-occurrence graph retrieval runs.

Release manifests and referential integrity pass automated checks. No API calls,
new acquisition, judging, answer generation, or human approval occurred during
this audit.

## Validity boundary

Expansion is engineering evidence only. It is not final dissertation evidence.
Questions and qrels remain generated and unapproved. Existing benchmark audit is
`pending_human_review`, labels pool diagnostic-only, and records 32 category
contract failures. Some questions also contain time-sensitive claims or weak
reference-answer construction that need review.

Only three retrieval systems exist for expanded release. Hybrid RRF and
Prompt-RAG Claude were not rerun. Phase 7 generation and H5 were not rerun.
Therefore expanded metrics must not replace frozen 22-document, 34-question,
five-system pilot results.

## Allowed reporting

Allowed: "Automated exploratory expansion reached 130 documents and 856 chunks;
release integrity passed, while benchmark validity remained pending human review."

Not allowed: "Phase 8 final-scale benchmark is validated," "owner approved," or
"expanded results confirm pilot hypotheses."

Canonical machine-readable audit:
`audits/phase8_exploratory/automated_audit.json`.
