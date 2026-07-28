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

## Automated repair and rerun R3

R3 repaired all 32 category-contract failures using source-verbatim text. One
Mission Shakti gold chunk containing administrative boilerplate was replaced by
another chunk from same frozen official document. Strict automatic audit then
reported zero failures across gold resolution, source-document alignment, exact
answer support, cross-scheme cardinality, question uniqueness, and category
contracts.

Three available systems were rerun over 100 questions and 140 automated gold
judgments. Aggregate diagnostic results:

| System | MRR@10 | Recall@10 | nDCG@10 |
|---|---:|---:|---:|
| BM25 | 0.5813 | 0.7750 | 0.6017 |
| FAISS | 0.4662 | 0.6100 | 0.4637 |
| Entity-co-occurrence graph | 0.1537 | 0.3050 | 0.1756 |

R2 was invalidated because abbreviation-sensitive sentence splitting caused one
strict exact-support failure. R3 preserves contiguous verbatim source text.

R3 remains `pending_human_review`. Automated contract compliance does not make
questions natural, labels human-relevant, or results final evidence. Frozen BM25
and FAISS indexes also lack modern per-index `configuration_hash`; release-level
manifest integrity passes, but strict index-provenance mode does not.
