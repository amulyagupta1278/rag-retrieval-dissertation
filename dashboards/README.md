# V2 pilot dashboard

All dashboard code, generated data, static figures, offline HTML, tests, and audit logs live in
this folder. Repository evidence outside `dashboards/` is read-only input.

## Open dashboard

Open `dashboards/dashboard.html` in any modern browser. It is self-contained and requires no
server or network connection.

## Rebuild

```bash
python3 -m venv .venv-dashboard
.venv-dashboard/bin/pip install -r dashboards/requirements.txt
.venv-dashboard/bin/python dashboards/build_dataframe.py
.venv-dashboard/bin/python dashboards/build_dashboard.py
.venv-dashboard/bin/python -m pytest -q dashboards/tests
```

Expected contract: 170 rows = 34 frozen R5 questions × 5 real systems, primary
`final_pooled` owner-adjudicated qrels, seed-42 statistics, zero blacklisted reads.

## Folder map

- `build_dataframe.py`: validates sources and builds one reconciled per-query dataframe.
- `charts.py`: analysis and dual Matplotlib/Plotly chart functions.
- `build_dashboard.py`: creates static figures, analysis tables, manifest, and offline HTML.
- `assets/`: dashboard styling.
- `data/`: tidy data, analysis tables, Gate 1 audit, and output manifest.
- `data/evidence_browser.json`: frozen reference answers and positive pooled passages for C6.
- `figures/`: 300-dpi PNG and vector PDF charts.
- `tests/`: source-boundary, metric, chart, and manifest tests.
- `BLOCKERS.md`, `DECISIONS.md`, `RESULTS_LOG.md`: audit trail.

## Current evidence boundary

C2–C4 and C6–C8 use authoritative seed-42 Phase 6 evidence. C5/H5 and answer browsing remain
visibly blocked because required Phase 7 `h5_results.json` is absent at target base commit
`6049994`. Frozen reference answers and evidence passages remain available; generated-answer
browsing is blocked. No later-branch number is imported.
