# Prompt-RAG Retrieval Protocol V1 — Phase 5A Candidate

Status: **NOT FROZEN; EXECUTION PROHIBITED; OWNER ARCHITECTURE CHOICE REQUIRED**

Recorded: 2026-07-26

Repository HEAD at entry: `70de0fd17f825ca04527c7ff50f91a2e5959a084`

Branch: `codex/dissertation-rebuild-v2`

## 1. Scope and stop boundary

Phase 5A defines Prompt-RAG retrieval/reranking only. It does not authorize an
API call, retrieval run, answer generation, metric calculation, pool expansion,
owner-label inspection, H4/H5 verdict, or commit. H5 answer generation,
faithfulness, and completeness require a separate protocol after retrieval
systems and pooled judgments are complete.

The repository does not define a unique Prompt-RAG architecture. This protocol
therefore records the evidence, alternatives, recommendation, common safety
contract, and unresolved choices, then stops for owner approval. The placeholder
prompt must never be sent to a model.

## 2. Starting checkpoint

- Phase 4 exists at commit `70de0fd17f825ca04527c7ff50f91a2e5959a084`
  (`feat: complete Phase 4 hybrid RRF evaluation`).
- The working tree was clean before Phase 5A files were created.
- Python is CPython 3.12.2 at
  `/Users/amulyagupta/.pyenv/versions/3.12.2/bin/python` on arm64 macOS.
- Installed versions and the protected Phase 0–4 checkpoint manifest hash are recorded in
  `audits/phase5a/leakage_boundary.json`.
- `docs/EXPERIMENT_PROTOCOL_V2.md` has SHA-256
  `78547d0fc4a81ae64303103b22f577366a0d7895d8e5dbe94b0e417e366115b7`
  and is not modified; hypotheses remain unchanged.
- The current blind pool has 620 unique query/chunk rows. All 620
  `relevance_judgment` and `reviewer_notes` fields are blank. Its SHA-256 is
  `5c424b6a0bbca1343499621c5fd705a904eaf11c1109824c3ec6094c0dc643e2`.

## 3. Verified historical meaning

Reachable documentation calls Prompt-RAG “Prompt-based retrieval (LLM-guided
reranking).” This is a documentation-only intended meaning, not a verified
implementation. No reachable provider integration, model selection, endpoint,
prompt, candidate generator, depth, batching contract, response schema, run, or
output artifact defines Prompt-RAG.

Reachable history contains local CrossEncoder reranking scripts. Those are
verified implementations of a different system, not Prompt-RAG. They inspect
qrels/categories and compare candidate modes/depths, making them obsolete and
invalid as a design source for this benchmark-blind Phase 5A protocol.

The evidence supports these classifications:

| Meaning | Finding |
|---|---|
| Query rewriting | No evidence found |
| LLM relevance scoring | Guidance is implied, but scoring is undefined |
| Reranking | Documentation-only intended family |
| Direct corpus selection | No evidence found |
| Multi-stage retrieval | Implied by reranking, but the first stage is undefined |
| Combination | No uniquely supported combination |

Detailed commit, blob, path, and content hashes are in
`audits/phase5a/history_and_claims_audit.json`. Any historical assertion of a
working Prompt-RAG/API system is **unsupported by committed artifacts**.

## 4. Architecture alternatives and recommendation

No alternative is selected or frozen.

| ID | Architecture | Candidate depth | Main validity consequence |
|---|---|---:|---|
| A | Frozen Phase 2A BM25 candidates, then LLM relevance reranking | 50 | Reranker is bounded by BM25 candidate recall |
| B | Frozen Phase 4 Hybrid candidates, then LLM relevance reranking | 50 | Prompt-RAG inherits Hybrid and cannot isolate the reranker cleanly |
| C | LLM relevance scoring over all frozen chunks | 140 | Avoids a first-stage ceiling but is direct corpus scoring, not the documented reranker |
| D | LLM query rewriting followed by retrieval/reranking | unresolved | Unsupported by history and adds prompt/tuning degrees of freedom |

Recommendation: **A, pending explicit owner approval**. The basis is structural:
it is the simplest auditable staged system consistent with “LLM-guided
reranking,” with a deterministic first stage and an explicit candidate ceiling.
The recommendation is not based on BM25, FAISS, Graph, or Hybrid performance.

The owner must select the architecture before an actual prompt is authored. The
owner must also select the provider/model/version; likely benchmark gain is not a
permitted selection criterion.

## 5. Fair-comparison and leakage boundary

Every authorized future run must:

1. Use the exact frozen 140-chunk corpus and all 34 R5 questions.
2. Keep chunk IDs as retrieval units.
3. Expose only `query_id` and `question` from a query, and only `chunk_id`,
   `text`, and `source_title` from each candidate.
