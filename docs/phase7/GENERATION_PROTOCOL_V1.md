# Phase 7 Claude Top-3 Generation Protocol

Status: frozen offline; live execution prohibited pending owner trace approval.

## Scope

Generate one evidence-grounded answer for each frozen query/retrieval-system pair:
34 R5 questions × 5 retrieval systems = 170 logical requests. Retrieval rankings,
ordering, scores, chunk text, and query text remain frozen. Generation does not
rerun or tune retrieval.

## Provider contract

- Provider: Anthropic Claude API, Messages endpoint `/v1/messages`.
- API version: `2023-06-01`.
- SDK: `anthropic==0.116.0`.
- Requested model: `claude-haiku-4-5-20251001`.
- Returned-model rule: exact string match only. Any difference is terminal
  `model_drift`; no alias or fallback is accepted.
- Context: first three available chunks in frozen retrieval order.
- Maximum output: 256 tokens.
- Temperature: 0, supported by installed SDK request contract.
- Stream: false. Tools: empty. Service tier: `standard_only`.
- Timeout: 120 seconds. Automatic retries: zero.
- No prompt caching assumption, tools, web, file access, best-of-N, fallback,
  response replacement, or result-dependent context changes.

Anthropic documents dated pre-4.6 identifiers as pinned snapshots. Serving
infrastructure may still change, so request and returned model strings, timestamps,
usage, response IDs, hashes, and latency must be retained.

## Blinding and context

Generator receives fixed prompt, question, anonymous evidence IDs E01–E03, exact
chunk text, and strict response schema. It never receives retrieval-system identity,
rank numbers, scores, qrels, reference answers, categories, grades, metrics, or
hypothesis results.

Canonical JSON serialization uses UTF-8, sorted keys, compact separators, and no
text normalization beyond JSON escaping. No evidence text is truncated. When a
frozen retriever returns fewer than three chunks, every available chunk is included
and missing positions are not padded.

## Response and failure handling

Every supported material claim requires inline `[E0N]` citations and matching
unique `cited_evidence_ids`. Insufficient evidence requires an empty answer, empty
citations, `abstained=true`, and nonempty reason. Optional claim mappings use only
supplied IDs.

All frozen failure classes are terminal. Zero retries. Ambiguous dispatch is treated
as potentially billed. No failed output is replaced. Completed output paths use
exclusive creation. Recovery requires a new path and separate owner approval.

## Execution sequence

1. Verify dependency and freeze manifests.
2. Verify commit-bound owner approval for trace only.
3. Run exactly ten frozen trace requests; stop on first terminal failure or cap risk.
4. Preserve trace checkpoint and report actual provider usage/cost.
5. Do not execute remaining 160 requests without separate owner approval.

Phase 7 freeze itself performs no credential access or API call.
