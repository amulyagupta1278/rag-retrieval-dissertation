"""
run_bm25.py — BM25 Sparse Retrieval Experiment
=================================================
Usage:
    cd dissertation/
    python experiments/run_bm25.py [--top-k 10] [--rebuild] [--k1 1.5] [--b 0.75]

Outputs (in runs/):
    retrieval/bm25_run.jsonl    — per-query ranked results
    metrics/bm25_metrics.csv    — MRR, Recall@k, nDCG@k, latency
    reports/bm25_*_summary.md   — human-readable report
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.logging_utils import setup_logging, get_logger
from src.utils.io_utils import load_jsonl, load_yaml
from src.retrievers.bm25_retriever import BM25Retriever
from src.retrievers.base_retriever import RetrievalRun
from src.evaluation.evaluator import RetrievalEvaluator
from src.evaluation.report_generator import ReportGenerator

logger = get_logger("run_bm25")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run BM25 sparse retrieval experiment")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--rebuild", action="store_true")
    p.add_argument("--k1", type=float, default=None, help="BM25 k1 parameter")
    p.add_argument("--b", type=float, default=None, help="BM25 b parameter")
    p.add_argument("--chunks", default="data/chunks/chunks.jsonl")
    p.add_argument("--qa-dataset", default="data/queries/qa_dataset.jsonl")
    p.add_argument("--qrels", default="data/qrels/qrels.tsv")
    p.add_argument("--query-categories", default="data/queries/query_categories.json")
    p.add_argument("--config", default="configs/retrieval.yaml")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)

    cfg = load_yaml(args.config).get("bm25", {})
    top_k = args.top_k
    k1 = args.k1 if args.k1 is not None else cfg.get("k1", 1.5)
    b = args.b if args.b is not None else cfg.get("b", 0.75)

    logger.info("=== BM25 Experiment | top_k=%d | k1=%.2f | b=%.2f ===", top_k, k1, b)

    chunks_path = Path(args.chunks)
    if not chunks_path.exists():
        logger.error("Chunks not found: %s", chunks_path)
        sys.exit(1)
    chunks = load_jsonl(chunks_path)
    logger.info("Loaded %d chunks", len(chunks))

    qa_path = Path(args.qa_dataset)
    if not qa_path.exists():
        logger.error("QA dataset not found: %s", qa_path)
        sys.exit(1)
    qa_items = load_jsonl(qa_path)
    logger.info("Loaded %d QA items", len(qa_items))

    retriever = BM25Retriever(
        k1=k1,
        b=b,
        index_path=cfg.get("index_path", "indexes/bm25/bm25_index.pkl"),
    )

    index_path = Path(cfg.get("index_path", "indexes/bm25/bm25_index.pkl"))
    if args.rebuild or not index_path.exists():
        logger.info("Building BM25 index…")
        retriever.build_index(chunks)
    else:
        logger.info("Loading existing BM25 index…")
        retriever.load_index()

    config_snapshot = {"retriever": "bm25", "top_k": top_k, "k1": k1, "b": b}
    runs = retriever.run_benchmark(qa_items, top_k=top_k, config_snapshot=config_snapshot)

    run_file = Path("runs/retrieval/bm25_run.jsonl")
    RetrievalRun.save_run_file(runs, run_file)
    logger.info("Run file saved → %s", run_file)

    qrels_path = Path(args.qrels)
    if not qrels_path.exists():
        logger.warning("Qrels not found at %s; skipping evaluation.", qrels_path)
        return

    evaluator = RetrievalEvaluator(
        qrels_path=qrels_path,
        query_categories_path=args.query_categories if Path(args.query_categories).exists() else None,
    )
    bundles = evaluator.evaluate_run_file(run_file, retriever_name="bm25")
    evaluator.save_metrics_csv(bundles, "runs/metrics/bm25_metrics.csv")

    reporter = ReportGenerator("runs/reports")
    reporter.generate(bundles, run_name=f"bm25_top{top_k}_k1{k1}_b{b}", config=config_snapshot)

    agg = next((b for b in bundles if b.query_category == "all"), None)
    if agg:
        logger.info(
            "BM25 results — MRR=%.4f | R@10=%.4f | nDCG@10=%.4f | latency=%.1f ms",
            agg.mrr,
            agg.recall_at_k.get(10, 0),
            agg.ndcg_at_k.get(10, 0),
            agg.avg_latency_ms,
        )


if __name__ == "__main__":
    main()