4. Never expose qrels, reference answers, categories, gold evidence, metrics,
   sealed provenance, owner judgments, system identity, or hidden gold status.
5. Use no benchmark training, benchmark-sensitive tuning, manual query-specific
   rules, or results-guided prompt changes.
6. Label a staged system as a reranker and report its generator, depth, and
   per-query/aggregate candidate-recall ceiling.
7. Preserve missing/invalid responses as failures. Never backfill or substitute
   BM25, Hybrid, or another system.
8. Preserve negative or weak Prompt-RAG results.

An audit incident is recorded: a broad Git-history search displayed a current
Phase 4 manifest containing metric material. No metric was used or copied into
the architecture, prompt, provider/model choice, or config. Because this design
is still blocked and non-executable, owner approval remains mandatory before any
freeze. See `audits/phase5a/leakage_boundary.json`.

## 6. Proposed common response contract

This contract is proposed for the reranking alternatives and is testable before
a provider is selected:

```json
{
  "candidate_scores": [
    {"chunk_id": "<candidate chunk ID>", "score": 0.0}
  ]
}
```

- The response must contain every and only the supplied candidate ID exactly
  once.
- Scores must be finite JSON numbers; higher means more relevant.
- Rank by descending score, breaking exact ties by ascending chunk ID.
- Missing, extra, duplicate, malformed, or non-finite entries fail the affected
  query/batch. There is no fallback.
- The top-50 output has one row per frozen query; known unique chunk IDs; ranks
  `1..min(50, candidate_depth)`; retained raw scores; and explicit failure state
  without backfill.

`src/retrievers/prompt_rag_contract.py` contains only offline input validation,
strict parsing, and deterministic ordering. It performs no retrieval or network
activity.

## 7. Parameters that must be frozen before execution

The following are deliberately unresolved: provider; exact immutable model and
version; endpoint; declared SDK and version; candidate generator/depth; actual
prompt; batch size; context window; temperature; seed; top-p; output token limit;
timeout; retry count/schedule; rate-limit behavior; and repeatability repetitions.

Already fixed as design constraints:

- Candidate ordering, once a generator is approved: query ID ascending, then
  first-stage rank ascending.
- No silent truncation, dropped candidate, duplicate, fallback, or backfill.
- No credentials in repository artifacts or logs.
- Exact raw request/response preservation after credential exclusion, with a
  redaction log.
- Token, latency, cost, retry, and error accounting includes failed attempts.
- No metrics until the structural trace gate passes.

The candidate config is `configs/prompt_rag_v1_candidate.json`. It has
`execution_authorized: false`. The prompt file SHA-256 is
`e95c6936d1b7a7e2dfed58c8cd753c1e58b8b77252d2eb462e0d28fb2074c35d`,
but the file is an explicit non-executable placeholder, not a frozen prompt.

## 8. Trace and stop gates

After owner architecture approval but before any results:

1. Select trace query IDs by a documented structural rule that cannot use
   categories, qrels, answers, metrics, provenance, or performance traces.
2. Freeze those IDs, the actual prompt/hash, and every provider/runtime field.
3. Execute only the authorized trace gate.
4. Stop on any candidate-set mismatch, truncation, parse/schema error, duplicate,
   provider/model mismatch, secret exposure, invalid trace, or unexpected
   fallback behavior.
5. Calculate no retrieval metrics until the owner accepts the trace gate.
6. Expand no pool until a valid complete ranking run exists.
7. Begin no owner judging until Prompt-RAG candidates join the final system union.

## 9. Calls, tokens, cost, latency, and failures

For alternatives A/B, 34 queries × 50 candidates = 1,700 candidate judgments.
Calls would be 170, 68, or 34 for batch sizes 10, 25, or 50 respectively. At a
planning-only 300–600 candidate-text tokens per chunk, candidate text alone is
about 510,000–1,020,000 input tokens, excluding instructions, questions, JSON,
outputs, and retries.

For alternative C, 34 × 140 = 4,760 candidate judgments. Calls would be 476,
204, or 102 for batch sizes 10, 25, or 50. Candidate text alone is about
1,428,000–2,856,000 input tokens under the same planning range.

An exact token or monetary estimate is not valid until provider/model/tokenizer,
actual prompt, batching, and an authoritative price snapshot are frozen. No live
price lookup or API call was made. Full accounting and fail-closed policies are
in `audits/phase5a/cost_and_failure_policy.json`.

## 10. Freeze-readiness decision

Phase 5A is **not freeze-ready**. The owner must approve an architecture and
first-stage generator, provider/model/version/SDK, batching, actual prompt,
generation controls, timeout/retries, and repeatability plan. The detailed
20-item decision is in `audits/phase5a/freeze_readiness.json`.

Until then, the mandatory stop remains in force: no Prompt-RAG execution, API
call, retrieval result, metric, answer, pool addition, owner judgment, H4/H5
verdict, or commit.
