"""
run_faiss.py — FAISS Dense Retrieval Experiment
=================================================
Usage:
    cd dissertation/
    python experiments/run_faiss.py [--top-k 10] [--rebuild]

Outputs (in runs/):
    retrieval/faiss_run.jsonl    — per-query ranked results (run file)
    metrics/faiss_metrics.csv    — MRR, Recall@k, nDCG@k, latency
    reports/faiss_*_summary.md   — human-readable report
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add parent to path for src imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.logging_utils import setup_logging, get_logger
from src.utils.io_utils import load_jsonl, load_yaml
from src.retrievers.faiss_retriever import FAISSRetriever
from src.retrievers.base_retriever import RetrievalRun
from src.evaluation.evaluator import RetrievalEvaluator
from src.evaluation.report_generator import ReportGenerator

logger = get_logger("run_faiss")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run FAISS dense retrieval experiment")
    p.add_argument("--top-k", type=int, default=10, help="Retrieval budget per query")
    p.add_argument("--rebuild", action="store_true", help="Force rebuilding the FAISS index")
    p.add_argument("--chunks", default="data/chunks/chunks.jsonl", help="Chunk JSONL path")
    p.add_argument("--qa-dataset", default="data/queries/qa_dataset.jsonl", help="QA dataset path")
    p.add_argument("--qrels", default="data/qrels/qrels.tsv", help="Qrels TSV path")
    p.add_argument("--query-categories", default="data/queries/query_categories.json")
    p.add_argument("--config", default="configs/retrieval.yaml", help="Retrieval config path")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)

    # Load config
    cfg = load_yaml(args.config).get("faiss", {})
    top_k = args.top_k

    logger.info("=== FAISS Experiment | top_k=%d ===", top_k)

    # Load chunks
    chunks_path = Path(args.chunks)
    if not chunks_path.exists():
        logger.error("Chunks not found: %s. Run the ingestion pipeline first.", chunks_path)
        sys.exit(1)
    chunks = load_jsonl(chunks_path)
    logger.info("Loaded %d chunks", len(chunks))

    # Load QA dataset
    qa_path = Path(args.qa_dataset)
    if not qa_path.exists():
        logger.error("QA dataset not found: %s. Run the benchmark pipeline first.", qa_path)
        sys.exit(1)
    qa_items = load_jsonl(qa_path)
    logger.info("Loaded %d QA items", len(qa_items))

    # Build / load FAISS index
    index_path = Path(cfg.get("index_path", "indexes/faiss/faiss.index"))
    retriever = FAISSRetriever(
        index_dir=index_path.parent,
        chunks_path=chunks_path,
        model_name=cfg.get("model_name", "sentence-transformers/all-MiniLM-L6-v2"),
    )

    if args.rebuild or not index_path.exists():
        logger.info("Building FAISS index…")
        retriever.build_index(chunks)
    else:
        logger.info("Loading existing FAISS index…")
        retriever.load_index()

    # Run benchmark
    config_snapshot = {"retriever": "faiss", "top_k": top_k, **cfg}
    runs = retriever.run_benchmark(qa_items, top_k=top_k, config_snapshot=config_snapshot)

    # Save run file
    run_file = Path("runs/retrieval/faiss_run.jsonl")
    RetrievalRun.save_run_file(runs, run_file)
    logger.info("Run file saved → %s", run_file)

    # Evaluate
    qrels_path = Path(args.qrels)
    if not qrels_path.exists():
        logger.warning("Qrels not found at %s; skipping evaluation.", qrels_path)
        return

    evaluator = RetrievalEvaluator(
        qrels_path=qrels_path,
        query_categories_path=args.query_categories if Path(args.query_categories).exists() else None,
    )
    bundles = evaluator.evaluate_run_file(run_file, retriever_name="faiss")
    evaluator.save_metrics_csv(bundles, "runs/metrics/faiss_metrics.csv")

    reporter = ReportGenerator("runs/reports")
    reporter.generate(bundles, run_name=f"faiss_top{top_k}", config=config_snapshot)

    # Print aggregate summary
    agg = next((b for b in bundles if b.query_category == "all"), None)
    if agg:
        logger.info(
            "FAISS results — MRR=%.4f | R@10=%.4f | nDCG@10=%.4f | latency=%.1f ms",
            agg.mrr,
            agg.recall_at_k.get(10, 0),
            agg.ndcg_at_k.get(10, 0),
            agg.avg_latency_ms,
        )


if __name__ == "__main__":
    main()
