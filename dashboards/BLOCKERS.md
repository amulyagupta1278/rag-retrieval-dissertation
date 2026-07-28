# Dashboard blockers

## B1 — Phase 7 H5 source absent from required base commit

- Required base: `6049994253e78a353442f594d027980b1fd89689` (`origin/main`, PR #1 merge).
- Required path: `runs/v2/phase7_generation_claude_top3_v2/evaluation_v2_ai/h5_results.json`.
- Verification: `test -f` fails at required base commit.
- Git history: path first appears later at commit
  `3725934751368b4d4c0d46d35ea16366e0ad109b`.
- Effect: C5 H5 charts and generation-answer browser are omitted and replaced by visible blocked
  notices. No value is copied from another branch or guessed.
- Unblock condition: merge verified Phase 7 evidence into `main`, then rerun dashboard build.

No retrieval-data blocker found for C2–C4 and C6–C8.

## B2 — base repository full suite is not green at commit 6049994

- Dashboard suite: 9 passed.
- Full repository suite with declared dependencies: 478 passed, 14 failed, 9 xfailed.
- Failures are outside `dashboards/`: missing ignored owner-adjudication CSV and `.DS_Store`,
  README hypothesis-section mismatch, and historical frozen-manifest hash mismatches for
  `pyproject.toml`.
- Effect: dashboard verification passes; repository-wide green status cannot be claimed from this
  base. No protected historical artifact was changed to mask failures.
