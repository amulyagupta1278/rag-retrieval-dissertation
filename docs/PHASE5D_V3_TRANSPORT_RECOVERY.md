# Phase 5D V3 Transport-Recovery Protocol

V3 is separate recovery after V2 full run stopped on first request without HTTP
status or returned usage. V2 terminal ledger, failure record, trace evidence, and
approval remain immutable. V3 writes only under
`runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/` and never selects, merges,
resumes, or backfills from V2 output.

## Unchanged retrieval contract

- model `claude-haiku-4-5-20251001`;
- exact V2 fixed-key schema;
- identical prompt bytes and SHA-256;
- identical 34 questions and frozen BM25 top-50 candidates;
- remaining scope is same 26 non-trace primary queries in same order;
- integer 0–3 score anchors and score-descending/chunk-ID-ascending ranking;
- temperature, maximum output, SDK, service tier, tools, caching, and streaming;
- zero automatic retries, fallback, backfill, answer generation, or result
  selection.

Each V3 query receives one new network attempt. This is separately authorized
recovery, not retry inside failed V2 run. Any ambiguous dispatch, connection
failure, timeout, HTTP failure, model/schema failure, budget breach, or malformed
response terminates V3.

## Ambiguous-billing budget

Recorded cumulative spend is $1.040028, but failed V2 dispatch may have been
billed. V3 reserves 40,000 input tokens plus maximum 2,048 output tokens for that
attempt: $0.050240. Largest observed trace request used 30,645 input tokens, so
input reserve adds 9,355 tokens (30.527%); exact failed-request usage remains
unverified.

Recovery itself retains prior 792,820-token input budget and maximum 53,248
output tokens: $1.059060. Reserved prior exposure is $1.090268. Budgeted
cumulative worst case is $2.149328 under proposed $2.15 cap, leaving $0.000672.
Provider usage remains authoritative and is added before content validation.

## Gates

V3 runner must verify every V2 trace/failure hash, exact request payload hashes,
26-query scope, pending separate approval, request cap, and empty V3 output root.
No live call occurs until offline tests, secret scan, manifest verification, and
commit complete, followed by exact commit-bound owner live approval.
