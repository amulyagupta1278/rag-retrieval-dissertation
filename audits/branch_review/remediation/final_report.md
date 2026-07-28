# Branch-review remediation report

Verdict: **STOP**

REC-001 through REC-014 and REC-016 through REC-027 are resolved. REC-015 remains
blocked on one owner-only fact that cannot be inferred or stored safely: fresh
confirmation that active Google AI Studio project shows Plan: Free, has no linked
billing account, and covers current process environment/credential context.

No Gemini/API call is authorized or possible through frozen workflow until that
attestation and separate trace execution approval are completed after commit review.

## Completed corrections

- Recorded dated non-secret owner confirmation that exposed credential was revoked
  and replaced. No credential or project/billing identifier is stored.
- Made Phase 5B runner directly executable from repository root.
- Added complete config-derived hash/request preflight before credential access.
- Removed caller-selected input, output, and checkpoint paths.
- Required exact `v2q-001` through `v2q-034` IDs and canonical safe filenames.
- Added separate config/prompt/plan/Git/free-tier-bound trace and full approvals.
- Added canonical schema-v2 ledger, exclusive process lock, strict state validation,
  request caps, crash-safe durable states, idempotent response recovery, and no
  valid-response overwrite.
- Bound full mode to independently recomputed 24-response trace evidence and exact
  returned `modelVersion`.
- Added approved transport retries, immediate 429 quota stop, sanitized `from None`
  exceptions, complete credential-free attempt history, and invalid-response evidence.
- Pinned installable `google-genai[local-tokenizer]==2.13.0` in both dependency files
  and added runtime version enforcement.
- Regenerated complete 35-artifact Phase 5 manifest with no self-hash.
- Rejected empty Phase 0 per-query rankings and invalid explicit ranks.
- Hardened Phase 2 R5 path/hash/count/version/config/provenance contracts.
- Corrected R4-candidate → R5 freeze provenance and fixed approval timestamp.
- Added deterministic equal-score FAISS winning-window tie by stable window ID.
- Enforced Graph query/R5/qrel/chunk/BM25/FAISS/config/registry/index hashes and
  rejected unknown chunks at every ranking depth.
- Corrected H1 wording without changing numeric values.
- Disclosed exact Phase 4 premeasurement combined/component invocation counts.
- Replaced Hybrid `improves` overclaim with point-estimate-higher-but-inconclusive;
  bootstrap values remain unchanged.
- Added independent test-side balanced metric implementation and strict paired
  bootstrap ID/order/length checks.
- Separated logical calls, authorized attempt caps, counterfactual retry demand,
  quota stops, successful responses, conditional free cost, and unauthorized paid
  counterfactual.

Exact per-finding evidence and before/after hashes:
`audits/branch_review/remediation/finding_resolution_matrix.json`.

## Research-integrity preservation

- 41 critical corpus, QA, qrel, ranking, metric, pool, raw-latency, and sealed owner
  package files matched starting hashes.
- No corpus, question, qrel, ranking, score, pool, or owner-label byte changed.
- Phase 2 H1 numeric sequence unchanged; wording only changed.
- Phase 4 bootstrap numeric sequence unchanged; interpretation wording only changed.
- Phase 4 timing object and raw 680 samples unchanged; disclosure metadata only changed.
- Existing negative/inconclusive findings remain preserved.
- Retrieval, generation, metric-production, pool expansion, and owner judging were not
  run. Independent read-only metric tests were authorized and executed.

Details: `audits/branch_review/remediation/protected_artifact_comparison.json` and
`audits/branch_review/remediation/independent_metric_verification.json`.

## Verification

- Direct runner `--help`: passed.
- Focused suite: **178 passed**.
- Full suite: **308 passed**.
- Independent metric oracle: **3 passed**.
- Phase 5 manifest: **35/35 hashes match**.
- Secret scan: **0 credential-shaped candidates** after boundary-aware classification.
- `git diff --check`: passed.
- `git diff --cached --check`: passed.
- Phase 5B live run path: absent.
- API calls, stage, commit, and push: zero.

Existing tests read sealed owner package only to assert blankness; remediation agent did
not inspect owner-judgment values, and no labels exist or changed.

## Required owner action

Before any trace approval, owner must update
`audits/phase5b/free_tier_owner_confirmation.json` with a fresh non-secret confirmation:

1. Active Google AI Studio project shows Plan: Free.
2. No billing account is linked.
3. Confirmation covers current process environment and active credential context.
4. Credential/environment context has not changed since confirmation.

Do not store key, key fragment, project ID, billing ID, screenshots containing secrets,
or environment dumps. After owner confirmation, regenerate affected config-bound hashes,
review, commit, then create separate trace approval. Full approval remains unavailable
until trace repeatability gate passes.
