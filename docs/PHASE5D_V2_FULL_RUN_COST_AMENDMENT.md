# Phase 5D V2 Full-Run Cost Amendment

This additive amendment raises cumulative hard cost cap from $1.90 to $2.10 for
26 remaining primary queries. It does not change model, V2 fixed-key schema,
prompt, candidates, scoring, ranking, SDK, request controls, or no-retry policy.
Committed 24-call trace and V1 failure evidence remain immutable.

## Budget

Observed cumulative spend through trace is $1.040028. Earlier provider counting
measured 771,768 input tokens for remaining 26 payloads. Trace response usage was
two input tokens per request above pre-count, so corrected remaining count is
771,820. Maximum output is 53,248 tokens. Corrected-count worst case is
$1.038060; cumulative worst case is $2.078088.

Runtime additionally reserves 21,000 input tokens for counting uncertainty.
Budgeted remaining input ceiling becomes 792,820 tokens. Budgeted cumulative
worst case becomes $2.099088, leaving $0.000912 beneath $2.10 cap. Actual provider
usage remains authoritative and enters durable ledger before content validation.

## Execution boundary

- Only 26 non-trace primaries may run, in frozen query order.
- Trace primaries and replicates may not rerun.
- Call 27 is refused.
- No retry, fallback, backfill, output selection, relevance metrics, pool
  expansion, generation, or owner judging occurs during full retrieval run.
- Any ambiguous dispatch, provider failure, model drift, schema failure, input
  budget breach, or cost-cap breach terminates run.
- Full output writes only under
  `runs/v2/phase5d_prompt_rag_claude_v2/full/`; trace directory is read-only.

Live execution remains blocked until amendment is committed and owner supplies
exact commit-bound approval statement.
