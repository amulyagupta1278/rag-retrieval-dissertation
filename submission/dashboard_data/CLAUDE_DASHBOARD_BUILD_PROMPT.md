# Claude dashboard build prompt

Copy everything below into Claude Code while working in dashboard worktree:

```text
You are rebuilding dissertation dashboard for repository:

/Users/amulyagupta/Desktop/rag-retrieval-dissertation-dashboard

Dashboard branch:

feat/dashboard

Authoritative data handoff exists in sibling worktree:

/Users/amulyagupta/Desktop/rag-retrieval-dissertation/submission/dashboard_data

Do not design from memory or copy unsupported claims from old dashboard. Read these files first:

1. DATA_CONTRACT.md
2. dashboard_payload_v2.json
3. manifest.json
4. retrieval_metrics.csv
5. category_metrics.csv
6. query_metrics.csv
7. generation_quality.csv
8. h5_correlations.csv
9. r4_pairwise_statistics.csv
10. operations_cost_latency.csv
11. validation_status.csv
12. scope_comparison.csv

Also read canonical reports:

- /Users/amulyagupta/Desktop/rag-retrieval-dissertation/submission/FINAL_DISSERTATION_REPORT_DRAFT.md
- /Users/amulyagupta/Desktop/rag-retrieval-dissertation/docs/PHASE8_R4_FINAL_REPORT.md
- /Users/amulyagupta/Desktop/rag-retrieval-dissertation/audits/phase8_r4/canonical_status.json

Goal
====

Build two coordinated outputs from one verified data model:

1. Interactive dissertation dashboard for exploration and defence demonstration.
2. Academic evidence dashboard producing publication-ready static figures/tables for report.

Preserve existing dashboard history. Work only on feat/dashboard. Do not alter pilot, R4 evidence,
human-review CSVs, hashes, manifests, or source artifacts. Copy normalized handoff files into
dashboards/data/v2/ byte-identically and record source SHA-256 values.

Research framing — non-negotiable
=================================

- Human-validated V2 pilot remains canonical dissertation evidence.
- Phase 8 R4 is human-owner-validated exploratory scaling evidence. It remains non-preregistered.
- Never merge pilot and R4 into one unlabeled leaderboard.
- Never describe R4 labels, mappings, or synthesis questions as human validated.
- Never include 20 synthesis candidates in primary five-category R4 metrics.
- Never present R4 pairwise tests as preregistered H1–H4 confirmation.
- Never encode unavailable latency as zero.
- Never average six generation dimensions into an invented composite score.
- Show label-source/claim-class badge beside every metric, chart, table, and download.
- Use exact values from normalized data; no manual transcription.

Required badges
===============

- CANONICAL — human-validated pilot retrieval evidence.
- MIXED LABELS — pilot generation: 26 owner labels + 144 disclosed AI labels.
- OWNER VALIDATED — R4 gold crosswalks and generation labels completed by owner.
- PRIOR AI LABELS — preserved only for owner–AI comparison, not final R4 scoring.
- EXPLORATORY — R4 statistics and scaling conclusions.
- SEPARATE — 20 synthesis candidates outside primary metrics.

Information architecture
========================

Use one persistent top navigation with these views:

1. Overview
   - Research question and five systems.
   - Pilot/R4 benchmark toggle, default Pilot.
   - Scale cards: 22→130 documents, 140→954 chunks, 34→100 primary questions.
   - Validation-state cards using validation_status.csv.
   - Core conclusion: retrieval quality is multidimensional and scale-sensitive.
   - Clear disclaimer: Pilot supports claims; R4 supports engineering scalability.

2. Retrieval performance
   - Benchmark selector: Pilot / R4.
   - R4 split selector: Locked test (default), Development, All 100 descriptive.
   - Metric selector: MRR@10, Recall@10, Precision@10, nDCG@10, Hit@10.
   - Complete Evidence Recall available only where supplied; show N/A elsewhere.
   - Five-system grouped bars or dot plot.
   - Sort toggle and exact-value table.
   - Explicit winner cards generated from selected metric, never hard-coded.

3. Category analysis
   - System × category heatmap using category_metrics.csv.
   - Metric selector.
   - Category profile/radar only if readable; heatmap remains primary.
   - Pilot shows six categories including synthesis.
   - R4 shows five primary categories; synthesis excluded and separately disclosed.
   - Display category sample size.

4. Hypotheses and statistics
   - Pilot H1–H4 section sourced from canonical preregistered results path named in payload.
   - Do not invent or simplify hypothesis definitions.
   - Show verdicts: H1 inconclusive; H2/H3/H4 not supported.
   - Separate R4 exploratory section using r4_pairwise_statistics.csv.
   - Forest plot: left-minus-right nDCG difference, 95% CI, Holm-adjusted p.
   - Visually separate statistical detection from hypothesis support.

5. Generation quality
   - Pilot Phase 7 and R4 selector.
   - Six independent dimensions: correctness, faithfulness, completeness, citation accuracy,
     unsupported-claim severity, abstention quality.
   - Unsupported-claim severity direction is inverted: lower is better.
   - Human/AI label disclosure always visible.
   - Abstention counts by system.
   - H5 panel using h5_correlations.csv with rho, CI, status, and interpretation limits.
   - Show non-estimable constant dimensions as N/A, not zero.

6. Query explorer
   - Use query_metrics.csv: 670 query-system rows.
   - Filters: benchmark, split, category, system, success/failure, metric range.
   - Question and reference answer panel.
   - Per-system metric comparison for selected query.
   - Search by question ID or text.
   - Download filtered rows as CSV.
   - Claim-class badge remains visible.

7. Cost and operations
   - Use operations_cost_latency.csv.
   - Cost, hard cap, valid records, failures, retries, measured latency.
   - Prompt-RAG R4 retrieval mean latency 16.820007 s.
   - Other missing latency displayed as “Not measured”.
   - Explain API cost versus offline methods.

8. Validation and provenance
   - Show completed 260-row human-review status:
       * 140 R4 gold mappings
       * 100 R4 generated answers
       * 20 synthesis candidates
   - Current state: 260/260 owner reviewed; mappings 139 grade-2 and one grade-0; synthesis
     12 accept, 4 revise, 4 reject.
   - Link/download three review CSV packages from:
     /Users/amulyagupta/Desktop/rag-retrieval-dissertation/submission/human_review/phase8_r4
   - Show source artifact paths and SHA-256 values from manifest.json.
   - Explain pilot/R4 evidence boundary.

Interactive dashboard requirements
==================================

- Static-build compatible; must run offline after build.
- No CDN/runtime network dependency. Vendor locally or use native web APIs.
- Responsive at 1440×900, 1920×1080, 1024×768, and 390×844.
- Keyboard navigation, visible focus, semantic HTML, ARIA labels, minimum WCAG AA contrast.
- Reduced-motion support. Motion must explain state change, never decorate continuously.
- Persist selected benchmark/split/metric in URL or local state.
- Tooltips must include exact value, N, split, source class, and metric definition.
- Loading, empty, error, and unavailable states required.
- No fake live data, fake counters, fabricated percentages, or decorative 3D scene.
- Prefer restrained academic visual language: deep navy, blue, orange accent, neutral background.
- Avoid glassmorphism, excessive gradients, tiny labels, scrolling marquees, and visual clutter.

Academic dashboard requirements
===============================

Generate reproducible export assets from same normalized data:

- Figure 1: Pilot five-system MRR/Recall/nDCG comparison.
- Figure 2: R4 locked-test five-system MRR/Recall/nDCG comparison.
- Figure 3: Pilot six-category heatmap.
- Figure 4: R4 five-category locked-test heatmap.
- Figure 5: Pilot H1–H4 outcome/forest panel using canonical definitions.
- Figure 6: R4 exploratory pairwise nDCG forest plot.
- Figure 7: Generation-quality six-dimension small multiples with label-source disclosure.
- Figure 8: H5 correlations with confidence intervals and non-estimable markers.
- Figure 9: Corpus/benchmark scaling comparison.
- Figure 10: Validation/provenance matrix.

For every academic figure:

- Export SVG and PDF where possible, plus 300-DPI PNG.
- Use colorblind-safe palette and patterns/labels so meaning does not rely on color.
- Minimum readable print font size.
- Include numbered caption, metric definition, sample size, split, claim class, and source path.
- Do not crop titles, legends, footnotes, or confidence intervals.
- Store figures under dashboards/figures/v2/.
- Store machine-readable figure data under dashboards/data/v2/figure_sources/.

Required tables
===============

- Pilot aggregate retrieval metrics.
- R4 locked-test retrieval metrics.
- Category metrics for both benchmarks.
- Pilot hypothesis outcomes.
- R4 exploratory pairwise comparisons.
- Generation quality by system and label source.
- Cost/latency/failure summary.
- Validation and provenance status.

Export tables as CSV and print-ready HTML. Never round source files; round display to four decimals.

260-row human-review integration
================================

Owner review is frozen. Load final status from `audits/phase8_r4_human_validated/` and final data from
`runs/phase8_r4_human_validated/`:

- Frozen completed files:
  phase8_r4_gold_mapping_review_140_COMPLETED.csv
  phase8_r4_generation_human_review_100_COMPLETED.csv
  phase8_r4_synthesis_candidate_review_20_COMPLETED.csv
- Validate exact row counts, unique IDs, allowed grades/decisions, blanks, and protected columns.
- Never overwrite automated source files.
- Use recalculated owner-validated metrics from dashboard payload; do not recompute in frontend.
- Keep synthesis separate despite completed review: 12 accepted, 4 revise, 4 reject.

Engineering structure
=====================

- Keep data preparation separate from rendering.
- One schema-validated data loader.
- One chart registry mapping chart IDs to source dataset, filters, caption, and claim class.
- One export pipeline shared by interactive and academic views.
- Avoid duplicate metric constants in JavaScript/HTML.
- Preserve exact source hashes in build manifest.
- Fail closed if payload schema, source hash, row count, system set, or benchmark set changes.

Tests and acceptance criteria
=============================

Data tests:

- dashboard_payload_v2.json loads and schema_version=1.
- retrieval rows=20, category rows=55, query rows=670.
- generation rows=10, H5 rows=8, R4 comparison rows=10.
- exactly five systems per benchmark.
- R4 locked test N=40; development N=60; all descriptive N=100.
- pilot N=34.
- source hashes match manifest.
- no missing value converted to numeric zero.

UI tests:

- Every navigation route renders.
- Pilot is default.
- R4 charts show OWNER VALIDATED and EXPLORATORY badges.
- Toggle and filters update chart, table, caption, and URL state together.
- Query explorer returns correct five-system panel.
- Keyboard-only navigation works.
- Mobile viewport has no horizontal overflow except intentionally scrollable tables.
- Print view fits A4/Letter without clipped captions.

Visual regression:

- Capture desktop, tablet, and mobile screenshots for every view.
- Check overflow, collisions, clipped labels, unreadable legends, and empty plots.
- Test with long question/reference-answer text.

Repository rules
================

- Existing historical dashboard commits remain unchanged.
- New work uses additive/replacement commits on feat/dashboard.
- Do not modify sibling research worktree.
- Do not make API calls.
- Do not access credentials.
- Do not push until tests, source-hash verification, and screenshot review pass.
- Commit logical checkpoints.
- Final report must list files changed, tests, screenshots, data hashes, known limitations,
  current human-review status, commit SHA, and exact local launch command.

First response before coding
============================

Return:

1. Existing-dashboard defect audit.
2. Proposed component/data architecture.
3. Exact files to preserve, replace, add, and archive.
4. Test plan.
5. Risks or missing dependencies.

Then implement without requesting design choices unless required evidence is genuinely missing.
```

## Input files Claude should receive

Everything resides under:

```text
/Users/amulyagupta/Desktop/rag-retrieval-dissertation/submission/dashboard_data/
```

Human-review packages reside under:

```text
/Users/amulyagupta/Desktop/rag-retrieval-dissertation/submission/human_review/phase8_r4/
```

Claude must not treat unfinished review sheets as completed evidence.
