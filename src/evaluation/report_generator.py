"""
Report Generator — Evaluation Layer
======================================
Research purpose
    Converts raw MetricBundles into human-readable Markdown tables and a
    machine-readable JSON summary — the primary deliverables that go into
    the dissertation's results section.

Design choice
    Markdown output because it renders directly in GitHub, Jupyter, and
    most dissertation template environments. JSON output for programmatic
    downstream use (plotting, further analysis).

Alternative approaches
    LaTeX tables would be more dissertation-final; they are deferred to
    the final semester when the full results set is available.

Expected strengths
    Generates per-retriever and cross-retriever comparison tables in one
    call; includes latency alongside accuracy metrics so operational trade-
    offs are visible without a separate step.

Expected weaknesses
    Significance results are emitted by the separate query-level statistical
    evaluator rather than embedded in every baseline report.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .metrics import MetricBundle

logger = logging.getLogger(__name__)

DISPLAY_NAMES = {
    "graphrag": "Entity-Co-occurrence Graph Retrieval",
    "structured_graph": "Structured Metadata Graph Retrieval",
}


class ReportGenerator:
    """Generates Markdown and JSON experiment reports from MetricBundles."""

    def __init__(self, reports_dir: str | Path = "runs/reports") -> None:
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        bundles: list[MetricBundle],
        run_name: str,
        config: dict | None = None,
    ) -> Path:
        """
        Write experiment_summary.md and metrics.json for *run_name*.

        Parameters
        ----------
        bundles : list[MetricBundle]
            Output of RetrievalEvaluator.evaluate_run_file.
        run_name : str
            Identifier used in file names (e.g. "faiss_v1_topk10").
        config : dict | None
            Experiment configuration written into the report header.

        Returns
        -------
        Path
            Path to the generated Markdown report.
        """
        md_path = self.reports_dir / f"{run_name}_summary.md"
        json_path = self.reports_dir / f"{run_name}_metrics.json"

        # --- JSON output ---
        output = {
            "run_name": run_name,
            "config": config or {},
            "metrics": [b.to_dict() for b in bundles],
        }
        json_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        logger.info("JSON metrics → %s", json_path)

        # --- Markdown output ---
        lines: list[str] = []
        lines += [
            f"# Experiment Report: `{run_name}`",
            "",
        ]

        if config:
            lines += ["## Configuration", "```json", json.dumps(config, indent=2), "```", ""]

        # Aggregate table
        aggregate = [b for b in bundles if b.query_category == "all"]
        if aggregate:
            lines += self._build_comparison_table(aggregate, title="## Aggregate Metrics")

        # Per-category table
        categorical = [b for b in bundles if b.query_category != "all"]
        if categorical:
            categories = sorted({b.query_category for b in categorical})
            for cat in categories:
                cat_bundles = [b for b in categorical if b.query_category == cat]
                lines += self._build_comparison_table(
                    cat_bundles, title=f"### Category: `{cat}`"
                )

        # Latency table
        lines += self._build_latency_table(bundles)

        md_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Markdown report → %s", md_path)
        return md_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_comparison_table(bundles: list[MetricBundle], title: str = "") -> list[str]:
        if not bundles:
            return []

        k_values = sorted(bundles[0].recall_at_k.keys())

        headers = ["Retriever", "N", "MRR"] + [f"MRR@{k}" for k in k_values] + [f"R@{k}" for k in k_values] + [f"nDCG@{k}" for k in k_values]
        rows = []
        for b in sorted(bundles, key=lambda x: x.retriever):
            row = [
                DISPLAY_NAMES.get(b.retriever, b.retriever),
                str(b.num_queries),
                f"{b.mrr:.4f}",
            ]
            row += [f"{b.mrr_at_k.get(k, 0):.4f}" for k in k_values]
            row += [f"{b.recall_at_k.get(k, 0):.4f}" for k in k_values]
            row += [f"{b.ndcg_at_k.get(k, 0):.4f}" for k in k_values]
            rows.append(row)

        lines = [title, ""] if title else []
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
        return lines

    @staticmethod
    def _build_latency_table(bundles: list[MetricBundle]) -> list[str]:
        aggregate = [b for b in bundles if b.query_category == "all"]
        if not aggregate:
            return []

        lines = ["## Latency (ms, avg per query)", ""]
        lines.append("| Retriever | Avg Latency (ms) |")
        lines.append("| --- | --- |")
        for b in sorted(aggregate, key=lambda x: x.avg_latency_ms):
            lines.append(f"| {DISPLAY_NAMES.get(b.retriever, b.retriever)} | {b.avg_latency_ms:.2f} |")
        lines.append("")
        return lines
