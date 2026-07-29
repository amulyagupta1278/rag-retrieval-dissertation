# Dashboard wake-up summary

## Open

- Screen 1 record: `dashboards/dashboard.html`
- Screen 2 exhibit: `dashboards/screen2_exhibit.html`

Both work locally. Screen 2 needs no server or internet.

## Built

- One exact-commit pipeline: 170 rows = 34 questions × 5 systems.
- Six numbered Screen 1 figures in 300-dpi PNG and vector PDF.
- Seven-panel dark Screen 2 exhibit with inline GSAP and Three.js.
- Real H5 aggregate with frozen CIs and label-source disclosure; no synthetic scatter.
- Source/output hash manifests and deterministic rebuild tests.

## Integrity fixes

- FAISS correctly described as dense-vector baseline.
- Difficulty direction corrected: hardest means most systems miss.
- Query and category ties retain every co-winner.
- Exhibit runs offline.
- One provenance commit used everywhere:
  `7bc5bda9c6fc01964bab0247145699fe14e35175`.
- Invalid seed-123 lineage read count: 0.

## Verification

- Gate 1 reconciliation: passed.
- Gate 2 figures: passed.
- Gate 3 exhibit: passed; headless browser boot confirmed.
- Dashboard tests: 10 passed.
- Consecutive builds: byte-identical.
- Full repository suite remains environment-limited by missing non-dashboard dependencies;
  documented in `BLOCKERS.md`.
