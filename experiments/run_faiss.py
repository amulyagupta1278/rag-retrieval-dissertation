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
    p.add_argument("--build-only", action="store_true", help="Build/load index and exit without QA evaluation")
    p.add_argument("--chunks", default="data/chunks/chunks.jsonl", help="Chunk JSONL path")
    p.add_argument("--qa-dataset", default="data/queries/qa_dataset.jsonl", help="QA dataset path")
    p.add_argument("--qrels", default="data/qrels/qrels.tsv", help="Qrels TSV path")
    p.add_argument("--query-categories", default="data/queries/query_categories.json")
    p.add_argument("--config", default="configs/retrieval.yaml", help="Retrieval config path")
    p.add_argument("--index-dir", default=None)
    p.add_argument("--model-name", default=None)
    p.add_argument("--model-revision", default=None)
    p.add_argument("--similarity-metric", choices=("l2", "cosine"), default=None)
    p.add_argument("--normalize-embeddings", action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--query-prefix", default=None)
    p.add_argument("--passage-prefix", default=None)
    p.add_argument("--output-root", default="runs")
    p.add_argument("--split", choices=("all", "dev", "test", "holdout"), default="all")
    p.add_argument("--configuration-lock", default=None)
    p.add_argument("--require-index-provenance", action="store_true")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)
    if args.split == "holdout":
        if not args.configuration_lock:
            raise RuntimeError("Holdout evaluation requires --configuration-lock")
        from src.evaluation.holdout_lock import verify_lock
        verify_lock(args.configuration_lock, Path(__file__).resolve().parents[1])

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

    # Build / load FAISS index
    index_dir = Path(args.index_dir) if args.index_dir else Path(cfg.get("index_path", "indexes/faiss/faiss.index")).parent
    index_path = index_dir / "faiss.index"
    normalize = args.normalize_embeddings if args.normalize_embeddings is not None else cfg.get("normalize_embeddings", False)
    retriever = FAISSRetriever(
        index_dir=index_dir,
        chunks_path=chunks_path,
        model_name=args.model_name or cfg.get("model_name", "sentence-transformers/all-MiniLM-L6-v2"),
        model_revision=args.model_revision or cfg.get("model_revision"),
        similarity_metric=args.similarity_metric or cfg.get("similarity_metric", "l2"),
        normalize_embeddings=normalize,
        query_prefix=args.query_prefix if args.query_prefix is not None else cfg.get("query_prefix", ""),
        passage_prefix=args.passage_prefix if args.passage_prefix is not None else cfg.get("passage_prefix", ""),
    )

    if args.rebuild or not index_path.exists():
        logger.info("Building FAISS index…")
        retriever.build_index(chunks)
    else:
        logger.info("Loading existing FAISS index…")
        retriever.load_index()
    retriever.validate_provenance(chunks, require_complete=args.require_index_provenance or args.split == "holdout")

    if args.build_only:
        if retriever.index.ntotal != len(chunks) or len(retriever.chunk_ids) != len(chunks):
            raise RuntimeError(
                f"FAISS cardinality mismatch: index={retriever.index.ntotal} "
                f"ids={len(retriever.chunk_ids)} chunks={len(chunks)}"
            )
        logger.info("Build-only gate passed: %d chunks", len(chunks))
        return

    qa_path = Path(args.qa_dataset)
    if not qa_path.exists():
        logger.error("QA dataset not found: %s. Run the benchmark pipeline first.", qa_path)
        sys.exit(1)
    qa_items = load_jsonl(qa_path)
    if args.split != "all":
        qa_items = [item for item in qa_items if item.get("split") == args.split]
        if not qa_items:
            raise RuntimeError(f"No QA items found for split={args.split}")
    logger.info("Loaded %d QA items", len(qa_items))

    # Run benchmark
    config_snapshot = {
        "retriever": "faiss", "top_k": top_k, "model_name": retriever.model_name,
        "model_revision": retriever.model_revision, "similarity_metric": retriever.similarity_metric,
        "normalize_embeddings": retriever.normalize_embeddings, "query_prefix": retriever.query_prefix,
        "passage_prefix": retriever.passage_prefix,
        "split": args.split,
    }
    runs = retriever.run_benchmark(qa_items, top_k=top_k, config_snapshot=config_snapshot)

    # Save run file
    output_root = Path(args.output_root)
    run_file = output_root / "retrieval" / "faiss_run.jsonl"
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
        qa_dataset_path=qa_path, split=args.split,
        chunks_path=chunks_path,
    )
    bundles = evaluator.evaluate_run_file(run_file, retriever_name="faiss")
    evaluator.save_metrics_csv(bundles, output_root / "metrics" / "faiss_metrics.csv")

    reporter = ReportGenerator(output_root / "reports")
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
