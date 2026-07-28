# Dissertation Retrieval Rebuild — Recovered Phase Plan

Status date: 2026-07-26  
Repository: `rag-retrieval-dissertation`  
Active branch: `codex/dissertation-rebuild-v2`

## Provenance and interpretation

This roadmap recovers the lost Codex master plan and reconciles it with decisions
actually approved during Phases 0–5B.

Historical source:

- Codex thread: `Use available skills`
- Thread ID: `019f9006-eaa0-7622-ad4d-a94d34aeddcb`
- Source title: `Dissertation Retrieval Rebuild — Verified, Phase-Gated Plan (v6)`
- Preserved attachment copies:
  - `~/.codex/attachments/3447e953-596c-45a6-b36b-d36d62b375bb/pasted-text.txt`
  - `~/.codex/attachments/dc7a6eca-8033-4f70-9464-b0a067af23e7/pasted-text.txt`
- Both source copies have SHA-256
  `fb002afaa6cb17eeaee08e1280a16cb4ad1ce2c3c74ff77c491e6ab6ee7dac42`.

Historical v6 called itself an eight-phase plan because it counted Phase 0 through
Phase 7. It did not contain a separately numbered Phase 8. Its post-Phase-7 corpus
ramp and final deliverable are labelled Phase 8 here so the remaining work is
visible and unambiguous.

Historical v6 is evidence of original intent, not current executable protocol.
Later approved corrections control wherever they differ. Important supersessions:

- branch changed from `test` to `codex/dissertation-rebuild-v2`;
- corpus/benchmark became frozen 140-chunk R5 pilot with 34 questions;
- evaluation changed from a narrow metric set to balanced metric panel;
- Graph became corrected v3.2 implementation;
- Hybrid default became fixed RRF `k=60`, without result-driven tuning;
- Prompt-RAG changed from direct-answer Gemini CoT over BM25 top-20 to retrieval-
  only reranking over frozen BM25 top-50;
- Gemini Phase 5B/5C route was attempted, failed before valid rankings, and is
  archived. Current Phase 5D V2 uses `claude-haiku-4-5-20251001`, unchanged
  prompt/candidates/scoring/ranking, and fixed-key structured JSON;
- owner judgments wait for union of candidates from every compared system;
- current 34-query work is pilot/development evidence, not final dissertation
  inference.

## Standing research-integrity rules

1. Preserve historical files and prior runs. Corrections use new versioned paths.
2. Never tune corpus, questions, qrels, prompts, aliases, scores, or parameters
   because a hypothesis or system performed poorly.
3. Every run binds exact input paths, SHA-256 hashes, Git commit/tree, config,
   environment, seed, and output path.
4. Fail closed on malformed, missing, duplicate, incompatible, or unknown IDs.
5. Preserve raw rankings and per-query traces before calculating aggregates.
6. Use deterministic ordering and tie rules. Use seed 42 where randomness exists.
7. Keep unjudged candidates unjudged. Same-document membership is not relevance.
8. Keep system/rank/score/current-gold provenance hidden during owner judging.
9. No single metric determines best system. No composite score or hidden weighting.
10. Report aggregate and six category slices with query N and uncertainty where
    applicable. Report contradictory metrics explicitly.
11. Separate retrieval, efficiency, and generation evaluation.
12. Preserve negative, weak, or inconclusive results.
13. Pilot/non-exhaustive qrels cannot support final dissertation verdicts.
14. No API secret enters repository, logs, requests, responses, or manifests.
15. Network/API work requires explicit phase approval and all frozen gates.
16. Stop at every phase checkpoint. Do not silently enter next phase.

## Canonical hypotheses

- **H1:** BM25 performs competitively with FAISS on exact-match and terminology-
  sensitive queries.
- **H2:** FAISS outperforms BM25 on paraphrased/semantic queries where query
  vocabulary differs from source text.
- **H3:** Entity-Co-occurrence Graph Retrieval outperforms BM25 and FAISS on
  entity-relation and multi-hop queries.
- **H4:** Hybrid BM25 + Entity-Co-occurrence Graph retrieval via RRF achieves the
  highest aggregate MRR across mixed query types, at the cost of higher latency.
- **H5:** Retrieval quality does not translate monotonically into generation
  faithfulness; retrieval and generation require separate evaluation.

H1 primary equivalence test remains preregistered paired BM25-minus-FAISS MRR@10
95% CI wholly inside `[-0.05, +0.05]` on exact-lookup plus terminology queries.
Sensitivity margin is `±0.03`. Overlap with either primary boundary is
inconclusive. This margin is a design choice, not a universal literature threshold.

