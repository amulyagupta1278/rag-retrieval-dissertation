# Dashboard data handoff

This directory contains frontend-neutral, evidence-backed data for rebuilding dissertation
dashboard. It does not contain layout, styling, or UI code.

## Required framing

Dashboard must open on human-validated V2 pilot. Phase 8 R4 must appear as separate exploratory
scaling view. Never merge pilot and R4 metrics into one leaderboard.

- **Pilot:** 22 documents, 140 chunks, 34 questions, 755 human relevance labels.
- **R4:** 130 documents, 954 chunks, 100 primary questions, 140 automatic crosswalk mappings.
- **R4 synthesis:** 20 automated candidates, excluded from primary five-category metrics.
- **Pilot generation:** 26 human-owner labels plus 144 disclosed AI labels.
- **R4 generation:** 100 AI-assigned labels and zero owner-labelled overlap.

## Files

| File | Dashboard use |
|---|---|
| `dashboard_payload_v2.json` | Single-load payload containing all normalized summaries |
| `scope_comparison.csv` | Pilot-versus-R4 scale cards |
| `retrieval_metrics.csv` | Aggregate leaderboards and metric selectors |
| `category_metrics.csv` | Category heatmaps and system profiles |
| `query_metrics.csv` | 670 query-system rows for drill-down and failure analysis |
| `generation_quality.csv` | Six-dimension answer-quality comparison |
| `h5_correlations.csv` | Retrieval-to-generation association panel |
| `r4_pairwise_statistics.csv` | Exploratory R4 forest/table view |
| `operations_cost_latency.csv` | Cost, validity, retry, and latency cards |
| `validation_status.csv` | Mandatory human/AI provenance badges |
| `manifest.json` | Source and generated-file SHA-256 hashes |

## Recommended screens

1. **Overview:** scope, validation badges, core finding, pilot/R4 toggle.
2. **Retrieval:** aggregate leaderboard, metric selector, category heatmap.
3. **Hypotheses:** pilot H1–H4 outcomes and separate R4 exploratory comparisons.
4. **Generation:** correctness, faithfulness, completeness, citations, unsupported claims,
   abstention.
5. **Operations:** latency, cost, failures, retries, model disclosure.
6. **Evidence:** source paths, hashes, limitations, downloadable human-review packages.

## Hard UI rules

- Show claim-class badge beside every chart: `CANONICAL`, `MIXED LABELS`, `AUTOMATED`, or
  `EXPLORATORY`.
- Default to locked-test R4 metrics when R4 selected; label all-100 and development values clearly.
- Never show missing latency as zero.
- Never call R4 human validated until `validation_status.csv` changes through frozen owner review.
- Never include 20 synthesis candidates in primary R4 five-category totals.
- Never present R4 pairwise tests as preregistered H1–H4 confirmation.

Rebuild with:

```bash
python scripts/build_dashboard_data_handoff.py
```
