# Phase 9 H5c-v3 Citation-Syntax Recovery Amendment

Status: **freeze before provider execution**.

H5c-v2 stopped after request 19 because provider returned combined inline citation syntax
`[E01, E02, E03]`, while frozen validator accepted only adjacent syntax `[E01][E02][E03]`.
Response otherwise passed provider, JSON-schema, evidence-ID, claim-mapping, and abstention checks.
Eighteen valid v2 responses are not reused.

H5c-v3 is a fresh 60-request panel with new blinded IDs and separate outputs. All scientific
design, questions, contexts, conditions, model, temperature, 1,024-token output limit, zero-retry
rule, endpoint, scoring, analysis, and decision thresholds remain unchanged.

Two prespecified citation-syntax changes apply:

1. Prompt states that multiple inline citations must use adjacent tags.
2. Before existing semantic validation, deterministic normalization converts a bracket containing
   only comma-separated legal evidence IDs into adjacent tags. Example:
   `[E01, E02, E03]` becomes `[E01][E02][E03]`.

Raw provider response remains immutable. Normalization cannot add, remove, or change evidence IDs
and does not relax claim-to-evidence, citation-union, abstention, model, usage, or stop checks.
Original H5 remains `not_estimable`; H5c-v3 may support H5c only.
