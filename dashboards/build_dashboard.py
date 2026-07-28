#!/usr/bin/env python3
"""Build all V2 pilot charts and one self-contained offline dashboard."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.io as pio

from charts import (
    CATEGORY_LABELS,
    PILOT_NOTE,
    SYSTEM_LABELS,
    SYSTEMS,
    all_system_summary,
    bootstrap_category_intervals,
    category_leader_figures,
    complementarity_figures,
    configure_matplotlib,
    discrimination_audit,
    ensure_exact_systems,
    forest_rows,
    hypothesis_forest_figures,
    item_response_figures,
    oracle_figures,
    rank_failure_figures,
    save_static,
)


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboards"
DATA = DASHBOARD / "data"
FIGURES = DASHBOARD / "figures"
FRAME = DATA / "per_query_pilot.csv"
GATE1 = DATA / "gate1_reconciliation.json"
EVIDENCE_BROWSER = DATA / "evidence_browser.json"
STATISTICS = ROOT / "runs/v2/phase6_seed42_final/statistics/preregistered_h1_h4_results.json"
H5 = ROOT / "runs/v2/phase7_generation_claude_top3_v2/evaluation_v2_ai/h5_results.json"
CSS = DASHBOARD / "assets/dashboard.css"
OUTPUT = DASHBOARD / "dashboard.html"
MANIFEST = DATA / "dashboard_build_manifest.json"
BLACKLISTED = (
    "runs/v2/phase6_metrics/statistical_tests.json",
    "runs/v2/phase6_metrics/per_query_metrics.csv",
    "data/v2/pilot/qrels/INVALID-seed123-ai-graded-phase6.tsv",
)


def sha256(path: Path) -> str:
    """Return file SHA-256."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_inputs() -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Load sole chart dataframe and authoritative seed-42 statistics."""

    frame = pd.read_csv(FRAME)
    gate1 = json.loads(GATE1.read_text(encoding="utf-8"))
    statistics = json.loads(STATISTICS.read_text(encoding="utf-8"))
    evidence_browser = json.loads(EVIDENCE_BROWSER.read_text(encoding="utf-8"))
    if len(frame) != 170 or frame[["query_id", "system"]].duplicated().any():
        raise ValueError("dashboard dataframe must contain 170 unique query/system rows")
    ensure_exact_systems(frame["system"].unique())
    if set(frame["qrel_base"]) != {"final_pooled"}:
        raise ValueError("dashboard charts require final_pooled basis only")
    if gate1.get("blacklisted_sources_read") != []:
        raise ValueError("Gate 1 reports blacklisted source read")
    if gate1.get("validity_guard") != "passed_seed42_only":
        raise ValueError("Gate 1 validity status failed")
    if statistics.get("conclusions_are_exploratory_pilot_evidence") is not True:
        raise ValueError("statistics omit exploratory-pilot disclosure")
    if statistics.get("invalid_historical_statistics_reused") is not False:
        raise ValueError("statistics reuse invalid lineage")
    if not isinstance(evidence_browser, list) or len(evidence_browser) != 34:
        raise ValueError("evidence browser must contain 34 queries")
    return frame, gate1, statistics, evidence_browser


def _table(headers: list[str], rows: list[list[str]], numeric: set[int] | None = None) -> str:
    numeric = numeric or set()
    head = "".join(
        f'<th class="{"number" if index in numeric else ""}">{html.escape(value)}</th>'
        for index, value in enumerate(headers)
    )
    body = []
    for row in rows:
        cells = "".join(
            f'<td class="{"number" if index in numeric else ""}">{value}</td>'
            for index, value in enumerate(row)
        )
        body.append(f"<tr>{cells}</tr>")
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def _plot_html(figure: Any, *, include_library: bool, div_id: str) -> str:
    return pio.to_html(
        figure,
        full_html=False,
        include_plotlyjs="inline" if include_library else False,
        config={"displaylogo": False, "responsive": True},
        div_id=div_id,
    )


def _summary_table(summary: pd.DataFrame) -> str:
    rows = []
    for record in summary.itertuples():
        rows.append(
            [
                html.escape(SYSTEM_LABELS[record.system]),
                f"{record.mrr_at_10:.3f}",
                f"{record.recall_at_10:.3f}",
                f"{record.ndcg_graded_at_10:.3f}",
                f"{record.ce_recall_at_10:.3f}",
            ]
        )
    return _table(
        ["System", "MRR@10", "Recall@10", "Graded nDCG@10", "Complete evidence recall@10"],
        rows,
        {1, 2, 3, 4},
    )


