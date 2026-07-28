# Phase 5D V2 Fixed-Key Claude Trace Protocol

V2 corrects only V1 response serialization. V1 failure evidence remains byte-
preserved under `runs/v2/phase5d_prompt_rag_claude_v1/` and `audits/phase5d/`.
V2 starts from request one in `runs/v2/phase5d_prompt_rag_claude_v2/`. V1 and
V2 responses may never be selected, merged, backfilled, or compared to choose a
preferred output.

## Frozen retrieval contract

- Frozen Phase 2A BM25 top-50, same 34 queries and 140 chunks.
- Model `claude-haiku-4-5-20251001`; `anthropic==0.116.0`.
- Prompt bytes and SHA-256 unchanged.
- One stateless request contains query plus all 50 candidates in frozen BM25 order.
- Candidate rank and score remain hidden from model.
- Temperature 0, maximum output 2,048 tokens, standard service tier, no tools,
  thinking, caching, streaming, fallback, backfill, or automatic retry.
- Integer score anchors remain 0 through 3. Ranking remains score descending,
  then exact chunk ID ascending; BM25 rank never breaks ties.

`candidate_scores` is now an object with exactly 50 fixed properties. Each exact
supplied chunk ID is required once and maps to one integer. Both object levels
reject additional properties. Offline parser also rejects missing/extra IDs,
booleans, non-integers, values outside 0–3, refusals, truncation, model drift,
tools, and malformed envelopes.

## Trace and money gate

V1 spent $0.177402. Cumulative hard cap remains $1.90, leaving $1.722598 before
V2. Frozen V2 trace envelope is 705,963 input tokens plus at most 49,152 output
tokens across exactly 24 requests. V2 trace worst case is $0.951723; cumulative
worst case after trace is $1.129125.

Eight structurally selected query IDs run in fixed order: all primaries, then all
replicate-1 calls, then all replicate-2 calls. Runner counts each attempted call
before dispatch and refuses call 25. No retry occurs. Any provider, schema, model,
or content failure terminates trace. Billable response usage is added to durable
ledger before content validation, including contract-invalid HTTP-200 responses.
Ambiguous transport failures terminate with billing ambiguity recorded.

Only repeatability metrics follow trace. Retrieval relevance metrics, pool
expansion, answer generation, owner judging, and remaining 26 primaries remain
blocked. Live execution additionally requires exact owner statement bound to
committed freeze, config hash, and manifest hash.

## Gemini disposition

Gemini Phase 5C route is abandoned after preserved schema/API/model endpoint
failures. Its files are byte-preserved under `archive/phase5_gemini_failed/` with
original-path/hash index. Gemini code, commands, config, dependency, tests, and
run directories are absent from active Phase 5 manifests and execution paths.
