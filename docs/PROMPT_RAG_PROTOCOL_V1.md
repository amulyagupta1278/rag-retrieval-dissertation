# Prompt-RAG Retrieval Protocol V1 — Phase 5B Offline Freeze

Status: **OFFLINE FROZEN; LIVE API EXECUTION PROHIBITED PENDING OWNER APPROVAL**

Phase 5A commit: `d9689aeae520ed24a5f0c409a18134f5f9042e0f`

Recorded: 2026-07-26

Branch: `codex/dissertation-rebuild-v2`

## 1. Scope and boundary

Prompt-RAG is a retrieval reranker, not answer generation. It reranks frozen
Phase 2A BM25 top-50 chunks for each of the 34 frozen R5 questions. Phase 5B
freezes its offline contract only. It does not authorize credentials, live API
requests, retrieval results, metrics, pool expansion, owner judging, generation,
H4/H5 verdicts, or commit.

Hypotheses remain unchanged. Negative or weak future results must be preserved.

## 2. Phase 5A lineage and provider correction

Phase 5A found only a documentation-level historical meaning: “LLM-guided
reranking.” No historical Prompt-RAG implementation uniquely defined provider,
model, prompt, candidates, or API behavior. Phase 5A recommended architecture A
for structural simplicity and committed its blocked design gate at `d9689ae`.

Owner then approved architecture A. OpenAI was considered and rejected because
no approved OpenAI credential infrastructure was available. Owner corrected the
provider to Google Gemini Developer API, using existing Gemini credential
infrastructure and free-tier availability. This was an owner-approved design
correction based on cost, reproducibility controls, and operational access—not
expected benchmark performance. No retrieval result informed the correction.

## 3. Frozen architecture

- System: `Prompt-RAG-Gemini-2.5-Flash-BM25-50`
- First stage: byte-preserved Phase 2A BM25 top-50.
- Second stage: one Gemini relevance-scoring request per query.
- Request count: 34 primary requests; one query plus all 50 candidates each.
- Candidate order: frozen BM25 rank order.
- Candidate fields exposed: `chunk_id`, `text`.
- Query fields exposed: `query_id`, `question`.
- Hidden: BM25 rank/score, category, qrels, answers, gold evidence, metrics,
  sealed provenance, owner labels, and system identity.
- Output: 50 integer scores, then score-descending/chunk-ID-ascending ranking.
- Exact ties never use BM25 rank.

BM25 order remains visible through position because architecture requires it.
Prompt states position is not evidence. Potential order bias remains disclosed;
no post-result reorder experiment or prompt tuning is permitted.

Source ranking SHA-256:
`93b42dc121927561bf880cbe44ccf264c60bac1196adac08ce3d6d5e80d2db6a`.
Its bytes remain unchanged. Because source rows also contain a forbidden
`category` field, live preparation must use derived query/chunk-only ranking
`audits/phase5b/bm25_top50_query_chunk_only.jsonl`, SHA-256
`323f325bb730f3d0a0a5e37b7938d96090d831d5569fc2ae91330ec0c2f59390`.
The derivation preserves all 34 × 50 chunk orders exactly and discards rank,
score, and category before the API boundary.

## 4. Frozen Gemini controls

| Control | Value |
|---|---|
| Provider | Google Gemini Developer API |
| Model request string | `gemini-2.5-flash` |
| API version | `v1beta` |
| Endpoint family | `models.generateContent` |
| SDK | `google-genai[local-tokenizer]==2.13.0` |
| Request style | stateless, non-streaming, one request/query |
| Temperature | `0` |
| Thinking budget | `0` |
| Response candidate count | `1` |
| Maximum output tokens | `4096` |
| Response MIME type | `application/json` |
| Tools/search/URL context/code/file search | absent/disabled |
| Cached content | absent |
| Safety settings | provider defaults; any block is terminal |
| Timeout | 120,000 ms per attempt |
| Attempts | maximum 3; SDK internal attempts fixed at 1 |
| Retry delays | 1 s, then 2 s; no jitter |
| Retried HTTP statuses | `408`, `500`, `502`, `503`, `504` |
| HTTP 429 | immediate quota stop; never retried in same execution |

Top-p, top-k, and seed are omitted because owner did not freeze them. No value is
invented. Credentials may come only from `GEMINI_API_KEY` in the environment and
must never enter config, request, response archive, logs, errors, or Git.

`gemini-2.5-flash` is a stable model name, not a dated immutable snapshot.
First valid trace response establishes returned `modelVersion`. Every later
trace, replicate, and full-run response must match exactly; mismatch aborts run.

## 5. Prompt and scoring contract

Frozen prompt: `prompts/prompt_rag_retrieval_v1.txt`

SHA-256: `64be8830d92ecbfa378e6259aa65670675ff3bf1aa9e19b9934c08f1f19373d9`

Integer scale:

- `0`: irrelevant, misleading, or no useful evidence.
- `1`: related background, unlikely to answer a material part alone.
- `2`: concrete evidence useful for a material part.
- `3`: direct, specific evidence strongly addressing the question or an
  essential answer element.