## Balanced evaluation contract

Retrieval panel:

- MRR@5 and MRR@10;
- Recall@5 and Recall@10;
- Hit Rate@5 and Hit Rate@10;
- Precision@5 and Precision@10;
- binary nDCG@10 for historical continuity;
- graded nDCG@10 using qrel grades;
- Complete Evidence Recall@5 and @10;
- candidate recall ceiling for rerankers.

Operational panel:

- mean, median, and p95 latency;
- build time, index size, and peak memory where measurable;
- API input/output/thinking tokens, retries, failures, quota stops, and cost for
  Prompt-RAG.

Generation panel, evaluated separately in Phase 7:

- correctness;
- faithfulness;
- completeness;
- citation/evidence accuracy;
- abstention quality;
- unsupported-claim rate.

Statistics:

- paired whole-query bootstrap, 10,000 samples, seed 42, for effect estimates;
- H1 two-sided equivalence interval rule, never one-sided noninferiority substitute;
- paired randomization tests for preregistered directional superiority claims;
- Holm correction across preregistered confirmatory comparisons;
- pilot inference always labelled exploratory.

---

## Phase 0 — Forensics, correction, protocol, and provenance

### Goal

Establish trustworthy source of truth before rebuilding systems.

### Work

1. Preserve historical report, data, runs, evidence, backup branch, and
   `origin/main` artifacts unchanged.
2. Recompute exact historical mid-sem metrics from explicit CLI inputs.
3. Implement independent hand-computed metric fixtures and fail-closed contracts.
4. Determine exact binary-nDCG disagreement cause.
5. Document historical claim status using commit SHA, path, and file hash.
6. Trace five raw sources through cleaned documents into historical chunks.
7. Audit historical 28 QA records, six categories, and 78 qrels.
8. Distinguish numerically recomputable from fully reproducible.
9. Freeze balanced V2 experiment protocol and hypothesis rules.

### Deliverables

- `docs/EXPERIMENT_PROTOCOL_V2.md`
- `docs/MIDSEM_RESULTS_CORRECTION.md`
- `docs/ARTIFACT_PROVENANCE_V2.md`
- `docs/MIDSEM_CORPUS_PROVENANCE.md`
- `scripts/forensics/recompute_midsem_metrics.py`
- `audits/phase0/`

### Checkpoint status

Complete and preserved. Historical 28-query recomputation remains forensic, not
final inferential evidence.

---

## Phase 1 — Corpus and owner-authorized pilot benchmark

### Original goal

Build clean government-scheme corpus without synthetic fallback or raw schema
leakage, then create balanced six-category benchmark.

### Current frozen scope

- 140 corpus chunks;
- 34 R5 questions;
- six categories: exact lookup, terminology, paraphrase, entity relation,
  synthesis, and multi-hop;
- immutable benchmark ID `pilot-qa-v2-owner-approved-20260724-r5`;
- AI-assisted and owner-authorized, not independently human-annotated;
- direct-support qrels are not exhaustive relevance judgments.

### Required quality gates

1. Natural, unambiguous questions with fully supported reference answers.
2. Gold chunks contain required evidence.
3. No JSON/schema leakage or weak lexical shortcut.
4. Paraphrases materially change vocabulary.
5. Entity-relation questions ask real relationships.
6. Multi-hop questions cannot be answered from one chunk.
7. Synthesis questions require at least three evidence chunks.
8. Near-duplicate intents resolved.
9. Grade 2 means direct support; grade 1 means useful but insufficient context;
   grade 0 only means explicit reviewed nonrelevance.

### Checkpoint status

Complete. R3 and R4 candidate preserved; R5 frozen without post-result content
changes.

---

## Phase 2 — Frozen lexical and dense baselines

### Phase 2A: BM25 and FAISS pilot

Systems:

- BM25 with frozen tokenizer, `k1=1.5`, `b=0.75`;
- FAISS-windowed-max using
  `sentence-transformers/all-MiniLM-L6-v2` at pinned revision;
- tokenizer-aware 254-content-token windows with 32-token overlap;
- normalized embeddings, `IndexFlatIP`, cosine similarity;
- exact scoring over every window;
- chunk score = maximum window score;
- deterministic chunk-ID ties;
- winning window ID/offset preserved.

Execution requirements:

