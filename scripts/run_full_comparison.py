#!/usr/bin/env python3
"""
Full Comparison Script — Compare All Three Retrievers
======================================================
Loads run files, computes metrics (MRR@5, MRR@10, Recall@5, Recall@10, nDCG@5, nDCG@10),
generates per-category breakdown, and produces markdown report with findings.
"""

import csv
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.evaluation.evaluator import RetrievalEvaluator
from src.evaluation.metrics import MetricBundle

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)


def load_run_file(path: Path) -> list[dict]:
    """Load JSONL run file."""
    runs = []
    if not path.exists():
        return runs
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    runs.append(json.loads(line))
    except Exception as e:
        logger.warning(f"Error loading {path}: {e}")
    return runs


def load_qa_dataset(path: Path) -> dict:
    """Load QA dataset: {question_id: {question, category, ...}}"""
    qa_map = {}
    if not path.exists():
        logger.warning(f"QA dataset not found: {path}")
        return qa_map
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    obj = json.loads(line)
                    qa_map[obj["question_id"]] = obj
    except Exception as e:
        logger.warning(f"Error loading QA dataset: {e}")
    return qa_map


def build_query_categories(qa_map: dict) -> dict:
    """Build {query_id: category} from QA dataset."""
    return {qid: qa["category"] for qid, qa in qa_map.items() if "category" in qa}


def compute_metrics_at_k(runs: list[dict], qrels: dict, k_values=[5, 10]) -> dict:
    """
    Compute MRR@k, Recall@k, nDCG@k for given k values.
    Returns {k: {metric: value}}
    """
    from src.evaluation.metrics import (
        compute_mrr,
        compute_recall_at_k,
        compute_ndcg_at_k,
    )

    metrics_by_k = {k: {"mrr": [], "recall": [], "ndcg": []} for k in k_values}
    latencies = []

    for run in runs:
        qid = run["query_id"]
        gold_ids = set(qrels.get(qid, {}).keys())
        ranked_ids = [r["chunk_id"] for r in run.get("results", [])]

        for k in k_values:
            mrr = compute_mrr(ranked_ids[:k], gold_ids)
            recall = compute_recall_at_k(ranked_ids, gold_ids, k)
            ndcg = compute_ndcg_at_k(ranked_ids, gold_ids, k)

            metrics_by_k[k]["mrr"].append(mrr)
            metrics_by_k[k]["recall"].append(recall)
            metrics_by_k[k]["ndcg"].append(ndcg)

        latencies.append(run.get("total_latency_ms", 0.0))

    # Average across queries
    result = {}
    for k in k_values:
        result[k] = {
            "mrr": sum(metrics_by_k[k]["mrr"]) / len(runs) if runs else 0.0,
            "recall": sum(metrics_by_k[k]["recall"]) / len(runs) if runs else 0.0,
            "ndcg": sum(metrics_by_k[k]["ndcg"]) / len(runs) if runs else 0.0,
        }

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    return result, avg_latency


def compute_per_category_metrics(
    runs: list[dict], qrels: dict, query_categories: dict, k=5
) -> dict:
    """Compute MRR@k per category."""
    from src.evaluation.metrics import compute_mrr

    category_metrics = {}

    for run in runs:
        qid = run["query_id"]
        category = query_categories.get(qid, "unknown")

        if category not in category_metrics:
            category_metrics[category] = []

        gold_ids = set(qrels.get(qid, {}).keys())
        ranked_ids = [r["chunk_id"] for r in run.get("results", [])]
        mrr = compute_mrr(ranked_ids, gold_ids)
        category_metrics[category].append(mrr)

    # Average per category
    result = {}
    for cat, mrr_list in category_metrics.items():
        result[cat] = sum(mrr_list) / len(mrr_list) if mrr_list else 0.0

    return result


