# Dashboard wake-up summary

## Built

- Separate `dashboards/` package containing all dashboard code, assets, generated data, figures,
  tests, audit logs, and offline HTML.
- One validated dataframe: 170 rows = 34 questions × 5 systems.
- Six interactive Plotly charts in self-contained `dashboard.html`.
- Six matching dissertation figures in 300-dpi PNG and vector PDF.
- Query browser with ranks, failure types, frozen reference answers, and 183 positive pooled
  evidence passages.
- Deterministic rebuild manifest covering 31 dashboard inputs/outputs.

## Verified

- Primary qrel basis: `final_pooled` owner-adjudicated.
- Seed-42-only validity guard passed; blacklisted reads: 0.
- Aggregate reconciliation maximum delta: `1.1102230246251565e-16`.
- Two full rebuilds were byte-identical.
- Dashboard tests: 9 passed.

## Real versus blocked

- Real: retrieval results for BM25, FAISS windowed-max, Entity Graph, Hybrid RRF, and Prompt-RAG
  reranker; H1–H4 seed-42 statistics; rank/failure, category, complementarity, and oracle analyses.
- Blocked: H5 generation correlations and generated-answer browser. Required Phase 7
  `h5_results.json` is absent from required base commit `6049994`; no later-branch values copied.
- Full repository suite is not green at this base: 478 passed, 14 failed, 9 xfailed. Failures are
  outside dashboard and documented in `BLOCKERS.md`.

## Open

Open `dashboards/dashboard.html` directly in a modern browser. No server or network needed.

Rebuild using commands in `dashboards/README.md`.
