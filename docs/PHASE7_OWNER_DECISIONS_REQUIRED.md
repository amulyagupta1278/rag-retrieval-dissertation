# Phase 7 Owner Decisions Required

Phase 7 cannot execute until Phase 6 human regrade, adjudication, final qrels, and
retrieval metrics are frozen.

Owner must choose and freeze, without using generation results:

1. provider and exact returned-model/version policy;
2. one context depth: top-3, top-5, or top-10;
3. output-token cap;
4. trace size: 10, 15, or 20 calls;
5. retry and ambiguous-dispatch policy;
6. total monetary hard cap;
7. answer evaluator: human-only, LLM judge, or hybrid;
8. final prompt wording and response schema.

Existing repository records support only one priced example: Anthropic
`claude-haiku-4-5-20251001` at frozen Phase 5D assumptions of $1/M input tokens and
$5/M output tokens. These are historical repository assumptions, not newly checked
live pricing. Any other provider/model has `owner verification required` status.
No option is selected or recommended here.

Offline evidence-character estimates for full 170-call panel:

| Context | Input-token estimate | Best case | Expected | 512-token hard-cap scenario |
|---|---:|---:|---:|---:|
| top-3 | 265,089 | $0.319489 | $0.373889 | $0.700289 |
| top-5 | 415,806 | $0.470206 | $0.524606 | $0.851006 |
| top-10 | 793,540 | $0.847940 | $0.902340 | $1.228740 |

Estimates use `ceil(evidence characters / 4) + 200` per request and are not
model-compatible token counts. Recalculate offline after owner freezes provider,
model, tokenizer, context depth, and output cap. Latency remains unknown until an
approved trace.