def _hypothesis_table(statistics: dict[str, Any]) -> str:
    summaries = statistics["summaries"]
    rows = [
        ["H1", "BM25 competitive with FAISS", html.escape(str(summaries["H1"]))],
        ["H2", "FAISS improves paraphrase retrieval", html.escape(summaries["H2"]["verdict"].replace("_", " "))],
        ["H3", "Graph improves entity relation / multi-hop", "not supported (0/16 tests met)"],
        ["H4", "Hybrid has highest aggregate MRR", "not supported (1/4 comparisons met)"],
        ["H5", "Retrieval quality predicts answer quality", "blocked: required Phase 7 source absent"],
    ]
    return _table(["Hypothesis", "Preregistered claim", "Authoritative pilot verdict"], rows)


def _discrimination_table(audit: pd.DataFrame) -> str:
    flagged = audit.loc[audit["flagged"]].head(12)
    rows = []
    for row in flagged.itertuples():
        correlation = "undefined" if pd.isna(row.point_biserial) else f"{row.point_biserial:.3f}"
        ranks = " · ".join(
            f"{SYSTEM_LABELS[system]} {getattr(row, f'{system}_gold_rank')}"
            for system in SYSTEMS
        ).replace(" 999", " miss")
        rows.append(
            [
                html.escape(row.query_id),
                html.escape(row.category.replace("_", " ")),
                html.escape(row.query_text),
                correlation,
                html.escape(ranks),
            ]
        )
    return _table(["Query", "Category", "Question", "Point-biserial", "Gold rank by system"], rows, {3})


def _query_browser(frame: pd.DataFrame, evidence_browser: list[dict[str, Any]]) -> str:
    meta = (
        frame[["query_id", "query_text", "category", "difficulty"]]
        .drop_duplicates()
        .sort_values(["difficulty", "query_id"], ascending=[False, True])
    )
    blocks: list[str] = []
    evidence_by_query = {row["query_id"]: row for row in evidence_browser}
    for query in meta.itertuples():
        evidence_record = evidence_by_query[query.query_id]
        panel = frame.loc[frame["query_id"] == query.query_id].set_index("system").reindex(SYSTEMS)
        rows = []
        for system in SYSTEMS:
            rank = int(panel.loc[system, "gold_rank"])
            rendered_rank = "not retrieved" if rank == 999 else str(rank)
            css_class = "rank-hit" if rank <= 5 else "rank-miss"
            rows.append(
                [
                    html.escape(SYSTEM_LABELS[system]),
                    f'<span class="{css_class}">{rendered_rank}</span>',
                    html.escape(str(panel.loc[system, "failure_type"]).replace("_", " ")),
                    f'{float(panel.loc[system, "mrr_at_10"]):.3f}',
                ]
            )
        heading = (
            f"{html.escape(query.query_id)} · {html.escape(CATEGORY_LABELS[query.category])} · "
            f"difficulty {query.difficulty:.2f}"
        )
        passages = "".join(
            "<details><summary>"
            + html.escape(
                f"Grade {passage['grade']} · {passage['document_title']} · {passage['chunk_id']}"
            )
            + "</summary><div class=\"query-detail\"><p>"
            + html.escape(passage["text"])
            + "</p></div></details>"
            for passage in evidence_record["evidence"]
        )
        blocks.append(
            f"<details><summary>{heading}</summary><div class=\"query-detail\">"
            f"<p>{html.escape(query.query_text)}</p>"
            f"<p><strong>Frozen reference answer:</strong> {html.escape(evidence_record['reference_answer'])}</p>"
            f"{_table(['System', 'Gold rank', 'Failure type', 'MRR@10'], rows, {1, 3})}"
            "<h3>Pooled positive evidence passages</h3>"
            + passages
            + "</div></details>"
        )
    return '<div class="query-browser">' + "".join(blocks) + "</div>"


