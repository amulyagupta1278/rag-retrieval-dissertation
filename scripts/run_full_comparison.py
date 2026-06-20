#!/usr/bin/env python3
"""
Full Comparison Script — Evaluate and Compare All Three Retrievers
====================================================================

Loads FAISS, BM25, and GraphRAG run files, computes evaluation metrics
(MRR, Recall@k, nDCG@k, Precision@k) at k=1,3,5,10, and generates:
  1. comparison_summary.csv — All retrievers, all metrics, aggregate + per-category
  2. per_category.csv — Breakdown by query category
  3. comparison_report.md — Markdown report with findings, failure analysis, sample results
"""

import csv
import json
import logging
import sys
from pathlib import Path
from sys import stdout

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.evaluation.evaluator import RetrievalEvaluator
from src.evaluation.metrics import MetricBundle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    stream=stdout,
)
logger = logging.getLogger(__name__)


def load_run_file(path: Path) -> list[dict]:
    """Load JSONL run file."""
    runs = []
    if not path.exists():
        logger.warning("Run file not found: %s", path)
        return runs
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                runs.append(json.loads(line))
    return runs


def load_qa_dataset(path: Path) -> dict:
    """Load QA dataset to map query_id → question."""
    qa_map = {}
    if not path.exists():
        logger.warning("QA dataset not found: %s", path)
        return qa_map
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                obj = json.loads(line)
                qa_map[obj["question_id"]] = obj["question"]
    return qa_map


