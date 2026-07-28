# Phase 7 V2 Claude Top-3 Generation Recovery Protocol

Status: frozen offline; $3.00 cumulative owner cap passes; live trace still requires
commit-bound owner approval.

## Recovery boundary

V1 stopped after two attempts: one valid response, then terminal `max_tokens`
truncation for P7B002. V1 remains immutable and is never resumed, retried,
overwritten, deleted, relabelled, or reused as V2 output.

V2 is a separate protocol version and output root. Sole generation-contract change:
`max_tokens` increases from 256 to 512. Provider, exact model, prompt, schema,
top-3 contexts, 170-pair panel, rankings, serialization, temperature, citations,
abstention, zero-retry, no-fallback, failure, evaluation, and H5 contracts remain
unchanged.

## Trace and reuse

V2 uses the same deterministic ten logical trace IDs. Each V2 trace request is a
new protocol-version request, not a V1 retry. V1 responses cannot be reused.
A valid V2 trace response may count toward the final V2 panel only when its exact
canonical request SHA-256 equals the frozen V2 panel request SHA-256. Such a reused
record must not be billed again in full-panel execution.

Token-limit finish reason remains terminal `truncation`; partial content is invalid.
No retry, replacement, fallback, or best-of selection is allowed.

## Cost gate

Frozen pricing remains Anthropic Haiku input $1/MTok and output $5/MTok. V1 spent
$0.005847. Conservative V2 full-panel exposure plus ambiguous-dispatch reserve and
V1 spend totals $1.119437. Owner amended cumulative Phase 7 cap from $0.95 to
$3.00 before V2 freeze, leaving $1.880563 headroom after worst-case exposure.

Every dispatch must first account for V1 spend, actual V2 usage, all unexecuted V2
request envelopes, and ambiguous reserve. Cap failure occurs before network call.
