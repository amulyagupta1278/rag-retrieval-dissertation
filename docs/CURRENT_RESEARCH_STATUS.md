# Current research status

Status date: 2026-08-07
State: **complete and submitted; defence revision in progress**

## Where things actually stand

All phases are closed. The dissertation was submitted as
`DISSERTATION_WILP_FINAL_SUBMISSION.pdf` on 2026-08-01.

| Phase | State |
|---|---|
| Phase 6 — human relevance judging | **Complete.** Blind regrade done, κ = 0.7421, 14 disagreements adjudicated, pooled qrels frozen. |
| Phase 7 — generation protocol | **Complete and executed.** |
| Phase 8 — final scale evidence | **Complete.** Option B holdout executed; R4 130-document scale run executed. |
| Phase 9 — H5 confirmatory | **Complete.** |

## Canonical evidence

`runs/canonical_v2_pilot/` is the authoritative results directory. All five systems have
frozen rankings against the final pooled qrels. Every headline figure recomputes from it:

```bash
python scripts/verify_headline_numbers.py
```

## Evidence tiers

Confirmatory claims rest on the 34-question human-validated pilot only.

The 12-question independent holdout supports generalisation claims — directional, not
decisive; paired confidence intervals cross zero.

The R4 130-document runs are **exploratory**. Labels are AI-assigned with no owner-labelled
overlap, so agreement is not estimable. They establish that the pipeline scales. They are not
confirmatory evidence and must not be cited as such.

## Open work

Not blockers on the submitted dissertation; these are the stated next steps.

1. Human review of the R4 gold crosswalks.
2. Human audit of the 100 R4 generated answers.
3. Paraphrase-only follow-up study. Some pilot paraphrase questions retained document
   terminology, which weakened the intended lexical-mismatch test for H2. Preregistration
   drafted.
4. Multilingual and independently sampled queries.
5. External multi-rater replication.

## Superseded records

Earlier revisions of this file described Phase 6 as structurally pending. That reflected the
state on 2026-07-27 and is no longer accurate.

Two historical artefacts are preserved unchanged as audit history, not as instructions:

- `audits/phase6/freeze_manifest.json` records an earlier Phase 7-open claim.
- `docs/DISSERTATION_PHASE_PLAN_RECOVERED.md` contains a stale Phase 5D next action.
