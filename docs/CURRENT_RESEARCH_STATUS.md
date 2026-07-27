# Current Research Status

Status date: 2026-07-27

Current authorized state treats Phase 6 first-pass workbook as structurally pending
independent 15% human regrade. Phase 6 is not complete. Final pooled qrels and
retrieval metrics must not be used until regrade, agreement, and adjudication gates
finish.

Phase 7 contains non-executable provider-neutral scaffolding only. No provider,
model, context depth, evaluator, cost cap, or prompt is frozen for execution. No
Phase 7 generation has occurred.

Phase 8 contains decision support and blank templates only. No final-scale option
has been chosen; no source acquisition, holdout authoring, labeling, or execution
has occurred. Pilot evidence is development evidence, not final dissertation
evidence.

Historical artifacts remain unchanged. In particular,
`audits/phase6/freeze_manifest.json` records an earlier Phase 7-open claim, and
`docs/DISSERTATION_PHASE_PLAN_RECOVERED.md` contains a stale Phase 5D next action.
Those are preserved audit history, not current instructions.

Dependency order:

1. completed blind regrade;
2. agreement calculation and explicit adjudication;
3. frozen final pooled qrels;
4. frozen Phase 6 retrieval metrics;
5. owner-frozen Phase 7 design and trace approval;
6. Phase 7 execution/evaluation;
7. Phase 8 final evidence work.

