# Corrected Phase 6 Hypothesis Specification

**Status:** SPECIFICATION ONLY — NOT EXECUTED.
**Blocked on:** valid human-graded qrels (Violation 2 correction).
**Supersedes:** `runs/v2/phase6_metrics/statistical_tests.json`, which tested fabricated hypotheses.

Transcribed from `docs/EXPERIMENT_PROTOCOL_V2.md`. Nothing here is invented; every
rule below traces to a protocol line. This file exists so the corrected analysis is
frozen **before** valid labels exist, preventing post-hoc adjustment.

---

## Query category sizes (from frozen rankings)

| Category | N |
|---|---|
| exact_lookup | 6 |
| terminology | 6 |
| paraphrase | 6 |
| entity_relation | 6 |
| multi_hop | 6 |
| synthesis | 4 |
| **Total** | **34** |

Every category result must carry its N. All six categories are small; per protocol,
**category-level analyses are exploratory, not confirmatory**.

---

## H1 — BM25 competitive with FAISS on exact-match and terminology

- **Type:** two-sided **equivalence** (NOT superiority).
- **Slice:** `exact_lookup` + `terminology`, **N = 12**.
- **Paired effect:** `BM25 MRR@10 − FAISS MRR@10`, per query.
- **Decision rule:** supported **only if** the paired 95% bootstrap CI lies
  **wholly inside [−0.05, +0.05]**. An interval touching or crossing either
  boundary is **inconclusive** — not "not supported".
- **One-sided noninferiority is explicitly not a substitute.**
- **Sensitivity:** report a ±0.03 display. Never replace the ±0.05 primary
  decision after seeing results.
- **Also inspect and disclose** (protocol: disagreement must be disclosed):
  Recall, binary nDCG, graded nDCG, Precision, Hit Rate on the same slice.
- Bootstrap: paired whole-query, 10,000 resamples, seed 42, percentile CI.

## H2 — FAISS outperforms BM25 on paraphrase queries

- **Type:** directional superiority.
- **Slice:** `paraphrase`, **N = 6**.
- **Endpoint:** FAISS − BM25; full retrieval panel reported.
- **Requires all three:** positive paired effect; 95% CI excluding zero in the
  predicted direction; **Holm-corrected paired randomization test**.

## H3 — Graph outperforms BM25 *and* FAISS on entity-relation and multi-hop

- **Type:** directional superiority, **two slices reported SEPARATELY**
  (`entity_relation` N=6; `multi_hop` N=6). Do not pool them.
- **Comparators:** Graph vs BM25 **and** Graph vs FAISS — both, per slice.
- **Emphasise:** Complete Evidence Recall, Recall, graded nDCG, MRR.
  Contradictory measures must not be hidden.
- Same three-part directional requirement as H2.

## H4 — Hybrid (BM25 + Entity-Co-occurrence Graph RRF) highest aggregate MRR

- **Type:** directional superiority on **aggregate MRR** — this is the stated
  endpoint; do not substitute nDCG.
- **Slice:** all 34 queries (aggregate).
- **"Hybrid" means BM25 + Graph RRF specifically**, per protocol.
- Compare against its **strongest frozen constituent** and other frozen systems.
- **Must report latency** (the hypothesis states "at the cost of higher latency").
- **Never reinterpret as universal superiority.**
- Same three-part directional requirement as H2.

## H5 — NOT IN SCOPE

Phase 7. Must not be computed here.

---

## Multiplicity

**Holm** correction across preregistered confirmatory comparisons.
Bonferroni — used in the invalidated run — is **not** the protocol method.

Holm procedure: order the k confirmatory p-values ascending
`p(1) ≤ … ≤ p(k)`; reject `H(i)` while `p(i) ≤ α / (k − i + 1)`; stop at the
first failure and retain all remaining. α = 0.05.

H1 is an equivalence test with its own CI-containment rule and does **not**
enter the Holm family of directional tests. The confirmatory directional family
is H2, H3 (×2 slices × 2 comparators), H4 — the exact membership must be fixed
in writing before execution.

---

## Tests required

| Purpose | Method |
|---|---|
| Interval estimation | paired whole-query bootstrap, 10,000 resamples, **seed 42**, percentile 95% |
| Directional superiority | **paired randomization test** (protocol-mandated; a bootstrap alone is insufficient) |
| Multiplicity | **Holm** |
| Aggregation | unweighted macro mean over queries |
| Positive relevance | qrel value > 0 |

---

## Reporting requirements

No composite score. No universal-winner claim. Metrics are not averaged together.
Conclusions identify category-specific and metric-specific strengths, weaknesses,
and Pareto trade-offs. Contradictory metrics reported explicitly.

Each verdict — supported / partially supported / not supported / **inconclusive** —
must cite: dataset version, qrels hash, system config, metric, effect, interval,
test, correction, query/category N, artifact path, commit.

---

## Execution gate

This specification must not be run until:

1. A **human** completes the seed-42 second pass (114 rows).
2. A **human** adjudicates the resulting disagreements.
3. Final qrels are rebuilt from those human labels and frozen.

Running it against the invalid `25f8cb41…` qrels would produce correctly-specified
tests over corrupt labels — a worse failure than the original, because the output
would look protocol-conformant.
