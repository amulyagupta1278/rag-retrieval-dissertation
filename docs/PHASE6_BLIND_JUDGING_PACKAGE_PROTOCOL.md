# Phase 6 Blind Judging-Package Protocol

This checkpoint creates an offline owner-review package only. It performs no
judging, adjudication, agreement calculation, retrieval evaluation, hypothesis
test, answer generation, or API call.

## Allowed inputs

- Phase 5F final blind pool: 755 unique pairs, SHA-256
  `ff48c3413e891377b3b7e035a35902146d2e9e3be088457f9d37f91d0b6c468f`;
- owner-approved R5 QA: question and reference answer only;
- frozen chunk metadata: candidate text and document ID only;
- frozen document metadata: source-document title only.

No sealed provenance, source system, rank, score, qrels, current-gold status,
predicted relevance, retrieval metric, or existing owner label enters package
construction.

## Reviewer columns

Each CSV row contains `display_id`, `query_id`, `question`, `reference_answer`,
`chunk_id`, `source_document_title`, `candidate_chunk`, blank
`relevance_grade`, and blank `rationale`. Row order and display IDs exactly match
the frozen Phase 5F blind pool.

When separately authorized, owner uses:

- `2`: candidate directly supports the reference answer;
- `1`: useful context but insufficient alone;
- `0`: irrelevant or misleading;
- `U`: unclear and requires adjudication.

Same-document membership is not evidence of relevance. System performance must
remain hidden while grading. This commit stops before any grade is entered.

## Deterministic rebuild

```bash
python scripts/build_phase6_blind_judging_package.py --overwrite
```
