# Phase 5F Prompt-RAG Pool Contribution Protocol

Phase 5F expands only the provisional blind retrieval pool. It does not read
qrels, owner judgments, reference answers, relevance labels, categories, or
metrics. It performs no API call, answer generation, evaluation, comparison,
agreement calculation, or hypothesis test.

## Frozen inputs

- Phase 5D V3 commit: `88c54c906e9ea4313a43664cd8b7b65e61ea5944`.
- Prompt-RAG rankings: `runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/complete_primary_rankings.jsonl`.
- Ranking SHA-256: `e665aa4dc80b468a0fc2af06173ab0e6963786a578653c9a9083e6ffa6b1e04f`.
- Existing blind pool: Phase 4 manifest-backed 620-pair pool, SHA-256
  `5c424b6a0bbca1343499621c5fd705a904eaf11c1109824c3ec6094c0dc643e2`.
- Existing sealed provenance: SHA-256
  `f15084529a8def018747947f2d48ea14a626ddcb75e1930e19927b759bf3e1fa`.

Every Phase 4 blind and sealed JSONL row is preserved byte-for-byte. Final files
interleave all rows using SHA-256 of display ID, independent of system, rank, and
score; new rows are not exposed as one contribution block. Prompt-RAG contributes
only unseen `(query_id, chunk_id)` pairs from each frozen primary top-10. New
display IDs continue each query's existing numeric sequence, but assignment order
uses SHA-256 of query/chunk IDs rather than retrieval rank.

## Blinding boundary

New blind rows contain only `display_id`, `query_id`, `question`, `chunk_id`,
`chunk_text`, blank `relevance_judgment`, and blank `reviewer_notes`. They contain
no system, rank, score, gold status, prediction, hash, or lineage field.

System identity, rank, score, frozen hashes, and source-record lineage exist only
under `sealed/`. Phase 6 reviewer packaging must consume only the final blind
pool; contribution-only and sealed files must not be shown during judging.

## Deterministic rebuild

```bash
python scripts/build_phase5f_prompt_rag_pool.py --overwrite
```

For a zsh wrapper, use `run_exit=$?`; `status` is reserved by zsh. No committed
wrapper remained active, so preserved Phase 5D execution evidence is unchanged.

Expected counts: 620 existing pairs, 340 Prompt-RAG top-10 pairs, 135 unseen
pairs, and 755 final deduplicated pairs. Phase 6 owner judging remains blocked
until this freeze is approved.
