# Dashboard results log

## Environment and provenance

- Branch: `feat/dashboard`
- Evidence commit: `7bc5bda9c6fc01964bab0247145699fe14e35175`
- Evidence date: 2026-07-29
- Dashboard Python: 3.14.4
- Primary qrels: `final_pooled` owner-adjudicated
- Bootstrap: 10,000 whole-query samples, seed 42

## Gate 1 — one verified data contract

Command:

```bash
/tmp/rag-dashboard-venv/bin/python dashboards/build_dataframe.py
```

Result: **passed**.

- 170 rows = 34 questions × 5 systems; 17 columns; nulls 0.
- Category counts: 6 exact lookup, 6 terminology, 6 paraphrase, 6 entity relation,
  6 multi-hop, 4 synthesis.
- Blacklisted source reads: 0.
- Maximum final-pooled reconciliation delta: `1.1102230246251565e-16`.
- Maximum known-gold reconciliation delta: `2.220446049250313e-16`.
- Every source path and SHA-256: `data/gate1_reconciliation.json`.

Reproduced aggregate values:

| System | MRR@10 | Recall@10 | Graded nDCG@10 | Complete evidence recall@10 |
|---|---:|---:|---:|---:|
| BM25 | 0.941176 | 0.800754 | 0.823500 | 0.411765 |
| FAISS windowed-max | 0.827941 | 0.700087 | 0.688270 | 0.294118 |
| Entity Graph | 0.676471 | 0.610333 | 0.621362 | 0.411765 |
| Hybrid RRF | 0.955882 | 0.844885 | 0.878327 | 0.500000 |
| Prompt-RAG reranker | 0.977941 | 0.835509 | 0.890687 | 0.588235 |

H5 source reproduced from same commit:

- ρ(MRR@10, faithfulness) = `-0.033280`, 95% CI `[-0.067153, -0.025598]`.
- ρ(complete-evidence-recall@10, completeness) = `+0.339535`,
  95% CI `[+0.158109, +0.506690]`.
- Labels: 26 human owner + 144 offline-AI; exploratory/descriptive only.

Gate 1 output SHA-256:

| Artifact | SHA-256 |
|---|---|
| `data/per_query_pilot.csv` | `c5a870faf12149faa0befeae080ce87fb3afe5a546310b5dc0049254a5e7a54c` |
| `data/per_query_pilot.parquet` | `c00e70bd40dc6320927edd35cb95af4f18570cb336f7c42f5e96b843adcd0e67` |
| `data/dashboard_payload.json` | `159119219368ae2a48fe6e3351888c30f3be37c9ab503ecee141e5f9fcfcebd3` |
| `data/gate1_reconciliation.json` | `cc2c43659a6f3c677d0f7051f3af7552791a96ed237328ead4fd3ad9b19fb65d` |

## Gate 2 — Screen 1 record

Command:

```bash
/tmp/rag-dashboard-venv/bin/python dashboards/screen1_figures.py
```

Result: **passed**. Six standalone 300-dpi PNG and six vector PDF figures produced:
response grid, tie-aware category MRR with CIs, H1–H4 forest, failure taxonomy with CIs,
real H5 aggregate, and provenance block. Each figure includes n, qrels base, seed, evidence
commit, and date. Hashes: `data/screen1_manifest.json`.

Findings shown: H1 inconclusive; H2 not supported; H3 not supported (0/16 tests); H4 not
supported overall; H5 rank quality does not positively predict faithfulness while evidence recall
has modest positive association with completeness.

## Gate 3 — Screen 2 exhibit

Commands:

```bash
python3 dashboards/vendor_assets.py
python3 dashboards/build_screen2.py
```

Result: **passed**.

- Required panels present: response grid, illustrative ability dial, 3D field, radar,
  tie-aware category bars, honest H5 aggregate, provenance.
- Difficulty direction: easy 0 → hard 1.
- 3D and category winner logic: exact tied maxima remain co-winners.
- External runtime dependencies: 0.
- GSAP 3.12.5 and Three.js r128 are pinned, hash-checked, and inline.
- Boot diagnostic hides after successful JavaScript initialization.
- Headless Chrome screenshot confirmed successful boot and rendered response grid.
- Inline JavaScript syntax checked with Node `vm.Script`.
- Output: 752,485 bytes; SHA-256
  `d9e5c9b5ff0f3399136c081112af290abadf94923b0f8b6ca4aa63dd66df7d14`.

## Reproducibility and tests

Commands:

```bash
/tmp/rag-dashboard-venv/bin/python dashboards/build_dataframe.py
/tmp/rag-dashboard-venv/bin/python dashboards/build_dashboard.py
/tmp/rag-dashboard-venv/bin/python -m pytest -q dashboards/tests
git diff --check
```

- Two consecutive rebuilds: 21 generated artifacts byte-identical.
- Dashboard suite: 10 passed.
- Full repository suite attempt: collection stopped with 10 missing-dependency errors
  (`anthropic`, `sentence_transformers`) in isolated dashboard environment.