def save_comparison_summary_csv(
    retriever_metrics: dict, output_path: Path
) -> None:
    """Save comparison_summary.csv with one row per retriever."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = [
        "Retriever",
        "MRR@5",
        "MRR@10",
        "Recall@5",
        "Recall@10",
        "nDCG@5",
        "nDCG@10",
        "Avg Latency (ms)",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()

        for ret_name, metrics in sorted(retriever_metrics.items()):
            row = {
                "Retriever": ret_name.upper(),
                "MRR@5": f"{metrics['metrics_by_k'][5]['mrr']:.4f}",
                "MRR@10": f"{metrics['metrics_by_k'][10]['mrr']:.4f}",
                "Recall@5": f"{metrics['metrics_by_k'][5]['recall']:.4f}",
                "Recall@10": f"{metrics['metrics_by_k'][10]['recall']:.4f}",
                "nDCG@5": f"{metrics['metrics_by_k'][5]['ndcg']:.4f}",
                "nDCG@10": f"{metrics['metrics_by_k'][10]['ndcg']:.4f}",
                "Avg Latency (ms)": f"{metrics['avg_latency']:.2f}"
                if metrics["avg_latency"] > 0
                else "N/A",
            }
            writer.writerow(row)

    logger.info(f"Saved {output_path}")


def save_per_category_csv(
    retriever_categories: dict, output_path: Path
) -> None:
    """Save per_category.csv with MRR@5 per category per retriever."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Collect all categories
    all_categories = set()
    for ret_name, cat_metrics in retriever_categories.items():
        all_categories.update(cat_metrics.keys())

    headers = ["Category"] + [ret.upper() for ret in sorted(retriever_categories.keys())]

    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()

        for category in sorted(all_categories):
            row = {"Category": category}
            for ret_name in sorted(retriever_categories.keys()):
                mrr = retriever_categories[ret_name].get(category, 0.0)
                row[ret_name.upper()] = f"{mrr:.4f}"
            writer.writerow(row)

    logger.info(f"Saved {output_path}")


def generate_markdown_report(
    retriever_metrics: dict,
    retriever_categories: dict,
    output_path: Path,
    qa_dataset_size: int,
) -> None:
    """Generate comprehensive markdown report."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as fh:
        fh.write("# Retrieval Comparison Report\n\n")
        fh.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        fh.write(f"**QA Dataset Size:** {qa_dataset_size} queries\n\n")

        # Overall metrics table
        fh.write("## Overall Metrics\n\n")
        fh.write(
            "| Retriever | MRR@5 | MRR@10 | Recall@5 | Recall@10 | nDCG@5 | nDCG@10 | Latency (ms) |\n"
        )
        fh.write(
            "|-----------|-------|--------|----------|-----------|--------|---------|-------------|\n"
        )

        for ret_name in sorted(retriever_metrics.keys()):
            metrics = retriever_metrics[ret_name]
            m5 = metrics["metrics_by_k"][5]
            m10 = metrics["metrics_by_k"][10]
            lat = (
                f"{metrics['avg_latency']:.2f}"
                if metrics["avg_latency"] > 0
                else "N/A"
            )
            fh.write(
                f"| {ret_name.upper()} | {m5['mrr']:.4f} | {m10['mrr']:.4f} | "
                f"{m5['recall']:.4f} | {m10['recall']:.4f} | {m5['ndcg']:.4f} | "
                f"{m10['ndcg']:.4f} | {lat} |\n"
            )

        # Per-category breakdown
        fh.write("\n## Per-Category Breakdown (MRR@5)\n\n")
        all_categories = set()
        for ret_name in retriever_categories:
            all_categories.update(retriever_categories[ret_name].keys())

        fh.write("| Category | " + " | ".join(sorted(retriever_metrics.keys())) + " |\n")
        fh.write("|----------|" + "|".join(["---"] * len(retriever_metrics)) + "|\n")

        for category in sorted(all_categories):
            row = [category]
            for ret_name in sorted(retriever_metrics.keys()):
                mrr = retriever_categories[ret_name].get(category, 0.0)
                row.append(f"{mrr:.4f}")
            fh.write("| " + " | ".join(row) + " |\n")

        # Key findings
        fh.write("\n## Key Findings\n\n")

        # Best overall
        best_ret = max(
            retriever_metrics.items(),
            key=lambda x: x[1]["metrics_by_k"][5]["mrr"],
        )
        fh.write(
            f"- **Best overall (MRR@5):** {best_ret[0].upper()} "
            f"({best_ret[1]['metrics_by_k'][5]['mrr']:.4f})\n"
        )

        # Worst overall
        worst_ret = min(
            retriever_metrics.items(),
            key=lambda x: x[1]["metrics_by_k"][5]["mrr"],
        )
        fh.write(
            f"- **Lowest overall (MRR@5):** {worst_ret[0].upper()} "
            f"({worst_ret[1]['metrics_by_k'][5]['mrr']:.4f})\n"
        )

        # Best by category
        fh.write("- **Best per category:**\n")
        for category in sorted(all_categories):
            best_cat = max(
                retriever_categories.items(),
                key=lambda x: x[1].get(category, 0.0),
            )
            mrr = best_cat[1].get(category, 0.0)
            fh.write(f"  - {category}: {best_cat[0].upper()} ({mrr:.4f})\n")

        # Failure analysis
        fh.write("\n## Failure Analysis\n\n")
        fh.write("**Lowest MRR@5 category per retriever:**\n")

        for ret_name in sorted(retriever_categories.keys()):
            cat_scores = retriever_categories[ret_name]
            if cat_scores:
                worst_cat = min(cat_scores.items(), key=lambda x: x[1])
                fh.write(
                    f"- {ret_name.upper()}: {worst_cat[0]} ({worst_cat[1]:.4f})\n"
                )

    logger.info(f"Saved {output_path}")


def generate_sample_queries_report(
    retriever_runs: dict, qa_map: dict, output_path: Path
) -> None:
    """Generate sample_queries.md with side-by-side retrieval results."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sample_questions = [
        "What is the annual benefit amount under PM-KISAN?",
        "What are the eligibility criteria for PMJAY?",
        "Which schemes target small and marginal farmers?",
        "What documents are required to apply for PM-KISAN?",
        "How does PMJAY determine which families are eligible?",
    ]

    with output_path.open("w", encoding="utf-8") as fh:
        fh.write("# Sample Query Results (Side-by-Side Comparison)\n\n")

        for sample_q in sample_questions:
            fh.write(f"## Query: {sample_q}\n\n")

            # Find matching question in qa_map
            matching_qid = None
            for qid, qa in qa_map.items():
                if qa.get("question", "").lower() == sample_q.lower():
                    matching_qid = qid
                    break

            if not matching_qid:
                fh.write("*(Question not found in dataset)*\n\n")
                continue

            # Get results from each retriever
            fh.write("| Rank | FAISS | BM25 | GraphRAG |\n")
            fh.write("|------|-------|------|----------|\n")

            max_rank = 3
            for rank in range(1, max_rank + 1):
                row = [str(rank)]

                for ret_name in ["faiss", "bm25", "graphrag"]:
                    if ret_name not in retriever_runs:
                        row.append("—")
                        continue

                    run = next(
                        (r for r in retriever_runs[ret_name] if r["query_id"] == matching_qid),
                        None,
                    )
                    if not run:
                        row.append("—")
                        continue

                    results = run.get("results", [])
                    if rank - 1 < len(results):
                        result = results[rank - 1]
                        chunk_id = result.get("chunk_id", "")
                        text = result.get("text", "")[:100]
                        row.append(f"**{chunk_id}**<br/>{text}...")
                    else:
                        row.append("—")

                fh.write("| " + " | ".join(row) + " |\n")

            fh.write("\n")

    logger.info(f"Saved {output_path}")