def _write_manifest(artifacts: list[Path], *, h5_available: bool) -> None:
    manifest = {
        "base_commit": "6049994253e78a353442f594d027980b1fd89689",
        "blacklisted_source_reads": 0,
        "h5_source_available": h5_available,
        "primary_qrel_base": "final_pooled",
        "source_statistics": STATISTICS.relative_to(ROOT).as_posix(),
        "validity_status": "passed_seed42_only",
        "artifacts": {
            path.relative_to(ROOT).as_posix(): sha256(path)
            for path in sorted(artifacts)
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build() -> None:
    """Generate analyses, static figures, offline HTML, and integrity manifest."""

    frame, _, statistics, evidence_browser = load_inputs()
    configure_matplotlib()
    DATA.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)

    intervals = bootstrap_category_intervals(frame)
    discrimination = discrimination_audit(frame)
    forest = forest_rows(statistics)
    summary = all_system_summary(frame)
    intervals.to_csv(DATA / "category_bootstrap_ci.csv", index=False)
    discrimination.to_csv(DATA / "discrimination_audit.csv", index=False)
    forest.to_csv(DATA / "hypothesis_forest_rows.csv", index=False)
    summary.to_csv(DATA / "system_summary.csv", index=False)

    category_plot, category_static = category_leader_figures(frame, intervals)
    item_plot, item_static = item_response_figures(frame)
    forest_plot, forest_static = hypothesis_forest_figures(forest)
    rank_plot, rank_static = rank_failure_figures(frame)
    complement_plot, complement_static, complement_data = complementarity_figures(frame)
    oracle_plot, oracle_static, oracle_data = oracle_figures(frame)
    complement_data.to_csv(DATA / "complementarity_unique_hits.csv", index=False)
    oracle_data.to_csv(DATA / "oracle_summary.csv", index=False)

    static_figures = [
        (category_static, "category_leader_matrix"),
        (item_static, "item_response_matrix"),
        (forest_static, "hypothesis_forest"),
        (rank_static, "rank_failure_drilldown"),
        (complement_static, "exploratory_complementarity"),
        (oracle_static, "exploratory_oracle_ceiling"),
    ]
    for figure, stem in static_figures:
        save_static(figure, FIGURES, stem)

    h5_available = H5.is_file()
    h5_panel = (
        '<div class="blocked"><strong>H5 evidence unavailable at required base commit.</strong> '
        'Required Phase 7 <code>h5_results.json</code> is absent, so correlations, generation-quality '
        'bars, abstention values, and answer browser are omitted. No later-branch value was copied.</div>'
    )
    if h5_available:
        raise RuntimeError("H5 source now exists; implement verified H5 reader before displaying it")

    css = CSS.read_text(encoding="utf-8")
    plot_blocks = [
        _plot_html(category_plot, include_library=True, div_id="category-leader"),
        _plot_html(item_plot, include_library=False, div_id="item-response"),
        _plot_html(forest_plot, include_library=False, div_id="hypothesis-forest"),
        _plot_html(rank_plot, include_library=False, div_id="rank-failure"),
        _plot_html(complement_plot, include_library=False, div_id="complementarity"),
        _plot_html(oracle_plot, include_library=False, div_id="oracle-ceiling"),
    ]
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RAG Retrieval Evaluation — V2 Pilot</title>
<style>{css}</style>
</head>
<body>
<header class="hero"><div class="shell">
  <div class="eyebrow">Dissertation evidence dashboard</div>
  <h1>RAG Retrieval Evaluation — V2 Pilot</h1>
  <p class="lede">Five real retrieval systems on one frozen pilot: 22 documents, 140 chunks, 34 owner-approved questions, and owner-adjudicated pooled qrels. Prompt-RAG is an LLM reranker over frozen BM25 top-50 candidates, not an answer generator.</p>
  <p class="caveat">{PILOT_NOTE}. Two documents contribute 65/140 chunks; results are descriptive pilot evidence, not broad external validity.</p>
  <nav class="jump-links" aria-label="Dashboard sections">
    <a href="#overview">Overview</a><a href="#categories">Categories</a><a href="#items">Benchmark audit</a>
    <a href="#hypotheses">Hypotheses</a><a href="#h5">H5</a><a href="#failures">Failures</a><a href="#future">Future work</a>
  </nav>
</div></header>
<main class="shell">
<section id="overview" class="section">
  <span class="badge">C1 · argument</span><h2>BM25 is a strong lexical baseline; no universal winner follows</h2>
  <p class="claim">Aggregate metrics establish system-level performance. Category and hypothesis panels below show where apparent differences hold—and where small-N uncertainty prevents stronger claims.</p>
  {_summary_table(summary)}
</section>
<section id="categories" class="section">
  <span class="badge">C2 · H1–H3</span><h2>Leadership changes by category and metric</h2>
  <p class="claim">Cell means and deterministic 10,000-sample bootstrap intervals expose category-specific strengths. Each category has only 4–6 questions, so intervals remain wide.</p>
  <div class="plot">{plot_blocks[0]}</div>
</section>
<section id="items" class="section">
  <span class="badge">C3 · benchmark audit</span><h2>Difficulty and discrimination expose fragile items</h2>
  <p class="claim">Hit@5 patterns show shared failures and system disagreement. Point-biserial values are descriptive across only five systems; 2PL/3PL IRT was not fitted.</p>
  <div class="plot">{plot_blocks[1]}</div>
  <h3>Flagged negative, near-zero, or undefined discrimination</h3>
  {_discrimination_table(discrimination)}
</section>
<section id="hypotheses" class="section">
  <span class="badge">C4 · H1–H4</span><h2>Most preregistered advantages are not supported</h2>
  <p class="claim">Effects and 95% intervals come directly from authoritative seed-42 preregistered results. H1 is an equivalence decision; H2–H4 use Holm-corrected directional families.</p>
  <div class="plot">{plot_blocks[2]}</div>
  {_hypothesis_table(statistics)}
</section>
<section id="h5" class="section">
  <span class="badge">C5 · H5 headline</span><h2>Retrieval quality versus generation quality</h2>
  {h5_panel}
</section>
<section id="failures" class="section">
  <span class="badge">C6 · depth</span><h2>Failure position distinguishes reranking from retrieval loss</h2>
  <p class="claim">Ranks 6–10 are near misses; ranks 11–50 are ranking failures; sentinel 999 means no pooled relevant chunk appeared in top-50.</p>
  <div class="plot">{plot_blocks[3]}</div>
  <h3>Per-query rank browser</h3>
  {_query_browser(frame, evidence_browser)}
  <div class="blocked"><strong>Generated-answer browser omitted.</strong> Frozen reference answers and pooled positive passages appear above, but required Phase 7 generation source is absent from base commit.</div>
</section>
<section id="future" class="section">
  <span class="badge future">C7 · exploratory future work</span><h2>Complementarity may motivate future routing research</h2>
  <p class="claim">Jaccard overlap and unique hits describe potential complementarity only. No router was built or claimed in this dissertation.</p>
  <div class="plot">{plot_blocks[4]}</div>
  <span class="badge future">C8 · hypothetical upper bound</span><h2>Per-query oracle is not an implemented system</h2>
  <p class="claim">Oracle selects each query's best observed MRR@10 after results are known. It is a ceiling, not submission evidence or a deployment claim.</p>
  <div class="plot">{plot_blocks[5]}</div>
</section>
<section class="section methods">
  <span class="badge">Methods</span><h2>Evidence and validity boundary</h2>
  <p>Every chart uses <code>dashboards/data/per_query_pilot.csv</code>, built from frozen seed-42 Phase 6 sources and reconciled to <code>system_comparison_table.json</code>. Primary basis is <code>final_pooled</code>. Blacklisted seed-123 statistics, invalid AI-generated qrels, and held-out v3_clean engineering results were not read.</p>
  <p>Static 300-dpi PNG/PDF figures and full provenance tables sit beside this file under <code>dashboards/</code>. Rebuild commands appear in <code>dashboards/README.md</code>.</p>
</section>
</main>
<footer class="shell">Base commit 6049994 · seed 42 · frozen V2 pilot · offline self-contained dashboard</footer>
</body>
</html>
"""
    document = "\n".join(line.rstrip() for line in document.splitlines()) + "\n"
    OUTPUT.write_text(document, encoding="utf-8")
    artifacts = [
        OUTPUT,
        FRAME,
        DATA / "per_query_pilot.parquet",
        EVIDENCE_BROWSER,
        GATE1,
        DATA / "category_bootstrap_ci.csv",
        DATA / "discrimination_audit.csv",
        DATA / "hypothesis_forest_rows.csv",
        DATA / "system_summary.csv",
        DATA / "complementarity_unique_hits.csv",
        DATA / "oracle_summary.csv",
        DASHBOARD / "build_dataframe.py",
        DASHBOARD / "charts.py",
        DASHBOARD / "build_dashboard.py",
        DASHBOARD / "requirements.txt",
        CSS,
        *sorted((DASHBOARD / "tests").glob("test_*.py")),
        *sorted(FIGURES.glob("*.png")),
        *sorted(FIGURES.glob("*.pdf")),
    ]
    _write_manifest(artifacts, h5_available=h5_available)
    print(json.dumps({"artifacts": len(artifacts), "h5_blocked": not h5_available, "output": str(OUTPUT.relative_to(ROOT))}, sort_keys=True))


if __name__ == "__main__":
    build()
