"""
run_graphrag.py — Entity-Co-occurrence Graph Retrieval Experiment
==============================================================
Usage:
    cd dissertation/
    python experiments/run_graphrag.py [--top-k 10] [--rebuild] [--max-hop 2]

Outputs (in runs/):
    retrieval/graphrag_run.jsonl    — per-query ranked results
    metrics/graphrag_metrics.csv    — MRR, Recall@k, nDCG@k, latency
    reports/graphrag_*_summary.md   — human-readable report
    indexes/graphrag/nodes.jsonl    — graph node artifacts
    indexes/graphrag/edges.jsonl    — graph edge artifacts
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.logging_utils import setup_logging, get_logger
from src.utils.io_utils import load_jsonl, load_yaml
from src.retrievers.graphrag_retriever import GraphRAGRetriever
from src.retrievers.base_retriever import RetrievalRun
from src.evaluation.evaluator import RetrievalEvaluator
from src.evaluation.report_generator import ReportGenerator

logger = get_logger("run_graphrag")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Entity-Co-occurrence Graph Retrieval experiment")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--rebuild", action="store_true")
    p.add_argument("--build-only", action="store_true", help="Build/load index and exit without QA evaluation")
    p.add_argument("--max-hop", type=int, default=None)
    p.add_argument("--chunks", default="data/chunks/chunks.jsonl")
    p.add_argument("--qa-dataset", default="data/queries/qa_dataset.jsonl")
    p.add_argument("--qrels", default="data/qrels/qrels.tsv")
    p.add_argument("--query-categories", default="data/queries/query_categories.json")
    p.add_argument("--config", default="configs/retrieval.yaml")
    p.add_argument("--graph-dir", default=None)
    p.add_argument("--output-root", default="runs")
    p.add_argument("--split", choices=("all", "dev", "test", "holdout"), default="all")
    p.add_argument("--configuration-lock", default=None)
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

    cfg = load_yaml(args.config).get("graphrag", {})
    top_k = args.top_k
    max_hop = args.max_hop if args.max_hop is not None else cfg.get("max_hop", 2)

    logger.info("=== Entity-Co-occurrence Graph Experiment | top_k=%d | max_hop=%d ===", top_k, max_hop)

    chunks_path = Path(args.chunks)
    if not chunks_path.exists():
        logger.error("Chunks not found: %s", chunks_path)
        sys.exit(1)
    chunks = load_jsonl(chunks_path)
    logger.info("Loaded %d chunks", len(chunks))

    graph_dir = Path(args.graph_dir) if args.graph_dir else Path(cfg.get("graph_path", "indexes/graphrag/graph.gpickle")).parent
    graph_path = graph_dir / "graph.gpickle"

    retriever = GraphRAGRetriever(
        entity_model=cfg.get("entity_model", "en_core_web_sm"),
        max_hop=max_hop,
        relation_window=cfg.get("relation_window", 2),
        min_entity_freq=cfg.get("min_entity_freq", 2),
        graph_path=graph_path,
        nodes_path=graph_dir / "nodes.jsonl",
        edges_path=graph_dir / "edges.jsonl",
    )

    if args.rebuild or not graph_path.exists():
        logger.info("Building entity-co-occurrence graph index…")
        retriever.build_index(chunks)
    else:
        logger.info("Loading existing entity-co-occurrence graph index…")
        retriever.load_index()

    if args.build_only:
        if len(retriever._chunk_meta) != len(chunks):
            raise RuntimeError(
                f"Entity-graph cardinality mismatch: index={len(retriever._chunk_meta)} chunks={len(chunks)}"
            )
        logger.info("Build-only gate passed: %d chunks", len(chunks))
        return

    qa_path = Path(args.qa_dataset)
    if not qa_path.exists():
        logger.error("QA dataset not found: %s", qa_path)
        sys.exit(1)
    qa_items = load_jsonl(qa_path)
    if args.split != "all":
        qa_items = [item for item in qa_items if item.get("split") == args.split]
        if not qa_items:
            raise RuntimeError(f"No QA items found for split={args.split}")
    logger.info("Loaded %d QA items", len(qa_items))

    config_snapshot = {
        "retriever": "graphrag",
        "human_name": retriever.human_name,
        "top_k": top_k,
        "max_hop": max_hop,
        "entity_model": cfg.get("entity_model", "en_core_web_sm"),
        "relation_window": cfg.get("relation_window", 2),
        "min_entity_freq": cfg.get("min_entity_freq", 2),
        "split": args.split,
    }
    runs = retriever.run_benchmark(qa_items, top_k=top_k, config_snapshot=config_snapshot)

    output_root = Path(args.output_root)
    run_file = output_root / "retrieval" / "graphrag_run.jsonl"
    RetrievalRun.save_run_file(runs, run_file)
    logger.info("Run file saved → %s", run_file)

    qrels_path = Path(args.qrels)
    if not qrels_path.exists():
        logger.warning("Qrels not found at %s; skipping evaluation.", qrels_path)
        return

    evaluator = RetrievalEvaluator(
        qrels_path=qrels_path,
        query_categories_path=args.query_categories if Path(args.query_categories).exists() else None,
        qa_dataset_path=qa_path, split=args.split,
    )
    bundles = evaluator.evaluate_run_file(run_file, retriever_name="graphrag")
    evaluator.save_metrics_csv(bundles, output_root / "metrics" / "graphrag_metrics.csv")

    reporter = ReportGenerator(output_root / "reports")
    reporter.generate(bundles, run_name=f"graphrag_top{top_k}_hop{max_hop}", config=config_snapshot)

    agg = next((b for b in bundles if b.query_category == "all"), None)
    if agg:
        logger.info(
            "Entity-graph results — MRR=%.4f | R@10=%.4f | nDCG@10=%.4f | latency=%.1f ms",
            agg.mrr,
            agg.recall_at_k.get(10, 0),
            agg.ndcg_at_k.get(10, 0),
            agg.avg_latency_ms,
        )


if __name__ == "__main__":
    main()
