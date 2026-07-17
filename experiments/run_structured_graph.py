#!/usr/bin/env python3
"""Build or evaluate the separate Structured Metadata Graph retriever."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evaluation.evaluator import RetrievalEvaluator
from src.evaluation.report_generator import ReportGenerator
from src.retrievers.base_retriever import RetrievalRun
from src.retrievers.structured_graph_retriever import StructuredMetadataGraphRetriever
from src.utils.io_utils import load_jsonl
from src.utils.logging_utils import get_logger, setup_logging

LOGGER = get_logger("run_structured_graph")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--qa-dataset")
    parser.add_argument("--qrels")
    parser.add_argument("--query-categories")
    parser.add_argument("--index-dir", required=True)
    parser.add_argument("--output-root", default="runs/structured_graph")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--split", choices=("all", "dev", "test", "holdout"), default="all")
    parser.add_argument("--configuration-lock", default=None)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--hop-decay", type=float, default=0.5)
    parser.add_argument("--min-entity-freq", type=int, default=2)
    parser.add_argument("--use-aliases", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--use-typed-metadata", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--use-weighted-traversal", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--use-fallback", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    setup_logging(args.log_level)
    if args.split == "holdout":
        if not args.configuration_lock:
            raise RuntimeError("Holdout evaluation requires --configuration-lock")
        from src.evaluation.holdout_lock import verify_lock
        verify_lock(args.configuration_lock, ROOT)
    chunks = load_jsonl(args.chunks)
    retriever = StructuredMetadataGraphRetriever(
        args.index_dir, max_depth=args.max_depth, hop_decay=args.hop_decay,
        min_entity_freq=args.min_entity_freq, use_aliases=args.use_aliases,
        use_typed_metadata=args.use_typed_metadata,
        use_weighted_traversal=args.use_weighted_traversal, use_fallback=args.use_fallback,
    )
    graph_path = Path(args.index_dir) / "graph.gpickle"
    if args.rebuild or not graph_path.exists():
        retriever.build_index(chunks)
    else:
        retriever.load_index()
    if len(retriever.chunk_meta) != len(chunks):
        raise RuntimeError("Structured graph index cardinality mismatch")
    if args.build_only:
        LOGGER.info("Structured graph build-only gate passed: %d chunks", len(chunks))
        return
    if not all((args.qa_dataset, args.qrels, args.query_categories)):
        raise ValueError("qa-dataset, qrels, and query-categories are required for evaluation")
    qa = load_jsonl(args.qa_dataset)
    if args.split != "all":
        qa = [item for item in qa if item.get("split") == args.split]
    if not qa:
        raise RuntimeError(f"No QA items found for split={args.split}")
    config = {
        "retriever": retriever.name, "top_k": args.top_k, "split": args.split,
        "max_depth": args.max_depth, "hop_decay": args.hop_decay,
        "use_aliases": args.use_aliases, "use_typed_metadata": args.use_typed_metadata,
        "use_weighted_traversal": args.use_weighted_traversal, "use_fallback": args.use_fallback,
    }
    runs = retriever.run_benchmark(qa, top_k=args.top_k, config_snapshot=config)
    output_root = Path(args.output_root)
    run_path = output_root / "retrieval/structured_graph_run.jsonl"
    RetrievalRun.save_run_file(runs, run_path)
    evaluator = RetrievalEvaluator(
        args.qrels, args.query_categories, qa_dataset_path=args.qa_dataset, split=args.split,
    )
    bundles = evaluator.evaluate_run_file(run_path, retriever_name="structured_graph")
    evaluator.save_metrics_csv(bundles, output_root / "metrics/structured_graph_metrics.csv")
    ReportGenerator(output_root / "reports").generate(
        bundles, "structured_metadata_graph_top10", config=config,
    )


if __name__ == "__main__":
    main()
