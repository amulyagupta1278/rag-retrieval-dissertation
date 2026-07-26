# Phase 5D Claude Provider-Recovery Protocol

Phase 5D preserves failed Gemini attempts and changes provider only. This is an
owner-directed deadline and credential-availability correction, not system
selection based on retrieval results.

## Frozen system

- First stage: byte-identical Phase 2A BM25 top-50.
- Second stage: one stateless Claude relevance-scoring request per query.
- Model: `claude-haiku-4-5-20251001`.
- SDK: `anthropic==0.116.0`; API version `2023-06-01`.
- Prompt: unchanged `prompts/prompt_rag_retrieval_v1.txt`.
- Structured output: strict `output_config.format` JSON Schema.
- Score: integer 0–3 with existing anchors.
- Ranking: score descending, then chunk ID ascending. BM25 rank never breaks ties.
- Temperature 0; thinking, tools, caching, and streaming disabled.
- Maximum output: 2,048 tokens; standard service tier only.
- No fallback, backfill, automatic retry, answer generation, or benchmark tuning.

Claude's wire-schema subset does not support `minimum`, `maximum`, `minItems`,
or `maxItems`. A pre-generation metadata check returned HTTP 400 until these
four constraints were removed. Wire schema still requires integer scores and
binds chunk IDs to exact 50-ID enum. Offline parser independently and strictly
requires 50 rows, one row per supplied ID, and integer scores from 0 through 3.
This compatibility correction occurred before any Claude generation.

Only query ID, question, chunk ID, and chunk text enter model request. Qrels,
reference answers, categories, metrics, sealed provenance, owner judgments,
first-stage ranks, and first-stage scores remain forbidden.

## Cost and failure gate

Claude API is paid. Current Haiku 4.5 list price is $1 per million input tokens
and $5 per million output tokens. Total run hard cap is $1.90, below owner's
previously disclosed approximate $2 remaining balance. Before generation, API
token-count endpoint must count all 34 unique frozen payloads. Worst-case cost
uses exact counted inputs and 2,048 output tokens for all 50 planned generations.
Execution refuses if estimate exceeds $1.90.

No automatic retry is allowed. Any timeout, connection failure, non-2xx status,
refusal, truncation, model mismatch, malformed schema, or ambiguous dispatch
stops scope. This prevents unknown duplicate billing. Actual input/output usage
and list-price cost are recorded after every valid response. Credential is read
only from `ANTHROPIC_API_KEY` and never serialized.

## Execution order

1. Freeze and test offline implementation.
2. Add `ANTHROPIC_API_KEY` to local environment or ignored `.env` loader context.
3. Run provider token count; this performs no generation.
4. Run 24-call trace: eight fixed query IDs, each primary plus two replicates.
5. Compute repeatability only. Failure blocks remaining calls; model/prompt tuning
   remains prohibited.
6. On pass, run remaining 26 primaries.
7. Freeze 34 primary top-50 rankings and add unseen top-10 pairs to blind pool.
8. Owner grades union pool. Retrieval metrics follow pooled judgments; answer
   generation remains separate.

Phase 5 cannot honestly finish owner judging without owner labels. Code must stop
at that boundary rather than invent judgments.
