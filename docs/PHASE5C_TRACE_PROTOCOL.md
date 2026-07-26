# Phase 5C Gemini Trace and Repeatability Protocol

## Scope

Phase 5C executes only frozen Prompt-RAG trace gate. It does not calculate
relevance metrics, expand blind pool, run remaining 26 primary queries, generate
answers, or expose owner judgments.

System remains frozen BM25 top-50 to Gemini relevance reranker. No prompt, model,
provider, candidate, ordering, scoring, retry, or ranking parameter may change.
Pre-result implementation-validity correction changes only Gemini structured-
output wire field from `responseSchema` to `responseJsonSchema`.

## Preconditions

Every precondition must pass before client creation:

1. Phase 5B implementation and Phase 5C evaluator committed.
2. Frozen code, config, prompt, queries, chunks, BM25 rankings, trace selection,
   token audit, and request hashes match committed manifests.
3. Working tree differs from HEAD only through exact unstaged owner runtime-control
   records permitted for trace mode.
4. Owner manually confirms active Google AI Studio project shows Plan `Free`, has
   no linked billing account, and current `GEMINI_API_KEY` environment context is
   unchanged.
5. Free-tier confirmation is no more than 24 hours old and binds frozen config.
6. Separate trace approval binds exact Git commit/tree, config, prompt, 24-call
   plan, and free-tier confirmation hash.
7. Replacement credential remains environment-only. No credential value enters
   repository or logs.

## Frozen execution

- Provider: Google Gemini Developer API.
- API: stable `v1` `generateContent`.
- SDK: `google-genai==2.13.0`.
- Requested model: `gemini-2.5-flash`.
- Temperature: 0.
- Thinking budget: 0.
- Candidate count: 1.
- Streaming/tools/search/grounding/caching/file access: disabled.
- One query plus all frozen 50 BM25 candidates per request.
- Strict 50-item candidate-score response schema.
- Standard JSON Schema sent through `responseJsonSchema`.
- Score range: integer 0–3.
- Ranking: score descending, then chunk ID ascending.
- No fallback, backfill, answer generation, or BM25-rank tie-break.

Trace query IDs, in frozen order:

1. `v2q-017`
2. `v2q-016`
3. `v2q-003`
4. `v2q-023`
5. `v2q-013`
6. `v2q-025`
7. `v2q-004`
8. `v2q-027`

Each query runs primary, replicate 1, and replicate 2. First valid execution is
primary. Replicates are audit evidence; best replicate is never selected.

Trace contains 24 logical calls and hard cap of 24 attempted requests. Every
attempt is durably counted before dispatch. Retries consume cap. `429` stops
without retry. Resume after quota reset requires separate owner approval and
unchanged frozen payloads.

Offline token envelope:

- input: 604,005 tokens;
- maximum response-contract output: 45,186 tokens;
- provider usage metadata becomes authoritative after execution.

Cost may be recorded as `$0.00` only after valid free-plan/no-billing confirmation.
Billing enablement, credits, paid fallback, model substitution, alternate key, or
alternate project are prohibited.

## Trace outputs

Runner preserves:

- credential-free request;
- raw response;
- response ID and modelVersion;
- provider usage, finish, and safety metadata;
- timestamps and sanitized attempt history;
- request/response hashes;
- durable attempt ledger.

Terminal HTTP `400` V1 attempt remains preserved under
`runs/v2/phase5b_prompt_rag/`. Corrected run writes only under
`runs/v2/phase5b_prompt_rag_response_json_schema_v2/`; V1 ledger cannot resume.

All returned `modelVersion` values must match. Any missing/extra/duplicate chunk,
changed ID, invalid score, malformed output, refusal, block, truncation, metadata
failure, or modelVersion mismatch is terminal. Failed scope remains failed; no
ranking replacement occurs.

## Repeatability evaluation

Evaluator independently validates exactly 24 raw records against frozen request
hashes and recomputes all pairwise comparisons among three executions per query.

Preregistered thresholds, required for every pair:

- candidate score agreement: at least 0.90;
- Kendall tau-b over score vectors: at least 0.90;
- identical deterministic rank positions: at least 0.80;
- Spearman rank correlation: at least 0.95;
- top-10 overlap: at least 0.90.

Evaluator also reports trace-only operations: successful primary coverage,
attempts, retries, failures, quota stops, refusals/blocks, malformed outputs,
mean/median/p95 latency, provider input/output/thinking/cached/total tokens,
returned modelVersion, and conditional zero cost.

No qrels, reference answers, categories, relevance metrics, sealed provenance, or
owner judgments enter runner or evaluator.

## Commands

After approval records are valid:

```bash
python scripts/run_phase5b_prompt_rag.py \
  --mode trace \
  --require-free-tier-owner-confirmation
```

After complete 24-call trace:

```bash
python scripts/evaluate_phase5c_trace.py
```

## Stop rule

After repeatability evaluation, stop for owner approval regardless of pass/fail.
Full mode remains unauthorized. Failed repeatability blocks full execution and
does not permit prompt/model tuning. Passed repeatability still requires separate
full-run approval.
