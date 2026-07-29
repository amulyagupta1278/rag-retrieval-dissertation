# Two-screen RAG evaluation dashboard

One verified pipeline produces two views of same V2 pilot evidence:

- **Screen 1 — record:** open `dashboards/dashboard.html`. It presents six numbered,
  print-grade figures. PNG and vector PDF files live in `dashboards/figures/`.
- **Screen 2 — exhibit:** open `dashboards/screen2_exhibit.html`. It is a self-contained,
  offline viva exhibit. It is not cited as evidence.

Evidence boundary: commit `7bc5bda9c6fc01964bab0247145699fe14e35175`, dated
2026-07-29. Primary qrels are `final_pooled` owner-adjudicated seed-42 evidence. Screen 2
contains inline pinned GSAP 3.12.5 and Three.js r128; it makes no network requests.

## Rebuild

Fetch evidence ref when clone does not already contain it:

```bash
git fetch origin codex/dissertation-rebuild-v2
python3 -m venv .venv-dashboard
.venv-dashboard/bin/pip install -r dashboards/requirements.txt
.venv-dashboard/bin/python dashboards/build_dataframe.py
.venv-dashboard/bin/python dashboards/build_dashboard.py
.venv-dashboard/bin/python -m pytest -q dashboards/tests
```

`build_dataframe.py` reads every study input using `git show` from exact evidence commit.
It refuses another commit and blocks invalid seed-123 paths before access. Outputs:

- `data/per_query_pilot.csv` and `.parquet`: 170 rows, 34 questions × 5 systems.
- `data/dashboard_payload.json`: only shared render payload for both screens.
- `data/gate1_reconciliation.json`: source hashes and aggregate reconciliation.

Renderers do not read repository evidence directly:

- `screen1_figures.py` builds Figures 5.1–5.6 at 300 DPI PNG and vector PDF.
- `build_screen2.py` injects same payload and pinned local libraries into one HTML file.
- `build_dashboard.py` coordinates both screens and freezes output hashes.

Vendor libraries are committed. `vendor_assets.py` is needed only to independently refetch
and verify exact pinned bytes.

## Interpretation boundary

Study compares vector-free BM25, Entity-Co-occurrence Graph, Hybrid RRF, and Prompt-RAG
reranking against dense-vector FAISS. Prompt-RAG reranks BM25 top-50 candidates; it is not
answer generation. H5 uses frozen real aggregate correlations and shows no synthetic scatter.
Pilot is exploratory: n=34, category n=4–6, and two documents supply 65/140 chunks.