Per-request response schema requires exactly 50 objects, exact supplied chunk
IDs through a dynamic enum, integer score `0..3`, required fields, and no extra
properties. Client still validates candidate completeness and uniqueness because
JSON Schema cannot prove all enum values occur once.

### Pre-result schema-field validity correction

First authorized network attempt returned terminal HTTP `400` before any valid
response. V1 had passed standard lower-case JSON Schema through SDK field
`response_schema`, serialized as API field `responseSchema`. `google-genai`
documents `response_schema` as its OpenAPI-subset path and assigns standard JSON
Schema to `response_json_schema`, serialized as `responseJsonSchema`. Corrected
contract uses `responseJsonSchema`; schema content, prompt, model, candidates,
score scale, and ranking remain unchanged. Exact provider error detail is not
available because frozen secret-safe policy discards provider error bodies, so
this cause is strongly supported rather than independently proven from body.

Failed V1 run stays immutable under `runs/v2/phase5b_prompt_rag/`. Corrected
execution uses `runs/v2/phase5b_prompt_rag_response_json_schema_v2/`; it cannot
resume or overwrite V1 ledger. Correction occurred with zero valid responses and
before any relevance metrics, making it implementation-validity repair rather
than benchmark-sensitive tuning.

First V2 request then returned terminal HTTP `404` with zero valid responses.
Official SDK defaults Gemini Developer API to `v1beta`; current
`generateContent` examples use `v1beta`, while current stable `v1` guidance
demonstrates Interactions API. Owner approved narrow API-version correction to
`v1beta` without changing model, prompt, candidates, schema, scoring, ranking, or
trace selection. V2 remains immutable under
`runs/v2/phase5b_prompt_rag_response_json_schema_v2/`; V3 writes only under
`runs/v2/phase5b_prompt_rag_v1beta_v3/`.

Malformed JSON; missing, extra, duplicate, or changed IDs; boolean/float or
out-of-range scores; blocks; refusals; truncation; missing metadata; non-text
parts; and unexpected tool calls are terminal failures. Failed queries receive
no ranking, fallback, or backfill.

## 6. Zero-charge execution gate

Experiment monetary charge must remain exactly `$0`. Before any request, owner
must manually confirm Google AI Studio project shows **Plan: Free** and has no
linked billing account. Confirmation uses
`audits/phase5b/free_tier_owner_confirmation.json`, tied to frozen config
SHA-256. It stores no key, project ID, billing identifier, or screenshot.
Confirmation must cover current process environment and active credential context,
be renewed within 24 hours of execution, and be repeated after any credential,
environment, or process-context change. Current free-tier artifact remains pending,
so runtime refuses execution. Billing status is procedurally owner-attested;
identifier prohibition prevents cryptographic project-to-key binding.

Free-tier confirmation, trace/full approval, and quota-reset approval are mutable
runtime-control records, not immutable freeze inputs. Freeze manifest names but
does not hash them. Live preflight permits only exact unstaged edits to free-tier
confirmation and selected mode approval (plus quota-reset approval during explicit
resume); every code, prompt, config, input, and other artifact must match committed
HEAD. Approval binds committed HEAD/tree plus frozen config, prompt, request plan,
and current confirmation hash. This separation avoids circular requirement where
approval must name commit containing approval itself.

Runtime requires `--require-free-tier-owner-confirmation`. Trace and full modes
are separate commands and never run implicitly together:

- Trace: 24 network attempts maximum—8 primaries plus 16 replicates.
- Full: 26 network attempts maximum—remaining primaries only, after separate
  owner approval following repeatability review.

Every network attempt is atomically counted before dispatch. Retries consume
cap. No model, key, project, provider, prompt, candidate depth, or payload may
change to obtain quota. Billing, credits, and paid fallback are prohibited.

Terminology is distinct: 50 logical calls comprise 24 trace calls and 26 remaining
full calls. Authorized network-attempt caps are likewise 24 and 26. Three-attempt
retry policy creates counterfactual demand of up to 150 attempts only if hard caps
did not exist; it does not authorize more than 50 network attempts. Quota-stopped
attempts and successful responses are observed counts available only after approved
execution.

HTTP `429 RESOURCE_EXHAUSTED` records sanitized error class/status, preserves
checkpoint, and stops without retry. Resume requires owner confirmation that
quota reset occurred. Payloads remain frozen; no result may be selected or
discarded based on outcome.

Explicit quota-reset resume permits only canonical durable files from selected
mode's interrupted request plan: ledger, validated raw records, attempt evidence,
and quota-stop record. Unknown paths, other-mode files, terminal-failure records,
non-plan IDs, staged controls, or changed frozen implementation remain blocked.

## 7. Token budget and cost

`google.genai.local_tokenizer.LocalTokenizer` with frozen Gemma-3 tokenizer asset
SHA-256 `1299c11d7cf632ef3b4e11937501358ada021bbdf7c47638d13c0ee982f2e79c`
counts contents, system instruction, and dynamic response schema offline. SDK
2.13.0 local tokenizer omits `response_json_schema`; audit therefore projects
identical schema through tokenizer-supported `response_schema` solely for token
counting. Live request still contains only `responseJsonSchema`.

