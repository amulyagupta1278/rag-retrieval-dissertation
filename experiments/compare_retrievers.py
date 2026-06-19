"""
compare_retrievers.py — Cross-Retriever Comparison
====================================================
Loads all available run files, evaluates them against the same qrels,
and produces:
    runs/metrics/metrics.csv              — unified comparison table
    runs/reports/experiment_summary.md    — cross-retriever Markdown report
    runs/reports/retrieval_results.json   — machine-readable summary

Usage:
    cd dissertation/
    python experiments/compare_retrievers.py [--run-dir runs/retrieval] [--qrels data/qrels/qrels.tsv]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.logging_utils import setup_logging, get_logger
from src.evaluation.evaluator import RetrievalEvaluator
from src.evaluation.report_generator import ReportGenerator
from src.evaluation.metrics import MetricBundle

logger = get_logger("compare_retrievers")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare all retriever run files")
    p.add_argument("--run-dir", default="runs/retrieval")
    p.add_argument("--qrels", default="data/qrels/qrels.tsv")
    p.add_argument("--query-categories", default="data/queries/query_categories.json")
    p.add_argument("--output-dir", default="runs/metrics")
    p.add_argument("--reports-dir", default="runs/reports")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def _print_ascii_table(bundles: list[MetricBundle]) -> None:
    aggregate = [b for b in bundles if b.query_category == "all"]
    if not aggregate:
        return

    header = f"{'Retriever':<12} {'MRR':>7} {'R@5':>7} {'R@10':>7} {'nDCG@10':>9} {'Lat(ms)':>9}"
    sep = "-" * len(header)
    print("\n" + sep)
    print(header)
    print(sep)
    for b in sorted(aggregate, key=lambda x: x.mrr, reverse=True):
        print(
            f"{b.retriever:<12} "
            f"{b.mrr:>7.4f} "
            f"{b.recall_at_k.get(5, 0):>7.4f} "
            f"{b.recall_at_k.get(10, 0):>7.4f} "
            f"{b.ndcg_at_k.get(10, 0):>9.4f} "
            f"{b.avg_latency_ms:>9.2f}"
        )
    print(sep + "\n")


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)

    run_dir = Path(args.run_dir)
    qrels_path = Path(args.qrels)

    if not qrels_path.exists():
        logger.error("Qrels not found: %s. Build the benchmark first.", qrels_path)
        sys.exit(1)

    run_files = sorted(run_dir.glob("*.jsonl"))
    if not run_files:
        logger.error("No run files found in %s. Run individual experiments first.", run_dir)
        sys.exit(1)

    logger.info("Found %d run files: %s", len(run_files), [f.name for f in run_files])

    cat_path = Path(args.query_categories)
    evaluator = RetrievalEvaluator(
        qrels_path=qrels_path,
        query_categories_path=cat_path if cat_path.exists() else None,
    )

    all_bundles: list[MetricBundle] = []
    for run_file in run_files:
        logger.info("Evaluating %s…", run_file.name)
        bundles = evaluator.evaluate_run_file(run_file)
        all_bundles.extend(bundles)

    # Save unified CSV
    output_dir = Path(args.output_dir)
    evaluator.save_metrics_csv(all_bundles, output_dir / "metrics.csv")

    # Print ASCII summary to stdout
    _print_ascii_table(all_bundles)

    # Generate Markdown report
    reporter = ReportGenerator(args.reports_dir)
    md_path = reporter.generate(
        all_bundles,
        run_name="comparison_all_retrievers",
        config={"run_files": [str(f) for f in run_files]},
    )
    logger.info("Comparison report → %s", md_path)

    # Save retrieval_results.json
    results_json_path = Path(args.reports_dir) / "retrieval_results.json"
    results_json_path.parent.mkdir(parents=True, exist_ok=True)
    results_json_path.write_text(
        json.dumps(
            {
                "run_files": [str(f) for f in run_files],
                "metrics": [b.to_dict() for b in all_bundles],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("retrieval_results.json → %s", results_json_path)

    # --- Per-category breakdown ---
    categories = sorted({b.query_category for b in all_bundles if b.query_category != "all"})
    if categories:
        logger.info("Category breakdown available for: %s", categories)
        for cat in categories:
            cat_bundles = [b for b in all_bundles if b.query_category == cat]
            logger.info("  [%s]", cat)
            for b in sorted(cat_bundles, key=lambda x: x.mrr, reverse=True):
                logger.info(
                    "    %s → MRR=%.4f R@10=%.4f nDCG@10=%.4f",
                    b.retriever,
                    b.mrr,
                    b.recall_at_k.get(10, 0),
                    b.ndcg_at_k.get(10, 0),
                )


if __name__ == "__main__":
    main()
