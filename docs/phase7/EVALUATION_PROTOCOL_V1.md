# Phase 7 Generation Evaluation Protocol

Status: preregistered before generation outputs; no evaluation executed.

## Mechanical validation

For all 170 planned records report schema validity, valid citation-ID coverage,
abstention rate, response failure rate, terminal failure class, latency, input/output
tokens, and cost. Failed or missing records remain failures; no imputation or
replacement.

## Answer-quality evaluation

Evaluate correctness, faithfulness, completeness, citation accuracy,
unsupported-claim severity, and abstention quality separately. No composite score.
No metric determines a universal winner.

Recommended hybrid process requires separate approval:

1. Blinded automated first pass labelled AI evaluation.
2. Deterministic 15% audit: exactly 26 of 170 records, selected by SHA-256 ordering
   with fixed seed 42.
3. Owner package hides retrieval-system identity and operational provenance.
4. AI/owner disagreements require explicit owner adjudication.
5. Judge provider, model, prompt, schema, cost cap, and execution require a separate
   freeze and approval. No judge calls are authorized by generation freeze.

Owner labels and system comparisons must not influence evaluation labels.