1. Fresh indexes against exact 140 chunks.
2. Same 34 frozen queries.
3. Raw unique-chunk top-50 rankings.
4. Full balanced metrics aggregate and per category.
5. Timing under same warm-up/repetition protocol.
6. 10,000 paired bootstraps, seed 42.
7. Failure taxonomy and per-query traces.
8. Truncated versus windowed FAISS reported only as implementation-validity
   comparison, not model-selection competition.

### Phase 2B: blind baseline pool

1. Preserve existing 504-pair BM25+FAISS top-10 union package.
2. Keep system/rank/score/gold status sealed.
3. Keep owner grades blank until every compared retrieval system contributes.
4. Do not infer or generate owner labels.

### Checkpoint status

Phase 2A complete. Phase 2B package preserved and intentionally incomplete.

---

## Phase 3 — Corrected Entity Graph retrieval

### Goal

Develop Graph retrieval from corpus-backed entity evidence, never from observed
benchmark gains.

### Frozen principles

1. Entity aliases require corpus evidence.
2. Matching uses normalized identity and word boundaries, never raw substring.
3. Scoring/configuration freezes before aggregate results.
4. Trace gates precede metrics.
5. No-seed behavior and seed coverage are reported by category.
6. Entity-relation and multi-hop results remain separate.
7. All misses receive trace-supported failure labels.

### Evaluation

- full balanced known-gold panel;
- aggregate plus every category;
- Graph versus BM25 and FAISS-windowed-max;
- 10,000 paired whole-query bootstraps, seed 42;
- aggregate, entity relation, and multi-hop comparisons;
- exploratory pilot only, no final H3 verdict.

### Pool contribution

Add only corrected v3.2 unseen Graph top-10 query/chunk pairs. Exclude invalid V1
and v3.1 candidates. Blind new pairs and seal provenance separately.

### Checkpoint status

Complete at corrected Graph v3.2; committed in `20a889f`.

---

## Phase 4 — Hybrid BM25 + corrected Graph via RRF

### Frozen system

- constituents: frozen BM25 and corrected Graph v3.2;
- Reciprocal Rank Fusion;
- equal weighting;
- default `k=60`;
- deterministic ties;
- no post-result tuning.

### Evaluation

1. Trace gate before metrics.
2. Balanced metric panel aggregate and per category.
3. Paired bootstrap versus both constituents.
4. Robustness checks without selecting favorable configuration.
5. Report latency as warm-cache operational latency, not cold-start latency.
6. Preserve 34-query unmeasured validation pass, five extra warm-up queries, 20
   measured repetitions over 34 queries, and 680 measured samples.
7. Preserve negative/inconclusive Hybrid finding; do not claim H4 support.

### Pool contribution

Add unseen frozen Hybrid top-10 candidates to blind pool, with provenance hidden.

### Checkpoint status

Complete and committed in `70de0fd`. Latency disclosure corrected without changing
rankings, metrics, bootstrap values, or pool contents.

---

## Phase 5 — Prompt-RAG retrieval-only reranker

Prompt-RAG is retrieval/reranking only. Answer generation belongs to Phase 7.

### Phase 5A: architecture audit and preregistration

1. Search Git history, docs, configs, scripts, and reports for historical meaning.
2. Classify implementation, documentation-only, unsupported, obsolete, or invalid
   claims.
3. Freeze fair architecture without qrels, answers, categories, metrics, sealed
   provenance, owner labels, or prior-system performance tuning.
4. Chosen architecture: frozen Phase 2A BM25 top-50 to LLM relevance reranker.

Status: complete; committed in `d9689ae`.

### Phase 5B: executable Gemini offline freeze — historical, abandoned

Frozen contract:

- Google Gemini Developer API, stable `v1`, `generateContent`;
- model request string `gemini-2.5-flash`;
- `google-genai==2.13.0`;
- one stateless query request containing all 50 candidates;
- 34 primary requests total;
- temperature 0, thinking budget 0, candidate count 1;
- streaming, tools, grounding, URL context, code execution, caching, and file
  search disabled;
- strict candidate-score JSON, integer scale 0–3;
- every supplied chunk scored exactly once;
- ranking by score descending then chunk ID ascending;
- no BM25-rank tie-break, fallback, backfill, or answer generation;
- provider-returned `modelVersion` must remain constant across run;
- raw request/response, usage, response ID, safety/finish metadata, timestamps,
  retry evidence, and hashes preserved;
- `429 RESOURCE_EXHAUSTED` stops without retry;
- retries only for 408/500/502/503/504 and transient transport failures;
- free tier only, no billing or paid fallback.

