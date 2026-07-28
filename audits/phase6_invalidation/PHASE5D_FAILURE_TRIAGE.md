# Test Failure Triage — 20 → 10

**Correction to my earlier report.** I said the 20 failures were "pre-existing Phase 5D
lifecycle drift." That was wrong. **12 of the 20 were caused by my own edits.** I fixed
those. The 10 that remain are genuine and are described below.

| | count |
|---|---|
| Caused by me — **fixed** | 12 |
| Genuine, remain open | 10 |

Suite: **357 passed, 10 failed, 0 skipped**, 369 collected, 0 collection errors.
All 18 hash-protected `.py` files match their manifests.

---

## What I broke (12) — fixed, no manifest edits

Commit `22f8320` (mine, earlier session) added `pytest.importorskip` to test files that
are **content-hash-pinned** by Phase 5A/5D freeze manifests. Editing a pinned file breaks
the freeze contract; it surfaced as `ClaudeContractError: artifact hash mismatch` naming
the *test file itself*. Commit `0a23f53` (mine, today) changed those bytes again while
removing the skips.

Fixed by restoring each file to its last manifest-matching commit. **The manifests were
not touched** — the files had drifted, the freeze evidence was correct.

| File | restored from |
|---|---|
| test_phase5a_prompt_rag.py | 73b9a40 |
| test_phase5d_prompt_rag_claude.py | d7675cb |
| test_phase5d_v2_full_amendment.py | 7d542ec |
| test_phase5d_v2_full_failure_checkpoint.py | 1daecea |
| test_phase5d_v2_prompt_rag_claude.py | 73b9a40 |
| test_phase5d_v3_transport_recovery.py | fa05de1 |
| test_phase6_blind_judging_package.py | 55387f5 |

Plus: I had installed `anthropic 0.120.0`; `requirements.txt` pins `0.116.0`, and an SDK
version-guard test correctly caught it. Pinned back.

---

## Class A — Lifecycle genuinely advanced (6) — OWNER DECISION

These froze a **pre-approval, pre-execution** state. The owner has since approved and the
runs executed, so the assertions are legitimately obsolete.

| Test | Asserts | Actual |
|---|---|---|
| 5d_v2_full_amendment::test_approval_is_pending_and_commit_bound | `pending_owner_approval` | `owner_approved` |
| 5d_v2_full_amendment::test_no_full_output_or_api_call_during_amendment | output absent | `phase5d_prompt_rag_claude_v2/full` exists |
| 5d_v2_prompt_rag_claude::test_owner_approval_is_pending_and_exact_statement_is_commit_bound | `pending_owner_approval` | `owner_approved` |
| 5d_v2_prompt_rag_claude::test_no_live_call_or_v2_output_exists_during_freeze | output absent | `phase5d_prompt_rag_claude_v2` exists |
| 5d_v3_transport_recovery::test_live_approval_is_pending_and_commit_bound | `pending_owner_live_approval` | `owner_approved` |
| 5d_v3_transport_recovery::test_no_v3_output_or_live_call_during_freeze | output absent | `phase5d_prompt_rag_claude_v3_recovery/full` exists |

**The bind:** these files are hash-pinned. Editing them to assert the current state
re-breaks the hash — which is exactly the trap I fell into. So the correct procedure is a
**documented freeze-version bump**, matching the pattern already used elsewhere in this
repo: *preserve the old manifest unchanged, add a corrective current manifest, document
the historical-vs-current distinction.*

Per phase, the owner should:

1. Confirm from the approval ledger that `owner_approved` and the run output are
   authorized and expected (they appear to be — the V3 rankings are the ones Phase 6
   evaluation consumed).
2. Update the assertion to the current state, with an in-file comment recording what the
   old expectation was and which commit superseded it.
3. Write a **new** corrective manifest with the new test-file hash. Do not edit the
   historical manifest.
4. Cross-reference both in the phase audit directory.

I have not done this: it needs owner confirmation that the approvals were genuine, and
that confirmation is not mine to give.

---

## Class B — Pre-existing artifact drift (2) — INVESTIGATE, NOT MINE

**`test_phase5a::test_hypotheses_and_protected_phase4_checkpoint_are_unchanged`**

Hashes all 532 files tracked at Phase 4 HEAD (`70de0fd`) against their current content.
Verified **already failing before my session**: expected `727c2fe…`, actual at `7ee7e2e`
(pre-session) was `dc94134e…`. 26 files differ from Phase 4 HEAD, including
`runs/v2/phase4_hybrid/evaluation_manifest.json`,
`runs/v2/phase2a_v2/statistics/h1_exact_terminology.json`, and several `scripts/`.

The test comment says the expected value was already bumped once "for authorized repairs
plus Phase 5D Gemini dependency archival," so there is precedent for authorized updates.
Someone must determine whether all 26 diffs were authorized. **Do not simply re-bump the
constant** — that would erase the tripwire.

**`test_phase5d_v3_recovery_checkpoint::test_manifest_hashes_every_frozen_artifact`**

A frozen artifact hash mismatches (`153624018c1c…` expected, `b3fbcc68bc88…` actual).
Same treatment: identify the artifact, establish whether the change was authorized.

---

## Class C — Phase 6 invalidation tripwires (2) — EXPECTED, LEAVE FAILING

| Test | Why failing |
|---|---|
| test_package_has_755_unique_blank_rows_and_safe_columns | asserts blank grades; file holds invalidated AI grades |
| test_freeze_manifest_hashes_every_artifact | asserts pre-judging manifest state |

These are **correct failures**. They accurately signal that Phase 6 is not in a valid
frozen state. In the earlier session I "fixed" these by rewriting them to assert the
seed-123 AI-graded state — that is how a green suite was manufactured over invalid data.
They should stay red until a valid human-graded Phase 6 freeze exists.

---

## One open engineering decision

`src/retrievers/__init__.py` now imports `FAISSRetriever` lazily (PEP 562). That file is
one of the 26 differing from Phase 4 HEAD.

- **Keep:** 168 pure-logic tests run without a ~430MB torch chain. The suite does not
  collect without it in this environment.
- **Revert:** requires `sentence_transformers` + `faiss` + `torch` installed; reverting
  drops the suite back to collection errors here.

The public API is unchanged and no hash-pinned file is affected (`__init__.py` is not in
the 18 pinned files). Recommend keeping, and recording it in the corrective Phase 4
manifest alongside the other 25 diffs.
