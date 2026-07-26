# Exhaustive dual review — `codex/dissertation-rebuild-v2`

Verdict: **STOP**

Review boundary: merge-base `df1b37384738641691a5f993bbab3032f6394f62` through HEAD `d9689aeae520ed24a5f0c409a18134f5f9042e0f`, plus staged, unstaged, untracked Phase 5 files, and direct cross-file dependencies.

## Inventory gate

- 419/419 input files have stable IDs `BR-0001`–`BR-0419` and dispositions.
- Classes: 132 audit artifacts, 7 configs, 45 data files, 5 docs, 1 prompt, 163 run artifacts, 32 scripts, 16 source files, 18 tests.
- Dispositions: 228 generated-and-hash-verified, 186 reviewed, 5 binary/unreviewable with byte hashes verified.
- Owner-judgment values were not opened. Only committed byte hash was checked.
- All 66 Python files parse; all 220 JSON and 103 JSONL files parse.

Full inventory: `audits/branch_review/file_inventory.json`.

## Critical blocker

`REC-001`: Gemini credential previously exposed in chat has no verified revocation/replacement. Repository scope contains no candidate secret value, but live execution stays prohibited until owner rotates it and records non-secret confirmation.

## Required before any Gemini execution

1. Make runner directly executable; `python scripts/run_phase5b_prompt_rag.py --help` currently fails importing `src`.
2. Enforce frozen config, prompt, queries, chunks, BM25 rankings, trace selection, request hashes, exact R5 IDs, and canonical output paths.
3. Enforce committed clean tree plus distinct trace execution approval; current runner ignores `execution_authorized: false`.
4. Replace resettable/unlocked checkpoint with canonical, strict, process-locked ledger bound to exact plan and outputs.
5. Make response/failure recording crash-safe and idempotent. Never redispatch when valid response already exists.
6. Bind trace `modelVersion` and complete trace evidence into full-run approval. Current full mode can accept different model version or status-only fake decision.
7. Retry approved transport timeouts/errors as frozen; sanitize exception chaining; preserve terminal attempt history and invalid-response metadata.
8. Add installable exact `google-genai[local-tokenizer]==2.13.0` dependency and runtime version check.
9. Regenerate complete Phase 5B manifest after fixes. Current manifest has seven stale hashes and omits runner/free-tier/evaluation artifacts.
10. Resolve free-tier credential-context limitation through immediate owner attestation without storing key/project identifiers.

## Required before commit

- Fix stale Phase 5B manifest and failing tests.
- Reject empty per-query Phase 0 rankings.
- Correct R5 freeze provenance to existing R4 candidate and test qrels parity.
- Correct H1 `not equivalent` wording to `inconclusive` where CI crosses margin.
- Disclose Phase 4 validation component-call counts.
- Replace Phase 4 `improves` label with point-direction plus inconclusive uncertainty.
- Clarify token audit: 50 authorized attempts versus uncapped theoretical 150 retry demand.

## Required before final evidentiary use

- Phase 2A R5 runner must enforce and record exact input hashes, command, Git SHA, package versions, counts, IDs, and qrels contract.
- Graph retrieval/evaluation must compare query/R5/BM25/FAISS bytes with frozen expected hashes, not merely canonical paths/current hashes.
- Graph evaluator must reject unknown ranked chunk IDs.
- FAISS winning-window ties need deterministic window-ID tie-break.
- Paired Phase 2 bootstrap must assert identical query-ID order.
- Add independent metric recomputation tests instead of relying mainly on generated artifact snapshots.

## Phase findings

### Phase 0

Historical binary nDCG reproduction and graded supplementary nDCG separation are supported. Root-cause explanation is correct. Defect: per-query empty result arrays are accepted despite fail-closed empty-run rule.

### Phase 1

R5 currently contains 34 unique questions and 48 unique resolving grade-2 qrels. Category counts are exact lookup 6, terminology 6, paraphrase 6, entity relation 6, multi-hop 6, synthesis 4. AI-assisted/owner-authorized and non-exhaustive labels remain accurate. Freeze script itself references missing pre-rename R4 paths and is not byte-reproducible.

### Phase 2

Final windowed algorithm matches approved representation: normalized MiniLM windows, 254/32 segmentation, IndexFlatIP cosine, all-window search, max-window chunk score, unique chunk ranking. Current artifacts are hash-frozen, but corrected runner does not enforce exact input lineage or record complete provenance. Equal winning-window scores lack explicit deterministic window tie.

### Phase 3

Invalid Graph V1/v3.1 candidates remain excluded. v3.2 exact-token query matching, corpus-backed aliases, independent traversal, hop decay, and deterministic score ties are strongly tested. Current artifacts resolve. Rerun scripts still need frozen query/baseline hash enforcement and unknown-chunk rejection.

### Phase 4

RRF formula is `1/(60+rank)` per component, equal weights, BM25 plus Graph v3.2 only. Warm-cache latency is not represented as cold-start. H4 remains exploratory/inconclusive numerically. Metadata understates validation component calls, and point-estimate label `improves` is stronger than CI evidence.

### Phase 5A/5B

Architecture and prompt contracts are coherent: BM25 top-50 reranker, one 50-candidate request/query, untrusted candidate text, strict integer 0–3 schema, score-descending/chunk-ID tie, no fallback/backfill, 429 quota stop, structural trace selection. No live run exists. Execution implementation and freeze safety remain blocked by findings above.

## Verification

- Focused: **89 passed, 1 failed**.
- Full: **279 passed, 1 failed**.
- Failure: stale `audits/phase5b/freeze_manifest.json` hash.
- `git diff --check`: clean before review artifacts.
- Resolvable file-hash claims: 629/642 current or contextual matches; 7 stale current claims, 2 missing obsolete targets, 4 historical code claims without reachable matching bytes.
- Secret scan: zero candidate secrets across 419 scoped files and reachable branch commits.
- Blind/sealed pools align at 504, 610, and 620 unique query/chunk pairs with zero sealed fields in blind rows.

Detailed verification: `audits/branch_review/hash_verification.json` and `audits/branch_review/test_results.txt`.

## Verified strengths

- Protected Phase 0–4 history remains byte-preserved.
- Negative/inconclusive outcomes are retained.
- No universal winner or composite score introduced.
- Non-exhaustive known-gold limitation is repeatedly disclosed.
- Graph/Hybrid ranking code has strong hand-computed deterministic tests.
- Prompt injection boundary and response parser fail closed on malformed IDs/scores.
- No API call, retrieval run, metric calculation, pool change, generation, owner-label inspection, stage, commit, or push occurred.

## Remaining uncertainty

- Credential rotation and actual free-project context are owner-verified, not independently machine-verifiable under no-identifier rule.
- `gemini-2.5-flash` remains stable alias, not dated immutable snapshot.
- Provider usage can differ from experimental local tokenizer counts.
- Saved Gemini response would be SDK serialization, not wire bytes.
- Four historical code hashes cannot be linked to reachable committed bytes; preserved generated outputs do verify after contextual path resolution.
- Corpus evidence supports Graph alias additions, but Git cannot prove selection was uninfluenced by prior v3.1 observations.

Complete reconciled findings: `audits/branch_review/reconciled_findings.json`.