Status: offline freeze committed in `49bd0ba`. Pre-execution audit found circular
runtime-control/clean-tree gate; narrow repair committed in `c5e05b8`. Frozen
prompt, model, candidates, request payloads, and ranking rules remained unchanged.
Subsequent attempts produced no valid Gemini ranking. Artifacts now live under
`archive/phase5_gemini_failed/` with byte-preservation hashes.

### Phase 5C: Gemini trace and repeatability gate — historical, failed

Preconditions:

1. Narrow Phase 5B execution-control repair reviewed and committed.
2. Clean frozen code/config/input tree.
3. Owner manually confirms active Google AI Studio project shows Plan `Free`, has
   no linked billing account, and current credential/environment is unchanged.
4. Fresh confirmation is less than 24 hours old and config-bound.
5. Separate trace execution approval binds commit, tree, config, prompt, 24-call
   plan, and confirmation hash.
6. `GEMINI_API_KEY` exists only in environment; value is never read into logs.

Execution:

- deterministic eight trace query IDs;
- three executions each: first valid is primary, next two are audit replicates;
- exactly 24 logical requests and maximum 24 attempted network requests;
- retries consume cap;
- count attempt durably before dispatch;
- stop cleanly on quota exhaustion or any terminal contract failure;
- never choose best replicate.

Trace outputs:

- raw credential-free request and raw response per execution;
- score agreement;
- ranking agreement;
- Kendall and Spearman correlations;
- top-10 overlap;
- modelVersion consistency;
- token, latency, retry, failure, quota, and safety metadata;
- repeatability gate decision against preregistered thresholds.

Prohibited during 5C:

- relevance metrics;
- pool expansion;
- full remaining-query run;
- answer generation;
- owner judging.

Checkpoint was not reached: preserved Gemini failures blocked valid trace output.

### Phase 5D V1/V2: Claude provider recovery and trace

Owner-directed provider recovery preserved BM25 top-50, prompt, scoring, ranking,
trace selection, and no-retry policy. V1 array schema produced four valid primary
records, then omitted one of 50 candidates on fifth HTTP-200 response. V1 stopped
fail-closed and remains immutable. V2 changes only response serialization to a
fixed-key object requiring every exact chunk ID and rejecting extras. V2 starts
in separate output root and never selects from V1.

V1 observed spend is $0.177402. V2 retains cumulative $1.90 hard cap. Offline V2
freeze and commit precede exact owner approval for 24-call trace. Trace computes
repeatability only; no relevance metrics or pool expansion.

### Phase 5E: remaining primary retrieval run

After separate approval:

1. Run only remaining 26 primary queries.
2. Never rerun eight trace primaries or select favorable replicates.
3. Hard cap 26 network attempts; retries consume cap.
4. Require same modelVersion established during trace.
5. Preserve failures without fallback/backfill.
6. Freeze complete 34-query top-50 rankings.

### Phase 5F: Prompt-RAG pool contribution

1. Add unseen Prompt-RAG top-10 query/chunk pairs.
2. Deduplicate by query/chunk pair against existing blind pool.
3. Hide system, rank, score, current gold, and predicted relevance.
4. Seal provenance separately.
5. Do not calculate final pooled metrics before owner judging.

---

## Phase 6 — Final pooled owner relevance review and fair retrieval comparison

### Candidate universe

Union of top-10 candidates from every system intended for comparison:

- BM25;
- FAISS-windowed-max;
- corrected Graph v3.2;
- frozen Hybrid RRF;
- Prompt-RAG Claude Haiku 4.5 reranker.

Deduplicate by `(query_id, chunk_id)`. Existing 504-pair Phase 2B package remains
unchanged; Graph, Hybrid, and Prompt-RAG contribute only unseen pairs.

### Blind owner package

Show:

- query ID;
- question;
- reference answer;
- candidate chunk;
- source document title.

Hide:

- system identity;
- rank and score;
- current gold status;
- predicted relevance;
- sealed provenance.

### Relevance rubric

- `2`: directly supports reference answer;
- `1`: useful context but insufficient alone;
- `0`: irrelevant or misleading;
- `U`: unclear and requires adjudication.

Never infer relevance from source-document overlap.

### Quality control

1. Owner judges every pooled pair.
2. Rejudge random 15%, seed 42.
3. Calculate intra-rater agreement.
4. Explicitly adjudicate every disagreement and `U`.
5. Record rationale for grade changes.
6. Never expose system performance until labels freeze.