- Primary input: 862,278 tokens across 34 requests.
- Per request: 23,977 minimum; 26,369 maximum; 25,361.117647 mean.
- Largest request headroom under 1,048,576-token input limit: 1,022,207.
- Maximum schema-contract output: 1,911 tokens/request, below frozen 4,096 cap.
- Two extra replicates for eight trace queries: 16 requests and 402,670 input
  tokens.
- Planned total: 50 requests and 1,264,948 input tokens.
- Trace envelope: 24 requests, 604,005 input tokens, maximum contract output
  45,186 tokens.
- Remaining full envelope: 26 requests, 660,943 input tokens, maximum contract
  output 48,947 tokens.
- Free-tier cost may be recorded as exactly `$0.00` only after fresh free-plan/no-
  billing confirmation. Paid counterfactual cost is not calculated or authorized.
  Rate-limit capacity is not guaranteed.

Local tokenizer is an experimental SDK feature. Counts are exact under frozen
SDK/tokenizer asset; future provider `usageMetadata` must be preserved and
compared after authorized execution. Difference is reported, never retroactively
used to alter prompt or limits.

Free-tier Gemini terms permit Google product-improvement use of submitted input
and output. Only approved public, non-sensitive corpus/query content may be sent.

If trace exceeds active free-tier TPM/RPD, split unchanged requests across quota
reset periods after owner approval. Provider `usageMetadata` is authoritative.

## 8. Structural trace and repeatability gate

Trace IDs use SHA-256 over UTF-8 `"42" + NUL + query_id`; select eight smallest
digests. No query text, category, qrel, answer, metric, provenance, or trace was
used.

Selected IDs, in digest order:

1. `v2q-017`
2. `v2q-016`
3. `v2q-003`
4. `v2q-023`
5. `v2q-013`
6. `v2q-025`
7. `v2q-004`
8. `v2q-027`

Each receives three executions: first valid execution is primary; next two are
audit replicates. Never select best replicate. Every primary/replicate pair must
meet all preregistered thresholds:

- exact candidate-score agreement ≥ 0.90;
- identical rank-position fraction ≥ 0.80;
- Kendall tau-b on score vectors ≥ 0.90;
- Spearman rank correlation ≥ 0.95;
- top-10 overlap fraction ≥ 0.90.

All model versions must match and terminal failure count must be zero. Any gate
failure blocks full run and metrics. Thresholds are pilot design gates, not
universal standards.

## 9. Retry, preservation, and statelessness

Only transport/timeouts and HTTP `408`, `500`, `502`, `503`, `504` may retry.
Every retry deserializes identical frozen request bytes and retains same SHA-256.
HTTP `429` and content/schema failures never retry.

Authorized execution must preserve exact credential-free request and raw
response; `responseId`; `modelVersion`; usage, finish, and safety metadata;
timestamps; retries/errors; request/response hashes; and explicit failure rows.
No chat, conversation state, caching, tools, fallback, or answer generation is
allowed.

## 10. Frozen evaluation protocol

Trace phase calculates repeatability and operational validity only. Relevance
metrics, pool expansion, and hypothesis verdicts remain prohibited.

After complete rankings, pooled judging, and approval, report aggregate plus all
six category slices for MRR@5/@10, Recall@5/@10, Hit Rate@5/@10,
Precision@5/@10, binary and graded nDCG@10, Complete Evidence Recall@5/@10,
and BM25 top-50 candidate recall ceiling. No composite score or prioritized
metric.

Primary comparator is frozen BM25. Use paired whole-query bootstrap with 10,000
samples and seed 42. Report point effects, 95% intervals, and whether each
interval includes zero. Pilot/non-exhaustive qrels cannot produce final
hypothesis verdict.

Operational reporting includes coverage, terminal failures, retries, quota
stops, refusals, malformed responses, mean/median/p95 latency, provider
input/output/thinking tokens, and cost. Sequence is immutable: commit freeze;
trace only; repeatability only; owner approval; remaining 26 primaries; freeze
rankings; add unseen top-10 to blind pool; owner judging; pooled metrics; later
separate generation/H5 protocol.

## 11. Offline freeze decision

Offline contract is remediation-ready. Executable config still cannot trigger a
request without separate trace/full approval bound to config, prompt, plan, clean
committed Git identity, and fresh free-tier attestation. Trace approval never
authorizes full mode. Live execution is not approved. Before any
credential use or request, owner must approve:

- frozen config and prompt hash;
- token/cost audit;
- trace IDs and thresholds;
- mocked contract tests;
- remaining stable-model and free-tier limitations;
- manual Plan: Free and no-linked-billing confirmation;
- dated confirmation that previously exposed Gemini key was revoked and replaced;
  owner provided this non-secret confirmation on 2026-07-26 and replacement remains
  environment-only. Key value and identifiers must never be shared or recorded.

Until approval: zero live Gemini calls, zero retrieval results/metrics, zero
pool additions, zero generated answers, zero owner judging, and zero commits.
