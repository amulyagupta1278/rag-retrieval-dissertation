# Dashboard decisions

1. Keep every dashboard-specific file under top-level `dashboards/`:
   code, generated data, figures, HTML, logs, tests, requirements, and documentation.
2. Treat repository evidence outside `dashboards/` as read-only input.
3. Build on isolated branch `feat/dashboard` from merged `origin/main` commit `6049994`; leave
   dirty Phase 8 worktree untouched.
4. Use `final_pooled` owner-adjudicated qrels as primary dataframe basis. Validate known-gold
   sources separately; never mix bases in one chart.
5. Classify first positive-qrel rank as: `hit` (1–5), `near_miss` (6–10),
   `ranking_failure` (11–50), `missing_evidence` (not in returned ranking).
6. Use deterministic whole-query bootstrap intervals: 10,000 resamples, seed 42.
7. Do not fit 2PL/3PL IRT. Discrimination audit is descriptive point-biserial across five systems.
8. Use Matplotlib for 300-dpi PNG/PDF and Plotly for one self-contained offline HTML file.
9. Use local temporary virtual environment for dashboard dependencies; commit pinned
   `dashboards/requirements.txt`, never commit environment files.
10. Omit H5 charts until required source exists at target base. Do not import later-branch evidence.
11. Provide C6 browser from a deterministic Gate 1 derivative containing frozen reference answers
    and all 183 positive pooled evidence passages. Generated-answer browsing remains blocked with H5.
12. Remove PDF creation timestamps so full dashboard rebuild is byte-deterministic.