### Final pooled retrieval evaluation

1. Version immutable pooled qrels.
2. Report known-gold and final pooled metrics separately.
3. Run balanced panel aggregate and by category for all five systems.
4. Use 10,000 paired bootstraps, seed 42.
5. Apply H1/H2/H3/H4 hypothesis-specific rules without universal winner claim.
6. Explain every material shift caused by new judgments.
7. Show worst traces and failure taxonomy for every system.

Checkpoint: final pool, sealed provenance, owner judgments, agreement,
adjudication, qrels hash, rankings, metrics, tests, and Git status. Pilot results
remain exploratory.

---

## Phase 7 — Generation and H5

### Boundary

Begin only after retrieval systems and pooled qrels freeze. Retrieval rankings may
not change during generation evaluation.

### Preregistration

Freeze before any answer generation:

1. provider, exact model/version, endpoint, SDK, and API controls;
2. one fixed answer prompt and hash;
3. exact retrieved context depth and serialization;
4. same generator for every retriever;
5. missing-retrieval and abstention behavior;
6. citation format and evidence mapping;
7. timeout, retry, failure, token, cost, and raw-response policy;
8. correctness, faithfulness, completeness, citation accuracy, abstention quality,
   and unsupported-claim rubrics;
9. human/automated judging protocol and leakage boundaries;
10. statistical comparisons and multiplicity correction.

### Execution

1. Generate one answer per frozen `(query, retrieval system)` pair under identical
   controls.
2. Preserve raw prompts, contexts, responses, usage, failures, and hashes.
3. Score generation dimensions separately from retrieval.
4. Compare query-level retrieval metrics with correctness, faithfulness, and
   completeness.
5. Test H5 without assuming higher retrieval MRR must improve generation.
6. Report unsupported claims and abstentions explicitly.

Checkpoint: frozen protocol, sample traces, complete generation panel, H5 analysis,
cost/latency, failures, hashes, tests, and no universal-system claim.

---

## Phase 8 — Final-scale confirmation, holdout, and dissertation package

Historical v6 placed this work after Phase 7 without a number. It is numbered here
for visibility.

### 8A. Decide final evidence scale

Current R5 corpus and 34 questions are pilot data. Before final dissertation claims,
owner must choose and preregister either:

- a larger staged corpus/benchmark ramp; or
- a justified final locked corpus plus independent holdout.

Do not silently relabel pilot results as final evidence.

### 8B. Staged corpus ramp, if retained

Historical targets were approximately 45, 70, then 100 documents. Every expansion
requires explicit approval before acquisition.

At every step:

1. acquire only traceable official sources, never synthetic fallback;
2. regenerate QA/qrels for new corpus rather than reuse old labels blindly;
3. rerun cross-scheme, lexical-shortcut, duplicate, multi-hop, synthesis, and
   support audits;
4. manually review benchmark before retrieval;
5. freeze systems before results;
6. run all systems under identical protocol;
7. build blind union pool and judge unseen candidates;
8. rerun balanced metrics, uncertainty, failures, efficiency, and generation;
9. stop on validity failure, not on unfavorable hypothesis outcome.

### 8C. Independent holdout

1. Freeze 10–20 new questions never used in development.
2. Cover all six categories and underrepresented schemes.
3. Apply same evidence, multi-hop, synthesis, and lexical-confound audits.
4. Freeze labels before any system result is observed.
5. Run all frozen systems without parameter changes.
6. Report holdout separately from development/pilot benchmark.

### 8D. Final hypothesis decisions

For H1–H5, report one of:

- supported;
- partially supported;
- not supported;
- inconclusive.

Each verdict cites exact dataset version, system version, metric, effect, interval,
test/correction, category N, artifact path, commit, and SHA-256. Contradictory
metrics and limitations remain visible.

### 8E. Final dissertation package

- consolidated results chapter;
- corpus, benchmark, qrels, and owner-review provenance;
- all five retrieval systems and frozen configs;
- retrieval, efficiency, and generation tables;
- per-query traces and failure taxonomies;
- statistical report and sensitivity analyses;
- reproducibility commands and environment lock;
- protected historical corrections and limitations;
- README/dissertation wording matched to actual executed evidence;
- immutable release tag/archive after owner approval.

## Current next action

Commit Phase 5D V2 fixed-key offline freeze, obtain exact commit-bound owner
approval, then execute 24-call Claude trace only. No relevance metrics, pool
expansion, remaining-primary run, generation, or owner judging during trace.
