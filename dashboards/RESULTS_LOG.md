# Dashboard results log

## Environment

- Base commit: `6049994253e78a353442f594d027980b1fd89689`
- Branch: `feat/dashboard`
- Dashboard interpreter: Python 3.14.4 in temporary local virtual environment
- Dashboard dependencies: pinned in `dashboards/requirements.txt`

## Gate 1 — authoritative dataframe and reconciliation

Command:

```bash
/tmp/rag-dashboard-venv/bin/python dashboards/build_dataframe.py
/tmp/rag-dashboard-venv/bin/python -m pytest -q dashboards/tests/test_build_dataframe.py
```

Result: **PASSED**.

- Primary qrel base: `final_pooled`
- Rows: 170 = 34 queries × 5 systems
- Columns: 17
- Categories: exact lookup 6, terminology 6, paraphrase 6, entity relation 6,
  multi-hop 6, synthesis 4
- Null values: 0
- Duplicate query/system rows: 0
- Blacklisted sources read: 0
- Validity guard: `passed_seed42_only`
- Primary maximum absolute reconciliation delta versus
  `system_comparison_table.json`: `1.1102230246251565e-16`
- Known-gold robustness maximum absolute reconciliation delta: `2.220446049250313e-16`
- Tests: 3 passed

Output hashes:

| Artifact | SHA-256 |
|---|---|
| `dashboards/data/per_query_pilot.csv` | `c5a870faf12149faa0befeae080ce87fb3afe5a546310b5dc0049254a5e7a54c` |
| `dashboards/data/per_query_pilot.parquet` | `c00e70bd40dc6320927edd35cb95af4f18570cb336f7c42f5e96b843adcd0e67` |
| `dashboards/data/evidence_browser.json` | `b0b096670ac401b6d71da5354987393adaa85e64831d55bb7e8073da3eefdfd9` |
| `dashboards/data/gate1_reconciliation.json` | `3bb00eff3a0a44ab99c162bc2f40c32b1e02dff7c5d8ef02ba92a1077bbaffb8` |

Gate 1 source hashes and every metric-level reconciliation row are stored in
`dashboards/data/gate1_reconciliation.json`.

### Validity confirmation

Builder rejects these paths before file access:

- `runs/v2/phase6_metrics/statistical_tests.json`
- `runs/v2/phase6_metrics/per_query_metrics.csv`
- `data/v2/pilot/qrels/INVALID-seed123-ai-graded-phase6.tsv`

Only seed-42 Phase 6, frozen R5 QA/qrels, frozen pilot chunk/document metadata, and five frozen ranking files entered dataframe build.
No chart was generated before this gate passed.

Evidence-browser validation: 34 queries, 183 positive pooled passages (89 grade 1, 94 grade 2),
all chunk and document IDs resolved.

## Gate 2 — core argument charts and dual-render pipeline

Command:

```bash
/tmp/rag-dashboard-venv/bin/python dashboards/build_dashboard.py
/tmp/rag-dashboard-venv/bin/python -m pytest -q dashboards/tests
```

Result: **PASSED**. Nine dashboard tests passed.

- C2: 90 category/system/metric estimates, 10,000 whole-query bootstrap samples, seed 42.
  Every interactive cell exposes mean, 95% interval, and query N; static MRR cells print same.
- C3: 34-query hit matrix; discrimination audit found 10 positive items and 24 undefined items
  where all five systems had same Hit@5. No 2PL/3PL IRT was fitted.
- C4: 10 authoritative seed-42 MRR@10 effect rows. H1 inconclusive; H2 not supported;
  H3 0/16 tests met; H4 1/4 comparisons met and not supported overall.
- C5: visibly blocked. Required H5 source is absent at base commit; zero H5 numbers displayed.
- Six Matplotlib figures emitted as 300-dpi PNG plus vector PDF. Six matching Plotly figures
  embedded in one offline HTML file with no external script source.

Aggregate values reproduced from sole primary dataframe:

| System | MRR@10 | Recall@10 | Graded nDCG@10 | CE Recall@10 |
|---|---:|---:|---:|---:|
| BM25 | 0.941176 | 0.800754 | 0.823500 | 0.411765 |
| FAISS windowed-max | 0.827941 | 0.700087 | 0.688270 | 0.294118 |
| Entity Graph | 0.676471 | 0.610333 | 0.621362 | 0.411765 |
| Hybrid RRF | 0.955882 | 0.844885 | 0.878327 | 0.500000 |
| Prompt-RAG reranker | 0.977941 | 0.835509 | 0.890687 | 0.588235 |

Authoritative forest rows:

| Hypothesis/comparison | Effect | 95% CI | Verdict |
|---|---:|---:|---|
| H1 BM25−FAISS, exact+terminology | +0.066667 | [−0.083333, +0.241667] | inconclusive |
| H2 FAISS−BM25, paraphrase | −0.425000 | [−0.766667, 0.000000] | not supported |
| H3 Graph−BM25, entity relation | −0.083333 | [−0.250000, 0.000000] | not supported |
| H3 Graph−FAISS, entity relation | 0.000000 | [−0.250000, +0.250000] | not supported |
| H3 Graph−BM25, multi-hop | 0.000000 | [0.000000, 0.000000] | not supported |
| H3 Graph−FAISS, multi-hop | +0.083333 | [0.000000, +0.250000] | not supported |
| H4 Hybrid−BM25, aggregate | +0.014706 | [0.000000, +0.044118] | not supported |
| H4 Hybrid−FAISS, aggregate | +0.127941 | [+0.022059, +0.238235] | not supported |
| H4 Hybrid−Graph, aggregate | +0.279412 | [+0.147059, +0.426471] | supported comparison only |
| H4 Hybrid−Prompt-RAG, aggregate | −0.022059 | [−0.088235, +0.022059] | not supported |

## Gate 3 — rank failures and evidence browser

Result: **PASSED**.

- 170 system/query ranks rendered; 999 remains explicit “not retrieved.”
- BM25: 33 Hit@5, 1 rank 11–50 failure.
- FAISS: 34 Hit@5.
- Entity Graph: 24 Hit@5, 10 missing-evidence failures.
- Hybrid: 33 Hit@5, 1 rank 11–50 failure.
- Prompt-RAG reranker: 34 Hit@5.
- Browser contains 34 frozen questions/reference answers and 183 pooled positive passages.
- Generated answers remain omitted because H5 source is absent.

## Gate 4 — explicitly exploratory future-work panels

Result: **PASSED**.

- C7 Jaccard/unique-hit chart labels routing as unbuilt future work; unique Hit@5 count is zero
  for every system in this highly saturated pilot.
- C8 hypothetical per-query oracle MRR@10 is 1.000000; best fixed-system value is 0.977941.
  Fixed and oracle bars carry deterministic seed-42 bootstrap intervals.
- Neither panel is framed as submission evidence or an implemented router.

## Rebuild reproducibility and artifact hashes

Two consecutive full rebuilds produced byte-identical CSV, Parquet, JSON, HTML, PNG, PDF, and
manifest files. PDF timestamps are deliberately omitted.

| Artifact | SHA-256 |
|---|---|
| `dashboards/dashboard.html` | `a152d3af78d636403e549a072b8ccf1af60228cd98676afe5b5baf8f0cf62824` |
| `dashboards/data/category_bootstrap_ci.csv` | `e824247dd3a82441fb9c96ec31d35edaadfec690952b0954466b1aada7f60f02` |
| `dashboards/data/discrimination_audit.csv` | `482434a6067bddc28b74a9573f637414d45300d4c1ff6143ceebe35ae8646241` |
| `dashboards/data/hypothesis_forest_rows.csv` | `1c3d565a9ce029ebda0b76a391fa943800ae925d9dad2411301c2702464ccb31` |
| `dashboards/data/dashboard_build_manifest.json` | `c37ee64e22b71531be2823ac0b0bdd44a4b7cf6cc580fcda268fb3fbd50eddc1` |

## Tests

Dashboard suite: **9 passed**.

Full base-repository suite under Python 3.13 with declared dependencies: **478 passed, 14 failed,
9 xfailed**. All 14 failures are pre-existing base-state issues outside `dashboards/`: missing
ignored owner-adjudication output and `.DS_Store`, missing README hypothesis section, and historical
frozen-manifest mismatch for `pyproject.toml`. No historical file was modified to hide them.