def main():
    base_path = Path(__file__).parent.parent
    runs_dir = base_path / "runs" / "retrieval"
    qrels_path = base_path / "data" / "qrels" / "qrels.tsv"
    qa_dataset_path = base_path / "data" / "queries" / "qa_dataset_v1.jsonl"

    output_metrics_dir = base_path / "runs" / "metrics"
    output_reports_dir = base_path / "runs" / "reports"

    output_metrics_dir.mkdir(parents=True, exist_ok=True)
    output_reports_dir.mkdir(parents=True, exist_ok=True)

    # Load qrels
    evaluator = RetrievalEvaluator(qrels_path=qrels_path)
    qrels = evaluator.qrels

    # Load QA dataset
    qa_map = load_qa_dataset(qa_dataset_path)
    query_categories = build_query_categories(qa_map)

    # Load run files
    retriever_names = ["faiss", "bm25", "graphrag"]
    retriever_runs = {}
    retriever_metrics = {}
    retriever_categories = {}

    for ret_name in retriever_names:
        run_file = runs_dir / f"{ret_name}_run.jsonl"
        if not run_file.exists():
            logger.warning(f"Run file not found: {run_file} (skipping {ret_name})")
            continue

        logger.info(f"Loading {ret_name}...")
        runs = load_run_file(run_file)
        if not runs:
            logger.warning(f"No runs loaded from {run_file}")
            continue

        retriever_runs[ret_name] = runs

        # Compute metrics
        metrics_by_k, avg_latency = compute_metrics_at_k(runs, qrels, k_values=[5, 10])
        retriever_metrics[ret_name] = {
            "metrics_by_k": metrics_by_k,
            "avg_latency": avg_latency,
        }

        # Compute per-category metrics
        per_cat = compute_per_category_metrics(runs, qrels, query_categories, k=5)
        retriever_categories[ret_name] = per_cat

    if not retriever_metrics:
        logger.error("No retrievers loaded. Exiting.")
        return

    # Save results
    save_comparison_summary_csv(
        retriever_metrics, output_metrics_dir / "comparison_summary.csv"
    )
    save_per_category_csv(
        retriever_categories, output_metrics_dir / "per_category.csv"
    )
    generate_markdown_report(
        retriever_metrics,
        retriever_categories,
        output_reports_dir / "comparison_report.md",
        len(qa_map),
    )
    generate_sample_queries_report(
        retriever_runs, qa_map, output_reports_dir / "sample_queries.md"
    )

    logger.info("\nComparison complete. Results in runs/metrics/ and runs/reports/")


if __name__ == "__main__":
    main()