def generate_markdown_report(
    all_bundles: list[MetricBundle],
    run_data: dict[str, list[dict]],
    qa_map: dict,
    output_path: Path,
) -> None:
    """Generate comprehensive Markdown report with findings and sample results."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as fh:
        fh.write("# Retrieval Comparison Report\n\n")

        # Aggregate metrics table
        fh.write("## Aggregate Performance (All Queries)\n\n")
        fh.write("| Retriever | Queries | MRR | Recall@5 | Recall@10 | nDCG@5 | nDCG@10 | Latency (ms) |\n")
        fh.write("|-----------|---------|-----|----------|-----------|--------|---------|-------------|\n")

        aggregate_bundles = [b for b in all_bundles if b.query_category == "all"]
        for bundle in sorted(aggregate_bundles, key=lambda b: b.retriever):
            recall_5 = bundle.recall_at_k.get(5, 0.0)
            recall_10 = bundle.recall_at_k.get(10, 0.0)
            ndcg_5 = bundle.ndcg_at_k.get(5, 0.0)
            ndcg_10 = bundle.ndcg_at_k.get(10, 0.0)
            fh.write(
                f"| {bundle.retriever} | {bundle.num_queries} | {bundle.mrr:.4f} | "
                f"{recall_5:.4f} | {recall_10:.4f} | {ndcg_5:.4f} | {ndcg_10:.4f} | "
                f"{bundle.avg_latency_ms:.2f} |\n"
            )

        # Per-category metrics
        fh.write("\n## Per-Category Breakdown\n\n")
        category_bundles = [b for b in all_bundles if b.query_category != "all"]
        if category_bundles:
            categories = sorted(set(b.query_category for b in category_bundles))
            for cat in categories:
                fh.write(f"\n### {cat.replace('_', ' ').title()}\n\n")
                fh.write("| Retriever | MRR | Recall@5 | Recall@10 | nDCG@5 | nDCG@10 |\n")
                fh.write("|-----------|-----|----------|-----------|--------|--------|\n")
                cat_bundles = [b for b in category_bundles if b.query_category == cat]
                for bundle in sorted(cat_bundles, key=lambda b: b.retriever):
                    recall_5 = bundle.recall_at_k.get(5, 0.0)
                    recall_10 = bundle.recall_at_k.get(10, 0.0)
                    ndcg_5 = bundle.ndcg_at_k.get(5, 0.0)
                    ndcg_10 = bundle.ndcg_at_k.get(10, 0.0)
                    fh.write(
                        f"| {bundle.retriever} | {bundle.mrr:.4f} | {recall_5:.4f} | "
                        f"{recall_10:.4f} | {ndcg_5:.4f} | {ndcg_10:.4f} |\n"
                    )

        # Key findings
        fh.write("\n## Key Findings\n\n")

        # Rank retrievers by MRR
        mrr_scores = {b.retriever: b.mrr for b in aggregate_bundles}
        sorted_retrievers = sorted(mrr_scores.items(), key=lambda x: x[1], reverse=True)

        fh.write("### Mean Reciprocal Rank (MRR)\n")
        fh.write("- Measures effectiveness for exact-match queries\n")
        for i, (retriever, mrr) in enumerate(sorted_retrievers, 1):
            fh.write(f"  {i}. **{retriever.upper()}**: MRR = {mrr:.4f}\n")

        # Recall comparison
        fh.write("\n### Recall@10 (Coverage)\n")
        fh.write("- Measures how many relevant chunks are retrieved\n")
        recall_scores = {b.retriever: b.recall_at_k.get(10, 0.0) for b in aggregate_bundles}
        sorted_recall = sorted(recall_scores.items(), key=lambda x: x[1], reverse=True)
        for i, (retriever, recall) in enumerate(sorted_recall, 1):
            fh.write(f"  {i}. **{retriever.upper()}**: Recall@10 = {recall:.4f}\n")

        # Latency comparison
        fh.write("\n### Query Latency\n")
        fh.write("- Time to retrieve results (milliseconds)\n")
        latency_scores = {b.retriever: b.avg_latency_ms for b in aggregate_bundles}
        sorted_latency = sorted(latency_scores.items(), key=lambda x: x[1])
        for i, (retriever, latency) in enumerate(sorted_latency, 1):
            fh.write(f"  {i}. **{retriever.upper()}**: {latency:.2f} ms\n")

        # Failure analysis
        fh.write("\n## Failure Analysis\n\n")
        fh.write("### Expected Behavior by Query Category\n\n")

        failure_notes = {
            "exact_match": (
                "**FAISS & BM25** should excel; **GraphRAG** may struggle without entity matches.\n"
                "  - FAISS uses semantic similarity, effective for exact matches.\n"
                "  - BM25 ranks by term frequency; excellent for exact terminology.\n"
                "  - GraphRAG requires entity extraction; fails if no entities present."
            ),
            "terminology_heavy": (
                "**BM25** likely strongest; **FAISS** effective via semantic understanding.\n"
                "  - BM25 tokenizes and ranks by IDF; built for terminology.\n"
                "  - FAISS captures synonyms via embeddings.\n"
                "  - GraphRAG depends on NER performance."
            ),
            "paraphrase": (
                "**FAISS** should outperform; **BM25** and **GraphRAG** more limited.\n"
                "  - FAISS embeddings capture semantic paraphrases.\n"
                "  - BM25 struggles with word reordering (no semantic understanding).\n"
                "  - GraphRAG limited without entity-level paraphrasing."
            ),
            "entity_relation": (
                "**GraphRAG** specialized advantage; **FAISS** and **BM25** baseline.\n"
                "  - GraphRAG explicitly models entity relationships.\n"
                "  - FAISS/BM25 retrieve relevant chunks but lack structured reasoning."
            ),
            "multi_hop": (
                "All three systems face challenges; **GraphRAG** has structural advantage.\n"
                "  - GraphRAG's 2-hop traversal bridges multi-step paths.\n"
                "  - FAISS/BM25 limited to single-query matching without ranking over chains."
            ),
            "synthesis": (
                "All systems limited; requires collecting diverse relevant evidence.\n"
                "  - Depends on recall@10+ and diverse chunk retrieval.\n"
                "  - GraphRAG's entity linking may help coherence but not coverage."
            ),
        }

        for cat, note in failure_notes.items():
            fh.write(f"\n#### {cat.replace('_', ' ').title()}\n{note}\n")

        # Sample retrieval results
        fh.write("\n## Sample Retrieval Results (First 5 Queries)\n\n")

        sample_query_ids = [f"q_{i:04d}" for i in range(1, 6)]
        for query_id in sample_query_ids:
            # Get question text
            qa_key = None
            for retriever_name in run_data:
                runs = run_data[retriever_name]
                for run in runs:
                    if run["query_id"] == query_id:
                        qa_key = run.get("query_text", "Unknown")
                        break
                if qa_key:
                    break

            if not qa_key:
                continue

            fh.write(f"\n### Query: {query_id} — {qa_key}\n\n")

            # Side-by-side results
            fh.write("| Rank | FAISS | BM25 | GraphRAG |\n")
            fh.write("|------|-------|------|----------|\n")

            for retriever_name in ["faiss", "bm25", "graphrag"]:
                if retriever_name not in run_data:
                    continue

            max_results = 3
            for rank in range(1, max_results + 1):
                cells = [str(rank)]
                for retriever_name in ["faiss", "bm25", "graphrag"]:
                    if retriever_name not in run_data:
                        cells.append("—")
                        continue

                    runs = run_data[retriever_name]
                    run = next((r for r in runs if r["query_id"] == query_id), None)
                    if not run:
                        cells.append("—")
                        continue

                    results = run.get("results", [])
                    if rank - 1 < len(results):
                        result = results[rank - 1]
                        chunk_id = result.get("chunk_id", "")
                        score = result.get("score", 0.0)
                        cells.append(f"{chunk_id[:12]}… ({score:.3f})")
                    else:
                        cells.append("—")

                fh.write("| " + " | ".join(cells) + " |\n")

    logger.info("Report written → %s", output_path)


def main() -> None:
    """Load runs, evaluate, and generate comparison outputs."""
    base_path = Path(__file__).parent.parent
    runs_dir = base_path / "runs" / "retrieval"
    qrels_path = base_path / "data" / "qrels" / "qrels.tsv"
    query_categories_path = base_path / "data" / "queries" / "query_categories.json"
    qa_dataset_path = base_path / "data" / "queries" / "qa_dataset_v1.jsonl"
    output_metrics_dir = base_path / "runs" / "metrics"
    output_reports_dir = base_path / "runs" / "reports"

    # Ensure output directories exist
    output_metrics_dir.mkdir(parents=True, exist_ok=True)
    output_reports_dir.mkdir(parents=True, exist_ok=True)

    # Initialize evaluator
    evaluator = RetrievalEvaluator(
        qrels_path=qrels_path,
        query_categories_path=query_categories_path,
        k_values=[1, 3, 5, 10],
    )

    # Evaluate each run file
    all_bundles: list[MetricBundle] = []
    run_data: dict[str, list[dict]] = {}

    retriever_names = ["faiss", "bm25", "graphrag"]
    for ret_name in retriever_names:
        run_file = runs_dir / f"{ret_name}_run.jsonl"
        logger.info("Evaluating %s...", ret_name)
        bundles = evaluator.evaluate_run_file(run_file, retriever_name=ret_name)
        all_bundles.extend(bundles)
        run_data[ret_name] = load_run_file(run_file)

    # Save metrics CSVs
    summary_csv = output_metrics_dir / "comparison_summary.csv"
    evaluator.save_metrics_csv(all_bundles, summary_csv)

    per_category_csv = output_metrics_dir / "per_category.csv"
    category_bundles = [b for b in all_bundles if b.query_category != "all"]
    evaluator.save_metrics_csv(category_bundles, per_category_csv)

    # Load QA dataset for report generation
    qa_map = load_qa_dataset(qa_dataset_path)

    # Generate markdown report
    report_path = output_reports_dir / "comparison_report.md"
    generate_markdown_report(all_bundles, run_data, qa_map, report_path)

    logger.info("\n" + "=" * 70)
    logger.info("COMPARISON COMPLETE")
    logger.info("=" * 70)
    logger.info("Generated files:")
    logger.info("  • %s", summary_csv)
    logger.info("  • %s", per_category_csv)
    logger.info("  • %s", report_path)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
