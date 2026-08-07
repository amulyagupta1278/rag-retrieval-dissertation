# Phase 7 Generation Protocol — Draft

Status: `non_executable_draft_pending_phase6_and_owner_decisions`

## Boundary

Phase 7 remains blocked. No generation may run until completed 114-row human
regrade, agreement report, adjudication, frozen final pooled qrels, frozen Phase 6
retrieval metrics, and hash-verified rankings pass `phase7_gate.py`.

Planned panel contains 34 R5 questions × five frozen retrieval systems = 170 exact
query/system observations. Each pair receives one answer. No best-of-N, favorable
replacement, hidden retry, or result-dependent context choice is allowed.

## Frozen-input loader

Loader verifies SHA-256, exact query coverage, unique query IDs, unique ranked
chunk IDs, and complete five-system set. Systems are BM25, FAISS-windowed-max,
corrected Graph v3.2, Hybrid RRF, and Prompt-RAG Claude reranker. Rankings remain
immutable. Empty retrieval output remains empty evidence and may cause abstention.

## Context serialization

Serializer exposes question and ranked evidence text only. It removes retrieval
system identity, rank numbers, scores, qrels, metrics, categories, owner grades,
and reference answers. Evidence IDs are anonymized as `E01`, `E02`, and so on.
Frozen order is preserved. Candidate depths 3, 5, and 10 exist only for offline
token estimation; owner must select one before execution without observing
generation quality.

## Answer contract

Draft fields:

- `answer`: text;
- `cited_evidence_ids`: unique supplied IDs;
- `abstained`: boolean;
- `abstention_reason`: text;
- optional `claim_to_evidence`: provider-neutral mapping.

Every material claim must cite supporting supplied evidence. Insufficient evidence
requires explicit abstention. Invalid or unsupported citation IDs fail closed.

## Failure and attempt contract

Explicit terminal classes cover missing response, timeout, ambiguous dispatch,
non-2xx, refusal, safety block, truncation, malformed output, model drift, missing
usage, invalid or unsupported citations, duplicate response, and context mismatch.
Attempt ledger will record logical request ID, query ID, retrieval system, attempt,
request/response hashes, timestamp, returned model version, usage, latency, status,
failure class, billing ambiguity, and cumulative cost. Completed outputs cannot be
overwritten. Recovery requires separate approval and output path.

## Artifact lineage

Execution freeze must hash prompt, config, final qrels, five rankings, serialized
contexts, requests, responses, and evaluation records. Current planning manifest
contains no final qrels or execution hashes.

## Pending owner decisions

Provider, exact model/version, context depth, output-token cap, trace size, retry
policy, total monetary cap, and evaluator design remain unset. Draft prompt also
requires owner review. No credential, network, API, generation, or evaluation work
is authorized by this document.

